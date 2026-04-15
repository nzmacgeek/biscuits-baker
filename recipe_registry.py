"""
recipe_registry.py - Central registry of all known Baker recipes.

New recipes can be registered by adding them to RECIPE_CLASSES below.
"""

from __future__ import annotations

from typing import Dict, List, Type

from config import Config
from recipes.base import BaseRecipe
from recipes.musl_blueyos import MuslBlueyosRecipe
from recipes.dimsim import DimsimRecipe
from recipes.claw import ClawRecipe
from recipes.matey import MateyRecipe
from recipes.blueyos_bash import BlueyosBashRecipe
from recipes.blueyos_tzinfo import BlueyosTzinfoRecipe

# ---------------------------------------------------------------------------
# All known recipe classes
# ---------------------------------------------------------------------------

RECIPE_CLASSES: List[Type[BaseRecipe]] = [
    MuslBlueyosRecipe,
    DimsimRecipe,
    ClawRecipe,
    MateyRecipe,
    BlueyosBashRecipe,
    BlueyosTzinfoRecipe,
]


def load_recipes(config: Config) -> Dict[str, BaseRecipe]:
    """Instantiate all known recipes and return a {name: recipe} mapping."""
    return {cls.name: cls(config) for cls in RECIPE_CLASSES}
