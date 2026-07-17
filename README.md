# Discord Mass Report Bot v3.0

Interactive Discord bot for mass reporting via Discord's internal API.
Multi-token, proxy-aware, with real-time statistics.

## Features

- **1-6 user tokens** — round-robin rotation between tokens
- **200+ residential proxies** — automatic IP rotation
- **Real-time stats** — success/fail/rate-limit/RPM directly in Discord
- **Stealth** — random user-agents, realistic headers, adaptive delays
- **Safe** — rate-limit handling, auto backoff, multi-endpoint fallback

## Commands (prefix: !)

| Command | Description |
|---------|-------------|
| `!addtokens <tok1> [tok2] ...` | Add 1-6 user tokens |
| `!tokens` | List registered tokens |
| `!remtoken <index>` | Remove a token |
| `!report <user_id> [reason]` | Start mass reporting |
| `!stop` | Stop all operations |
| `!stats` | Live statistics |
| `!proxies [load\|status\|rotate]` | Manage proxies |
| `!help` | Show all commands |

## Quick Start

```bash
# 1. Install dependencies
pip install discord.py-self aiohttp colorama

# 2. Set bot token
export DISCORD_BOT_TOKEN='your_bot_token_here'

# 3. Run
python3 discord_report_bot.py
```

## Requirements

- Python 3.10+
- discord.py-self 2.0.0+
- aiohttp
- colorama (optional, for terminal)
- GitHub: [kaykewps020](https://github.com/kaykewps020)
