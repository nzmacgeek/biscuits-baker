"""Tests for helpers/password.py"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from helpers.password import set_root_password, _update_shadow, _ensure_passwd


class TestSetRootPassword:

    def test_raises_for_missing_sysroot(self, tmp_path):
        with pytest.raises(RuntimeError, match="Sysroot directory not found"):
            set_root_password(str(tmp_path / "no_such_sysroot"), "password")

    def test_creates_etc_shadow(self, tmp_path):
        sysroot = tmp_path / "sysroot"
        sysroot.mkdir()
        set_root_password(str(sysroot), "testpass")
        shadow = sysroot / "etc" / "shadow"
        assert shadow.exists(), "/etc/shadow should be created"

    def test_shadow_has_root_entry(self, tmp_path):
        sysroot = tmp_path / "sysroot"
        sysroot.mkdir()
        set_root_password(str(sysroot), "testpass")
        shadow = (sysroot / "etc" / "shadow").read_text()
        assert shadow.startswith("root:"), "First entry should be root"

    def test_shadow_root_entry_is_hashed(self, tmp_path):
        sysroot = tmp_path / "sysroot"
        sysroot.mkdir()
        set_root_password(str(sysroot), "testpass")
        shadow = (sysroot / "etc" / "shadow").read_text()
        root_line = [l for l in shadow.splitlines() if l.startswith("root:")][0]
        pw_hash = root_line.split(":")[1]
        assert pw_hash.startswith("$"), "Hash should start with $ (crypt format)"
        assert pw_hash != "testpass", "Plain text password should not be stored"

    def test_creates_etc_passwd(self, tmp_path):
        sysroot = tmp_path / "sysroot"
        sysroot.mkdir()
        set_root_password(str(sysroot), "testpass")
        passwd = sysroot / "etc" / "passwd"
        assert passwd.exists(), "/etc/passwd should be created"

    def test_passwd_has_root_entry(self, tmp_path):
        sysroot = tmp_path / "sysroot"
        sysroot.mkdir()
        set_root_password(str(sysroot), "testpass")
        passwd = (sysroot / "etc" / "passwd").read_text()
        assert "root:" in passwd

    def test_update_shadow_preserves_existing_entries(self, tmp_path):
        sysroot = tmp_path / "sysroot"
        etc = sysroot / "etc"
        etc.mkdir(parents=True)
        (etc / "shadow").write_text("daemon:!:0:0:99999:7:::\nnobody:!:0:0:99999:7:::\n")
        set_root_password(str(sysroot), "testpass")
        lines = (etc / "shadow").read_text().splitlines()
        names = [l.split(":")[0] for l in lines if l]
        assert "root" in names
        assert "daemon" in names
        assert "nobody" in names

    def test_update_shadow_replaces_existing_root(self, tmp_path):
        sysroot = tmp_path / "sysroot"
        etc = sysroot / "etc"
        etc.mkdir(parents=True)
        (etc / "shadow").write_text("root:OLD_HASH:0:0:99999:7:::\n")
        set_root_password(str(sysroot), "newpass")
        shadow = (etc / "shadow").read_text()
        assert "OLD_HASH" not in shadow
        root_line = [l for l in shadow.splitlines() if l.startswith("root:")][0]
        assert root_line.split(":")[1] != "OLD_HASH"

    def test_ensure_passwd_does_not_duplicate_root(self, tmp_path):
        sysroot = tmp_path / "sysroot"
        etc = sysroot / "etc"
        etc.mkdir(parents=True)
        (etc / "passwd").write_text("root:x:0:0:root:/root:/bin/sh\n")
        set_root_password(str(sysroot), "pass")
        lines = (etc / "passwd").read_text().splitlines()
        root_entries = [l for l in lines if l.startswith("root:")]
        assert len(root_entries) == 1, "Should have exactly one root entry"

    def test_shadow_permissions_enforced_on_existing_file(self, tmp_path):
        """Shadow file must be 0o600 even when it already existed."""
        sysroot = tmp_path / "sysroot"
        etc = sysroot / "etc"
        etc.mkdir(parents=True)
        shadow = etc / "shadow"
        shadow.write_text("root:OLD:0:0:99999:7:::\n")
        # Set overly permissive mode before the call
        shadow.chmod(0o644)
        set_root_password(str(sysroot), "newpass")
        mode = oct(shadow.stat().st_mode & 0o777)
        assert mode == oct(0o600), f"shadow should be 0o600, got {mode}"
