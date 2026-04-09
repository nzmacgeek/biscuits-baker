"""
stages/prepare.py - Prepare stage for Baker.

Fetches/updates the kernel repository and all component sources.
Creates required output directories.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from stage_runner import Stage


class PrepareStage(Stage):
    """Fetch sources and set up directory structure."""

    name = "prepare"

    def run(self) -> None:
        cfg = self.config
        self.log.info("Preparing build environment")

        # Create required directories
        for path in (
            cfg.abs_sysroot,
            cfg.abs_output_dir,
            cfg.abs_build_dir,
            cfg.abs_sources_dir,
            cfg.abs_kernel_source,
        ):
            os.makedirs(path, exist_ok=True)
            self.log.debug("Ensured directory: %s", path)

        # Fetch/update kernel repository
        self._fetch_kernel()

        # Fetch extra repos if defined
        for repo_url in cfg.network.extra_repos:
            self._clone_or_pull(repo_url, cfg.abs_sources_dir)

        # Run fetch() for each enabled recipe
        self._fetch_components()

        self.log.info("Prepare stage complete.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_kernel(self) -> None:
        repo = self.config.network.kernel_repo
        branch = self.config.network.kernel_branch
        dest = self.config.abs_kernel_source

        if not repo:
            self.log.info("No kernel_repo configured; skipping kernel fetch.")
            return

        if os.path.isdir(os.path.join(dest, ".git")):
            self.log.info("Updating kernel repository at %s", dest)
            self._git(["git", "pull", "--ff-only"], cwd=dest)
        else:
            self.log.info("Cloning kernel from %s (branch %s) → %s", repo, branch, dest)
            os.makedirs(dest, exist_ok=True)
            self._git(
                ["git", "clone", "--branch", branch, "--depth", "1", repo, dest],
            )

    def _clone_or_pull(self, repo_url: str, base_dir: str) -> None:
        name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
        dest = os.path.join(base_dir, name)
        if os.path.isdir(os.path.join(dest, ".git")):
            self.log.info("Updating %s", name)
            self._git(["git", "pull", "--ff-only"], cwd=dest)
        else:
            self.log.info("Cloning %s → %s", repo_url, dest)
            self._git(["git", "clone", "--depth", "1", repo_url, dest])

    def _fetch_components(self) -> None:
        from recipe_registry import load_recipes

        recipes = load_recipes(self.config)
        enabled_names = {c.name for c in self.config.components if c.enabled}
        for name, recipe in recipes.items():
            if name in enabled_names:
                self.log.info("Fetching sources for: %s", name)
                try:
                    recipe.fetch()
                except Exception as exc:  # noqa: BLE001
                    self.log.warning("Fetch failed for %s: %s", name, exc)

    def _git(self, cmd: list, cwd: str = None) -> None:
        if shutil.which("git") is None:
            self.log.warning("git not found; skipping: %s", " ".join(cmd))
            return
        self.log.debug("git: %s", " ".join(cmd))
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            self.log.warning("git command failed: %s\n%s", " ".join(cmd), result.stderr)
