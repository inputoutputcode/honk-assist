# Voice Pipeline Specification

The voice pipeline handles real-time speech processing for both meeting participation and Telegram voice messages. It converts speech to text, generates intelligent responses, and converts them back to speech.

---

## Pipeline Overview

```
Audio In → VAD → STT (Deepgram) → LLM (Claude Haiku) → TTS (ElevenLabs) → Audio Out
              ↑                                                                  │
              └──────── Interruption detection ──────────────────────────────────┘
```

All stages operate in **streaming mode** — each component begins processing as soon as data arrives from the previous stage, minimizing end-to-end latency.

---

## Speech-to-Text: Deepgram Nova-3

### Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Model | `nova-3` | Best streaming latency + accuracy balance |
| Mode | Streaming (WebSocket) | Real-time processing, ~150ms first word |
| Language | `en` (configurable) | Primary language |
| Diarization | `diarize=true` | Speaker identification in meetings |
| Endpointing | `endpointing=300` | 300ms silence to finalize utterance |
| Interim results | `interim_results=true` | Show partial transcripts for responsiveness |
| Punctuation | `punctuate=true` | Cleaner text for LLM processing |
| Smart format | `smart_format=true` | Numbers, dates, currency formatting |
| Encoding | `linear16` / `opus` | PCM for meetings, Opus for Telegram |
| Sample rate | `16000` | Standard for speech recognition |

### Streaming API Connection

```python
# Deepgram WebSocket URL
wss://api.deepgram.com/v1/listen?
  model=nova-3&
  diarize=true&
  endpointing=300&
  interim_results=true&
  punctuate=true&
  smart_format=true&
  encoding=linear16&
  sample_rate=16000
```

### Performance Characteristics

| Metric | Value |
|--------|-------|
| First word latency | ~150ms |
| Full transcript latency | <300ms after utterance end |
| Word Error Rate (WER) | ~6.8% (English) |
| Pricing | $0.0043/min (pay-as-you-go) |
| Diarization latency overhead | Minimal (~50ms) |

### Why Deepgram?

- **Fastest streaming STT available** — 150ms first word beats all competitors
- **Built-in diarization** — no separate service needed, no GPU required
- **Cost-effective** — cheapest per-minute among major providers
- Alternatives considered: OpenAI Whisper (batch only, 1-2s), Google Cloud STT (more expensive), AssemblyAI (comparable but pricier)

---

## LLM: Claude Haiku (Voice) / Sonnet (Text)

### Model Routing

| Context | Model | Rationale |
|---------|-------|-----------|
| Meeting voice responses | Claude 4.5 Haiku | ~660ms TTFB, fast enough for conversation |
| Telegram voice responses | Claude 4.5 Haiku | Same speed requirement |
| Telegram text responses | Claude 4.5 Sonnet | Better reasoning, latency less critical |
| Post-meeting summaries | Claude 4.5 Sonnet | Quality over speed |
| Memory/context processing | Claude 4.5 Sonnet | Complex analysis tasks |

### Voice Response Prompt Strategy

For meeting contexts, the system prompt emphasizes:

```
- Be concise (1-3 sentences for most responses)
- Respond only when directly addressed or when you have valuable input
- Summarize rather than repeat
- Say "I don't know" rather than guessing
- Announce yourself when joining: "Hi, I'm [Name]'s AI assistant. I'll be taking notes."
```

### "Should I Respond?" Gate

Not every transcript chunk needs a voice response. A lightweight gate determines whether to respond:

1. **Always respond:** Direct questions, name mentions, explicit requests
2. **Sometimes respond:** Topic changes, factual corrections, action items
3. **Never respond:** Casual banter, agreement with others, background conversation

This gate runs as a fast Claude Haiku check before generating a full response, reducing unnecessary interruptions.

### Performance Characteristics

| Metric | Haiku | Sonnet |
|--------|-------|--------|
| Time to First Token (TTFT) | ~660ms | ~1.1-1.2s |
| Output speed | ~96 tokens/s | ~41 tokens/s |
| Input cost | $1/M tokens | $3/M tokens |
| Output cost | $5/M tokens | $15/M tokens |

### Optimization Techniques

- **Streaming:** Response tokens sent to TTS as they arrive
- **Short system prompts:** Minimize input token count for voice
- **Prompt caching:** Cache system prompt + recurring context
- **Sentence-level TTS:** Start speaking the first sentence while generating the rest

---

## TTS: ElevenLabs Flash v2.5

### Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Model | `eleven_flash_v2_5` | Fastest model, ~75ms model latency |
| Streaming | Enabled | Send text chunks, receive audio chunks |
| Voice ID | Custom (selected during setup) | Consistent identity across meetings and Telegram |
| Output format | `mp3_44100_128` (meetings) / `ogg_opus` (Telegram) | Platform-appropriate formats |
| Stability | 0.5 | Balance between expressive and stable |
| Similarity boost | 0.75 | Close to chosen voice identity |
| Style | 0 | Neutral for professional context |

### Streaming Flow

```python
# Text arrives sentence-by-sentence from LLM
# Each sentence is sent to ElevenLabs streaming endpoint
# Audio chunks are returned and played immediately

POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream
Content-Type: application/json

{
  "text": "Here's what I think about that proposal.",
  "model_id": "eleven_flash_v2_5",
  "voice_settings": {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0
  }
}
```

### Telegram Voice Format

Telegram requires ogg/opus format for native voice message display:

```bash
# Convert ElevenLabs output to Telegram-compatible format
ffmpeg -i input.mp3 -ac 1 -acodec libopus -b:a 128k output.ogg
```

### Performance Characteristics

| Metric | Value |
|--------|-------|
| Model latency | ~75ms |
| End-to-end TTFB | ~135ms |
| Audio quality | High (professional voice) |
| Pricing | ~$0.18/1K characters (~$0.30/min of speech) |

### Why ElevenLabs?

- **Flash v2.5 is the fastest** high-quality TTS available (~75ms)
- Voice cloning support for consistent identity
- Excellent streaming API
- Alternative considered: Cartesia Sonic 3 (~40-95ms, cheaper, but lower quality and fewer voice options)

---

## Latency Budget

### Target: <1.5s to first audio output

| Stage | Budget | Notes |
|-------|--------|-------|
| Audio capture + VAD + buffering | 100ms | VAD endpointing delay |
| STT streaming + finalization | 400ms | Deepgram Nova-3 with 300ms endpointing |
| Network overhead | 50ms | VPS ↔ cloud APIs |
| LLM TTFT (Claude Haiku) | 700ms | Time to first token, streaming |
| TTS TTFB (ElevenLabs Flash) | 150ms | Time to first audio chunk |
| Audio playback buffer | 50ms | Small buffer before playback |
| **Total** | **~1,450ms** | Within 1.5s target |

### Breakdown by Scenario

| Scenario | Expected Latency | Notes |
|----------|-----------------|-------|
| Meeting: direct question → voice reply | ~1.5s | Full pipeline |
| Telegram: voice note → voice reply | ~3-5s | Non-real-time, includes file download/upload |
| Telegram: text → text reply | ~1-2s | No STT/TTS overhead |
| Meeting: "should I respond?" gate says no | ~0ms | No output generated |

---

## Voice Activity Detection (VAD)

### Endpointing Strategy

VAD determines when a speaker has finished talking and it's time to process.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Endpointing threshold | 300ms | 300ms of silence = utterance complete |
| Min speech duration | 100ms | Ignore very short sounds (coughs, etc.) |
| Energy threshold | Adaptive | Adjust to room noise level |

**300ms endpointing** is a balance:
- Too short (100ms): Cuts off mid-sentence pauses → fragmented responses
- Too long (500ms+): Adds unnecessary delay before processing begins
- 300ms catches natural sentence endings while tolerating brief pauses

### In Meetings

- Deepgram handles VAD natively with `endpointing=300`
- Interim results show partial transcripts (useful for "I hear you" signals)
- Final results trigger the LLM processing pipeline

---

## Interruption Handling

When a meeting participant starts talking while HonkAssist is speaking:

1. **Detect:** VAD detects new speech input during TTS playback
2. **Stop:** Immediately halt TTS audio output
3. **Listen:** Process the new speech through STT
4. **Respond:** Generate new response incorporating the interruption context

Pipecat handles this natively with its `UserStartedSpeakingFrame` / `UserStoppedSpeakingFrame` events:

```python
# Pipecat interruption handling (simplified)
@pipeline.event
async def on_user_started_speaking(frame):
    # Stop current TTS playback
    await tts_service.cancel()
    # Clear pending LLM output
    await llm_service.cancel()
```

---

## Speaker Diarization

### Real-Time (During Meetings)

- **Provider:** Deepgram built-in (`diarize=true`)
- **Output:** Speaker IDs (speaker_0, speaker_1, ...) with each transcript segment
- **Accuracy:** Good for 2-6 speakers, degrades with more
- **Latency overhead:** Minimal (~50ms)

### Speaker Name Mapping

Deepgram provides numeric speaker IDs. To map to real names:

1. **MeetingBaas participant list:** When available, map speaker IDs to meeting participant names
2. **Voice enrollment:** Optional — enroll known voices for automatic identification
3. **Manual correction:** Ask "Who was that?" if unsure

### Post-Meeting Refinement

For higher accuracy on saved transcripts:

- Re-process meeting recording with WhisperX (Whisper + pyannote) for better diarization
- This is batch processing — runs after the meeting, not real-time
- Improves speaker attribution accuracy from ~80% to ~95%

---

## Audio Format Reference

| Context | Format | Sample Rate | Channels | Codec |
|---------|--------|-------------|----------|-------|
| Meeting input (MeetingBaas) | PCM | 16kHz | Mono | linear16 |
| Deepgram STT input | PCM/Opus | 16kHz | Mono | linear16/opus |
| ElevenLabs TTS output | MP3 | 44.1kHz | Mono | mp3 |
| Telegram voice (receive) | OGG | 48kHz | Mono | opus |
| Telegram voice (send) | OGG | 48kHz | Mono | opus |
| Meeting output (MeetingBaas) | PCM | 16kHz | Mono | linear16 |

---

## Cost Estimates

| Component | Rate | 10 hrs/mo meetings | 40 hrs/mo meetings |
|-----------|------|--------------------|--------------------|
| Deepgram STT | $0.0043/min | ~$2.60 | ~$10.30 |
| Claude Haiku (voice) | ~$0.001/response | ~$5 | ~$20 |
| ElevenLabs TTS | ~$0.30/min output | ~$5 | ~$20 |
| **Voice pipeline total** | | **~$12.60/mo** | **~$50.30/mo** |

*Estimates assume the agent speaks ~15-20% of meeting time and averages 2-3 sentence responses.*
