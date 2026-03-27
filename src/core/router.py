"""Routes messages between clients and Pipecat."""

from core.connection import registry
from core.converter import converter
from meetingbaas_pipecat.utils.logger import logger


class MessageRouter:
    """Routes messages between clients and Pipecat."""

    def __init__(self, registry, converter, logger=logger):
        self.registry = registry
        self.converter = converter
        self.logger = logger
        self.closing_clients = set()  # Track clients that are in the process of closing

    def mark_closing(self, client_id: str):
        """Mark a client as closing to prevent sending more data to it."""
        self.closing_clients.add(client_id)
        self.logger.debug(f"Marked client {client_id} as closing")

    async def send_binary(self, message: bytes, client_id: str):
        """Send binary data to a client."""
        if client_id in self.closing_clients:
            self.logger.debug(f"Skipping send to closing client {client_id}")
            return

        client = self.registry.get_client(client_id)
        if client:
            try:
                await client.send_bytes(message)
                self.logger.debug(f"Sent {len(message)} bytes to client {client_id}")
            except Exception as e:
                self.logger.debug(f"Error sending binary to client {client_id}: {e}")

    async def send_text(self, message: str, client_id: str):
        """Send text message to a specific client."""
        if client_id in self.closing_clients:
            self.logger.debug(f"Skipping send_text to closing client {client_id}")
            return

        client = self.registry.get_client(client_id)
        if client:
            try:
                await client.send_text(message)
                self.logger.debug(
                    f"Sent text message to client {client_id}: {message[:100]}..."
                )
            except Exception as e:
                self.logger.debug(f"Error sending text to client {client_id}: {e}")

    async def broadcast(self, message: str):
        """Broadcast text message to all clients."""
        for client_id, connection in self.registry.active_connections.items():
            if client_id not in self.closing_clients:
                try:
                    await connection.send_text(message)
                    self.logger.debug(f"Broadcast text message to client {client_id}")
                except Exception as e:
                    self.logger.debug(f"Error broadcasting to client {client_id}: {e}")

    async def send_to_pipecat(self, message: bytes, client_id: str):
        """Convert raw audio to Protobuf frame and send to Pipecat.
        
        Includes silence detection: frames with RMS below SILENCE_THRESHOLD
        are dropped to avoid forwarding empty/silent audio to the pipeline.
        """
        import struct, math
        if client_id in self.closing_clients:
            self.logger.info(
                f"[ROUTER] Skipping send to Pipecat for closing client {client_id}"
            )
            return

        # Audio level analysis, silence filtering, and amplification
        GAIN = 20  # Amplify audio aggressively — Google Meet audio is very quiet
        SILENCE_THRESHOLD = 5  # RMS below this = true silence (lowered from 30 — Meet audio is ~33 RMS for speech)
        if not hasattr(self, '_audio_stats'):
            self._audio_stats = {}
        stats = self._audio_stats.setdefault(client_id, {
            'count': 0, 'max_rms': 0, 'total_rms': 0,
            'silent_frames': 0, 'speech_frames': 0
        })
        stats['count'] += 1
        if len(message) >= 4:
            try:
                samples = list(struct.unpack(f'<{len(message)//2}h', message))
                rms = math.sqrt(sum(s*s for s in samples) / len(samples))
                stats['total_rms'] += rms
                if rms > stats['max_rms']:
                    stats['max_rms'] = rms

                # --- Silence filter: skip frames that are silence ---
                if rms < SILENCE_THRESHOLD:
                    stats['silent_frames'] += 1
                    # Log periodically so we know silence is being detected
                    if stats['silent_frames'] <= 3 or stats['silent_frames'] % 2000 == 0:
                        self.logger.info(
                            f"[SILENCE-SKIP] frame#{stats['count']} RMS={rms:.1f} "
                            f"(threshold={SILENCE_THRESHOLD}) silent={stats['silent_frames']} "
                            f"speech={stats['speech_frames']} ({client_id[:8]})"
                        )
                    return  # Don't forward silence to Pipecat

                stats['speech_frames'] += 1
                if stats['speech_frames'] <= 5 or stats['speech_frames'] % 500 == 0:
                    avg_rms = stats['total_rms'] / stats['count']
                    self.logger.info(
                        f"[AUDIO-SPEECH] frame#{stats['count']} RMS={rms:.1f} avg={avg_rms:.1f} "
                        f"max={stats['max_rms']:.1f} peak={max(abs(s) for s in samples)} "
                        f"GAIN={GAIN}x silent={stats['silent_frames']} speech={stats['speech_frames']} "
                        f"({client_id[:8]})"
                    )
                # Amplify speech samples
                amplified = [max(-32768, min(32767, s * GAIN)) for s in samples]
                message = struct.pack(f'<{len(amplified)}h', *amplified)
            except Exception:
                pass

        pipecat = self.registry.get_pipecat(client_id)
        if not pipecat:
            # Log once per 1000 attempts
            if not hasattr(self, '_missing_count'):
                self._missing_count = {}
            self._missing_count[client_id] = self._missing_count.get(client_id, 0) + 1
            if self._missing_count[client_id] <= 3 or self._missing_count[client_id] % 1000 == 0:
                available = list(self.registry.pipecat_connections.keys())
                self.logger.info(f"[ROUTER] No Pipecat connection for {client_id}. Available pipecat connections: {available}. Miss count: {self._missing_count[client_id]}")
            return
        if pipecat:
            try:
                serialized_frame = self.converter.raw_to_protobuf(message)
                await pipecat.send_bytes(serialized_frame)
                if not hasattr(self, '_fwd_count'):
                    self._fwd_count = {}
                self._fwd_count[client_id] = self._fwd_count.get(client_id, 0) + 1
                if self._fwd_count[client_id] <= 5 or self._fwd_count[client_id] % 500 == 0:
                    self.logger.info(
                        f"[ROUTER-FWD] Forwarded {len(message)}→{len(serialized_frame)} bytes to Pipecat for {client_id} (total: {self._fwd_count[client_id]})"
                    )
            except Exception as e:
                # Check for connection closed errors specifically
                if "close" in str(e).lower() or "closed" in str(e).lower():
                    self.logger.debug(
                        f"Connection closed when sending to Pipecat for client {client_id}: {e}"
                    )
                    self.mark_closing(client_id)
                else:
                    self.logger.error(f"Error sending to Pipecat: {str(e)}")

    async def send_from_pipecat(self, message: bytes, client_id: str):
        """Extract audio from Protobuf frame and send to client."""
        if client_id in self.closing_clients:
            self.logger.debug(
                f"Skipping send from Pipecat for closing client {client_id}"
            )
            return

        client = self.registry.get_client(client_id)
        if client:
            try:
                audio_data = self.converter.protobuf_to_raw(message)
                if audio_data:
                    if not hasattr(self, '_out_stats'):
                        self._out_stats = {}
                    ostats = self._out_stats.setdefault(client_id, {'count': 0})
                    ostats['count'] += 1
                    if ostats['count'] <= 10 or ostats['count'] % 200 == 0:
                        import struct, math
                        try:
                            samples = struct.unpack(f'<{len(audio_data)//2}h', audio_data)
                            rms = math.sqrt(sum(s*s for s in samples) / len(samples))
                            peak = max(abs(s) for s in samples)
                            nonzero = sum(1 for s in samples if s != 0)
                            hex_preview = audio_data[:32].hex()
                            self.logger.info(f"[AUDIO-OUT] #{ostats['count']} {len(audio_data)}B RMS={rms:.0f} peak={peak} nz={nonzero}/{len(samples)} hex={hex_preview} → {client_id[:8]}")
                        except Exception:
                            self.logger.info(f"[AUDIO-OUT] #{ostats['count']} {len(audio_data)}B hex={audio_data[:32].hex()} → {client_id[:8]}")
                    await client.send_bytes(audio_data)
                    self.logger.debug(
                        f"Forwarded audio ({len(audio_data)} bytes) from Pipecat to client {client_id}"
                    )
            except Exception as e:
                # Check for connection closed errors specifically
                if "close" in str(e).lower() or "closed" in str(e).lower():
                    self.logger.debug(
                        f"Connection closed when sending to client {client_id}: {e}"
                    )
                    self.mark_closing(client_id)
                else:
                    self.logger.error(f"Error processing Pipecat message: {str(e)}")


# Create a singleton instance
router = MessageRouter(registry, converter)
