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
