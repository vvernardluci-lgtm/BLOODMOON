
import discord
from discord.ext import commands
import os
from flask import Flask
import threading
import traceback
import datetime
import re

BOT_NAME = "Ria"
BOT_VERSION = "2.0"
BOT_COLOR = 0x8B0000  # Blood red

# --- 24/7 WEB SERVER (UptimeRobot + Render) ---
app = Flask(__name__)
@app.route('/')
def home():
    return f"{BOT_NAME} v{BOT_VERSION} IS ALIVE - 24/7 ONLINE! ✨"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_flask, daemon=True).start()

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

def blood_embed(description=None, title=None, footer_text=None):
    """Clean Ria embed - blood red, Ria on top"""
    embed = discord.Embed(description=description, title=title, color=BOT_COLOR)
    try:
        icon = bot.user.display_avatar.url if bot.user and bot.user.display_avatar else None
        embed.set_author(name=BOT_NAME, icon_url=icon)
    except:
        embed.set_author(name=BOT_NAME)
    if footer_text:
        embed.set_footer(text=footer_text)
    return embed

def parse_time(time_str):
    """Parse 10s, 5m, 2h, 1d"""
    if not time_str:
        return None, None
    match = re.match(r"^(\d+)(s|m|h|d)$", time_str.lower())
    if not match:
        return None, None
    amount = int(match.group(1))
    unit = match.group(2)
    seconds = {"s": amount, "m": amount*60, "h": amount*3600, "d": amount*86400}[unit]
    seconds = max(10, min(seconds, 2419200))  # 10s min, 28d max
    return seconds, datetime.timedelta(seconds=seconds)

# --- EVENTS ---
@bot.event
async def on_ready():
    print(f"✨ {BOT_NAME} v{BOT_VERSION} ONLINE as {bot.user} | {len(bot.guilds)} servers")
    await bot.change_presence(activity=discord.Game(name=f"{BOT_NAME} | !help"))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CommandOnCooldown):
        e = blood_embed(description=f"⏳ Cooldown! Try again in `{int(error.retry_after)}s`")
        try:
            await ctx.send(embed=e, delete_after=5)
        except:
            pass
        return
    if isinstance(error, commands.MissingPermissions):
        e = blood_embed(description=f"🔒 You need: `{', '.join(error.missing_permissions)}`")
        try:
            await ctx.send(embed=e, delete_after=7)
        except:
            pass
        return
    if isinstance(error, commands.BotMissingPermissions):
        e = blood_embed(description=f"🤖 I need: `{', '.join(error.missing_permissions)}`")
        try:
            await ctx.send(embed=e, delete_after=7)
        except:
            pass
        return
    if isinstance(error, commands.MemberNotFound):
        e = blood_embed(description="👤 User not found! Use `@user`")
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
    e = blood_embed(description=f"Hey {ctx.author.mention}! I'm **{BOT_NAME}** ✨")
    e.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=e)

@bot.command()
async def embed(ctx, *, text=None):
    if not text:
        return await ctx.send(embed=blood_embed(description="`!embed [text]` • Create embed"))
    try:
        await ctx.message.delete()
    except:
        pass
    e = blood_embed(description=text)
    e.set_footer(text=f"By {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=e)

@bot.command()
async def bloodmoon(ctx):
    e = blood_embed(description=f"Hi! I am **{BOT_NAME}** 🌙✨\nYour cute blood moon assistant!")
    e.set_footer(text=f"{BOT_NAME} v{BOT_VERSION}")
    await ctx.send(embed=e)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    e = discord.Embed(title=f"🖼️ {member.display_name}'s Avatar", color=BOT_COLOR)
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
    e = blood_embed(description=f"🏓 Pong! `{latency}ms`")
    await ctx.send(embed=e)

@bot.command()
async def say(ctx, *, message=None):
    if not message:
        return await ctx.send(embed=blood_embed(description="`!say [text]` • Say anonymously"))
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
        return await ctx.send(embed=blood_embed(description="🧹 Use `1-100` only!"), delete_after=5)
    try:
        deleted = await ctx.channel.purge(limit=number + 1)
        e = blood_embed(description=f"🧹 Cleared `{len(deleted)-1}` messages!", footer_text=f"By {ctx.author.display_name}")
        await ctx.send(embed=e, delete_after=3)
    except Exception as ex:
        await ctx.send(embed=blood_embed(description=f"❌ Failed: `{ex}`"), delete_after=5)

@bot.command()
@commands.has_permissions(manage_guild=True)
@commands.cooldown(1, 60, commands.BucketType.guild)
async def announce(ctx, *, text=None):
    if not text:
        return await ctx.send(embed=blood_embed(description="`!announce [text]` • Make announcement"))
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
        return await ctx.send(embed=blood_embed(description="`!mute @user [10m/1h/1d] [reason]`"), delete_after=7)
    if member.id == ctx.author.id:
        return await ctx.send(embed=blood_embed(description="❌ You can't mute yourself!"), delete_after=5)
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send(embed=blood_embed(description="❌ Higher/equal role! Can't mute."), delete_after=7)

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
        e = discord.Embed(title="🔇・MUTED", description="> A member has been muted", color=BOT_COLOR)
        try:
            e.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url if bot.user else None)
        except:
            e.set_author(name=BOT_NAME)
        e.add_field(name="👤 User", value=f"{member.mention}\n`{member.display_name}`", inline=False)
        e.add_field(name="⏰ Duration", value=f"`{time}`", inline=True)
        e.add_field(name="\u200b", value="\u200b", inline=True)
        e.add_field(name="📝 Reason", value=f"```{reason}```", inline=False)
        e.set_footer(text=f"🛡️ Muted by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=e)
    except discord.Forbidden:
        await ctx.send(embed=blood_embed(description="❌ No permission! My role must be higher!"), delete_after=7)
    except Exception as ex:
        await ctx.send(embed=blood_embed(description=f"❌ Failed: `{ex}`"), delete_after=7)

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def unmute_cmd(ctx, member: discord.Member = None, *, reason: str = "Unmuted"):
    if member is None:
        return await ctx.send(embed=blood_embed(description="`!unmute @user [reason]`"), delete_after=7)
    try:
        await member.timeout(None, reason=reason)
        try:
            await ctx.message.delete()
        except:
            pass
        e = discord.Embed(title="🔊・UNMUTED", description="> A member has been unmuted", color=BOT_COLOR)
        try:
            e.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url if bot.user else None)
        except:
            e.set_author(name=BOT_NAME)
        e.add_field(name="👤 User", value=f"{member.mention}\n`{member.display_name}`", inline=False)
        e.add_field(name="📝 Reason", value=f"```{reason}```", inline=False)
        e.set_footer(text=f"🛡️ Unmuted by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=e)
    except Exception as ex:
        await ctx.send(embed=blood_embed(description=f"❌ Failed: `{ex}`"), delete_after=7)

@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(
        title="✨ Ria • Command List",
        description=f"**Prefix:** `!` • **Version:** `v{BOT_VERSION}` • Cute & powerful!",
        color=BOT_COLOR
    )
    try:
        e.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url if bot.user else None)
    except:
        e.set_author(name=BOT_NAME)
    e.add_field(
        name="💖 General",
        value=(
            "`!hello` • Say hello\n"
            "`!ping` • Check latency\n"
            "`!embed [text]` • Create embed\n"
            "`!bloodmoon` • Ria message\n"
            "`!avatar [@user]` • Show avatar\n"
            "`!say [text]` • Say anonymously"
        ),
        inline=False
    )
    e.add_field(
        name="🛡️ Moderation",
        value=(
            "`!clear [number]` • Clear msgs\n"
            "`!announce [text]` • Announce\n"
            "`!mute @user [10m] [reason]` • Mute\n"
            "`!unmute @user [reason]` • Unmute"
        ),
        inline=False
    )
    e.add_field(
        name="ℹ️ Info",
        value="`!help` • This list",
        inline=False
    )
    e.set_footer(text=f"11 Commands • {BOT_NAME} v{BOT_VERSION} • Made with 💖")
    await ctx.send(embed=e)

# --- START ---
token = os.getenv("TOKEN") or os.getenv("BOT_TOKEN")
if not token:
    print("ERROR: No TOKEN or BOT_TOKEN found!")
else:
    bot.run(token)
                   
