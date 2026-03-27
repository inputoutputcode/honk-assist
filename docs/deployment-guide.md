# Deployment Guide

Step-by-step instructions to deploy HonkAssist from zero to a running system.

**Estimated time:** 4–6 hours for initial setup  
**Who:** Technical user with Linux/SSH experience  
**End-user involvement:** ~15 minutes (Telegram bot creation, initial onboarding)

---

## Deployment Environments

HonkAssist supports two deployment targets:

| Environment | Purpose | Hardware | OpenClaw Status |
|------------|---------|----------|----------------|
| **Hetzner CPX31 VPS** | Production (end-user) | 4 vCPU AMD, 8GB RAM, 160GB SSD | Fresh install |
| **NVIDIA DGX Spark** | Dev/test | ARM64, GB10 GPU, 128GB unified memory | Already running (Honk agent) |

### Hetzner VPS (Production)

- Clean Ubuntu 24.04 install
- Dedicated `openclaw` system user
- Single-purpose: runs only HonkAssist
- Follow this guide from Step 1

### DGX Spark (Dev/Test)

The Spark already runs OpenClaw with the Honk agent. HonkAssist is added as a **second agent** on the same gateway.

**Key differences from Hetzner:**
- Skip Steps 1–4 (server exists, OS hardened, Node.js/Python installed)
- Skip Step 8 (OpenClaw systemd already running)
- OpenClaw config adds a second agent entry instead of being the sole agent
- Pipecat runs alongside existing services (vLLM, etc.)
- Tailscale already configured
- Can test with local models (Qwen3-Next-80B on port 8080) for LLM instead of Claude API

**To deploy on Spark, skip to:** [Step 5: Install OpenClaw](#step-5-install--configure-openclaw) and follow the [OpenClaw Agent Spec](specs/openclaw-agent.md) for multi-agent configuration.

> **Note:** The DGX Spark uses ARM64 (aarch64). Verify Pipecat and its dependencies have ARM64 wheels available, or build from source.

---

## Prerequisites

### Accounts & API Keys

Before starting, create accounts and gather API keys:

| Service | URL | What You Need | Free Tier? |
|---------|-----|---------------|------------|
| Hetzner Cloud | [console.hetzner.cloud](https://console.hetzner.cloud) | Account + payment method | No |
| Anthropic | [console.anthropic.com](https://console.anthropic.com) | API key + $20 credits | $5 free |
| ElevenLabs | [elevenlabs.io](https://elevenlabs.io) | API key + voice ID | Limited free |
| Deepgram | [console.deepgram.com](https://console.deepgram.com) | API key | $200 free credit |
| MeetingBaas | [meetingbaas.com](https://www.meetingbaas.com) | API key | 4 hrs free |
| Telegram | [@BotFather](https://t.me/BotFather) in Telegram | Bot token | Free |
| Tailscale | [tailscale.com](https://tailscale.com) | Account | Free for personal |
| Hetzner Storage Box | [robot.hetzner.com](https://robot.hetzner.com) | BX11 (~€3/mo) | No |

### Local Requirements

- SSH key pair (`ssh-keygen -t ed25519` if you don't have one)
- Terminal/SSH client
- Tailscale installed on your machine

---

## Step 1: Create the VPS

1. Log in to [Hetzner Cloud Console](https://console.hetzner.cloud)
2. Create a new project (e.g., "honk-assist")
3. **Add Server:**
   - **Location:** Nuremberg (nbg1) or Falkenstein (fsn1)
   - **Image:** Ubuntu 24.04
   - **Type:** Shared vCPU → **CPX31** (4 vCPU AMD, 8 GB RAM, 160 GB SSD)
   - **Networking:** Public IPv4 + IPv6
   - **SSH Key:** Paste your public key from `~/.ssh/id_ed25519.pub`
   - **Name:** `honk-assist`
4. Click **Create & Buy Now** (~€15/mo)
5. Note the public IP address

### ✅ Verify

```bash
ssh root@<SERVER-IP>
# Should connect without password prompt
```

---

## Step 2: System Hardening

SSH into the server as root and run:

```bash
# Update system
apt update && apt upgrade -y

# Create service user
adduser --disabled-password --gecos "" openclaw
usermod -aG sudo openclaw

# Copy SSH key to service user
mkdir -p /home/openclaw/.ssh
cp /root/.ssh/authorized_keys /home/openclaw/.ssh/
chown -R openclaw:openclaw /home/openclaw/.ssh
chmod 700 /home/openclaw/.ssh
chmod 600 /home/openclaw/.ssh/authorized_keys

# Harden SSH
cat >> /etc/ssh/sshd_config.d/hardening.conf << 'EOF'
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
EOF

systemctl restart ssh

# Firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw --force enable

# Fail2ban
apt install -y fail2ban
systemctl enable --now fail2ban

# Automatic security updates
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
# Select "Yes" when prompted
```

### ✅ Verify

Open a **new terminal** (keep the root session open as backup):

```bash
ssh openclaw@<SERVER-IP>
# Should connect successfully
```

> ⚠️ Only proceed once you've confirmed `openclaw` user SSH works. Root login is now disabled.

---

## Step 3: Install Tailscale VPN

```bash
# As root or with sudo
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# Follow the auth URL — log in with your Tailscale account
```

Once connected, lock down SSH to Tailscale only:

```bash
# Note your Tailscale IP
tailscale ip -4
# e.g., 100.x.x.x

# Remove public SSH, allow only via Tailscale
sudo ufw delete allow ssh
sudo ufw allow in on tailscale0 to any port 22
```

### ✅ Verify

```bash
# From your local machine (with Tailscale running):
ssh openclaw@<TAILSCALE-IP>     # Should work
ssh openclaw@<PUBLIC-IP>         # Should be refused
```

---

## Step 4: Install Node.js & Python

```bash
# Node.js 22.x LTS
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

# Python 3.12 (default on Ubuntu 24.04)
sudo apt install -y python3-pip python3-venv python3-dev

# Build tools
sudo apt install -y build-essential git ffmpeg
```

### ✅ Verify

```bash
node --version    # v22.x.x
python3 --version # 3.12.x
ffmpeg -version   # ffmpeg version ...
```

---

## Step 5: Install & Configure OpenClaw

```bash
# Install globally
sudo npm install -g openclaw

# Initialize workspace (as openclaw user)
su - openclaw
openclaw init
```

Edit the configuration:

```bash
nano ~/.openclaw/openclaw.json
```

Add the following (replace all `<PLACEHOLDER>` values):

```json
{
  "model": "anthropic/claude-haiku-4",
  "anthropicApiKey": "<YOUR-ANTHROPIC-API-KEY>",
  "channels": {
    "telegram": {
      "token": "<YOUR-TELEGRAM-BOT-TOKEN>",
      "allowedUsers": ["<END-USER-TELEGRAM-ID>"]
    }
  },
  "tts": {
    "provider": "elevenlabs",
    "apiKey": "<YOUR-ELEVENLABS-API-KEY>",
    "voiceId": "<CHOSEN-VOICE-ID>"
  },
  "stt": {
    "provider": "deepgram",
    "apiKey": "<YOUR-DEEPGRAM-API-KEY>"
  }
}
```

> **Note:** Check `openclaw help` for the exact config schema — field names may differ between versions.

### ✅ Verify

```bash
openclaw gateway start
# Should start without errors
# Ctrl+C to stop (we'll set up systemd next)
```

---

## Step 6: Set Up Agent Identity

```bash
cd ~/.openclaw/workspace
```

Create `SOUL.md` — the agent's personality:

```markdown
# SOUL.md

You are HonkAssist, a professional AI meeting assistant.

## Core Behavior
- Be concise and clear in meetings — don't ramble
- Take careful notes of decisions and action items
- When asked a question in a meeting, respond helpfully but briefly
- In Telegram, be more conversational and detailed
- Always announce yourself when joining a meeting

## Voice
- Speak naturally, not robotically
- Use clear language, avoid jargon unless the context calls for it
- If you don't know something, say so — don't make things up
```

Create `USER.md` — the end-user's profile:

```markdown
# USER.md

- **Name:** [End-user's name]
- **Role:** [Their role/business]
- **Timezone:** [Their timezone]
- **Notes:** [Preferences, communication style, key context]
```

Initialize memory:

```bash
mkdir -p memory/meetings
touch MEMORY.md
```

---

## Step 7: Create OpenClaw Systemd Service

```bash
sudo tee /etc/systemd/system/openclaw.service << 'EOF'
[Unit]
Description=OpenClaw AI Agent (HonkAssist)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=openclaw
WorkingDirectory=/home/openclaw/.openclaw
Environment=OPENCLAW_NO_RESPAWN=1
ExecStart=/usr/bin/openclaw gateway start
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now openclaw
```

### ✅ Verify

```bash
sudo systemctl status openclaw
# Should show "active (running)"

sudo journalctl -u openclaw -f
# Should show startup logs without errors
```

---

## Step 8: Create Telegram Bot

This step requires the **end-user** (or do it on their behalf):

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Choose a name (e.g., "HonkAssist")
4. Choose a username (e.g., `honkassist_bot`)
5. Copy the bot token
6. Get the end-user's Telegram user ID:
   - Search for **@userinfobot** in Telegram
   - Send it any message — it replies with your user ID

Update `openclaw.json` with the bot token and user ID.

### ✅ Verify

Send "Hello" to the bot in Telegram. You should get a text response.

---

## Step 9: Test Voice Messages

1. Send a voice note to the bot in Telegram (hold the mic button, speak, release)
2. The bot should:
   - Transcribe your voice (Deepgram)
   - Generate a response (Claude)
   - Convert to speech (ElevenLabs)
   - Reply with a voice note

### ✅ Verify

- Voice note is transcribed accurately
- Response is relevant to what you said
- Voice reply plays correctly in Telegram
- Round-trip time is under 5 seconds

---

## Step 10: Install Pipecat (Meeting Voice Pipeline)

```bash
# Create directory and venv
sudo mkdir -p /opt/pipecat
sudo chown openclaw:openclaw /opt/pipecat
python3 -m venv /opt/pipecat/venv

# Install Pipecat with integrations
source /opt/pipecat/venv/bin/activate
pip install "pipecat-ai[deepgram,anthropic,elevenlabs]"

# Clone MeetingBaas speaking bot example
cd /opt/pipecat
git clone https://github.com/Meeting-BaaS/speaking-meeting-bot.git
cd speaking-meeting-bot
pip install -r requirements.txt
deactivate
```

Create the environment file:

```bash
cat > /opt/pipecat/config.env << 'EOF'
MEETING_BAAS_API_KEY=<YOUR-MEETINGBAAS-KEY>
DEEPGRAM_API_KEY=<YOUR-DEEPGRAM-KEY>
ANTHROPIC_API_KEY=<YOUR-ANTHROPIC-KEY>
ELEVENLABS_API_KEY=<YOUR-ELEVENLABS-KEY>
ELEVENLABS_VOICE_ID=<YOUR-VOICE-ID>
EOF

chmod 600 /opt/pipecat/config.env
```

---

## Step 11: Create Pipecat Systemd Service

```bash
sudo tee /etc/systemd/system/pipecat.service << 'EOF'
[Unit]
Description=Pipecat Voice Pipeline (HonkAssist)
After=network-online.target openclaw.service
Wants=network-online.target

[Service]
Type=simple
User=openclaw
WorkingDirectory=/opt/pipecat/speaking-meeting-bot
EnvironmentFile=/opt/pipecat/config.env
ExecStart=/opt/pipecat/venv/bin/python main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now pipecat
```

### ✅ Verify

```bash
sudo systemctl status pipecat
# Should show "active (running)"
```

---

## Step 12: Set Up Encrypted Data Directory

```bash
sudo apt install -y gocryptfs

# Create encrypted storage
mkdir -p /home/openclaw/.openclaw-encrypted
mkdir -p /home/openclaw/.openclaw-data

# Initialize (SAVE THE MASTER KEY!)
gocryptfs -init /home/openclaw/.openclaw-encrypted

# Mount
gocryptfs /home/openclaw/.openclaw-encrypted /home/openclaw/.openclaw-data
```

> ⚠️ After each server reboot, the tech user must SSH in and mount the encrypted directory by running `gocryptfs /home/openclaw/.openclaw-encrypted /home/openclaw/.openclaw-data` and entering the password.

---

## Step 13: Set Up Backups

Order a Hetzner Storage Box (BX11, ~€3/mo, 1 TB) from [robot.hetzner.com](https://robot.hetzner.com).

```bash
sudo apt install -y borgbackup

# Initialize backup repository (first time only)
borg init --encryption=repokey \
  sftp://u<STORAGEBOX-USER>@<STORAGEBOX>.your-storagebox.de:23/./backups

# Create backup script
cat > /home/openclaw/backup.sh << 'SCRIPT'
#!/bin/bash
export BORG_REPO="sftp://u<USER>@<HOST>.your-storagebox.de:23/./backups"
export BORG_PASSPHRASE="<BACKUP-PASSWORD>"

borg create ::'{now:%Y-%m-%d}' \
  /home/openclaw/.openclaw/workspace \
  /opt/pipecat/config.env \
  --exclude '*.log' \
  --exclude 'node_modules'

borg prune --keep-daily=7 --keep-weekly=4 --keep-monthly=6
SCRIPT

chmod 700 /home/openclaw/backup.sh

# Schedule daily at 3 AM
(crontab -l 2>/dev/null; echo "0 3 * * * /home/openclaw/backup.sh") | crontab -
```

### ✅ Verify

```bash
/home/openclaw/backup.sh
borg list sftp://u<USER>@<HOST>.your-storagebox.de:23/./backups
# Should show today's backup
```

---

## Step 14: Health Checks

```bash
cat > /home/openclaw/healthcheck.sh << 'SCRIPT'
#!/bin/bash
STATUS=""

if systemctl is-active --quiet openclaw; then
  STATUS+="✅ OpenClaw running\n"
else
  STATUS+="❌ OpenClaw DOWN\n"
fi

if systemctl is-active --quiet pipecat; then
  STATUS+="✅ Pipecat running\n"
else
  STATUS+="❌ Pipecat DOWN\n"
fi

DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 80 ]; then
  STATUS+="⚠️ Disk usage at ${DISK_USAGE}%\n"
else
  STATUS+="✅ Disk usage at ${DISK_USAGE}%\n"
fi

echo -e "$STATUS"
SCRIPT

chmod 700 /home/openclaw/healthcheck.sh

# Run weekly Monday 9 AM
(crontab -l 2>/dev/null; echo "0 9 * * 1 /home/openclaw/healthcheck.sh") | crontab -
```

---

## Step 15: End-to-End Testing

Run through each of these tests:

| Test | How | Expected Result |
|------|-----|-----------------|
| Text via Telegram | Send "Hello" to the bot | Text response |
| Voice via Telegram | Send a voice note | Voice note reply |
| Meeting join | Send a Google Meet link via Telegram | Bot joins meeting, announces itself |
| Meeting voice | Ask the bot a question in the meeting | Bot responds with voice |
| Memory recall | Ask "What did we discuss?" | Agent recalls from memory |
| Security: public SSH | `ssh openclaw@<PUBLIC-IP>` | Connection refused |
| Security: Tailscale SSH | `ssh openclaw@<TAILSCALE-IP>` | Connection succeeds |
| Backup | Run `backup.sh` manually | Backup completes |
| Service recovery | `sudo systemctl restart openclaw` | Service restarts cleanly |

---

## End-User Onboarding

Once everything is verified, hand off to the end-user:

1. **Add the bot:** Search for the bot username in Telegram, tap Start
2. **Test text:** Send "Hello, are you there?"
3. **Test voice:** Hold the mic button, speak, release
4. **Test meeting:** Send a Google Meet/Teams/Zoom link
5. **Start teaching:** Share business context, preferences, key information

The end-user never touches a terminal. Everything happens through Telegram.

---

## Troubleshooting

### OpenClaw won't start

```bash
sudo journalctl -u openclaw --since "10 min ago"
# Check for API key errors, config syntax issues
```

Common causes:
- Invalid API key in `openclaw.json`
- JSON syntax error in config
- Port conflict (shouldn't happen — OpenClaw uses outbound only)

### Telegram bot not responding

1. Check OpenClaw is running: `sudo systemctl status openclaw`
2. Check logs: `sudo journalctl -u openclaw -f`
3. Verify bot token is correct
4. Verify the user's Telegram ID is in the allowlist
5. Restart: `sudo systemctl restart openclaw`

### Voice messages fail

- Check ElevenLabs API key and quota
- Check Deepgram API key and quota
- Verify ffmpeg is installed: `ffmpeg -version`
- Check logs for specific error messages

### Meeting bot doesn't join

- Verify MeetingBaas API key
- Check Pipecat service: `sudo systemctl status pipecat`
- Check Pipecat logs: `sudo journalctl -u pipecat -f`
- Try a different meeting platform
- Ensure the meeting link is valid and the meeting is active

### High latency on voice responses

- Check VPS CPU usage: `top` or `htop`
- Check network latency to APIs: `ping api.deepgram.com`
- Review ElevenLabs plan — lower tiers may have rate limits
- Consider upgrading to dedicated vCPU (CCX23) if CPU is the bottleneck

### Disk space issues

```bash
df -h /
du -sh /home/openclaw/.openclaw/workspace/memory/*
# Clean old logs, rotate meeting transcripts
```

### After VPS reboot

```bash
# Mount encrypted data directory
gocryptfs /home/openclaw/.openclaw-encrypted /home/openclaw/.openclaw-data

# Services should auto-start via systemd, but verify:
sudo systemctl status openclaw
sudo systemctl status pipecat
```
