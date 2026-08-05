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
    # Replaces, rather than edits, 2026-08-04-password-reset: that note shipped
    # with the code but the email provider's sender was never verified, so the
    # endpoint 503s and the note was never true. Editing it in place would not
    # reach anyone — seen ids accumulate in localStorage, so every device that
    # already read "you can reset it now" would keep that as the last word. A
    # retracted note gets a new id; the dead one just retires unused.
    # Phrased as a dated status so it ages into accurate history once reset is
    # live, at which point a separate "it works now" note lands above it.
    Announcement(
        id="2026-08-05-password-reset-soon",
        date="2026-08-05",
        title="Password reset is almost ready",
        body=(
            "There's a \"Forgot your password?\" link on the login page now, "
            "but it isn't switched on yet — we're still finishing setup with "
            "the service that sends the email, so for the moment it will tell "
            "you reset isn't available. Keep your password somewhere safe "
            "until then, and we'll post here the day it starts working."
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
