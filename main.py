
import discord
from discord.ext import commands
import os
from flask import Flask
from threading import Thread

# --- 24/7 WEB SERVER FOR RENDER ---
app = Flask('')
@app.route('/')
def home():
    return "BLOODMOON is alive 24/7! 🌙"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🌙 BLOODMOON ONLINE as {bot.user}!")
    await bot.change_presence(activity=discord.Game(name="🌙 BLOODMOON | !help"))

@bot.command()
async def hello(ctx):
    embed = discord.Embed(title="Hello! 🌙", description=f"Hey {ctx.author.mention}!", color=0xFF0000)
    await ctx.send(embed=embed)

@bot.command()
async def embed(ctx, *, text="BLOODMOON 🌙"):
    try: await ctx.message.delete()
    except: pass
    embed = discord.Embed(title="🌙 BLOODMOON", description=text, color=0xFF0000)
    embed.set_footer(text=f"By {ctx.author}", icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def say(ctx, *, text):
    try: await ctx.message.delete()
    except: pass
    embed = discord.Embed(description=text, color=0xFF0000)
    embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def announce(ctx, channel: discord.TextChannel = None, *, text):
    try: await ctx.message.delete()
    except: pass
    target = channel or ctx.channel
    embed = discord.Embed(title="📢 ANNOUNCEMENT", description=text, color=0xFF0000)
    embed.set_footer(text="BLOODMOON 🌙")
    await target.send(embed=embed)
    await ctx.send(f"✅ Announced in {target.mention}", delete_after=5)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member}'s Avatar", color=0xFF0000)
    embed.set_image(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def clear(ctx, amount: int = 5):
    if ctx.author.guild_permissions.manage_messages:
        await ctx.channel.purge(limit=amount+1)
        await ctx.send(f"🧹 Cleared {amount}!", delete_after=3)

@bot.command()
async def help_blood(ctx):
    embed = discord.Embed(title="🌙 BLOODMOON COMMANDS", color=0xFF0000)
    embed.add_field(name="!hello", value="Say hello", inline=False)
    embed.add_field(name="!embed [text]", value="Embed + auto delete", inline=False)
    embed.add_field(name="!say [text]", value="Say as embed + auto delete", inline=False)
    embed.add_field(name="!announce #channel text", value="Announce anywhere + auto delete", inline=False)
    embed.add_field(name="!avatar", value="Show avatar", inline=False)
    embed.add_field(name="!clear", value="Clear messages", inline=False)
    embed.set_footer(text="BLOODMOON 24/7 🌙")
    await ctx.send(embed=embed)

keep_alive()
bot.run(os.environ.get("BOT_TOKEN"))
