# Runbook: AI analysis is failing

Users report *"The AI service is temporarily unavailable"*, or any AI call failing.

`/api/health` is **not** an AI check — it returns `{"status":"ok"}` without touching
Google, and did so throughout both real outages. Start here instead.

---

## 1. Ask the server what's wrong

```bash
TOKEN=$(curl -s -X POST https://<api-host>/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"..."}' | jq -r .access_token)

curl -s -H "Authorization: Bearer $TOKEN" \
  'https://<api-host>/api/ai/status?probe=true' | jq
```

`?probe=true` spends one real provider call (capped by `AI_PROBE_DAILY_LIMIT`, cached
60s process-wide). Drop it to see the model chain and SDK version for free.

To include Google's own error text, set `MEAL_AI_STATUS_DETAIL=1` in the Render
dashboard, re-run, then **turn it back off** — signup is open, so any account can read it.

| `probe.status` | What it means | What to do |
|---|---|---|
| `ok` | Provider is answering | The fault is elsewhere — check the frontend CSP (`vercel.json` `connect-src`) and `VITE_API_URL` |
| `upstream_5xx` | **Google returned 5xx.** Its outage, not yours | Usually transient and already retried + failed over. If sustained, switch `MEAL_AI_MODEL` to another generation in the dashboard |
| `unreachable` | Never got a reply: DNS, TCP, TLS, or our deadline | Check Render's status and outbound networking |
| `internal_error` | The SDK itself raised | Compare `sdk_version` and the build log's `pip` output against the last good deploy |
| `rejected` | Key, model id, or region | **Read `message`** — it's the only thing that separates them (see §3) |
| `rate_limited` | Quota or requests-per-minute exhausted | Check Google AI Studio; consider lowering `AI_DAILY_LIMIT` |
| `not_configured` | `GEMINI_API_KEY` empty or removed | Re-set it in the dashboard |
| `quota_exhausted` | You've used today's probe allowance | Raise `AI_PROBE_DAILY_LIMIT`, or read the logs below |

## 2. Render logs

Filter Application logs on `Gemini`. Every branch logs a distinct string.

| Log line | Cause | How the traceback looks |
|---|---|---|
| `Gemini server error` | **Google 5xx** | Leaf is `google.genai.errors.ServerError: 503 UNAVAILABLE ... 'The model is overloaded'`; frames end in `_api_client.py` |
| `Gemini unreachable` | **Our network** | Leaf is an `httpx.*` type — `ConnectError` (DNS/refused), `ConnectTimeout`, `ReadTimeout` (our own deadline) — or `ssl.SSLCertVerificationError`. Nested `socket.gaierror: [Errno -2]` means DNS. `kind=` names it without reading the stack |
| `Gemini call raised an unexpected error` | **Dependency drift** | Leaf is `TypeError`/`AttributeError`/`ImportError`/pydantic `ValidationError`, and **every frame is inside `site-packages/google/genai/`** with none of ours. See §4 |
| `Gemini rejected the request` + `code=…` | **Key / model / region** | `ClientError`; read the message (§3) |
| `Retrying Gemini in …` | Retries firing; frequency tracks provider health | — |
| `Giving up on Gemini after …` | The retry budget was spent — the outage outlasted a full minute of attempts | Raise `MEAL_AI_DEADLINE_S`, but raise the frontend timeout with it |

Only the **final** attempt logs a full traceback; earlier ones log a one-line WARNING,
so an outage doesn't bury the decisive line under identical stacks.

## 3. Reading a `ClientError` (HTTP 400) message

All three of these are 400 — the status code cannot tell them apart, which is exactly
what made the July 2026 outage take three days.

| Message contains | Cause | Fix |
|---|---|---|
| `API key not valid` | Wrong or revoked key | Re-issue in AI Studio. `_env()` already strips whitespace/quotes, so a survivor is genuinely wrong |
| `is not found for API version` | Retired model id | Set `MEAL_AI_MODEL` to a current id — no deploy needed |
| `User location is not supported` | Server IP is in the EEA/UK/CH | Move the service outside those regions. See [`incident-2026-07-gemini-eea-region.md`](incident-2026-07-gemini-eea-region.md) |

## 4. Dependency drift

`render.yaml` runs `pip install -r requirements.txt` on every build. `google-genai`
declares its own dependencies as **ranges**, so a rebuild months later can resolve a
`pydantic` or `httpx` the pinned SDK has never run against — failing 100% of calls with
a `TypeError` from inside `site-packages`.

`backend/requirements.txt` now pins those transitives explicitly. If you bump
`google-genai`, bump them together and re-run the suite. To confirm drift as a cause,
diff the `Successfully installed …` line between the last good deploy and the current one.

## 5. What the app already does for you

Before escalating, note these are automatic:

- **Retry until the deadline**, not for a fixed number of attempts
  (`MEAL_AI_DEADLINE_S`, default 60s). Gemini's overload 503 returns in ~150ms, so an
  attempt count would spend the whole budget in a second or two; a minute of jittered
  backoff capped at 8s buys roughly a dozen attempts spread across the outage.
- **Alternating model chain** (`MEAL_AI_FALLBACK_MODEL`, default `gemini-2.5-flash`):
  attempt two already lands on the other serving pool, since overload is per pool.
- **Per-attempt request timeout**, so a hung provider fails fast instead of pinning a worker.
- 429s are **never** retried — the correct remedy is the "try again in a minute" the user
  already sees.

So a single user report of one failure is expected noise. Sustained failure across users
is what this runbook is for.
