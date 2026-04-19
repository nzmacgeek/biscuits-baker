"""Tests for recipe_registry.py."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import load_config
from recipe_registry import load_recipes


def test_registry_includes_new_blueyos_userland_recipes(tmp_path):
    cfg = load_config(str(tmp_path / "no.yaml"))
    recipes = load_recipes(cfg)

    assert "blueyos-base" in recipes
    assert "blueyos-archiving-tools" in recipes
    assert "login-tools" in recipes
    assert "walkies" in recipes
    assert "ncurses" in recipes
    assert "readline" in recipes
    assert "bash" in recipes
    assert "glibc-blueyos" in recipes
    assert "blueyos-bash" not in recipes
