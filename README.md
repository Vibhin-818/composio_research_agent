# Composio Research Agent — 100 Apps

An automated research pipeline that profiles 100 apps across 10 categories — auth,
self-serve vs gated access, API surface, MCP presence, buildability — and generates a
single-page HTML case study with findings, patterns, clusters and an accuracy sample.

Retrieval runs on **Composio Instant** (Exa search + fetch) with an automatic
**DuckDuckGo fallback**. Extraction and verification use the NVIDIA
**Nemotron 3.5 Lightning 30B A3B** API through its OpenAI-compatible chat endpoint.

## Pipeline

```
apps.yaml
  -> Composio EXA_SEARCH              find candidate doc URLs
  -> Composio EXA_GET_CONTENTS_ACTION fetch + clean page text
  -> gap-fill loop                    re-query fields still unknown / low-confidence
  -> NVIDIA Nemotron API               strict JSON extraction with retry
  -> Pydantic validation               normalized auth labels; failures enter review queue
  -> self-critique verification       flags disputed rows as needs-human
  -> SQLite docs cache + results + manual-review queue
  -> pandas analytics + clusters
  -> Jinja2 -> docs/index.html
```

If Composio is unavailable or errors, retrieval falls back to DuckDuckGo + httpx +
trafilatura. The LLM, validation, verification, cache, analytics and report never
depend on Composio.

## What it produces

| Output | Description |
| --- | --- |
| `results.json` | JSON export of structured records for all 100 apps |
| `store/cache.sqlite` | Cached documents, app results and manual-review queue |
| `patterns.json` | Deterministic counts + clusters (auth, access, blockers, segments) |
| `verification.json` | Hand-checked sample + pass-1 → pass-2 accuracy delta |
| `docs/index.html` | Single-page case study (built; deployed via Pages) |

## Stack

Python 3.12 · Composio Instant (Exa) · NVIDIA Nemotron API · Pydantic · SQLite ·
pandas · Jinja2 · ddgs/httpx/trafilatura (fallback) · GitHub Pages.

## Setup (Windows)

```powershell
# 1. Virtual environment
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Dependencies
py -m pip install -r requirements.txt
```

### Configure API keys

1. Create an NVIDIA API key for the Nemotron endpoint at
   <https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b>.
2. Copy the local template and add the key to `.env`:

   ```powershell
   Copy-Item .env.example .env
   # Set NVIDIA_API_KEY in .env. Keep this file private; it is gitignored.
   ```

### Enable Composio retrieval (optional)

1. Sign up at <https://dashboard.composio.dev> — **Hobby** plan, **$0, no card**.
2. **Project Settings → General → enable "Instant Toolkits"** (off by default).
3. Set `COMPOSIO_API_KEY` in `.env`. Retrieval falls back to DuckDuckGo if Composio
   is not configured; NVIDIA_API_KEY is required for model calls.

4. Optional: check the one-time **$2 Instant credit** under Billing.

## Run

```powershell
py run.py              # all 100 (writes results.json after each app)
py analysis.py         # patterns.json (counts + clusters)
py report\build.py     # docs/index.html

py run.py --limit 3    # smoke test
py run.py --ids 1,2,5  # specific apps
```

Runs are **resumable**: fetched docs are cached in `store/cache.sqlite` and
`results.json` is rewritten after every app. Re-running re-processes apps but reuses the
cache; delete `store/cache.sqlite` and `results.json` for a clean run.

## Verification

```powershell
# hand-check 15–20 apps against official docs and fill verification_sample.csv:
# pass2_value is the final reviewed value; document human corrections in notes
py verify_sample.py    # writes verification.json with measured pass deltas and misses
py report\build.py
```

## Deploy (GitHub Actions → Pages)

1. Push the repo to GitHub (`main`).
2. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. `.github/workflows/pages.yml` runs `analysis.py` + `report/build.py` and deploys `docs/`.

Live URL: `https://<user>.github.io/<repo>/`.

## Composio notes

- **Role:** retrieval layer only (`EXA_SEARCH` + `EXA_GET_CONTENTS_ACTION` via a Session).
- The keyless `composio_search` toolkit was retired 2026-11-13; Instant tools need
  **Instant Toolkits enabled** in project settings.
- The Composio SDK session is not concurrency-safe, so `agent/composio_tools.py`
  serializes calls with a lock while extraction stays concurrent.
- Full details, free-tier facts and troubleshooting: [COMPOSIO.md](./COMPOSIO.md).

## Layout

```
apps.yaml              the 100 apps + hints (input)
schema.py              Pydantic models = the research contract
config.py              paths, model, concurrency
run.py                 orchestrator (retrieve -> extract -> gap-fill -> verify)
analysis.py            pandas patterns + clusters
verify_sample.py       accuracy harness
agent/
  llm.py               NVIDIA OpenAI-compatible JSON chat wrapper
  cache.py             SQLite docs, results and manual-review queue
  composio_tools.py    Composio Instant session wrapper (primary retrieval)
  retrieve.py          Composio-first retrieval + DuckDuckGo fallback
  extract.py           structured extraction and auth-label normalization
  verify.py            retrying evidence consistency check
report/
  build.py             renders the HTML from JSON
  template.html        case-study page
docs/.gitkeep          built output is generated (gitignored)
.env.example           key + overrides template (real .env is gitignored)
```
