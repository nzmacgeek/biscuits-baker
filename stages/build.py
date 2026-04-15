"""
stages/build.py - Build stage for Baker.

Resolves component build order, then runs configure + build + install
for each enabled component recipe.
"""

from __future__ import annotations

from stage_runner import Stage
from deps import resolve_build_order


class BuildStage(Stage):
    """Build all enabled components in dependency order."""

    name = "build"

    def run(self) -> None:
        from recipe_registry import load_recipes

        cfg = self.config
        recipes = load_recipes(cfg)

        # Filter to enabled components (minus excluded)
        enabled_names = [
            c.name for c in cfg.components
            if c.enabled and c.name not in cfg.exclude
        ]

        if not enabled_names:
            self.log.warning("No components enabled for build.  Check baker.yaml.")
            return

        # Resolve build order (handles dependency sorting)
        try:
            build_order = resolve_build_order(recipes, enabled=enabled_names)
        except Exception as exc:
            raise RuntimeError(f"Dependency resolution failed: {exc}") from exc

        self.log.info("Build order: %s", " → ".join(build_order))

        failed = []
        for name in build_order:
            recipe = recipes.get(name)
            if recipe is None:
                self.log.warning("No recipe found for component: %s", name)
                continue

            self.log.info("-" * 50)
            self.log.info("Component: %s %s", recipe.name, recipe.version)
            self.log.info("-" * 50)

            try:
                self.log.info("[%s] fetch", name)
                recipe.fetch()
                self.log.info("[%s] configure", name)
                recipe.configure()
                self.log.info("[%s] build", name)
                recipe.build()
                self.log.info("[%s] install", name)
                recipe.install()
                self.log.info("[%s] done", name)
            except Exception as exc:  # noqa: BLE001
                self.log.error("[%s] FAILED: %s", name, exc)
                failed.append(name)

        if failed:
            raise RuntimeError(f"Build failed for components: {', '.join(failed)}")

        self.log.info("Build stage complete.")
