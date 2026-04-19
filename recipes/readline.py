"""recipes/readline.py - Recipe for readline from the blueyos-bash repo."""

from __future__ import annotations

from recipes.blueyos_bash import BlueyosBashRepoRecipe


class ReadlineRecipe(BlueyosBashRepoRecipe):
    """GNU Readline library for BlueyOS."""

    name = "readline"
    version = "8.2"
    dependencies = ["musl-blueyos", "ncurses"]
    build_target = "readline"
    payload_subdir = "readline"
    install_paths = ["usr/lib", "usr/include/readline", "usr/share"]
