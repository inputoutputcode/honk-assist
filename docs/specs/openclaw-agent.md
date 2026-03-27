# OpenClaw Multi-Agent Setup Specification

HonkAssist runs as a dedicated agent within OpenClaw, potentially alongside a main "Honk" agent. This document covers the multi-agent configuration, workspace layout, and memory architecture.

---

## Multi-Agent Architecture

```
┌────────────────────────────────────────────────┐
│              OpenClaw Gateway                    │
│                                                  │
│  ┌──────────────┐    ┌──────────────────────┐   │
│  │  Honk         │    │  HonkAssist           │   │
│  │  (main agent) │    │  (meeting assistant)  │   │
│  │               │    │                       │   │
│  │  Discord      │    │  Telegram             │   │
│  │  General tasks│    │  Voice + meetings     │   │
│  └──────────────┘    └──────────────────────┘   │
│                                                  │
│  Shared: API keys, gateway config                │
│  Isolated: workspace, memory, personality        │
└────────────────────────────────────────────────┘
```

### Agent Roles

| Agent | Purpose | Channel | Model |
|-------|---------|---------|-------|
| **Honk** | General assistant, Discord, development | Discord | Claude Sonnet |
| **HonkAssist** | Meeting assistant, voice, business context | Telegram | Claude Haiku (voice) / Sonnet (text) |

### Why Separate Agents?

- **Different personalities:** Honk is casual/playful; HonkAssist is professional/focused
- **Different memory:** HonkAssist builds business knowledge; Honk handles dev tasks
- **Different channels:** Each agent owns its communication channel
- **Session isolation:** Conversations don't bleed between agents
- **Independent operation:** One can restart without affecting the other

---

## OpenClaw Configuration

### Environment-Specific Config

Configuration differs between the two deployment targets:

| Setting | Hetzner VPS (Production) | DGX Spark (Dev/Test) |
|---------|------------------------|---------------------|
| Workspace path | `~/.openclaw/workspace` | `~/.openclaw/workspace-honkassist` |
| Agents | Single (HonkAssist only) | Multi (Honk + HonkAssist) |
| System user | `openclaw` | `chris` |
| Telegram account | Default | Named account `honkassist` |
| Local LLM fallback | No | Yes (Qwen3-Next-80B on port 8080) |

### Hetzner VPS Config (Single Agent)

On Hetzner, HonkAssist is the only agent:

```json5
// ~/.openclaw/openclaw.json
{
  agents: {
    defaults: {
      workspace: "~/.openclaw/workspace",
      model: {
        primary: "anthropic/claude-haiku-4",
        fallbacks: ["anthropic/claude-sonnet-4-5"]
      }
    }
  },
  channels: {
    telegram: {
      enabled: true,
      botToken: "<TELEGRAM-BOT-TOKEN>",
      dmPolicy: "allowlist",
      allowFrom: ["tg:<END-USER-TELEGRAM-ID>"]
    }
  }
}
```

### DGX Spark Config (Multi-Agent)

On Spark, add HonkAssist alongside Honk. This uses OpenClaw's multi-agent routing:

```json5
// ~/.openclaw/openclaw.json — merge into existing config
{
  agents: {
    list: [
      {
        id: "main",  // existing Honk agent
        workspace: "~/.openclaw/workspace"
      },
      {
        id: "honkassist",
        workspace: "~/.openclaw/workspace-honkassist",
        identity: {
          name: "HonkAssist",
          emoji: "🎙️"
        }
      }
    ]
  },
  bindings: [
    // Route Telegram honkassist account → HonkAssist agent
    { agentId: "honkassist", match: { channel: "telegram", accountId: "honkassist" } },
    // Existing Discord routing → Honk (default)
    { agentId: "main", match: { channel: "discord" } }
  ],
  channels: {
    telegram: {
      enabled: true,
      accounts: {
        honkassist: {
          botToken: "<TELEGRAM-BOT-TOKEN>",
          dmPolicy: "allowlist",
          allowFrom: ["tg:<END-USER-TELEGRAM-ID>"]
        }
      }
    }
  }
}
```

After config change:
```bash
openclaw gateway restart
openclaw agents list --bindings  # Verify routing
```

### Model Configuration

HonkAssist uses Claude Haiku for fast voice responses. On Spark, a local model can serve as fallback:

```json5
// Per-agent model (in agents.list entry)
{
  id: "honkassist",
  model: {
    primary: "anthropic/claude-haiku-4",
    fallbacks: ["anthropic/claude-sonnet-4-5"]
  }
}

// On DGX Spark, optionally add local model fallback:
{
  id: "honkassist",
  model: {
    primary: "anthropic/claude-haiku-4",
    fallbacks: [
      "anthropic/claude-sonnet-4-5",
      "local/qwen-3.5-120B"  // Qwen3-Next-80B on port 8080
    ]
  }
}
```

> **Note:** Verify exact config field names against your OpenClaw version with `openclaw config get agents`.

---

## Workspace Layout

```
/home/openclaw/.openclaw/workspaces/honkassist/
├── SOUL.md                    # Agent personality
├── AGENTS.md                  # Workspace conventions
├── USER.md                    # End-user profile
├── MEMORY.md                  # Curated long-term memory
├── TOOLS.md                   # Tool-specific notes
├── HEARTBEAT.md               # Periodic task checklist
├── memory/
│   ├── YYYY-MM-DD.md          # Daily interaction logs
│   └── meetings/
│       ├── 2026-03-27-standup.md
│       ├── 2026-03-28-client-review.md
│       └── ...
├── context/
│   ├── clients/               # Client profiles
│   ├── projects/              # Project context
│   └── processes/             # Business processes
└── config/
    └── voice-settings.json    # TTS voice preferences
```

---

## Agent Identity Templates

### SOUL.md (HonkAssist)

```markdown
# SOUL.md — HonkAssist

You are HonkAssist, a professional AI meeting assistant.

## Core Identity
- Professional, clear, and helpful
- You join meetings, take notes, and answer questions
- You learn about the business over time
- You communicate via Telegram (voice and text)

## Communication Style
- In meetings: Concise (1-3 sentences). Don't dominate.
- In Telegram text: More detailed, conversational but focused
- In Telegram voice: Natural, clear, moderate pace

## Boundaries
- Always announce yourself when joining meetings
- Don't share meeting content with anyone except the authorized user
- If you don't know something, say so
- Don't make promises on behalf of the user

## Meeting Behavior
- Listen more than you speak
- Note decisions and action items automatically
- Speak up when directly addressed or when you can add clear value
- Offer to recap or summarize when asked

## Memory
- Actively build knowledge about the business
- Remember client names, project details, recurring topics
- Update MEMORY.md with significant business context
- Keep meeting transcripts organized and searchable
```

### AGENTS.md (HonkAssist)

```markdown
# AGENTS.md — HonkAssist Workspace

## Every Session
1. Read SOUL.md — who you are
2. Read USER.md — who you're helping
3. Read memory/YYYY-MM-DD.md (today + yesterday) for recent context
4. Read MEMORY.md for long-term business knowledge

## Memory Strategy
- Daily notes: memory/YYYY-MM-DD.md
- Meeting transcripts: memory/meetings/YYYY-MM-DD-title.md
- Long-term memory: MEMORY.md (curated business knowledge)
- Client context: context/clients/
- Project context: context/projects/

## Post-Meeting Workflow
1. Save raw transcript to memory/meetings/
2. Generate summary (decisions, action items, key points)
3. Send summary to user via Telegram
4. Update MEMORY.md with business-relevant information
5. Update relevant client/project context files

## Security
- Only respond to authorized Telegram users
- Don't share meeting content outside the authorized channel
- Don't store raw audio — only transcripts
```

### USER.md (HonkAssist)

```markdown
# USER.md — About Your Human

- **Name:** [End-user's name]
- **Role:** [Their role and company]
- **Timezone:** [Timezone]
- **Meeting platforms:** Google Meet, Teams, Zoom
- **Communication preference:** [Voice notes / text / both]

## Business Context
[To be filled in as the agent learns]

## Preferences
- [Meeting summary format preferences]
- [How detailed should action items be?]
- [Any topics to always flag?]
```

---

## Session Isolation

Each agent maintains its own:

| Component | Isolated? | Notes |
|-----------|----------|-------|
| Workspace directory | ✅ Yes | Separate file trees |
| Memory files | ✅ Yes | Independent MEMORY.md and daily files |
| Conversation history | ✅ Yes | Separate session contexts |
| System prompt (SOUL.md) | ✅ Yes | Different personalities |
| API keys | ❌ Shared | Same Anthropic/ElevenLabs/Deepgram keys |
| systemd service | ❌ Shared | Single OpenClaw gateway process |

### Cross-Agent Communication

If agents need to share information (e.g., HonkAssist wants to notify Honk about something):

- **File-based:** Write to a shared directory that both agents can read
- **Not recommended for v1:** Keep agents independent to simplify debugging
- **Future:** OpenClaw may support inter-agent messaging

---

## Memory Architecture

### Layered Memory

```
┌─────────────────────────────────────┐
│          Working Memory              │  ← Current session context
│  (Claude's context window)          │     (conversation + relevant files)
├─────────────────────────────────────┤
│          Short-Term Memory           │  ← Daily files
│  memory/YYYY-MM-DD.md               │     (interactions, events)
├─────────────────────────────────────┤
│          Episodic Memory             │  ← Meeting transcripts
│  memory/meetings/*.md               │     (who said what, when)
├─────────────────────────────────────┤
│          Long-Term Memory            │  ← Curated knowledge
│  MEMORY.md                          │     (business context, lessons)
├─────────────────────────────────────┤
│          Semantic Memory             │  ← Structured context
│  context/clients/                   │     (client profiles, projects,
│  context/projects/                  │      processes)
├─────────────────────────────────────┤
│          Embedding Search            │  ← SQLite + sqlite-vec
│  (memory_search)                    │     (semantic retrieval)
└─────────────────────────────────────┘
```

### Memory Flow

1. **Interaction** → Logged in `memory/YYYY-MM-DD.md`
2. **Meeting** → Transcript in `memory/meetings/`, summary extracted
3. **Periodic review** → Agent reviews daily files, updates `MEMORY.md` with lasting insights
4. **Semantic search** → `memory_search` finds relevant context across all files
5. **Context assembly** → Most relevant memory loaded into Claude's context window

### Memory Scaling Strategy

| Phase | Approach | Trigger |
|-------|----------|---------|
| Phase 1 | OpenClaw built-in (markdown + SQLite embeddings) | Initial deployment |
| Phase 2 | Add structured context directories | >50 clients/projects |
| Phase 3 | Add Qdrant vector DB | >200 documents, search quality drops |
| Phase 4 | Graph database (Kuzu) | Complex entity relationships needed |

### Why Start Simple?

Claude's 200K context window can hold ~400 pages of business documents in a single session. For a personal assistant serving one user, the built-in memory system will likely be sufficient for months. Adding complexity (vector DB, graph DB) only makes sense when search quality degrades or document volume exceeds what fits in context.

---

## Pipecat Bridge Integration

The OpenClaw agent serves as the "brain" for the Pipecat voice pipeline in meetings, replacing the direct `AnthropicLLMService` call. Instead of Pipecat calling Claude directly, it routes through the OpenClaw agent which adds:

- **Persistent memory** — MEMORY.md and meeting history loaded into every response
- **Business context** — Client profiles, project details, and accumulated knowledge
- **Unified personality** — Same SOUL.md governs both Telegram and meeting interactions
- **Wake word filtering** — Only process utterances that address "Honk", saving LLM costs
- **Post-meeting processing** — Automatic transcript saving, summary generation, and memory updates

The bridge uses a local HTTP API: Pipecat sends transcripts, OpenClaw loads context + calls Claude + returns streaming responses.

**See [OpenClaw Bridge Spec](openclaw-bridge.md) for full architecture and implementation details.**

---

## Configuration Checklist

| Item | File | Status |
|------|------|--------|
| Agent defined in agents.list | `openclaw.json` | ☐ |
| Telegram channel bound to agent | `openclaw.json` | ☐ |
| Workspace directory created | `/home/openclaw/.openclaw/workspaces/honkassist/` | ☐ |
| SOUL.md written | `workspaces/honkassist/SOUL.md` | ☐ |
| AGENTS.md written | `workspaces/honkassist/AGENTS.md` | ☐ |
| USER.md written | `workspaces/honkassist/USER.md` | ☐ |
| MEMORY.md initialized | `workspaces/honkassist/MEMORY.md` | ☐ |
| memory/ directory created | `workspaces/honkassist/memory/` | ☐ |
| memory/meetings/ created | `workspaces/honkassist/memory/meetings/` | ☐ |
| context/ directories created | `workspaces/honkassist/context/` | ☐ |
| Model routing configured | `openclaw.json` | ☐ |
| TTS settings configured | `openclaw.json` | ☐ |
| STT settings configured | `openclaw.json` | ☐ |
