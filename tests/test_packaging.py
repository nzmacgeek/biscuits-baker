"""Tests for helpers/packaging.py - Package creation helpers."""

from __future__ import annotations

import os
import sys
import tarfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from helpers.packaging import PackageBuilder


class TestPackageBuilder:
    def test_creates_output_dir(self, tmp_path):
        output = str(tmp_path / "pkgs")
        PackageBuilder(output)
        assert os.path.isdir(output)

    def test_build_package_creates_file(self, tmp_path):
        sysroot = tmp_path / "sysroot"
        sysroot.mkdir()
        (sysroot / "hello").write_text("world")

        builder = PackageBuilder(str(tmp_path / "pkgs"))
        pkg = builder.build_package("mycomp", "1.0.0", str(sysroot))
        assert os.path.exists(pkg)
        assert pkg.endswith(".tar.gz")

    def test_package_contains_manifest(self, tmp_path):
        sysroot = tmp_path / "sysroot"
        sysroot.mkdir()
        (sysroot / "file.txt").write_text("content")

        builder = PackageBuilder(str(tmp_path / "pkgs"))
        pkg = builder.build_package("comp", "2.3.4", str(sysroot))

        with tarfile.open(pkg) as tf:
            members = tf.getnames()
        assert any("MANIFEST.json" in m for m in members)

    def test_package_with_include_paths(self, tmp_path):
        sysroot = tmp_path / "sysroot"
        sysroot.mkdir()
        (sysroot / "include_me.txt").write_text("yes")
        (sysroot / "exclude_me.txt").write_text("no")

        builder = PackageBuilder(str(tmp_path / "pkgs"))
        pkg = builder.build_package(
            "comp", "1.0", str(sysroot),
            include_paths=["include_me.txt"]
        )

        with tarfile.open(pkg) as tf:
            members = tf.getnames()
        assert any("include_me.txt" in m for m in members)
        assert not any("exclude_me.txt" in m for m in members)

    def test_list_packages(self, tmp_path):
        sysroot = tmp_path / "sysroot"
        sysroot.mkdir()
        (sysroot / "f").write_text("x")

        output = str(tmp_path / "pkgs")
        builder = PackageBuilder(output)
        builder.build_package("a", "1.0", str(sysroot))
        builder.build_package("b", "2.0", str(sysroot))

        packages = builder.list_packages()
        assert len(packages) == 2

    def test_metadata_in_manifest(self, tmp_path):
        import json

        sysroot = tmp_path / "sysroot"
        sysroot.mkdir()
        (sysroot / "x").write_text("x")

        builder = PackageBuilder(str(tmp_path / "pkgs"))
        pkg = builder.build_package(
            "mycomp", "3.0", str(sysroot),
            metadata={"custom_key": "custom_value", "arch": "x86_64"},
        )

        with tarfile.open(pkg) as tf:
            manifest_member = next(m for m in tf.getmembers() if "MANIFEST.json" in m.name)
            data = json.loads(tf.extractfile(manifest_member).read())

        assert data["name"] == "mycomp"
        assert data["version"] == "3.0"
        assert data["custom_key"] == "custom_value"
