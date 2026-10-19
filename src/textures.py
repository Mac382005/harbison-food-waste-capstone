"""Texture-modified diets (IDDSI food levels) used for residents and menu types.

The stored value matches the menu_variant names used by the Harbison four-week menu
("Regular", "Soft Bite Sized", "Minced", "Puree"); the label is what staff see.
"""
from __future__ import annotations

import re

TEXTURES = {
    "Regular": {"label": "Regular", "level": 7},
    "Soft Bite Sized": {"label": "Soft & Bite-Sized", "level": 6},
    "Minced": {"label": "Minced & Moist", "level": 5},
    "Puree": {"label": "Pureed", "level": 4},
}
# Ice cream and jelly melt to thin liquid, so they are left off generated orders for these diets.
NO_MELTING_DESSERTS = {"Minced", "Puree"}

_ALIASES = {
    "Regular": ["regular", "normal", "full", "rg7", "rg", "level 7", "l7", "iddsi 7", "7"],
    "Soft Bite Sized": ["soft bite sized", "soft and bite sized", "soft & bite sized", "soft & bite-sized",
                        "soft and bite-sized", "soft", "sb6", "sb", "level 6", "l6", "iddsi 6", "6"],
    "Minced": ["minced", "minced and moist", "minced & moist", "mince", "mince moist", "mm5", "mm", "level 5",
               "l5", "iddsi 5", "5"],
    "Puree": ["puree", "pureed", "purée", "puréed", "pu4", "pu", "level 4", "l4", "iddsi 4", "4"],
}
_LOOKUP = {re.sub(r"\s+", " ", a): key for key, names in _ALIASES.items() for a in names}


def parse_texture(text: str | None) -> str | None:
    """Recognise a texture written in common ways ('Minced and moist', 'MM5', 'Level 4'...)."""
    cleaned = re.sub(r"[\s_\-/]+", " ", (text or "").strip().lower())
    if not cleaned:
        return "Regular"
    if cleaned in _LOOKUP:
        return _LOOKUP[cleaned]
    return _LOOKUP.get(cleaned.replace("-", " "))


def texture_label(value: str | None, with_level: bool = False) -> str:
    info = TEXTURES.get(value or "Regular")
    if info is None:
        return value or "Regular"
    return f"{info['label']} (Level {info['level']})" if with_level else info["label"]
