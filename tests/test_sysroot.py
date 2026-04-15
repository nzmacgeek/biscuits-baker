"""Tests for helpers/sysroot.py - Sysroot installation helpers."""

from __future__ import annotations

import os
import sys
import stat

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from helpers.sysroot import SysrootInstaller


class TestSysrootInstaller:
    def test_ensure_dir_creates_directory(self, tmp_path):
        sysroot = str(tmp_path / "sysroot")
        installer = SysrootInstaller(sysroot)
        path = installer.ensure_dir("usr", "bin")
        assert os.path.isdir(path)

    def test_create_standard_layout(self, tmp_path):
        sysroot = str(tmp_path / "sysroot")
        installer = SysrootInstaller(sysroot)
        installer.create_standard_layout()
        for required in ("bin", "etc", "usr/bin", "usr/lib", "usr/include"):
            assert os.path.isdir(os.path.join(sysroot, required)), \
                f"Missing sysroot dir: {required}"

    def test_install_file(self, tmp_path):
        sysroot = str(tmp_path / "sysroot")
        installer = SysrootInstaller(sysroot)

        src = tmp_path / "hello"
        src.write_text("hello world")

        dest = installer.install_file(str(src), "usr/share/hello", mode=0o644)
        assert os.path.exists(dest)
        assert open(dest).read() == "hello world"

    def test_install_file_sets_mode(self, tmp_path):
        sysroot = str(tmp_path / "sysroot")
        installer = SysrootInstaller(sysroot)

        src = tmp_path / "exec"
        src.write_text("#!/bin/sh")

        dest = installer.install_binary(str(src), "usr/bin/exec")
        assert os.path.exists(dest)
        st = os.stat(dest)
        assert st.st_mode & 0o111  # executable bit set

    def test_install_tree(self, tmp_path):
        sysroot = str(tmp_path / "sysroot")
        installer = SysrootInstaller(sysroot)

        src_dir = tmp_path / "src_tree"
        src_dir.mkdir()
        (src_dir / "a.txt").write_text("a")
        (src_dir / "sub").mkdir()
        (src_dir / "sub" / "b.txt").write_text("b")

        installer.install_tree(str(src_dir), "usr/share/myapp")
        assert os.path.exists(os.path.join(sysroot, "usr/share/myapp/a.txt"))
        assert os.path.exists(os.path.join(sysroot, "usr/share/myapp/sub/b.txt"))

    def test_symlink(self, tmp_path):
        sysroot = str(tmp_path / "sysroot")
        installer = SysrootInstaller(sysroot)
        installer.ensure_dir("usr/bin")

        link = installer.symlink("busybox", "usr/bin/sh")
        assert os.path.islink(link)
        assert os.readlink(link) == "busybox"

    def test_exists(self, tmp_path):
        sysroot = str(tmp_path / "sysroot")
        installer = SysrootInstaller(sysroot)
        installer.ensure_dir("etc")
        assert installer.exists("etc")
        assert not installer.exists("nonexistent")

    def test_abs_path(self, tmp_path):
        sysroot = str(tmp_path / "sysroot")
        installer = SysrootInstaller(sysroot)
        result = installer.abs_path("usr", "bin", "sh")
        assert result == os.path.join(sysroot, "usr", "bin", "sh")

    def test_list_installed_files(self, tmp_path):
        sysroot = str(tmp_path / "sysroot")
        installer = SysrootInstaller(sysroot)
        installer.ensure_dir("etc")
        (tmp_path / "sysroot" / "etc" / "passwd").write_text("root:x:0:0:::/bin/sh\n")

        files = installer.list_installed_files()
        assert any("passwd" in f for f in files)

    def test_install_tree_root_guard_merges_not_wipes(self, tmp_path):
        """install_tree with dest_rel='.' must not delete the sysroot root."""
        sysroot = tmp_path / "sysroot"
        sysroot.mkdir()
        sentinel = sysroot / "sentinel.txt"
        sentinel.write_text("keep me")

        payload = tmp_path / "payload"
        tz_dir = payload / "usr" / "share" / "zoneinfo"
        tz_dir.mkdir(parents=True)
        (tz_dir / "UTC").write_text("tz data")

        installer = SysrootInstaller(str(sysroot))
        installer.install_tree(str(payload), ".")

        assert sentinel.is_file(), "install_tree wiped the sysroot root"
        assert (sysroot / "usr" / "share" / "zoneinfo" / "UTC").is_file()

    def test_install_tree_empty_dest_rel_merges(self, tmp_path):
        """install_tree with dest_rel='' behaves same as '.'."""
        sysroot = tmp_path / "sysroot"
        sysroot.mkdir()
        (sysroot / "existing.txt").write_text("existing")

        payload = tmp_path / "payload"
        payload.mkdir()
        (payload / "new.txt").write_text("new")

        installer = SysrootInstaller(str(sysroot))
        installer.install_tree(str(payload), "")

        assert (sysroot / "existing.txt").is_file()
        assert (sysroot / "new.txt").is_file()
