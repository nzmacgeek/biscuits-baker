"""
recipes/zlib.py - zlib 1.3.1 for BlueyOS (i386, static musl).

zlib uses its own non-autoconf configure that doesn't support --host,
so we pass CC/CFLAGS/LDFLAGS directly in the environment.  The resulting
static library (libz.a) and headers are merged into the sysroot so that
other ports (GCC, git, curl, ...) can find them at configure time.
"""

from __future__ import annotations

import os
import shutil

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "1.3.1"


class ZlibRecipe(PortRecipe):
    name = "zlib"
    version = _VERSION
    description = "zlib compression library (static, i386)"
    dependencies = ["musl-blueyos"]
    install_paths = ["usr/lib/libz.a", "usr/include/zlib.h"]
    pkg_depends = []

    tarball_url = f"https://zlib.net/zlib-{_VERSION}.tar.gz"
    tarball_name = f"zlib-{_VERSION}.tar.gz"
    src_subdir = f"zlib-{_VERSION}"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"zlib source not found at {src}. Run 'baker prepare' first."
            )

        env = self._cross_env(static=True)
        # zlib's configure script detects CC from environment; we also need
        # to pass CFLAGS so it generates a 32-bit library.  musl-gcc's specs
        # already force i386 code generation, but we add -m32 explicitly for
        # safety with zlib's Makefile substitution logic.
        env["CFLAGS"] = env.get("CFLAGS", "-O2") + " -m32"

        self.log.info("Configuring zlib %s", self.version)
        self.run(
            ["./configure", "--prefix=/usr", "--static"],
            cwd=src,
            env=env,
        )

        make_flags = self.config.kernel.make_flags.split()
        self.log.info("Building zlib %s", self.version)
        self.run(["make"] + make_flags, cwd=src, env=env)

    def install(self) -> None:
        src = self._source_dir
        staging = self._staging_dir
        os.makedirs(staging, exist_ok=True)

        self.log.info("Installing zlib into staging at %s", staging)
        self.run(["make", f"DESTDIR={staging}", "install"], cwd=src)

        # Merge into sysroot so GCC and other port builds can find -lz
        self._merge_into_sysroot(staging)

    def _merge_into_sysroot(self, staging: str) -> None:
        """Copy zlib headers and libs into sysroot/usr/{include,lib}."""
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
        self.log.info("Merged zlib into sysroot at %s", sysroot)
