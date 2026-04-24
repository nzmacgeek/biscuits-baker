"""
recipes/musl_dev.py - musl libc development package for BlueyOS.

Packages the musl headers, static libraries, and CRT objects from the
baker's already-built musl toolchain so they can be installed inside
BlueyOS and used by a native compiler (TCC, GCC) running in the OS.

Files installed inside BlueyOS:
  /usr/include/  — full musl C library headers
  /usr/lib/libc.a, libm.a, libpthread.a, librt.a, ...  — static libs
  /usr/lib/crt1.o, crti.o, crtn.o  — CRT objects (needed for linking)
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import tempfile

from recipes._musl_package import MuslPackageRecipe
from recipes.base import RecipeError


class MuslDevRecipe(MuslPackageRecipe):
    """Package musl libc dev files for use inside BlueyOS."""

    name = "musl-dev"
    version = "1.2.5"
    description = "musl libc headers and static libraries for BlueyOS development"
    dependencies = ["musl-blueyos"]
    install_paths = [
        "usr/include",
        "usr/lib/libc.a",
        "usr/lib/crt1.o",
        "usr/lib/crti.o",
        "usr/lib/crtn.o",
    ]

    def build(self) -> None:
        pass  # musl already built by musl-blueyos

    def install(self) -> None:
        pass  # musl already in sysroot; no extra install step

    def package(self) -> str | None:
        musl_prefix = self._resolve_musl_make_prefix()
        include_dir = os.path.join(musl_prefix, "include")
        lib_dir = os.path.join(musl_prefix, "lib")

        if not os.path.isdir(include_dir):
            raise RecipeError(
                f"musl include dir not found at {include_dir}. "
                "Run 'baker toolchain' first."
            )

        dpkbuild = self.resolve_dpkbuild()

        with tempfile.TemporaryDirectory(prefix="musl-dev-pkg-") as pkg_dir:
            # Headers → /usr/include/
            payload_include = os.path.join(pkg_dir, "payload", "usr", "include")
            shutil.copytree(include_dir, payload_include, symlinks=True)

            # Static libs and CRT objects → /usr/lib/
            payload_lib = os.path.join(pkg_dir, "payload", "usr", "lib")
            os.makedirs(payload_lib, exist_ok=True)
            for pattern in ("*.a", "crt*.o", "Scrt1.o", "rcrt1.o"):
                for src in glob.glob(os.path.join(lib_dir, pattern)):
                    shutil.copy2(src, payload_lib)

            # Manifest
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
                "provides": ["libc-dev"],
                "maintainer": "BlueyOS Project",
                "homepage": "https://musl.libc.org",
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

        dpk = glob.glob(os.path.join(self.config.abs_output_dir, "musl-dev-*.dpk"))
        if not dpk:
            raise RecipeError("dpkbuild did not produce musl-dev-*.dpk in output/")
        self.log.info("Package: %s", dpk[0])
        return dpk[0]
