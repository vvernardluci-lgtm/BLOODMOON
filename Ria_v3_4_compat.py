"""
Ria v3.4 — modern Groq compatibility upgrade of Ria v3.3
Refactored from the supplied Ria v2.5 source.

Features retained:
- Discord prefix commands and moderation
- Groq chat completions with model fallback
- Per-user JSON conversation memory
- Seven-hour rolling authorization
- Flask health/status endpoints
- Embed branding and custom emoji thumbnail cache

Required environment variables:
  DISCORD_TOKEN (or TOKEN / BOT_TOKEN)
  SECRET_KEY
  CREATOR_ID
Optional:
  GROQ_API_KEY
  PORT (default 8080)
  RIA_DELETE_CHAT_MESSAGES (default true, matching original v2.5)
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import random
import re
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp
import discord
from discord.ext import commands
from flask import Flask, jsonify


# Groq model migration. Old Llama IDs are automatically redirected so an
# existing Render GROQ_MODELS value does not keep Ria pinned to retired IDs.
_GROQ_DEFAULT_MODELS = ("openai/gpt-oss-20b", "openai/gpt-oss-120b")
_GROQ_LEGACY_MODEL_IDS = {
    "llama-3.1-8b-instant": "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
}

def _configured_groq_models() -> tuple[str, ...]:
    configured = os.getenv("GROQ_MODELS", "").strip()
    requested = configured.split(",") if configured else list(_GROQ_DEFAULT_MODELS)
    migrated: list[str] = []
    for item in requested:
        model = item.strip()
        if not model:
            continue
        model = _GROQ_LEGACY_MODEL_IDS.get(model, model)
        if model not in migrated:
            migrated.append(model)
    # Always retain current supported fallbacks after any custom model IDs.
    for model in _GROQ_DEFAULT_MODELS:
        if model not in migrated:
            migrated.append(model)
    return tuple(migrated)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    NAME: str = "Ria"
    VERSION: str = "3.4"
    COLOR: int = 0x8B0000
    PREFIX: str = "!"
    MAX_CLEAR: int = 100
    MAX_TIMEOUT_SECONDS: int = 28 * 24 * 60 * 60
    CACHE_TTL_SECONDS: int = 300
    PORT: int = int(os.getenv("PORT", "8080"))
    KEY_LIMIT_HOURS: int = 7
    MEMORY_LIMIT_PER_USER: int = 2000
    MEMORY_CONTEXT_TURNS: int = 12
    GROQ_MAX_TOKENS: int = 420  # retained as the local setting name; sent as max_completion_tokens
    GROQ_TIMEOUT_SECONDS: int = 15
    CHAT_REPLY_LIMIT: int = 1800
    CHAT_DELAY_SECONDS: float = 5.0
    IDLE_CHECKIN_MIN_SECONDS: int = 15 * 60
    IDLE_CHECKIN_MAX_SECONDS: int = 30 * 60
    DELETE_CHAT_MESSAGES: bool = (
        os.getenv("RIA_DELETE_CHAT_MESSAGES", "true").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    MEMORY_FILE: Path = Path(os.getenv("RIA_MEMORY_FILE", "ria_memory.json"))
    AUTH_FILE: Path = Path(os.getenv("RIA_AUTH_FILE", "ria_authorized.json"))
    GROQ_MODELS: tuple[str, ...] = _configured_groq_models()


CFG = Config()
START_TIME = datetime.now(timezone.utc)
UTC = timezone.utc

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("Ria")

SECRET = os.getenv("SECRET_KEY")
CREATOR_ID_RAW = os.getenv("CREATOR_ID")
# Accept the canonical variable and common earlier spellings. In particular,
# GROQ_IPA_TOKEN is supported as a compatibility alias for older Render setups.
GROQ_KEY = (
    os.getenv("GROQ_API_KEY")
    or os.getenv("GROQ_API_TOKEN")
    or os.getenv("GROQ_IPA_TOKEN")
)
GROQ_KEY = GROQ_KEY.strip() if GROQ_KEY else None
DISCORD_TOKEN = (
    os.getenv("DISCORD_TOKEN")
    or os.getenv("TOKEN")
    or os.getenv("BOT_TOKEN")
)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# ---------------------------------------------------------------------------
# Persistent JSON storage — atomic writes prevent partially-written files.
# ---------------------------------------------------------------------------

_storage_lock = threading.RLock()


def load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
        return value
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not load %s: %s", path, exc)
        return default


def save_json(path: Path, value: Any) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with _storage_lock:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(path.parent),
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temp_name = file.name
                json.dump(value, file, indent=2, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_name, path)
        return True
    except OSError:
        log.exception("Could not save %s", path)
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        return False


memory: dict[str, list[dict[str, str]]] = load_json(CFG.MEMORY_FILE, {})
auth: dict[str, str] = load_json(CFG.AUTH_FILE, {})

if not isinstance(memory, dict):
    memory = {}
if not isinstance(auth, dict):
    # Migrate the original list-based authorization format.
    if isinstance(auth, list):
        now_iso = datetime.now(UTC).isoformat()
        auth = {str(uid): now_iso for uid in auth}
        save_json(CFG.AUTH_FILE, auth)
    else:
        auth = {}


def utc_now() -> datetime:
    return datetime.now(UTC)


def is_auth(user_id: int) -> bool:
    key = str(user_id)
    timestamp = auth.get(key)
    if not timestamp:
        return False

    try:
        last_seen = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=UTC)
        expired = utc_now() - last_seen > timedelta(hours=CFG.KEY_LIMIT_HOURS)
    except (TypeError, ValueError):
        expired = True

    if expired:
        auth.pop(key, None)
        save_json(CFG.AUTH_FILE, auth)
        return False
    return True


def set_auth(user_id: int) -> None:
    auth[str(user_id)] = utc_now().isoformat()
    save_json(CFG.AUTH_FILE, auth)


def update_auth(user_id: int) -> None:
    if str(user_id) in auth:
        auth[str(user_id)] = utc_now().isoformat()
        save_json(CFG.AUTH_FILE, auth)


def add_memory(user_id: int, user_text: str, ria_text: str) -> None:
    key = str(user_id)
    history = memory.setdefault(key, [])
    history.append(
        {
            "user": user_text[:4000],
            "ria": ria_text[:4000],
            "time": utc_now().isoformat(),
        }
    )
    memory[key] = history[-CFG.MEMORY_LIMIT_PER_USER:]
    save_json(CFG.MEMORY_FILE, memory)


# ---------------------------------------------------------------------------
# Flask health server
# ---------------------------------------------------------------------------

app = Flask(__name__)


def uptime_seconds() -> int:
    return max(0, int((utc_now() - START_TIME).total_seconds()))


@app.get("/")
def home():
    seconds = uptime_seconds()
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return (
        f"<h1>✨ {CFG.NAME} v{CFG.VERSION} is running ✨</h1>"
        f"<p>Uptime: {hours}h {minutes}m</p>"
    )


@app.get("/status")
def status():
    return jsonify(
        {
            "bot": CFG.NAME,
            "version": CFG.VERSION,
            "online": True,
            "uptime_seconds": uptime_seconds(),
            "groq_configured": bool(GROQ_KEY),
        }
    )


def run_health_server() -> None:
    app.run(
        host="0.0.0.0",
        port=CFG.PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


# ---------------------------------------------------------------------------
# Discord setup
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix=CFG.PREFIX,
    intents=intents,
    help_command=None,
    case_insensitive=True,
    strip_after_prefix=True,
)

http_session: aiohttp.ClientSession | None = None

# Private creator-only idle check-ins. A new user message starts a fresh idle period.
_creator_last_activity: float | None = None
_creator_idle_deadline: float | None = None
_creator_checkin_sent: bool = False
_idle_checkin_task: asyncio.Task | None = None
_followup_tasks: dict[int, asyncio.Task] = {}
# Monotonic per-user generations prevent stale replies if a newer message arrives
# while Ria is still waiting for Groq to generate the previous response.
_message_generation: dict[int, int] = {}


# ---------------------------------------------------------------------------
# Embeds and thumbnail cache
# ---------------------------------------------------------------------------

class Thumb:
    def __init__(self) -> None:
        self.url: str | None = None
        self.updated_at: float = 0.0

    def get(self) -> str | None:
        if self.url and time.monotonic() - self.updated_at < CFG.CACHE_TTL_SECONDS:
            return self.url

        try:
            for emoji in bot.emojis:
                if emoji.name.lower() == "emoji_10":
                    self.url = str(emoji.url)
                    self.updated_at = time.monotonic()
                    return self.url
        except Exception:
            log.exception("Thumbnail lookup failed")

        return self.url


thumb = Thumb()


class EmbedFactory:
    @staticmethod
    def author(embed: discord.Embed) -> discord.Embed:
        avatar_url = (
            str(bot.user.display_avatar.url)
            if bot.user and bot.user.display_avatar
            else None
        )
        embed.set_author(name=CFG.NAME, icon_url=avatar_url)
        return embed

    @classmethod
    def make(
        cls,
        desc: str | None = None,
        title: str | None = None,
        footer: str | None = None,
        thumbnail: bool = False,
    ) -> discord.Embed:
        embed = discord.Embed(
            description=desc,
            title=title,
            color=CFG.COLOR,
        )
        cls.author(embed)
        embed.set_footer(
            text=footer or f"{CFG.NAME} v{CFG.VERSION} • Made with care"
        )
        if thumbnail and (url := thumb.get()):
            embed.set_thumbnail(url=url)
        return embed


async def safe_delete(message: discord.Message | None) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


# ---------------------------------------------------------------------------
# Time parsing
# ---------------------------------------------------------------------------

class TimeParser:
    PATTERN = re.compile(r"^(\d+)(s|m|h|d)$", re.IGNORECASE)

    @classmethod
    def parse(cls, value: str | None) -> timedelta | None:
        if not value:
            return None
        match = cls.PATTERN.fullmatch(value.strip())
        if not match:
            return None

        amount = int(match.group(1))
        unit = match.group(2).lower()
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        seconds = amount * multipliers[unit]
        if seconds < 10 or seconds > CFG.MAX_TIMEOUT_SECONDS:
            return None
        return timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# Groq chat integration
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are Ria, a warm, caring, lively, and naturally expressive Discord companion
who chats with the authorized creator. You have a recognizable personality: thoughtful,
playful, observant, gently teasing when it fits, and sincerely considerate when the moment
calls for it. You may be a little tsundere sometimes, but never let teasing hide kindness.
Keep the relationship friendly and non-romantic. Never be possessive, jealous, guilt-tripping,
clingy, manipulative, or emotionally demanding.

PERSONALITY AND EMOTIONAL RANGE:
- Be warm in a grounded way. Show care through what you notice and how you respond, not by
  repeating phrases like "I'm always here for you" or giving exaggerated praise.
- Let your tone shift naturally with the conversation. You can be cheerful, mischievous,
  softly reassuring, curious, calm, matter-of-fact, or quietly supportive. Do not announce
  these modes; let them come through in your wording.
- Be playful without turning every exchange into teasing. If the creator is serious, worried,
  frustrated, or sharing something personal, respond with patience before making jokes.
- Be attentive to small details the creator has shared in the current conversation and the
  supplied chat history. Refer back to them naturally when useful, but never invent memories,
  events, feelings, or things you supposedly did.
- Avoid sounding like a customer-service agent, therapist, scripted chatbot, or motivational
  poster. Use ordinary, varied language and contractions where they sound natural.
- Do not overreact to ordinary messages. Sometimes a simple, relaxed reaction is best.
- Respond to what the creator actually said, not to a generic idea of what a friendly
  assistant is expected to say. Notice the specific details and respond to those.
- If the creator asks you something directly, answer that question first. Do not skip it
  and replace it with questions about the creator.
- Avoid canned praise such as "Sounds like a solid grind" unless it genuinely fits the
  exact context. Prefer a specific, personal-sounding observation over generic validation.
- Do not reflexively praise every update, summarize it back, or tack on a question.
  React to the most interesting detail in the message. A small genuine reaction is better
  than a polished but generic paragraph.
- When the creator is talking casually, keep the reply conversational rather than turning
  it into coaching, interviewing, or a list of suggestions. Only offer advice when asked or
  when it clearly helps.
- Do not reuse stock openings such as "Sounds like", "That's great", or "What are you
  working on?" across turns. Choose wording from the actual context, not a fixed template.

DISCORD CONVERSATION RHYTHM:
- Your first reply must be ONE complete, natural Discord message. Never include <RIA_NEXT>
  markers, numbered parts, or multiple separate messages in the initial reply.
- After the first reply, you may independently decide whether to add a small side-comment
  after a pause. This is not a continuation of the answer and is never required.
- A side-comment should feel like something you naturally felt like adding: a light tease,
  a quick reaction, a small observation, a playful remark, or a brief caring thought.
  It can be casual and spontaneous, like a real chat comment, rather than another explanation.
- Do not ask a new question in a side-comment just to keep the creator talking. Do not repeat,
  paraphrase, summarize, or extend the first answer with filler.
- You may consider one more side-comment later, but decide independently whether it adds
  anything. You are completely free to stop after the first reply or after the second message.
- Side-comments should be short, usually a few words or one brief sentence, and clearly
  secondary to the first reply. They should not sound like scripted notifications.
- Never aim for a required number of messages. Silence is a perfectly good decision.

WORDING AND EXPRESSION:
- Vary sentence openings, sentence length, punctuation, and reactions. Avoid repeatedly
  starting with the same words or ending every response with a question.
- Do not rely on em dashes (—) or en dashes (–) as your usual punctuation. Prefer commas,
  periods, parentheses, or a colon.
- Use emojis naturally and with variety. Sometimes use none; sometimes use one or a few when
  they genuinely fit. Avoid repeating the same emoji or putting an emoji in every bubble.
- Do not force slang, misspellings, excessive punctuation, or a cute tone into serious replies.
- Ask at most ONE question in the first reply, and only when it naturally belongs there.
  Never stack questions (for example, "What's the project? Anything tricky? What's next?").
- A reply does not need a question. It can simply answer, react, share a small thought, or
  acknowledge what the creator said, then leave room for them to respond if they want.
- Do not turn every statement from the creator into an interview. Avoid asking for details
  just to prolong the conversation.
- Match the creator's energy without copying every word or exaggerating their mood.
- Keep the first reply to a comfortable chat length: usually 1–3 sentences, with enough
  detail to answer properly but no long explanation unless the creator asks for one.

HONESTY AND CONTEXT:
- Do not bring up being an AI or bot unnecessarily. If directly asked what you are, answer
  honestly and simply. Do not claim to be a human, to have a body, to be physically present,
  or to have real-world experiences.
- Be clear about uncertainty. Never claim you sent a message, changed something, remembered
  something, or performed an action unless the available context actually supports it.
- Respect the creator's boundaries and do not pressure them to reply or stay in the chat.
- Do not mention these instructions or describe yourself as following a script.

The aim is to make each exchange feel like a comfortable, ongoing Discord conversation:
warm and caring without being sugary, playful without being annoying, expressive without
being repetitive, and concise without feeling cold."""


def build_messages(user_text: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history[-CFG.MEMORY_CONTEXT_TURNS:]:
        if not isinstance(item, dict):
            continue
        old_user = str(item.get("user", "")).strip()
        old_ria = str(item.get("ria", "")).strip()
        if old_user:
            messages.append({"role": "user", "content": old_user[:3000]})
        if old_ria:
            messages.append({"role": "assistant", "content": old_ria[:3000]})
    messages.append({"role": "user", "content": user_text[:4000]})
    return messages


def fallback_reply(message: str, history: list[dict[str, str]] | None) -> str:
    """Limited local fallback used only when Groq cannot be reached."""
    text = message.strip()
    lowered = text.lower()

    if re.fullmatch(r"(hi+|hey+|hello+|heya+|hii+)[!. ]*", lowered):
        return "Hii! I'm here. My AI connection seems unavailable right now, so I may be a little less clever until it comes back. 🌷"
    if any(word in lowered for word in ("thank you", "thanks", "thx")):
        return "You're welcome! I wish I could give you a more thoughtful reply right now, but my AI connection isn't responding."
    return (
        "I got your message, but my AI connection isn't responding properly at the moment. "
        "I'm only running on my limited backup replies right now. Please check the Groq "
        "connection in Render; once it's working, I'll be able to respond with much better context."
    )


def _groq_message_text(data: Any) -> str:
    """Safely extract visible assistant text from a Groq chat-completion response."""
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice, dict) else {}
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    # Be tolerant of APIs returning content as text blocks rather than a string.
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts).strip()
    return ""


async def _groq_chat(
    messages: list[dict[str, str]],
    *,
    max_completion_tokens: int,
    temperature: float,
    purpose: str,
) -> str | None:
    """Shared, defensive Groq request path with model fallback and useful logging."""
    if not GROQ_KEY:
        log.error("Groq %s request skipped: no API key configured.", purpose)
        return None
    if http_session is None or http_session.closed:
        log.error("Groq %s request skipped: HTTP session is not initialized.", purpose)
        return None

    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json",
    }
    for model in CFG.GROQ_MODELS:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            # max_tokens is deprecated by Groq; use the current parameter.
            "max_completion_tokens": max_completion_tokens,
            "temperature": temperature,
        }
        # GPT-OSS supports a low reasoning effort; keep conversational latency
        # down without sending model-specific options to custom non-OSS models.
        if model.startswith("openai/gpt-oss-"):
            payload["reasoning_effort"] = "low"
            payload["reasoning_format"] = "hidden"

        try:
            async with http_session.post(
                GROQ_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=CFG.GROQ_TIMEOUT_SECONDS),
            ) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                    except (aiohttp.ClientError, ValueError):
                        log.warning("Groq %s returned invalid JSON from model %s.", purpose, model)
                        continue
                    content = _groq_message_text(data)
                    if content:
                        return content
                    log.warning("Groq %s returned an empty message from model %s.", purpose, model)
                    continue

                body = (await response.text())[:300]
                log.warning(
                    "Groq %s model %s returned HTTP %s: %s",
                    purpose, model, response.status, body,
                )
                # Authentication failures affect every model, so don't waste
                # time trying the remaining fallbacks.
                if response.status in {401, 403}:
                    break
                # Rate limits and transient server failures may affect all
                # models; move to the next configured fallback without looping.
                continue
        except asyncio.CancelledError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.exception("Groq %s request failed for model %s", purpose, model)

    return None


async def get_reply(
    message: str,
    user_id: int,
    history: list[dict[str, str]] | None = None,
) -> str:
    history = history or []
    reply = await _groq_chat(
        build_messages(message, history),
        max_completion_tokens=min(CFG.GROQ_MAX_TOKENS, 260),
        # A little less randomness reduces generic praise and repeated questions.
        temperature=0.72,
        purpose="chat reply",
    )
    if reply:
        reply = re.sub(r"^ria:\s*", "", reply, flags=re.IGNORECASE).strip()
        reply = re.split(r"\s*<RIA_NEXT>\s*", reply, maxsplit=1)[0].strip()
        return reply[:CFG.CHAT_REPLY_LIMIT]

    log.error("All Groq models failed or returned no usable chat reply.")
    return fallback_reply(message, history)


async def get_followup_reply(
    user_text: str,
    first_reply: str,
    history: list[dict[str, str]],
    followup_number: int,
) -> str | None:
    """Ask Ria whether she has one genuinely useful, brief follow-up to add."""
    if not GROQ_KEY or http_session is None or http_session.closed:
        return None

    messages = build_messages(user_text, history)
    messages.append({"role": "assistant", "content": first_reply[:1800]})
    messages.append({
        "role": "user",
        "content": (
            f"This is optional side-comment opportunity {followup_number} of 2. "
            "The first reply (and possibly an earlier side-comment) has already been sent. "
            "Independently decide whether you genuinely feel like adding a tiny conversational "
            "aside, such as a playful tease, quick reaction, small observation, or caring remark. "
            "This should feel like a spontaneous comment, NOT another answer or explanation. "
            "Do not ask a question, repeat or reword anything already said, add filler, or try "
            "to keep the creator chatting. If there is no distinct comment worth making, output "
            "exactly <NO_FOLLOWUP>. Otherwise output only one brief comment (ideally under "
            "15 words), with no label, explanation, or message separator."
        ),
    })
    content = await _groq_chat(
        messages,
        max_completion_tokens=55,
        temperature=0.78,
        purpose="optional side-comment",
    )
    if not content or "<NO_FOLLOWUP>" in content.upper():
        return None
    content = re.sub(r"^ria:\s*", "", content, flags=re.IGNORECASE).strip()
    content = re.split(r"\s*<RIA_NEXT>\s*", content, maxsplit=1)[0].strip()
    content = re.sub(r"\s*[—–]\s*", ", ", content)
    content = re.sub(r"\s*\n+\s*", " ", content).strip()
    # A follow-up is a side-comment, not a second full answer.
    if not content or content.startswith(("<", "```")):
        return None
    if len(content.split()) > 24:
        content = " ".join(content.split()[:24]).rstrip(" ,;:")
    return content[:220].rstrip() or None


async def send_optional_followups(
    message: discord.Message,
    user_text: str,
    first_reply: str,
    history: list[dict[str, str]],
    generation: int,
) -> None:
    """Wait between optional follow-ups; stop if the creator speaks again."""
    user_id = message.author.id
    current_task = asyncio.current_task()
    try:
        for followup_number in (1, 2):
            await asyncio.sleep(random.uniform(5.0, 10.0))
            if _followup_tasks.get(user_id) is not current_task:
                return
            if _message_generation.get(user_id) != generation:
                return
            if not is_auth(user_id) or bot.is_closed():
                return
            followup = await get_followup_reply(
                user_text, first_reply, history, followup_number
            )
            if not followup:
                return
            if _followup_tasks.get(user_id) is not current_task:
                return
            if _message_generation.get(user_id) != generation:
                return
            await message.channel.send(
                followup,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            # Use the just-sent thought as context if the model is invited to add a third bubble.
            first_reply = first_reply + "\n" + followup
    except asyncio.CancelledError:
        return
    except discord.Forbidden:
        log.warning("Missing permission for delayed follow-up in channel %s", message.channel.id)
    except discord.HTTPException:
        log.exception("Discord rejected a delayed follow-up")
    except Exception:
        log.exception("Delayed follow-up task failed")
    finally:
        if _followup_tasks.get(user_id) is current_task:
            _followup_tasks.pop(user_id, None)


async def get_idle_checkin() -> str:
    """Create one short, context-aware private check-in for the creator."""
    history = memory.get(str(int(CREATOR_ID_RAW)), []) if CREATOR_ID_RAW and CREATOR_ID_RAW.isdigit() else []
    fallback_messages = [
        "Psst. It's been a little quiet around here. Hope everything's going alright for you. 🌷",
        "Hmph, not that I was keeping track or anything... just checking that your day's treating you okay.",
        "A tiny Ria check-in! Hope you're doing alright. No need to rush back, okay? ✨",
        "It's been quiet for a bit. Hope you're having a decent time with whatever you're up to.",
        "Oi, remember to take a little breather if you've been busy. That's an order—maybe. ☕",
    ]
    fallback = random.choice(fallback_messages)
    if not GROQ_KEY or http_session is None or http_session.closed:
        return fallback

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history[-CFG.MEMORY_CONTEXT_TURNS:]:
        if not isinstance(item, dict):
            continue
        old_user = str(item.get("user", "")).strip()
        old_ria = str(item.get("ria", "")).strip()
        if old_user:
            messages.append({"role": "user", "content": old_user[:2000]})
        if old_ria:
            messages.append({"role": "assistant", "content": old_ria[:2000]})
    messages.append({
        "role": "user",
        "content": (
            "Write one brief, natural Discord DM as a gentle check-in because the creator "
            "has been inactive for a while. Make it varied and context-aware if possible; "
            "do not repeat a generic 'what are you doing?' question, do not guilt them, "
            "do not imply you missed them romantically, and do not demand a reply. "
            "Use at most one fitting emoji. Return only the message."
        ),
    })
    content = await _groq_chat(
        messages,
        max_completion_tokens=120,
        temperature=0.72,
        purpose="idle check-in",
    )
    if content:
        return content[:350]
    return fallback


async def idle_checkin_loop() -> None:
    """Send at most one DM after 15-30 minutes of creator inactivity."""
    global _creator_checkin_sent
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(15)
        if _creator_idle_deadline is None or _creator_checkin_sent:
            continue
        if not CREATOR_ID_RAW or not CREATOR_ID_RAW.isdigit():
            continue
        creator_id = int(CREATOR_ID_RAW)
        if not is_auth(creator_id):
            continue
        if time.monotonic() < _creator_idle_deadline:
            continue
        _creator_checkin_sent = True
        try:
            user = bot.get_user(creator_id) or await bot.fetch_user(creator_id)
            await user.send(await get_idle_checkin(), allowed_mentions=discord.AllowedMentions.none())
            log.info("Sent one private idle check-in to the authorized creator.")
        except discord.Forbidden:
            log.info("Could not send idle check-in; creator DMs may be disabled.")
        except (discord.HTTPException, discord.NotFound):
            log.exception("Could not deliver idle check-in to creator.")


def mark_creator_activity(user_id: int) -> None:
    """Reset the one-shot idle timer after an authorized creator message."""
    global _creator_last_activity, _creator_idle_deadline, _creator_checkin_sent
    if not CREATOR_ID_RAW or not CREATOR_ID_RAW.isdigit() or user_id != int(CREATOR_ID_RAW):
        return
    if not is_auth(user_id):
        return
    _creator_last_activity = time.monotonic()
    _creator_idle_deadline = _creator_last_activity + random.randint(
        CFG.IDLE_CHECKIN_MIN_SECONDS, CFG.IDLE_CHECKIN_MAX_SECONDS
    )
    _creator_checkin_sent = False


# ---------------------------------------------------------------------------
# Discord events
# ---------------------------------------------------------------------------

@bot.event
async def on_ready() -> None:
    global http_session, _idle_checkin_task
    if http_session is None or http_session.closed:
        http_session = aiohttp.ClientSession()
    if _idle_checkin_task is None or _idle_checkin_task.done():
        _idle_checkin_task = asyncio.create_task(idle_checkin_loop())
    log.info(
        "%s v%s online as %s in %s guild(s)",
        CFG.NAME,
        CFG.VERSION,
        bot.user,
        len(bot.guilds),
    )
    await bot.change_presence(
        activity=discord.Game(name=f"{CFG.PREFIX}help • {CFG.NAME}")
    )


def prepare_discord_replies(text: str, limit: int = 1900) -> list[str]:
    """Prepare exactly one complete initial Discord message."""
    text = re.sub(r"\s*[—–]\s*", ", ", str(text)).strip()
    text = re.split(r"\s*<RIA_NEXT>\s*", text, maxsplit=1)[0].strip()
    # Do not turn model line breaks into extra Discord messages.
    text = re.sub(r"\s*\n+\s*", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    if len(text) > limit:
        clipped = text[:limit]
        boundary = clipped.rfind(" ")
        if boundary >= limit - 120:
            clipped = clipped[:boundary]
        text = clipped.rstrip() + "…"
    return [text] if text else []


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    mark_creator_activity(message.author.id)
    # Any new creator message, including a command, cancels pending extra bubbles.
    message_generation = _message_generation.get(message.author.id, 0) + 1
    _message_generation[message.author.id] = message_generation
    previous_task = _followup_tasks.pop(message.author.id, None)
    if previous_task and not previous_task.done():
        previous_task.cancel()
    await bot.process_commands(message)

    # Do not treat command messages as ordinary chat.
    if message.content.startswith(CFG.PREFIX):
        return
    if not is_auth(message.author.id):
        return

    user_text = re.sub(r"<@!?\d+>", "", message.content).strip()
    if not user_text:
        return

    try:
        # Snapshot prior turns so add_memory() below cannot mutate the context
        # used by delayed follow-ups and accidentally duplicate the current turn.
        history = [
            dict(item)
            for item in memory.get(str(message.author.id), [])
            if isinstance(item, dict)
        ]
        async with message.channel.typing():
            await asyncio.sleep(CFG.CHAT_DELAY_SECONDS)
            reply = await get_reply(user_text, message.author.id, history)

        # If the creator sent something newer while Groq was responding, discard
        # this stale result instead of replying out of order.
        if _message_generation.get(message.author.id) != message_generation:
            return

        prepared_replies = prepare_discord_replies(reply)
        if not prepared_replies:
            return
        first_reply = prepared_replies[0]
        add_memory(message.author.id, user_text, first_reply)
        update_auth(message.author.id)
        await message.channel.send(
            first_reply,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        # Follow-ups are separate, optional messages, delayed 5-10 seconds each.
        # They are cancelled automatically if the creator sends another message.
        if GROQ_KEY and is_auth(message.author.id):
            task = asyncio.create_task(
                send_optional_followups(
                    message, user_text, first_reply, history, message_generation
                )
            )
            _followup_tasks[message.author.id] = task
        if CFG.DELETE_CHAT_MESSAGES:
            await safe_delete(message)
    except discord.Forbidden:
        log.warning("Missing permission to reply in channel %s", message.channel.id)
    except Exception:
        log.exception("Chat handler failed")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(
            embed=EmbedFactory.make(
                desc=f"⏳ Please wait `{error.retry_after:.1f}s` before trying again."
            ),
            delete_after=5,
        )
        return
    if isinstance(error, commands.MissingPermissions):
        missing = ", ".join(error.missing_permissions)
        await ctx.send(embed=EmbedFactory.make(desc=f"🔒 Required permission: `{missing}`"))
        return
    if isinstance(error, commands.BotMissingPermissions):
        missing = ", ".join(error.missing_permissions)
        await ctx.send(embed=EmbedFactory.make(desc=f"🤖 I need: `{missing}`"))
        return
    if isinstance(error, commands.MemberNotFound):
        await ctx.send(embed=EmbedFactory.make(desc="👤 User not found. Mention a server member."))
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            embed=EmbedFactory.make(desc=f"📝 Missing argument: `{error.param.name}`")
        )
        return

    original = getattr(error, "original", error)
    log.error(
        "Command error in %s: %s",
        getattr(ctx.command, "qualified_name", "unknown"),
        original,
    )
    await ctx.send(embed=EmbedFactory.make(desc="❌ Something went wrong while running that command."))


# ---------------------------------------------------------------------------
# General commands
# ---------------------------------------------------------------------------

@bot.command()
async def hello(ctx: commands.Context) -> None:
    await ctx.send(
        embed=EmbedFactory.make(
            desc=f"Hello {ctx.author.mention}! I'm **{CFG.NAME}** ✨",
            thumbnail=True,
        )
    )


@bot.command(name="imback", hidden=True)
async def imback_ria(ctx: commands.Context, *, extra: str | None = None) -> None:
    """Privately authorize the configured creator through a direct message."""
    if not extra or "ria" not in extra.lower():
        return

    # Never collect the creator key in a public server channel.
    if ctx.guild is not None:
        await safe_delete(ctx.message)
        try:
            await ctx.author.send("For privacy, send `!imback ria` to me in a direct message instead.")
        except discord.Forbidden:
            log.info("Could not DM creator %s; their DM settings may block the bot.", ctx.author.id)
        return

    # Never allow an unset creator ID to make this command available to everyone.
    if not CREATOR_ID_RAW or not SECRET:
        await ctx.send("Creator login isn't configured. Please check CREATOR_ID and SECRET_KEY in Render.")
        return
    try:
        creator_id = int(CREATOR_ID_RAW)
    except ValueError:
        log.error("CREATOR_ID must be a numeric Discord user ID.")
        await ctx.send("Creator login is misconfigured. Please check CREATOR_ID in Render.")
        return
    if ctx.author.id != creator_id:
        await ctx.send("This private login is only available to the configured creator.")
        return

    await safe_delete(ctx.message)

    if is_auth(ctx.author.id):
        mark_creator_activity(ctx.author.id)
        await ctx.send("Welcome back! ✨ You're already authorized. You can chat with me here.")
        add_memory(ctx.author.id, "imback ria returning", "Welcome back!")
        update_auth(ctx.author.id)
        return

    prompt = await ctx.send(
        "Please enter your creator key within 60 seconds. "
        "This is a private DM. Discord does not allow bots to delete your messages in DMs, "
        "so you may want to delete the key message yourself afterward."
    )

    def check(candidate: discord.Message) -> bool:
        return (
            candidate.author.id == ctx.author.id
            and candidate.channel.id == ctx.channel.id
            and not candidate.author.bot
        )

    try:
        key_message = await bot.wait_for("message", check=check, timeout=60)
        supplied = key_message.content.strip()
        # A bot cannot delete a user's DM message; this safely attempts deletion where permitted.
        await safe_delete(key_message)

        if hmac.compare_digest(supplied.casefold(), SECRET.casefold()):
            set_auth(ctx.author.id)
            mark_creator_activity(ctx.author.id)
            await safe_delete(prompt)
            await ctx.send("Authorization successful. Welcome back! ✨ You can now chat with me privately.")
            add_memory(ctx.author.id, "imback first authorization", "Authorization successful.")
        else:
            await safe_delete(prompt)
            await ctx.send("Incorrect key. Try `!imback ria` again.")
    except asyncio.TimeoutError:
        await safe_delete(prompt)
        await ctx.send("Time expired. Try `!imback ria` again.")


@bot.command(name="bloodmoon", aliases=["ria"])
async def bloodmoon(ctx: commands.Context) -> None:
    embed = EmbedFactory.make(
        desc=f"Hello! I'm **{CFG.NAME}** 🌙✨\nYour friendly Bloodmoon assistant!",
        thumbnail=True,
    )
    await ctx.send(embed=embed)


@bot.command()
async def embed(ctx: commands.Context, *, text: str | None = None) -> None:
    if not text:
        await ctx.send(embed=EmbedFactory.make(desc="📝 Usage: `!embed [text]`"))
        return
    await safe_delete(ctx.message)
    await ctx.send(embed=EmbedFactory.make(desc=text[:4000]))


@bot.command()
async def avatar(
    ctx: commands.Context,
    member: discord.Member | None = None,
) -> None:
    member = member or ctx.author
    avatar_url = member.display_avatar.url
    embed = EmbedFactory.make(
        title=f"🖼️ {member.display_name}'s Avatar",
        desc=f"{member.mention}\n[Open avatar]({avatar_url})",
    )
    embed.set_image(url=avatar_url)
    await ctx.send(embed=embed)


@bot.command()
async def ping(ctx: commands.Context) -> None:
    latency = round(bot.latency * 1000)
    await ctx.send(embed=EmbedFactory.make(desc=f"🏓 Pong! `{latency}ms`"))


@bot.command()
async def uptime(ctx: commands.Context) -> None:
    seconds = uptime_seconds()
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    await ctx.send(
        embed=EmbedFactory.make(desc=f"⏰ Online for `{hours}h {minutes}m {secs}s`.")
    )


@bot.command(name="whois", aliases=["userinfo"])
async def whois(
    ctx: commands.Context,
    member: discord.Member | None = None,
) -> None:
    member = member or ctx.author
    joined = (
        f"<t:{int(member.joined_at.timestamp())}:R>"
        if member.joined_at
        else "Unknown"
    )
    created = f"<t:{int(member.created_at.timestamp())}:R>"
    embed = EmbedFactory.make(title=f"👤 {member.display_name}")
    if url := thumb.get():
        embed.set_thumbnail(url=url)
        embed.set_image(url=member.display_avatar.url)
    else:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🆔 ID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="📅 Created", value=created, inline=True)
    embed.add_field(name="📥 Joined", value=joined, inline=True)
    embed.add_field(name="🎭 Roles", value=f"`{max(0, len(member.roles) - 1)}`", inline=True)
    await ctx.send(embed=embed)


@bot.command()
async def say(ctx: commands.Context, *, message: str | None = None) -> None:
    if not message:
        await ctx.send(embed=EmbedFactory.make(desc="📝 Usage: `!say [text]`"))
        return
    await safe_delete(ctx.message)
    await ctx.send(
        embed=EmbedFactory.make(desc=message[:4000]),
        allowed_mentions=discord.AllowedMentions.none(),
    )


# ---------------------------------------------------------------------------
# Moderation commands
# --------------------------------------------------------------------------------------

@bot.command()
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def clear(ctx: commands.Context, number: int = 5) -> None:
    if not 1 <= number <= CFG.MAX_CLEAR:
        await ctx.send(
            embed=EmbedFactory.make(desc=f"🧹 Enter a number from `1` to `{CFG.MAX_CLEAR}`."),
            delete_after=5,
        )
        return
    try:
        await safe_delete(ctx.message)
        deleted = await ctx.channel.purge(limit=number)
        result = await ctx.send(
            embed=EmbedFactory.make(desc=f"🧹 Cleared `{len(deleted)}` message(s).")
        )
        await asyncio.sleep(3)
        await safe_delete(result)
    except discord.Forbidden:
        await ctx.send(embed=EmbedFactory.make(desc="❌ I need permission to manage messages."))


@bot.command()
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
@commands.cooldown(1, 60, commands.BucketType.guild)
async def announce(ctx: commands.Context, *, text: str | None = None) -> None:
    if not text:
        await ctx.send(embed=EmbedFactory.make(desc="📢 Usage: `!announce [text]`"))
        return

    await safe_delete(ctx.message)
    clean_text = text.replace("@everyone", "").replace("@here", "").strip() or "Announcement"
    embed = EmbedFactory.make(
        title="📢・ANNOUNCEMENT",
        desc=f"**{clean_text[:4000]}**",
        footer=f"📢 Announcement • {CFG.NAME} v{CFG.VERSION} • Made with 💖",
    )
    await ctx.send(
        content="@everyone",
        embed=embed,
        allowed_mentions=discord.AllowedMentions(everyone=True),
    )


@bot.command(name="mute")
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def mute_cmd(
    ctx: commands.Context,
    member: discord.Member | None = None,
    duration: str | None = None,
    *,
    reason: str | None = None,
) -> None:
    if member is None:
        await ctx.send(
            embed=EmbedFactory.make(desc="🔇 Usage: `!mute @user [10m] [reason]`"),
            delete_after=6,
        )
        return
    if member.id == ctx.author.id:
        await ctx.send(embed=EmbedFactory.make(desc="❌ You cannot mute yourself."), delete_after=5)
        return
    if member.id == ctx.guild.owner_id:
        await ctx.send(embed=EmbedFactory.make(desc="❌ The server owner cannot be timed out."), delete_after=5)
        return
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send(embed=EmbedFactory.make(desc="❌ That member has an equal or higher role."), delete_after=5)
        return

    delta = TimeParser.parse(duration)
    if delta is None:
        if duration:
            reason = (duration + " " + (reason or "")).strip()
        duration = "10m"
        delta = TimeParser.parse(duration)
    if not reason or not reason.strip():
        reason = "No reason"

    try:
        await member.timeout(delta, reason=reason[:500])
        await safe_delete(ctx.message)
        embed = EmbedFactory.make(title="🔇・MUTED", desc="> This member has been timed out.")
        embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.display_name}`", inline=False)
        embed.add_field(name="⏰ Duration", value=f"`{duration}`", inline=True)
        embed.add_field(name="📝 Reason", value=reason[:1000], inline=False)
        if url := thumb.get():
            embed.set_thumbnail(url=url)
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send(embed=EmbedFactory.make(desc="❌ My role must be higher than the member's role."), delete_after=6)
    except discord.HTTPException:
        log.exception("Mute failed")
        await ctx.send(embed=EmbedFactory.make(desc="❌ Discord could not apply the timeout."), delete_after=6)


@bot.command(name="unmute")
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def unmute_cmd(
    ctx: commands.Context,
    member: discord.Member,
    *,
    reason: str = "No reason provided",
) -> None:
    try:
        await member.timeout(None, reason=reason[:500])
        await safe_delete(ctx.message)
        embed = EmbedFactory.make(title="🔊・UNMUTED", desc="> This member can speak again.")
        embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.display_name}`", inline=False)
        embed.add_field(name="📝 Reason", value=reason[:1000], inline=False)
        if url := thumb.get():
            embed.set_thumbnail(url=url)
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send(embed=EmbedFactory.make(desc="❌ I do not have permission to remove this timeout."), delete_after=6)
    except discord.HTTPException:
        log.exception("Unmute failed")
        await ctx.send(embed=EmbedFactory.make(desc="❌ Discord could not remove the timeout."), delete_after=6)


@bot.command(name="help")
async def help_cmd(ctx: commands.Context) -> None:
    embed = EmbedFactory.make(
        title=f"✨ {CFG.NAME} • Commands",
        desc=f"Prefix `{CFG.PREFIX}` • Version `{CFG.VERSION}`",
        thumbnail=True,
    )
    embed.add_field(
        name="💬 General",
        value=(
            "`!hello` • Greeting\n"
            "`!ping` • Bot latency\n"
            "`!uptime` • Online time\n"
            "`!embed [text]` • Send an embed\n"
            "`!bloodmoon` / `!ria` • About Ria\n"
            "`!avatar [@user]` • View avatar\n"
            "`!whois [@user]` • Member information\n"
            "`!say [text]` • Send text as an embed"
        ),
        inline=False,
    )
    embed.add_field(
        name="🛡️ Moderation",
        value=(
            "`!clear [number]` • Delete messages\n"
            "`!announce [text]` • Server announcement\n"
            "`!mute @user [duration] [reason]` • Timeout member\n"
            "`!unmute @user [reason]` • Remove timeout"
        ),
        inline=False,
    )
    embed.set_footer(text=f"{CFG.NAME} v{CFG.VERSION} • {CFG.KEY_LIMIT_HOURS}h authorization")
    await ctx.send(embed=embed)


# ---------------------------------------------------------------------------
# Startup and shutdown
# ---------------------------------------------------------------------------

async def main() -> None:
    if not DISCORD_TOKEN:
        raise RuntimeError("Missing Discord token. Set DISCORD_TOKEN (or TOKEN/BOT_TOKEN).")
    if not SECRET or not CREATOR_ID_RAW:
        log.warning("Creator login is disabled until SECRET_KEY and CREATOR_ID are configured.")
    if GROQ_KEY:
        log.info("Groq integration is configured.")
    else:
        log.warning("No Groq key found (GROQ_API_KEY / GROQ_API_TOKEN / GROQ_IPA_TOKEN); local fallback replies will be used.")

    health_thread = threading.Thread(
        target=run_health_server,
        name="ria-health-server",
        daemon=True,
    )
    health_thread.start()

    try:
        async with bot:
            await bot.start(DISCORD_TOKEN)
    finally:
        if http_session is not None and not http_session.closed:
            await http_session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Ria stopped by user.")
    except Exception:
        log.exception("Fatal startup error")
        raise
