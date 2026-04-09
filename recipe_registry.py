"""
recipe_registry.py - Central registry of all known Baker recipes.

New recipes can be registered by adding them to RECIPE_CLASSES below.
"""

from __future__ import annotations

from typing import Dict, List, Type

from config import Config
from recipes.base import BaseRecipe
from recipes.musl import MuslRecipe
from recipes.linux_headers import LinuxHeadersRecipe
from recipes.busybox import BusyBoxRecipe

# ---------------------------------------------------------------------------
# All known recipe classes
# ---------------------------------------------------------------------------

RECIPE_CLASSES: List[Type[BaseRecipe]] = [
    MuslRecipe,
    LinuxHeadersRecipe,
    BusyBoxRecipe,
]


def load_recipes(config: Config) -> Dict[str, BaseRecipe]:
    """Instantiate all known recipes and return a {name: recipe} mapping."""
    return {cls.name: cls(config) for cls in RECIPE_CLASSES}
