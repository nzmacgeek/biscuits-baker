"""
stages/build.py - Build stage for Baker.

Resolves component build order, then runs configure + build + install
for each enabled component recipe.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from helpers.host_tools import build_host_env
from stage_runner import Stage
from deps import resolve_build_order


class BuildStage(Stage):
    """Build all enabled components in dependency order."""

    name = "build"
    target_component: str | None = None
    include_dependencies: bool = False
    check_main_updates: bool = False

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

        target = self.__class__.target_component
        include_deps = self.__class__.include_dependencies

        if target:
            if target not in enabled_names:
                raise RuntimeError(
                    f"Requested component '{target}' is not enabled (or is excluded) in baker.yaml."
                )
            if target not in recipes:
                raise RuntimeError(f"No recipe found for requested component: {target}")

            if include_deps:
                try:
                    build_order = resolve_build_order(recipes, enabled=[target])
                except Exception as exc:
                    raise RuntimeError(f"Dependency resolution failed: {exc}") from exc
            else:
                build_order = [target]
        else:
            # Resolve build order (handles dependency sorting)
            try:
                build_order = resolve_build_order(recipes, enabled=enabled_names)
            except Exception as exc:
                raise RuntimeError(f"Dependency resolution failed: {exc}") from exc

        self.log.info("Build order: %s", " → ".join(build_order))

        if target and self.__class__.check_main_updates:
            self.log.info("Checking for upstream updates on main before targeted build")
            for name in build_order:
                recipe = recipes.get(name)
                if recipe is None:
                    continue
                self._refresh_repo_main(recipe_name=name, repo_dir=recipe.source_dir)

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

    def _refresh_repo_main(self, recipe_name: str, repo_dir: str) -> None:
        """Fetch and fast-forward `main` when the recipe source is a git repo on main."""
        if shutil.which("git") is None:
            self.log.warning("git not found; skipping update check for %s", recipe_name)
            return

        git_dir = os.path.join(repo_dir, ".git")
        if not os.path.isdir(git_dir):
            self.log.debug("%s is not a git repo; skipping update check", repo_dir)
            return

        branch = self._git_capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)
        if not branch:
            self.log.warning("Unable to determine git branch for %s; skipping update check", recipe_name)
            return
        if branch != "main":
            self.log.info("%s is on branch '%s'; skipping auto-update (main only)", recipe_name, branch)
            return

        if not self._git_ok(["git", "fetch", "origin", "main"], cwd=repo_dir):
            self.log.warning("Failed to fetch origin/main for %s", recipe_name)
            return

        local_main = self._git_capture(["git", "rev-parse", "main"], cwd=repo_dir)
        origin_main = self._git_capture(["git", "rev-parse", "origin/main"], cwd=repo_dir)
        if not local_main or not origin_main:
            self.log.warning("Could not compare local main vs origin/main for %s", recipe_name)
            return

        if local_main == origin_main:
            self.log.info("%s is up to date on main", recipe_name)
            return

        self.log.info("Updating %s main branch (fast-forward)", recipe_name)
        if not self._git_ok(["git", "pull", "--ff-only", "origin", "main"], cwd=repo_dir):
            self.log.warning("Fast-forward pull failed for %s; continuing with current checkout", recipe_name)

    def _git_ok(self, cmd: list[str], cwd: str) -> bool:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=build_host_env(),
        )
        if result.returncode != 0:
            if result.stderr:
                self.log.debug(result.stderr.rstrip())
            return False
        return True

    def _git_capture(self, cmd: list[str], cwd: str) -> str | None:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=build_host_env(),
        )
        if result.returncode != 0:
            if result.stderr:
                self.log.debug(result.stderr.rstrip())
            return None
        return result.stdout.strip()
