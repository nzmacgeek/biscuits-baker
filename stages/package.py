"""
stages/package.py - Package stage for Baker.

Creates a discrete distributable archive for each successfully built
component and copies the finished packages to the ``core/`` directory.
"""

from __future__ import annotations

import os
import shutil

from stage_runner import Stage
from helpers.packaging import PackageBuilder


class PackageStage(Stage):
    """Package each built component into a distributable archive."""

    name = "package"

    def run(self) -> None:
        from recipe_registry import load_recipes

        cfg = self.config
        recipes = load_recipes(cfg)

        enabled_names = [
            c.name for c in cfg.components
            if c.enabled and c.name not in cfg.exclude
        ]

        if not enabled_names:
            self.log.warning("No components to package.")
            return

        builder = PackageBuilder(cfg.abs_output_dir)
        packages = []

        for name in enabled_names:
            recipe = recipes.get(name)
            if recipe is None:
                self.log.warning("No recipe for component: %s; skipping.", name)
                continue

            self.log.info("Packaging: %s %s", recipe.name, recipe.version)
            try:
                pkg_path = recipe.package()
                if pkg_path:
                    packages.append(pkg_path)
                    self.log.info("Package created: %s", pkg_path)
            except Exception as exc:  # noqa: BLE001
                self.log.error("Packaging failed for %s: %s", name, exc)

        # Copy finished packages to the core/ directory
        if packages:
            self._copy_to_core(packages)

        self.log.info(
            "Package stage complete.  %d package(s) created.", len(packages)
        )
        for pkg in packages:
            self.log.info("  %s", pkg)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _copy_to_core(self, packages: list) -> None:
        """Copy all built packages to the core packages directory."""
        core_dir = self.config.abs_core_packages_dir
        os.makedirs(core_dir, exist_ok=True)

        for pkg_path in packages:
            if not os.path.isfile(pkg_path):
                continue
            dest = os.path.join(core_dir, os.path.basename(pkg_path))
            shutil.copy2(pkg_path, dest)
            self.log.info("Copied to core: %s", dest)

        self.log.info(
            "Built packages available in: %s", core_dir
        )
