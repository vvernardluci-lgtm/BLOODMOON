"""
================================================================================
Ria v2.5 - BLOODMOON with Groq Brain + 7 Hour Key Limit
Anonymous, Blood Red, 13 Commands + Hidden !imback ria, 24/7
Fixed: No mention needed, less emoji, natural typing, no keep mentioning
New: 7 Hour Limit on key - auto clear conversation after 7h no reply
================================================================================
Bot: Ria v2.5
Author: Vernard Luci (Lucky 15)
Features:
- 13 Commands (8 General, 4 Moderation, 1 Information) + Hidden !imback ria
- Anonymous Embeds (Ria only on top, Made with 💖, no name leak)
- Blood Red Color (0x8B0000)
- Thumbnail: Emoji_10 + First Guild Sticker
- Announce: Bold medium font (**text**), no sticker, pings @everyone
- 24/7 Online: Flask + UptimeRobot
- Supports Both TOKEN and BOT_TOKEN
- Hidden !imback ria: Only creator, secret key YourCreatorIsBack, Welcome back, My Creator!!
- No mention needed, less emoji, natural typing, no keep mentioning
- 2000+ Memory: Saves forever
- Groq Brain: Real brain like Meta AI, not random codes, only for responses
- 7 Hour Limit: If no reply for 7 hours, auto clear auth, back to first message
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
import json
import random
import asyncio
from typing import Optional
from dataclasses import dataclass

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
    KEY_LIMIT_HOURS: int = 7

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

# --- SECTION 3: 24/7 FLASK ---
app = Flask(__name__)

@app.route('/')
def home():
    delta = datetime.datetime.now(datetime.timezone.utc) - START_TIME
    h, r = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(r, 60)
    return f'<html><body style="background:#0a0000;color:#ffaaaa;font-family:Arial;text-align:center;padding:60px"><h1>✨ {CFG.NAME} v{CFG.VERSION} IS ALIVE ✨</h1><p>Uptime: {h}h {m}m | 13 Commands + Hidden !imback ria | 7H Limit | Made with 💖</p></body></html>'

@app.route('/status')
def status():
    delta = datetime.datetime.now(datetime.timezone.utc) - START_TIME
    return jsonify({"bot": CFG.NAME, "version": CFG.VERSION, "online": True, "uptime": int(delta.total_seconds())})

def run_flask():
    app.run(host='0.0.0.0', port=CFG.PORT)

threading.Thread(target=run_flask, daemon=True).start()
log.info(f"Flask started on port {CFG.PORT}")

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

# --- SECTION 5: THUMBNAIL MANAGER ---
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

# --- GROQ BRAIN + SECRET KEY + 2000+ MEMORY + 7 HOUR LIMIT ---
RIA_SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("RIA_SECRET_KEY") or "YourCreatorIsBack"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MEMORY_FILE = "ria_memory.json"
AUTHORIZED_FILE = "ria_authorized.json"

def load_json_file(filepath, default):
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return default

def save_json_file(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as ex:
        log.error(f"Save {filepath} error: {ex}")

ria_memory = load_json_file(MEMORY_FILE, {})
# New: authorized with timestamp for 7 hour limit
authorized_data = load_json_file(AUTHORIZED_FILE, {})  # {user_id_str: last_active_iso}
# Convert old list format to new dict format if needed
if isinstance(authorized_data, list):
    new_dict = {}
    for uid in authorized_data:
        new_dict[str(uid)] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    authorized_data = new_dict
    save_json_file(AUTHORIZED_FILE, authorized_data)

authorized_users = authorized_data

log.info(f"Loaded {len(ria_memory)} users memory, {len(authorized_users)} authorized with 7h limit")

def is_authorized(user_id: int) -> bool:
    """Check if authorized and within 7 hour limit"""
    uid = str(user_id)
    if uid not in authorized_users:
        return False
    try:
        last_active_str = authorized_users[uid]
        last_active = datetime.datetime.fromisoformat(last_active_str.replace('Z', '+00:00'))
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        elapsed = (now - last_active).total_seconds()
        limit_seconds = CFG.KEY_LIMIT_HOURS * 3600
        if elapsed > limit_seconds:
            # Expired - auto clear conversation auth, back to first message
            log.info(f"User {user_id} expired after {CFG.KEY_LIMIT_HOURS}h, clearing auth")
            del authorized_users[uid]
            save_json_file(AUTHORIZED_FILE, authorized_users)
            return False
        return True
    except Exception as ex:
        log.error(f"Auth check error for {user_id}: {ex}")
        return False

def authorize_user(user_id: int):
    uid = str(user_id)
    authorized_users[uid] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save_json_file(AUTHORIZED_FILE, authorized_users)
    log.info(f"User {user_id} authorized with 7h limit")

def update_last_active(user_id: int):
    """Update last active time for 7h limit"""
    uid = str(user_id)
    if uid in authorized_users:
        authorized_users[uid] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_json_file(AUTHORIZED_FILE, authorized_users)

def add_memory(user_id, user_msg, ria_reply):
    uid = str(user_id)
    if uid not in ria_memory:
        ria_memory[uid] = []
    ria_memory[uid].append({
        "user": user_msg,
        "ria": ria_reply,
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })
    if len(ria_memory[uid]) > 2000:
        ria_memory[uid] = ria_memory[uid][-2000:]
    save_json_file(MEMORY_FILE, ria_memory)

def get_cute_reply(user_message: str, username: str, user_id, history=None) -> str:
    """
    Brain with Groq AI - real brain, not random codes
    Fixed: No mentioning, less emoji, normal person
    """
    # Groq brain
    if GROQ_API_KEY:
        try:
            import requests
            memory_context = ""
            if history and len(history) > 0:
                recent = history[-10:]
                for m in recent:
                    memory_context += f"User: {m.get('user','')}\nRia: {m.get('ria','')}\n"
            
            system_prompt = f"""You are Ria, a friendly Discord assistant, talking like a real person.
- Talk like a normal person would be, short, natural, casual, not like bot codes!
- Don't sound like AI, don't sound like codes, talk like human texting
- Less emoji, max 1 emoji, or no emoji, natural
- Don't keep mentioning user's name, don't repeat same phrases
- You have 2000+ memory, you remember Creator forever
- Keep replies short (1-2 sentences), casual, like Discord DM
- No embed, just normal chat, human-like, not "Ria is..." style
- Don't be romantic girlfriend, just friendly, natural
Memory:
{memory_context}"""
            
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "max_tokens": 150,
                    "temperature": 0.8
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                reply = data['choices'][0]['message']['content'].strip()
                if len(reply) > 300:
                    reply = reply[:300]
                return reply
            else:
                log.error(f"Groq error {response.status_code}: {response.text[:200]}")
        except Exception as ex:
            log.error(f"Groq brain error: {ex}")
    
    # Fixed: Not sounding like codes - talk like normal person, human-like, not fallback codes
    msg_lower = user_message.lower()
    # Human-like responses, not like bot codes
    if any(w in msg_lower for w in ["hello", "hi", "hey", "helo"]):
        replies = [
            f"hehe hi! how are you today?",
            f"helloo! whats up?",
            f"hi! happy to see you",
            f"heyy, im here!",
            f"oh hi! how's your day going?"
        ]
        return random.choice(replies)
    if "how are you" in msg_lower or "how r u" in msg_lower:
        replies = [
            f"im good! thanks for asking, how about you?",
            f"im doing okay, just chilling, you?",
            f"pretty good! thanks for checking",
            f"im alright, how are you doing?"
        ]
        return random.choice(replies)
    if "thank" in msg_lower:
        replies = [
            f"you're welcome! happy to help",
            f"no problem at all!",
            f"anytime!",
            f"of course!"
        ]
        return random.choice(replies)
    if "cute" in msg_lower or "adorable" in msg_lower:
        return f"aww stop, you're making me shy"
    if "love you" in msg_lower or "love u" in msg_lower:
        return f"aww that's sweet of you, thank you"
    if "miss you" in msg_lower:
        return f"i missed you too, where were you?"
    if "sad" in msg_lower or "tired" in msg_lower:
        replies = [
            f"aww, are you okay? im here if you need to talk",
            f"that sucks, hope you feel better soon",
            f"im here for you, don't worry",
            f"take it easy okay? you got this"
        ]
        return random.choice(replies)
    if "happy" in msg_lower:
        return f"yayy that's good to hear, tell me more about it"
    # For normal chat - not sounding like codes, more human natural
    if "really" in msg_lower:
        replies = [
            f"yeah really!",
            f"mhm, for real",
            f"yes really, why?",
            f"of course, what do you mean?"
        ]
        return random.choice(replies)
    if "weird" in msg_lower or "hmm" in msg_lower:
        replies = [
            f"hmm yeah it is kinda weird",
            f"right? i thought so too",
            f"lol yeah, what do you think about it?",
            f"ikr, weird right?"
        ]
        return random.choice(replies)
    if "sentence" in msg_lower or "meant" in msg_lower:
        replies = [
            f"oh sorry, what do you mean?",
            f"ah my bad, what did you mean then?",
            f"oops sorry, tell me again?",
            f"ohh i see, sorry about that"
        ]
        return random.choice(replies)
    # Generic natural responses - not like codes
    natural_replies = [
        f"ohh i see, yeah that makes sense",
        f"hmm interesting, tell me more",
        f"lol really? what happened then?",
        f"oh yeah? how so?",
        f"wait fr? that's cool",
        f"ah i get it, then what?",
        f"ohh okay, i understand",
        f"mhm, and then?",
        f"oh wow, that's actually interesting",
        f"yeah? what do you think about it?",
        f"lol yeah i know right",
        f"ohh yeah, i was thinking about that too",
    ]
    return random.choice(natural_replies)

thumb = ThumbnailManager(ttl=CFG.CACHE_TTL)

# --- SECTION 6: EMBED FACTORY ---
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

# --- SECTION 7: HELPERS ---
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

# --- SECTION 8: EVENTS ---
# NEW: Cute AI chat only for authorized via hidden !imback ria - no mention needed, normal person, 7h limit
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    try:
        await bot.process_commands(message)
    except:
        pass
    if message.content.startswith(CFG.PREFIX):
        return
    user_id = message.author.id
    if not is_authorized(user_id):
        return
    # Fixed: No mention needed - talk like normal person would be
    user_message = message.content
    user_message = re.sub(r'<@!?\d+>', '', user_message).strip()
    if not user_message:
        return
    try:
        history = ria_memory.get(str(user_id), [])
        reply = get_cute_reply(user_message, message.author.display_name, user_id, history)
        # Fixed: Response 5 second - like normal person thinking, not instant codes
        typing_delay = 5.0
        async with message.channel.typing():
            await asyncio.sleep(typing_delay)
            add_memory(user_id, user_message, reply)
            update_last_active(user_id)
        await message.channel.send(reply)
        # New: Delete mine too - auto delete user's message along with hidden command and key
        await safe_delete(message)
    except Exception as ex:
        log.error(f"AI chat error: {ex}")

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
    e = EmbedFactory.create(description=f"Hello {ctx.author.mention}! I am **{CFG.NAME}** ✨\nNice to see you!", thumb_url=False)
    await ctx.send(embed=e)

@bot.command(name="imback")
async def imback_ria(ctx, *, extra=None):
    """
    Hidden chat with Ria - !imback ria - only creator, not in help list
    Secret key YourCreatorIsBack, 7 hour limit, Welcome back, My Creator!!
    """
    # Must be !imback ria - hidden code, only you know!
    if extra is None or "ria" not in extra.lower():
        return
    await safe_delete(ctx.message)
    user_id = ctx.author.id
    creator_id_env = os.getenv("CREATOR_ID")
    if creator_id_env:
        try:
            if int(creator_id_env) != user_id:
                return
        except:
            pass
    if is_authorized(user_id):
        try:
            await ctx.send(f"Welcome back, My Creator!! 💓")
            async with ctx.channel.typing():
                await asyncio.sleep(1)
            cute = get_cute_reply("hello", ctx.author.display_name, user_id)
            await ctx.send(cute)
            add_memory(user_id, "imback ria (returning creator)", "Welcome back, My Creator!! 💓")
            update_last_active(user_id)
        except Exception as ex:
            log.error(f"imback welcome back error: {ex}")
        return
    try:
        prompt_msg = await ctx.send(
            f"{ctx.author.mention} My Creator, please enter the secret key to continue... "
            f"Type the secret key in this channel within 60 seconds! (Auto-deleted for security!)"
        )
        def check(m):
            return m.author.id == user_id and m.channel.id == ctx.channel.id
        try:
            key_msg = await bot.wait_for('message', check=check, timeout=60.0)
            content = key_msg.content
            is_correct = RIA_SECRET_KEY in content or RIA_SECRET_KEY.lower() in content.lower()
            try:
                await safe_delete(key_msg)
            except:
                pass
            if is_correct:
                authorize_user(user_id)
                try:
                    await safe_delete(prompt_msg)
                except:
                    pass
                await ctx.send(f"Welcome back, My Creator!! 💓")
                add_memory(user_id, "imback ria (first auth with secret key)", "Welcome back, My Creator!! 💓")
                async with ctx.channel.typing():
                    await asyncio.sleep(1.2)
                await ctx.send(
                    f"Ehehe~ Ria missed you so much! "
                    f"Ria will remember you forever! 2000+ memory! "
                    f"Now you can chat with me anytime! Just talk like normal person!"
                )
            else:
                try:
                    await safe_delete(prompt_msg)
                except:
                    pass
                await ctx.send(
                    f"Oops wrong key {ctx.author.mention}! Ehehe~ Try !imback ria again with correct key!",
                    delete_after=10
                )
        except asyncio.TimeoutError:
            try:
                await safe_delete(prompt_msg)
            except:
                pass
            await ctx.send(
                f"{ctx.author.mention} Time's up! Secret key scan timed out! Try !imback ria again!",
                delete_after=10
            )
    except Exception as ex:
        log.error(f"imback hidden error: {ex}")
        try:
            await ctx.send(f"Oops error {ctx.author.mention}! Try !imback ria again!", delete_after=10)
        except:
            pass

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

# --- SECTION 10: MODERATION COMMANDS (4) ---
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
    clean = text.replace("@everyone", "").replace("@here", "").strip() or "Announcement"
    e = discord.Embed(title="📢・ANNOUNCEMENT", description=f"**{clean}**", color=CFG.COLOR)
    EmbedFactory.set_author(e)
    e.set_footer(text=f"📢 Announcement • {CFG.NAME} v{CFG.VERSION} • Made with 💖")
    await ctx.send(content="@everyone", embed=e, allowed_mentions=discord.AllowedMentions(everyone=True))

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
    e.set_footer(text=f"13 Commands • {CFG.NAME} v{CFG.VERSION} • Made with 💖 • 7H Limit")
    await ctx.send(embed=e)

# --- START ---
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
