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
from recipes.yap import YapRecipe
from recipes.matey import MateyRecipe
from recipes.ncurses import NcursesRecipe
from recipes.readline import ReadlineRecipe
from recipes.blueyos_bash import BashRecipe
from recipes.blueyos_tzinfo import BlueyosTzinfoRecipe
from recipes.blueyos_base import BlueyosBaseRecipe
from recipes.blueyos_archiving_tools import BlueyosArchivingToolsRecipe
from recipes.login_tools import LoginToolsRecipe
from recipes.walkies import WalkiesRecipe
from recipes.scout import ScoutRecipe
from recipes.openssl import OpenSSLRecipe
from recipes.nano import NanoRecipe
from recipes.vim import VimRecipe
from recipes.dropbear import DropbearRecipe
from recipes.w3m import W3mRecipe
from recipes.musl_dev import MuslDevRecipe
from recipes.kernel_headers import KernelHeadersRecipe
from recipes.gnu_make import GnuMakeRecipe
from recipes.tcc import TccRecipe
from recipes.binutils import BinutilsRecipe
from recipes.zlib import ZlibRecipe
from recipes.gmp import GmpRecipe
from recipes.mpfr import MpfrRecipe
from recipes.mpc import MpcRecipe
from recipes.gcc_native import GccNativeRecipe
from recipes.busybox import BusyboxRecipe

# ---------------------------------------------------------------------------
# All known recipe classes
# ---------------------------------------------------------------------------

RECIPE_CLASSES: List[Type[BaseRecipe]] = [
    MuslBlueyosRecipe,
    GlibcBlueyosRecipe,
    DimsimRecipe,
    ClawRecipe,
    YapRecipe,
    MateyRecipe,
    NcursesRecipe,
    ReadlineRecipe,
    BashRecipe,
    BlueyosTzinfoRecipe,
    BlueyosBaseRecipe,
    BlueyosArchivingToolsRecipe,
    LoginToolsRecipe,
    WalkiesRecipe,
    ScoutRecipe,
    OpenSSLRecipe,
    NanoRecipe,
    VimRecipe,
    DropbearRecipe,
    W3mRecipe,
    MuslDevRecipe,
    KernelHeadersRecipe,
    GnuMakeRecipe,
    TccRecipe,
    BinutilsRecipe,
    ZlibRecipe,
    GmpRecipe,
    MpfrRecipe,
    MpcRecipe,
    GccNativeRecipe,
    BusyboxRecipe,
]


def load_recipes(config: Config) -> Dict[str, BaseRecipe]:
    """Instantiate all known recipes and return a {name: recipe} mapping."""
    return {cls.name: cls(config) for cls in RECIPE_CLASSES}
