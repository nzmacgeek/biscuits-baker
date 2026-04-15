"""
recipes/musl_blueyos.py - Recipe for musl-blueyos.

musl-blueyos is the C library for the BlueyOS userland.  Building it is
handled by the dedicated ToolchainStage (``baker toolchain``).  This
recipe records the component so it appears in dependency graphs and can
be referenced by other recipes.  The actual build delegates to
``tools/build-musl.sh`` inside the biscuits source tree.
"""

from __future__ import annotations

import os

from recipes.base import BaseRecipe


class MuslBlueyosRecipe(BaseRecipe):
    """C library (musl-blueyos) for BlueyOS userland."""

    name = "musl-blueyos"
    version = "1.2.5"
    dependencies: list = []

    def build(self) -> None:
        """musl-blueyos is built by the ToolchainStage; nothing to do here."""
        musl_lib = os.path.join(self.config.abs_musl_prefix, "lib", "libc.a")
        if os.path.isfile(musl_lib):
            self.log.info(
                "musl-blueyos already installed at %s", self.config.abs_musl_prefix
            )
        else:
            self.log.warning(
                "musl-blueyos not found at %s — run 'baker toolchain' first.",
                self.config.abs_musl_prefix,
            )

    def install(self) -> None:
        pass  # Installed by ToolchainStage

    def package(self):
        return None  # musl ships as part of the sysroot, not a separate package
