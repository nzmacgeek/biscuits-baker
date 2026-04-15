"""
helpers/change_detection.py - Git-based change detection for Baker.

Tracks the HEAD commit hash of each source repository between runs.
A repository is considered "changed" when its current HEAD differs from
the hash that was recorded during the previous prepare stage.

State is stored in ``<build_dir>/.baker_state.json``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_STATE_FILE = ".baker_state.json"


class ChangeDetector:
    """Detects source changes in a set of git repositories."""

    def __init__(self, build_dir: str) -> None:
        self.build_dir = os.path.abspath(build_dir)
        self._state_file = os.path.join(self.build_dir, _STATE_FILE)
        self._prev_state: Dict[str, str] = self._load_state()
        self._current_state: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def has_changed(self, name: str, repo_path: str) -> bool:
        """Return True if *repo_path* has a different HEAD than the last run.

        On the very first run (no stored state) every repo is considered changed.

        Args:
            name:      Logical name of the repository (key in state file).
            repo_path: Absolute path to the checked-out repository.
        """
        current = self._head_hash(repo_path)
        if current is None:
            logger.debug("Cannot read HEAD for %s at %s; assuming unchanged.", name, repo_path)
            return False

        self._current_state[name] = current
        previous = self._prev_state.get(name)
        changed = previous is None or previous != current

        if changed:
            logger.debug(
                "%s: HEAD changed %s → %s", name, previous or "(new)", current[:12]
            )
        return changed

    def save_state(self, repos: List[Tuple[str, str]]) -> None:
        """Persist the current HEAD hashes for all *repos* to the state file.

        Args:
            repos: List of ``(name, path)`` tuples.
        """
        os.makedirs(self.build_dir, exist_ok=True)
        state: Dict[str, str] = {}
        for name, path in repos:
            h = self._head_hash(path)
            if h:
                state[name] = h
        try:
            with open(self._state_file, "w") as fh:
                json.dump(state, fh, indent=2)
            logger.debug("Saved repo state to %s", self._state_file)
        except OSError as exc:
            logger.warning("Could not save change-detection state: %s", exc)

    def changed_since_last_run(self, repos: List[Tuple[str, str]]) -> List[str]:
        """Return the names of repos that changed since the last saved state.

        Args:
            repos: List of ``(name, path)`` tuples.
        """
        return [name for name, path in repos if self.has_changed(name, path)]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_state(self) -> Dict[str, str]:
        if not os.path.isfile(self._state_file):
            return {}
        try:
            with open(self._state_file) as fh:
                data = json.load(fh)
            return {k: v for k, v in data.items() if isinstance(v, str)}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load change-detection state: %s", exc)
            return {}

    @staticmethod
    def _head_hash(repo_path: str) -> Optional[str]:
        """Return the full HEAD commit hash for the git repo at *repo_path*, or None."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None
