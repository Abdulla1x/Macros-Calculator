# Incident: AI meal analysis down for three days

**26 July 2026 · resolved**

Every AI macro estimate failed for roughly three days. The API key was valid, the
model existed, the payload was well-formed, and the exact deployed code worked
perfectly from a laptop. The server was simply in the wrong country.

| | |
|---|---|
| Time to root cause | ~3 days |
| Hypotheses ruled out | 6 of 7 |
| Rows migrated | 225 |
| Data lost | 0 |

---

## It started as a feature request that was already built

The ask was to let the AI estimate macros from text or voice without requiring a
photo. Reading the code showed that text-only input **already worked and always
had**: the backend accepted a missing image, the 422 only fired when image *and*
text were both absent, and a passing test posted a description with no image.

It looked image-only because **the whole feature was down**, photo and text alike.
The message on screen — *"AI analysis failed"* — was the catch-all 502, not the
missing-image 422. So the job changed: find out why every request was failing.

## Root cause

```
google.genai.errors.ClientError: 400 FAILED_PRECONDITION
{'error': {'code': 400,
           'message': 'User location is not supported for the API use.',
           'status': 'FAILED_PRECONDITION'}}
```

Google's Terms of Service permit **only Paid Services when serving users in the
EEA, Switzerland or the UK**, and "user location" is decided by the IP a request
arrives from — [Google's own clarification](https://discuss.ai.google.dev/t/clarification-on-only-paid-services-for-eea-ch-uk/107860)
states *"IP is the primary signal that will be considered towards determining
user's location."* A backend in Frankfurt presents an EEA address, so Google read
the **server itself** as an EEA user and refused the free tier before the request
reached the model.

The distinction matters and is easy to get wrong: this is not a rule about where
*developers* may work. It is a rule about who may be *served* on the free tier,
enforced by request IP.

Two things made this expensive to find, and both were fixed:
`backend/app/routers/ai.py` caught every exception and **logged nothing**, and
`MEAL_AI_MODEL` — the one environment variable that swaps models without a
deploy — wasn't documented anywhere.

### Why the documentation doesn't warn you

Google's regional documentation actively suggests Frankfurt is fine:

- [`available-regions`](https://ai.google.dev/gemini-api/docs/available-regions)
  lists Germany, the UK, Switzerland and every EEA country as supported, with
  **no free-versus-paid distinction anywhere on the page**.
- [`billing`](https://ai.google.dev/gemini-api/docs/billing) states that "we make
  the free tier and paid tier available in many regions" and links to that same
  list.

The restriction lives in the Terms of Service, which neither page flags. Reading
the official availability documentation and concluding a Frankfurt deployment is
supported is a reasonable inference — it is simply wrong.

---

## Then how did it work before?

This is the part the investigation never fully closed. The service was in
Frankfurt from the day it was deployed and that setting never changed. So "the
region" explains why calls were failing; it does not, on its own, explain why the
same region was fine for two weeks and then wasn't.

### Established

- The backend ran in Frankfurt from deployment and the feature demonstrably
  worked — there are successful analyses stored from that period.
- The region was never changed; it was set once at creation and read back
  unchanged from the dashboard.
- Failures arrived as `400`s, and by the time they were noticed every request was
  failing.
- Moving to Ohio fixed it immediately, with no change to the key, the model, or a
  single line of application code.
- The restriction is Google's **documented, long-standing position** — only Paid
  Services may serve EEA/CH/UK users, with IP as the signal. Established after
  the fact: neither the error message nor the regional availability page says so.

### Most likely

Enforcement of an existing rule changed during that window, rather than the rule
itself appearing. It is the only explanation consistent with all the facts above:
nothing on this side moved, and a pure region change fixed it outright.

### Never proven

- No announcement was found pinning when enforcement began, so the date is
  **inferred from when errors appeared, not confirmed**. Since the policy
  pre-dates the outage, why it only started biting this deployment in late July
  remains unexplained.
- Alternatives were never eliminated — a change in how the account was classified,
  or in how that server's traffic was seen, would look identical from outside.
- Testing this is now harder by choice. The Frankfurt service was deleted once
  Ohio was verified, so reproducing the failure would mean rebuilding it. That is
  the right trade for a working app, and worth naming as a deliberate cost rather
  than an oversight.

The practical upshot doesn't change. But **"it worked yesterday" was never
evidence that nothing had changed** — what changed was on the provider's side,
which is precisely the category of change no amount of reading your own code will
reveal.

---

## Six dead ends

Everything plausible pointed somewhere else, because the failure was invisible
from every angle checked first. The same key and the same code worked flawlessly
from a laptop in the UAE — only the *server's* location mattered, and nothing in
the app reported location.

| Hypothesis | Ruled out by |
|---|---|
| ~~Missing-image validation~~ | The text-only path already worked, with a passing test to prove it |
| ~~Model deprecation~~ | Real — `gemini-2.5-flash` was retiring — but migrating to 3.5 changed nothing |
| ~~Invalid or mangled API key~~ | The key listed 56 models fine. A bad key returns **400**, not 401 — the same status as the real error |
| ~~Malformed request payload~~ | Contents and response schema verified offline; both transformed cleanly |
| ~~Quota exhaustion~~ | About 20 calls a day against a ceiling of roughly 1,500 |
| ~~Broken deployed code~~ | The exact deployed commit was checked out locally and worked with the production key |

**→ The server's region.** Frankfurt presents an EEA IP, which Google treats as an
EEA *user* — and those may only be served on paid tiers. Confirmed by the settings
page, then by the log line above.

The third row is the one that cost the most time. Because an invalid key and a
blocked region both return `400`, the status code alone could not separate them —
only the message body could, and the message body was being discarded.

---

## The fix: move the backend out of the EEA

Enabling billing would have worked instantly, and was rejected for a sound reason:
signup is open and there was no global spend cap, so abuse cost was unbounded —
and budget alerts notify rather than cap. **Free fails safe; paid fails
expensive.**

| | Region | State |
|---|---|---|
| Was | Frankfurt (EU Central) | Every call refused |
| Now | Ohio (US East) | API and database co-located |

1. `pg_dump` of the Frankfurt database — 21 KB, verified against live row counts
2. New database project in **AWS US East 2 (Ohio)**, restored, counts matched
   exactly (5 users / 180 meals / 25 foods / 5 settings / 10 analyses)
3. New web service in **Ohio**, deliberately co-located so queries stay local
4. `JWT_SECRET` carried across, so no one was logged out
5. Frontend repointed and rebuilt; old service and database deleted only after
   verification

```console
$ curl -X POST $API/api/ai/analyze -F 'text=two eggs and toast'

{"meal_name": "Two eggs and toast",
 "calories": {"low": 300, "estimate": 360, "high": 430},
 "protein":  {"low": 15,  "estimate": 18.5, "high": 22}, ... }
```

The first estimate from Ohio. One response proving four things: the data
migrated, the secret matched, the queries ran, and Google accepted the request.

> **What this did and did not solve.** It fixed the *technical* block: calls now
> originate from Ohio, so Google sees a US IP. It did not change the Terms of
> Service position, which is about who the app **serves**. This app is publicly
> reachable, so an EEA user signing up would be served on the free tier —
> invisible to enforcement, because Google only ever sees the server's IP, but a
> contractual question rather than a technical one. Immaterial at five users;
> relevant if it ever grows.

---

## Two more failures, both wearing a healthy disguise

Each had the same shape as the original — a layer that looked completely fine
sitting directly on top of the broken one.

**`relation "users" does not exist`** — the pooled database endpoint reports an
empty `search_path`, so unqualified queries failed while the connection, database
and user were all correct. Switching to the direct endpoint fixed it, which turned
out to be what the old service had used all along.

**`Failed to fetch`** — the Content Security Policy in `frontend/vercel.json`
hard-coded the old API origin, so the browser refused every request *before
sending it*. Health checks, CORS and preflight all passed from the terminal,
because CSP exists only in browsers. The blocked request never appeared in the
network tab.

---

## Remediation: what the outage actually changed

**Provider errors that name themselves.** The direct fix for the thing that made
this take days. A provider-neutral error hierarchy in
`backend/app/services/meal_ai.py` maps failures to distinct statuses — 429, 503,
502 — and logs the provider's own words. The next failure of this kind announces
its cause instead of vanishing into a bare `except`.

**A ceiling on spend.** A consequence of choosing not to enable billing. Per-user
limits bounded one account; nothing bounded the total, so repeated signups
multiplied the allowance without limit. `AI_GLOBAL_DAILY_LIMIT` now counts every
call across every account — which is also what would make the paid tier safe,
should that trade ever look worth making.

**A refund hole, closed.** Found while building the cap. Every failure used to
hand the quota slot back, which made input that reliably produced garbage an
uncapped free path to the provider. Only failures that happen *before* the model
runs are refunded now.

> **Shipped alongside — not caused by the incident.** Voice notes became editable
> text: transcription now runs the moment recording stops and drops the text into
> the description box, where it can be corrected before it becomes an estimate.
> This was a separate feature request made after the outage was resolved, and is
> recorded here only so the session's work is complete.

---

## Three things worth remembering

**Test from where the failure actually happens.** Terminal checks could never have
caught the CSP block; a browser could never have seen Google refusing a German
server. Three separate failures here hid behind a layer that looked perfectly
healthy from the wrong vantage point.

**Model retirement is an operational risk, not a footnote.** Models get retired on
a schedule, sometimes ahead of it. The model id is overridable at runtime via
`MEAL_AI_MODEL`, so swapping it takes a dashboard edit rather than a deploy.

**Transcription will invent words for silence.** One second of silence came back
transcribed as `"one"`, despite an explicit instruction to return nothing. Very
short recordings are now discarded client-side — and showing the transcript before
the estimate means anything stray is visible and deletable, which is precisely the
point of that design.

---

## What shipped

| Commit | What it did |
|---|---|
| `ddbec8d` | Diagnosable provider errors, model migration, voice notes |
| `4ff3611` | Allow the new API origin in the CSP — the fix for "Failed to fetch" |
| `248f5c4` | Pin the deployment region so this cannot silently recur; drop the retired origin |
| `73fe81f` | Transcribe voice notes to editable text; add the global daily cap |

16 files · +1,032 / −187 · 134 backend tests passing · types and build clean.

---

## Sources

- [Only Paid Services for EEA/CH/UK — clarification](https://discuss.ai.google.dev/t/clarification-on-only-paid-services-for-eea-ch-uk/107860)
  — Google's own statement that the rule is about end-user location, with IP as
  the deciding signal
- [Gemini API available regions](https://ai.google.dev/gemini-api/docs/available-regions)
  — lists every EEA country as supported, without distinguishing tiers
- [Gemini API billing](https://ai.google.dev/gemini-api/docs/billing)
  — free and paid tiers "available in many regions"

The restriction was checked against these pages in July 2026. It is a policy, not
a technical constant — re-check before relying on any of it.

