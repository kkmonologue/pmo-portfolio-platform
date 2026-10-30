"""LLM extractor for any OpenAI-compatible chat-completions endpoint.

Gemini, Groq, Mistral and Ollama all expose one, so switching provider is configuration:
a base URL, an API key and a model name. API keys are read from environment variables (or
a local .env file) and are never logged or written anywhere.

- One request per update, temperature 0, JSON output validated with pydantic.
- Invalid JSON gets one repair attempt (the error is sent back to the model).
- Responses are cached in SQLite keyed by provider, model, prompt version and input, so
  re-running an evaluation costs nothing and free-tier quotas go further.
- A simple rate limiter (requests per minute) plus retries with backoff on 429 / 5xx,
  honouring Retry-After.
"""

import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import ValidationError

from .categories import DEFAULT_CATEGORIES
from .schema import Extraction

PROMPT_VERSION = "v1"


@dataclass(frozen=True)
class Provider:
    base_url: str
    key_env: str | None
    default_model: str
    default_rpm: int


# Model names change over time: check your provider's console and override with LLM_MODEL.
PROVIDERS = {
    "gemini": Provider("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "gemini-3.8-flash", 10),
    "groq": Provider("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-120b", 30),
    "mistral": Provider("https://api.mistral.ai/v1", "MISTRAL_API_KEY", "mistral-small-latest", 30),
    "ollama": Provider("http://localhost:11434/v1", None, "llama3.2", 600),
}


def build_system_prompt(categories: dict[str, dict]) -> str:
    cats = "\n".join(f"- {name}: {spec['definition']}" for name, spec in categories.items())
    return f"""You read bi-weekly project status updates written by project owners in an after-sales PMO and return structured signals as JSON.

Return exactly this JSON object and nothing else:
{{"rag": "green|amber|red", "stated_rag": "green|amber|red|null", "risks": [{{"category": "<one of the categories>", "severity": "low|medium|high"}}], "blocked": true|false, "next_milestone_date": "YYYY-MM-DD|null", "next_milestone_date_precision": "day|week|null"}}

Risk categories (use "other" if none fits):
{cats}

Rules:
- risks: only problems that are currently open. Ignore progress, solved issues and statements like "no risks". One entry per category.
- severity: high = will miss a date or needs escalation; medium = could affect the timeline; low = minor, little impact.
- blocked: true only if the project itself cannot move forward right now. A delayed shipment or a solved blocker is not a blocked project.
- next_milestone_date: the date given for the next step or milestone. Resolve dates without a year relative to the posting date (a next step is usually in the future). If only a week is given ("w/c 10 Nov", "CW46"), return the Monday of that week with precision "week".
- rag is the PMO's definition, judged from the content, not copied from what the author typed: red if blocked, any high-severity risk, or the next milestone date is more than 14 days before the posting date; amber if any medium-severity risk or the next milestone date is before the posting date; green otherwise.
- stated_rag: the colour the author wrote (Green/G/on track, Amber/Yellow/A/at risk, Red/R/off track), or null if none."""


def _user_prompt(text: str, posted_on: dt.date) -> str:
    return f'Posting date: {posted_on.isoformat()}\nUpdate:\n"""\n{text}\n"""'


def _parse_json(content: str) -> dict:
    content = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.S)
    if fenced:
        content = fenced.group(1)
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in response")
    data = json.loads(content[start : end + 1])
    for key in ("stated_rag", "next_milestone_date", "next_milestone_date_precision", "rag"):
        if data.get(key) in ("null", "", "none", "None"):
            data[key] = None
    return data


class LLMExtractor:
    def __init__(
        self,
        provider: str = "gemini",
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        rpm: int | None = None,
        categories: dict[str, dict] | None = None,
        cache_path: str | Path | None = "data/llm_cache.sqlite",
        max_retries: int = 6,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        p = PROVIDERS.get(provider)
        if p is None and not base_url:
            raise ValueError(f"Unknown provider {provider!r}; use one of {sorted(PROVIDERS)} or pass base_url")
        self.provider = provider
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or p.base_url).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL") or p.default_model
        key_env = p.key_env if p else None
        self.api_key = api_key or os.getenv("LLM_API_KEY") or (os.getenv(key_env) if key_env else None)
        if key_env and not self.api_key:
            raise RuntimeError(f"No API key: set {key_env} (or LLM_API_KEY) in your environment or .env file")
        self.min_interval = 60.0 / (rpm or int(os.getenv("LLM_RPM", "0")) or (p.default_rpm if p else 30))
        self.categories = categories or DEFAULT_CATEGORIES
        self.system_prompt = build_system_prompt(self.categories)
        self.max_retries = max_retries
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        self.client = httpx.Client(base_url=self.base_url, headers=headers, timeout=timeout, transport=transport)
        self._last_call = 0.0
        self._json_mode = True  # switched off if the provider rejects response_format
        self._lock = threading.Lock()
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "repairs": 0, "failures": 0}
        self.cache = None
        if cache_path:
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            self.cache = sqlite3.connect(str(cache_path), check_same_thread=False)
            self.cache.execute("create table if not exists responses (key text primary key, response text, model text, created_at text)")

    @property
    def name(self) -> str:
        return f"llm:{self.provider}:{self.model}"

    def _key(self, text: str, posted_on: dt.date) -> str:
        raw = "|".join([self.base_url, self.model, PROMPT_VERSION, self.system_prompt, posted_on.isoformat(), text])
        return hashlib.sha256(raw.encode()).hexdigest()

    def _throttle(self) -> None:
        with self._lock:
            wait = self._last_call + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def _chat(self, messages: list[dict]) -> str:
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            body = {"model": self.model, "messages": messages, "temperature": 0}
            if self._json_mode:
                body["response_format"] = {"type": "json_object"}
            self._throttle()
            self.stats["requests"] += 1
            try:
                r = self.client.post("/chat/completions", json=body)
            except httpx.TransportError:
                if attempt == self.max_retries:
                    raise
                self.stats["retries"] += 1
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == self.max_retries:
                    r.raise_for_status()
                self.stats["retries"] += 1
                retry_after = r.headers.get("retry-after")
                time.sleep(float(retry_after) if retry_after and retry_after.replace(".", "").isdigit() else delay)
                delay = min(delay * 2, 60)
                continue
            if r.status_code == 400 and self._json_mode and "response_format" in r.text:
                # some OpenAI-compatible endpoints don't support JSON mode; the prompt asks for JSON anyway
                self._json_mode = False
                continue
            if r.status_code in (401, 403):
                raise RuntimeError(f"{self.provider} rejected the API key (HTTP {r.status_code}); check the key in your .env file")
            if r.status_code == 404:
                raise RuntimeError(f"{self.provider} has no model {self.model!r} (HTTP 404); set LLM_MODEL to a model your account can use")
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        raise RuntimeError("unreachable")

    def extract(self, text: str, posted_on: dt.date) -> Extraction:
        key = self._key(text, posted_on)
        if self.cache:
            row = self.cache.execute("select response from responses where key = ?", (key,)).fetchone()
            if row:
                self.stats["cache_hits"] += 1
                return Extraction.model_validate_json(row[0]).normalised([*self.categories, "other"])
        messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": _user_prompt(text, posted_on)}]
        content = self._chat(messages)
        try:
            result = Extraction.model_validate(_parse_json(content))
        except (ValueError, ValidationError) as err:
            self.stats["repairs"] += 1
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"That was not valid: {str(err)[:300]}. Return only the JSON object in the required format."},
            ]
            try:
                result = Extraction.model_validate(_parse_json(self._chat(messages)))
            except (ValueError, ValidationError):
                self.stats["failures"] += 1
                return Extraction()  # empty result, counted as a failure; not cached so a rerun retries
        result = result.normalised([*self.categories, "other"])
        if self.cache:
            with self._lock:
                self.cache.execute(
                    "insert or replace into responses values (?, ?, ?, ?)",
                    (key, result.model_dump_json(), self.model, dt.datetime.now().isoformat()),
                )
                self.cache.commit()
        return result
