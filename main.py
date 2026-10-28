
import discord
from discord.ext import commands
import os
from flask import Flask
import threading
import traceback

BOT_NAME = "Ria"

app = Flask(__name__)
@app.route('/')
def home():
    return f"{BOT_NAME} IS ALIVE - 24/7 ONLINE!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_flask, daemon=True).start()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

def blood_embed(description=None, title=None):
    embed = discord.Embed(description=description, title=title, color=0x8B0000)
    try:
        icon = bot.user.display_avatar.url if bot.user and bot.user.display_avatar else None
        embed.set_author(name=BOT_NAME, icon_url=icon)
    except:
        embed.set_author(name=BOT_NAME)
    return embed

@bot.event
async def on_ready():
    print(f"{BOT_NAME} ONLINE: {bot.user}")
    await bot.change_presence(activity=discord.Game(name=f"{BOT_NAME} | !help"))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CommandOnCooldown):
        e = blood_embed(description=f"Cooldown! Try again in {int(error.retry_after)}s")
        try:
            await ctx.send(embed=e, delete_after=5)
        except:
            pass
        return
    if isinstance(error, commands.MissingPermissions):
        e = blood_embed(description=f"You need permission: {', '.join(error.missing_permissions)}")
        try:
            await ctx.send(embed=e, delete_after=7)
        except:
            pass
        return
    if isinstance(error, commands.BotMissingPermissions):
        e = blood_embed(description=f"I need permission: {', '.join(error.missing_permissions)}")
        try:
            await ctx.send(embed=e, delete_after=7)
        except:
            pass
        return
    print(f"ERROR: {error}")
    traceback.print_exception(type(error), error, error.__traceback__)

@bot.command()
async def hello(ctx):
    await ctx.send(embed=blood_embed(description="Hello!"))

@bot.command()
async def embed(ctx, *, text=None):
    if not text:
        return await ctx.send(embed=blood_embed(description="Usage: !embed [text]"))
    await ctx.send(embed=blood_embed(description=text))

@bot.command()
async def bloodmoon(ctx):
    e = blood_embed(description="Hi! I am Ria!")
    await ctx.send(embed=e)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    e = discord.Embed(title=f"{member.display_name} Avatar", color=0x8B0000)
    try:
        e.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url if bot.user else None)
    except:
        e.set_author(name=BOT_NAME)
    e.set_image(url=member.display_avatar.url)
    await ctx.send(embed=e)

@bot.command()
async def say(ctx, *, message=None):
    if not message:
        return await ctx.send(embed=blood_embed(description="Usage: !say [text]"))
    try:
        await ctx.message.delete()
    except:
        pass
    e = blood_embed(description=message)
    await ctx.send(embed=e)

@bot.command()
@commands.has_permissions(manage_messages=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def clear(ctx, number: int = 5):
    if number < 1 or number > 100:
        return await ctx.send(embed=blood_embed(description="Clear 1-100 only!"), delete_after=5)
    try:
        deleted = await ctx.channel.purge(limit=number + 1)
        e = blood_embed(description=f"Cleared {len(deleted)-1} messages!")
        await ctx.send(embed=e, delete_after=3)
    except Exception as ex:
        await ctx.send(embed=blood_embed(description=f"Failed: {ex}"), delete_after=5)

@bot.command()
@commands.has_permissions(manage_guild=True)
@commands.cooldown(1, 60, commands.BucketType.guild)
async def announce(ctx, *, text=None):
    if not text:
        return await ctx.send(embed=blood_embed(description="Usage: !announce [text]"))
    try:
        await ctx.message.delete()
    except:
        pass

    ping_everyone = False
    clean_text = text
    if "@everyone" in text or "@here" in text:
        ping_everyone = True
        clean_text = text.replace("@everyone", "").replace("@here", "").strip()
        if not clean_text:
            clean_text = "Announcement"

    e = discord.Embed(title="ANNOUNCEMENT", description=clean_text, color=0x8B0000)
    try:
        e.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url if bot.user else None)
    except:
        e.set_author(name=BOT_NAME)

    if ping_everyone:
        await ctx.send(content="@everyone", embed=e, allowed_mentions=discord.AllowedMentions(everyone=True))
    else:
        await ctx.send(embed=e)

@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(
        title="Ria • Command List",
        description="**Prefix:** `!` • Here are all my commands:",
        color=0x8B0000
    )
    try:
        e.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url if bot.user else None)
    except:
        e.set_author(name=BOT_NAME)
    e.add_field(
        name="General Commands",
        value=(
            "`!hello` • Say hello\n"
            "`!embed [text]` • Create embed\n"
            "`!bloodmoon` • Show Ria message\n"
            "`!avatar [@user]` • Show avatar\n"
            "`!say [text]` • Say anonymously"
        ),
        inline=False
    )
    e.add_field(
        name="Moderation",
        value=(
            "`!clear [number]` • Clear messages\n"
            "`!announce [text]` • Make announcement"
        ),
        inline=False
    )
    e.add_field(
        name="Information",
        value="`!help` • Show this list",
        inline=False
    )
    e.set_footer(text="7 Commands • Ria")
    await ctx.send(embed=e)

token = os.getenv("TOKEN") or os.getenv("BOT_TOKEN")
if not token:
    print("ERROR: No TOKEN or BOT_TOKEN found!")
else:
    bot.run(token)
    
