"""In-app announcements: committed release notes plus a live status banner.

Two different needs share one endpoint because they share one place in the UI:

* **Release notes** are content, so they live here in code. Adding one needs a
  deploy, which is the right cost for "here's what's new".
* **The status banner** is an incident tool, so it comes from an env var read on
  every request. An outage notice has to be postable from the Render dashboard
  without waiting on a build — the same escape hatch MEAL_AI_MODEL has.

Deliberately no database table: the notes are the same for every user, and
"which ones have I read" is a per-device preference the frontend keeps in
localStorage.
"""
import os

from .schemas import Announcement

STATUS_BANNER_ENV = "STATUS_BANNER"

# Newest first — the frontend shows them in this order and treats the first id
# as the one to mark as seen. Ids are stable strings, never renumbered: they're
# the localStorage keys that remember a user already dismissed a note.
ANNOUNCEMENTS: list[Announcement] = [
    Announcement(
        id="2026-08-26-estimate-accuracy",
        date="2026-08-26",
        title="The app now keeps score of its own estimates",
        body=(
            "Every AI meal estimate has always come with a range -- "
            "\"~580 kcal (500-680)\" -- and until now nothing had ever "
            "checked whether the range was any good. The Analytics page has a "
            "new section that checks it, against your own meals.\n\n"
            "**It measures against what you saved, not against a scale.** If "
            "you corrected an estimate before saving, the app compares the two "
            "and asks whether your number fell inside the range it showed you. "
            "That is honestly described as how far you moved its number, not "
            "how wrong it was -- unless you weighed the food, your correction "
            "is an estimate too.\n\n"
            "**Saving an estimate untouched proves nothing, so it is not "
            "counted.** If you accept a number as-is, the saved value *is* the "
            "estimate, so of course it sits inside its own range. Counting "
            "those would produce a score near 100% that measures nothing but "
            "its own definition. Only the meals you actually corrected can "
            "test the range, so those are counted separately -- and on most "
            "accounts there will be far fewer of them than you would expect.\n\n"
            "**Where there isn't enough to say, it says so instead of "
            "guessing.** Each macro needs ten corrections before a percentage "
            "appears; below that you get the count and how many more are "
            "needed. Calories and protein fill up at different rates, so one "
            "may be answering while the other is still waiting.\n\n"
            "**Every percentage arrives with a range of its own.** A rate "
            "built from eleven corrections is not a precise number, so it is "
            "shown as \"91%, plausibly 62-98%\". It would be a strange "
            "feature about honest uncertainty that reported its own findings "
            "with false confidence.\n\n"
            "One limitation worth stating: only meals saved straight after an "
            "analysis are counted, and editing a meal later is not reflected. "
            "Every figure here is a lower bound."
        ),
    ),
    Announcement(
        id="2026-08-25-calorie-planning",
        date="2026-08-25",
        title="Move calories between days, on purpose",
        body=(
            "Settings has a new **Calorie planning** section. It does two "
            "things, and they are opposites of each other.\n\n"
            "**Plan a bigger day.** Going out on Saturday? Say how many extra "
            "calories you want that day and pick which days around it give them "
            "up. Saturday's target goes up, those days' targets come down by "
            "the same total, and your week is unchanged.\n\n"
            "**Make up a day that already happened.** Went over last night? "
            "Pick that day, and the app works out how far over it ran from the "
            "meals you logged. Then *you* choose which of the days ahead absorb "
            "it. It works the same way in reverse if you are bulking and came "
            "in under.\n\n"
            "Some things worth saying plainly, because they are choices rather "
            "than accidents:\n\n"
            "**None of this is a debt, and the app will never chase you for "
            "it.** Your expenditure is measured from your average intake "
            "against your weight trend, so one large day already shows up as a "
            "slightly slower week whether or not you do anything about it. This "
            "only lets you decide where it lands.\n\n"
            "**Nothing here will pop up at you.** There is no prompt after a "
            "big day, and no notification. There is one link under your calorie "
            "ring, and it is there whether the day went well or badly. Being "
            "asked \"shall we cut the next four days?\" every time you overshoot "
            "is how a planning tool turns into something worse.\n\n"
            "**You pick the days, not the app.** All the server does is refuse "
            "a spread that would take any day below a safe calorie floor -- and "
            "when it refuses, it names the day and tells you to spread wider "
            "rather than quietly shaving less than you asked for.\n\n"
            "**Protein never moves.** Carbohydrate and fat absorb the "
            "difference. Protein comes off your body weight rather than your "
            "calorie budget, and it matters more on a smaller day, not less.\n\n"
            "One related change you will notice straight away: your calorie "
            "ring now shows the real percentage when you go over. It used to "
            "stop at 100%, so a 2,400 kcal day against a 2,000 kcal goal read "
            "as if you had landed exactly on it."
        ),
    ),
    Announcement(
        id="2026-08-24-food-library",
        date="2026-08-24",
        title="Your saved foods, where you can finally fix them",
        body=(
            "Settings has a new **Food library** section listing every food the "
            "app will autocomplete for you -- and you can now correct one, "
            "rename it, or delete it.\n\n"
            "This needed fixing. Every result you pick from Open Food Facts has "
            "always been saved to your library automatically, and so has "
            "anything you ticked \"save to library\" on while logging. Until now "
            "nothing showed you the result, so if one of them had the wrong "
            "serving size, it kept filling in that wrong number on every meal "
            "you built from it and there was no way to reach it. Now there is.\n\n"
            "Each food is badged with where its numbers came from -- **yours** "
            "or **Open Food Facts** -- because those deserve different amounts "
            "of trust. Correct any of the numbers on an Open Food Facts entry "
            "and it becomes yours, since they are no longer what Open Food "
            "Facts said.\n\n"
            "One thing worth being clear about: editing a food changes what "
            "gets filled in **next** time. Meals you have already logged keep "
            "the numbers they were saved with -- a meal records its own macros, "
            "so nothing here rewrites your history.\n\n"
            "Two smaller fixes alongside it. **Your carbs and fat averages on "
            "the Analytics page were wrong, and are now right** -- they used to "
            "be divided by every day you logged rather than the days you "
            "actually recorded that macro on, so if you only tracked carbs "
            "occasionally the average came out far below what you really ate. "
            "Each macro is now averaged over its own days, the tile tells you "
            "how many days that was, and carbs and fat have tiles of their own "
            "if you track them. Expect those numbers to move up.\n\n"
            "And a mistyped or out-of-date address now gets a proper \"page not "
            "found\" with a way back, instead of an empty screen."
        ),
    ),
    Announcement(
        id="2026-08-23-fewer-quiet-failures",
        date="2026-08-23",
        title="Three things that were quietly wrong",
        body=(
            "Nothing new to look at this time -- this was a pass over the ways "
            "the app could fail without telling you.\n\n"
            "If your browser blocks site data, or you are in private mode, the "
            "app used to show you a blank white page and no explanation. It now "
            "loads normally, and the login screen warns you that you will be "
            "signed out when you close the tab, because in that mode it cannot "
            "store anything to keep you signed in.\n\n"
            "Water quick-add buttons: there is a fourth box in Settings. There "
            "always should have been -- the server accepted four all along and "
            "the screen only ever drew three, so the last one was impossible to "
            "set.\n\n"
            "The AI estimate box now clears itself after you save a meal, "
            "instead of leaving the last meal's photos and description sitting "
            "above the next one. The description you type is kept if you "
            "navigate away mid-thought and come back, which is the opposite of "
            "what it did before, and the right way round."
        ),
    ),
    Announcement(
        id="2026-08-21-supplement-tracker",
        date="2026-08-21",
        title="Tick off your supplements",
        body=(
            "Add what you take in Settings -- a name, the dose if you want one, "
            "and the times of day you mean to take it -- and a card appears on "
            "your dashboard with a box for each dose. Tick them as you go. It "
            "follows whichever day you are looking at, like the water and steps "
            "cards, so you can fill in yesterday with the same arrows.\n\n"
            "It will tell you when a dose is overdue while you have the app "
            "open, and that is the honest limit of it: **nothing here will "
            "notify you on your phone.** Real push notifications on Android go "
            "through Google Play Services, and scheduled local ones need a "
            "browser feature that was never actually built, so a reminder that "
            "reached you while the app was closed is not something this app can "
            "deliver. It would rather say so than quietly not fire.\n\n"
            "Taking a break from something? Pause it -- it drops off the card "
            "and keeps every dose you already ticked. Deleting removes the "
            "history with it, and you will be told how much before it does. "
            "Nothing here counts towards your calories or macros: a protein "
            "powder big enough to matter is a meal, and logging it in both "
            "places would count it twice."
        ),
    ),
    Announcement(
        id="2026-08-21-steps-tracker",
        date="2026-08-21",
        title="Log your steps on the dashboard",
        body=(
            "There is a steps card next to the water one now. Type the day's "
            "count and save it; type it again later and it replaces the "
            "figure rather than adding to it, because it is the same day's "
            "walking counted twice. It shows roughly what that walking cost "
            "in calories once you have a weigh-in to work it out from. Set a "
            "daily goal in Settings if you want one -- until you do, the card "
            "shows the count on its own rather than measuring you against a "
            "number nobody picked.\n\n"
            "Entering it by hand is the only option, and that is worth being "
            "straight about: reading step counts automatically needs Health "
            "Connect or Apple Health, both of which are closed to a web app "
            "like this one. Nothing here syncs with your phone or your watch. "
            "Your calorie target does not move with your steps either -- once "
            "your daily burn is measured from your own logs, the walking you "
            "did is already inside that number, and adding it again would "
            "tell you to eat for it twice."
        ),
    ),
    Announcement(
        id="2026-08-21-water-tracker",
        date="2026-08-21",
        title="Track your water from the dashboard",
        body=(
            "There is a water card on your dashboard now, under the calorie "
            "and protein rings. Tap a button to add a glass; tap undo if you "
            "tapped the wrong one. It follows whichever day you are looking "
            "at, so you can fill in yesterday with the same arrows you "
            "already use for meals.\n\n"
            "Your daily goal is worked out from your weight — 35 ml for every "
            "kilogram — and the card shows you that sum rather than just the "
            "answer. If you have not logged a weigh-in yet it falls back to a "
            "general 2 litres and tells you that is what it is doing. You can "
            "also set your own goal, and change the quick-add amounts to "
            "match the glasses and bottles you actually use, in Settings."
        ),
    ),
    Announcement(
        id="2026-08-20-measured-tdee",
        date="2026-08-20",
        title="Your calorie burn is now measured, not guessed",
        body=(
            "Until now the app worked out your daily burn from a formula — your "
            "height, age and sex, times a rough multiplier for how active you "
            "said you were. That multiplier is a convention, and it can be a "
            "few hundred calories out for any one person. Now, once you have "
            "logged enough, the app measures your burn from your own data "
            "instead: what you actually ate, against how your weight actually "
            "moved. It needs about two weeks — 10 or more weigh-ins spread "
            "across at least 14 days, with meals logged on most of them — and "
            "until then it keeps using the formula and tells you exactly what "
            "it is still waiting for. When it does measure, it shows you the "
            "sample it used and what the old formula would have said, so you "
            "can see the two agree or disagree. Today's half-finished logging "
            "never counts, so your goal cannot drift while you are eating "
            "towards it. If your logs imply you burn less than your body uses "
            "at rest, the app says so rather than quietly handing you a very "
            "low target — that almost always means meals are going unlogged."
        ),
    ),
    Announcement(
        id="2026-08-20-body-profile-targets",
        date="2026-08-20",
        title="Daily goals that follow your weight",
        body=(
            "Settings has a new Body profile section — height, date of birth, "
            "sex, activity level and the rate you want to gain or lose. Fill it "
            "in and the app works out your BMI, roughly what you burn in a day, "
            "and a calorie and macro target to match. Tick \"work out my goals "
            "from my body profile\" and those become your daily goals, "
            "recalculated every time you log a weigh-in, so they stop being a "
            "number you guessed once. Every figure is shown next to what it was "
            "calculated from, because these are estimates from a formula, not "
            "measurements of you — expect them to be a few hundred calories out "
            "and let your own weight trend correct them. Ask for a rate that is "
            "too aggressive and you will be told what you got instead, and why. "
            "The profile is optional and everything works without it."
        ),
    ),
    Announcement(
        id="2026-08-15-meal-templates",
        date="2026-08-15",
        title="Save a meal, then log it again in one tap",
        body=(
            "Meals you eat often no longer need retyping. Build a meal as "
            "usual, then hit \"Save as template\" — it appears under Quick log "
            "on your dashboard, and tapping it opens the form with every "
            "ingredient already filled in at the weight you saved. Adjust "
            "anything before saving: change one ingredient's weight and only "
            "that ingredient recalculates. Saving a template with a name you "
            "already used replaces the old one, and the message tells you when "
            "that happens. Templates are logged against whichever day you're "
            "viewing, so you can catch up on yesterday without retyping it."
        ),
    ),
    # Third and final note on this. The two before it (2026-08-04, then
    # 2026-08-05) each promised reset was working or imminent; neither was true,
    # because every email provider tried has refused the account. Each
    # correction gets a NEW id rather than an edit: seen ids accumulate in
    # localStorage, so editing in place reaches nobody who already read the old
    # wording — which is precisely the audience a correction is for.
    #
    # This one deliberately makes no promise about timing. That is what made the
    # previous two rot. Say what is true and what the user should do about it,
    # and nothing about when it changes.
    Announcement(
        id="2026-08-14-password-reset-unavailable",
        date="2026-08-14",
        title="Password reset isn't available yet",
        body=(
            "The \"Forgot your password?\" link on the login page isn't "
            "switched on — we haven't been able to get email sending set up, "
            "so for now it will tell you reset isn't available. Please keep "
            "your password somewhere safe: if you forget it, there is "
            "currently no way back into your account. We'll post here if that "
            "changes."
        ),
    ),
    Announcement(
        id="2026-08-02-photos-and-gallery",
        date="2026-08-02",
        title="Pick photos from your gallery, and use more than one",
        body=(
            "On Android the photo button used to open the camera and give you "
            "no way to reach your gallery — that's fixed, you now get the "
            "normal chooser. You can also attach up to four photos to one "
            "analysis: another angle, or the packet's nutrition label next to "
            "the plate, and the estimate gets sharper. Extra photos are "
            "treated as the same meal, so nothing is counted twice."
        ),
    ),
    Announcement(
        id="2026-07-28-weight-tracking",
        date="2026-07-28",
        title="Track your weight",
        body=(
            "There's a new Weight page: log a weigh-in and see it charted "
            "against a smoothed trend line, so a heavy dinner or a salty meal "
            "doesn't read as real change. Re-logging a date replaces that day's "
            "entry. Pick kilograms or pounds in Settings."
        ),
    ),
    Announcement(
        id="2026-07-26-voice-notes",
        date="2026-07-26",
        title="Speak your meals",
        body=(
            "Tap the mic in AI meal analysis and describe what you ate. The "
            "recording is transcribed into the description box so you can fix "
            "anything it mishears before the macros are estimated."
        ),
    ),
    Announcement(
        id="2026-07-26-ai-restored",
        date="2026-07-26",
        title="AI analysis is working again",
        body=(
            "AI estimates failed for some of July after the server moved to a "
            "region where our AI provider's free tier isn't offered. The server "
            "has moved back and analysis is running normally."
        ),
    ),
    Announcement(
        id="2026-07-23-any-date",
        date="2026-07-23",
        title="Log meals for any day",
        body=(
            "The dashboard now has day navigation, so you can review or "
            "back-fill a meal you forgot to log without editing the date by "
            "hand."
        ),
    ),
    Announcement(
        id="2026-07-09-accounts",
        date="2026-07-09",
        title="Your own account",
        body=(
            "Macros Calculator is now multi-user: your meals, foods and goals "
            "are private to your account and follow you across devices."
        ),
    ),
]


def status_banner() -> str | None:
    """The current outage/maintenance notice, or None.

    Read per request rather than at import so a value set in the hosting
    dashboard takes effect on the next request instead of the next deploy.
    """
    return os.environ.get(STATUS_BANNER_ENV, "").strip() or None
