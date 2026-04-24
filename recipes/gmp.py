"""
recipes/gmp.py - GMP 6.3.0 for BlueyOS (i386, static musl).

GMP is the first of the three GCC prerequisites (GMP → MPFR → MPC → GCC).
After building we install to staging AND merge into sysroot so that the
MPFR and MPC recipes can find gmp.h and libgmp.a at configure time.
"""

from __future__ import annotations

import os
import shutil

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "6.3.0"


class GmpRecipe(PortRecipe):
    name = "gmp"
    version = _VERSION
    description = "GNU Multiple Precision Arithmetic Library (static, i386)"
    dependencies = ["musl-blueyos"]
    install_paths = ["usr/lib/libgmp.a", "usr/include/gmp.h"]
    pkg_depends = []

    tarball_url = f"https://gmplib.org/download/gmp/gmp-{_VERSION}.tar.xz"
    tarball_name = f"gmp-{_VERSION}.tar.xz"
    src_subdir = f"gmp-{_VERSION}"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"gmp source not found at {src}. Run 'baker prepare' first."
            )

        env = self._cross_env(static=True)
        make_flags = self.config.kernel.make_flags.split()

        self.log.info("Configuring GMP %s for i686-linux-musl", self.version)
        self.run(
            [
                "./configure",
                *self._autoconf_host_flags,
                "--prefix=/usr",
                "--enable-static",
                "--disable-shared",
                "--disable-cxx",  # no C++ lib; keeps deps minimal
                "--with-pic",
            ],
            cwd=src,
            env=env,
        )

        self.log.info("Building GMP %s", self.version)
        self.run(["make"] + make_flags, cwd=src, env=env)

    def install(self) -> None:
        src = self._source_dir
        staging = self._staging_dir
        os.makedirs(staging, exist_ok=True)

        self.log.info("Installing GMP into staging at %s", staging)
        self.run(["make", f"DESTDIR={staging}", "install"], cwd=src)

        # Merge into sysroot so MPFR, MPC, and GCC can find it.
        self._merge_into_sysroot(staging)

    def _merge_into_sysroot(self, staging: str) -> None:
        sysroot = self.config.abs_sysroot
        for rel in (
            os.path.join("usr", "include"),
            os.path.join("usr", "lib"),
        ):
            src_dir = os.path.join(staging, rel)
            dst_dir = os.path.join(sysroot, rel)
            if not os.path.isdir(src_dir):
                continue
            os.makedirs(dst_dir, exist_ok=True)
            for item in os.listdir(src_dir):
                s = os.path.join(src_dir, item)
                d = os.path.join(dst_dir, item)
                if os.path.isfile(s):
                    shutil.copy2(s, d)
                elif os.path.isdir(s):
                    if os.path.exists(d):
                        shutil.rmtree(d)
                    shutil.copytree(s, d)
        self.log.info("Merged GMP into sysroot at %s", sysroot)
