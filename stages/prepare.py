"""
stages/prepare.py - Prepare stage for Baker.

Fetches/updates all source repositories (kernel, musl-blueyos, dimsim,
and all package repositories) and sets up directory structure.  Also
records the latest commit hash per repo so downstream stages can detect
when sources have changed.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from helpers.host_tools import build_host_env
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
            cfg.abs_core_packages_dir,
        ):
            os.makedirs(path, exist_ok=True)
            self.log.debug("Ensured directory: %s", path)

        # Fetch/update kernel repository (biscuits)
        self._fetch_repo(
            cfg.network.kernel_repo,
            cfg.network.kernel_branch,
            cfg.abs_kernel_source,
            label="kernel (biscuits)",
        )

        # Fetch musl-blueyos repository (goes into kernel source tree as musl-blueyos
        # so biscuits' tools/build-musl.sh can find it)
        if cfg.network.musl_blueyos_repo:
            musl_dest = os.path.join(cfg.abs_kernel_source, "musl-blueyos")
            self._fetch_repo(
                cfg.network.musl_blueyos_repo,
                cfg.network.musl_blueyos_branch,
                musl_dest,
                label="musl-blueyos",
            )

        if cfg.network.glibc_blueyos_repo:
            glibc_dest = os.path.join(cfg.abs_sources_dir, "glibc-blueyos")
            self._fetch_repo(
                cfg.network.glibc_blueyos_repo,
                cfg.network.glibc_blueyos_branch,
                glibc_dest,
                label="glibc-blueyos",
            )

        # Fetch dimsim repository
        if cfg.network.dimsim_repo:
            dimsim_dest = os.path.join(cfg.abs_sources_dir, "dimsim")
            self._fetch_repo(
                cfg.network.dimsim_repo,
                cfg.network.dimsim_branch,
                dimsim_dest,
                label="dimsim",
            )

        # Fetch all declared package repos
        for pr in cfg.network.package_repos:
            if pr.url:
                dest = os.path.join(cfg.abs_sources_dir, pr.name)
                self._fetch_repo(pr.url, pr.branch, dest, label=pr.name)

        # Fetch extra repos if defined
        for repo_url in cfg.network.extra_repos:
            self._clone_or_pull(repo_url, cfg.abs_sources_dir)

        # Detect and report changed repos since last prepare
        self._detect_changes()

        self.log.info("Prepare stage complete.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_repo(
        self, repo_url: str, branch: str, dest: str, label: str = ""
    ) -> None:
        if not repo_url:
            self.log.info("No URL configured for %s; skipping.", label or dest)
            return

        if os.path.isdir(os.path.join(dest, ".git")):
            self.log.info("Updating %s at %s", label or repo_url, dest)
            self._pull_latest(dest, branch, label or repo_url)
        else:
            self.log.info(
                "Cloning %s from %s (branch %s) → %s", label or repo_url, repo_url, branch, dest
            )
            os.makedirs(dest, exist_ok=True)
            self._git(
                ["git", "clone", "--branch", branch, "--depth", "1", repo_url, dest],
            )

    def _pull_latest(self, repo_dir: str, branch: str, label: str) -> None:
        """Fetch origin and reset the working tree to the latest commit on *branch*.

        Uses ``git checkout -B <branch> origin/<branch>`` so the checkout always
        lands on the configured branch regardless of what is currently checked
        out locally, and without requiring a fast-forward relationship.
        """
        if shutil.which("git") is None:
            return

        # Fetch the specific branch from origin
        result = subprocess.run(
            ["git", "fetch", "origin", branch],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            env=build_host_env(),
        )
        if result.returncode != 0:
            self.log.warning(
                "Failed to fetch origin/%s for %s: %s", branch, label, result.stderr.strip()
            )
            return

        # Reset local branch to match origin/<branch> exactly.
        # -B creates or resets the branch so we always end up on the right
        # branch even when the local checkout was pointing elsewhere.
        result = subprocess.run(
            ["git", "checkout", "-B", branch, f"origin/{branch}"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            env=build_host_env(),
        )
        if result.returncode != 0:
            self.log.warning(
                "Failed to checkout %s for %s: %s", branch, label, result.stderr.strip()
            )
        else:
            self.log.info("%s is now at origin/%s", label, branch)

    def _clone_or_pull(self, repo_url: str, base_dir: str) -> None:
        name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
        dest = os.path.join(base_dir, name)
        self._fetch_repo(repo_url, "main", dest, label=name)

    def _detect_changes(self) -> None:
        """Compare current HEAD hashes against stored state; log changed repos."""
        from helpers.change_detection import ChangeDetector

        cfg = self.config
        detector = ChangeDetector(cfg.abs_build_dir)

        repos_to_check: list[tuple[str, str]] = [
            ("biscuits", cfg.abs_kernel_source),
            ("musl-blueyos", os.path.join(cfg.abs_kernel_source, "musl-blueyos")),
            ("glibc-blueyos", os.path.join(cfg.abs_sources_dir, "glibc-blueyos")),
            ("dimsim", os.path.join(cfg.abs_sources_dir, "dimsim")),
        ]
        for pr in cfg.network.package_repos:
            repos_to_check.append((pr.name, os.path.join(cfg.abs_sources_dir, pr.name)))

        changed = []
        for name, path in repos_to_check:
            if os.path.isdir(os.path.join(path, ".git")):
                if detector.has_changed(name, path):
                    changed.append(name)
                    self.log.info("  [CHANGED] %s — will be rebuilt", name)
                else:
                    self.log.debug("  [unchanged] %s", name)

        if changed:
            self.log.info(
                "Changed repos detected (%d): %s", len(changed), ", ".join(changed)
            )
            detector.save_state(repos_to_check)
        else:
            self.log.info("No source changes detected since last prepare.")
            detector.save_state(repos_to_check)

    def _git(self, cmd: list, cwd: str = None) -> None:
        if shutil.which("git") is None:
            self.log.warning("git not found; skipping: %s", " ".join(cmd))
            return
        self.log.debug("git: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=build_host_env(),
        )
        if result.returncode != 0:
            self.log.warning("git command failed: %s\n%s", " ".join(cmd), result.stderr)
