# Product

This file records what the product is, who it serves and what it must keep true. How it looks lives in [DESIGN.md](DESIGN.md).

## Platform

web (an installable PWA, used mostly on phones; one responsive layout serves every width)

## Users

**Primary: careful trackers.** People who weigh their food, log many times a day and want the numbers to be right. The reference user logs about 6.5 meals a day, 59 days out of 60. They type the weighed grams, add a voice note describing the ingredients, attach photos, and check the estimate before saving. They also weigh in every day and log water and supplements on most days.

**Also served: the newcomer on day one.** Three strangers signed up in September 2026 and none logged a single thing. The loss is entirely at first use, so the first session has to work for someone who has never tracked before: set a target, log one meal, see it count. Careful tracking is where the product goes deep; it is not a prerequisite for starting.

## Product Purpose

Trackaholic is a calorie and macro tracker that makes logging food fast enough to do every time and honest enough to trust. Success means a new user logs a first meal in their first session and keeps logging. For an established user, it means the day's numbers, the weight trend and the weekly review are right without extra work.

## Positioning

AI photo logging stopped being unusual in 2026; MacroFactor, MyFitnessPal, Cronometer and PlateLens all ship it. Trackaholic stands on two things, each owning its own screens:

- **Your foods, the AI's eyes** (the Log panel). A voice note becomes editable text *before* anything is estimated, so a misheard word is a typo to fix rather than a wrong number to catch. Your saved foods supply the macros as facts, and the AI judges only the portion. Estimates come as ranges, not false precision.
- **A guide, not a rule** (Today and Progress). Targets flex: calories can move between days, and daily burn is measured from your own weigh-ins and intake. Going over is normal and is never treated as failure. Nothing nags.

It is also free and open source (MIT).

## Operating Context

- Logging happens in short bursts on a phone, often one-handed, at a kitchen counter, a desk or a table, in daylight and late at night.
- AI estimates take time: about 19 s at the median and 43 s at the 95th percentile. The estimate must survive moving around the app while it runs.
- The free-tier server sleeps when idle and takes about 50 s to wake. The app must stay usable and honest about it while that happens.
- Weekly habits: the weight trend and nutrition charts are looked at about once a week. The weekly review and the AI-accuracy page are nice to have.

## Capabilities and Constraints

- **Structure (fixed 2026-10-02):**
  - three tabs, Today · Progress · You, with Log as a button in the middle of the tab bar (top of a side rail on desktop);
  - Today puts calories first, then meals, then one full-width card per tracker;
  - Progress holds the weight trend and nutrition on one shared range control;
  - You holds every setting.
- **How meals are logged:** AI estimates are about half of meals; saved meals and recent meals carry most of the rest. Manual entry, Open Food Facts lookup and meal codes remain.
- **Trackers:**
  - **On by default:** the weigh-in only.
  - **Added by the user:** water, steps and supplements.
  - **No users yet:** steps and calorie plans have never been used on any account, so they stay out of the way.
- **Macros:** calories and protein are always tracked. Carbs and fat are opt-in, asked once at setup, and invisible when off.
- **First-use setup:** height, birth year, today's weight (which counts as the first weigh-in), and a goal (lose, maintain or gain). For lose or gain it asks how fast: 0.25, 0.5 or 0.75 kg a week, or the user's own figure. Goal weight is optional. A live line shows the resulting daily calories before the user confirms.
- **No invented numbers:** no target is shown until the user sets one. Features that need history show how close they are to unlocking instead of an empty chart.
- **Appearance:** light and dark follow the phone by default, with an Automatic / Light / Dark choice. There are eight colour palettes, and a second style, **Label**, which turns every screen into a black-and-white nutrition label.
- **Weigh-ins are editable:** today's from the Today card, any day's from the weigh-in history in Progress.
- **Notifications:** in-app only. No push notifications.
- **Units:** kg or lb.

## Brand Commitments

- **Name:** Trackaholic (domain `trackaholic.app`), replacing "Macros Calculator"; the rename lands as its own step. The name winks at compulsive tracking, so the product must never act like it rewards compulsion.
- **Look:** recorded in [DESIGN.md](DESIGN.md). The wordmark joins the two brand ideas: the segmented calories gauge and the nutrition label ("Serving size: 1 habit").
- **Voice: wry, in small doses.**
  - Humour lives in quiet moments: empty states, unlocks, the weekly review, the wordmark.
  - Numbers, errors and anything about health stay plain.
  - Example: "Nothing logged yet. Suspiciously disciplined."
- **Never strict or shaming:**
  - no red alarms for going over;
  - no motion or copy that punishes;
  - over-target states offer a way forward, not a verdict.
- **Sentence case** for every heading, label and button.
- **Gamification is an open question.** Streaks, leaderboards, friends and achievements are under consideration for later, with no rules decided yet. Whatever is decided has to fit "never strict or shaming". The points raised so far, to weigh when it is decided:
  - classic streaks reset to zero, and in a food tracker a missed day is often a bad day;
  - leaderboards on weight or calories reward eating less;
  - friends means sharing health data.

## Evidence on Hand

- Real usage figures from the reference account (above), measured 2026-10-02.
- Estimate accuracy is measured per user against what they actually saved, and the app refuses to report a figure when the evidence is too thin. Accuracy figures from the reference account describe weighed, voice-described meals and must never be quoted as a general claim.
- Absent, and not to be fabricated: testimonials, user counts, accuracy benchmarks, press, pricing.

## Product Principles

1. **Daily things are one tap from Today.** Weekly things live in Progress, occasional things in You.
2. **Honest over impressive.** Ranges, "not enough data yet" and "the server is waking" beat a confident wrong answer.
3. **The user's own data is the authority.** Saved foods are facts, the AI estimates only what it can see, and every estimate is reviewable before it is saved.
4. **Calm by default.** One headline number, little text, details behind a tap.
5. **First use is the product.** Every screen has a designed empty state that says what to do next.

## Accessibility & Inclusion

- WCAG 2.2 AA:
  - axe stays at 0 violations;
  - touch targets are at least 24 px (44 px preferred for primary actions);
  - focus is visible;
  - text and non-text contrast pass in every theme shipped.
- Motion respects the reduced-motion setting everywhere.
- Every icon has a text label or an accessible name.
- Numbers use tabular figures so they don't shift as they change.
