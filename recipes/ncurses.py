"""recipes/ncurses.py - Recipe for ncurses from the blueyos-bash repo."""

from __future__ import annotations

from recipes.blueyos_bash import BlueyosBashRepoRecipe


class NcursesRecipe(BlueyosBashRepoRecipe):
    """Terminal handling library for BlueyOS."""

    name = "ncurses"
    version = "6.5"
    dependencies = ["musl-blueyos"]
    build_target = "ncurses"
    payload_subdir = "ncurses"
    install_paths = ["usr/lib", "usr/include", "usr/share/terminfo", "usr/share/tabset"]
