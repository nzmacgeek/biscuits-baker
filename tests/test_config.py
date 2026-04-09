"""Tests for config.py - Configuration loader."""

from __future__ import annotations

import os
import textwrap
import tempfile
import pytest

# Ensure the repo root is on the path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import load_config, Config, KernelConfig, NetworkConfig, ImageConfig


class TestLoadConfigDefaults:
    """load_config returns sensible defaults when the file is missing."""

    def test_returns_config_object(self, tmp_path):
        missing = str(tmp_path / "nonexistent.yaml")
        cfg = load_config(missing)
        assert isinstance(cfg, Config)

    def test_default_arch(self, tmp_path):
        cfg = load_config(str(tmp_path / "no.yaml"))
        assert cfg.arch == "x86_64"

    def test_default_log_level(self, tmp_path):
        cfg = load_config(str(tmp_path / "no.yaml"))
        assert cfg.log_level == "info"

    def test_abs_paths_are_set(self, tmp_path):
        cfg = load_config(str(tmp_path / "no.yaml"))
        assert os.path.isabs(cfg.abs_sysroot)
        assert os.path.isabs(cfg.abs_output_dir)
        assert os.path.isabs(cfg.abs_build_dir)


class TestLoadConfigFromFile:
    """load_config correctly reads and merges values from baker.yaml."""

    def _write_yaml(self, tmp_path, content: str) -> str:
        p = tmp_path / "baker.yaml"
        p.write_text(textwrap.dedent(content))
        return str(p)

    def test_arch_override(self, tmp_path):
        path = self._write_yaml(tmp_path, "arch: aarch64\n")
        cfg = load_config(path)
        assert cfg.arch == "aarch64"

    def test_sysroot_override(self, tmp_path):
        path = self._write_yaml(tmp_path, "sysroot: my_sysroot\n")
        cfg = load_config(path)
        assert cfg.sysroot == "my_sysroot"
        assert cfg.abs_sysroot.endswith("my_sysroot")

    def test_kernel_config_override(self, tmp_path):
        path = self._write_yaml(
            tmp_path,
            """
            kernel:
              config: my.config
              make_flags: "-j8"
              install_modules: false
            """,
        )
        cfg = load_config(path)
        assert cfg.kernel.config == "my.config"
        assert cfg.kernel.make_flags == "-j8"
        assert cfg.kernel.install_modules is False

    def test_network_override(self, tmp_path):
        path = self._write_yaml(
            tmp_path,
            """
            network:
              kernel_repo: "https://example.com/kernel"
              kernel_branch: "dev"
              extra_repos:
                - "https://example.com/extra"
            """,
        )
        cfg = load_config(path)
        assert cfg.network.kernel_repo == "https://example.com/kernel"
        assert cfg.network.kernel_branch == "dev"
        assert cfg.network.extra_repos == ["https://example.com/extra"]

    def test_components_parsed(self, tmp_path):
        path = self._write_yaml(
            tmp_path,
            """
            components:
              - name: musl
                enabled: true
              - name: busybox
                enabled: false
            """,
        )
        cfg = load_config(path)
        assert len(cfg.components) == 2
        names = {c.name for c in cfg.components}
        assert names == {"musl", "busybox"}
        disabled = [c for c in cfg.components if c.name == "busybox"]
        assert disabled[0].enabled is False

    def test_image_config(self, tmp_path):
        path = self._write_yaml(
            tmp_path,
            """
            image:
              enabled: true
              format: ext4
              size_mb: 128
              output: output/myos.img
              bootloader: grub
            """,
        )
        cfg = load_config(path)
        assert cfg.image.enabled is True
        assert cfg.image.format == "ext4"
        assert cfg.image.size_mb == 128
        assert cfg.image.output == "output/myos.img"
        assert cfg.image.bootloader == "grub"

    def test_exclude_list(self, tmp_path):
        path = self._write_yaml(tmp_path, "exclude:\n  - debug-tools\n  - docs\n")
        cfg = load_config(path)
        assert "debug-tools" in cfg.exclude
        assert "docs" in cfg.exclude
