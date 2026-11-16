"""Shared primary destinations for survey and seasonal navigation."""
from html import escape
from urllib.parse import quote

DESTINATIONS = (("/life-list/", "Inventory"), ("/field/", "Field Targets"))


def survey_destinations(active_route="", *, context=""):
    suffix = "?from=" + quote(context, safe="") if context else ""
    return '<div class="survey-destinations">' + "".join(
        f'<a href="{route}{escape(suffix, quote=True)}"'
        + (' aria-current="page"' if route == active_route else '')
        + f'>{label}</a>' for route, label in DESTINATIONS
    ) + '</div>'
