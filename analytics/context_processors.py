"""Template context shared by every page: the sidebar navigation.

Keeping the menu in one list means adding a page later is a one-line change,
and the active-link highlighting needs no per-template logic.
"""
from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class NavItem:
    label: str
    url_name: str  # "namespace:name" or plain name, as used with {% url %}
    icon: str  # SVG path data for a 24x24 outline icon


NAV_ITEMS = [
    NavItem("Overview", "analytics:overview", "M3 12l9-9 9 9M5 10v10h14V10"),
    NavItem(
        "Customer Analytics",
        "analytics:customers",
        "M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8z",
    ),
    NavItem("Trend Analysis", "analytics:trends", "M3 17l6-6 4 4 8-8M15 7h6v6"),
    NavItem("Customer Segments", "analytics:segments", "M21 12A9 9 0 1112 3v9h9z"),
    NavItem(
        "AI Business Assistant",
        "ai_assistant:chat",
        "M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z",
    ),
    NavItem("Data Upload", "analytics:upload", "M4 16v4h16v-4M12 4v12M7 9l5-5 5 5"),
    NavItem("Reports", "reports:index", "M9 12h6M9 16h6M7 3h7l5 5v13H7z"),
    NavItem(
        "Settings",
        "accounts:settings",
        "M12 15a3 3 0 100-6 3 3 0 000 6zM19 12h2M3 12h2M12 3v2M12 19v2",
    ),
]


def navigation(request):
    match = request.resolver_match
    current = f"{match.namespace}:{match.url_name}" if match and match.namespace else (
        match.url_name if match else ""
    )
    return {
        "nav_items": NAV_ITEMS,
        "current_url_name": current,
        "allow_registration": settings.ALLOW_REGISTRATION,
    }
