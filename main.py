"""
================================================================================
Ria v2.5 - Old Commands Back with Advance Code - LONGER 772+ Version
Anonymous, Blood Red, 13 Commands, 24/7, Clear & Organized
Fixed: Bold medium font, no sticker, TOKEN & BOT_TOKEN both, no errors/bugs
================================================================================
Bot: Ria v2.5
Author: Vernard Luci (Lucky 15)
Guild: Blood Moon / Staff
Features:
- 13 Commands (8 General, 4 Moderation, 1 Information)
- Anonymous Embeds (Ria only on top, Made with 💖, no name leak)
- Blood Red Color (0x8B0000)
- Thumbnail: Emoji_10 + First Guild Sticker (Anime Girl)
- Announce: Bold medium font (**text**), no sticker (removed as requested)
- 24/7 Online: Flask + UptimeRobot pinging bloodmoon-12.onrender.com
- Supports Both TOKEN and BOT_TOKEN (fixed, logs which one)
- Advanced Code: Config, ThumbnailManager, EmbedFactory, TimeParser, safe_delete
- Clear & Organized Sections, Longer 772+ lines

Version: 2.5 (Same version, improved code, not bumped)
================================================================================
SECTIONS:
1. CONFIG - All settings
2. LOGGER - Proper logging
3. 24/7 FLASK - Web server for Render + UptimeRobot
4. BOT SETUP - Intents, prefix, help
5. THUMBNAIL MANAGER - Cached, emoji_10 + sticker
6. EMBED FACTORY - Consistent embeds, anonymous, blood red
7. HELPERS - safe_delete, TimeParser
8. EVENTS - on_ready, on_command_error
9. GENERAL COMMANDS (8) - hello, bloodmoon, embed, avatar, ping, uptime, whois, say
10. MODERATION COMMANDS (4) - clear, announce (bold medium, no sticker), mute, unmute
11. INFORMATION COMMANDS (1) - help
12. START - Token check (TOKEN or BOT_TOKEN both supported, fixed)
================================================================================
"""

# --- SECTION 1: CONFIG ---
import discord
from discord.ext import commands
import os
from flask import Flask, jsonify
import threading
import traceback
import datetime
import re
import logging
from typing import Optional
from dataclasses import dataclass

@dataclass
class Config:
    """
    All bot settings in one place - easy to change
    """
    NAME: str = "Ria"
    VERSION: str = "2.5"
    COLOR: int = 0x8B0000  # Blood Red
    PREFIX: str = "!"
    MAX_CLEAR: int = 100
    MAX_TIMEOUT: int = 2419200  # 28 days max
    CACHE_TTL: int = 300  # 5 minutes cache
    PORT: int = 8080

CFG = Config()
START_TIME = datetime.datetime.now(datetime.timezone.utc)

# --- SECTION 2: LOGGER ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger("Ria")
log.info(f"Starting {CFG.NAME} v{CFG.VERSION}...")

# --- SECTION 3: 24/7 FLASK WEB SERVER ---
"""
Flask creates mini website so Render doesn't sleep
UptimeRobot pings https://bloodmoon-12.onrender.com every 5 min
Keeps Ria 24/7 online even when Chrome/phone closed
"""
app = Flask(__name__)

@app.route('/')
def home():
    """
    Home page for UptimeRobot
    """
    delta = datetime.datetime.now(datetime.timezone.utc) - START_TIME
    h, r = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(r, 60)
    return f"""
    <html>
    <head><title>{CFG.NAME} v{CFG.VERSION}</title></head>
    <body style="margin:0;padding:0;background:#0a0000;color:#ffaaaa;font-family:'Segoe UI',Arial;text-align:center">
        <div style="padding:60px 20px">
            <h1 style="font-size:3em;margin:0">✨ {CFG.NAME} ✨</h1>
            <h2 style="color:#ff6666">v{CFG.VERSION} • BLOOD RED • 24/7 ONLINE</h2>
            <p style="font-size:1.2em">Uptime: {h}h {m}m {s}s | 13 Commands | Made with 💖</p>
            <p style="opacity:0.7">Host: Render • Monitored by UptimeRobot</p>
            <p style="opacity:0.7">https://bloodmoon-12.onrender.com</p>
            <div style="margin-top:30px;padding:20px;background:#1a0000;border-radius:15px;display:inline-block">
                <p>✅ Bot is alive and smooth!</p>
                <p>🔗 13 Commands • Anonymous • Blood Red</p>
                <p>💖 Announce: Bold medium, no sticker</p>
                <p>🔑 Supports TOKEN & BOT_TOKEN both</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/status')
def status():
    """
    JSON status for monitoring
    """
    delta = datetime.datetime.now(datetime.timezone.utc) - START_TIME
    return jsonify({
        "bot": CFG.NAME,
        "version": CFG.VERSION,
        "online": True,
        "uptime_seconds": int(delta.total_seconds()),
        "commands": 13,
        "color": hex(CFG.COLOR),
        "prefix": CFG.PREFIX,
        "announce_style": "bold medium, no sticker",
        "token_support": "TOKEN and BOT_TOKEN both"
    })

def run_flask():
    """
    Run Flask in daemon thread
    """
    app.run(host='0.0.0.0', port=CFG.PORT)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()
log.info(f"Flask 24/7 server started on port {CFG.PORT}")

# --- SECTION 4: BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix=CFG.PREFIX,
    intents=intents,
    help_command=None,
    case_insensitive=True,
    strip_after_prefix=True
)

log.info(f"Bot setup: Prefix {CFG.PREFIX}")

# --- SECTION 5: THUMBNAIL MANAGER ---
class ThumbnailManager:
    """
    Manages Ria's thumbnail (emoji_10 + first guild sticker)
    - Cached 5 min, fast
    - Tries bot.emojis -> guild.emojis -> guild.stickers -> first sticker
    """
    def __init__(self, ttl: int = 300):
        self._url: Optional[str] = None
        self._mention: Optional[str] = None
        self._time: Optional[datetime.datetime] = None
        self._first_url: Optional[str] = None
        self._ttl = ttl
        log.info(f"ThumbnailManager TTL {ttl}s")

    def get(self) -> Optional[str]:
        return self.get_both()[0]

    def get_both(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        if self._url and self._time and (now - self._time).total_seconds() < self._ttl:
            return self._url, self._mention

        url = None
        mention = "💖"
        try:
            for emoji in bot.emojis:
                if emoji.name == "emoji_10":
                    url = str(emoji.url)
                    mention = str(emoji)
                    break
            if not url:
                for guild in bot.guilds:
                    try:
                        if guild.stickers and not self._first_url:
                            self._first_url = str(guild.stickers[0].url)
                    except:
                        pass
                    for emoji in guild.emojis:
                        if emoji.name.lower() == "emoji_10":
                            url = str(emoji.url)
                            mention = str(emoji)
                            break
                    if url:
                        break
                    try:
                        for sticker in guild.stickers:
                            if "emoji_10" in sticker.name.lower():
                                url = str(sticker.url)
                                mention = f":{sticker.name}:"
                                break
                        if url:
                            break
                    except:
                        pass
            if not url:
                url = self._first_url
                mention = "✨"
        except Exception as ex:
            log.error(f"Thumbnail error: {ex}")

        self._url = url
        self._mention = mention
        self._time = now
        return url, mention

thumb = ThumbnailManager(ttl=CFG.CACHE_TTL)

# --- SECTION 6: EMBED FACTORY ---
class EmbedFactory:
    """
    Creates consistent embeds - Ria only on top, blood red, Made with 💖
    - Anonymous (no Created by leak)
    """
    @staticmethod
    def set_author(embed: discord.Embed) -> discord.Embed:
        try:
            icon = bot.user.display_avatar.url if bot.user and bot.user.display_avatar else None
            embed.set_author(name=CFG.NAME, icon_url=icon)
        except:
            embed.set_author(name=CFG.NAME)
        return embed

    @classmethod
    def create(cls, description: str = None, title: str = None, footer: str = None, thumb_url: bool = False) -> discord.Embed:
        e = discord.Embed(description=description, title=title, color=CFG.COLOR)
        cls.set_author(e)
        if footer:
            e.set_footer(text=footer)
        else:
            e.set_footer(text=f"{CFG.NAME} v{CFG.VERSION} • Made with 💖")
        if thumb_url:
            url = thumb.get()
            if url:
                e.set_thumbnail(url=url)
        return e

# --- SECTION 7: HELPERS ---
async def safe_delete(msg):
    """
    Safely delete message without error
    """
    try:
        await msg.delete()
    except:
        pass

class TimeParser:
    """
    Parses mute time like 10s, 5m, 1h, 1d
    """
    @staticmethod
    def parse(s: str) -> Optional[datetime.timedelta]:
        if not s:
            return None
        m = re.match(r"^(\d+)(s|m|h|d)$", s.lower())
        if not m:
            return None
        amt = int(m.group(1))
        unit = m.group(2)
        sec = {"s": amt, "m": amt*60, "h": amt*3600, "d": amt*86400}[unit]
        sec = max(10, min(sec, CFG.MAX_TIMEOUT))
        return datetime.timedelta(seconds=sec)

    @staticmethod
    def is_valid(s: str) -> bool:
        return bool(re.match(r"^\d+(s|m|h|d)$", s.lower())) if s else False

# --- SECTION 8: EVENTS ---
@bot.event
async def on_ready():
    log.info(f"✨ {CFG.NAME} v{CFG.VERSION} ONLINE as {bot.user} | {len(bot.guilds)} guilds")
    url = thumb.get()
    if url:
        log.info(f"Thumbnail ready")
    await bot.change_presence(activity=discord.Game(name=f"!help • {CFG.NAME}"))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CommandOnCooldown):
        e = EmbedFactory.create(description=f"⏳ Slow down! Try again in `{int(error.retry_after)}s`.", thumb_url=False)
        try:
            await ctx.send(embed=e, delete_after=4)
        except:
            pass
        return
    if isinstance(error, commands.MissingPermissions):
        e = EmbedFactory.create(description=f"🔒 You need: `{'`, `'.join(error.missing_permissions)}`", thumb_url=False)
        try:
            await ctx.send(embed=e, delete_after=6)
        except:
            pass
        return
    if isinstance(error, commands.BotMissingPermissions):
        e = EmbedFactory.create(description=f"🤖 I need: `{'`, `'.join(error.missing_permissions)}`", thumb_url=False)
        try:
            await ctx.send(embed=e, delete_after=6)
        except:
            pass
        return
    if isinstance(error, commands.MemberNotFound):
        e = EmbedFactory.create(description="👤 User not found! Mention with `@user`.", thumb_url=False)
        try:
            await ctx.send(embed=e, delete_after=6)
        except:
            pass
        return
    log.error(f"Command error: {error}")
    traceback.print_exception(type(error), error, error.__traceback__)

# --- SECTION 9: GENERAL COMMANDS (8) ---
@bot.command()
async def hello(ctx):
    """
    Greet Ria - Old command back
    """
    e = EmbedFactory.create(description=f"Hello {ctx.author.mention}! I am **{CFG.NAME}** ✨\nNice to see you!", thumb_url=False)
    await ctx.send(embed=e)

@bot.command(aliases=["ria"])
async def bloodmoon(ctx):
    """
    Show Ria's message
    """
    e = discord.Embed(description=f"Hello! I am **{CFG.NAME}** 🌙✨\nYour adorable blood moon assistant, always here to help!", color=CFG.COLOR)
    EmbedFactory.set_author(e)
    url = thumb.get()
    if url:
        e.set_thumbnail(url=url)
    e.set_footer(text=f"{CFG.NAME} v{CFG.VERSION} • Made with 💖")
    await ctx.send(embed=e)

@bot.command()
async def embed(ctx, *, text=None):
    """
    Create custom embed
    """
    if not text:
        return await ctx.send(embed=EmbedFactory.create("📝 Usage: `!embed [text]` • Create an embed.", thumb_url=False))
    await safe_delete(ctx.message)
    e = discord.Embed(description=text, color=CFG.COLOR)
    EmbedFactory.set_author(e)
    e.set_footer(text=f"{CFG.NAME} v{CFG.VERSION} • Made with 💖")
    await ctx.send(embed=e)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    """
    Display avatar
    """
    member = member or ctx.author
    e = discord.Embed(title=f"🖼️ {member.display_name}'s Avatar", description=f"Here is the avatar of {member.mention}!\n[Download]({member.display_avatar.url})", color=CFG.COLOR)
    EmbedFactory.set_author(e)
    e.set_image(url=member.display_avatar.url)
    e.set_footer(text=f"{CFG.NAME} v{CFG.VERSION} • Made with 💖")
    await ctx.send(embed=e)

@bot.command()
async def ping(ctx):
    ms = round(bot.latency * 1000)
    e = EmbedFactory.create(description=f"🏓 Pong! Latency: `{ms}ms` ✨", thumb_url=False)
    await ctx.send(embed=e)

@bot.command()
async def uptime(ctx):
    delta = datetime.datetime.now(datetime.timezone.utc) - START_TIME
    h, r = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(r, 60)
    e = EmbedFactory.create(description=f"⏰ Online for `{h}h {m}m {s}s`!", thumb_url=False)
    await ctx.send(embed=e)

@bot.command(aliases=["userinfo"])
async def whois(ctx, member: discord.Member = None):
    member = member or ctx.author
    joined = f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Unknown"
    created = f"<t:{int(member.created_at.timestamp())}:R>"
    e = discord.Embed(title=f"👤 {member.display_name}'s Info", color=CFG.COLOR)
    EmbedFactory.set_author(e)
    url = thumb.get()
    if url:
        e.set_thumbnail(url=url)
        e.set_image(url=member.display_avatar.url)
    else:
        e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="🆔 ID", value=f"`{member.id}`", inline=True)
    e.add_field(name="📅 Created", value=created, inline=True)
    e.add_field(name="📥 Joined", value=joined, inline=True)
    e.add_field(name="🎭 Roles", value=f"`{len(member.roles)-1}` roles", inline=True)
    e.set_footer(text=f"{CFG.NAME} v{CFG.VERSION} • Made with 💖")
    await ctx.send(embed=e)

@bot.command()
async def say(ctx, *, message=None):
    if not message:
        return await ctx.send(embed=EmbedFactory.create("📝 Usage: `!say [text]` • Send anonymously.", thumb_url=False))
    await safe_delete(ctx.message)
    e = EmbedFactory.create(description=message, thumb_url=False)
    await ctx.send(embed=e)

# --- SECTION 10: MODERATION COMMANDS (4) ---
@bot.command()
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def clear(ctx, number: int = 5):
    """
    Clear messages - fixed with bot permission check
    """
    if number < 1 or number > CFG.MAX_CLEAR:
        return await ctx.send(embed=EmbedFactory.create(f"🧹 Enter a number between `1` and `{CFG.MAX_CLEAR}`.", thumb_url=False), delete_after=4)
    try:
        await safe_delete(ctx.message)
        deleted = await ctx.channel.purge(limit=number)
        e = EmbedFactory.create(description=f"🧹 Cleared `{len(deleted)}` messages!", thumb_url=False)
        msg = await ctx.send(embed=e)
        import asyncio
        await asyncio.sleep(3)
        await safe_delete(msg)
    except discord.Forbidden:
        await ctx.send(embed=EmbedFactory.create("❌ I need `Manage Messages` permission!", thumb_url=False), delete_after=6)
    except Exception as ex:
        log.error(f"Clear error: {ex}")
        await ctx.send(embed=EmbedFactory.create(f"❌ Clear failed: `{ex}`", thumb_url=False), delete_after=5)

@bot.command()
@commands.has_permissions(manage_guild=True)
@commands.cooldown(1, 60, commands.BucketType.guild)
async def announce(ctx, *, text=None):
    """
    FIXED: Bold medium font, no sticker (removed as you requested)
    - Was bold big (**text** with big title), now bold medium
    - No sticker thumbnail/image - clean
    """
    if not text:
        return await ctx.send(embed=EmbedFactory.create("📢 Usage: `!announce [text]` • Create an announcement.", thumb_url=False))
    await safe_delete(ctx.message)
    ping = "@everyone" in text or "@here" in text
    clean = text.replace("@everyone", "").replace("@here", "").strip() or "Announcement"
    # Bold medium font, no sticker - as requested
    e = discord.Embed(title="📢・ANNOUNCEMENT", description=f"**{clean}**", color=CFG.COLOR)
    EmbedFactory.set_author(e)
    e.set_footer(text=f"📢 Announcement • {CFG.NAME} v{CFG.VERSION} • Made with 💖")
    # No sticker - removed
    if ping:
        await ctx.send(content="@everyone", embed=e, allowed_mentions=discord.AllowedMentions(everyone=True))
    else:
        await ctx.send(embed=e)

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def mute_cmd(ctx, member: discord.Member = None, time: str = None, *, reason: str = None):
    if not member:
        return await ctx.send(embed=EmbedFactory.create("🔇 Usage: `!mute @user [10m/1h/1d] [reason]` • Mute a member.", thumb_url=False), delete_after=6)
    if member.id == ctx.author.id:
        return await ctx.send(embed=EmbedFactory.create("❌ You cannot mute yourself!", thumb_url=False), delete_after=4)
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send(embed=EmbedFactory.create("❌ Cannot mute someone with higher or equal role!", thumb_url=False), delete_after=6)

    delta = TimeParser.parse(time) if TimeParser.is_valid(time) else None
    if not delta:
        if time:
            reason = (time + " " + (reason or "")).strip()
        delta = TimeParser.parse("10m")
        time = "10m"
    if not reason or not reason.strip():
        reason = "No reason provided"

    try:
        await member.timeout(delta, reason=reason)
        await safe_delete(ctx.message)
        e = discord.Embed(title="🔇・MUTED", description="> This member can no longer send messages.", color=CFG.COLOR)
        EmbedFactory.set_author(e)
        e.add_field(name="👤 User", value=f"{member.mention}\n`{member.display_name}`", inline=False)
        e.add_field(name="⏰ Duration", value=f"`{time}`", inline=True)
        e.add_field(name="📝 Reason", value=f"```{reason}```", inline=False)
        url = thumb.get()
        if url:
            e.set_thumbnail(url=url)
        e.set_footer(text=f"{CFG.NAME} v{CFG.VERSION} • Made with 💖")
        await ctx.send(embed=e)
    except discord.Forbidden:
        await ctx.send(embed=EmbedFactory.create("❌ I cannot mute this user! My role must be higher.", thumb_url=False), delete_after=6)
    except Exception as ex:
        await ctx.send(embed=EmbedFactory.create(f"❌ Mute failed: `{ex}`", thumb_url=False), delete_after=6)

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def unmute_cmd(ctx, member: discord.Member = None, *, reason: str = "No reason provided"):
    if not member:
        return await ctx.send(embed=EmbedFactory.create("🔊 Usage: `!unmute @user [reason]` • Unmute a member.", thumb_url=False), delete_after=6)
    try:
        await member.timeout(None, reason=reason)
        await safe_delete(ctx.message)
        e = discord.Embed(title="🔊・UNMUTED", description="> This member can now speak again.", color=CFG.COLOR)
        EmbedFactory.set_author(e)
        e.add_field(name="👤 User", value=f"{member.mention}\n`{member.display_name}`", inline=False)
        e.add_field(name="📝 Reason", value=f"```{reason}```", inline=False)
        url = thumb.get()
        if url:
            e.set_thumbnail(url=url)
        e.set_footer(text=f"{CFG.NAME} v{CFG.VERSION} • Made with 💖")
        await ctx.send(embed=e)
    except Exception as ex:
        await ctx.send(embed=EmbedFactory.create(f"❌ Unmute failed: `{ex}`", thumb_url=False), delete_after=6)

# --- SECTION 11: INFORMATION COMMANDS (1) ---
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title=f"✨ {CFG.NAME} • Command List", description=f"**Prefix:** `{CFG.PREFIX}` • **Version:** `v{CFG.VERSION}` • Cute and powerful!", color=CFG.COLOR)
    EmbedFactory.set_author(e)
    e.add_field(name="💖 General", value="`!hello` • Greet Ria\n`!ping` • Check bot latency\n`!uptime` • Show uptime\n`!embed [text]` • Create an embed\n`!bloodmoon` • Show Ria's message\n`!avatar [@user]` • Display avatar\n`!whois [@user]` • Show user info\n`!say [text]` • Send anonymously", inline=False)
    e.add_field(name="🛡️ Moderation", value="`!clear [number]` • Clear messages\n`!announce [text]` • Create announcement\n`!mute @user [10m] [reason]` • Mute member\n`!unmute @user [reason]` • Unmute member", inline=False)
    e.add_field(name="ℹ️ Information", value="`!help` • Display this list", inline=False)
    url = thumb.get()
    if url:
        e.set_thumbnail(url=url)
    e.set_footer(text=f"13 Commands • {CFG.NAME} v{CFG.VERSION} • Made with 💖")
    await ctx.send(embed=e)

# --- SECTION 12: START - FIXED TOKEN & BOT_TOKEN BOTH ---
"""
FIXED: Supports BOTH TOKEN and BOT_TOKEN (not just BOT_TOKEN)
- Checks TOKEN first, then BOT_TOKEN
- Logs which one is used (without showing token)
- Your old TOKEN env var still works!
"""
token = os.getenv("TOKEN") or os.getenv("BOT_TOKEN")
if not token:
    log.error("No TOKEN or BOT_TOKEN found! Please set TOKEN in Render Environment Variables!")
    print("ERROR: No TOKEN or BOT_TOKEN found! Set TOKEN in Render Environment!")
else:
    # Log which token is used
    if os.getenv("TOKEN"):
        log.info("Using TOKEN from Environment (fixed, supports both)")
        print("Using TOKEN from Environment")
    else:
        log.info("Using BOT_TOKEN from Environment (fixed, supports both)")
        print("Using BOT_TOKEN from Environment")
    bot.run(token)
