"""Release notes and the live status banner.

Public on purpose: the response contains no user data, and an unauthenticated
endpoint means an outage notice still renders on the login page — which is
exactly where someone lands when the app looks broken.
"""
from fastapi import APIRouter

from ..announcements import ANNOUNCEMENTS, status_banner
from ..schemas import AnnouncementsResponse

router = APIRouter(prefix="/api/announcements", tags=["announcements"])


@router.get("", response_model=AnnouncementsResponse)
def list_announcements():
    return AnnouncementsResponse(banner=status_banner(), items=ANNOUNCEMENTS)
