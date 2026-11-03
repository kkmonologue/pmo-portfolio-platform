# Status update extraction (stage 5)

`extractor/` turns free-text bi-weekly updates into structured signals: the RAG status judged from the content, the colour the author typed, open risks (category and severity), whether the project is blocked, and the next milestone date. It stands on its own (text and a posting date in, signals out), so it works on any PMO's updates, not only this platform's.

Two extractors share one interface:

| | `rules` | `llm` |
|---|---|---|
| How | keyword lists, regular expressions, a date parser | any OpenAI-compatible chat API: Gemini, Groq, Mistral, DeepSeek, Kimi, Ollama (local) |
| Needs | nothing | an API key in `.env` (or Ollama running locally) |
| Role | baseline and fallback; used in CI | the real extractor |

## Quick start

```bash
# Baseline on both evaluation sets (no API needed)
uv run python -m extractor eval

# Add your key: copy .env.example to .env and fill in GEMINI_API_KEY (or GROQ_API_KEY, ...)
uv run python -m extractor eval --extractor rules llm --provider groq --sample 100

# Any spreadsheet of updates, any company
uv run python -m extractor extract --input updates.xlsx --text-column Comments --date-column Date --output signals.xlsx

# Into the warehouse (incremental; the Dagster pipeline does this automatically)
uv run python -m extractor warehouse --extractor rules
uv run python -m extractor warehouse --extractor llm --max-new 200
```

The report goes to `data/eval/report.md`, with per-update errors in `data/eval/results.json`.

## Evaluation design

**Two sets, because one would mislead.**

- **Simulated** (stratified sample of 300 by RAG colour, risk / no risk and blocked): the simulator labels every update from the project's hidden state at the time of writing, so ground truth is exact. But the text comes from templates, so it's easier than real writing.
- **Challenge** (29 hand-written, hand-labelled updates in `extractor/challenge_set.jsonl`): phrasing the rules were not written for, such as solved problems described with risk words, "not blocked anymore", blockers hidden behind "none", implied severity ("go-live will slip a month", "not realistic"), typed colours that contradict the content, and dates like "22nd Oct" or "12th of December". Each case says why it is tricky, and a test checks every label follows the RAG definition.

**One RAG definition, written down.** Red if blocked, any high-severity risk, or the next milestone more than 14 days before the posting date. Amber if any medium-severity risk or the next milestone is overdue. Green otherwise. The labels, the rules and the LLM prompt all use it: this is the PMO's documented criterion, not a hint to the model.

**Metrics.** RAG accuracy and macro-F1 with a confusion matrix; risk precision / recall / F1 over the set of categories per update; severity accuracy on correctly found risks; blocked precision / recall; next-milestone date accuracy (exact day, or within 6 days when only a week is given). Reference line: how often the colour the author typed matches the content.

## Results

Run on 2026-11-03: rules versus `openai/gpt-oss-120b` on Groq's free tier. The simulated set was sampled down to 100 (same stratification) to fit the free tier's daily token budget.

### Challenge set (n = 29): realistic phrasing

| Metric | rules | LLM (gpt-oss-120b) |
|---|---|---|
| RAG accuracy | 0.59 | **0.97** |
| RAG macro-F1 | 0.56 | **0.95** |
| Risk precision / recall / F1 | 0.75 / 0.15 / 0.25 | 0.70 / **0.70** / **0.70** |
| Severity accuracy (found risks) | 1.00 | 0.86 |
| Blocked precision / recall | 0.00 / 0.00 | 0.57 / **1.00** |
| Next-milestone date accuracy | 0.90 | 0.85 |
| Date missing | 0.05 | 0.15 |

RAG confusion (rows = truth, columns = extracted):

| | rules: green | amber | red | LLM: green | amber | red |
|---|---|---|---|---|---|---|
| **green** | 11 | 1 | 1 | 13 | 0 | 0 |
| **amber** | 2 | 3 | 0 | 0 | 4 | 1 |
| **red** | 7 | 1 | 3 | 0 | 0 | 11 |

The rules call 7 of 11 red projects green: they miss blockers and implied severity. The LLM gets 28 of 29 right, finds every blocker, and recovers 70% of risks instead of 15%.

### Simulated set (n = 100): template text

| Metric | rules | LLM (gpt-oss-120b) |
|---|---|---|
| RAG accuracy | **0.96** | 0.86 |
| RAG macro-F1 | **0.95** | 0.85 |
| Risk precision / recall / F1 | 0.82 / 0.85 / 0.83 | **0.91 / 0.94 / 0.92** |
| Severity accuracy (found risks) | **1.00** | 0.84 |
| Blocked precision / recall | 1.00 / 1.00 | 0.83 / 1.00 |
| Next-milestone date accuracy | 0.90 | 0.85 |
| Typed colour matches the content (reference) | 0.89 | 0.89 |

RAG confusion:

| | rules: green | amber | red | LLM: green | amber | red |
|---|---|---|---|---|---|---|
| **green** | 56 | 1 | 2 | 47 | 10 | 2 |
| **amber** | 0 | 22 | 0 | 0 | 21 | 1 |
| **red** | 1 | 0 | 18 | 0 | 1 | 18 |

### What this says

- **The rules only work on text written like their keywords.** Near-perfect on templates, 0.59 on realistic phrasing, and no blockers found at all. The LLM holds up on both.
- **The LLM finds risks better everywhere** (F1 0.92 and 0.70 against 0.83 and 0.25).
- **Its weakness is severity, and it errs on the cautious side.** Nearly all its RAG errors on simulated data are green updates read as amber (10 of 14). They come from rating a minor risk as medium, which the RAG definition turns into amber. For a PMO an extra amber is cheaper than a missed red, but it's the next thing to fix: give the prompt a few labelled severity examples, then re-run.
- **Practical setup:** the LLM as the extractor, the rules as the free fallback when no key is set or the API is down. That's how the platform is wired.

Reproduce: `uv run python -m extractor eval --extractor rules llm --provider groq --sample 100` (about 25 minutes on the free tier; cached afterwards). Per-update errors are in `data/eval/results.json`.

### Running it on free tiers

Gemini's free tier for the newest Flash model failed this run: repeated 503 (overloaded) and then a daily quota far below the ~330 requests needed. Groq's free tier (no card) worked, at 6 requests per minute to stay under its 8K tokens-per-minute limit. DeepSeek and Kimi are paid but cost cents for the whole evaluation.

## LLM client details (`extractor/llm.py`)

- **Provider-agnostic.** Presets for `gemini`, `groq`, `mistral`, `deepseek`, `kimi` and `ollama`; any other OpenAI-compatible endpoint works with `LLM_BASE_URL`. Model names change, so override with `LLM_MODEL`.
- **Validated output.** Temperature 0, JSON mode where supported (the client drops it automatically if a provider rejects it), pydantic validation, one repair round-trip on invalid JSON. Unknown categories become `other`. If parsing still fails, the result is empty and counted as a failure, not cached.
- **Built for free tiers.** Requests-per-minute limiter, retries with backoff on 429 / 5xx honouring `Retry-After`, a SQLite cache keyed by endpoint, model, prompt version and input, and `--max-new` / `LLM_MAX_PER_RUN` to spread a backlog over several runs.
- **Clear errors.** A rejected key or an unknown model name gives a message that says what to change in `.env`.
- **Tested without network.** `tests/test_extractor.py` runs the client against a fake API: parsing fenced JSON, caching, a 429 retry, repairing invalid JSON, falling back when JSON mode isn't supported, bad key and unknown model.

## Into the platform

- `extract.status_update_signals` in the warehouse holds one row per update and extractor. `python -m extractor warehouse` and the Dagster asset `extract/status_update_signals` (group `ai`) only process updates that extractor has not seen yet.
- dbt reads it as source `extract`. `stg_extract__status_update_signals` prefers an LLM result over the rules, and returns no rows when no extraction has run yet, so `dbt build` never depends on stage 5.
- `fct_status_update_signals` puts the extracted signals next to the update's project, meeting and typed colour; `stated_differs_from_content` flags optimistic reporting.
- `mart_project_risks` gains a category **reported**: the latest update (within 30 days) reads red or blocked. It's the one risk the rules on system data cannot see, because it only exists in the text.
- In Dagster the extraction runs between the raw load and dbt. `EXTRACTOR=llm` in `.env` switches the pipeline to the LLM, capped at `LLM_MAX_PER_RUN` updates per run.

## Privacy

Free API tiers may use what you send to train models. That's fine here only because every update is fictional and generated by this repository. Never send real company data to a free tier; use a paid tier with a no-training agreement, or a local model through Ollama.

## Caveats

- Simulated text is template-based, so simulated-set scores (for the rules especially) are optimistic. The challenge set is small (29); treat its numbers as directional.
- The rules were written knowing the general topic vocabulary, not the templates, but the templates are in the same repository. The challenge set exists to keep that honest.
- One annotator labelled the challenge set. A few severity calls (medium vs high) are judgement calls; disagreements on those are worth reading in `results.json` rather than taking the score at face value.
