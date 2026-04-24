"""
recipes/kernel_headers.py - Biscuits kernel headers package for BlueyOS.

Packages the BlueyOS-specific headers from src/biscuits/include/ so that
userspace programs running inside BlueyOS can include them via
  #include <biscuits/bluey.h>  etc.

These headers expose BlueyOS kernel internals (type definitions, port
constants, RLIMIT values) for programs that talk directly to the kernel
rather than going through musl.  They are installed at:
  /usr/include/biscuits/
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import tempfile

from recipes._musl_package import MuslPackageRecipe
from recipes.base import RecipeError


class KernelHeadersRecipe(MuslPackageRecipe):
    """Package biscuits kernel headers for inside-OS development."""

    name = "kernel-headers"
    version = "0.1.0"
    description = "BlueyOS (biscuits) kernel headers for userspace development"
    dependencies = []
    install_paths = ["usr/include/biscuits"]

    def __init__(self, config):
        super().__init__(config)
        self._kernel_include = os.path.join(
            config.abs_sources_dir, "biscuits", "include"
        )

    def build(self) -> None:
        if not os.path.isdir(self._kernel_include):
            raise RecipeError(
                f"biscuits include dir not found at {self._kernel_include}. "
                "Run 'baker prepare' first."
            )

    def install(self) -> None:
        # Merge kernel headers into sysroot/usr/include/biscuits/
        dst = os.path.join(self.config.abs_sysroot, "usr", "include", "biscuits")
        if os.path.isdir(self._kernel_include):
            shutil.copytree(self._kernel_include, dst, dirs_exist_ok=True)
            self.log.info("Installed kernel headers into sysroot/usr/include/biscuits/")

    def package(self) -> str | None:
        src = self._kernel_include
        if not os.path.isdir(src):
            raise RecipeError(
                f"biscuits include dir not found at {src}. "
                "Run 'baker prepare' first."
            )

        dpkbuild = self.resolve_dpkbuild()

        with tempfile.TemporaryDirectory(prefix="kernel-headers-pkg-") as pkg_dir:
            # Headers → /usr/include/biscuits/
            payload_inc = os.path.join(
                pkg_dir, "payload", "usr", "include", "biscuits"
            )
            shutil.copytree(src, payload_inc, symlinks=True)

            meta_dir = os.path.join(pkg_dir, "meta", "scripts")
            os.makedirs(meta_dir, exist_ok=True)
            manifest = {
                "name": self.name,
                "version": self.version,
                "arch": "i386",
                "description": self.description,
                "depends": [],
                "recommends": [],
                "conflicts": [],
                "provides": ["kernel-headers"],
                "maintainer": "BlueyOS Project",
                "homepage": "https://github.com/nzmacgeek/biscuits",
                "preinst": "",
                "postinst": "",
                "prerm": "",
                "postrm": "",
                "files": [],
                "scripts": {},
            }
            with open(os.path.join(pkg_dir, "meta", "manifest.json"), "w") as fh:
                json.dump(manifest, fh, indent=2)
            for script in ("preinst", "postinst", "prerm", "postrm"):
                sp = os.path.join(meta_dir, script)
                with open(sp, "w") as fh:
                    fh.write("#!/bin/sh\nexit 0\n")
                os.chmod(sp, 0o755)

            self.run([dpkbuild, "build", pkg_dir], cwd=self.config.abs_output_dir)

        dpk = glob.glob(
            os.path.join(self.config.abs_output_dir, "kernel-headers-*.dpk")
        )
        if not dpk:
            raise RecipeError(
                "dpkbuild did not produce kernel-headers-*.dpk in output/"
            )
        self.log.info("Package: %s", dpk[0])
        return dpk[0]
