"""
recipes/_port_recipe.py - Base class for upstream tarball port recipes.

``PortRecipe`` handles the common lifecycle for ports that are built from
an upstream source tarball:

* ``fetch()``   — download and extract the tarball once (cached in build/tarballs/).
* ``build()``   — must be implemented by each subclass (configure + make).
* ``install()`` — must be implemented by each subclass (make install DESTDIR=staging).
* ``package()`` — shared: builds a .dpk from the staging tree using dpkbuild.

Cross-compilation helpers:
  ``_musl_gcc()``   — path to the musl-gcc wrapper.
  ``_cross_env()``  — CC/CFLAGS/LDFLAGS dict for static i386 musl builds.
  ``_autoconf_host`` — --host=i686-linux-musl --build=x86_64-linux-gnu flags.
"""

from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import tempfile
import urllib.request

from recipes.base import BaseRecipe, RecipeError, safe_extract
from recipes._musl_package import MuslPackageRecipe


class PortRecipe(MuslPackageRecipe):
    """Base recipe for a port built from an upstream source tarball."""

    #: Override in subclasses: full URL of the source tarball.
    tarball_url: str = ""

    #: Tarball filename on disk (derived from tarball_url if not set).
    tarball_name: str = ""

    #: Name of the subdirectory produced by extracting the tarball.
    #: e.g. "openssl-3.4.1" for openssl-3.4.1.tar.gz.
    src_subdir: str = ""

    #: Short human-readable description (used in the .dpk manifest).
    description: str = ""

    #: Runtime dependencies to declare in the .dpk manifest.
    pkg_depends: list = []

    def __init__(self, config):
        super().__init__(config)
        tbn = self.tarball_name or os.path.basename(self.tarball_url)
        self._tarball_cache = os.path.join(config.abs_build_dir, "tarballs")
        self._tarball_path = os.path.join(self._tarball_cache, tbn)
        # Port build tree lives under build/<name>/
        self._port_dir = os.path.join(config.abs_build_dir, self.name)
        # Extracted source (may contain a subdir)
        extract_base = os.path.join(self._port_dir, "src")
        if self.src_subdir:
            self._source_dir = os.path.join(extract_base, self.src_subdir)
        else:
            self._source_dir = extract_base
        self._extract_base = extract_base
        # Staging dir for make install DESTDIR=
        self._staging_dir = os.path.join(self._port_dir, "staging")

    # ------------------------------------------------------------------
    # fetch
    # ------------------------------------------------------------------

    def fetch(self) -> None:
        os.makedirs(self._tarball_cache, exist_ok=True)
        os.makedirs(self._extract_base, exist_ok=True)

        if not os.path.exists(self._tarball_path):
            self.log.info("Downloading %s", self.tarball_url)
            try:
                urllib.request.urlretrieve(self.tarball_url, self._tarball_path)
            except Exception as exc:
                raise RecipeError(
                    f"Failed to download {self.tarball_url}: {exc}"
                ) from exc

        if not os.path.exists(self._source_dir):
            self.log.info("Extracting %s", self._tarball_path)
            safe_extract(self._tarball_path, self._extract_base)

    # ------------------------------------------------------------------
    # Cross-compilation helpers
    # ------------------------------------------------------------------

    def _musl_gcc(self) -> str:
        """Return the absolute path to the musl-gcc wrapper."""
        musl_root = self._resolve_musl_sysroot()
        candidate = os.path.join(musl_root, "bin", "musl-gcc")
        if os.path.isfile(candidate):
            return candidate
        raise RecipeError(
            f"musl-gcc not found at {candidate}. Run 'baker toolchain' first."
        )

    def _cross_env(
        self,
        extra_cflags: str = "",
        extra_ldflags: str = "",
        static: bool = True,
    ) -> dict:
        """Return CC/CFLAGS/LDFLAGS/AR/RANLIB for static i386 musl cross-builds.

        Adds the sysroot usr/include and usr/lib so ports can find musl-built
        libraries (ncurses, openssl, ...) without extra incantations.
        """
        sysroot = self.config.abs_sysroot
        musl_gcc = self._musl_gcc()
        cflags_parts = [
            "-O2",
            f"-I{sysroot}/usr/include",
        ]
        if extra_cflags:
            cflags_parts.append(extra_cflags)
        ldflags_parts = [f"-L{sysroot}/usr/lib"]
        if static:
            ldflags_parts.append("-static")
        if extra_ldflags:
            ldflags_parts.append(extra_ldflags)
        return {
            "CC": musl_gcc,
            "CFLAGS": " ".join(cflags_parts),
            "LDFLAGS": " ".join(ldflags_parts),
            "AR": "ar",
            "RANLIB": "ranlib",
            "STRIP": "strip",
        }

    @property
    def _autoconf_host_flags(self) -> list[str]:
        """--host / --build flags for autoconf cross-compilation."""
        machine = platform.machine()
        build_triple = f"{machine}-linux-gnu"
        return [
            "--host=i686-linux-musl",
            f"--build={build_triple}",
        ]

    # ------------------------------------------------------------------
    # package (shared)
    # ------------------------------------------------------------------

    def package(self) -> str | None:
        """Build a .dpk from self._staging_dir using dpkbuild."""
        staging = self._staging_dir
        if not os.path.isdir(staging):
            raise RecipeError(
                f"{self.name}: staging dir not found at {staging}. "
                "Did install() run?"
            )

        dpkbuild = self.resolve_dpkbuild()

        with tempfile.TemporaryDirectory(prefix=f"{self.name}-pkg-") as pkg_dir:
            # Link or copy payload tree
            payload_dst = os.path.join(pkg_dir, "payload")
            shutil.copytree(staging, payload_dst, symlinks=True)

            # Write manifest
            meta_dir = os.path.join(pkg_dir, "meta", "scripts")
            os.makedirs(meta_dir, exist_ok=True)
            manifest = {
                "name": self.name,
                "version": self.version,
                "arch": "i386",
                "description": self.description or self.name,
                "depends": self.pkg_depends,
                "recommends": [],
                "conflicts": [],
                "provides": [],
                "maintainer": "BlueyOS Project",
                "homepage": "",
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
                spath = os.path.join(meta_dir, script)
                with open(spath, "w") as fh:
                    fh.write("#!/bin/sh\nexit 0\n")
                os.chmod(spath, 0o755)

            self.run([dpkbuild, "build", pkg_dir], cwd=self.config.abs_output_dir)

        dpk_files = glob.glob(
            os.path.join(self.config.abs_output_dir, f"{self.name}-*.dpk")
        )
        if not dpk_files:
            raise RecipeError(
                f"dpkbuild did not produce a {self.name}-*.dpk in output/"
            )

        self.log.info("Package: %s", dpk_files[0])
        return dpk_files[0]
