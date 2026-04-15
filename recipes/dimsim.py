"""
recipes/dimsim.py - Recipe for dimsim package manager.

dimsim is a Go package manager for BlueyOS.  Building it produces two
static binaries: ``bin/dimsim`` and ``bin/dpkbuild``.  Both are
installed into ``sysroot/usr/bin/`` so they are available for the
package stage.  A copy is also placed on the host PATH by appending the
build output directory to the environment (used by subsequent recipes
that call ``dpkbuild``).
"""

from __future__ import annotations

import os
import shutil

from recipes.base import BaseRecipe, RecipeError


class DimsimRecipe(BaseRecipe):
    """dimsim package manager and dpkbuild tool."""

    name = "dimsim"
    version = "0.1.0"
    dependencies: list = []

    # Override source dir to use sources_dir/dimsim
    def __init__(self, config):
        super().__init__(config)
        self._source_dir = os.path.join(config.abs_sources_dir, "dimsim")
        self._build_dir = os.path.join(config.abs_build_dir, "dimsim")

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"dimsim source not found at {src}.  Run 'baker prepare' first."
            )

        if shutil.which("go") is None:
            raise RecipeError(
                "go toolchain not found.  Install Go to build dimsim."
            )

        self.log.info("Building dimsim and dpkbuild")
        self.run(["make"], cwd=src)

        # Verify the binaries were produced
        for binary in ("bin/dimsim", "bin/dpkbuild"):
            path = os.path.join(src, binary)
            if not os.path.isfile(path):
                raise RecipeError(
                    f"Expected binary not found after build: {path}"
                )
        self.log.info("dimsim build complete")

    def install(self) -> None:
        src = self._source_dir
        usr_bin = self.sysroot.ensure_dir("usr", "bin")

        for binary in ("bin/dimsim", "bin/dpkbuild"):
            src_path = os.path.join(src, binary)
            if os.path.isfile(src_path):
                dest = os.path.join(usr_bin, os.path.basename(binary))
                shutil.copy2(src_path, dest)
                os.chmod(dest, 0o755)
                self.log.info("Installed %s → %s", src_path, dest)

    def package(self):
        """dimsim ships as binaries inside the sysroot; no separate .dpk needed."""
        return None
