"""
stages/clean.py - Clean stage for Baker.

Removes build artifacts, the sysroot, and/or output files.
"""

from __future__ import annotations

import os
import shutil

from stage_runner import Stage


class CleanStage(Stage):
    """Remove build artifacts and optionally the sysroot."""

    name = "clean"

    # Flags to control what gets cleaned (set via config or CLI overrides)
    clean_build: bool = True
    clean_sysroot: bool = False
    clean_output: bool = False

    def run(self) -> None:
        cfg = self.config

        if self.clean_build:
            self._remove_dir(cfg.abs_build_dir, "build directory")

        if self.clean_sysroot:
            self._remove_dir(cfg.abs_sysroot, "sysroot")

        if self.clean_output:
            self._remove_dir(cfg.abs_output_dir, "output directory")

        self.log.info("Clean stage complete.")

    # ------------------------------------------------------------------

    def _remove_dir(self, path: str, label: str) -> None:
        if os.path.exists(path):
            self.log.info("Removing %s: %s", label, path)
            shutil.rmtree(path)
        else:
            self.log.debug("%s not found (already clean): %s", label, path)
