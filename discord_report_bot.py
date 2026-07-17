#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║              DISCORD MASS REPORT BOT — v3.0 STEALTH             ║
║        Fully interactive via Discord — Slash Commands           ║
║                  Proxy-aware · Multi-token · Safe               ║
╚══════════════════════════════════════════════════════════════════╝
"""

import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import random
import time
import json
import os
import sys
from datetime import datetime
from collections import deque

# ============================================================
# CONFIG
# ============================================================

INTRO = """
╔══════════════════════════════════════════════════════════════════╗
║              DISCORD MASS REPORT BOT — v3.0 STEALTH             ║
║        Fully interactive via Discord — Slash Commands           ║
║                  Proxy-aware · Multi-token · Safe               ║
╚══════════════════════════════════════════════════════════════════╝
"""

PROXY_PATHS = [
    "/storage/emulated/0/Download/Residencial Proxys/proxies.json",
    "/storage/emulated/0/Download/Residencial Proxys/proxies_simple.txt",
    "/storage/emulated/0/Download/Residencial Proxys/proxies_auth.txt",
]

REPORT_ENDPOINTS = [
    "https://discord.com/api/v9/reporting/user",
    "https://discord.com/api/v9/report",
    "https://discord.com/api/v9/users/@me/report",
]

DESCRIPTIONS = [
    "This account violates Discord's Terms of Service using automation for spam.",
    "User sends unsolicited messages with malicious content.",
    "Account suspected of being an automated bot violating guidelines.",
    "User is harassing others with explicit content and threats.",
    "Identity fraud - this account impersonates another person.",
    "Distribution of prohibited content and malicious links.",
    "Severe violation of community guidelines with hateful content.",
    "Compromised account being used for phishing attacks.",
    "User engages in self-botting violating the acceptable use policy.",
    "Spreading disinformation and harmful links across multiple servers.",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) discord/1.0.9047 Chrome/120.0.6099.291 Safari/537.36",
]

# ============================================================
# STATE
# ============================================================

class Stats:
    def __init__(self):
        self.reset()
    def reset(self):
        self.total = 0
        self.success = 0
        self.fail = 0
        self.rate_limited = 0
        self.timeout = 0
        self.invalid_token = 0
        self.start_time = None
        self.target_id = None
        self.reason = 1
        self.running = False
        self.timestamps = deque(maxlen=120)
        self.token_stats = {}

    @property
    def elapsed(self):
        if not self.start_time: return "0s"
        e = time.time() - self.start_time
        if e < 60: return f"{e:.0f}s"
        if e < 3600: return f"{e//60:.0f}m {e%60:.0f}s"
        return f"{e//3600:.0f}h {(e%3600)//60:.0f}m"

    @property
    def rpm(self):
        now = time.time()
        while self.timestamps and (now - self.timestamps[0]) > 60:
            self.timestamps.popleft()
        return len(self.timestamps)

    @property
    def rate(self):
        if self.total == 0: return 0.0
        return (self.success / self.total) * 100


stats = Stats()
tokens = []
proxies = []
proxy_rotate = True
stop_evt = asyncio.Event()
report_task = None
stats_task = None
stats_channel = None

# ============================================================
# PROXY LOADER
# ============================================================

def load_proxies(path=None):
    global proxies
    if path and os.path.exists(path):
        proxies = _load_file(path)
        return len(proxies)
    for p in PROXY_PATHS:
        if os.path.exists(p):
            proxies = _load_file(p)
            if proxies:
                return len(proxies)
    return 0

def _load_file(path):
    try:
        if path.endswith('.json'):
            with open(path) as f:
                data = json.load(f)
            out = []
            for e in data:
                if isinstance(e, dict):
                    u = e.get('url') or f"http://{e.get('username','')}:{e.get('password','')}@{e['ip']}:{e['port']}"
                    out.append(u)
            return out
        else:
            out = []
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    parts = line.split(':')
                    if len(parts) == 4:
                        out.append(f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}")
                    elif len(parts) == 2:
                        out.append(f"http://{parts[0]}:{parts[1]}")
                    else:
                        out.append(f"http://{line}")
            return out
    except:
        return []

# ============================================================
# DISCORD API HELPERS
# ============================================================

def make_headers(token):
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://discord.com",
        "Referer": "https://discord.com/channels/@me",
        "X-Discord-Locale": "en-US",
        "X-Super-Properties": "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiRGlzY29yZCIsImRldmljZSI6IiIsInN5c3RlbV9sb2NhbGUiOiJlbi1VUyIsImJyb3dzZXJfdXNlcl9hZ2VudCI6Ik1vemlsbGEvNS4wIChXaW5kb3dzIE5UIDEwLjA7IFdpbjY0OyB4NjQpIEFwcGxlV2Via2l0LzUzNy4zNiAoS0hUTUwsIGxpa2UgR2Vja28pIGRpc2NvcmQvMS4wLjkwNDcgQ2hyb21lLzEyMC4wLjYwOTkuMjkxIFNhZmFyaS81MzcuMzYiLCJicm93c2VyX3ZlcnNpb24iOiIxLjAuOTA0NyIsIm9zX3ZlcnNpb24iOiIxMC4wLjE5MDQ1In0=",
    }

async def send_report(session, token, target, reason, desc, proxy=None):
    endpoints = random.sample(REPORT_ENDPOINTS, len(REPORT_ENDPOINTS))
    payload = {"user_id": target, "reason": reason, "description": desc, "guild_id": None, "channel_id": None, "message_id": None}
    headers = make_headers(token)
    to = aiohttp.ClientTimeout(total=15)
    for ep in endpoints:
        try:
            async with session.post(ep, json=payload, headers=headers, timeout=to, proxy=proxy) as r:
                txt = await r.text()
                if r.status == 429:
                    ra = 5
                    try: ra = json.loads(txt).get("retry_after", 5)
                    except: pass
                    return (429, ra)
                if r.status in (401, 403): return (r.status, 0)
                if 200 <= r.status < 300: return (200, 0)
                return (r.status, 0)
        except asyncio.TimeoutError: return (408, 0)
        except: return (0, 0)
    return (-1, 0)

def validate_token(t):
    if not t or len(t) < 15: return False
    p = t.split('.')
    if len(p) < 2: return False
    try: int(p[0]); return True
    except: return False

def validate_uid(uid):
    if not uid or len(uid) < 10: return False
    try: int(uid); return True
    except: return False

# ============================================================
# WORKER
# ============================================================

async def worker():
    global stats, tokens, proxies, stop_evt
    ti = 0; pi = 0; fails = 0
    conn = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=conn) as session:
        while not stop_evt.is_set() and stats.running:
            token = tokens[ti % len(tokens)]; ti += 1
            proxy = None
            if proxies:
                proxy = proxies[pi % len(proxies)]
                if proxy_rotate: pi += 1
            desc = random.choice(DESCRIPTIONS)
            code, ra = await send_report(session, token, stats.target_id, stats.reason, desc, proxy)
            now = time.time()
            stats.total += 1
            stats.timestamps.append(now)
            ts = token[:20]
            if ts not in stats.token_stats: stats.token_stats[ts] = {"t":0,"s":0,"f":0}
            stats.token_stats[ts]["t"] += 1
            if code == 429:
                stats.rate_limited += 1; stats.token_stats[ts]["f"] += 1; fails += 1
                await asyncio.sleep(ra + random.uniform(1,3)); continue
            if code in (401, 403):
                stats.invalid_token += 1; stats.token_stats[ts]["f"] += 1; fails += 1
                await asyncio.sleep(random.uniform(0.5,1.5)); continue
            if code in (408, 0, -1):
                stats.timeout += 1; stats.fail += 1; stats.token_stats[ts]["f"] += 1; fails += 1
                await asyncio.sleep(random.uniform(1,3)); continue
            if 200 <= code < 300:
                stats.success += 1; stats.token_stats[ts]["s"] += 1; fails = 0
            else:
                stats.fail += 1; stats.token_stats[ts]["f"] += 1; fails += 1
            delay = random.uniform(1.5, 4.5)
            if fails > 10: delay *= 3
            elif fails > 5: delay *= 2
            await asyncio.sleep(delay)
    stats.running = False

# ============================================================
# BOT SETUP
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ============================================================
# EVENTS
# ============================================================

@bot.event
async def on_ready():
    print(f"[✓] Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"[✓] {len(tokens)} user tokens loaded")
    print(f"[✓] {len(proxies)} proxies loaded")
    print(f"[✓] Slash commands ready!")
    try:
        synced = await bot.tree.sync()
        print(f"[✓] Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"[!] Sync error: {e}")

# ============================================================
# SLASH COMMANDS
# ============================================================

@bot.tree.command(name="addtokens", description="Add 1-6 user tokens for mass reporting (separate by spaces)")
@app_commands.describe(tokens_str="Up to 6 user tokens separated by spaces")
async def addtokens(interaction: discord.Interaction, tokens_str: str):
    if stats.running:
        return await interaction.response.send_message("❌ Stop the report first with `/stop`", ephemeral=True)
    parts = tokens_str.split()
    if len(parts) > 6:
        return await interaction.response.send_message("❌ Maximum 6 tokens.", ephemeral=True)
    if not parts:
        return await interaction.response.send_message("❌ Provide at least 1 token.", ephemeral=True)
    
    await interaction.response.defer()
    valid = []; invalid = []
    for t in parts:
        if validate_token(t) and t not in tokens:
            valid.append(t)
        else:
            invalid.append(t[:25])
    tokens.extend(valid)
    
    embed = discord.Embed(title="🔑 Tokens Added", color=0x5865F2)
    if valid: embed.add_field(name=f"✅ Valid ({len(valid)})", value="\n".join(f"`{t[:25]}...`" for t in valid[:6]), inline=False)
    if invalid: embed.add_field(name=f"❌ Invalid/Duplicate ({len(invalid)})", value="\n".join(f"`{t}`" for t in invalid[:6]), inline=False)
    embed.add_field(name="Total", value=f"**{len(tokens)}/6**", inline=False)
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="tokens", description="List all registered tokens")
async def cmd_tokens(interaction: discord.Interaction):
    if not tokens:
        return await interaction.response.send_message("❌ No tokens added. Use `/addtokens`.", ephemeral=True)
    embed = discord.Embed(title=f"🔑 Tokens ({len(tokens)}/6)", color=0x5865F2)
    for i, t in enumerate(tokens, 1):
        embed.add_field(name=f"#{i}", value=f"`{t[:35]}...`", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="remtoken", description="Remove a token by index")
@app_commands.describe(index="Index number of the token to remove (1-based)")
async def remtoken(interaction: discord.Interaction, index: int):
    if stats.running:
        return await interaction.response.send_message("❌ Stop first with `/stop`.", ephemeral=True)
    if index < 1 or index > len(tokens):
        return await interaction.response.send_message(f"❌ Invalid index. Choose 1-{len(tokens)}.", ephemeral=True)
    removed = tokens.pop(index-1)
    await interaction.response.send_message(f"✅ Removed token #{index}: `{removed[:25]}...`")


@bot.tree.command(name="report", description="Start mass reporting a Discord user")
@app_commands.describe(user_id="Target Discord user ID", reason="Report reason (1-7)")
@app_commands.choices(reason=[
    app_commands.Choice(name="1 - Spam/Phishing", value=1),
    app_commands.Choice(name="2 - Harassment/Hate Speech", value=2),
    app_commands.Choice(name="3 - Inappropriate Content", value=3),
    app_commands.Choice(name="4 - Impersonation", value=4),
    app_commands.Choice(name="5 - Selling Accounts/Items", value=5),
    app_commands.Choice(name="6 - Self-Bot/ToS Violation", value=6),
    app_commands.Choice(name="7 - Other", value=7),
])
async def report(interaction: discord.Interaction, user_id: str, reason: app_commands.Choice[int] = None):
    global report_task, stats_task, stats_channel

    if not tokens:
        return await interaction.response.send_message("❌ Add tokens first with `/addtokens`.", ephemeral=True)
    if not validate_uid(user_id):
        return await interaction.response.send_message("❌ Invalid user ID (numeric snowflake).", ephemeral=True)
    if stats.running:
        return await interaction.response.send_message("⚠️ Already running. Use `/stop` first or `/stats`.", ephemeral=True)

    rcode = reason.value if reason else 1
    rname = reason.name if reason else "Spam/Phishing"

    embed = discord.Embed(title="🎯 Starting Mass Report", color=0x5865F2, timestamp=datetime.utcnow())
    embed.add_field(name="Target", value=f"`{user_id}`", inline=True)
    embed.add_field(name="Reason", value=f"`{rname}`", inline=True)
    embed.add_field(name="Tokens", value=f"`{len(tokens)}`", inline=True)
    embed.add_field(name="Proxies", value=f"`{len(proxies)}`" if proxies else "`0 (direct)`", inline=True)
    embed.set_footer(text="Reports starting...")
    await interaction.response.send_message(embed=embed)

    stats.reset()
    stats.target_id = user_id
    stats.reason = rcode
    stats.running = True
    stop_evt.clear()
    stats_channel = interaction.channel

    report_task = asyncio.create_task(worker())
    stats_task = asyncio.create_task(stats_updater())

    await asyncio.sleep(2)
    await interaction.followup.send(embed=build_embed())


@bot.tree.command(name="stop", description="Stop all mass report operations")
async def stop(interaction: discord.Interaction):
    global report_task, stats_task
    if not stats.running:
        return await interaction.response.send_message("❌ No report running.", ephemeral=True)
    stop_evt.set()
    stats.running = False
    if stats_task: stats_task.cancel(); stats_task = None
    embed = build_embed()
    embed.title = "🛑 Stopped"
    embed.color = 0xED4245
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="stats", description="Show live report statistics")
async def cmd_stats(interaction: discord.Interaction):
    if stats.total == 0 and not stats.running:
        return await interaction.response.send_message("📊 No reports sent yet. Use `/report`.", ephemeral=True)
    embed = build_embed()
    if stats.token_stats:
        lines = []
        for tok, ts in sorted(stats.token_stats.items()):
            rate = (ts["s"]/ts["t"]*100) if ts["t"] > 0 else 0
            lines.append(f"`{tok[:18]}...` → {ts['s']}/{ts['t']} ({rate:.0f}%)")
        if lines: embed.add_field(name="🔑 Per Token", value="\n".join(lines[:6]), inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="proxies", description="Manage proxy settings")
@app_commands.describe(action="Action: status / load / rotate")
async def cmd_proxies(interaction: discord.Interaction, action: str = "status"):
    if action == "status":
        embed = discord.Embed(title="🌐 Proxies", color=0x5865F2)
        embed.add_field(name="Status", value="✅ Loaded" if proxies else "❌ Not loaded", inline=True)
        embed.add_field(name="Count", value=f"`{len(proxies)}`", inline=True)
        embed.add_field(name="Rotation", value=f"`{'ON' if proxy_rotate else 'OFF'}`", inline=True)
        await interaction.response.send_message(embed=embed)
    elif action == "load":
        n = load_proxies()
        await interaction.response.send_message(f"✅ Loaded **{n}** proxies." if n else "❌ No proxies found.")
    elif action == "rotate":
        proxy_rotate = not proxy_rotate
        await interaction.response.send_message(f"🔄 Rotation: **{'ON' if proxy_rotate else 'OFF'}**")
    else:
        await interaction.response.send_message("❌ Use: `status`, `load`, or `rotate`", ephemeral=True)


@bot.tree.command(name="help", description="Show all commands")
async def cmd_help(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 Mass Report Bot — Commands", color=0x5865F2)
    embed.add_field(name="🔑 Tokens", value="`/addtokens` — Add 1-6 user tokens\n`/tokens` — List tokens\n`/remtoken` — Remove a token", inline=False)
    embed.add_field(name="🎯 Reporting", value="`/report` — Start mass reporting\n`/stop` — Stop all\n`/stats` — Live statistics", inline=False)
    embed.add_field(name="🌐 Proxies", value="`/proxies status` — Show status\n`/proxies load` — Load from storage\n`/proxies rotate` — Toggle rotation", inline=False)
    await interaction.response.send_message(embed=embed)


# ============================================================
# STATS UPDATER
# ============================================================

async def stats_updater():
    global stats_channel
    try:
        while stats.running and not stop_evt.is_set():
            await asyncio.sleep(15)
            if stats.running and not stop_evt.is_set() and stats_channel:
                await stats_channel.send(embed=build_embed())
    except asyncio.CancelledError: pass
    except: pass


def build_embed():
    embed = discord.Embed(
        title="📊 Mass Report — Live" if stats.running else "📊 Mass Report",
        color=0x5865F2 if stats.running else 0xED4245,
        timestamp=datetime.utcnow(),
    )
    if stats.target_id: embed.add_field(name="🎯 Target", value=f"`{stats.target_id}`", inline=True)
    embed.add_field(name="⏱ Elapsed", value=stats.elapsed, inline=True)
    embed.add_field(name="🚀 RPM", value=f"{stats.rpm}/min", inline=True)
    embed.add_field(name="📨 Total", value=f"{stats.total}", inline=True)
    embed.add_field(name="✅ Success", value=f"{stats.success} ({stats.rate:.1f}%)", inline=True)
    embed.add_field(name="❌ Failed", value=f"{stats.fail}", inline=True)
    embed.add_field(name="⏳ Rate Limit", value=f"{stats.rate_limited}", inline=True)
    embed.add_field(name="⚠️ Timeout", value=f"{stats.timeout}", inline=True)
    embed.add_field(name="🚫 Invalid Tokens", value=f"{stats.invalid_token}", inline=True)
    embed.set_footer(text="🟢 Running" if stats.running else "🔴 Stopped")
    return embed


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print(INTRO)
    n = load_proxies()
    print(f"[✓] Auto-loaded {n} proxies from storage")
    if n == 0: print("[!] No proxies found. Will use direct connection.")

    token = os.environ.get("DISCORD_BOT_TOKEN") or input("Bot token: ").strip()
    if not token:
        print("[X] No token. Exiting.")
        sys.exit(1)

    try:
        bot.run(token)
    except discord.LoginFailure:
        print("[X] Invalid bot token. Reset it in Discord Developer Portal.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[!] Shutdown.")
