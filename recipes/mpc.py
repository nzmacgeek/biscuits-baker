"""
recipes/mpc.py - MPC 1.3.1 for BlueyOS (i386, static musl).

MPC depends on GMP and MPFR.  Both are expected to have been merged into
the sysroot by their respective recipes before this one runs.

After install, merge into sysroot for GCC to find at configure time.
"""

from __future__ import annotations

import os
import shutil

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "1.3.1"


class MpcRecipe(PortRecipe):
    name = "mpc"
    version = _VERSION
    description = "GNU Multiple Precision Complex Library (static, i386)"
    dependencies = ["musl-blueyos", "gmp", "mpfr"]
    install_paths = ["usr/lib/libmpc.a", "usr/include/mpc.h"]
    pkg_depends = ["gmp", "mpfr"]

    tarball_url = f"https://ftp.gnu.org/gnu/mpc/mpc-{_VERSION}.tar.gz"
    tarball_name = f"mpc-{_VERSION}.tar.gz"
    src_subdir = f"mpc-{_VERSION}"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"mpc source not found at {src}. Run 'baker prepare' first."
            )

        env = self._cross_env(static=True)
        sysroot = self.config.abs_sysroot
        make_flags = self.config.kernel.make_flags.split()

        # Remove libtool .la files from the sysroot before building.  GMP and
        # MPFR install .la files whose dependency_libs embed absolute paths to
        # the sysroot directory; when libtool reads them on a different machine
        # (or from a DESTDIR install), it can't find /usr/lib/libgmp.la and
        # fails.  Static archives (.a) are sufficient for our purely-static
        # cross build.
        for la in ("libgmp.la", "libmpfr.la"):
            la_path = os.path.join(sysroot, "usr", "lib", la)
            if os.path.exists(la_path):
                os.remove(la_path)
                self.log.info("Removed %s (libtool .la not needed for static build)", la)

        self.log.info("Configuring MPC %s for i686-linux-musl", self.version)
        self.run(
            [
                "./configure",
                *self._autoconf_host_flags,
                "--prefix=/usr",
                "--enable-static",
                "--disable-shared",
                # Use explicit lib/include dirs so libtool doesn't look for .la files
                f"--with-gmp-lib={sysroot}/usr/lib",
                f"--with-gmp-include={sysroot}/usr/include",
                f"--with-mpfr-lib={sysroot}/usr/lib",
                f"--with-mpfr-include={sysroot}/usr/include",
            ],
            cwd=src,
            env=env,
        )

        self.log.info("Building MPC %s", self.version)
        self.run(["make"] + make_flags, cwd=src, env=env)

    def install(self) -> None:
        src = self._source_dir
        staging = self._staging_dir
        os.makedirs(staging, exist_ok=True)

        self.log.info("Installing MPC into staging at %s", staging)
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
        self.log.info("Merged MPC into sysroot at %s", sysroot)
