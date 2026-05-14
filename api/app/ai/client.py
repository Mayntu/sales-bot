"""
AIClient — wraps OpenAI chat completions.

Design decisions:
  - Singleton: created once in lifespan, shared across all requests.
    AsyncOpenAI pools HTTP connections internally via httpx, so one instance
    is all you need even under high load.
  - Retries: tenacity retries the raw API call up to 2 times (3 total attempts)
    with exponential backoff. max_retries=0 on the SDK level so tenacity is
    the single source of truth for retry logic.
  - Fallback: if all retries fail the exception is caught in generate() and a
    safe Russian fallback message is returned — the bot never goes silent.
"""

from __future__ import annotations

import json
import re
import sys
import traceback
from dataclasses import dataclass

import structlog
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.domain.conversations.service import normalize_next_state
from app.domain.users.models import UserState

log = structlog.get_logger(__name__)

FALLBACK_REPLY = "Прости, что-то пошло не так. Напиши ещё раз или попробуй чуть позже 🙂"


def _strip_llm_markdown_plain_text(reply: str) -> str:
    """Telegram messages are sent without parse_mode; **bold** would show literally."""
    s = reply.strip()
    for _ in range(16):  # unwind nested fake-bold
        nxt = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
        if nxt == s:
            break
        s = nxt
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", s)
    for _ in range(8):
        nxt = re.sub(r"__([^_]+)__", r"\1", s)
        if nxt == s:
            break
        s = nxt
    s = s.replace("**", "").replace("__", "")
    return s.strip()


@dataclass
class AIResult:
    reply: str
    next_state: UserState
    client_name: str | None
    client_goal: str | None
    agreed_product: str | None = None  # filled by AI when next_state=CLOSE


class AIClient:
    """
    Thread/coroutine-safe OpenAI client.

    Create once via init_ai_client() and inject with get_ai_client().
    AsyncOpenAI reuses an internal httpx.AsyncClient with connection pooling.
    """

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            timeout=30.0,
            max_retries=0,  # tenacity owns retry logic
        )

    # ── Internal: retried raw API call ───────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),  # 1 initial + 2 retries
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _call_api(self, system_prompt: str, messages: list[dict]) -> tuple[dict, dict | None]:
        res = await self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}, *messages],
            response_format={"type": "json_object"},
            temperature=0.85,
            max_tokens=600,
        )
        content = res.choices[0].message.content or "{}"
        # OpenAI occasionally wraps JSON in markdown fences despite response_format.
        # Strip ``` or ```json ... ``` wrappers before parsing.
        content = re.sub(r"^```(?:json)?\s*", "", content.strip())
        content = re.sub(r"\s*```$", "", content)
        raw = json.loads(content)

        usage_obj = getattr(res, "usage", None)
        usage_payload: dict | None = None
        if usage_obj is not None:
            usage_payload = {
                "prompt_tokens": usage_obj.prompt_tokens,
                "completion_tokens": usage_obj.completion_tokens,
                "total_tokens": usage_obj.total_tokens,
            }

        return raw, usage_payload

    # ── Public: parse + fallback ─────────────────────────────────────────────

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        current_state: UserState,
        *,
        request_scope: str = "chat",
    ) -> AIResult:
        """request_scope distinguishes log source, e.g. ``chat`` vs ``followup``."""
        try:
            data, usage = await self._call_api(system_prompt, messages)

            if usage is not None:
                log.info(
                    "openai_token_usage",
                    request_scope=request_scope,
                    model=self.model,
                    **usage,
                )
            else:
                log.warning(
                    "openai_usage_missing",
                    request_scope=request_scope,
                    model=self.model,
                    message="completion response had no usage field",
                )
        except Exception as exc:
            # Wrap log call in its own try/except: if structlog itself crashes
            # (e.g. format_exc_info pipeline failure) we must not swallow the
            # original error silently — print to stderr as guaranteed fallback.
            try:
                log.error(
                    "openai_generate_failed",
                    request_scope=request_scope,
                    model=self.model,
                    fallback=True,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
            except Exception:
                print(
                    f"[openai_generate_failed] structlog itself failed. "
                    f"Original error: {type(exc).__name__}: {exc}\n"
                    f"{''.join(traceback.format_exc())}",
                    file=sys.stderr,
                    flush=True,
                )
            return AIResult(
                reply=FALLBACK_REPLY,
                next_state=current_state,
                client_name=None,
                client_goal=None,
            )

        raw_state = str(data.get("next_state") or current_state.value).upper()
        try:
            proposed = UserState(raw_state)
        except Exception:
            proposed = current_state

        return AIResult(
            reply=_strip_llm_markdown_plain_text(data.get("reply") or FALLBACK_REPLY),
            next_state=normalize_next_state(current_state, proposed),
            client_name=data.get("client_name") or None,
            client_goal=data.get("client_goal") or None,
            agreed_product=data.get("agreed_product") or None,
        )


# ── Module-level singleton ────────────────────────────────────────────────────

_instance: AIClient | None = None


def init_ai_client() -> AIClient:
    """Call once during application lifespan startup."""
    global _instance
    s = get_settings()
    _instance = AIClient(api_key=s.openai_api_key, model=s.openai_model)
    return _instance


def get_ai_client() -> AIClient:
    """FastAPI dependency / direct accessor. Raises if not initialised."""
    if _instance is None:
        raise RuntimeError("AIClient is not initialised; call init_ai_client() in lifespan")
    return _instance
