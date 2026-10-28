
import discord
from discord.ext import commands
import os
from flask import Flask
import threading
import traceback

app = Flask(__name__)
@app.route('/')
def home():
    return "BLOODMOON IS ALIVE"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_flask, daemon=True).start()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

def blood_embed(description=None, title=None):
    embed = discord.Embed(description=description, title=title, color=0x2b2d31)
    try:
        icon = bot.user.display_avatar.url if bot.user and bot.user.display_avatar else None
        embed.set_author(name="BLOODMOON", icon_url=icon)
    except:
        embed.set_author(name="BLOODMOON")
    return embed

@bot.event
async def on_ready():
    print(f"BLOODMOON ONLINE: {bot.user}")

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
    await ctx.send(embed=blood_embed(description="Hello! Welcome to BLOODMOON."))

@bot.command()
async def embed(ctx, *, text=None):
    if not text:
        return await ctx.send(embed=blood_embed(description="Usage: !embed [text]"))
    await ctx.send(embed=blood_embed(description=text))

@bot.command()
async def bloodmoon(ctx):
    e = blood_embed(title="BLOODMOON", description="We rise under the blood moon.")
    e.set_image(url="https://i.imgur.com/8QmQ1rA.png")
    await ctx.send(embed=e)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    e = discord.Embed(title=f"{member.display_name} Avatar", color=0x2b2d31)
    try:
        e.set_author(name="BLOODMOON", icon_url=bot.user.display_avatar.url if bot.user else None)
    except:
        e.set_author(name="BLOODMOON")
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
    await ctx.send(embed=e, allowed_mentions=discord.AllowedMentions(everyone=False, users=True, roles=False))

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
    e = discord.Embed(title="ANNOUNCEMENT", description=text, color=0xff0000)
    try:
        e.set_author(name="BLOODMOON", icon_url=bot.user.display_avatar.url if bot.user else None)
    except:
        e.set_author(name="BLOODMOON")
    e.set_footer(text="BLOODMOON - Official Announcement")
    await ctx.send(content="@everyone", embed=e, allowed_mentions=discord.AllowedMentions(everyone=True))

@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="BLOODMOON Command Guide", description="Use the ! prefix. Responses are BLOODMOON embeds.", color=0x2b2d31)
    try:
        e.set_author(name="BLOODMOON", icon_url=bot.user.display_avatar.url if bot.user else None)
    except:
        e.set_author(name="BLOODMOON")
    e.add_field(name="General", value="!hello\n!embed [text]\n!bloodmoon\n!avatar [@user]", inline=False)
    e.add_field(name="Anonymous", value="!say [text]\n!say @member text", inline=False)
    e.add_field(name="Moderation", value="!clear [number]\n!announce [text]\n!help", inline=False)
    e.set_footer(text="BLOODMOON - Message commands anonymously")
    await ctx.send(embed=e)

bot.run(os.getenv("TOKEN"))
