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

        # Clean any stale objects from a previous build attempt before
        # rebuilding.  This ensures a consistent state regardless of whether
        # baker was run before.
        self.run(["make", "clean"], cwd=src)

        self.log.info("Building TCC %s", self.version)
        make_flags = self.config.kernel.make_flags.split()
        # Two extra make variables are required for a correct cross-build:
        #
        # i386-libtcc1-usegcc=yes
        #   By default, lib/Makefile builds libtcc1.a by running the just-
        #   built TCC binary.  Since that binary is i386 and we are on
        #   x86_64, it cannot execute → libtcc1.a is never produced.  This
        #   flag switches libtcc1.a compilation to use $(CC) (musl-gcc) and
        #   ar instead, which works correctly in the cross-build environment.
        #
        # CONFIG_musl=yes
        #   lib/Makefile includes bcheck.o by default.  bcheck.c uses
        #   glibc-only malloc hooks (__malloc_hook etc.) that do not exist in
        #   musl, causing compilation errors.  CONFIG_musl=yes sets BCHECK_O=
        #   (empty), omitting bcheck.o from libtcc1.a.
        self.run(
            [
                "make",
                "i386-libtcc1-usegcc=yes",
                "CONFIG_musl=yes",
            ]
            + make_flags,
            cwd=src,
        )

        # Verify both artefacts were produced.
        # Note: lib/Makefile creates the archive as ../libtcc1.a (one level up
        # from lib/), so the file lands at the root of the TCC source tree.
        tcc_bin = os.path.join(src, "tcc")
        libtcc1 = os.path.join(src, "libtcc1.a")
        if not os.path.isfile(tcc_bin):
            raise RecipeError("TCC binary not produced after make")
        if not os.path.isfile(libtcc1):
            raise RecipeError(
                "libtcc1.a not produced — TCC cannot link programs "
                "without it.  Check that musl-gcc is in PATH and "
                "i386-libtcc1-usegcc=yes took effect."
            )

        import subprocess as _sp
        result = _sp.run(["file", tcc_bin], capture_output=True, text=True)
        if "ELF 32-bit" not in result.stdout:
            raise RecipeError(
                f"TCC binary is not 32-bit ELF: {result.stdout.strip()}"
            )
        self.log.info("TCC binary OK: %s", result.stdout.strip())

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
