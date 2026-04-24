"""
recipes/dimsim.py - Recipe for dimsim package manager.

dimsim is written in C.  Building it produces two static binaries:
``bin/dimsim`` and ``bin/dpkbuild``.

Two build passes are performed in order:
1. BlueyOS target build (musl-gcc, static i386) — stashed as
   ``bin/dimsim.target`` and ``bin/dpkbuild.target``.
2. Host build (native gcc, dynamic) — overwrites ``bin/dimsim`` and
   ``bin/dpkbuild`` so that resolve_dpkbuild() finds a host-runnable
   binary for subsequent packaging calls.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from recipes.base import RecipeError
from recipes._musl_package import MuslPackageRecipe


class DimsimRecipe(MuslPackageRecipe):
    """dimsim package manager and dpkbuild tool."""

    name = "dimsim"
    version = "0.1.0"
    dependencies: list = []
    install_paths = ["usr/bin/dimsim", "usr/bin/dpkbuild"]

    def __init__(self, config):
        super().__init__(config)
        self._source_dir = os.path.join(config.abs_sources_dir, "dimsim")

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"dimsim source not found at {src}.  Run 'baker prepare' first."
            )

        # BlueyOS target build — static i386 against musl.  Done FIRST so that
        # the host build can overwrite bin/ afterwards (leaving host-runnable
        # binaries there for resolve_dpkbuild()).
        musl_gcc = self._find_musl_gcc()
        self.log.info("Building dimsim/dpkbuild for BlueyOS target via %s", musl_gcc)
        self.run(
            ["make", "blueyos", f"MUSL_CC={musl_gcc}"],
            cwd=src,
        )
        # Stash target binaries so install() can pick them up after the host
        # build overwrites bin/.
        for binary in ("bin/dimsim", "bin/dpkbuild"):
            src_path = os.path.join(src, binary)
            if not os.path.isfile(src_path):
                raise RecipeError(f"BlueyOS build: expected binary not found: {binary}")
            shutil.copy2(src_path, src_path + ".target")

        # Host build — native gcc (no -static to avoid glibc-static NSS issues).
        # Overwrites bin/ so that resolve_dpkbuild() finds a host-runnable binary.
        self.log.info("Building dimsim/dpkbuild for host (native, dynamic)")
        self.run(["make", "STATIC=0"], cwd=src)
        for binary in ("bin/dimsim", "bin/dpkbuild"):
            if not os.path.isfile(os.path.join(src, binary)):
                raise RecipeError(f"Host build: expected binary not found: {binary}")
        self.log.info("dimsim build complete (blueyos target + host)")

    def install(self) -> None:
        src = self._source_dir
        usr_bin = self.sysroot.ensure_dir("usr", "bin")

        for binary in ("bin/dimsim", "bin/dpkbuild"):
            # Prefer the BlueyOS target binary stashed as <binary>.target
            target_path = os.path.join(src, binary + ".target")
            src_path = os.path.join(src, binary)
            chosen = target_path if os.path.isfile(target_path) else src_path
            if os.path.isfile(chosen):
                dest = os.path.join(usr_bin, os.path.basename(binary))
                shutil.copy2(chosen, dest)
                os.chmod(dest, 0o755)
                self.log.info("Installed %s → %s", chosen, dest)

    def package(self) -> str | None:
        src = self._source_dir
        dpkbuild = self.resolve_dpkbuild()

        # Build a temporary package tree for dimsim itself using the BlueyOS
        # target binaries (stashed as <binary>.target during build()).
        import glob as _glob
        with tempfile.TemporaryDirectory(prefix="dimsim-pkg-") as pkg_dir:
            payload_bin = os.path.join(pkg_dir, "payload", "usr", "bin")
            os.makedirs(payload_bin, exist_ok=True)
            for binary in ("bin/dimsim", "bin/dpkbuild"):
                # Prefer the target binary; fall back to whatever is in bin/.
                target_path = os.path.join(src, binary + ".target")
                fallback = os.path.join(src, binary)
                chosen = target_path if os.path.isfile(target_path) else fallback
                if not os.path.isfile(chosen):
                    raise RecipeError(f"dimsim binary missing for packaging: {binary}")
                dest = os.path.join(payload_bin, os.path.basename(binary))
                shutil.copy2(chosen, dest)
                os.chmod(dest, 0o755)

            meta_dir = os.path.join(pkg_dir, "meta", "scripts")
            os.makedirs(meta_dir, exist_ok=True)
            manifest = {
                "name": "dimsim",
                "version": self.version,
                "arch": "i386",
                "description": "BlueyOS package manager (dimsim) and package builder (dpkbuild)",
                "depends": [],
                "recommends": [],
                "conflicts": [],
                "provides": ["package-manager"],
                "maintainer": "BlueyOS Project",
                "homepage": "https://github.com/nzmacgeek/dimsim",
                "files": [],
                "scripts": {},
            }
            with open(os.path.join(pkg_dir, "meta", "manifest.json"), "w") as fh:
                json.dump(manifest, fh, indent=2)

            for script in ("preinst", "postinst", "prerm", "postrm"):
                script_path = os.path.join(meta_dir, script)
                with open(script_path, "w") as fh:
                    fh.write("#!/bin/sh\nexit 0\n")
                os.chmod(script_path, 0o755)

            self.run([dpkbuild, "build", pkg_dir], cwd=self.config.abs_output_dir)

        dpk_files = _glob.glob(
            os.path.join(self.config.abs_output_dir, "dimsim-*.dpk")
        )
        if not dpk_files:
            raise RecipeError("dpkbuild did not produce a dimsim-*.dpk in output/")

        self.log.info("Package: %s", dpk_files[0])
        return dpk_files[0]

    def _find_musl_gcc(self) -> str:
        """Return path to a musl-gcc wrapper suitable for BlueyOS i386 builds."""
        musl_root = self._resolve_musl_sysroot()
        for candidate in [
            os.path.join(musl_root, "bin", "musl-gcc"),
            shutil.which("musl-gcc") or "",
        ]:
            if candidate and os.path.isfile(candidate):
                return candidate
        raise RecipeError(
            f"musl-gcc not found under {musl_root}. Run 'baker toolchain' first."
        )
