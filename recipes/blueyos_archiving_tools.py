"""
recipes/blueyos_archiving_tools.py - Recipe for blueyos-archiving-tools.

Builds tar, gzip, bzip2, and xz against musl-blueyos, stages their payloads
into the sysroot, and packages the resulting .dpk archives.
"""

from __future__ import annotations

import glob
import os
import shutil

from recipes.base import BaseRecipe, RecipeError


class BlueyosArchivingToolsRecipe(BaseRecipe):
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

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"{self.name} source not found at {src}. Run 'baker prepare' first."
            )

        musl_prefix = self._resolve_musl_prefix()
        self.log.info("Building %s against musl at %s", self.name, musl_prefix)
        self.run(
            [
                "make",
                f"MUSL_PREFIX={musl_prefix}",
                "CFLAGS=-O2 -pipe -fno-stack-protector",
            ],
            cwd=src,
        )

    def install(self) -> None:
        src = self._source_dir
        musl_prefix = self._resolve_musl_prefix()
        self.run(
            [
                "make",
                "install-staged",
                f"MUSL_PREFIX={musl_prefix}",
                f"SYSROOT={self.config.abs_sysroot}",
            ],
            cwd=src,
        )
        self.log.info("Installed %s payloads into %s", self.name, self.config.abs_sysroot)

    def package(self) -> str | None:
        src = self._source_dir
        musl_prefix = self._resolve_musl_prefix()
        dpkbuild = self.resolve_dpkbuild()
        env = {
            "PATH": os.path.dirname(dpkbuild) + os.pathsep + os.environ.get("PATH", ""),
        }
        self.run(["make", "dpk", f"MUSL_PREFIX={musl_prefix}"], cwd=src, env=env)

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

    def _resolve_musl_prefix(self) -> str:
        base = self.config.abs_musl_prefix
        for candidate in (base, os.path.join(base, "usr")):
            include_dir = os.path.join(candidate, "include")
            libc_a = os.path.join(candidate, "lib", "libc.a")
            if os.path.isdir(include_dir) and os.path.isfile(libc_a):
                return candidate
        return base
