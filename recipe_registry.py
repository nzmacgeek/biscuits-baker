"""
recipe_registry.py - Central registry of all known Baker recipes.

New recipes can be registered by adding them to RECIPE_CLASSES below.
"""

from __future__ import annotations

from typing import Dict, List, Type

from config import Config
from recipes.base import BaseRecipe
from recipes.musl_blueyos import MuslBlueyosRecipe
from recipes.glibc_blueyos import GlibcBlueyosRecipe
from recipes.dimsim import DimsimRecipe
from recipes.claw import ClawRecipe
from recipes.matey import MateyRecipe
from recipes.ncurses import NcursesRecipe
from recipes.readline import ReadlineRecipe
from recipes.blueyos_bash import BashRecipe
from recipes.blueyos_tzinfo import BlueyosTzinfoRecipe
from recipes.blueyos_base import BlueyosBaseRecipe
from recipes.blueyos_archiving_tools import BlueyosArchivingToolsRecipe
from recipes.login_tools import LoginToolsRecipe
from recipes.walkies import WalkiesRecipe

# ---------------------------------------------------------------------------
# All known recipe classes
# ---------------------------------------------------------------------------

RECIPE_CLASSES: List[Type[BaseRecipe]] = [
    MuslBlueyosRecipe,
    GlibcBlueyosRecipe,
    DimsimRecipe,
    ClawRecipe,
    MateyRecipe,
    NcursesRecipe,
    ReadlineRecipe,
    BashRecipe,
    BlueyosTzinfoRecipe,
    BlueyosBaseRecipe,
    BlueyosArchivingToolsRecipe,
    LoginToolsRecipe,
    WalkiesRecipe,
]


def load_recipes(config: Config) -> Dict[str, BaseRecipe]:
    """Instantiate all known recipes and return a {name: recipe} mapping."""
    return {cls.name: cls(config) for cls in RECIPE_CLASSES}
