"""Project-wide views shared by several apps."""
from django.shortcuts import render


def placeholder_view(request, title: str, phase: int, description: str):
    """Render a 'coming in Phase N' page for sections not built yet.

    The values arrive as keyword arguments from the `path(...)` definitions,
    so each section needs no view code of its own until its phase begins.
    """
    context = {"page_title": title, "phase": phase, "description": description}
    return render(request, "placeholder.html", context)
