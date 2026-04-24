"""
recipes/binutils.py - GNU binutils for BlueyOS (i386 native, static musl).

Cross-compiles binutils to run ON i386 inside BlueyOS and produce i386
output (--host == --target == i686-linux-musl).

Binaries installed inside BlueyOS:
  /usr/bin/as       — GNU assembler
  /usr/bin/ld       — GNU linker
  /usr/bin/ar       — archive tool
  /usr/bin/ranlib   — index archives
  /usr/bin/nm       — symbol listing
  /usr/bin/objdump  — object file inspection
  /usr/bin/objcopy  — object file conversion
  /usr/bin/strip    — binary stripping
  /usr/bin/size     — section sizes
  /usr/bin/strings  — printable strings

Together with TCC (or GCC native), this provides a complete native
toolchain for self-hosted builds inside BlueyOS.
"""

from __future__ import annotations

import os

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "2.44"


class BinutilsRecipe(PortRecipe):
    name = "binutils"
    version = _VERSION
    description = "GNU binutils: as/ld/ar/nm/objdump/strip for i386 BlueyOS"
    dependencies = ["musl-blueyos"]
    install_paths = [
        "usr/bin/as",
        "usr/bin/ld",
        "usr/bin/ar",
        "usr/bin/nm",
        "usr/bin/strip",
        "usr/bin/objdump",
        "usr/bin/objcopy",
    ]
    pkg_depends = []

    tarball_url = f"https://ftp.gnu.org/gnu/binutils/binutils-{_VERSION}.tar.xz"
    tarball_name = f"binutils-{_VERSION}.tar.xz"
    src_subdir = f"binutils-{_VERSION}"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"binutils source not found at {src}. Run 'baker prepare' first."
            )

        env = self._cross_env(static=True)

        self.log.info("Configuring binutils %s for i386 static musl", self.version)
        import platform as _platform
        build_triple = f"{_platform.machine()}-linux-gnu"
        self.run(
            [
                "./configure",
                # binutils runs ON i686-linux-musl (inside BlueyOS)
                "--host=i686-linux-musl",
                # and produces output FOR i686-linux-musl
                "--target=i686-linux-musl",
                f"--build={build_triple}",
                "--prefix=/usr",
                "--disable-nls",
                "--disable-gdb",
                "--disable-gdbserver",
                "--disable-sim",
                "--disable-libdecnumber",
                "--disable-readline",
                "--disable-werror",
                "--disable-gprofng",
                "--without-zlib",
                "--without-zstd",
                "--without-debuginfod",
                "--without-babeltrace",
                "--without-system-zlib",
            ],
            cwd=src,
            env=env,
        )

        self.log.info("Building binutils %s", self.version)
        make_flags = self.config.kernel.make_flags.split()
        self.run(["make"] + make_flags, cwd=src, env=env)

    def install(self) -> None:
        src = self._source_dir
        staging = self._staging_dir
        os.makedirs(staging, exist_ok=True)

        self.log.info("Installing binutils into staging at %s", staging)
        self.run(["make", f"DESTDIR={staging}", "install-strip"], cwd=src)

        # Remove the target-prefixed duplicates — since host==target, both
        # /usr/bin/as and /usr/bin/i686-linux-musl-as are produced.
        # Keep only the unprefixed names so they work as plain 'as', 'ld' etc.
        import glob as _glob
        import os as _os
        bin_dir = _os.path.join(staging, "usr", "bin")
        for p in _glob.glob(_os.path.join(bin_dir, "i686-linux-musl-*")):
            _os.remove(p)
        # Also remove any i686-linux-musl/ subtree (target-specific sysroot dirs)
        import shutil as _shutil
        target_dir = _os.path.join(staging, "usr", "i686-linux-musl")
        if _os.path.isdir(target_dir):
            _shutil.rmtree(target_dir)
