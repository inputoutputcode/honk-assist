# Security Specification

HonkAssist handles confidential business discussions. This document covers the security architecture, hardening measures, data policies, and threat model.

---

## Threat Model Summary

### What We're Protecting

- Business meeting content (transcripts, summaries, action items)
- Client and project information stored in memory
- API credentials (Anthropic, Deepgram, ElevenLabs, MeetingBaas, Telegram)
- Voice data (recordings, TTS output)

### Threat Actors

| Actor | Motivation | Capability |
|-------|-----------|------------|
| Opportunistic attacker | Crypto mining, botnet | Automated scanning, known exploits |
| Targeted attacker | Business intelligence | Custom attacks, social engineering |
| Cloud provider insider | Curiosity, coercion | Access to API data in transit |
| Telegram | Data mining, legal compliance | Access to message content |
| Rogue meeting participant | Disrupt or extract info | Social engineering, prompt injection |

### Risk Acceptance

| Risk | Decision | Rationale |
|------|----------|-----------|
| Telegram not E2E encrypted | **Accepted** | Convenience > perfect privacy for this use case |
| Cloud STT/TTS data exposure | **Accepted** | Standard for cloud AI; no self-hosted alternative at this scale |
| Anthropic 7-day data retention | **Accepted** | Data not used for training; 7 days is reasonable |
| VPS physical security | **Accepted** | Hetzner data centers are ISO 27001 certified |

---

## VPS Hardening

### SSH Hardening

```bash
# /etc/ssh/sshd_config.d/hardening.conf
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
```

- **Key-only authentication** — no password login possible
- **Root login disabled** — must use `openclaw` service user
- **Max 3 auth attempts** — limits brute-force per connection
- **Client keepalive** — drops idle connections after 10 minutes

### Firewall (ufw)

```bash
# Default policy
ufw default deny incoming
ufw default allow outgoing

# Allow SSH only from Tailscale
ufw allow in on tailscale0 to any port 22

# No other inbound ports needed
# Telegram, MeetingBaas, Deepgram, etc. are all outbound connections
```

**Key insight:** HonkAssist requires **zero inbound ports** from the public internet. All external services (Telegram Bot API, cloud APIs) are reached via outbound HTTPS/WebSocket connections. Only Tailscale VPN provides SSH access.

### fail2ban

```ini
# /etc/fail2ban/jail.local
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
```

- Bans IPs after 3 failed SSH attempts
- 1-hour ban duration
- Effective even with Tailscale (defense in depth)

### Tailscale VPN

```bash
# Install
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Lock down SSH to Tailscale only
sudo ufw delete allow ssh
sudo ufw allow in on tailscale0 to any port 22
```

**Benefits:**
- No public SSH port — invisible to port scanners
- WireGuard-based encryption for all management traffic
- MagicDNS for easy access (`ssh honk-assist`)
- Free for personal use (up to 100 devices)
- ACL support for multi-user access control

### Automatic Security Updates

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

Configuration (`/etc/apt/apt.conf.d/50unattended-upgrades`):
- Security updates only (stable, low risk)
- Optional auto-reboot at 3 AM if kernel update requires it
- Email notification on failures (if configured)

---

## Data Encryption

### At Rest: gocryptfs

Sensitive data (memory files, transcripts, context) is stored in an encrypted directory:

```bash
# Structure
/home/openclaw/.openclaw-encrypted/   # Encrypted ciphertext (persistent)
/home/openclaw/.openclaw-data/        # Decrypted mountpoint (runtime only)
```

**Properties:**
- AES-256-GCM encryption
- File-level encryption (each file encrypted individually)
- Directory and filename encryption
- Master key derived from password via scrypt

**Trade-off:** The encrypted directory must be manually mounted after each VPS reboot. The tech user SSHs in and runs:

```bash
gocryptfs /home/openclaw/.openclaw-encrypted /home/openclaw/.openclaw-data
# Enter password when prompted
```

This is intentional — it prevents automatic access to sensitive data if the VPS is compromised while powered off.

### In Transit

| Connection | Encryption | Notes |
|------------|-----------|-------|
| SSH management | WireGuard (Tailscale) + SSH | Double encrypted |
| Telegram Bot API | HTTPS (TLS 1.3) | Telegram's infrastructure |
| Anthropic API | HTTPS (TLS 1.3) | Standard API encryption |
| Deepgram WebSocket | WSS (TLS) | Encrypted streaming |
| ElevenLabs API | HTTPS (TLS 1.3) | Standard API encryption |
| MeetingBaas API | HTTPS (TLS 1.3) | Standard API encryption |

All API connections use TLS encryption. No plaintext data leaves the VPS.

---

## API Data Retention Policies

### Anthropic (Claude)

| Policy | Detail |
|--------|--------|
| API data retention | **7 days** (reduced from 30 days, Sept 2025) |
| Used for training | **No** (unless explicitly opted in) |
| Human review | Only if flagged by automated safety systems |
| Zero-retention option | Available for Enterprise customers |
| Data location | US-based infrastructure |

**Assessment:** ✅ Acceptable. 7-day retention for abuse monitoring is industry standard. Data is not used for training.

**Future:** When Anthropic offers zero-data-retention for non-Enterprise customers at a reasonable cost, upgrade to it.

### Deepgram

| Policy | Detail |
|--------|--------|
| Audio retention | Not retained after processing (streaming) |
| Transcript retention | Not retained for streaming API |
| Used for training | No (API customers) |
| SOC 2 compliance | Yes |

**Assessment:** ✅ Good. Streaming API processes audio in real-time without storage.

### ElevenLabs

| Policy | Detail |
|--------|--------|
| Generated audio | Stored in account history by default |
| Deletion | Available via API (immediate) |
| Enterprise zero-retention | Available |
| Text input retention | Stored with generation |

**Assessment:** ⚠️ Moderate. Generated audio is stored until deleted.

**Mitigation:**
- Delete generations via API after delivery to user
- Don't include raw sensitive data in TTS text — summarize first
- Consider: voice messages like "call client X about deal Y" are relatively low-risk

### MeetingBaas

| Policy | Detail |
|--------|--------|
| Audio/video | Processed in real-time, configurable retention |
| Transcripts | Available via API, configurable retention |
| Data location | Check current ToS |

**Mitigation:** Configure MeetingBaas to not retain recordings after delivery. Process transcripts immediately and store only on VPS.

---

## Telegram Privacy

### What Telegram Can See

- All text messages between user and bot
- All voice messages (audio content)
- Message metadata (timestamps, user IDs, IP addresses)
- Bot token and API calls

### What Telegram Cannot See

- Meeting audio (routed through MeetingBaas, not Telegram)
- Memory files on the VPS
- API credentials
- Internal processing (LLM prompts, context assembly)

### Mitigations

1. **Sensitive discussions:** For highly sensitive topics, prefer in-meeting voice (routed through MeetingBaas, not Telegram)
2. **No Secret Chats:** Telegram bots cannot use Secret Chats (E2E encrypted) — this is a platform limitation
3. **Allowlist:** Only the authorized user can message the bot
4. **Private bot:** Bot is not listed in any public bot directory

### Risk Assessment

For a personal AI assistant handling typical business discussions, Telegram's server-side encryption is **acceptable**. The primary concern is Telegram's access to message content, but:

- Telegram has a strong track record on privacy (refused government data requests)
- The bot is private (1:1 chat, not in groups)
- The most sensitive data (meeting audio) doesn't pass through Telegram
- Alternative (Signal) has significantly worse bot support

---

## Meeting Consent

### Bot Announcement

When HonkAssist joins a meeting, it **must announce itself**:

1. **Chat message:** Sent to meeting chat immediately on join
2. **Voice announcement:** Spoken aloud within first 10 seconds

```
"Hi, I'm [User's Name]'s AI assistant, HonkAssist. I'll be taking notes 
and I'm happy to help with any questions. Let me know if you'd prefer 
I leave."
```

### Why This Matters

- **Legal:** Many jurisdictions require consent for recording (two-party consent states/countries)
- **Ethical:** Participants should know AI is present
- **Practical:** Reduces surprise and builds trust
- **Professional:** Shows transparency about AI usage

### Participant Objection

If a meeting participant objects to AI presence:

1. Bot acknowledges: "Understood, I'll leave now."
2. Bot exits the meeting
3. Notifies user via Telegram: "A participant asked me to leave [meeting name]."
4. User decides whether to rejoin or proceed without AI

---

## Backup Encryption

### borgbackup

Backups to Hetzner Storage Box use borgbackup with encryption:

```bash
# Repository initialized with encryption
borg init --encryption=repokey \
  sftp://u<USER>@<HOST>.your-storagebox.de:23/./backups
```

| Property | Value |
|----------|-------|
| Encryption | AES-256-CTR + HMAC-SHA256 |
| Key storage | `repokey` (key stored in repo, password-protected) |
| Deduplication | Yes (block-level) |
| Compression | lz4 (fast, moderate compression) |

**Backup scope:**
- OpenClaw workspace (memory, config, identity)
- Pipecat config (config.env)
- Excludes: logs, node_modules, temporary files

**Retention:**
- Daily: 7 days
- Weekly: 4 weeks
- Monthly: 6 months

---

## API Key Management

### Storage

API keys are stored in:
- `openclaw.json` — OpenClaw API keys (Anthropic, Telegram, ElevenLabs, Deepgram)
- `/opt/pipecat/config.env` — Pipecat API keys (same services, meeting-specific)

### Security Measures

- File permissions: `chmod 600` (owner read/write only)
- Never committed to git
- Never logged or included in error messages
- Rotated periodically (every 6 months recommended)

### Key Rotation Procedure

1. Generate new key in provider's console
2. Update in `openclaw.json` and/or `config.env`
3. Restart services: `sudo systemctl restart openclaw pipecat`
4. Verify functionality
5. Revoke old key in provider's console

---

## Memory Poisoning Protection

### Attack Vector

A malicious actor could try to inject false information into the agent's memory by:

1. Sending crafted messages via Telegram (blocked by allowlist)
2. Speaking crafted statements in meetings (detected but harder to prevent)
3. Manipulating shared documents referenced in meetings

### Mitigations

| Layer | Protection |
|-------|-----------|
| Telegram allowlist | Only authorized user can send messages |
| Meeting presence | Bot only joins meetings invited by authorized user |
| OpenClaw protections | Built-in prompt injection safeguards |
| Memory review | Agent periodically reviews memory for inconsistencies |
| Human oversight | User can review and edit memory files directly |

---

## Voice Impersonation Protection

### Risk

The ElevenLabs voice used by HonkAssist could theoretically be misused to impersonate the voice owner.

### Mitigations

- **Voice ID restricted:** Only used within the bot's API calls; not exposed externally
- **Not the user's voice:** HonkAssist uses its own voice identity, not a clone of the user
- **API key protected:** ElevenLabs API key is not shared
- **Usage context:** Voice is only used in bot conversations and meetings where the bot is identified as AI

---

## Security Checklist

| Category | Item | Priority |
|----------|------|----------|
| **SSH** | Key-only authentication | Critical |
| **SSH** | Root login disabled | Critical |
| **SSH** | Tailscale-only access | Critical |
| **Firewall** | No public inbound ports | Critical |
| **Firewall** | fail2ban enabled | High |
| **Updates** | unattended-upgrades enabled | High |
| **Access** | Telegram allowlist configured | Critical |
| **Access** | Service runs as non-root user | High |
| **Encryption** | gocryptfs for sensitive data | High |
| **Encryption** | Backup encryption (borgbackup) | High |
| **API** | Keys in 600-permission files | High |
| **Meeting** | Bot announces itself on join | High |
| **Data** | ElevenLabs generations deleted after delivery | Medium |
| **Data** | No raw audio stored long-term | Medium |
| **VPN** | Tailscale installed and connected | Critical |
| **Monitoring** | Health checks configured | Medium |
