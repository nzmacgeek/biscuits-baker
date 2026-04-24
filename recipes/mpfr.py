"""
recipes/mpfr.py - MPFR 4.2.1 for BlueyOS (i386, static musl).

MPFR depends on GMP.  We expect GMP to have been merged into the sysroot
already (gmp recipe's install() does this), so the standard _cross_env
CFLAGS/LDFLAGS pointing at sysroot/usr are sufficient.

After install, merge into sysroot for MPC and GCC to find.
"""

from __future__ import annotations

import os
import shutil

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "4.2.1"


class MpfrRecipe(PortRecipe):
    name = "mpfr"
    version = _VERSION
    description = "GNU Multiple Precision Floating-Point Library (static, i386)"
    dependencies = ["musl-blueyos", "gmp"]
    install_paths = ["usr/lib/libmpfr.a", "usr/include/mpfr.h"]
    pkg_depends = ["gmp"]

    tarball_url = f"https://ftp.gnu.org/gnu/mpfr/mpfr-{_VERSION}.tar.xz"
    tarball_name = f"mpfr-{_VERSION}.tar.xz"
    src_subdir = f"mpfr-{_VERSION}"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"mpfr source not found at {src}. Run 'baker prepare' first."
            )

        env = self._cross_env(static=True)
        sysroot = self.config.abs_sysroot
        make_flags = self.config.kernel.make_flags.split()

        self.log.info("Configuring MPFR %s for i686-linux-musl", self.version)
        self.run(
            [
                "./configure",
                *self._autoconf_host_flags,
                "--prefix=/usr",
                "--enable-static",
                "--disable-shared",
                # GMP was merged into sysroot/usr by the gmp recipe
                f"--with-gmp={sysroot}/usr",
            ],
            cwd=src,
            env=env,
        )

        self.log.info("Building MPFR %s", self.version)
        self.run(["make"] + make_flags, cwd=src, env=env)

    def install(self) -> None:
        src = self._source_dir
        staging = self._staging_dir
        os.makedirs(staging, exist_ok=True)

        self.log.info("Installing MPFR into staging at %s", staging)
        self.run(["make", f"DESTDIR={staging}", "install"], cwd=src)

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
        self.log.info("Merged MPFR into sysroot at %s", sysroot)
