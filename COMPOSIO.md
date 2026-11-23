# Composio integration — notes

Composio is the **retrieval layer** of this pipeline:

```
EXA_SEARCH  →  find candidate doc URLs
EXA_GET_CONTENTS_ACTION  →  fetch clean page text
```

Everything else (NVIDIA Nemotron extraction, Pydantic, verification, SQLite cache, pandas
analytics, Jinja2 report) is independent of Composio. If Composio fails, the same step
falls back to DuckDuckGo + httpx + trafilatura.

## Implementation

`agent/composio_tools.py`:

- Loads `COMPOSIO_API_KEY` from `.env` if it is not already in the environment.
- Creates one **Session** (`client.sessions.create(user_id, toolkits=["exa"])`) and
  executes tools through it. Sessions are required for **Instant** tools; direct
  `client.tools.execute(...)` looks for a connected provider account instead.
- **Serializes calls with a lock**: the SDK session is not safe to use from multiple
  threads. Concurrent use hangs; the lock makes retrieval reliable while LLM extraction
  remains concurrent.
- Normalizes the SDK response (`ToolRouterSessionExecuteResponse.data`) before parsing
  URLs/text.

`agent/retrieve.py`:

- `retrieve()` / `retrieve_more()` try Composio first; on exception or empty results
  they fall back to DuckDuckGo.
- `retrieve_more()` powers the gap-fill loop in `run.py`.

## Enable (free)

1. Sign up at <https://dashboard.composio.dev> (Hobby: $0, no card).
2. **Project Settings → General → enable "Instant Toolkits"** (off by default).
3. Put the key in `.env`: `COMPOSIO_API_KEY=...` (see `.env.example`).
4. Check the **$2 one-time Instant credit** under Billing.

## Free-tier facts (checked 2026-11-23)

| Option | What you get | Catch |
| --- | --- | --- |
| Hobby (Platform) | $0, 100K tool calls/mo, hard-capped | 100K applies to your own app/key/MCP; managed apps capped at 20K |
| Free (for-you) | $0, 10K calls/mo, **$2 one-time** credits | Small allowance |
| `composio_search` (keyless) | Was the ideal no-key search | **Retired 2026-11-13** |
| Exa / Tavily Instant | No provider key needed | Metered from the $2 credit, then paid (~$0.007/search, ~$0.001/page) |
| NVIDIA API | API key required | Nemotron extraction and verification |

SQLite document caching reuses fetched material on reruns; serialized session calls
avoid unsafe concurrent use.

## Errors seen and fixes

| Error | Cause | Fix |
| --- | --- | --- |
| `ToolVersionRequiredError` | `version="latest"` with direct execution | Use Sessions (versioning handled) or pass a concrete toolkit version |
| `400 The 'account' parameter is not supported` | Multi-account selection disabled on the project | Execute without `account`; Instant is auto-selected |
| `400 No active connection found for toolkit 'exa'` | Instant Toolkits disabled | Enable **Instant Toolkits** in project settings |
| Hang / no progress | Shared SDK session used from multiple threads, or a stalled call | Serialized with a lock + 30s request timeout + circuit breaker (falls back to DuckDuckGo) |
| `402 Metering_WalletBalanceExhausted` | $2 credit used up | Falls back to DuckDuckGo automatically |

## Optional overrides

```
COMPOSIO_SEARCH_TOOL=EXA_SEARCH            # or TAVILY_SEARCH
COMPOSIO_FETCH_TOOL=EXA_GET_CONTENTS_ACTION
COMPOSIO_TOOLKITS=exa                      # comma-separated toolkits for the session
COMPOSIO_USER_ID=research-agent
COMPOSIO_TIMEOUT=30                        # seconds per Composio call
COMPOSIO_MAX_FAILS=3                       # consecutive failures before disabling Composio
```

## MCP

Two directions are possible:

1. Composio can expose a Session over MCP (`session.mcp.url`) for an agent to call its
   tools.
2. This pipeline is itself a natural MCP tool: a thin server exposing
   `research_app(name)` / `list_apps()` would let an external agent (or a Composio
   session) run the same research per app.
