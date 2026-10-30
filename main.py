"""
Ria v2.5 - Old Commands Back with Advance Code
Anonymous, Blood Red, 13 Commands, 24/7
"""
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

# --- CONFIG ---
@dataclass
class Config:
    NAME: str = "Ria"
    VERSION: str = "2.5"
    COLOR: int = 0x8B0000
    PREFIX: str = "!"
    MAX_CLEAR: int = 100
    MAX_TIMEOUT: int = 2419200
    CACHE_TTL: int = 300
    PORT: int = 8080

CFG = Config()
START_TIME = datetime.datetime.now(datetime.timezone.utc)

# --- LOGGER ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
log = logging.getLogger("Ria")

# --- 24/7 FLASK ---
app = Flask(__name__)
@app.route('/')
def home():
    delta = datetime.datetime.now(datetime.timezone.utc) - START_TIME
    h, m = divmod(int(delta.total_seconds()), 3600)
    m, _ = divmod(m, 60)
    return f"""
    <html><body style="background:#0a0000;color:#ffaaaa;font-family:Arial;text-align:center;padding:60px">
    <h1>✨ {CFG.NAME} v{CFG.VERSION} IS ALIVE ✨</h1>
    <p>Uptime: {h}h {m}m | 13 Commands | Made with 💖</p>
    </body></html>
    """

@app.route('/status')
def status():
    delta = datetime.datetime.now(datetime.timezone.utc) - START_TIME
    return jsonify({"bot": CFG.NAME, "version": CFG.VERSION, "online": True, "uptime": int(delta.total_seconds())})

def run_flask():
    app.run(host='0.0.0.0', port=CFG.PORT)

threading.Thread(target=run_flask, daemon=True).start()
log.info(f"Flask started on port {CFG.PORT}")

# --- BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=CFG.PREFIX, intents=intents, help_command=None, case_insensitive=True, strip_after_prefix=True)

# --- THUMBNAIL MANAGER (Old + Advance) ---
class ThumbnailManager:
    def __init__(self, ttl: int = 300):
        self._url: Optional[str] = None
        self._mention: Optional[str] = None
        self._time: Optional[datetime.datetime] = None
        self._first_url: Optional[str] = None
        self._ttl = ttl

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

# --- EMBED FACTORY (Old Commands Anonymous) ---
class EmbedFactory:
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

async def safe_delete(msg):
    try:
        await msg.delete()
    except:
        pass

class TimeParser:
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

# --- EVENTS ---
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

# --- GENERAL - OLD COMMANDS BACK (Anonymous, Presentable) ---
@bot.command()
async def hello(ctx):
    e = EmbedFactory.create(description=f"Hello {ctx.author.mention}! I am **{CFG.NAME}** ✨\nNice to see you!", thumb_url=False)
    await ctx.send(embed=e)

@bot.command(aliases=["ria"])
async def bloodmoon(ctx):
    e = discord.Embed(description=f"Hello! I am **{CFG.NAME}** 🌙✨\nYour adorable blood moon assistant, always here to help!", color=CFG.COLOR)
    EmbedFactory.set_author(e)
    url = thumb.get()
    if url:
        e.set_thumbnail(url=url)
    e.set_footer(text=f"{CFG.NAME} v{CFG.VERSION} • Made with 💖")
    await ctx.send(embed=e)

@bot.command()
async def embed(ctx, *, text=None):
    if not text:
        return await ctx.send(embed=EmbedFactory.create("📝 Usage: `!embed [text]` • Create an embed.", thumb_url=False))
    await safe_delete(ctx.message)
    e = discord.Embed(description=text, color=CFG.COLOR)
    EmbedFactory.set_author(e)
    e.set_footer(text=f"{CFG.NAME} v{CFG.VERSION} • Made with 💖")
    await ctx.send(embed=e)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
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

# --- MODERATION - OLD + ADVANCE ---
@bot.command()
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def clear(ctx, number: int = 5):
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
    if not text:
        return await ctx.send(embed=EmbedFactory.create("📢 Usage: `!announce [text]` • Create an announcement.", thumb_url=False))
    await safe_delete(ctx.message)
    ping = "@everyone" in text or "@here" in text
    clean = text.replace("@everyone", "").replace("@here", "").strip() or "Announcement"
    url, mention = thumb.get_both()
    e = discord.Embed(title="📢・ANNOUNCEMENT", description=f"**{clean}** {mention}", color=CFG.COLOR)
    EmbedFactory.set_author(e)
    e.set_footer(text=f"📢 Announcement • {CFG.NAME} v{CFG.VERSION} • Made with 💖")
    if url:
        e.set_thumbnail(url=url)
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

# --- START (Both TOKEN and BOT_TOKEN) ---
token = os.getenv("TOKEN") or os.getenv("BOT_TOKEN")
if not token:
    log.error("No TOKEN or BOT_TOKEN found!")
    print("ERROR: No TOKEN or BOT_TOKEN found!")
else:
    if os.getenv("TOKEN"):
        log.info("Using TOKEN")
    else:
        log.info("Using BOT_TOKEN")
    bot.run(token)
    
