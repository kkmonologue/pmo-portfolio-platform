# Status update extraction (stage 5)

`extractor/` turns free-text bi-weekly updates into structured signals: the RAG status judged from the content, the colour the author typed, open risks (category and severity), whether the project is blocked, and the next milestone date. It stands on its own (text and a posting date in, signals out), so it works on any PMO's updates, not only this platform's.

Two extractors share one interface:

| | `rules` | `llm` |
|---|---|---|
| How | keyword lists, regular expressions, a date parser | any OpenAI-compatible chat API: Gemini, Groq, Mistral, Ollama (local) |
| Needs | nothing | an API key in `.env` (or Ollama running locally) |
| Role | baseline and fallback; used in CI | the real extractor |

## Quick start

```bash
# Baseline on both evaluation sets (no API needed)
uv run python -m extractor eval

# Add your key: copy .env.example to .env and fill in GEMINI_API_KEY (or GROQ_API_KEY, ...)
uv run python -m extractor eval --extractor rules llm --provider gemini --sample 300

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

### Rule-based baseline

| Metric | Simulated (n = 300) | Challenge (n = 29) |
|---|---|---|
| RAG accuracy | 0.99 | 0.59 |
| RAG macro-F1 | 0.99 | 0.56 |
| Risk precision / recall / F1 | 0.88 / 0.87 / 0.87 | 0.75 / 0.15 / 0.25 |
| Severity accuracy (found risks) | 0.99 | 1.00 |
| Blocked precision / recall | 1.00 / 1.00 | 0.00 / 0.00 |
| Next-milestone date accuracy | 0.94 | 0.90 |
| Typed colour matches the content (reference) | 0.83 | 0.00 |

Keywords are near-perfect on template text and collapse on real-sounding text: they find 15% of risks and no blockers on the challenge set. That gap is the case for an LLM. And the colour authors type is wrong one time in six even on simulated data, so reading the content matters.

### LLM

Run `uv run python -m extractor eval --extractor rules llm --provider gemini` with your own key. The report puts both extractors side by side on both sets. Responses are cached in `data/llm_cache.sqlite`, so rerunning the report costs nothing.

## LLM client details (`extractor/llm.py`)

- **Provider-agnostic.** Presets for `gemini`, `groq`, `mistral` and `ollama`; any other OpenAI-compatible endpoint works with `LLM_BASE_URL`. Model names change, so override with `LLM_MODEL`.
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
