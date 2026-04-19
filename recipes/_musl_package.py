"""
recipes/_musl_package.py - Shared base for musl-linked BlueyOS packages.

Provides ``MuslPackageRecipe``, a convenience subclass of
``BaseRecipe`` that:

* Sets ``CC`` / ``MUSL_PREFIX`` so ``make`` picks up the correct musl sysroot.
* After a successful ``make``, runs ``make package`` (which calls
    ``dpkbuild``) and requires a ``.dpk`` file.
* Copies the ``.dpk`` into ``output/`` for the PackageStage to collect.
"""

from __future__ import annotations

import glob
import os
import shutil

from recipes.base import BaseRecipe, RecipeError


class MuslPackageRecipe(BaseRecipe):
    """Base recipe for packages built against musl-blueyos."""

    #: Override in subclasses: path of the binary to install under sysroot/usr/bin/
    binary_name: str = ""
    #: Override in subclasses: sysroot-relative destination for the binary
    binary_dest: str = ""

    def __init__(self, config):
        super().__init__(config)
        self._source_dir = os.path.join(config.abs_sources_dir, self.name)

    def _resolve_musl_make_prefix(self) -> str:
        """Return MUSL_PREFIX path with include/lib expected by package Makefiles.

        Some environments provide a sysroot layout (<prefix>/usr/include, <prefix>/usr/lib),
        while others provide a direct musl prefix (<prefix>/include, <prefix>/lib).
        """
        base = self.config.abs_musl_prefix
        candidates = [base, os.path.join(base, "usr")]
        for candidate in candidates:
            include_dir = os.path.join(candidate, "include")
            libc_a = os.path.join(candidate, "lib", "libc.a")
            if os.path.isdir(include_dir) and os.path.isfile(libc_a):
                return candidate
        return base

    # ------------------------------------------------------------------
    # Template method implementations
    # ------------------------------------------------------------------

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"{self.name} source not found at {src}.  Run 'baker prepare' first."
            )

        musl_prefix = self._resolve_musl_make_prefix()
        self.log.info(
            "Building %s against musl at %s", self.name, musl_prefix
        )
        env = {"MUSL_PREFIX": musl_prefix}
        make_flags = self.config.kernel.make_flags.split()
        self.run(["make"] + make_flags, cwd=src, env=env)

    def install(self) -> None:
        src = self._source_dir
        build_out = os.path.join(src, "build", self.binary_name or self.name)

        if not os.path.isfile(build_out):
            # Try top-level binary name
            build_out = os.path.join(src, "build", self.name)
        if not os.path.isfile(build_out):
            self.log.warning(
                "Built binary not found for %s; skipping sysroot install.", self.name
            )
            return

        dest_rel = self.binary_dest or os.path.join("usr", "bin", self.binary_name or self.name)
        self.sysroot.install_binary(build_out, dest_rel)
        self.log.info("Installed %s → sysroot/%s", build_out, dest_rel)

    def package(self) -> str | None:
        """Build a required `.dpk` package for this component."""
        src = self._source_dir
        musl_prefix = self._resolve_musl_make_prefix()

        dpkbuild = self.resolve_dpkbuild()
        env = {
            "MUSL_PREFIX": musl_prefix,
            "PATH": os.path.dirname(dpkbuild) + ":" + os.environ.get("PATH", ""),
        }

        self.run(["make", "package"], cwd=src, env=env)

        dpk_files = glob.glob(os.path.join(src, "*.dpk"))
        if not dpk_files:
            raise RecipeError(
                f"make package completed for {self.name}, but no .dpk was produced in {src}"
            )

        dest = os.path.join(self.config.abs_output_dir, os.path.basename(dpk_files[0]))
        shutil.copy2(dpk_files[0], dest)
        self.log.info("Package: %s", dest)
        return dest
