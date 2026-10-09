---
name: Trackaholic
description: A calorie and macro tracker that reads like a training computer's data page. Big numbers in fixed fields, calm by default, never shaming.
colors:
  ground: "#e4e7e1"
  field: "#eef0eb"
  ink: "#0f1210"
  ink-2: "#485049"
  rule: "#c3c9c1"
  track: "#cfd4cc"
  fill: "#0f1210"
  action: "#1747e0"
  action-ink: "#ffffff"
  plan: "#8c1d8c"
  label: "#f8f9f6"
  fact: "#1d6b3a"
  ground-dark: "#0b0e0c"
  field-dark: "#141815"
  ink-dark: "#e7ebe4"
  ink-2-dark: "#9ba49c"
  rule-dark: "#283029"
  track-dark: "#232924"
  fill-dark: "#e7ebe4"
  action-dark: "#7d9bff"
  action-ink-dark: "#0b0e0c"
  plan-dark: "#e88ae8"
  label-dark: "#050605"
  fact-dark: "#6fd394"
typography:
  display-number:
    fontFamily: "Mona Sans, system-ui, sans-serif"
    fontSize: "92px"
    fontWeight: 820
    lineHeight: 0.86
    letterSpacing: "-0.02em"
  field-number:
    fontFamily: "Mona Sans, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 780
    lineHeight: 1
    letterSpacing: "normal"
  row-number:
    fontFamily: "Mona Sans, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 760
    lineHeight: 1.2
    letterSpacing: "normal"
  title:
    fontFamily: "Mona Sans, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 750
    lineHeight: 1.25
    letterSpacing: "normal"
  body:
    fontFamily: "Mona Sans, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
  small:
    fontFamily: "Mona Sans, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
  label:
    fontFamily: "Mona Sans, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "0.09em"
  label-style-title:
    fontFamily: "Libre Franklin, Helvetica Neue, Arial, sans-serif"
    fontSize: "40px"
    fontWeight: 900
    lineHeight: 1
    letterSpacing: "-0.03em"
rounded:
  tag: "3px"
  control: "5px"
  log: "7px"
  sheet: "14px"
spacing:
  hairline: "2px"
  tight: "8px"
  row: "10px"
  block-y: "14px"
  block-x: "16px"
  block-x-wide: "28px"
components:
  button-primary:
    backgroundColor: "{colors.action}"
    textColor: "{colors.action-ink}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "42px"
  button-secondary:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "42px"
  log-button:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ground}"
    rounded: "{rounded.log}"
    padding: "0 20px"
    height: "50px"
  input:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "44px"
  chip-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ground}"
    rounded: "{rounded.control}"
    height: "36px"
  tag-your-food:
    textColor: "{colors.fact}"
    rounded: "{rounded.tag}"
    padding: "2px 7px"
---

# Design System: Trackaholic

## Overview

**Creative North Star: "The training computer's data page"**

Today reads like the data page of a sports watch or a cycle computer: a few big numbers in fixed places, readable at arm's length, mid-task, with one hand. Each number lives in a **field**. Fields are separated by thin rules and spacing, not by boxes, so the screen reads as one instrument rather than a stack of cards. Boxes are kept for things you can press.

The app is used in short bursts, many times a day: beside the kitchen scale in daylight, on the sofa at night. That scene decides the rest. It is calm and dense rather than decorative, it works in light and dark alike, and every number is set so it can be read at a glance.

The look holds two ideas from the brand. The **segmented gauge** (the calories display, distilled) is the app's signature shape, and it appears in the wordmark and the app icon. The **nutrition label** is the brand's playful side: it is in the wordmark, and anyone can switch the whole app into a black-and-white **Label** style.

**Key characteristics:**
- Big condensed numbers in fixed fields; small wide capital labels above them.
- Thin rules, not cards. Panels only where something is pressed or set apart.
- One action colour per palette, used only on things you can press.
- One **plan** colour, used only for targets, goals and projections, never for data.
- Going over a target is drawn calmly: the gauge fills past the target tick. No red, no shake.
- Light and dark in every palette, following the phone by default.

## Colors

Restrained: a tinted neutral ground, ink, one action colour and one plan colour. The default palette is **Daylight**. Seven more palettes (see Themes and palettes) change the ground tint, the action and plan colours, and the colour of the calories **band**.

### Primary
- **Action blue** (#1747e0 light / #7d9bff dark): primary buttons, links, "Due today", focus rings. Only on things that respond to a tap.

### Secondary
- **Plan purple** (#8c1d8c light / #e88ae8 dark): the target tick at the end of the calories gauge, goal lines and projections on charts. Never used for logged data.

### Tertiary
- **Fact green** (#1d6b3a light / #6fd394 dark): the "Your food" tag on AI results, marking values taken from the user's own saved foods rather than estimated.

### Neutral
- **Ground** (#e4e7e1 / #0b0e0c): the page. A display-glass grey-green in light; near-black in dark.
- **Field** (#eef0eb / #141815): inputs and set-apart panels.
- **Ink** (#0f1210 / #e7ebe4): text, numbers, filled gauge segments, the Log button.
- **Ink 2** (#485049 / #9ba49c): labels, units, secondary text. At least 6.5:1 on ground in both themes.
- **Rule** (#c3c9c1 / #283029): the hairlines between fields and rows.
- **Track** (#cfd4cc / #232924): unfilled gauge segments.
- **Label white** (#f8f9f6 / #050605): the ground of the nutrition-label object.

### Named Rules
**The Press Rule.** The action colour appears only on things that respond to a tap. If it isn't pressable, it isn't action-coloured.

**The Plan Rule.** The plan colour belongs to targets and goals only. Data is ink; the plan is purple (or the palette's plan colour).

**The No Red Rule.** Nothing turns red or alarming because a user ate more than their target. Going over is drawn with the same ink as going under. Error states use ink plus words, not colour alone.

## Typography

**Display, body and labels:** Mona Sans (with system-ui, sans-serif), one family with a width axis.
**Label style and wordmark:** Libre Franklin (with Helvetica Neue, Arial, sans-serif).

**Character:** Mona Sans does every job by changing width. Numbers are narrow and heavy, words are normal, small capital labels are slightly wide. Libre Franklin is the face of the real nutrition label and appears only where the label idea does.

### Hierarchy
- **Display number** (820, 92px phone / 132px desktop, line-height 0.86, width 75%): the calories headline on Today only.
- **Field number** (780, 30px, width 78%): secondary numbers in fields: eaten, protein, weekly rate.
- **Row number** (760, 20px, width 80%): kcal on meal rows.
- **Title** (750, 16px, width 112%): screen titles in the app bar and the date bar.
- **Body** (400, 15px, line-height 1.4): rows, descriptions, form text. Prose capped at about 70 characters per line.
- **Small** (400, 13px): captions, helper text, ranges.
- **Label** (650, 11px, letter-spacing 0.09em, uppercase, width 110%): field labels and section labels ("KCAL LEFT", "MEALS · 3").
- **Label-style title** (Libre Franklin 900, 40px phone / 56px desktop, letter-spacing -0.03em): the heading of a nutrition-label block.

### Named Rules
**The Fixed Digits Rule.** Every number uses tabular figures. Values change in place; nothing shifts sideways when a digit changes.

**The Sentence Case Rule.** Headings, buttons and labels are written in sentence case. The uppercase field labels are a typographic treatment of sentence-case text, not title case.

## Layout

One responsive layout. The same screens at every width, with different density and navigation placement.

- **Phone (under 900px):** a bottom tab bar (Today · Progress · Log · You), with the Log button in the middle. Blocks are full width, padded 14px vertically and 16px horizontally, separated by hairline rules.
- **Desktop (900px and up):** a 236px side rail (wordmark, Log button, tabs), and content in two columns (1.25fr / 1fr). On Today, the calories band spans the full width at the top. Meals go on the left, trackers on the right, and both columns run to the same bottom line, so content of different lengths never looks ragged. Blocks pad 28px horizontally.
- **Log panel:** a bottom sheet at 92% height on phones; a 480px right-side panel on desktop.
- **Settings-type screens** (You, the day in detail, meal screens) are a single column capped at 760px.
- **Spacing rhythm:** 8px between related controls, 10px inside rows, 14px/16px block padding. More space above a section title than below it.

## Elevation & Depth

Flat. There are no shadows at rest. Depth comes from tone: the ground, the slightly lighter field for inputs, the coloured calories band, and a scrim behind the Log panel. The only raised surfaces are the Log panel (sheet) and the toast, and both are separated by tone and position, not by shadows.

### Named Rules
**The Flat Rule.** No drop shadows on blocks, rows or buttons. If something needs to stand apart, change its ground, not its shadow.

## Shapes

Nearly square. Controls have a 5px radius, the Log button 7px, tags 3px, checkboxes 4px. The Log panel's top corners are 14px on phones. Gauges and meters are made of square segments with 2–3px gaps. Nothing is pill-shaped except the sheet's grab handle.

## Components

### The calories band (signature)
- **What:** the top of Today. A "KCAL LEFT" (or "KCAL OVER") label, the display number, "of 2,100 target", a 20-segment gauge with the plan-coloured target tick, then two fields: Eaten and Protein (with a 10-segment bar).
- **Colour:** the palette's band colour. In Daylight the band is the ground; in the other palettes it is a deep coloured panel with light ink.
- **Over target:** the gauge is full, the label reads "KCAL OVER", and one plain line reads "Over is fine. The week evens out." with a link to spread it.
- **Tap:** opens the day in detail, with calorie plans.
- **Carbs and fat:** when switched on, they are added as fields under protein. When off, nothing mentions them.

### Gauges and meters
- **Style:** square segments, filled in ink, unfilled in track. The calories gauge has 20 segments plus the target tick; protein and water have 10.
- **Never** rings. Progress is always segmented bars.

### Buttons
- **Shape:** 5px radius, 42px tall (40px minimum touch target, 44px preferred for primary actions).
- **Primary:** action colour fill, action-ink text.
- **Secondary:** transparent with a 1.5px ink border.
- **Ghost:** transparent with a 1.5px rule-coloured border (Undo, Cancel).
- **Log button:** ink fill, ground-coloured text, 7px radius, 50px tall. While an AI estimate runs it shows a spinner; when the estimate is ready it shows a dot and "Ready".
- **Disabled:** 45% opacity, no pointer.

### Chips
- **Style:** 36px tall, 1.5px rule border, 5px radius.
- **Selected:** ink fill, ground-coloured text.

### Blocks and rows
- **Blocks:** no border, no background. A hairline rule along the bottom, with an optional section label and value in the label style.
- **Rows:** at least 52px tall, with a chevron when they open something. Hairline rules between rows.
- **Meal rows:** time (13px, ink 2) · name and detail · kcal (row number), 56px minimum. Tapping one opens the meal screen (Edit, Log it again, Share as a code, Keep as a saved meal, Delete).

### Inputs
- **Style:** field ground, 1.5px rule border, 5px radius, 44px tall. Number inputs use the condensed bold number face.
- **Focus:** the border turns the action colour; keyboard focus also shows a 2px action-colour outline.

### Navigation
- **Tab bar (phone):** three tabs plus the central Log button. The current tab's icon is **filled** and its label bold, with a 2px ink marker that slides along the top edge.
- **Side rail (desktop):** the wordmark, the Log button, then the tabs. The current tab has a 3px ink bar on its left and a filled icon.

### Delete and Undo
- Deleting a meal returns to Today and leaves a struck-through line in its place, with an **Undo** button and a thin bar along the bottom that drains over **10 seconds**. Then the line folds away and the deletion is final. Undo puts the meal back where it was.

### AI estimate (Log panel)
- **While working:** the user's photos and note sit at the top. Below them are honest stages: "Sending 2 photos" with a real upload bar, then "Reading your note", "Using 1 of your saved foods" and "Estimating portions from the photos". There is no fake percentage. After a long wait the last stage reads "Still looking. This one's got layers." The panel can be closed; the Log button keeps working, and a toast says when the estimate is ready.
- **Result:** one row per item, with name, quantity source ("200 g from your note", "about 10 g, from the photo"), kcal and range. Items taken from saved foods show a **Your food** tag and "exact". One "Save N new foods to my library" row and one "Keep as a saved meal" row follow. The footer holds Back and "Save meal · 563 kcal".

### The nutrition-label object
- **Used:** everywhere in the Label style, and in the wordmark.
- **Anatomy:** a 2px ink border on label white; a heavy title; a 10px rule, then the calories row, a 5px rule, then the nutrient rows with 1px rules; a 10px rule, then fine print. All in Libre Franklin.

### Toasts
- Ink ground, ground-coloured text, 8px radius, above the tab bar on phones and bottom-right on desktop. They last 5 seconds and have a close button. One optional action ("View").

### Skeletons
- Track-coloured blocks with a slow shimmer, shown for at least 650 ms on first load of a data screen. No spinners in content.

## Do's and Don'ts

### Do:
- **Do** put every number in a field with a label above it, and use tabular figures.
- **Do** separate content with hairline rules and spacing before reaching for a panel.
- **Do** keep the action colour for pressable things and the plan colour for targets.
- **Do** design every screen's empty state, with the next step in plain words.
- **Do** check every new colour pair at 4.5:1 for text and 3:1 for non-text, in light and dark, in all eight palettes.
- **Do** keep touch targets at least 24px (WCAG 2.2), and 44px for primary actions.

### Don't:
- **Don't** use emoji as icons. Use the icon set.
- **Don't** use rings for progress.
- **Don't** use red, shaking or warning motion for going over a target.
- **Don't** wrap every block in a bordered card. That flattens the hierarchy the fields create.
- **Don't** add drop shadows or gradients.
- **Don't** put a small label or eyebrow above a heading as decoration. Field labels label numbers; headings stand alone.
- **Don't** show a target, chart or trend built on invented numbers. Show what unlocks it instead.

## Motion

Motion says what changed. Nothing moves for decoration. Animations are built with the Motion library (`animate`, `stagger`), loaded lazily, and wrapped so that the reduced-motion setting is respected everywhere.

**Tokens:**
- **Ease (default):** `cubic-bezier(0.16, 1, 0.3, 1)`, an exponential ease-out.
- **Fast:** 150ms (tab changes: a crossfade).
- **Base:** 240ms (most transitions).
- **Screen push and back:** 260ms; content slides 28px from the right on push, from the left on back, and fades in.
- **Log panel open:** spring, stiffness 380, damping 36. It rises from the bottom on phones and slides from the right on desktop. The scrim fades in over 200ms.
- **Log panel close:** 240ms, `cubic-bezier(0.4, 0, 1, 1)`.
- **Toast in:** spring, stiffness 420, damping 32, rising 18px.

**The catalogue:**
- **Rolling numbers:** when a value changes, only the digits that changed roll into place (0.45em, 320ms, staggered 40ms from the right). They roll up when the value rises and down when it falls.
- **Gauge fill:** newly lit segments light one after another (220ms each, 35ms apart).
- **First target:** after setup, the calories number counts up from zero (900ms) and the gauge draws in.
- **AI result:** rows arrive one by one (300ms, 90ms apart, rising 10px). The "Your food" tag snaps in with a small overshoot (scale 0.5 → 1.12 → 1).
- **Save a meal:** the panel drops away, the new meal row opens into the list (360ms) with a brief action-tinted highlight, the gauge fills and the numbers roll.
- **Delete:** the struck-through line draws its strike (350ms); the Undo bar drains linearly over 10 seconds; the line then folds closed (280ms).
- **Unlock:** a locked Progress section is replaced by its content (350ms), and its trend line draws itself (1.1s).
- **Charts:** a range change redraws the trend line (700ms) and grows the bars from the baseline.
- **Weekly review:** the checks appear one by one (80ms apart).
- **Once-a-day rewards:** ticking the last supplement pops the checkboxes in turn; reaching the water goal ripples the meter. Each shows once per day.
- **Server waking:** six segments light in sequence where a spinner would be.

**Reduced motion:** with the system setting on (or the in-app choice), only fades remain (120ms), loops stop, and numbers change instantly. The 10-second Undo window still applies.

**The Never Punish Rule.** No motion reacts to going over a target, missing a weigh-in or skipping a day.

## Iconography

- **Set:** Phosphor (MIT). Regular weight everywhere; the **fill** weight only for the current tab.
- **Size:** 22px default, 18px inside buttons and rows.
- **Weigh-in:** Phosphor has no bathroom scale, so this one icon is drawn on Phosphor's 256 grid at its 16-unit line weight:

```svg
<svg viewBox="0 0 256 256" fill="none" stroke="currentColor" stroke-width="16" stroke-linecap="round" stroke-linejoin="round">
  <rect x="40" y="40" width="176" height="176" rx="40"/>
  <path d="M84 112a52 52 0 0 1 88 0"/>
  <path d="M128 136l16-28"/>
</svg>
```

- **Mapping:** Today `calendar-check` · Progress `chart-line` · You `user` · Log `plus` · Water `drop` · Supplements `pill` · Voice `microphone` · Photo `camera` · Saved foods `book-open` · Edit `pencil-simple` · Log it again `copy` · Share `share-network` · Keep `star` · Delete `trash` · Back/next `caret-left`/`caret-right` · Close `x` · Done `check`.
- Every icon is decorative next to a text label, or has an accessible name.

## Brand

**Name:** Trackaholic, renamed from "Macros Calculator" on 2026-10-06.

### Wordmark
The name set in Libre Franklin 900, with the segmented gauge as its rule (nine lit segments, three unlit, and the plan-coloured target tick), and a nutrition-label line beneath: "Serving size … 1 habit". It sits at the top of the desktop rail (28px) and on the sign-in screen (40px).

```svg
<svg viewBox="0 0 212 68" role="img" aria-label="Trackaholic">
  <text x="0" y="34" font-family="Libre Franklin, Helvetica Neue, Arial, sans-serif" font-weight="900" font-size="40" letter-spacing="-1.4" fill="currentColor">Trackaholic</text>
  <g fill="currentColor">
    <rect x="0" y="42" width="15" height="8"/><rect x="17.4" y="42" width="15" height="8"/><rect x="34.8" y="42" width="15" height="8"/>
    <rect x="52.2" y="42" width="15" height="8"/><rect x="69.6" y="42" width="15" height="8"/><rect x="87" y="42" width="15" height="8"/>
    <rect x="104.4" y="42" width="15" height="8"/><rect x="121.8" y="42" width="15" height="8"/><rect x="139.2" y="42" width="15" height="8"/>
    <g opacity="0.22"><rect x="156.6" y="42" width="15" height="8"/><rect x="174" y="42" width="15" height="8"/><rect x="191.4" y="42" width="15" height="8"/></g>
  </g>
  <rect x="209" y="42" width="3" height="8" fill="#8c1d8c"/>
  <rect x="0" y="53" width="212" height="1" fill="currentColor"/>
  <text x="0" y="66" font-family="Libre Franklin, Helvetica Neue, Arial, sans-serif" font-size="12" fill="currentColor">Serving size</text>
  <text x="212" y="66" text-anchor="end" font-family="Libre Franklin, Helvetica Neue, Arial, sans-serif" font-weight="800" font-size="12" fill="currentColor">1 habit</text>
</svg>
```

Convert the text to outlines when the logo files are produced, so the mark does not depend on the font being installed.

### App icon
The gauge: five lit segments, two dark, and the target tick, centred as one group on near-black. It reads at 48px, survives Android's round crop (the group sits inside the central 80% safe zone), and has no letters to blur.

```svg
<svg viewBox="0 0 100 100" role="img" aria-label="Trackaholic">
  <rect width="100" height="100" fill="#0f1210"/>
  <g fill="#f2f4ef"><rect x="15.6" y="41" width="7" height="18"/><rect x="25.0" y="41" width="7" height="18"/><rect x="34.4" y="41" width="7" height="18"/><rect x="43.8" y="41" width="7" height="18"/><rect x="53.2" y="41" width="7" height="18"/></g>
  <g fill="#3a423c"><rect x="62.6" y="41" width="7" height="18"/><rect x="72.0" y="41" width="7" height="18"/></g>
  <rect x="81.4" y="37" width="3" height="26" fill="#e88ae8"/>
</svg>
```

## Voice

Wry, in small doses. Humour lives in quiet, good moments. Errors, going over a target, and anything about the body stay plain.

| Moment | What the app says |
|---|---|
| No meals yet today | Nothing logged yet. Suspiciously disciplined. |
| First weigh-in saved | First weigh-in. Your trend line starts now. |
| Weight trend unlocks | Seven weigh-ins. You've earned a trend line. |
| Daily burn unlocks | Enough data. Here's what you actually burn, measured, not guessed. |
| All supplement doses ticked | All doses done. Your future self says thanks. |
| Water goal reached | 2.5 litres. Fully hydrated, mildly smug. |
| AI estimate taking a while | Still looking. This one's got layers. |
| Weekly review, nothing to fix | Nothing to fix this week. Carry on. |
| Server waking up | Waking the server. It's on a free plan and naps a lot. About a minute; you can keep going. |
| Target set | Your target: 2,100 kcal and 150 g protein. A guide, not a rule. |
| Over the calorie target (plain) | Over is fine. The week evens out. Spread it across the next few days if you like. |
| A save fails (plain) | That didn't save. Check your connection, then try again. |
| Deleting an account (plain) | This deletes everything: meals, weigh-ins, foods. It can't be undone. |

## Themes and palettes

**Theme:** light and dark, following the phone's setting by default, with an Automatic / Light / Dark choice in You → Appearance.

**Style:** **Fields** (default, this document) or **Label** (every screen as a black-and-white nutrition label, in Libre Franklin). Palettes apply to Fields only.

**Palettes:** eight, chosen in You → Appearance. Every text pair measures at least 4.5:1 and every non-text pair at least 3:1, in both themes; the lowest is Citrus's action colour on its light ground, at 4.7:1. Daylight keeps the calories band on the ground; every other palette gives the band its own deep colour.

The exact tokens, as CSS custom properties. Each palette defines the full set for light; its dark block redefines the same names. In the band tokens, `band-ink` and the like apply to text and segments drawn on the band.

```css
/* Daylight (default) */
--ground: #e4e7e1; --field: #eef0eb; --ink: #0f1210; --ink-2: #485049; --rule: #c3c9c1; --track: #cfd4cc; --fill: #0f1210;
--action: #1747e0; --action-ink: #ffffff; --plan: #8c1d8c; --label: #f8f9f6; --fact: #1d6b3a;
--band: var(--ground); --band-ink: var(--ink); --band-ink-2: var(--ink-2); --band-track: var(--track); --band-fill: var(--fill); --band-plan: var(--plan); --band-rule: var(--rule);
/* Daylight dark */
--ground: #0b0e0c; --field: #141815; --ink: #e7ebe4; --ink-2: #9ba49c; --rule: #283029; --track: #232924; --fill: #e7ebe4;
--action: #7d9bff; --action-ink: #0b0e0c; --plan: #e88ae8; --label: #050605; --fact: #6fd394;

/* Ocean */
--ground: #dce5ee; --field: #e9eff5; --ink: #0b1a2a; --ink-2: #3d5064; --rule: #b5c4d2; --track: #c3d0dc; --fill: #0b1a2a;
--action: #0b57c4; --action-ink: #ffffff; --plan: #7a4300; --label: #f6f9fc; --fact: #0f6a46;
--band: #0e2a47; --band-ink: #f2f6fa; --band-ink-2: #a9bfd3; --band-track: #26486b; --band-fill: #f2f6fa; --band-plan: #ffb24a; --band-rule: #23436a;
/* Ocean dark */
--ground: #06101a; --field: #0c1825; --ink: #e6eef5; --ink-2: #93a8bb; --rule: #1b2b3b; --track: #172635; --fill: #e6eef5;
--action: #6fa8ff; --action-ink: #06101a; --plan: #ffb24a; --label: #03080d; --fact: #5fd6a2; --band: #0f2d4d; --band-rule: #23466e;

/* Sand */
--ground: #eae1d2; --field: #f3ede2; --ink: #1f1a14; --ink-2: #5a5044; --rule: #cdc1ae; --track: #d8cdbb; --fill: #1f1a14;
--action: #12595e; --action-ink: #ffffff; --plan: #8a2d5a; --label: #fbf8f2; --fact: #12595e;
--band: #2b2420; --band-ink: #f5ede1; --band-ink-2: #c6b6a2; --band-track: #4b4038; --band-fill: #f5ede1; --band-plan: #f2a6cb; --band-rule: #463b33;
/* Sand dark */
--ground: #14110d; --field: #1c1813; --ink: #efe6d8; --ink-2: #ab9e8c; --rule: #2e281f; --track: #2a241c; --fill: #efe6d8;
--action: #5cc6c9; --action-ink: #14110d; --plan: #f2a6cb; --label: #0a0806; --fact: #5cc6c9; --band: #2e2621; --band-rule: #4a3f36;

/* Berry */
--ground: #ecdfe7; --field: #f5ecf1; --ink: #22101c; --ink-2: #5d4555; --rule: #d1bbca; --track: #dccad6; --fill: #22101c;
--action: #8c1a5a; --action-ink: #ffffff; --plan: #0d6a64; --label: #fcf7fa; --fact: #0d6a64;
--band: #3a1430; --band-ink: #fbeef6; --band-ink-2: #d6b0c8; --band-track: #5c2b4f; --band-fill: #fbeef6; --band-plan: #7fe0d6; --band-rule: #57284b;
/* Berry dark */
--ground: #120a10; --field: #1b1018; --ink: #f3e6ee; --ink-2: #b399a9; --rule: #2e1d29; --track: #2a1a25; --fill: #f3e6ee;
--action: #ff8fc8; --action-ink: #120a10; --plan: #7fe0d6; --label: #0a0509; --fact: #7fe0d6; --band: #3d1633; --band-rule: #5c2c50;

/* Mono */
--ground: #e7e7e7; --field: #f1f1f1; --ink: #111111; --ink-2: #4a4a4a; --rule: #c8c8c8; --track: #d3d3d3; --fill: #111111;
--action: #111111; --action-ink: #ffffff; --plan: #b0136e; --label: #fafafa; --fact: #1d6b3a;
--band: #111111; --band-ink: #f2f2f2; --band-ink-2: #a8a8a8; --band-track: #333333; --band-fill: #f2f2f2; --band-plan: #ff6fb5; --band-rule: #2e2e2e;
/* Mono dark */
--ground: #0c0c0c; --field: #161616; --ink: #ededed; --ink-2: #a3a3a3; --rule: #2c2c2c; --track: #262626; --fill: #ededed;
--action: #ededed; --action-ink: #0c0c0c; --plan: #ff6fb5; --label: #050505; --fact: #6fd394; --band: #1c1c1c; --band-rule: #333333;

/* Ember */
--ground: #e6e4e3; --field: #f0eeed; --ink: #141212; --ink-2: #4d4847; --rule: #c9c5c3; --track: #d4d0ce; --fill: #141212;
--action: #b3261e; --action-ink: #ffffff; --plan: #1f5fa8; --label: #faf9f8; --fact: #1d6b3a;
--band: #1a1717; --band-ink: #f4f1f0; --band-ink-2: #b0a9a7; --band-track: #3a3434; --band-fill: #f4f1f0; --band-plan: #7fb2ff; --band-rule: #332d2d;
/* Ember dark */
--ground: #0e0c0c; --field: #171414; --ink: #efeceb; --ink-2: #a9a2a0; --rule: #2d2828; --track: #282323; --fill: #efeceb;
--action: #ff5a4e; --action-ink: #0e0c0c; --plan: #7fb2ff; --label: #070606; --fact: #6fd394; --band: #1d1919; --band-rule: #3a3333;

/* Citrus */
--ground: #f3f3ee; --field: #fbfbf7; --ink: #1a1c14; --ink-2: #50544a; --rule: #d6d7cd; --track: #dfe0d6; --fill: #1a1c14;
--action: #c2410c; --action-ink: #ffffff; --plan: #2f7d32; --label: #fdfdfa; --fact: #2f7d32;
--band: #24561f; --band-ink: #f6fbf2; --band-ink-2: #c3dbbd; --band-track: #3f7339; --band-fill: #f6fbf2; --band-plan: #ffb067; --band-rule: #386a32;
/* Citrus dark */
--ground: #0f110c; --field: #171a12; --ink: #eef0e6; --ink-2: #a4a99a; --rule: #2a2e23; --track: #252a1e; --fill: #eef0e6;
--action: #ff9a4d; --action-ink: #0f110c; --plan: #8fd88a; --label: #070806; --fact: #8fd88a; --band: #1f4a1b; --band-rule: #2f6229;

/* Violet */
--ground: #e6e2ee; --field: #f0edf5; --ink: #17122a; --ink-2: #4f4766; --rule: #c9c1d8; --track: #d5cee2; --fill: #17122a;
--action: #5b2fc9; --action-ink: #ffffff; --plan: #9a4508; --label: #faf9fc; --fact: #1d6b3a;
--band: #2a1a5e; --band-ink: #f4f0ff; --band-ink-2: #bfb2e6; --band-track: #45358a; --band-fill: #f4f0ff; --band-plan: #ffb067; --band-rule: #3f3080;
/* Violet dark */
--ground: #0d0a17; --field: #151122; --ink: #ece8f7; --ink-2: #a49cbc; --rule: #2a2440; --track: #241e38; --fill: #ece8f7;
--action: #a98bff; --action-ink: #0d0a17; --plan: #ffb067; --label: #06050b; --fact: #6fd394; --band: #2b1b60; --band-rule: #46368a;

/* Label style (palettes do not apply; it sets every token a palette sets, so none leaks through) */
--ground: #e9ebec; --label: #ffffff; --ink: #000000; --ink-2: #3f4245; --track: #d4d7d9; --action: #000000; --action-ink: #ffffff; --field: #ffffff; --rule: #000000; --fill: #000000; --plan: #000000; --fact: #000000;
--band: var(--label); --band-ink: var(--ink); --band-ink-2: var(--ink-2); --band-track: var(--track); --band-fill: var(--fill); --band-plan: var(--plan); --band-rule: var(--rule);
/* Label style dark */
--ground: #161718; --label: #000000; --ink: #ffffff; --ink-2: #c4c7ca; --track: #3a3c3e; --action: #ffffff; --action-ink: #000000; --field: #000000; --rule: #ffffff; --fill: #ffffff; --plan: #ffffff; --fact: #ffffff;
```
