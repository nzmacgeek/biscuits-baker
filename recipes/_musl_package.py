"""
recipes/_musl_package.py - Shared base for musl-linked BlueyOS packages.

Provides ``MuslPackageRecipe``, a convenience subclass of
``BaseRecipe`` that:

* Sets ``CC`` / ``MUSL_PREFIX`` so ``make`` picks up the correct musl sysroot.
* After a successful ``make``, tries ``make package`` (which calls
  ``dpkbuild``) to produce a ``.dpk`` file.
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

    # ------------------------------------------------------------------
    # Template method implementations
    # ------------------------------------------------------------------

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"{self.name} source not found at {src}.  Run 'baker prepare' first."
            )

        musl_prefix = self.config.abs_musl_prefix
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
        """Try ``make package`` (dpkbuild) first; fall back to tar.gz."""
        src = self._source_dir
        musl_prefix = self.config.abs_musl_prefix

        dpkbuild_in_src = os.path.join(
            self.config.abs_sources_dir, "dimsim", "bin", "dpkbuild"
        )
        dpkbuild = (
            shutil.which("dpkbuild")
            or (dpkbuild_in_src if os.path.isfile(dpkbuild_in_src) else None)
        )

        if dpkbuild and os.path.isdir(src):
            env = {
                "MUSL_PREFIX": musl_prefix,
                "PATH": os.path.dirname(dpkbuild) + ":" + os.environ.get("PATH", ""),
            }
            try:
                self.run(["make", "package"], cwd=src, env=env)
                # Find the produced .dpk file and copy it to output/
                dpk_files = glob.glob(os.path.join(src, "*.dpk"))
                if dpk_files:
                    dest = os.path.join(self.config.abs_output_dir, os.path.basename(dpk_files[0]))
                    shutil.copy2(dpk_files[0], dest)
                    self.log.info("Package: %s", dest)
                    return dest
            except RecipeError as exc:
                self.log.warning(
                    "make package failed for %s: %s; falling back to tar.gz", self.name, exc
                )

        # Fallback: produce a tar.gz from the sysroot install paths
        from helpers.packaging import PackageBuilder

        builder = PackageBuilder(self.config.abs_output_dir)
        paths = self.install_paths or None
        return builder.build_package(
            name=self.name,
            version=self.version,
            sysroot=self.config.abs_sysroot,
            include_paths=paths,
            metadata={"arch": self.config.arch},
        )
