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
            "are private to your account and follow you across devices. There "
            "is no password reset yet, so keep your password somewhere safe."
        ),
    ),
]


def status_banner() -> str | None:
    """The current outage/maintenance notice, or None.

    Read per request rather than at import so a value set in the hosting
    dashboard takes effect on the next request instead of the next deploy.
    """
    return os.environ.get(STATUS_BANNER_ENV, "").strip() or None
