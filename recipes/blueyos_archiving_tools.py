"""
recipes/blueyos_archiving_tools.py - Recipe for blueyos-archiving-tools.

Builds tar, gzip, bzip2, and xz against musl-blueyos, stages their payloads
into the sysroot, and packages the resulting .dpk archives.
"""

from __future__ import annotations

import glob
import os
import shutil

from recipes._musl_package import MuslPackageRecipe
from recipes.base import RecipeError


class BlueyosArchivingToolsRecipe(MuslPackageRecipe):
    """Build and package the BlueyOS archiving tool set."""

    name = "blueyos-archiving-tools"
    version = "0.1.0"
    dependencies = ["musl-blueyos"]
    install_paths = [
        "usr/bin/tar",
        "usr/bin/gzip",
        "usr/bin/gunzip",
        "usr/bin/zcat",
        "usr/bin/bzip2",
        "usr/bin/bunzip2",
        "usr/bin/bzcat",
        "usr/bin/xz",
        "usr/bin/unxz",
        "usr/bin/xzcat",
        "usr/bin/lzma",
        "usr/bin/unlzma",
    ]

    def configure(self) -> None:
        self._ensure_musl_specs()

    def _musl_make_vars(self) -> list[str]:
        """Return the make variables needed for all musl-linked targets."""
        musl_prefix = self._resolve_musl_make_prefix()
        musl_gcc = os.path.join(self._resolve_musl_sysroot(), "bin", "musl-gcc")
        vars_ = [f"MUSL_PREFIX={musl_prefix}"]
        if os.path.isfile(musl_gcc):
            vars_.append(f"CC={musl_gcc}")
        return vars_

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"{self.name} source not found at {src}. Run 'baker prepare' first."
            )

        musl_prefix = self._resolve_musl_make_prefix()
        self.log.info("Building %s against musl at %s", self.name, musl_prefix)
        self.run(
            [
                "make",
                *self._musl_make_vars(),
                "CFLAGS=-O2 -pipe -fno-stack-protector",
            ],
            cwd=src,
        )

    def install(self) -> None:
        src = self._source_dir
        self.run(
            [
                "make",
                "install-staged",
                *self._musl_make_vars(),
                f"SYSROOT={self.config.abs_sysroot}",
            ],
            cwd=src,
        )
        self.log.info("Installed %s payloads into %s", self.name, self.config.abs_sysroot)

    def package(self) -> str | None:
        src = self._source_dir
        dpkbuild = self.resolve_dpkbuild()
        env = {
            "PATH": os.path.dirname(dpkbuild) + os.pathsep + os.environ.get("PATH", ""),
        }
        self.run(["make", "dpk", *self._musl_make_vars()], cwd=src, env=env)

        dpk_files = sorted(
            glob.glob(os.path.join(src, "build", "dpk", "*.dpk"))
            + glob.glob(os.path.join(src, "*.dpk"))
        )
        if not dpk_files:
            raise RecipeError(f"No .dpk files produced for {self.name}")

        copied: list[str] = []
        for dpk_file in dpk_files:
            dest = os.path.join(self.config.abs_output_dir, os.path.basename(dpk_file))
            shutil.copy2(dpk_file, dest)
            copied.append(dest)
        self.log.info("Packages: %s", ", ".join(copied))
        return copied[0]
