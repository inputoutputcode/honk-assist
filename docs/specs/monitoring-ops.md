# Monitoring & Operations

Operational procedures to keep HonkAssist running reliably with minimal manual intervention.

---

## systemd Services

HonkAssist runs two systemd services:

### OpenClaw Service

```ini
# /etc/systemd/system/openclaw.service
[Unit]
Description=OpenClaw AI Agent
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
```

### Pipecat Service

```ini
# /etc/systemd/system/pipecat.service
[Unit]
Description=Pipecat Voice Pipeline
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
```

### Service Management

```bash
# Start/stop/restart
sudo systemctl start openclaw pipecat
sudo systemctl stop openclaw pipecat
sudo systemctl restart openclaw pipecat

# Check status
sudo systemctl status openclaw
sudo systemctl status pipecat

# Enable at boot
sudo systemctl enable openclaw pipecat

# View logs (live)
sudo journalctl -u openclaw -f
sudo journalctl -u pipecat -f

# View logs (last hour)
sudo journalctl -u openclaw --since "1 hour ago"
```

---

## Health Checks

### Automated Health Check Script

```bash
#!/bin/bash
# /home/openclaw/healthcheck.sh

ALERT=0

# Check OpenClaw
if systemctl is-active --quiet openclaw; then
    echo "✅ OpenClaw running"
else
    echo "❌ OpenClaw DOWN"
    ALERT=1
fi

# Check Pipecat
if systemctl is-active --quiet pipecat; then
    echo "✅ Pipecat running"
else
    echo "❌ Pipecat DOWN"
    ALERT=1
fi

# Check disk space
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 80 ]; then
    echo "⚠️ Disk usage at ${DISK_USAGE}%"
    ALERT=1
else
    echo "✅ Disk at ${DISK_USAGE}%"
fi

# Check RAM
FREE_MB=$(free -m | awk '/Mem:/ {print $7}')
if [ "$FREE_MB" -lt 512 ]; then
    echo "⚠️ Low memory: ${FREE_MB}MB available"
    ALERT=1
else
    echo "✅ Memory: ${FREE_MB}MB available"
fi

# Check Tailscale
if tailscale status &>/dev/null; then
    echo "✅ Tailscale connected"
else
    echo "⚠️ Tailscale disconnected"
    ALERT=1
fi

exit $ALERT
```

### Cron Schedule

```bash
chmod 700 /home/openclaw/healthcheck.sh

# Run weekly on Monday 9am, log output
(crontab -l 2>/dev/null; echo "0 9 * * 1 /home/openclaw/healthcheck.sh >> /var/log/honkassist-health.log 2>&1") | crontab -
```

### External Monitoring (Optional)

| Service | What It Does | Cost |
|---------|-------------|------|
| [UptimeRobot](https://uptimerobot.com) | Ping VPS every 5 min, alert on downtime | Free tier |
| [Healthchecks.io](https://healthchecks.io) | Monitor cron jobs (backups, health) | Free tier |
| OpenClaw heartbeat | Self-check via Discord/Telegram | Built-in |

---

## Log Rotation

### journald (systemd logs)

```bash
# /etc/systemd/journald.conf.d/retention.conf
[Journal]
SystemMaxUse=500M
MaxRetentionSec=30d
```

```bash
sudo systemctl restart systemd-journald
```

### Application Logs

```bash
# /etc/logrotate.d/honkassist
/var/log/honkassist-*.log {
    weekly
    rotate 8
    compress
    delaycompress
    missingok
    notifempty
}
```

---

## Backup Strategy

### Hetzner Storage Box + borgbackup

```bash
# Install borgbackup
sudo apt install -y borgbackup

# Init backup repo (first time only)
borg init --encryption=repokey \
    sftp://u<STORAGEBOX-USER>@<STORAGEBOX>.your-storagebox.de:23/./honkassist-backups
```

### Backup Script

```bash
#!/bin/bash
# /home/openclaw/backup.sh
set -euo pipefail

export BORG_REPO="sftp://u<USER>@<HOST>.your-storagebox.de:23/./honkassist-backups"
export BORG_PASSPHRASE="<BACKUP-PASSWORD>"

echo "[$(date)] Starting backup..."

borg create --stats ::'{now:%Y-%m-%d_%H:%M}' \
    /home/openclaw/.openclaw/workspace \
    /opt/pipecat/config.env \
    --exclude '*.log' \
    --exclude 'node_modules' \
    --exclude '__pycache__' \
    --exclude '.git'

borg prune --stats \
    --keep-daily=7 \
    --keep-weekly=4 \
    --keep-monthly=6

echo "[$(date)] Backup complete."
```

### Cron: Daily at 3 AM

```bash
chmod 700 /home/openclaw/backup.sh
(crontab -l 2>/dev/null; echo "0 3 * * * /home/openclaw/backup.sh >> /var/log/honkassist-backup.log 2>&1") | crontab -
```

### What Gets Backed Up

| Path | Contents | Size |
|------|----------|------|
| `~/.openclaw/workspace/` | Memory, SOUL.md, AGENTS.md, meeting transcripts | ~10-100 MB |
| `/opt/pipecat/config.env` | API keys and environment config | <1 KB |

### What Does NOT Get Backed Up (intentionally)

- Node modules (`node_modules/`)
- Python venvs (`/opt/pipecat/venv/`)
- Session transcripts (`~/.openclaw/agents/*/sessions/`) — large, regenerable
- System logs

---

## Monthly Maintenance Checklist

**For the tech user — run once per month (~30 min):**

```markdown
- [ ] SSH into VPS via Tailscale
- [ ] Run `sudo apt update && sudo apt upgrade -y`
- [ ] Check service health: `systemctl status openclaw pipecat`
- [ ] Check disk: `df -h /` (should be <70%)
- [ ] Check memory: `free -h`
- [ ] Review logs: `journalctl -u openclaw --since "30 days ago" | grep -i error | tail -20`
- [ ] Verify backups: `borg list` (should show daily entries)
- [ ] Test Telegram: send "ping" to the bot
- [ ] Check API usage/billing:
  - [ ] Anthropic console (credits remaining?)
  - [ ] ElevenLabs dashboard (characters remaining?)
  - [ ] Deepgram console (balance?)
  - [ ] MeetingBaas usage
- [ ] Update OpenClaw if new version: `sudo npm update -g openclaw && sudo systemctl restart openclaw`
- [ ] Reboot if kernel update pending: `sudo reboot`
```

---

## Runbook: Common Issues

### Bot Not Responding to Telegram

```bash
# 1. Check OpenClaw is running
sudo systemctl status openclaw

# 2. Check recent logs for errors
sudo journalctl -u openclaw --since "10 min ago" | grep -i error

# 3. Restart
sudo systemctl restart openclaw

# 4. If still broken, check config
cat ~/.openclaw/openclaw.json | python3 -m json.tool

# 5. Check Telegram bot token is valid
curl -s "https://api.telegram.org/bot<TOKEN>/getMe" | python3 -m json.tool
```

### Meeting Bot Won't Join

```bash
# 1. Check Pipecat is running
sudo systemctl status pipecat

# 2. Check MeetingBaas API key
curl -s https://api.meetingbaas.com/health -H "Authorization: Bearer <KEY>"

# 3. Restart Pipecat
sudo systemctl restart pipecat

# 4. Check logs
sudo journalctl -u pipecat --since "10 min ago"
```

### High Disk Usage

```bash
# Check what's using space
du -sh /home/openclaw/.openclaw/* | sort -rh | head -10

# Clean old session transcripts (>30 days)
find /home/openclaw/.openclaw/agents/*/sessions/ -name "*.jsonl" -mtime +30 -delete

# Clean old journal logs
sudo journalctl --vacuum-time=7d
```

### VPS Unreachable

```bash
# 1. Check via Hetzner console (web terminal)
# 2. If responsive via console but not SSH:
sudo tailscale up    # reconnect Tailscale
sudo ufw status      # check firewall

# 3. If completely unresponsive:
# Use Hetzner console to reboot the server
```

### API Key Expired/Invalid

```bash
# Update key in OpenClaw config
nano ~/.openclaw/openclaw.json
# Update the relevant API key

# Restart to pick up changes
sudo systemctl restart openclaw

# For Pipecat keys
nano /opt/pipecat/config.env
sudo systemctl restart pipecat
```

### Out of API Credits

| Service | How to Check | How to Add Credits |
|---------|-------------|-------------------|
| Anthropic | [console.anthropic.com/settings/billing](https://console.anthropic.com/settings/billing) | Add payment method, auto-reload |
| ElevenLabs | [elevenlabs.io/app/settings/billing](https://elevenlabs.io/app/settings/billing) | Upgrade plan or buy character packs |
| Deepgram | [console.deepgram.com/settings](https://console.deepgram.com/settings) | Add credits |
| MeetingBaas | Dashboard | Top up hours |

---

## Cost Monitoring

### Track Monthly Spending

Create a simple tracking file:

```markdown
# /home/openclaw/.openclaw/workspace/memory/cost-tracking.md

## 2026-04
- Hetzner VPS: €15.00
- Anthropic: $XX.XX
- ElevenLabs: $XX.XX
- Deepgram: $XX.XX
- MeetingBaas: $XX.XX
- Storage Box: €3.00
- **Total: $XX.XX**
```

### Cost Alerts

- **Anthropic:** Set usage limits in console settings
- **ElevenLabs:** Plan includes fixed character quota — monitor in dashboard
- **Deepgram:** Set budget alerts in console
- **MeetingBaas:** Track hours manually (meeting duration × $0.69/hr)

### Cost Optimization Tips

- Use Claude **Haiku** for voice (not Sonnet) — 10x cheaper
- Cache Pipecat system prompts (Anthropic prompt caching)
- Use Deepgram **pay-as-you-go** tier (not pre-paid if usage is low)
- ElevenLabs **Starter** ($5/mo) is enough for light use
- Delete ElevenLabs generations after delivery to stay within quota
