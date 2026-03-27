# 🪿 HonkAssist

**Voice-enabled AI meeting assistant**

> Join meetings. Listen. Speak. Remember everything.

HonkAssist is a self-hosted AI assistant that joins your video meetings with real-time voice, takes commands via Telegram, and builds persistent memory of your business over time. Powered by Claude, Deepgram, ElevenLabs, and OpenClaw.

**Status:** 🚧 Pre-alpha / In Development

---

## What It Does

- **Joins meetings** — Google Meet, Microsoft Teams, Zoom via MeetingBaas
- **Listens and speaks** — real-time voice with ~1.5s response latency
- **Telegram voice interface** — send voice notes, get voice replies
- **Persistent memory** — learns your business context across sessions
- **Turnkey operation** — runs 24/7 on a VPS, managed via Telegram

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Hetzner CPX31 VPS                        │
│                                                            │
│  ┌──────────────────┐    ┌───────────────────────────────┐ │
│  │    OpenClaw       │    │    Pipecat Voice Pipeline     │ │
│  │    (Node.js)      │    │    (Python)                   │ │
│  │                   │    │                               │ │
│  │  ┌─────────────┐ │    │  Audio ←→ Deepgram STT        │ │
│  │  │  Telegram   │ │    │  Text  → Claude Haiku         │ │
│  │  │  Bot        │ │    │  Text  → ElevenLabs TTS       │ │
│  │  └─────────────┘ │    │  Audio → Meeting speakers     │ │
│  │                   │    └───────────────────────────────┘ │
│  │  ┌─────────────┐ │                                      │
│  │  │  Memory     │ │    ┌───────────────────────────────┐ │
│  │  │  (SQLite +  │ │    │  MeetingBaas API              │ │
│  │  │  markdown)  │ │    │  (joins meetings, routes audio)│ │
│  │  └─────────────┘ │    └───────────────────────────────┘ │
│  └──────────────────┘                                      │
└────────────────────────────────────────────────────────────┘
         │                           │
         ▼                           ▼
   ┌──────────┐   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ Anthropic │   │ Deepgram │  │ElevenLabs│  │MeetingBaas│
   │ Claude API│   │ STT API  │  │ TTS API  │  │ Bot API  │
   └──────────┘   └──────────┘  └──────────┘  └──────────┘
```

## Monthly Cost Estimate

| Service | Low Usage | Medium Usage | High Usage |
|---------|-----------|--------------|------------|
| Hetzner CPX31 VPS | €15 | €15 | €15 |
| Claude API (mostly Haiku) | $15 | $30 | $50 |
| ElevenLabs TTS | $5 | $11 | $22 |
| Deepgram STT | $3 | $7 | $12 |
| MeetingBaas (5–20 hrs/mo) | $3 | $14 | $28 |
| Hetzner Storage Box (backup) | €3 | €3 | €3 |
| **Total** | **~$45/mo** | **~$85/mo** | **~$135/mo** |

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | System design, data flows, technology choices |
| [Deployment Guide](docs/deployment-guide.md) | Step-by-step from zero to running system |
| [Voice Pipeline Spec](docs/specs/voice-pipeline.md) | STT, LLM, TTS configuration and latency |
| [Meeting Bot Spec](docs/specs/meeting-bot.md) | MeetingBaas + Pipecat integration |
| [Telegram Integration](docs/specs/telegram-integration.md) | Bot setup, voice messages, commands |
| [OpenClaw Agent Setup](docs/specs/openclaw-agent.md) | Multi-agent config and memory |
| [Security](docs/specs/security.md) | VPS hardening, encryption, threat model |
| [Monitoring & Ops](docs/specs/monitoring-ops.md) | systemd, backups, runbooks |

## Tech Stack

| Component | Technology | Role |
|-----------|-----------|------|
| Agent framework | [OpenClaw](https://openclaw.com) | Orchestration, memory, Telegram |
| Voice pipeline | [Pipecat](https://github.com/pipecat-ai/pipecat) | Real-time audio routing |
| Meeting bot | [MeetingBaas](https://meetingbaas.com) | Join meetings across platforms |
| STT | [Deepgram Nova-3](https://deepgram.com) | Streaming speech-to-text |
| LLM | [Claude Haiku](https://anthropic.com) | Fast voice responses |
| TTS | [ElevenLabs Flash v2.5](https://elevenlabs.io) | Streaming text-to-speech |
| Messenger | [Telegram Bot API](https://core.telegram.org/bots/api) | User interface |

## Deployment Environments

| Environment | Purpose | Hardware | Notes |
|------------|---------|----------|-------|
| **Hetzner CPX31** | Production | 4 vCPU AMD, 8GB RAM | Clean install, single agent |
| **NVIDIA DGX Spark** | Dev/Test | ARM64, GB10 GPU, 128GB | Multi-agent (alongside Honk), local LLM available |

See the [Deployment Guide](docs/deployment-guide.md) for setup instructions for both environments.

## Quick Start

```bash
# Hetzner (production):
# 1. Provision Hetzner CPX31 with Ubuntu 24.04
# 2. Install OpenClaw + Pipecat
# 3. Configure API keys (Anthropic, Deepgram, ElevenLabs, MeetingBaas, Telegram)
# 4. Start services
sudo systemctl start openclaw pipecat

# DGX Spark (dev/test):
# 1. Add HonkAssist as second agent in existing OpenClaw config
# 2. Install Pipecat in venv
# 3. Configure API keys
# See docs/specs/openclaw-agent.md for multi-agent setup
```

## License

MIT
