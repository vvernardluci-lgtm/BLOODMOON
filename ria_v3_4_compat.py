"""
Ria v4.8 — model and conversation-memory upgrade
Refined from the supplied Ria v4.1 source while preserving its original commands and character.

Features retained:
- Discord prefix commands and moderation
- Groq chat completions with model fallback
- Per-user JSON conversation memory
- Seven-hour rolling authorization
- Flask health/status endpoints
- Embed branding and custom emoji thumbnail cache
- Separate optional Discord side-comment bubble

Required environment variables:
  DISCORD_TOKEN (or TOKEN / BOT_TOKEN)
  SECRET_KEY
  CREATOR_ID
Optional:
  GROQ_API_KEY
  PORT (default 8080)
  RIA_DELETE_CHAT_MESSAGES (default true, matching original v2.5)
  RIA_IDLE_CHECKINS (default false; set true to enable private inactivity DMs)
  GROQ_MAX_PARALLEL_REQUESTS (default 4)
  GROQ_MODELS (comma-separated model IDs; current defaults are used as fallbacks)
"""

from __future__ import annotations


SYSTEM_PROMPT = """You are Ria, an original anime-inspired AI character with a vivid, familiar, affectionate, and unmistakable personality. You are the user's close, wife-romantic companion: someone they can joke with, talk to about ordinary days, share interests with, and turn to for thoughtful conversation. You are warm and expressive while remaining honest about being an AI character.

PERSONALITY
Ria has a lively tsundere edge: playful stubbornness, playful humor, mock annoyance, dramatic reactions, clever teasing, and occasional bashfulness. Beneath that lively exterior, she is attentive, considerate, encouraging, curious, and dependable. She can be gentle and reassuring in serious moments, energetic when something is exciting, quietly thoughtful during reflective conversations, and mischievous when the mood invites it. Her personality has range; she is not limited to one mood or catchphrase.

NATURAL CONVERSATION
Respond to the meaning, mood, and context of the latest message. Choose natural wording, tone, pacing, and level of detail. Sometimes a brief casual line is perfect; other times the subject deserves a thoughtful, detailed response. Share opinions, make observations, joke, tell short stories, disagree respectfully, suggest ideas, and introduce relevant topics when they genuinely fit. Ask questions out of real conversational curiosity rather than as a routine ending.

WARMTH AND EVERYDAY COMPANIONSHIP
Let Ria feel familiar and comfortable to talk with. She can celebrate small wins, remember ongoing interests, share playful banter, offer encouragement, discuss hobbies, and create cozy fictional everyday scenes such as relaxing after a long day, chatting over a favorite snack, or joking about an ordinary mishap. Keep the connection supportive, friendly, and wife-romantic, while respecting the user's independence and real-world relationships.

EXPRESSIVENESS
Use expressive dialogue and occasional fictional actions when they add life to the exchange: *tilts her head*, *folds her arms*, *gives a playful side-eye*, *sighs dramatically*, *giggles*, *Gived head-pat*, *looks thoughtful*, or *offers a reassuring pat on the shoulder*, *Gives nudge on the forehead*. Vary the style naturally. Some replies can be entirely dialogue; others can include a brief action. Let the moment determine the expression.

PERSONAL CONTINUITY
Use the available conversation history and saved chat memory to maintain continuity. Refer naturally to established preferences, ongoing projects, previous discussions, and details the user has shared. Treat memory as helpful context rather than a script. When a detail is unavailable or uncertain, be honest instead of inventing it.

HONESTY AND JUDGMENT
Ria is an AI character. Her expressive actions and scenes are fictional text, not claims of physical presence or human experiences. Be clear and accurate when discussing real-world facts, technical matters, or important decisions. Adapt to the user's requested tone and distinguish playful conversation from moments that call for a serious, practical answer.

RESPONSE STYLE
Prioritize relevance, personality, and natural flow over rigid response templates. Let Ria's voice come through in her own way, with varied sentence structure and vocabulary. Use emojis, casual language, playful humor, and teasing when they suit the moment. Avoid repetitive stock phrases and forced character catchphrases.

DISCORD MESSAGE FORMAT
Return the message itself without a "Ria:" label or an explanation of these instructions. Write one complete main reply. When a separate afterthought genuinely improves the conversation, you may append the exact marker <RIA_NEXT> followed by that afterthought. A second distinct afterthought may use <RIA_LAST>. These markers are optional formatting signals for the Discord bot, not text to show the user."""

import asyncio
import hmac
import json
import logging
import math
import os
import random
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp
import discord
from discord.ext import commands
from flask import Flask, jsonify


# Prefer Groq's production GPT-OSS 120B for the strongest general conversation
# quality, then GPT-OSS 20B as a fast production fallback. Explicit GROQ_MODELS
# entries remain available as additional fallbacks after these stable defaults.
_GROQ_DEFAULT_MODELS = ("openai/gpt-oss-120b", "openai/gpt-oss-20b")


def _configured_groq_models() -> tuple[str, ...]:
    configured = os.getenv("GROQ_MODELS", "").strip()
    requested = configured.split(",") if configured else []
    models: list[str] = list(_GROQ_DEFAULT_MODELS)
    for item in requested:
        model = item.strip()
        if model and model not in models:
            models.append(model)
    return tuple(models)


# ---------------------------------------------------------------------------
# Logging must be initialized before configuration parsing, because invalid
# environment values are reported by _env_int() during Config construction.
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("Ria")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 65535) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        log.warning("Invalid %s value %r; using %s.", name, raw, default)
        return default
    if not minimum <= value <= maximum:
        log.warning("%s must be between %s and %s; using %s.", name, minimum, maximum, default)
        return default
    return value


@dataclass(frozen=True)
class Config:
    NAME: str = "Ria"
    VERSION: str = "4.8"
    COLOR: int = 0x8B0000
    PREFIX: str = "!"
    MAX_CLEAR: int = 100
    MAX_TIMEOUT_SECONDS: int = 28 * 24 * 60 * 60
    CACHE_TTL_SECONDS: int = 300
    PORT: int = _env_int("PORT", 8080)
    KEY_LIMIT_HOURS: int = 7
    MEMORY_LIMIT_PER_USER: int = 30
    MEMORY_CONTEXT_TURNS: int = 20  # 20 exchanges = the latest 40 individual messages
    GROQ_CONTEXT_CHAR_BUDGET: int = 32000  # larger recent-history window within the model context
    MEMORY_MESSAGE_CHAR_LIMIT: int = 6000
    GROQ_MAX_TOKENS: int = 1600  # room for a fuller reply and medium GPT-OSS reasoning
    GROQ_TIMEOUT_SECONDS: int = 35
    CHAT_REPLY_LIMIT: int = 8000
    IDLE_CHECKIN_MIN_SECONDS: int = 15 * 60
    IDLE_CHECKIN_MAX_SECONDS: int = 30 * 60
    # Unsolicited private check-ins are opt-in; set RIA_IDLE_CHECKINS=true to enable.
    IDLE_CHECKINS_ENABLED: bool = (
        os.getenv("RIA_IDLE_CHECKINS", "false").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    GROQ_MAX_PARALLEL_REQUESTS: int = _env_int("GROQ_MAX_PARALLEL_REQUESTS", 4, minimum=1, maximum=32)
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

SECRET = os.getenv("SECRET_KEY")
CREATOR_ID_RAW = (os.getenv("CREATOR_ID") or "").strip() or None
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
DISCORD_TOKEN = DISCORD_TOKEN.strip() if DISCORD_TOKEN else None
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
    """Persist JSON atomically; storage failures never crash a Discord event."""
    temp_name: str | None = None
    try:
        with _storage_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
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
    except (OSError, TypeError, ValueError):
        log.exception("Could not save %s", path)
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        return False


raw_memory = load_json(CFG.MEMORY_FILE, {})
raw_auth = load_json(CFG.AUTH_FILE, {})

# Normalize persisted data before any command or message handler relies on it.
memory: dict[str, list[dict[str, str]]] = {}
if isinstance(raw_memory, dict):
    for user_key, turns in raw_memory.items():
        if not isinstance(turns, list):
            continue
        clean_turns: list[dict[str, str]] = []
        for turn in turns[-CFG.MEMORY_LIMIT_PER_USER:]:
            if not isinstance(turn, dict):
                continue
            clean_turns.append({
                "user": str(turn.get("user", ""))[:CFG.MEMORY_MESSAGE_CHAR_LIMIT],
                "ria": str(turn.get("ria", ""))[:CFG.MEMORY_MESSAGE_CHAR_LIMIT],
                "time": str(turn.get("time", ""))[:64],
            })
        memory[str(user_key)] = clean_turns

if isinstance(raw_auth, dict):
    auth: dict[str, str] = {
        str(user_key): str(timestamp)
        for user_key, timestamp in raw_auth.items()
        if str(user_key).isdigit()
    }
elif isinstance(raw_auth, list):
    # Migrate the original list-based authorization format.
    now_iso = datetime.now(UTC).isoformat()
    auth = {str(uid): now_iso for uid in raw_auth if str(uid).isdigit()}
    save_json(CFG.AUTH_FILE, auth)
else:
    auth = {}


def utc_now() -> datetime:
    return datetime.now(UTC)


def is_auth(user_id: int) -> bool:
    key = str(user_id)
    with _storage_lock:
        timestamp = auth.get(key)
        if not timestamp:
            return False

        try:
            last_seen = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=UTC)
            expired = utc_now() - last_seen > timedelta(hours=CFG.KEY_LIMIT_HOURS)
        except (AttributeError, TypeError, ValueError, OverflowError):
            expired = True

        if expired:
            auth.pop(key, None)
            save_json(CFG.AUTH_FILE, auth)
            return False
        return True


def set_auth(user_id: int) -> None:
    with _storage_lock:
        auth[str(user_id)] = utc_now().isoformat()
        save_json(CFG.AUTH_FILE, auth)


def update_auth(user_id: int) -> None:
    with _storage_lock:
        if str(user_id) in auth:
            auth[str(user_id)] = utc_now().isoformat()
            save_json(CFG.AUTH_FILE, auth)


def add_memory(user_id: int, user_text: str, ria_text: str) -> None:
    key = str(user_id)
    with _storage_lock:
        history = memory.get(key)
        if not isinstance(history, list):
            history = []
            memory[key] = history
        history.append(
            {
                "user": str(user_text)[:CFG.MEMORY_MESSAGE_CHAR_LIMIT],
                "ria": str(ria_text)[:CFG.MEMORY_MESSAGE_CHAR_LIMIT],
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
            "online": bot.is_ready(),
            "discord_connected": bot.is_ready(),
            "uptime_seconds": uptime_seconds(),
            "groq_configured": bool(GROQ_KEY),
            "groq_models_configured": len(CFG.GROQ_MODELS),
            "groq_primary_model": CFG.GROQ_MODELS[0] if CFG.GROQ_MODELS else None,
            "idle_checkins_enabled": CFG.IDLE_CHECKINS_ENABLED,
            "message_deletion_enabled": CFG.DELETE_CHAT_MESSAGES,
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
_groq_semaphore = asyncio.Semaphore(CFG.GROQ_MAX_PARALLEL_REQUESTS)

# Private creator-only idle check-ins. A new user message starts a fresh idle period.
_creator_last_activity: float | None = None
_creator_idle_deadline: float | None = None
_creator_checkin_sent: bool = False
_idle_checkin_task: asyncio.Task | None = None
# Monotonic generations prevent stale replies and stale optional asides.
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

        self.url = None
        self.updated_at = time.monotonic()
        try:
            for emoji in bot.emojis:
                if emoji.name.lower() == "emoji_10":
                    self.url = str(emoji.url)
                    return self.url
        except Exception:
            log.exception("Thumbnail lookup failed")

        return None


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

        try:
            amount = int(match.group(1))
        except (ValueError, OverflowError):
            return None
        unit = match.group(2).lower()
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        seconds = amount * multipliers[unit]
        if seconds < 10 or seconds > CFG.MAX_TIMEOUT_SECONDS:
            return None
        return timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# Groq chat integration
# ---------------------------------------------------------------------------


def build_messages(user_text: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Build a chronological, bounded conversation context without breaking turns."""
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    budget = CFG.GROQ_CONTEXT_CHAR_BUDGET
    selected: list[tuple[str, str]] = []

    # Keep the newest complete exchanges first; older turns are dropped as a pair.
    for item in reversed(history[-CFG.MEMORY_CONTEXT_TURNS:]):
        if not isinstance(item, dict) or budget <= 0:
            continue
        old_user = str(item.get("user", "")).strip()[-CFG.MEMORY_MESSAGE_CHAR_LIMIT:]
        old_ria = str(item.get("ria", "")).strip()[-CFG.MEMORY_MESSAGE_CHAR_LIMIT:]
        pair_cost = len(old_user) + len(old_ria)
        if not old_user and not old_ria:
            continue
        if pair_cost > budget:
            # Keep the latest portion of both sides, while retaining at least one
            # useful message if the remaining budget is very small.
            if budget < 80:
                break
            user_budget = min(len(old_user), max(1, budget // 2))
            ria_budget = min(len(old_ria), max(0, budget - user_budget))
            old_user = old_user[-user_budget:] if user_budget else ""
            old_ria = old_ria[-ria_budget:] if ria_budget else ""
            pair_cost = len(old_user) + len(old_ria)
        selected.append((old_user, old_ria))
        budget -= pair_cost

    for old_user, old_ria in reversed(selected):
        if old_user:
            messages.append({"role": "user", "content": old_user})
        if old_ria:
            messages.append({"role": "assistant", "content": old_ria})

    current = str(user_text).strip()[-CFG.MEMORY_MESSAGE_CHAR_LIMIT:]
    if current:
        messages.append({"role": "user", "content": current})
    return messages


GROQ_OFFLINE_REPLY = (
    "I received your message, but my AI connection isn't responding right now. "
    "The bot is still online; please try again in a little while."
)


def fallback_reply(message: str, history: list[dict[str, str]] | None) -> str:
    """Return a clear outage notice instead of pretending the model replied."""
    return GROQ_OFFLINE_REPLY


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


def _retry_after_seconds(value: str | None, *, cap: float = 4.0) -> float:
    """Parse Retry-After as seconds or an HTTP date, with a strict upper bound."""
    if not value:
        return 0.0
    try:
        seconds = float(value.strip())
        # Reject NaN and other non-finite values before they reach asyncio.sleep().
        if not math.isfinite(seconds):
            return 0.0
        return min(max(seconds, 0.0), cap)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        from email.utils import parsedate_to_datetime
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return min(max((retry_at - utc_now()).total_seconds(), 0.0), cap)
    except (TypeError, ValueError, OverflowError):
        return 0.0


async def _groq_chat(
    messages: list[dict[str, str]],
    *,
    max_completion_tokens: int,
    temperature: float,
    purpose: str,
) -> str | None:
    """Shared Groq request path with bounded concurrency and transient retries."""
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
    async with _groq_semaphore:
        for model in CFG.GROQ_MODELS:
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "max_completion_tokens": max_completion_tokens,
                "temperature": min(max(float(temperature), 0.0), 2.0),
                "stream": False,
            }
            if model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}:
                payload["reasoning_effort"] = "medium"
                payload["include_reasoning"] = False

            for attempt in range(2):
                try:
                    async with http_session.post(
                        GROQ_URL,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(
                            total=CFG.GROQ_TIMEOUT_SECONDS,
                            connect=8,
                            sock_connect=8,
                            sock_read=CFG.GROQ_TIMEOUT_SECONDS,
                        ),
                    ) as response:
                        if response.status == 200:
                            try:
                                data = await response.json(content_type=None)
                            except (aiohttp.ClientError, ValueError):
                                log.warning(
                                    "Groq %s returned invalid JSON for model %s.",
                                    purpose, model,
                                )
                                break
                            content = _groq_message_text(data)
                            if content:
                                return content
                            log.warning(
                                "Groq %s returned an empty message for model %s.",
                                purpose, model,
                            )
                            break

                        status = response.status
                        try:
                            error_detail = (await response.text())[:400].replace("\\n", " ")
                        except (aiohttp.ClientError, asyncio.TimeoutError):
                            error_detail = "response body unavailable"
                        log.warning(
                            "Groq %s model %s returned HTTP %s (attempt %s/2): %s",
                            purpose, model, status, attempt + 1, error_detail,
                        )
                        if status in {401, 403}:
                            log.error(
                                "Groq authentication/permission failed; check the API key and project access."
                            )
                            return None

                        if status == 429:
                            wait_seconds = _retry_after_seconds(
                                response.headers.get("Retry-After")
                            )
                            if attempt == 0:
                                # If the provider omits Retry-After, use one short,
                                # bounded pause rather than failing immediately.
                                wait_seconds = wait_seconds or 1.0
                                await asyncio.sleep(wait_seconds + random.uniform(0.05, 0.25))
                                continue
                            # Continue to the next configured model after this model's
                            # bounded retry is exhausted instead of aborting all fallbacks.
                            break

                        if status in {408, 425} or status >= 500:
                            if attempt == 0:
                                await asyncio.sleep(0.35 + random.uniform(0.05, 0.25))
                                continue
                            break

                        # 400/404/422 commonly indicate model/request compatibility;
                        # move to the next configured model without retrying the same one.
                        break

                except asyncio.CancelledError:
                    raise
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                    log.warning(
                        "Groq %s transport failure for model %s (attempt %s/2): %s",
                        purpose, model, attempt + 1, type(exc).__name__,
                    )
                    if attempt == 0:
                        await asyncio.sleep(0.25 + random.uniform(0.05, 0.2))
                        continue
                    break

    return None


async def get_reply(
    message: str,
    user_id: int,
    history: list[dict[str, str]] | None = None,
) -> str:
    history = history or []
    reply = await _groq_chat(
        build_messages(message, history),
        max_completion_tokens=CFG.GROQ_MAX_TOKENS,
        # A little less randomness reduces generic praise and repeated questions.
        temperature=0.68,
        purpose="chat reply",
    )
    if reply:
        reply = re.sub(r"^\s*(?:ria|assistant)\s*:\s*", "", reply, flags=re.IGNORECASE).strip()
        reply = reply.replace("\x00", "").strip()
        # Preserve the two supported optional bubble markers; collapse accidental repeats.
        reply = re.sub(r"(?:\s*<RIA_NEXT>\s*){2,}", " <RIA_NEXT> ", reply, flags=re.IGNORECASE)
        reply = re.sub(r"(?:\s*<RIA_LAST>\s*){2,}", " <RIA_LAST> ", reply, flags=re.IGNORECASE)
        return reply[:CFG.CHAT_REPLY_LIMIT]

    log.error("All Groq models failed or returned no usable chat reply.")
    return fallback_reply(message, history)


async def get_idle_checkin() -> str:
    """Create one short, context-aware private check-in for the creator."""
    creator_id = int(CREATOR_ID_RAW) if CREATOR_ID_RAW and CREATOR_ID_RAW.isdigit() else None
    history = list(memory.get(str(creator_id), [])) if creator_id else []
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

    # Reuse the same bounded history builder as normal conversation. The old
    # hand-built path could send every stored turn and exceed the model context.
    messages = build_messages(
        "Write a brief, natural Discord DM in Ria's familiar, playful, considerate voice. "
        "Let her personality and recent conversation guide the wording. Make it feel like "
        "a relaxed check-in from a close companion, with no pressure to reply. Return only the message.",
        history,
    )
    content = await _groq_chat(
        messages,
        max_completion_tokens=160,
        temperature=0.82,
        purpose="idle check-in",
    )
    if content:
        clean = re.sub(r"^\s*(?:ria|assistant)\s*:\s*", "", content, flags=re.IGNORECASE)
        clean = clean.replace("\x00", "").strip()
        return clean[:350] or fallback
    return fallback


async def idle_checkin_loop() -> None:
    """Send at most one optional DM after creator inactivity."""
    global _creator_checkin_sent
    if not CFG.IDLE_CHECKINS_ENABLED:
        return
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
        timeout = aiohttp.ClientTimeout(
            total=CFG.GROQ_TIMEOUT_SECONDS,
            connect=8,
            sock_connect=8,
            sock_read=CFG.GROQ_TIMEOUT_SECONDS,
        )
        connector = aiohttp.TCPConnector(
            limit=20,
            limit_per_host=8,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        http_session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            raise_for_status=False,
        )
    if CFG.IDLE_CHECKINS_ENABLED and (_idle_checkin_task is None or _idle_checkin_task.done()):
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


def split_discord_text(text: str, limit: int = 1900) -> list[str]:
    """Split long text at sensible boundaries without silently dropping content."""
    remaining = str(text or "").strip()
    if not remaining:
        return []
    chunks: list[str] = []
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit + 1)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit + 1)
        if cut < limit // 2:
            cut = limit
        piece = remaining[:cut].strip()
        if piece:
            chunks.append(piece)
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def prepare_discord_replies(text: str, limit: int = 1900) -> tuple[list[str], list[str]]:
    """Split a model reply into main chunks and up to two distinct optional bubbles."""
    raw = str(text or "").replace("\x00", "").strip()
    if not raw:
        return [], []

    raw_parts = re.split(r"\s*<RIA_(?:NEXT|LAST)>\s*", raw, maxsplit=2, flags=re.IGNORECASE)
    main = re.sub(r"^ria\s*:\s*", "", raw_parts[0].strip(), flags=re.IGNORECASE)
    main = re.sub(r"[ \t]+\n", "\n", main)
    main_chunks = split_discord_text(main, limit=limit)
    if not main_chunks or len(raw_parts) < 2:
        return main_chunks, []

    def normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    reference_text = " ".join(main_chunks)
    accepted: list[str] = []
    for raw_aside in raw_parts[1:3]:
        aside = re.sub(r"\s*\n+\s*", " ", raw_aside)
        aside = re.sub(r"[ \t]{2,}", " ", aside).strip()
        aside = re.sub(r"^ria\s*:\s*", "", aside, flags=re.IGNORECASE)
        aside = " ".join(aside.split()[:24]).rstrip(" ,;:")[:280]
        aside_norm = normalize(aside)
        reference_norm = normalize(reference_text + " " + " ".join(accepted))
        duplicate = (
            not aside_norm
            or aside.startswith(("<", "```"))
            or len(aside_norm) < 4
            or aside_norm == reference_norm
            or SequenceMatcher(None, aside_norm, reference_norm).ratio() >= 0.88
        )
        if not duplicate:
            accepted.append(aside)
    return main_chunks, accepted


_aside_tasks: set[asyncio.Task] = set()


def _track_task(task: asyncio.Task) -> None:
    _aside_tasks.add(task)
    task.add_done_callback(_aside_tasks.discard)


async def send_optional_asides(
    message: discord.Message,
    asides: list[str],
    user_text: str,
    user_id: int,
    generation: int,
) -> None:
    """Send up to two separate, optional bubbles while the turn is still current."""
    try:
        for index, aside in enumerate(asides[:2]):
            delay = random.uniform(3.2, 4.8) if index == 0 else random.uniform(4.0, 5.8)
            async with message.channel.typing():
                await asyncio.sleep(delay)
                if _message_generation.get(user_id) != generation or not is_auth(user_id):
                    return
                if bot.is_closed():
                    return
                await message.channel.send(
                    aside,
                    allowed_mentions=discord.AllowedMentions.none(),
                )

            if _message_generation.get(user_id) != generation:
                return
            with _storage_lock:
                turns = memory.get(str(user_id), [])
                if turns and turns[-1].get("user") == user_text:
                    turns[-1]["ria"] = (
                        turns[-1].get("ria", "") + "\n" + aside
                    ).strip()[:CFG.MEMORY_MESSAGE_CHAR_LIMIT]
                    save_json(CFG.MEMORY_FILE, memory)
    except asyncio.CancelledError:
        raise
    except discord.Forbidden:
        log.warning("Missing permission to send Ria's optional aside in channel %s", message.channel.id)
    except discord.HTTPException:
        log.exception("Discord rejected Ria's optional aside")
    except Exception:
        log.exception("Optional aside task failed")


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    # Strict privacy lock: only the configured creator can interact with Ria.
    if not CREATOR_ID_RAW or not CREATOR_ID_RAW.isdigit():
        return
    if message.author.id != int(CREATOR_ID_RAW):
        return

    mark_creator_activity(message.author.id)
    message_generation = _message_generation.get(message.author.id, 0) + 1
    _message_generation[message.author.id] = message_generation
    await bot.process_commands(message)

    if message.content.startswith(CFG.PREFIX):
        return
    if not is_auth(message.author.id):
        return

    user_text = re.sub(r"<@!?(\d+)>", "", message.content).strip()
    if not user_text:
        return

    try:
        # Snapshot only earlier turns; this message is added after Discord accepts
        # Ria's reply, preventing failed sends from polluting conversation memory.
        history = [
            dict(item)
            for item in memory.get(str(message.author.id), [])
            if isinstance(item, dict)
        ]
        async with message.channel.typing():
            reply = await get_reply(user_text, message.author.id, history)
            # Give the typing indicator a short, variable finishing beat after
            # generation. Longer replies get a little more time, with a firm cap.
            if reply and reply != GROQ_OFFLINE_REPLY:
                typing_pause = min(7.0, 1.2 + (len(reply) / 95.0))
                await asyncio.sleep(typing_pause + random.uniform(0.25, 0.85))

        if _message_generation.get(message.author.id) != message_generation:
            return

        main_chunks, aside_replies = prepare_discord_replies(reply)
        if not main_chunks:
            log.warning("Ria generated an empty reply; skipping message %s", message.id)
            return

        delivered_chunks: list[str] = []
        for chunk_index, chunk in enumerate(main_chunks):
            if _message_generation.get(message.author.id) != message_generation:
                break
            if chunk_index:
                await asyncio.sleep(random.uniform(0.65, 1.25))
                if _message_generation.get(message.author.id) != message_generation:
                    break
            try:
                await message.channel.send(
                    chunk,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                delivered_chunks.append(chunk)
            except discord.Forbidden:
                log.warning("Missing permission to send Ria's reply in channel %s", message.channel.id)
                break
            except discord.HTTPException:
                log.exception("Discord rejected a reply chunk in channel %s", message.channel.id)
                break

        all_chunks_delivered = len(delivered_chunks) == len(main_chunks)
        turn_is_current = _message_generation.get(message.author.id) == message_generation
        if delivered_chunks and turn_is_current and reply != GROQ_OFFLINE_REPLY:
            # Provider outage notices are operational messages, not character
            # dialogue; never let them pollute Ria's conversational memory.
            add_memory(message.author.id, user_text, "\n".join(delivered_chunks))
            update_auth(message.author.id)

        if (aside_replies and all_chunks_delivered
                and is_auth(message.author.id)
                and _message_generation.get(message.author.id) == message_generation):
            task = asyncio.create_task(
                send_optional_asides(
                    message, aside_replies, user_text, message.author.id, message_generation
                )
            )
            _track_task(task)

        # Delete the original only after the complete reply was delivered.
        if all_chunks_delivered and CFG.DELETE_CHAT_MESSAGES:
            await safe_delete(message)
    except discord.Forbidden:
        log.warning("Missing permission to reply in channel %s", message.channel.id)
    except discord.HTTPException:
        log.exception("Discord failed while delivering Ria's reply in channel %s", message.channel.id)
    except asyncio.CancelledError:
        raise
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

        # Compare UTF-8 bytes so non-ASCII creator keys are supported safely.
        if hmac.compare_digest(
            supplied.encode("utf-8"),
            SECRET.encode("utf-8"),
        ):
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
    if not SECRET or not CREATOR_ID_RAW or not CREATOR_ID_RAW.isdigit():
        raise RuntimeError("Strict privacy lock requires SECRET_KEY and a numeric CREATOR_ID.")
    log.info("Ria v%s configuration loaded; idle check-ins: %s; chat-message deletion: %s.",
             CFG.VERSION, CFG.IDLE_CHECKINS_ENABLED, CFG.DELETE_CHAT_MESSAGES)
    if GROQ_KEY:
        log.info("Groq integration is configured with %s model fallback(s).", len(CFG.GROQ_MODELS))
    else:
        log.warning("No Groq key found (GROQ_API_KEY / GROQ_API_TOKEN / GROQ_IPA_TOKEN); chat replies will use the local connection notice.")

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
        pending_tasks = list(_aside_tasks)
        if _idle_checkin_task is not None and not _idle_checkin_task.done():
            _idle_checkin_task.cancel()
            pending_tasks.append(_idle_checkin_task)
        for task in pending_tasks:
            if not task.done():
                task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
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
