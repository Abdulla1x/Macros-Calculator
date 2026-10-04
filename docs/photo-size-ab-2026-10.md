# Picking a photo size with an A/B instead of a hunch

**3–4 October 2026 · shipped in PR #71**

Meal photos used to be uploaded at full size, 2–8 MB each. The plan was to shrink
them on the phone first, to **1024 px**, because "the model downsamples them
anyway". That plan was measured before it shipped, and it was wrong twice: the
saving it promised doesn't show up on the AI bill, and 1024 px changed what the
model answered. The app ships **1536 px** instead.

| | |
|---|---|
| Click to answer, real 2.7 MB photo, ~2 Mbit/s uplink, instant stand-in model | 11.4 s → **2.1 s** |
| Bytes per photo | 2–3 MB → **~130–240 KB** (11–14x) |
| Location data sent to the AI provider | every photo → **none** |
| Prompt tokens per photo, any size | **1,870** (unchanged) |
| Size the plan called for | 1024 px — **rejected** |

---

## Why shrink at all

Three costs, all real:

- **Bandwidth.** The free hosting plan allows 5 GB of outbound traffic a month.
  98% of it was photos being forwarded to the model — about 3 users at the
  author's logging intensity would have filled it.
- **Upload time** on mobile data, which the app's progress bar was already
  measuring as its own phase.
- **Server memory.** Each attempt to call the model briefly holds ~6–7x the
  photo payload on a 512 MB instance; an earlier outage was a memory exhaustion
  on exactly that path.

The reasoning for *how much* to shrink was "the model downsamples anyway, so
the extra pixels buy nothing". That is two claims — that bigger photos cost
more, and that the model can't use the extra pixels — and both were testable.

## The first claim was false: the bill doesn't change

Google's docs say Gemini 3 bills an image at a fixed budget (1,120 tokens at the
default resolution) regardless of its pixel count. Measured: the same photo cost
**1,870 prompt tokens** at full size, at 1536 px and at 1024 px. So shrinking
saves bandwidth, seconds and memory — but not one cent of AI cost. That removes
the main reason to go as small as possible.

## The second claim needed an experiment

Google doesn't publish the pixel size its fixed budget corresponds to, so
whether 1024 px throws away detail the model would have used can't be looked
up. It had to be measured.

**The setup** (`backend/scripts/compare_estimates.py`):

- **Seven real meal photos** from a phone: five plates and two nutrition labels
  (fine print is where lost detail would show first).
- Each sent at **full size, 1536 px and 1024 px**, resized by the *shipped*
  browser code running in headless Chromium — testing a copy would prove nothing
  about the real thing.
- **Photo only, no description.** This app's best estimates come from typed
  weights; with them in the request, every size converges on the text and any
  image effect disappears.
- **The app's exact request** — same prompt, schema and temperature, via a
  shared `analysis_config()` — but **no fallback model**, so a switch to a
  different model can't masquerade as a size effect.
- **Every combination twice.** The model runs at temperature 0.2, so the same
  photo twice gives two answers. A size that moves the estimate by 40 kcal
  means nothing until it's compared with how far the *same* size moves between
  two identical calls. Calls were interleaved, so a model having a slow or odd
  hour affects every size alike.
- **The decision rule was written down before the run:** take 1024 if its
  difference from full size stays within that run-to-run noise, no photo moves
  more than ~10%, and the ranges don't widen. Otherwise test 1536 by the same
  rule.

## Results

Calorie estimates, in the order the runs came back:

| Photo | Full size | **1536 px** | 1024 px |
|---|---|---|---|
| Plate A | 255, 265 | **240, 240** | 295, 275 |
| Plate B | 350, 260 | **390** | 458, 465 |
| Label 1 | 138, 138 | **138** | 138, 138 |
| Label 2 | 218, 182 | **182, 182** | 218, 182 |
| Plate C | 405, 425 | **430, 458** | 520, 430 |
| Plate D | 550, 522 | **550** | 620, 611 |
| Plate E | 510, 540 | **520** | 490, 575 |

| Against full size | 1024 px | 1536 px |
|---|---|---|
| Median difference | 9.6% | 7.0% |
| Largest difference | +51% | +28% |
| Within the run-to-run noise | 4 of 7 | 5 of 7 |
| Uncertainty range width | ×1.13 | ×1.04 |
| Direction of the differences | **5 of 5 higher** | 3 lower, 3 higher |

**1024 failed the rule.** The clearest case is plate B: its two 1024 runs
agree with each other (458, 465) and both sit well above both full-size runs.
And every one of 1024's non-zero differences went the same way — higher. By
coin-flip odds, five out of five in one direction happens about 1 time in 16
by chance; not proof, but not the pattern of noise either.

**1536 passed.** Its differences fall on both sides of the full-size answer,
its ranges stay the same width, and where it was run twice it mostly repeated
itself exactly (240, 240 and 182, 182). Plate B is still its weakest result —
but that's also the photo whose *full-size* estimate swung by 90 kcal between
two identical calls, so it is the noisiest baseline in the set.

**The labels were identical at every size.** Text survived 1024 px; it was the
plates — portion and texture — that shifted.

The likely explanation, which this experiment supports but doesn't prove: the
model's own resize keeps more than 1024 px of detail, so an aggressive resize
before upload discards information it would have used. 1536 is also the size
at which the older fallback model's 768 px tiles are native.

## What the numbers do and don't say

- **This measures agreement with the full-size answer, not accuracy.** "1024
  read 51% higher" means it disagreed with what the same model says when it
  sees the original photo — not that it was 51% wrong. Nobody weighed these
  meals for this test. The defensible claim is narrower: *shrinking to 1536
  doesn't change the model's answer; shrinking to 1024 does, and in one
  direction.*
- **Seven photos from one person, one model.** Enough to reject a size that
  leans the same way every time; not enough to quote a general effect size.
- **4 of the 14 planned second runs at 1536 never happened.** A free-tier daily
  quota and a Gemini overload ran out the clock. The decision was made on a
  complete first pass plus three consistent repeats.
- **The fallback model wasn't tested.** In production the older model often
  answers when the main one is overloaded; 1536 being native for its tiles is
  reasoning from its documentation, not a measurement.

## What shipped

- **`lib/photoSize.ts`** — the sizing rules, free of the DOM so they can be unit
  tested — and **`lib/photoDownscale.ts`**, the canvas work.
- **It never blocks an upload.** Anything that goes wrong falls back to
  sending the original photo, as before:
  - a format the browser can't decode (HEIC in Chrome on Android);
  - an encoder that quietly returns PNG instead of JPEG;
  - a re-encode that comes out *bigger* than the original;
  - a decoder that hangs for more than 15 s.
- **Details that are easy to get wrong:**
  - EXIF rotation is applied, so photos don't arrive sideways;
  - transparency is filled white instead of black;
  - small photos are never upscaled;
  - photos decode **one at a time**, because four 12 MP photos decoded at
    once is ~200 MB on a low-end phone.
- **Location data is stripped as a side effect.** Re-encoding writes no EXIF.
  All seven originals in the test carried GPS coordinates; none of the shrunk
  copies do.
- **The work starts when a photo is picked**, so it's usually done before the
  Analyze button is pressed.
- **The frontend got unit tests without a test framework.** `npm test` compiles
  them with the project's own TypeScript compiler and runs them on Node's
  built-in runner. Each sizing rule was broken on purpose to confirm its test
  actually fails.
- **A server log line** — `analysis input: images=N image_bytes=M` — proves it
  in production. First readings:
  - 127 KB from a desktop browser;
  - 187 KB from a fresh phone camera photo;
  - server memory steady at 165–168 MB.

## Three things worth remembering

1. **"The provider downsamples anyway" was a guess wearing a fact's clothes.**
   It was half right — the bill doesn't depend on size — and half wrong: the
   pixels before the provider's resize still mattered.
2. **Measure the noise before the effect.** Without the repeats, plate B's
   full-size runs alone (350 vs 260) would have made any single comparison
   meaningless — and 1024's consistent lean would have been invisible.
3. **Write the decision rule before you look.** It is what made "the size we
   planned failed" an outcome rather than a debate.

The same experiment surfaced something bigger: the free AI tier allows far
fewer requests per day than the app was configured for. That one gets its own
note once it's fixed.
