"""Tests for helpers/change_detection.py"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from helpers.change_detection import ChangeDetector


class TestChangeDetector:

    def test_first_run_all_changed(self, tmp_path):
        """With no prior state file every repo is considered changed."""
        detector = ChangeDetector(str(tmp_path))
        assert detector._prev_state == {}

    def test_has_changed_unknown_path(self, tmp_path):
        """Repo with non-git path: has_changed returns False (cannot read HEAD)."""
        detector = ChangeDetector(str(tmp_path))
        result = detector.has_changed("nonexistent", str(tmp_path / "no_such_repo"))
        assert result is False

    def test_save_and_reload_state(self, tmp_path):
        """State saved to disk is reloaded on next instantiation."""
        repos = [("repo-a", str(tmp_path / "a")), ("repo-b", str(tmp_path / "b"))]
        detector = ChangeDetector(str(tmp_path))

        # Manually inject known hashes
        state = {"repo-a": "aaa" * 13 + "aa", "repo-b": "bbb" * 13 + "bb"}
        os.makedirs(str(tmp_path), exist_ok=True)
        with open(os.path.join(str(tmp_path), ".baker_state.json"), "w") as f:
            json.dump(state, f)

        detector2 = ChangeDetector(str(tmp_path))
        assert detector2._prev_state.get("repo-a") == state["repo-a"]
        assert detector2._prev_state.get("repo-b") == state["repo-b"]

    def test_state_file_corrupt_does_not_crash(self, tmp_path):
        """A corrupt state file is ignored gracefully."""
        state_file = os.path.join(str(tmp_path), ".baker_state.json")
        with open(state_file, "w") as f:
            f.write("{INVALID JSON]]")
        detector = ChangeDetector(str(tmp_path))
        assert detector._prev_state == {}

    def test_changed_since_last_run_empty_list(self, tmp_path):
        detector = ChangeDetector(str(tmp_path))
        result = detector.changed_since_last_run([])
        assert result == []
