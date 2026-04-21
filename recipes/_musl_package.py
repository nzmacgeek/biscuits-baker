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

    def _ensure_musl_specs(self) -> bool:
        """Ensure musl-gcc.specs exists for the resolved musl sysroot.

        Generates the file from the detected sysroot layout when it is
        missing.  Called before any configure step that invokes the
        musl-gcc compiler wrapper so that the CC probe succeeds.

        Returns True when specs are present (pre-existing or freshly generated).
        """
        from helpers.musl import ensure_musl_specs
        return ensure_musl_specs(self._resolve_musl_sysroot(), self.log)

    def _resolve_musl_sysroot(self) -> str:
        """Return the sysroot root that contains the musl-gcc wrapper.

        Used by configure-script-based builds (scout, claw) that need the
        prefix root where ``bin/musl-gcc`` lives.  Searches ``base`` first,
        then ``base/usr``, falling back to ``base`` when neither contains the
        wrapper.
        """
        base = self.config.abs_musl_prefix
        for candidate in [base, os.path.join(base, "usr")]:
            if os.path.isfile(os.path.join(candidate, "bin", "musl-gcc")):
                return candidate
        return base

    def _resolve_musl_make_prefix(self) -> str:
        """Return MUSL_PREFIX where ``include/`` and ``lib/libc.a`` are co-located.

        Package Makefiles (matey, yap, ...) derive paths as::

            MUSL_INCLUDE = $(MUSL_PREFIX)/include
            MUSL_LIB     = $(MUSL_PREFIX)/lib

        so the returned prefix must have musl headers directly under
        ``include/`` *and* ``libc.a`` directly under ``lib/``.  On hybrid
        sysroots (e.g. ``/opt/blueyos-sysroot``) the headers live at the
        root but ``libc.a`` is nested under ``usr/lib/`` -- in that case
        ``base/usr`` satisfies both requirements.

        Searches ``base`` then ``base/usr``; falls back to ``base`` for
        non-standard layouts.
        """
        base = self.config.abs_musl_prefix
        for candidate in [base, os.path.join(base, "usr")]:
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
