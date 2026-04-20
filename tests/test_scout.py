"""Tests for recipes/scout.py."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import Config, KernelConfig
from recipes.base import RecipeError
from recipes.scout import ScoutRecipe


def _make_config(tmp_path) -> Config:
    cfg = Config(kernel=KernelConfig())
    cfg.abs_sysroot = str(tmp_path / "sysroot")
    cfg.abs_output_dir = str(tmp_path / "output")
    cfg.abs_build_dir = str(tmp_path / "build")
    cfg.abs_sources_dir = str(tmp_path / "src")
    cfg.abs_core_packages_dir = str(tmp_path / "core")
    cfg.abs_musl_prefix = str(tmp_path / "musl")
    cfg.abs_toolchain_prefix = str(tmp_path / "toolchain")

    for path in (
        cfg.abs_sysroot,
        cfg.abs_output_dir,
        cfg.abs_build_dir,
        cfg.abs_sources_dir,
        cfg.abs_core_packages_dir,
        cfg.abs_musl_prefix,
    ):
        os.makedirs(path, exist_ok=True)

    return cfg


def _make_executable(path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return str(path)


class TestScoutRecipeMetadata:
    def test_name(self, tmp_path):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        assert recipe.name == "scout"

    def test_version(self, tmp_path):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        assert recipe.version == "0.1.0"

    def test_dependencies_include_musl_and_claw(self, tmp_path):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        assert "musl-blueyos" in recipe.dependencies
        assert "claw" in recipe.dependencies

    def test_install_paths_include_scoutd(self, tmp_path):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        assert "sbin/scoutd" in recipe.install_paths

    def test_install_paths_include_network_tools(self, tmp_path):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        assert "usr/bin/nslookup" in recipe.install_paths
        assert "usr/bin/ping" in recipe.install_paths
        assert "usr/bin/tracert" in recipe.install_paths

    def test_install_paths_include_config_and_service(self, tmp_path):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        assert "etc/scout/scout.conf" in recipe.install_paths
        assert "etc/claw/services.d/scout.service.yml" in recipe.install_paths


class TestScoutConfigure:
    def test_configure_raises_when_source_missing(self, tmp_path):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        with pytest.raises(RecipeError, match="scout source not found"):
            recipe.configure()

    def test_configure_raises_when_no_autogen_and_no_configure(self, tmp_path):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        src = tmp_path / "src" / "scout"
        src.mkdir(parents=True)
        with pytest.raises(RecipeError, match="configure script not found"):
            recipe.configure()

    def test_configure_runs_autogen_when_configure_missing(self, tmp_path, monkeypatch):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        src = tmp_path / "src" / "scout"
        src.mkdir(parents=True)

        autogen = src / "autogen.sh"
        autogen.write_text("#!/bin/sh\ntouch configure\n")
        autogen.chmod(0o755)

        # configure-blueyos.sh is absent so the fallback configure is used
        musl_prefix = tmp_path / "musl"
        (musl_prefix / "include").mkdir(parents=True, exist_ok=True)
        (musl_prefix / "lib" / "libc.a").parent.mkdir(parents=True, exist_ok=True)
        (musl_prefix / "lib" / "libc.a").write_bytes(b"")

        calls = []

        def fake_run(cmd, cwd=None, env=None):
            calls.append(cmd)
            if cmd[:2] == ["bash", "autogen.sh"]:
                (src / "configure").write_text("#!/bin/sh\nexit 0\n")
                (src / "configure").chmod(0o755)

        monkeypatch.setattr(recipe, "run", fake_run)
        recipe.configure()

        assert any(cmd[:2] == ["bash", "autogen.sh"] for cmd in calls), (
            "autogen.sh should have been invoked"
        )

    def test_configure_uses_configure_blueyos_sh_when_present(self, tmp_path, monkeypatch):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        src = tmp_path / "src" / "scout"
        src.mkdir(parents=True)

        (src / "configure").write_text("#!/bin/sh\nexit 0\n")
        (src / "configure").chmod(0o755)

        tools = src / "tools"
        tools.mkdir()
        (tools / "configure-blueyos.sh").write_text("#!/bin/sh\nexit 0\n")
        (tools / "configure-blueyos.sh").chmod(0o755)

        calls = []
        monkeypatch.setattr(recipe, "run", lambda cmd, cwd=None, env=None: calls.append(cmd))

        recipe.configure()

        assert any("configure-blueyos.sh" in str(cmd) for cmd in calls), (
            "configure-blueyos.sh should have been used"
        )

    def test_configure_passes_libc_and_sysroot_to_wrapper(self, tmp_path, monkeypatch):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        src = tmp_path / "src" / "scout"
        src.mkdir(parents=True)

        (src / "configure").write_text("#!/bin/sh\nexit 0\n")
        (src / "configure").chmod(0o755)

        tools = src / "tools"
        tools.mkdir()
        (tools / "configure-blueyos.sh").write_text("#!/bin/sh\nexit 0\n")
        (tools / "configure-blueyos.sh").chmod(0o755)

        captured = []
        monkeypatch.setattr(recipe, "run", lambda cmd, cwd=None, env=None: captured.append(cmd))

        recipe.configure()

        configure_cmd = next(cmd for cmd in captured if "configure-blueyos.sh" in str(cmd))
        joined = " ".join(configure_cmd)
        assert "--libc=musl" in joined
        assert "--sysroot=" in joined
        assert "--build-dir=" in joined


class TestScoutBuild:
    def test_build_raises_when_source_missing(self, tmp_path):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        with pytest.raises(RecipeError, match="source not found"):
            recipe.build()

    def test_build_raises_when_build_dir_missing(self, tmp_path):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        (tmp_path / "src" / "scout").mkdir(parents=True)
        with pytest.raises(RecipeError, match="build directory not found"):
            recipe.build()

    def test_build_runs_make_in_build_dir(self, tmp_path, monkeypatch):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        (tmp_path / "src" / "scout").mkdir(parents=True)
        build_dir = tmp_path / "build" / "scout"
        build_dir.mkdir(parents=True)

        captured = []
        monkeypatch.setattr(recipe, "run", lambda cmd, cwd=None, env=None: captured.append((cmd, cwd)))

        recipe.build()

        assert any("make" in cmd[0] for cmd, _ in captured)
        assert all(cwd == str(build_dir) for _, cwd in captured)


class TestScoutInstall:
    def test_install_skips_gracefully_when_build_dir_missing(self, tmp_path, caplog):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        import logging
        with caplog.at_level(logging.WARNING, logger="baker.recipe.scout"):
            recipe.install()
        assert any("build directory not found" in r.message for r in caplog.records)

    def test_install_runs_make_install_and_copies_tree(self, tmp_path, monkeypatch):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)

        build_dir = tmp_path / "build" / "scout"
        build_dir.mkdir(parents=True)

        install_calls = []

        def fake_run(cmd, cwd=None, env=None):
            install_calls.append(cmd)

        def fake_install_tree(src, dst):
            pass

        monkeypatch.setattr(recipe, "run", fake_run)
        monkeypatch.setattr(recipe.sysroot, "install_tree", fake_install_tree)

        recipe.install()

        assert any("install" in cmd for cmd in install_calls)
        assert any(f"DESTDIR=" in arg for cmd in install_calls for arg in cmd)


class TestScoutPackage:
    def test_package_raises_when_build_dir_missing(self, tmp_path):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)
        with pytest.raises(RecipeError, match="build directory not found"):
            recipe.package()

    def test_package_raises_when_no_dpk_produced(self, tmp_path, monkeypatch):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)

        build_dir = tmp_path / "build" / "scout"
        build_dir.mkdir(parents=True)

        dpkbuild = tmp_path / "bin" / "dpkbuild"
        _make_executable(dpkbuild)
        monkeypatch.setattr("shutil.which", lambda name: str(dpkbuild) if name == "dpkbuild" else None)
        monkeypatch.setattr(recipe, "run", lambda cmd, cwd=None, env=None: None)

        with pytest.raises(RecipeError, match="no .dpk was produced"):
            recipe.package()

    def test_package_copies_dpk_to_output(self, tmp_path, monkeypatch):
        cfg = _make_config(tmp_path)
        recipe = ScoutRecipe(cfg)

        build_dir = tmp_path / "build" / "scout"
        dist_dir = build_dir / "dist"
        dist_dir.mkdir(parents=True)

        dpkbuild = tmp_path / "bin" / "dpkbuild"
        _make_executable(dpkbuild)
        monkeypatch.setattr("shutil.which", lambda name: str(dpkbuild) if name == "dpkbuild" else None)

        dpk_name = "scout-0.1.0-1-i386.dpk"

        def fake_run(cmd, cwd=None, env=None):
            if "package" in cmd:
                (dist_dir / dpk_name).write_bytes(b"fake-dpk")

        monkeypatch.setattr(recipe, "run", fake_run)

        result = recipe.package()

        expected = os.path.join(cfg.abs_output_dir, dpk_name)
        assert result == expected
        assert os.path.isfile(expected)
