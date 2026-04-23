"""
recipes/blueyos_base.py - Recipe for blueyos-base.

blueyos-base builds the core BlueyOS userland utilities and default system
configuration files. Upstream provides both `install-sysroot` and `package`
targets, so Baker delegates to upstream packaging and requires a `.dpk`
artifact.
"""

from __future__ import annotations

import glob
import os
import shutil

from recipes._musl_package import MuslPackageRecipe
from recipes.base import RecipeError


class BlueyosBaseRecipe(MuslPackageRecipe):
    """blueyos-base - core utilities and default system files."""

    name = "blueyos-base"
    version = "0.1.0"
    dependencies = ["musl-blueyos"]
    install_paths = [
        "usr/bin",
        "etc/passwd",
        "etc/group",
        "etc/issue",
        "etc/motd",
    ]

    def install(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"{self.name} source not found at {src}.  Run 'baker prepare' first."
            )

        musl_prefix = self._resolve_musl_make_prefix()
        self.run(
            [
                "make",
                "install-sysroot",
                f"SYSROOT={self.config.abs_sysroot}",
            ],
            cwd=src,
            env={"MUSL_PREFIX": musl_prefix},
        )
        self.log.info("Installed blueyos-base into %s", self.config.abs_sysroot)

    def package(self) -> str | None:
        src = self._source_dir
        musl_prefix = self._resolve_musl_make_prefix()
        dpkbuild = self.resolve_dpkbuild()

        env = {"MUSL_PREFIX": musl_prefix}
        env["PATH"] = os.path.dirname(dpkbuild) + ":" + os.environ.get("PATH", "")

        self.run(["make", "package"], cwd=src, env=env)
        dpk_files = glob.glob(os.path.join(src, "*.dpk"))
        if not dpk_files:
            raise RecipeError(
                f"make package completed for {self.name}, but no .dpk was produced in {src}"
            )

        dest = os.path.join(self.config.abs_output_dir, os.path.basename(dpk_files[0]))
        shutil.copy2(dpk_files[0], dest)
        self.log.info("Package: %s", dest)
        return dest
        src = self._source_dir
        musl_prefix = self._resolve_musl_make_prefix()
        dpkbuild = self.resolve_dpkbuild()

        env = {"MUSL_PREFIX": musl_prefix}
        env["PATH"] = os.path.dirname(dpkbuild) + ":" + os.environ.get("PATH", "")

        self.run(["make", "package"], cwd=src, env=env)
        dpk_files = glob.glob(os.path.join(src, "*.dpk"))
        if not dpk_files:
            raise RecipeError(
                f"make package completed for {self.name}, but no .dpk was produced in {src}"
            )

        dest = os.path.join(self.config.abs_output_dir, os.path.basename(dpk_files[0]))
        shutil.copy2(dpk_files[0], dest)
        self.log.info("Package: %s", dest)
        return dest