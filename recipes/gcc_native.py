"""
recipes/gcc_native.py - GCC 14.2.0 native for BlueyOS (i386, static musl).

Builds a GCC that:
  - runs ON i686-linux-musl (inside BlueyOS)
  - targets i686-linux-musl (produces i386 ELF output)

Prerequisites (expected to be in the sysroot already):
  - zlib   (libz.a + zlib.h)
  - GMP    (libgmp.a + gmp.h)
  - MPFR   (libmpfr.a + mpfr.h)
  - MPC    (libmpc.a + mpc.h)
  - binutils (provides as/ld at /usr/bin inside the OS)
  - musl-dev (headers + libs for linking C programs)

The GCC build is VERY long (~30-60 min on modern hardware).  Baker runs
it lazily when invoked; the recipe just writes down the correct build
procedure.

Installed inside BlueyOS:
  /usr/bin/gcc         — C compiler
  /usr/bin/g++         — C++ compiler (if c++ enabled)
  /usr/bin/cpp         — C preprocessor
  /usr/libexec/gcc/    — internal GCC executables (cc1, collect2, ...)
  /usr/lib/gcc/        — internal GCC libraries (libgcc.a, crtbegin.o, ...)
"""

from __future__ import annotations

import os
import platform

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "14.2.0"


class GccNativeRecipe(PortRecipe):
    name = "gcc-native"
    version = _VERSION
    description = "GCC C/C++ compiler running natively on i386 BlueyOS"
    dependencies = ["musl-blueyos", "zlib", "gmp", "mpfr", "mpc", "binutils"]
    # Minimal install_paths check — just verify the compiler binary appears
    install_paths = ["usr/bin/gcc"]
    pkg_depends = ["musl-dev", "binutils", "gmp", "mpfr", "mpc"]

    tarball_url = f"https://ftp.gnu.org/gnu/gcc/gcc-{_VERSION}/gcc-{_VERSION}.tar.xz"
    tarball_name = f"gcc-{_VERSION}.tar.xz"
    src_subdir = f"gcc-{_VERSION}"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"GCC source not found at {src}. Run 'baker prepare' first."
            )

        # GCC must be built in a separate build directory (in-tree builds
        # are unsupported by GCC upstream).
        build_dir = os.path.join(self._port_dir, "build")
        os.makedirs(build_dir, exist_ok=True)

        env = self._cross_env(static=True)
        sysroot = self.config.abs_sysroot
        musl_gcc = self._musl_gcc()
        machine = platform.machine()

        make_flags = self.config.kernel.make_flags.split()

        self.log.info("Configuring GCC %s for i686-linux-musl native", self.version)
        self.run(
            [
                os.path.join(src, "configure"),
                # GCC will RUN on i686-linux-musl (inside BlueyOS)
                "--host=i686-linux-musl",
                # GCC will PRODUCE code for i686-linux-musl
                "--target=i686-linux-musl",
                # We are BUILDING on the host x86_64 machine
                f"--build={machine}-linux-gnu",
                "--prefix=/usr",
                # C only for the first native compiler; no C++ until we have
                # a proper musl-g++ cross-wrapper for the Canadian cross build.
                "--enable-languages=c",
                "--disable-multilib",
                # No bootstrap: we're cross-compiling, not building on the target
                "--disable-bootstrap",
                "--disable-nls",
                "--disable-werror",
                "--disable-libgomp",
                "--disable-libssp",
                "--disable-libquadmath",
                "--disable-libsanitizer",
                "--disable-libvtv",
                "--disable-libcc1",
                "--disable-shared",   # produce static host binaries
                "--enable-static",
                "--without-isl",      # skip Graphite optimisation (avoids ISL dep)
                # GMP/MPFR/MPC merged into sysroot/usr by their own recipes
                f"--with-gmp={sysroot}/usr",
                f"--with-mpfr={sysroot}/usr",
                f"--with-mpc={sysroot}/usr",
                # zlib merged into sysroot/usr
                f"--with-zlib={sysroot}/usr",
                # Sysroot for the INSTALLED compiler targeting BlueyOS
                "--with-sysroot=/",
                "--with-native-system-header-dir=/usr/include",
                # Build-machine compilers (x86_64 host gcc for build-side tools)
                "CC_FOR_BUILD=gcc",
                "CXX_FOR_BUILD=g++",
                # Host compiler: musl-gcc cross-compiles FROM x86_64 TO i686
                f"CC={musl_gcc}",
                f"CFLAGS=-O2 -I{sysroot}/usr/include",
                f"LDFLAGS=-L{sysroot}/usr/lib -static",
                "CFLAGS_FOR_TARGET=-O2",
            ],
            cwd=build_dir,
            env=env,
        )

        self.log.info("Building GCC %s (this will take a while)", self.version)
        self.run(
            ["make", "MAKEINFO=true", "all-gcc", "all-target-libgcc"] + make_flags,
            cwd=build_dir,
            env=env,
        )

    def install(self) -> None:
        build_dir = os.path.join(self._port_dir, "build")
        staging = self._staging_dir
        os.makedirs(staging, exist_ok=True)

        self.log.info("Installing GCC into staging at %s", staging)
        self.run(
            [
                "make",
                "MAKEINFO=true",
                f"DESTDIR={staging}",
                "install-gcc",
                "install-target-libgcc",
            ],
            cwd=build_dir,
        )

        # Remove the target-prefixed symlinks (i686-linux-musl-gcc etc.);
        # since host==target they duplicate the plain names.
        import glob as _glob
        bin_dir = os.path.join(staging, "usr", "bin")
        for p in _glob.glob(os.path.join(bin_dir, "i686-linux-musl-*")):
            os.remove(p)

        # Sanity check: verify the installed gcc binary is 32-bit ELF.
        import subprocess as _sp
        gcc_bin = os.path.join(bin_dir, "gcc")
        if os.path.isfile(gcc_bin):
            result = _sp.run(["file", gcc_bin], capture_output=True, text=True)
            if "ELF 32-bit" not in result.stdout:
                raise RecipeError(
                    f"Installed gcc is not a 32-bit ELF binary! file output:\n"
                    f"{result.stdout}"
                )
