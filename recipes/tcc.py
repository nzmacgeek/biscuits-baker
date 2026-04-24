"""
recipes/tcc.py - TinyCC (TCC) for BlueyOS (i386 native, static musl).

TinyCC is a compact C99/C11 compiler that includes its own ELF linker.
Cross-compiled here to run natively ON i386 (inside BlueyOS) and TARGET
i386, it forms the foundation of the self-hosting toolchain:

  tcc hello.c -o hello     # compiles and links in one step

TCC is configured so that at runtime inside BlueyOS it finds:
  /usr/include/       — musl headers  (from musl-dev package)
  /usr/lib/libc.a     — musl static lib
  /usr/lib/crt1.o     — musl CRT start file

The TCC binary is statically linked against musl (no runtime deps).
"""

from __future__ import annotations

import os
import shutil

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "0.9.27"


class TccRecipe(PortRecipe):
    name = "tcc"
    version = _VERSION
    description = "TinyCC — lightweight self-hosting C99/C11 compiler (i386)"
    dependencies = ["musl-blueyos", "musl-dev"]
    install_paths = ["usr/bin/tcc", "usr/lib/tcc"]
    pkg_depends = ["musl-dev"]

    tarball_url = f"http://download.savannah.gnu.org/releases/tinycc/tcc-{_VERSION}.tar.bz2"
    tarball_name = f"tcc-{_VERSION}.tar.bz2"
    src_subdir = f"tcc-{_VERSION}"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"tcc source not found at {src}. Run 'baker prepare' first."
            )

        musl_gcc = self._musl_gcc()
        sysroot = self.config.abs_sysroot

        self.log.info("Configuring TCC %s (i386 host + target)", self.version)
        # TCC uses its own non-autoconf configure script.
        # --cc            : compiler used to BUILD tcc (musl-gcc → i386 binary)
        # --cpu           : CPU tcc will TARGET at runtime inside BlueyOS
        # --crtprefix     : where tcc looks for crt1.o etc. inside BlueyOS
        # --libpaths      : where tcc looks for .a libs inside BlueyOS
        # --sysincludepaths: where tcc looks for headers inside BlueyOS
        self.run(
            [
                "./configure",
                f"--cc={musl_gcc}",
                "--cpu=i386",
                "--prefix=/usr",
                "--tccdir=/usr/lib/tcc",
                "--crtprefix=/usr/lib",
                "--libpaths=/usr/lib",
                "--sysincludepaths=/usr/include",
                "--extra-cflags=-O2",
                "--extra-ldflags=-static",
            ],
            cwd=src,
        )

        self.log.info("Building TCC %s", self.version)
        make_flags = self.config.kernel.make_flags.split()
        self.run(["make"] + make_flags, cwd=src)

    def install(self) -> None:
        src = self._source_dir
        staging = self._staging_dir
        os.makedirs(staging, exist_ok=True)

        self.log.info("Installing TCC into staging at %s", staging)
        self.run(["make", f"DESTDIR={staging}", "install"], cwd=src)

        # Strip the binary to reduce size (TCC is already small but let's keep it tidy)
        tcc_bin = os.path.join(staging, "usr", "bin", "tcc")
        if os.path.isfile(tcc_bin):
            self.run(["strip", tcc_bin])
