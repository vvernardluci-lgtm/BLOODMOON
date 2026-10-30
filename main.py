import discord
from discord.ext import commands
import os
from flask import Flask
import threading
import traceback
import datetime
import re
from typing import Optional

# --- CONFIG v2.5 (Improved Code, Same Version) ---
BOT_NAME = "Ria"
BOT_VERSION = "2.5"
BOT_COLOR = 0x8B0000
BOT_START_TIME = datetime.datetime.now(datetime.timezone.utc)
MAX_CLEAR = 100
MAX_TIMEOUT = 2419200
CACHE_SECONDS = 300

# --- 24/7 WEB SERVER (Improved) ---
app = Flask(__name__)
@app.route('/')
def home():
    delta = datetime.datetime.now(datetime.timezone.utc) - BOT_START_TIME
    h = int(delta.total_seconds() // 3600)
    m = int((delta.total_seconds() % 3600) // 60)
    return f"""
    <html><body style="background:#1a0000;color:#ffcccc;font-family:Arial;text-align:center;padding:50px">
    <h1>✨ {BOT_NAME} v{BOT_VERSION} IS ALIVE ✨</h1>
    <p>Uptime: {h}h {m}m</p>
    <p>24/7 ONLINE | Blood Red Embeds | Made with 💖</p>
    <p>discord.gg/bloodmoon</p>
    </body></html>
    """

def run_flask():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_flask, daemon=True).start()

# --- BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None, case_insensitive=True, strip_after_prefix=True)

# --- THUMBNAIL (Cached & Optimized) ---
_cache_url: Optional[str] = None
_cache_time: Optional[datetime.datetime] = None
_first_sticker_url: Optional[str] = None

def get_emoji_10_url() -> Optional[str]:
    """Get thumbnail URL - cached for 5 min, tries emoji_10 then first sticker"""
    global _cache_url, _cache_time, _first_sticker_url
    now = datetime.datetime.now(datetime.timezone.utc)
    if _cache_url and _cache_time and (now - _cache_time).total_seconds() < CACHE_SECONDS:
        return _cache_url

    url = None
    try:
        # 1. Bot emojis
        for emoji in bot.emojis:
            if emoji.name == "emoji_10":
                url = str(emoji.url)
                break
        # 2. Guilds
        if not url:
            for guild in bot.guilds:
                try:
                    if guild.stickers and not _first_sticker_url:
                        _first_sticker_url = str(guild.stickers[0].url)
                except:
                    pass
                for emoji in guild.emojis:
                    if emoji.name.lower() == "emoji_10":
                        url = str(emoji.url)
                        break
                if url:
                    break
                try:
                    for sticker in guild.stickers:
                        if "emoji_10" in sticker.name.lower():
                            url = str(sticker.url)
                            break
                    if url:
                        break
                except:
                    pass
        # 3. Fallback to first sticker
        if not url:
            url = _first_sticker_url
    except Exception as ex:
        print(f"[Thumbnail] Error: {ex}")

    _cache_url = url
    _cache_time = now
    return url

# --- HELPERS (Improved) ---
def set_ria_author(embed: discord.Embed) -> discord.Embed:
    try:
        icon = bot.user.display_avatar.url if bot.user and bot.user.display_avatar else None
        embed.set_author(name=BOT_NAME, icon_url=icon)
    except:
        embed.set_author(name=BOT_NAME)
    return embed

def blood_embed(description: str = None, title: str = None, footer: str = None) -> discord.Embed:
    e = discord.Embed(description=description, title=title, color=BOT_COLOR)
    set_ria_author(e)
    if footer:
        e.set_footer(text=footer)
    return e

async def safe_delete(msg):
    try:
        await msg.delete()
    except:
        pass

def parse_time(s: str) -> Optional[datetime.timedelta]:
    if not s:
        return None
    m = re.match(r"^(\d+)(s|m|h|d)$", s.lower())
    if not m:
        return None
    amt = int(m.group(1))
    unit = m.group(2)
    sec = {"s": amt, "m": amt*60, "h": amt*3600, "d": amt*86400}[unit]
    sec = max(10, min(sec, MAX_TIMEOUT))
    return datetime.timedelta(seconds=sec)

# --- EVENTS ---
@bot.event
async def on_ready():
    print(f"✨ {BOT_NAME} v{BOT_VERSION} ONLINE as {bot.user} | {len(bot.guilds)} servers")
    url = get_emoji_10_url()
    if url:
        print(f"✅ Thumbnail: {url[:70]}...")
    await bot.change_presence(activity=discord.Game(name=f"!help • {BOT_NAME}"))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CommandOnCooldown):
        e = blood_embed(description=f"⏳ Slow down! Try again in `{int(error.retry_after)}s`.")
        try:
            await ctx.send(embed=e, delete_after=4)
        except:
            pass
        return
    if isinstance(error, commands.MissingPermissions):
        e = blood_embed(description=f"🔒 You need: `{'`, `'.join(error.missing_permissions)}`")
        try:
            await ctx.send(embed=e, delete_after=6)
        except:
            pass
        return
    if isinstance(error, commands.BotMissingPermissions):
        e = blood_embed(description=f"🤖 I need: `{'`, `'.join(error.missing_permissions)}`")
        try:
            await ctx.send(embed=e, delete_after=6)
        except:
            pass
        return
    if isinstance(error, commands.MemberNotFound):
        e = blood_embed(description="👤 User not found! Mention with `@user`.")
        try:
            await ctx.send(embed=e, delete_after=6)
        except:
            pass
        return
    print(f"ERROR: {error}")
    traceback.print_exception(type(error), error, error.__traceback__)

# --- GENERAL (Improved Wording) ---
@bot.command()
async def hello(ctx):
    e = blood_embed(description=f"Hello {ctx.author.mention}! I am **{BOT_NAME}** ✨\nSo nice to see you!", footer=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=e)

@bot.command(aliases=["ria"])
async def bloodmoon(ctx):
    url = get_emoji_10_url()
    e = discord.Embed(description=f"Hey! I am **{BOT_NAME}** 🌙✨\nYour cute blood moon assistant, always here to help you!", color=BOT_COLOR)
    set_ria_author(e)
    if url:
        e.set_thumbnail(url=url)
    e.set_footer(text=f"{BOT_NAME} v{BOT_VERSION} • Made with 💖")
    await ctx.send(embed=e)

@bot.command()
async def embed(ctx, *, text=None):
    if not text:
        return await ctx.send(embed=blood_embed("📝 Usage: `!embed [text]` • Create a custom embed."))
    await safe_delete(ctx.message)
    e = discord.Embed(description=text, color=BOT_COLOR)
    set_ria_author(e)
    e.set_footer(text=f"Created by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=e)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    e = discord.Embed(title=f"🖼️ {member.display_name}'s Avatar", description=f"Avatar of {member.mention}\n[Download Link]({member.display_avatar.url})", color=BOT_COLOR)
    set_ria_author(e)
    e.set_image(url=member.display_avatar.url)
    e.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=e)

@bot.command()
async def ping(ctx):
    ms = round(bot.latency * 1000)
    e = blood_embed(description=f"🏓 Pong! Latency: `{ms}ms` ✨", footer=f"{BOT_NAME} v{BOT_VERSION}")
    await ctx.send(embed=e)

@bot.command()
async def uptime(ctx):
    delta = datetime.datetime.now(datetime.timezone.utc) - BOT_START_TIME
    h, r = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(r, 60)
    e = blood_embed(description=f"⏰ Online for `{h}h {m}m {s}s` • Always here for you!", footer=f"Since {BOT_START_TIME.strftime('%Y-%m-%d %H:%M UTC')}")
    await ctx.send(embed=e)

@bot.command(aliases=["userinfo"])
async def whois(ctx, member: discord.Member = None):
    member = member or ctx.author
    joined = f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Unknown"
    created = f"<t:{int(member.created_at.timestamp())}:R>"
    e = discord.Embed(title=f"👤 {member.display_name}", description=f"Information about {member.mention}", color=BOT_COLOR)
    set_ria_author(e)
    url = get_emoji_10_url()
    if url:
        e.set_thumbnail(url=url)
        e.set_image(url=member.display_avatar.url)
    else:
        e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="🆔 ID", value=f"`{member.id}`", inline=True)
    e.add_field(name="📅 Created", value=created, inline=True)
    e.add_field(name="📥 Joined", value=joined, inline=True)
    e.add_field(name="🎭 Roles", value=f"`{len(member.roles)-1}` roles", inline=True)
    e.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=e)

@bot.command()
async def say(ctx, *, message=None):
    if not message:
        return await ctx.send(embed=blood_embed("📝 Usage: `!say [text]` • Send anonymously."))
    await safe_delete(ctx.message)
    e = blood_embed(description=message)
    await ctx.send(embed=e)

# --- MODERATION (Improved Design) ---
@bot.command()
@commands.has_permissions(manage_messages=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def clear(ctx, number: int = 5):
    if number < 1 or number > MAX_CLEAR:
        return await ctx.send(embed=blood_embed(f"🧹 Enter a number between `1` and `{MAX_CLEAR}`."), delete_after=4)
    try:
        deleted = await ctx.channel.purge(limit=number + 1)
        e = blood_embed(description=f"🧹 Cleared `{len(deleted)-1}` messages!", footer=f"Cleared by {ctx.author.display_name}")
        await ctx.send(embed=e, delete_after=3)
    except Exception as ex:
        await ctx.send(embed=blood_embed(f"❌ Clear failed: `{ex}`"), delete_after=4)

@bot.command()
@commands.has_permissions(manage_guild=True)
@commands.cooldown(1, 60, commands.BucketType.guild)
async def announce(ctx, *, text=None):
    if not text:
        return await ctx.send(embed=blood_embed("📢 Usage: `!announce [text]` • Create an announcement."))
    await safe_delete(ctx.message)
    ping = "@everyone" in text or "@here" in text
    clean = text.replace("@everyone", "").replace("@here", "").strip() or "Announcement"
    e = discord.Embed(title="📢・ANNOUNCEMENT", description=clean, color=BOT_COLOR)
    set_ria_author(e)
    e.set_footer(text=f"Announced by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
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
        return await ctx.send(embed=blood_embed("🔇 Usage: `!mute @user [10m/1h/1d] [reason]` • Mute a member."), delete_after=6)
    if member.id == ctx.author.id:
        return await ctx.send(embed=blood_embed("❌ You cannot mute yourself!"), delete_after=4)
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send(embed=blood_embed("❌ Cannot mute someone with higher or equal role!"), delete_after=6)

    delta = parse_time(time) if time and re.match(r"^\d+(s|m|h|d)$", time.lower()) else None
    if not delta:
        if time:
            reason = (time + " " + (reason or "")).strip()
        delta = parse_time("10m")
        time = "10m"
    if not reason or not reason.strip():
        reason = "No reason provided"

    try:
        await member.timeout(delta, reason=reason)
        await safe_delete(ctx.message)
        e = discord.Embed(title="🔇・MUTED", description="> This member can no longer send messages.", color=BOT_COLOR)
        set_ria_author(e)
        e.add_field(name="👤 User", value=f"{member.mention}\n`{member.display_name}`", inline=False)
        e.add_field(name="⏰ Duration", value=f"`{time}`", inline=True)
        e.add_field(name="📝 Reason", value=f"```{reason}```", inline=False)
        url = get_emoji_10_url()
        if url:
            e.set_thumbnail(url=url)
        e.set_footer(text=f"🛡️ Muted by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=e)
    except discord.Forbidden:
        await ctx.send(embed=blood_embed("❌ I cannot mute this user! My role must be higher."), delete_after=6)
    except Exception as ex:
        await ctx.send(embed=blood_embed(f"❌ Mute failed: `{ex}`"), delete_after=6)

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def unmute_cmd(ctx, member: discord.Member = None, *, reason: str = "No reason provided"):
    if not member:
        return await ctx.send(embed=blood_embed("🔊 Usage: `!unmute @user [reason]` • Unmute a member."), delete_after=6)
    try:
        await member.timeout(None, reason=reason)
        await safe_delete(ctx.message)
        e = discord.Embed(title="🔊・UNMUTED", description="> This member can now speak again.", color=BOT_COLOR)
        set_ria_author(e)
        e.add_field(name="👤 User", value=f"{member.mention}\n`{member.display_name}`", inline=False)
        e.add_field(name="📝 Reason", value=f"```{reason}```", inline=False)
        url = get_emoji_10_url()
        if url:
            e.set_thumbnail(url=url)
        e.set_footer(text=f"🛡️ Unmuted by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=e)
    except Exception as ex:
        await ctx.send(embed=blood_embed(f"❌ Unmute failed: `{ex}`"), delete_after=6)

@bot.command(name="help")
async def help_cmd(ctx):
    url = get_emoji_10_url()
    e = discord.Embed(title=f"✨ {BOT_NAME} • Command List", description=f"**Prefix:** `!` • **Version:** `v{BOT_VERSION}` • Cute and powerful!", color=BOT_COLOR)
    set_ria_author(e)
    e.add_field(name="💖 General", value="`!hello` • Greet Ria\n`!ping` • Check bot latency\n`!uptime` • Show uptime\n`!embed [text]` • Create an embed\n`!bloodmoon` • Show Ria's message\n`!avatar [@user]` • Display avatar\n`!whois [@user]` • Show user info\n`!say [text]` • Send anonymously", inline=False)
    e.add_field(name="🛡️ Moderation", value="`!clear [number]` • Clear messages\n`!announce [text]` • Create announcement\n`!mute @user [10m] [reason]` • Mute member\n`!unmute @user [reason]` • Unmute member", inline=False)
    e.add_field(name="ℹ️ Information", value="`!help` • Display this list", inline=False)
    if url:
        e.set_thumbnail(url=url)
    e.set_footer(text=f"13 Commands • {BOT_NAME} v{BOT_VERSION} • Made with 💖")
    await ctx.send(embed=e)

# --- START ---
token = os.getenv("TOKEN") or os.getenv("BOT_TOKEN")
if not token:
    print("ERROR: No TOKEN!")
else:
    bot.run(token)
