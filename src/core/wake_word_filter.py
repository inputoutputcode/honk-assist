"""Wake word filter for Pipecat pipeline.

Sits between STT and LLM in the pipeline. Only forwards transcripts
to the LLM when the wake word "Honk" is detected. Silently drops
all other speech to save LLM costs and avoid unwanted responses.

Pipeline: STT → WakeWordFilter → UserAggregator → LLM → TTS
"""

import os
import re
from typing import Optional

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    TranscriptionFrame,
    InterimTranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


WAKE_WORD = os.getenv("HONK_WAKE_WORD", "Honk")
WAKE_WORD_PATTERN = re.compile(
    rf"\b{re.escape(WAKE_WORD)}\b",
    re.IGNORECASE,
)


class WakeWordFilter(FrameProcessor):
    """Filters transcription frames based on wake word detection.
    
    Only passes through TranscriptionFrame when the text contains
    the wake word. All other frame types pass through unmodified.
    InterimTranscriptionFrames are always dropped (they're partial
    and don't need wake word checking).
    
    Args:
        enabled: Whether filtering is active (default: True)
        wake_word: Word to listen for (default: from env or "Honk")
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        wake_word: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._enabled = enabled and os.getenv(
            "HONK_WAKE_WORD_ENABLED", "true"
        ).lower() in ("true", "1", "yes")
        self._wake_word = wake_word or WAKE_WORD
        self._pattern = re.compile(
            rf"\b{re.escape(self._wake_word)}\b",
            re.IGNORECASE,
        )
        self._stats = {"total": 0, "passed": 0, "filtered": 0}
        
        logger.info(
            f"[WAKE-WORD] Filter initialized: "
            f"enabled={self._enabled} word='{self._wake_word}'"
        )

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames, filtering transcriptions by wake word."""
        await super().process_frame(frame, direction)

        # Only filter TranscriptionFrames (final STT output)
        if isinstance(frame, TranscriptionFrame) and self._enabled:
            self._stats["total"] += 1
            text = frame.text if hasattr(frame, "text") else str(frame)

            if self._pattern.search(text):
                self._stats["passed"] += 1
                logger.info(
                    f"[WAKE-WORD] ✅ PASS '{self._wake_word}' detected "
                    f"({self._stats['passed']}/{self._stats['total']}): "
                    f"{text[:120]}"
                )
                await self.push_frame(frame, direction)
            else:
                self._stats["filtered"] += 1
                if self._stats["filtered"] <= 10 or self._stats["filtered"] % 100 == 0:
                    logger.info(
                        f"[WAKE-WORD] ❌ FILTER no wake word "
                        f"({self._stats['filtered']}/{self._stats['total']}): "
                        f"{text[:120]}"
                    )
                # Don't push — silently drop

        elif isinstance(frame, InterimTranscriptionFrame):
            # Drop interim transcriptions — they're noisy and partial
            pass

        else:
            # All other frames pass through (audio, control, etc.)
            await self.push_frame(frame, direction)
