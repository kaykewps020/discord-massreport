#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║              DISCORD MASS REPORT BOT — v3.0 STEALTH             ║
║        Fully interactive via Discord — English Language         ║
║                  Proxy-aware · Multi-token · Safe               ║
╚══════════════════════════════════════════════════════════════════╝

Commands (prefix: !):
  !addtokens <tok1> [tok2] ...  — Add 1-6 user tokens
  !tokens                        — Show added tokens
  !remtoken <index>              — Remove a token by index
  !report <user_id> [reason]     — Start mass reporting
  !stats                         — Live statistics
  !stop                          — Stop all operations
  !proxies [load|path|status]    — Manage proxies
  !help                          — Show this help
"""

import discord
from discord.ext import commands
from discord import File

import aiohttp
import asyncio
import random
import time
import json
import os
import sys
import signal
import threading
from datetime import datetime
from collections import deque
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

BOT_PREFIX = "!"
BOT_TOKEN = ""  # Will be asked on first run or set via env

DEFAULT_PROXY_PATH = "/storage/emulated/0/Download/Residencial Proxys/proxies.json"
ALT_PROXY_PATHS = [
    "/storage/emulated/0/Download/Residencial Proxys/proxies_simple.txt",
    "/storage/emulated/0/Download/Residencial Proxys/proxies_auth.txt",
]

# Discord's report API endpoints (multiple for redundancy)
REPORT_ENDPOINTS = [
    "https://discord.com/api/v9/reporting/user",
    "https://discord.com/api/v9/report",
    "https://discord.com/api/v9/users/@me/report",
]

REPORT_REASONS = {
    1: "Spam or Phishing",
    2: "Harassment or Hate Speech",
    3: "Inappropriate Content",
    4: "Impersonation",
    5: "Selling Accounts/Items",
    6: "Self-Bot/ToS Violation",
    7: "Other",
}

REPORT_DESCRIPTIONS = [
    "This account is violating Discord's Terms of Service by using automation for spam.",
    "User is sending unsolicited messages with malicious content.",
    "Account suspected of being an automated bot performing activities against guidelines.",
    "User is harassing other members with explicit content and threats.",
    "Identity fraud - this account is impersonating another person.",
    "Distribution of prohibited content and malicious links.",
    "Suspicious invite farming and mass spam activity.",
    "Severe violation of community guidelines with hateful content.",
    "Compromised account being used for phishing attacks.",
    "User is engaging in self-botting and violating the acceptable use policy.",
    "Account spreading disinformation and harmful links in multiple servers.",
    "This user is repeatedly violating Discord's community guidelines.",
    "Sending unsolicited DMs with promotional spam content.",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) discord/1.0.9047 Chrome/120.0.6099.291 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) discord/1.0.9047 Chrome/120.0.6099.291 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 OPR/109.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# ============================================================
# GLOBAL STATE
# ============================================================

class ReportStats:
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
        self.reason_code = 1
        self.is_running = False
        self.timestamps = deque(maxlen=120)  # for RPM calculation
        self.token_stats = {}  # token_prefix -> {total, success, fail}
    
    @property
    def elapsed(self):
        if not self.start_time:
            return "0s"
        e = time.time() - self.start_time
        if e < 60: return f"{e:.0f}s"
        elif e < 3600: return f"{e//60:.0f}m {e%60:.0f}s"
        else: return f"{e//3600:.0f}h {(e%3600)//60:.0f}m"
    
    @property
    def rpm(self):
        now = time.time()
        while self.timestamps and (now - self.timestamps[0]) > 60:
            self.timestamps.popleft()
        return len(self.timestamps)
    
    @property
    def success_rate(self):
        if self.total == 0: return 0.0
        return (self.success / self.total) * 100


stats = ReportStats()
user_tokens = []       # List of user tokens for reporting
proxy_list = []        # List of proxy URLs
proxy_rotation = True  # Rotate proxies between requests
report_task = None     # asyncio.Task for the report loop
stop_event = asyncio.Event()

# ============================================================
# PROXY LOADER
# ============================================================

def load_proxies_from_json(path):
    """Load proxies from JSON format."""
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        proxies = []
        for entry in data:
            if isinstance(entry, dict):
                if 'url' in entry:
                    proxies.append(entry['url'])
                elif 'auth' in entry:
                    proxies.append(f"http://{entry['auth']}")
                elif 'username' in entry:
                    proxies.append(f"http://{entry['username']}:{entry['password']}@{entry['ip']}:{entry['port']}")
        return proxies
    except:
        return []

def load_proxies_from_simple(path):
    """Load proxies from simple format: ip:port:user:pass"""
    proxies = []
    try:
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                parts = line.split(':')
                if len(parts) == 4:
                    proxies.append(f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}")
                elif len(parts) == 2:
                    proxies.append(f"http://{parts[0]}:{parts[1]}")
    except:
        pass
    return proxies

def load_proxies_from_auth(path):
    """Load proxies from auth format: user:pass@ip:port"""
    proxies = []
    try:
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                proxies.append(f"http://{line}")
    except:
        pass
    return proxies

def load_proxies(path=None):
    """Load proxies from various formats."""
    global proxy_list
    
    if path and os.path.exists(path):
        # Try loading based on extension or content
        if path.endswith('.json'):
            proxy_list = load_proxies_from_json(path)
        elif path.endswith('_auth.txt') or path.endswith('_simple.txt'):
            p1 = load_proxies_from_simple(path)
            p2 = load_proxies_from_auth(path)
            proxy_list = p1 or p2
        else:
            # Try all formats
            proxy_list = load_proxies_from_simple(path)
            if not proxy_list:
                proxy_list = load_proxies_from_auth(path)
            if not proxy_list:
                proxy_list = load_proxies_from_json(path)
    else:
        # Try default paths
        for p in [DEFAULT_PROXY_PATH] + ALT_PROXY_PATHS:
            if os.path.exists(p):
                loaded = []
                if p.endswith('.json'):
                    loaded = load_proxies_from_json(p)
                elif '_simple' in p:
                    loaded = load_proxies_from_simple(p)
                elif '_auth' in p:
                    loaded = load_proxies_from_auth(p)
                if loaded:
                    proxy_list = loaded
                    return len(proxy_list)
    
    return len(proxy_list)

# ============================================================
# DISCORD API — REPORT SENDING
# ============================================================

def make_headers(token):
    """Generate realistic headers for Discord API requests."""
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://discord.com",
        "Referer": "https://discord.com/channels/@me",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-Debug-Options": "bugReporterEnabled",
        "X-Discord-Locale": "en-US",
        "X-Super-Properties": "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiRGlzY29yZCIsImRldmljZSI6IiIsInN5c3RlbV9sb2NhbGUiOiJlbi1VUyIsImJyb3dzZXJfdXNlcl9hZ2VudCI6Ik1vemlsbGEvNS4wIChXaW5kb3dzIE5UIDEwLjA7IFdpbjY0OyB4NjQpIEFwcGxlV2Via2l0LzUzNy4zNiAoS0hUTUwsIGxpa2UgR2Vja28pIGRpc2NvcmQvMS4wLjkwNDcgQ2hyb21lLzEyMC4wLjYwOTkuMjkxIFNhZmFyaS81MzcuMzYiLCJicm93c2VyX3ZlcnNpb24iOiIxLjAuOTA0NyIsIm9zX3ZlcnNpb24iOiIxMC4wLjE5MDQ1IiwicmVmZXJyZXIiOiIiLCJyZWZlcnJpbmdfZG9tYWluIjoiIiwicmVmZXJyZXJfY3VycmVudCI6IiIsInJlZmVycmluZ19kb21haW5fY3VycmVudCI6IiIsInJlbGVhc2VfY2hhbm5lbCI6InN0YWJsZSIsImNsaWVudF9idWlsZF9udW1iZXIiOjE5NzQ1MSwiY2xpZW50X2V2ZW50X3NvdXJjZSI6bnVsbH0=",
    }

def make_payload(target_id, reason_code, description):
    """Generate report payload (works across multiple endpoints)."""
    return {
        "user_id": target_id,
        "reason": reason_code,
        "description": description,
        "guild_id": None,
        "channel_id": None,
        "message_id": None,
    }

async def send_report(session, token, target_id, reason_code, description, proxy=None):
    """Send a single report. Returns (status_code, response_text, is_rate_limited, retry_after)."""
    
    headers = make_headers(token)
    payload = make_payload(target_id, reason_code, description)
    
    # Shuffle endpoints to avoid pattern detection
    endpoints = random.sample(REPORT_ENDPOINTS, len(REPORT_ENDPOINTS))
    
    for endpoint in endpoints:
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with session.post(
                endpoint, json=payload, headers=headers,
                timeout=timeout, proxy=proxy
            ) as resp:
                text = await resp.text()
                
                if resp.status == 429:
                    retry_after = 5
                    try:
                        data = json.loads(text)
                        retry_after = data.get("retry_after", 5)
                    except:
                        pass
                    return (429, text, True, retry_after)
                
                if resp.status in (401, 403):
                    return (resp.status, text, False, 0)
                
                if 200 <= resp.status < 300:
                    return (resp.status, "", False, 0)
                
                return (resp.status, text, False, 0)
                
        except asyncio.TimeoutError:
            return (408, "Timeout", False, 0)
        except aiohttp.ClientError as e:
            return (0, str(e), False, 0)
        except Exception as e:
            return (-1, str(e), False, 0)
    
    return (-2, "All endpoints failed", False, 0)


# ============================================================
# TOKEN VALIDATION
# ============================================================

def validate_token(token):
    """Basic token format validation."""
    if not token or len(token) < 15: return False
    parts = token.split('.')
    if len(parts) < 2: return False
    try:
        int(parts[0])
        return True
    except ValueError:
        return False

def validate_user_id(uid):
    """Validate Discord snowflake ID."""
    if not uid or len(uid) < 10: return False
    try:
        int(uid)
        return True
    except ValueError:
        return False

async def verify_token_online(session, token, proxy=None):
    """Verify token against Discord API."""
    headers = make_headers(token)
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with session.get(
            "https://discord.com/api/v9/users/@me",
            headers=headers, timeout=timeout, proxy=proxy
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return (True, data.get("username", "Unknown"), data.get("id", "?"))
            elif resp.status == 401:
                return (False, "Invalid/expired token", None)
            else:
                return (False, f"HTTP {resp.status}", None)
    except Exception as e:
        return (False, str(e)[:60], None)


# ============================================================
# REPORT WORKER — BACKGROUND TASK
# ============================================================

async def report_worker(ctx):
    """Background task that continuously sends reports."""
    global stats, user_tokens, proxy_list, stop_event
    
    stop_event.clear()
    stats.is_running = True
    stats.start_time = time.time()
    stats.target_id = ctx.kwargs.get('target_id', stats.target_id)
    
    token_index = 0
    proxy_index = 0
    consecutive_fails = 0
    
    connector = aiohttp.TCPConnector(limit=0, force_close=False, ttl_dns_cache=300)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        while not stop_event.is_set() and stats.is_running:
            # Rotate token (round-robin)
            token = user_tokens[token_index % len(user_tokens)]
            token_index += 1
            
            # Rotate proxy (if available)
            proxy = None
            if proxy_list:
                proxy = proxy_list[proxy_index % len(proxy_list)]
                if proxy_rotation:
                    proxy_index += 1
            
            # Random description
            description = random.choice(REPORT_DESCRIPTIONS)
            
            # Send report
            status_code, text, is_rl, retry_after = await send_report(
                session, token, stats.target_id, stats.reason_code, description, proxy
            )
            
            # Update stats
            now = time.time()
            stats.total += 1
            stats.timestamps.append(now)
            
            tok_short = token[:20]
            if tok_short not in stats.token_stats:
                stats.token_stats[tok_short] = {"total": 0, "success": 0, "fail": 0}
            stats.token_stats[tok_short]["total"] += 1
            
            if status_code == 429:
                stats.rate_limited += 1
                stats.token_stats[tok_short]["fail"] += 1
                consecutive_fails += 1
                delay = retry_after + random.uniform(1, 3)
                await asyncio.sleep(delay)
                continue
            elif status_code in (401, 403):
                stats.invalid_token += 1
                stats.token_stats[tok_short]["fail"] += 1
                consecutive_fails += 1
                await asyncio.sleep(random.uniform(0.5, 1.5))
                continue
            elif status_code in (408, 0, -1, -2):
                stats.timeout += 1
                stats.fail += 1
                stats.token_stats[tok_short]["fail"] += 1
                consecutive_fails += 1
                await asyncio.sleep(random.uniform(1.0, 3.0))
                continue
            elif 200 <= status_code < 300:
                stats.success += 1
                stats.token_stats[tok_short]["success"] += 1
                consecutive_fails = 0
            else:
                stats.fail += 1
                stats.token_stats[tok_short]["fail"] += 1
                consecutive_fails += 1
            
            # Adaptive delay: increase if consecutive fails
            base_delay = random.uniform(1.5, 4.5)
            if consecutive_fails > 5:
                base_delay *= 2  # Back off
            elif consecutive_fails > 15:
                base_delay *= 4  # Heavy back off
            
            await asyncio.sleep(base_delay)
    
    stats.is_running = False


# ============================================================
# HELPER — STATS EMBED BUILDER
# ============================================================

def build_stats_embed():
    """Build a Discord embed with current statistics."""
    embed = discord.Embed(
        title="📊 Mass Report — Live Statistics",
        color=0x5865F2 if stats.is_running else 0xED4245,
        timestamp=datetime.utcnow(),
    )
    
    if stats.target_id:
        embed.add_field(name="🎯 Target", value=f"`{stats.target_id}`", inline=True)
    
    embed.add_field(name="⏱ Elapsed", value=stats.elapsed, inline=True)
    embed.add_field(name="🚀 RPM", value=f"{stats.rpm}/min", inline=True)
    
    embed.add_field(name="📨 Total", value=f"{stats.total}", inline=True)
    embed.add_field(name="✅ Success", value=f"{stats.success} ({stats.success_rate:.1f}%)", inline=True)
    embed.add_field(name="❌ Failed", value=f"{stats.fail}", inline=True)
    
    embed.add_field(name="⏳ Rate Limited", value=f"{stats.rate_limited}", inline=True)
    embed.add_field(name="⚠️ Timeouts", value=f"{stats.timeout}", inline=True)
    embed.add_field(name="🚫 Invalid Tokens", value=f"{stats.invalid_token}", inline=True)
    
    if stats.is_running:
        embed.set_footer(text="🟢 Running — use !stop to halt")
    else:
        embed.set_footer(text="🔴 Stopped — use !report to start")
    
    return embed


# ============================================================
# DISCORD BOT SETUP
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

# Store which channel to send stats updates to
stats_channel = None
stats_update_task = None

# ============================================================
# COMMANDS
# ============================================================

@bot.event
async def on_ready():
    print(f"[+] Bot logged in as {bot.user} (ID: {bot.user.id})")
    print(f"[+] Prefix: {BOT_PREFIX}")
    print(f"[+] Loaded {len(user_tokens)} user tokens")
    print(f"[+] Loaded {len(proxy_list)} proxies")
    print(f"[+] Bot is ready!")


# ─── HELP ───

@bot.command(name="help")
async def cmd_help(ctx):
    """Show all available commands."""
    embed = discord.Embed(
        title="🤖 Mass Report Bot — Commands",
        description="Interact with me using the prefix `!`",
        color=0x5865F2,
    )
    embed.add_field(
        name="🔑 Token Management",
        value=(
            "`!addtokens <tok1> [tok2] [tok3] [tok4] [tok5] [tok6]`\n"
            "  Add 1-6 user tokens (space separated)\n\n"
            "`!tokens` — List all added tokens\n\n"
            "`!remtoken <index>` — Remove a token by index"
        ),
        inline=False,
    )
    embed.add_field(
        name="🎯 Reporting",
        value=(
            "`!report <user_id> [reason_code]`\n"
            "  Start mass reporting a user.\n"
            "  Reason codes: 1=Spam, 2=Harassment, 3=Inappropriate, 4=Impersonation,\n"
            "               5=Selling, 6=Self-bot, 7=Other\n\n"
            "`!stop` — Stop all report operations\n\n"
            "`!stats` — Display live statistics"
        ),
        inline=False,
    )
    embed.add_field(
        name="🌐 Proxies",
        value=(
            "`!proxies` — Show proxy status\n"
            "`!proxies load [path]` — Load proxies from file\n"
            "`!proxies rotate on/off` — Toggle proxy rotation"
        ),
        inline=False,
    )
    embed.set_footer(text="Bot by OpenCode-Uncensored")
    await ctx.send(embed=embed)


# ─── ADD TOKENS ───

@bot.command(name="addtokens")
async def cmd_addtokens(ctx, *tokens):
    """Add 1-6 user tokens for mass reporting."""
    global user_tokens
    
    if len(tokens) == 0:
        return await ctx.send("❌ Usage: `!addtokens <token1> [token2] ... [token6]`")
    
    if len(tokens) > 6:
        return await ctx.send("❌ Maximum of 6 tokens allowed.")
    
    if stats.is_running:
        return await ctx.send("❌ Cannot change tokens while reporting is active. Use `!stop` first.")
    
    valid = []
    invalid = []
    duplicate = []
    
    for t in tokens:
        t = t.strip()
        if not validate_token(t):
            invalid.append(t[:20] + "...")
            continue
        if t in user_tokens:
            duplicate.append(t[:20] + "...")
            continue
        # Verify online
        async with aiohttp.ClientSession() as session:
            ok, info, uid = await verify_token_online(session, t)
            if ok:
                valid.append((t, info, uid))
            else:
                invalid.append(f"{t[:20]}... ({info})")
    
    if valid:
        for t, username, uid in valid:
            user_tokens.append(t)
    
    embed = discord.Embed(
        title="🔑 Token Status",
        color=0x5865F2,
    )
    if valid:
        embed.add_field(
            name=f"✅ Added ({len(valid)})",
            value="\n".join([f"`{t[:20]}...` → **{u}** (ID: `{i}`)" for t, u, i in valid]),
            inline=False,
        )
    if invalid:
        embed.add_field(
            name=f"❌ Failed ({len(invalid)})",
            value="\n".join([f"`{t}`" for t in invalid[:5]]),
            inline=False,
        )
    if duplicate:
        embed.add_field(
            name=f"⚠️ Duplicates ({len(duplicate)})",
            value="\n".join([f"`{t}`" for t in duplicate[:3]]),
            inline=False,
        )
    embed.add_field(
        name=f"📊 Total Tokens",
        value=f"**{len(user_tokens)}/6**",
        inline=False,
    )
    await ctx.send(embed=embed)


# ─── LIST TOKENS ───

@bot.command(name="tokens")
async def cmd_tokens(ctx):
    """List all added tokens."""
    if not user_tokens:
        return await ctx.send("❌ No tokens added. Use `!addtokens` to add some.")
    
    embed = discord.Embed(
        title="🔑 Registered Tokens",
        description=f"**{len(user_tokens)}/6** tokens loaded",
        color=0x5865F2,
    )
    
    for i, token in enumerate(user_tokens, 1):
        embed.add_field(
            name=f"Token #{i}",
            value=f"```{token[:35]}...```",
            inline=False,
        )
    
    await ctx.send(embed=embed)


# ─── REMOVE TOKEN ───

@bot.command(name="remtoken")
async def cmd_remtoken(ctx, index: int = None):
    """Remove a token by index."""
    global user_tokens
    
    if index is None:
        return await ctx.send("❌ Usage: `!remtoken <index>`")
    
    if stats.is_running:
        return await ctx.send("❌ Cannot modify tokens while reporting. Stop first.")
    
    if index < 1 or index > len(user_tokens):
        return await ctx.send(f"❌ Invalid index. Choose 1-{len(user_tokens)}.")
    
    removed = user_tokens.pop(index - 1)
    await ctx.send(f"✅ Removed token #{index}: `{removed[:25]}...`")


# ─── REPORT ───

@bot.command(name="report")
async def cmd_report(ctx, target_id: str = None, reason_code: int = 1):
    """Start mass reporting a user."""
    global report_task, stats_channel, stats
    
    if not user_tokens:
        return await ctx.send("❌ No tokens loaded. Use `!addtokens` first.")
    
    if target_id is None:
        return await ctx.send("❌ Usage: `!report <user_id> [reason_code]`")
    
    if not validate_user_id(target_id):
        return await ctx.send("❌ Invalid user ID. Must be a numeric Discord snowflake.")
    
    if reason_code not in REPORT_REASONS:
        return await ctx.send(
            f"❌ Invalid reason code. Options:\n"
            + "\n".join([f"  `{k}` = {v}" for k, v in REPORT_REASONS.items()])
        )
    
    if stats.is_running:
        return await ctx.send("⚠️ Report already running. Use `!stop` first or `!stats` to check.")
    
    # Confirm
    reason_name = REPORT_REASONS[reason_code]
    embed = discord.Embed(
        title="🎯 Starting Mass Report",
        color=0x5865F2,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(name="Target User ID", value=f"`{target_id}`", inline=True)
    embed.add_field(name="Reason", value=f"`{reason_name}` (code {reason_code})", inline=True)
    embed.add_field(name="Tokens", value=f"`{len(user_tokens)}`", inline=True)
    embed.add_field(name="Proxies", value=f"`{len(proxy_list)}`" if proxy_list else "`0 (direct)`", inline=True)
    embed.add_field(name="Proxy Rotation", value=f"`{'ON' if proxy_rotation else 'OFF'}`", inline=True)
    embed.set_footer(text="Reports will start immediately...")
    
    await ctx.send(embed=embed)
    
    # Set up stats
    stats.reset()
    stats.target_id = target_id
    stats.reason_code = reason_code
    stats_channel = ctx.channel
    
    # Start background worker
    class FakeCtx:
        def __init__(self, tid):
            self.kwargs = {'target_id': tid}
    
    fake_ctx = FakeCtx(target_id)
    report_task = asyncio.create_task(report_worker(fake_ctx))
    
    # Start periodic stats updates
    global stats_update_task
    stats_update_task = asyncio.create_task(periodic_stats_update(ctx.channel))
    
    # Send initial stats
    await asyncio.sleep(2)
    await ctx.send(embed=build_stats_embed())


# ─── STOP ───

@bot.command(name="stop")
async def cmd_stop(ctx):
    """Stop all report operations."""
    global report_task, stats_update_task
    
    if not stats.is_running:
        return await ctx.send("❌ No report is currently running.")
    
    stop_event.set()
    stats.is_running = False
    
    if stats_update_task:
        stats_update_task.cancel()
        stats_update_task = None
    
    # Send final stats
    embed = build_stats_embed()
    embed.title = "🛑 Mass Report — Stopped"
    embed.color = 0xED4245
    await ctx.send(embed=embed)


# ─── STATS ───

@bot.command(name="stats")
async def cmd_stats(ctx):
    """Display current statistics."""
    if stats.total == 0 and not stats.is_running:
        return await ctx.send("📊 No reports have been sent yet. Use `!report <user_id>` to start.")
    
    embed = build_stats_embed()
    
    # Add per-token breakdown if data exists
    if stats.token_stats:
        breakdown = []
        for tok, tstats in sorted(stats.token_stats.items()):
            rate = (tstats["success"] / tstats["total"] * 100) if tstats["total"] > 0 else 0
            breakdown.append(f"`{tok[:18]}...` → {tstats['success']}/{tstats['total']} ({rate:.0f}%)")
        
        if breakdown:
            embed.add_field(
                name="🔑 Per-Token Breakdown",
                value="\n".join(breakdown[:6]),
                inline=False,
            )
    
    await ctx.send(embed=embed)


# ─── PROXIES ───

@bot.command(name="proxies")
async def cmd_proxies(ctx, action: str = None, *args):
    """Manage proxy configuration."""
    global proxy_list, proxy_rotation
    
    if action is None:
        # Show status
        embed = discord.Embed(
            title="🌐 Proxy Status",
            color=0x5865F2,
        )
        embed.add_field(name="Status", value=f"{'✅ Loaded' if proxy_list else '❌ Not loaded'}", inline=True)
        embed.add_field(name="Count", value=f"`{len(proxy_list)}` proxies", inline=True)
        embed.add_field(name="Rotation", value=f"`{'ON' if proxy_rotation else 'OFF'}`", inline=True)
        if stats_channel and stats.is_running:
            embed.add_field(name="Active Proxy", value=f"`{proxy_list[0][:50]}...`" if proxy_list else "None", inline=False)
        await ctx.send(embed=embed)
        return
    
    if action.lower() == "load":
        path = args[0] if args else None
        count = load_proxies(path)
        if count > 0:
            await ctx.send(f"✅ Loaded **{count}** proxies from `{path or 'default paths'}`")
        else:
            await ctx.send(f"❌ No proxies found at `{path or 'default paths'}`")
        return
    
    if action.lower() == "rotate":
        if args and args[0].lower() in ("on", "true", "1"):
            proxy_rotation = True
            await ctx.send("✅ Proxy rotation turned **ON**")
        elif args and args[0].lower() in ("off", "false", "0"):
            proxy_rotation = False
            await ctx.send("✅ Proxy rotation turned **OFF**")
        else:
            await ctx.send(f"⚠️ Current rotation: `{'ON' if proxy_rotation else 'OFF'}`\nUsage: `!proxies rotate on/off`")
        return
    
    await ctx.send("❌ Unknown action. Use `!proxies`, `!proxies load [path]`, or `!proxies rotate on/off`")


# ─── PERIODIC STATS UPDATES ───

async def periodic_stats_update(channel):
    """Send stats updates every 15 seconds while reporting."""
    try:
        while stats.is_running and not stop_event.is_set():
            await asyncio.sleep(15)
            if stats.is_running and not stop_event.is_set():
                embed = build_stats_embed()
                await channel.send(embed=embed)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[!] Stats update error: {e}")


@bot.event
async def on_command_error(ctx, error):
    """Handle command errors gracefully."""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument. Use `!help` for usage.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument. Use `!help` for usage.")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignore unknown commands
    else:
        await ctx.send(f"❌ Error: {str(error)[:100]}")
        print(f"[!] Command error: {error}")


# ============================================================
# MAIN — ENTRY POINT
# ============================================================

def print_banner():
    """Print startup banner."""
    banner = """
╔══════════════════════════════════════════════════════════════════╗
║              DISCORD MASS REPORT BOT — v3.0 STEALTH             ║
║        Fully interactive via Discord — English Language         ║
║                  Proxy-aware · Multi-token · Safe               ║
╚══════════════════════════════════════════════════════════════════╝
    """
    print(banner)

def get_bot_token():
    """Get the bot token from env or user input."""
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if token:
        return token
    
    print("[!] Bot token not found in environment.")
    print("[!] Please enter your Discord bot token:")
    print("[!] (Or set it via: export DISCORD_BOT_TOKEN='your_token')\n")
    
    try:
        token = input("Token: ").strip()
        if token:
            return token
    except:
        pass
    
    return None

if __name__ == "__main__":
    print_banner()
    
    # Auto-load proxies
    proxy_count = load_proxies()
    print(f"[✓] Auto-loaded {proxy_count} proxies from storage")
    if proxy_count == 0:
        print("[!] No proxies found. Reports will use direct connection.")
    
    # Get bot token
    bot_token = get_bot_token()
    if not bot_token:
        print("[X] No bot token provided. Exiting.")
        sys.exit(1)
    
    try:
        bot.run(bot_token)
    except discord.LoginFailure:
        print("[X] Invalid bot token. Please check your token and try again.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[!] Shutting down...")
        sys.exit(0)
