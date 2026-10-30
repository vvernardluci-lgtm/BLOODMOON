
import discord
from discord.ext import commands
import os
from flask import Flask
import threading
import traceback
import datetime
import re

BOT_NAME = "Ria"
BOT_VERSION = "2.5"
BOT_COLOR = 0x8B0000
BOT_START_TIME = datetime.datetime.now(datetime.timezone.utc)

# --- 24/7 WEB SERVER ---
app = Flask(__name__)
@app.route('/')
def home():
    uptime = datetime.datetime.now(datetime.timezone.utc) - BOT_START_TIME
    hours = int(uptime.total_seconds() // 3600)
    return f"{BOT_NAME} v{BOT_VERSION} IS ALIVE - Uptime: {hours}h - 24/7 ONLINE! ✨"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_flask, daemon=True).start()

# --- BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None, case_insensitive=True)

# --- CUSTOM STICKER :emoji_10: FOR THUMBNAIL ---
# Auto-detects emoji named "emoji_10" in your server
# Or set direct URL: EMOJI_10_URL = "https://cdn.discordapp.com/emojis/123456789.png"
EMOJI_10_URL = None

def get_emoji_10_url():
    """Get :emoji_10: sticker URL for thumbnail"""
    try:
        for emoji in bot.emojis:
            if emoji.name == "emoji_10":
                return str(emoji.url)
    except:
        pass
    return EMOJI_10_URL

def blood_embed(description=None, title=None, footer_text=None, timestamp=False):
    embed = discord.Embed(description=description, title=title, color=BOT_COLOR)
    if timestamp:
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    try:
        icon = bot.user.display_avatar.url if bot.user and bot.user.display_avatar else None
        embed.set_author(name=BOT_NAME, icon_url=icon)
    except:
        embed.set_author(name=BOT_NAME)
    if footer_text:
        embed.set_footer(text=footer_text)
    return embed

def parse_time(time_str):
    if not time_str:
        return None, None
    match = re.match(r"^(\d+)(s|m|h|d)$", time_str.lower())
    if not match:
        return None, None
    amount = int(match.group(1))
    unit = match.group(2)
    seconds = {"s": amount, "m": amount*60, "h": amount*3600, "d": amount*86400}[unit]
    seconds = max(10, min(seconds, 2419200))
    return seconds, datetime.timedelta(seconds=seconds)

@bot.event
async def on_ready():
    print(f"✨ {BOT_NAME} v{BOT_VERSION} ONLINE as {bot.user} | {len(bot.guilds)} servers")
    emoji_url = get_emoji_10_url()
    if emoji_url:
        print(f"✅ Found :emoji_10: thumbnail: {emoji_url}")
    await bot.change_presence(activity=discord.Game(name=f"{BOT_NAME} v{BOT_VERSION} | !help"))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CommandOnCooldown):
        e = blood_embed(description=f"⏳ You are on cooldown! Please try again in `{int(error.retry_after)}s`.")
        try:
            await ctx.send(embed=e, delete_after=5)
        except:
            pass
        return
    if isinstance(error, commands.MissingPermissions):
        e = blood_embed(description=f"🔒 You need the following permission: `{', '.join(error.missing_permissions)}`")
        try:
            await ctx.send(embed=e, delete_after=7)
        except:
            pass
        return
    if isinstance(error, commands.BotMissingPermissions):
        e = blood_embed(description=f"🤖 I need the following permission: `{', '.join(error.missing_permissions)}`")
        try:
            await ctx.send(embed=e, delete_after=7)
        except:
            pass
        return
    if isinstance(error, commands.MemberNotFound):
        e = blood_embed(description="👤 User not found! Please mention a valid user using `@user`.")
        try:
            await ctx.send(embed=e, delete_after=7)
        except:
            pass
        return
    print(f"ERROR: {error}")
    traceback.print_exception(type(error), error, error.__traceback__)

# --- GENERAL ---
@bot.command()
async def hello(ctx):
    e = blood_embed(description=f"Hello {ctx.author.mention}! I am **{BOT_NAME}** ✨\nNice to see you!", footer_text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=e)

@bot.command(aliases=["ria"])
async def bloodmoon(ctx):
    e = blood_embed(description=f"Hello! I am **{BOT_NAME}** 🌙✨\nYour adorable blood moon assistant, always here to help!", footer_text=f"{BOT_NAME} v{BOT_VERSION} • Made with 💖")
    emoji_url = get_emoji_10_url()
    if emoji_url:
        e.set_thumbnail(url=emoji_url)
    await ctx.send(embed=e)

@bot.command()
async def embed(ctx, *, text=None):
    if not text:
        return await ctx.send(embed=blood_embed(description="📝 Usage: `!embed [text]` — Create a custom embed message."))
    try:
        await ctx.message.delete()
    except:
        pass
    e = blood_embed(description=text, footer_text=f"Created by {ctx.author.display_name}")
    try:
        e.set_footer(text=f"Created by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    except:
        pass
    await ctx.send(embed=e)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    e = discord.Embed(title=f"🖼️ {member.display_name}'s Avatar", description=f"Here is the avatar of {member.mention}!\n[Download]({member.display_avatar.url})", color=BOT_COLOR)
    try:
        e.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url if bot.user else None)
    except:
        e.set_author(name=BOT_NAME)
    e.set_image(url=member.display_avatar.url)
    e.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=e)

@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    e = blood_embed(description=f"🏓 Pong! My latency is `{latency}ms`.", footer_text=f"{BOT_NAME} v{BOT_VERSION}")
    await ctx.send(embed=e)

@bot.command()
async def uptime(ctx):
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = now - BOT_START_TIME
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    e = blood_embed(description=f"⏰ I have been online for `{hours}h {minutes}m {seconds}s`!", footer_text=f"Since {BOT_START_TIME.strftime('%Y-%m-%d %H:%M UTC')}")
    await ctx.send(embed=e)

@bot.command(aliases=["userinfo"])
async def whois(ctx, member: discord.Member = None):
    member = member or ctx.author
    joined = f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Unknown"
    created = f"<t:{int(member.created_at.timestamp())}:R>"
    e = discord.Embed(title=f"👤 {member.display_name}'s Info", color=BOT_COLOR)
    try:
        e.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url if bot.user else None)
    except:
        e.set_author(name=BOT_NAME)
    # --- THUMBNAIL IS NOW :emoji_10: STICKER ---
    emoji_url = get_emoji_10_url()
    if emoji_url:
        e.set_thumbnail(url=emoji_url)
        e.set_image(url=member.display_avatar.url)
    else:
        e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="🆔 ID", value=f"`{member.id}`", inline=True)
    e.add_field(name="📅 Created", value=created, inline=True)
    e.add_field(name="📥 Joined", value=joined, inline=True)
    e.add_field(name="🎭 Roles", value=f"`{len(member.roles)-1}` roles", inline=True)
    e.set_footer(text=f"Requested by {ctx.author.display_name} • :emoji_10:")
    await ctx.send(embed=e)

@bot.command()
async def say(ctx, *, message=None):
    if not message:
        return await ctx.send(embed=blood_embed(description="📝 Usage: `!say [text]` — Send a message anonymously."))
    try:
        await ctx.message.delete()
    except:
        pass
    e = blood_embed(description=message)
    await ctx.send(embed=e)

# --- MODERATION ---
@bot.command()
@commands.has_permissions(manage_messages=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def clear(ctx, number: int = 5):
    if number < 1 or number > 100:
        return await ctx.send(embed=blood_embed(description="🧹 Please provide a number between `1` and `100`."), delete_after=5)
    try:
        deleted = await ctx.channel.purge(limit=number + 1)
        e = blood_embed(description=f"🧹 Successfully cleared `{len(deleted)-1}` messages!", footer_text=f"Cleared by {ctx.author.display_name}")
        await ctx.send(embed=e, delete_after=3)
    except Exception as ex:
        await ctx.send(embed=blood_embed(description=f"❌ Failed to clear messages: `{ex}`"), delete_after=5)

@bot.command()
@commands.has_permissions(manage_guild=True)
@commands.cooldown(1, 60, commands.BucketType.guild)
async def announce(ctx, *, text=None):
    if not text:
        return await ctx.send(embed=blood_embed(description="📢 Usage: `!announce [text]` — Create an announcement."))
    try:
        await ctx.message.delete()
    except:
        pass
    ping_everyone = "@everyone" in text or "@here" in text
    clean_text = text.replace("@everyone", "").replace("@here", "").strip() or "Announcement"
    e = discord.Embed(title="📢・ANNOUNCEMENT", description=clean_text, color=BOT_COLOR)
    try:
        e.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url if bot.user else None)
    except:
        e.set_author(name=BOT_NAME)
    e.set_footer(text=f"Announced by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    if ping_everyone:
        await ctx.send(content="@everyone", embed=e, allowed_mentions=discord.AllowedMentions(everyone=True))
    else:
        await ctx.send(embed=e)

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def mute_cmd(ctx, member: discord.Member = None, time: str = None, *, reason: str = None):
    if member is None:
        return await ctx.send(embed=blood_embed(description="🔇 Usage: `!mute @user [10m/1h/1d] [reason]` — Mute a member."), delete_after=7)
    if member.id == ctx.author.id:
        return await ctx.send(embed=blood_embed(description="❌ You cannot mute yourself!"), delete_after=5)
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send(embed=blood_embed(description="❌ You cannot mute someone with a higher or equal role!"), delete_after=7)
    if time and re.match(r"^\d+(s|m|h|d)$", time.lower()):
        seconds, delta = parse_time(time)
    else:
        if time:
            reason = (time + " " + (reason or "")).strip()
        seconds, delta = parse_time("10m")
        time = "10m"
    if delta is None:
        seconds, delta = parse_time("10m")
        time = "10m"
    if not reason or not reason.strip():
        reason = "No reason provided"
    try:
        await member.timeout(delta, reason=reason)
        try:
            await ctx.message.delete()
        except:
            pass
        e = discord.Embed(title="🔇・MUTED", description="> A member has been muted and cannot send messages.", color=BOT_COLOR)
        try:
            e.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url if bot.user else None)
        except:
            e.set_author(name=BOT_NAME)
        e.add_field(name="👤 User", value=f"{member.mention}\n`{member.display_name}`", inline=False)
        e.add_field(name="⏰ Duration", value=f"`{time}`", inline=True)
        e.add_field(name="\u200b", value="\u200b", inline=True)
        e.add_field(name="📝 Reason", value=f"```{reason}```", inline=False)
        emoji_url = get_emoji_10_url()
        if emoji_url:
            e.set_thumbnail(url=emoji_url)
        e.set_footer(text=f"🛡️ Muted by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=e)
    except discord.Forbidden:
        await ctx.send(embed=blood_embed(description="❌ I do not have permission to mute that user! Please ensure my role is higher than theirs."), delete_after=7)
    except Exception as ex:
        await ctx.send(embed=blood_embed(description=f"❌ Failed to mute the user: `{ex}`"), delete_after=7)

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def unmute_cmd(ctx, member: discord.Member = None, *, reason: str = "No reason provided"):
    if member is None:
        return await ctx.send(embed=blood_embed(description="🔊 Usage: `!unmute @user [reason]` — Unmute a member."), delete_after=7)
    try:
        await member.timeout(None, reason=reason)
        try:
            await ctx.message.delete()
        except:
            pass
        e = discord.Embed(title="🔊・UNMUTED", description="> A member has been unmuted and can now speak again.", color=BOT_COLOR)
        try:
            e.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url if bot.user else None)
        except:
            e.set_author(name=BOT_NAME)
        e.add_field(name="👤 User", value=f"{member.mention}\n`{member.display_name}`", inline=False)
        e.add_field(name="📝 Reason", value=f"```{reason}```", inline=False)
        emoji_url = get_emoji_10_url()
        if emoji_url:
            e.set_thumbnail(url=emoji_url)
        e.set_footer(text=f"🛡️ Unmuted by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=e)
    except Exception as ex:
        await ctx.send(embed=blood_embed(description=f"❌ Failed to unmute the user: `{ex}`"), delete_after=7)

@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(
        title=f"✨ {BOT_NAME} • Command List",
        description=f"**Prefix:** `!` • **Version:** `v{BOT_VERSION}` • Cute and powerful!",
        color=BOT_COLOR
    )
    try:
        e.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url if bot.user else None)
    except:
        e.set_author(name=BOT_NAME)
    e.add_field(
        name="💖 General Commands",
        value=(
            "`!hello` • Greet Ria\n"
            "`!ping` • Check bot latency\n"
            "`!uptime` • Show uptime\n"
            "`!embed [text]` • Create an embed\n"
            "`!bloodmoon` • Show Ria's message\n"
            "`!avatar [@user]` • Display avatar\n"
            "`!whois [@user]` • Show user info\n"
            "`!say [text]` • Send anonymously"
        ),
        inline=False
    )
    e.add_field(
        name="🛡️ Moderation",
        value=(
            "`!clear [number]` • Clear messages\n"
            "`!announce [text]` • Create announcement\n"
            "`!mute @user [10m] [reason]` • Mute member\n"
            "`!unmute @user [reason]` • Unmute member"
        ),
        inline=False
    )
    e.add_field(
        name="ℹ️ Information",
        value="`!help` • Display this list",
        inline=False
    )
    emoji_url = get_emoji_10_url()
    if emoji_url:
        e.set_thumbnail(url=emoji_url)
    e.set_footer(text=f"13 Commands • {BOT_NAME} v{BOT_VERSION} • :emoji_10: • Made with 💖")
    await ctx.send(embed=e)

# --- START ---
token = os.getenv("TOKEN") or os.getenv("BOT_TOKEN")
if not token:
    print("ERROR: No TOKEN or BOT_TOKEN found!")
else:
    bot.run(token)
    
