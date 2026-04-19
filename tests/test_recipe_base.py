"""Tests for shared recipe base helpers."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import Config, KernelConfig
from recipes.base import BaseRecipe, RecipeError


class DummyRecipe(BaseRecipe):
    name = "dummy"

    def build(self) -> None:
        return None


def _make_config(tmp_path) -> Config:
    cfg = Config(kernel=KernelConfig())
    cfg.abs_sysroot = str(tmp_path / "sysroot")
    cfg.abs_output_dir = str(tmp_path / "output")
    cfg.abs_build_dir = str(tmp_path / "build")
    cfg.abs_sources_dir = str(tmp_path / "src")
    cfg.abs_core_packages_dir = str(tmp_path / "core")
    cfg.abs_musl_prefix = str(tmp_path / "musl")

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


def test_resolve_dpkbuild_prefers_path(monkeypatch, tmp_path):
    cfg = _make_config(tmp_path)
    recipe = DummyRecipe(cfg)
    host_dpkbuild = _make_executable(tmp_path / "host-bin" / "dpkbuild")

    monkeypatch.setattr("shutil.which", lambda name: host_dpkbuild if name == "dpkbuild" else None)

    assert recipe.resolve_dpkbuild() == host_dpkbuild


def test_resolve_dpkbuild_falls_back_to_local_dimsim(monkeypatch, tmp_path):
    cfg = _make_config(tmp_path)
    recipe = DummyRecipe(cfg)
    local_dpkbuild = _make_executable(tmp_path / "src" / "dimsim" / "bin" / "dpkbuild")

    monkeypatch.setattr("shutil.which", lambda name: None)

    assert recipe.resolve_dpkbuild() == local_dpkbuild


def test_resolve_dpkbuild_falls_back_to_sysroot(monkeypatch, tmp_path):
    cfg = _make_config(tmp_path)
    recipe = DummyRecipe(cfg)
    sysroot_dpkbuild = _make_executable(tmp_path / "sysroot" / "usr" / "bin" / "dpkbuild")

    monkeypatch.setattr("shutil.which", lambda name: None)

    assert recipe.resolve_dpkbuild() == sysroot_dpkbuild


def test_resolve_dpkbuild_raises_when_missing(monkeypatch, tmp_path):
    cfg = _make_config(tmp_path)
    recipe = DummyRecipe(cfg)

    monkeypatch.setattr("shutil.which", lambda name: None)

    with pytest.raises(RecipeError, match="dpkbuild not found"):
        recipe.resolve_dpkbuild()