"""Tests for VM and extract workflow — VmConfig loading, QEMU command construction."""

from __future__ import annotations

import os
import textwrap
import tempfile
import unittest.mock as mock
from pathlib import Path

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import load_config, VmConfig, ImageConfig


# ---------------------------------------------------------------------------
# VmConfig loading
# ---------------------------------------------------------------------------

class TestVmConfigDefaults:
    def test_default_ram(self, tmp_path):
        cfg = load_config(str(tmp_path / "no.yaml"))
        assert cfg.vm.ram_mb == 512

    def test_default_cpus(self, tmp_path):
        cfg = load_config(str(tmp_path / "no.yaml"))
        assert cfg.vm.cpus == 2

    def test_default_display(self, tmp_path):
        cfg = load_config(str(tmp_path / "no.yaml"))
        assert cfg.vm.display == "none"

    def test_default_kvm(self, tmp_path):
        cfg = load_config(str(tmp_path / "no.yaml"))
        assert cfg.vm.kvm == "auto"

    def test_default_snapshot(self, tmp_path):
        cfg = load_config(str(tmp_path / "no.yaml"))
        assert cfg.vm.snapshot is True

    def test_default_extra_args(self, tmp_path):
        cfg = load_config(str(tmp_path / "no.yaml"))
        assert cfg.vm.extra_args == []


class TestVmConfigFromYaml:
    def _write(self, tmp_path, content):
        p = tmp_path / "baker.yaml"
        p.write_text(textwrap.dedent(content))
        return str(p)

    def test_ram_loaded(self, tmp_path):
        p = self._write(tmp_path, """\
            vm:
              ram_mb: 1024
        """)
        cfg = load_config(p)
        assert cfg.vm.ram_mb == 1024

    def test_cpus_loaded(self, tmp_path):
        p = self._write(tmp_path, """\
            vm:
              cpus: 4
        """)
        cfg = load_config(p)
        assert cfg.vm.cpus == 4

    def test_display_gtk(self, tmp_path):
        p = self._write(tmp_path, """\
            vm:
              display: gtk
        """)
        cfg = load_config(p)
        assert cfg.vm.display == "gtk"

    def test_snapshot_false(self, tmp_path):
        p = self._write(tmp_path, """\
            vm:
              snapshot: false
        """)
        cfg = load_config(p)
        assert cfg.vm.snapshot is False

    def test_extra_args_list(self, tmp_path):
        p = self._write(tmp_path, """\
            vm:
              extra_args:
                - "-nographic"
                - "-monitor"
                - "none"
        """)
        cfg = load_config(p)
        assert cfg.vm.extra_args == ["-nographic", "-monitor", "none"]

    def test_kvm_disabled(self, tmp_path):
        p = self._write(tmp_path, """\
            vm:
              kvm: disabled
        """)
        cfg = load_config(p)
        assert cfg.vm.kvm == "disabled"


# ---------------------------------------------------------------------------
# ImageConfig disk-sizing fields
# ---------------------------------------------------------------------------

class TestImageConfigDiskSizing:
    def _write(self, tmp_path, content):
        p = tmp_path / "baker.yaml"
        p.write_text(textwrap.dedent(content))
        return str(p)

    def test_default_swap_mb(self, tmp_path):
        cfg = load_config(str(tmp_path / "no.yaml"))
        assert cfg.image.swap_mb == 64

    def test_default_headroom_pct(self, tmp_path):
        cfg = load_config(str(tmp_path / "no.yaml"))
        assert cfg.image.headroom_pct == 30

    def test_swap_loaded(self, tmp_path):
        p = self._write(tmp_path, """\
            image:
              swap_mb: 128
        """)
        cfg = load_config(p)
        assert cfg.image.swap_mb == 128

    def test_headroom_loaded(self, tmp_path):
        p = self._write(tmp_path, """\
            image:
              headroom_pct: 50
        """)
        cfg = load_config(p)
        assert cfg.image.headroom_pct == 50


# ---------------------------------------------------------------------------
# VmStage QEMU command construction
# ---------------------------------------------------------------------------

class TestVmStageQemuCommand:
    """Unit-test _build_qemu_cmd without launching QEMU."""

    def _make_cfg(self, **vm_kwargs):
        """Return a minimal Config-like object with VmConfig."""
        vm = VmConfig(**vm_kwargs)
        cfg = mock.MagicMock()
        cfg.vm = vm
        cfg.abs_kernel_source = "/fake/biscuits"
        return cfg

    def _get_stage(self, cfg):
        from stages.vm import VmStage
        stage = VmStage.__new__(VmStage)
        stage.config = cfg
        stage.log = mock.MagicMock()
        return stage

    def test_basic_command_structure(self):
        cfg = self._make_cfg()
        stage = self._get_stage(cfg)
        cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "none", True)
        assert cmd[0] == "qemu-system-i386"
        assert "-m" in cmd
        assert "512M" in cmd
        assert "-smp" in cmd
        assert "2" in cmd

    def test_snapshot_flag_present(self):
        cfg = self._make_cfg()
        stage = self._get_stage(cfg)
        cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "none", True)
        assert "-snapshot" in cmd

    def test_no_snapshot_flag_when_disabled(self):
        cfg = self._make_cfg()
        stage = self._get_stage(cfg)
        cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "none", False)
        assert "-snapshot" not in cmd

    def test_display_none_uses_serial_stdio(self):
        cfg = self._make_cfg(display="none")
        stage = self._get_stage(cfg)
        cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "none", True)
        assert "-display" in cmd
        idx = cmd.index("-display")
        assert cmd[idx + 1] == "none"
        assert "-serial" in cmd
        assert "stdio" in cmd

    def test_display_gtk_uses_vga(self):
        cfg = self._make_cfg(display="gtk")
        stage = self._get_stage(cfg)
        cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "gtk", True)
        assert "-display" in cmd
        idx = cmd.index("-display")
        assert cmd[idx + 1] == "gtk"
        assert "-vga" in cmd

    def test_kvm_disabled_no_flag(self):
        cfg = self._make_cfg(kvm="disabled")
        stage = self._get_stage(cfg)
        cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "none", True)
        assert "-enable-kvm" not in cmd

    def test_kvm_enabled_flag_present(self):
        cfg = self._make_cfg(kvm="enabled")
        stage = self._get_stage(cfg)
        cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "none", True)
        assert "-enable-kvm" in cmd

    def test_kvm_auto_no_flag_when_no_dev_kvm(self):
        cfg = self._make_cfg(kvm="auto")
        stage = self._get_stage(cfg)
        with mock.patch("os.access", return_value=False):
            cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "none", True)
        assert "-enable-kvm" not in cmd

    def test_kvm_auto_flag_when_dev_kvm_accessible(self):
        cfg = self._make_cfg(kvm="auto")
        stage = self._get_stage(cfg)
        with mock.patch("os.access", return_value=True):
            cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "none", True)
        assert "-enable-kvm" in cmd

    def test_drive_contains_image_path(self):
        cfg = self._make_cfg()
        stage = self._get_stage(cfg)
        cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "none", True)
        drive_args = " ".join(cmd)
        assert "/fake/disk.img" in drive_args

    def test_extra_args_appended(self):
        cfg = self._make_cfg(extra_args=["-nographic", "-monitor", "none"])
        stage = self._get_stage(cfg)
        cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "none", True)
        assert "-nographic" in cmd
        assert "-monitor" in cmd
        assert "none" in cmd

    def test_log_disk_added_when_present(self, tmp_path):
        cfg = self._make_cfg()
        log_disk_dir = tmp_path / "build"
        log_disk_dir.mkdir()
        log_disk = log_disk_dir / "blueyos-log-fat.img"
        log_disk.write_bytes(b"\x00" * 512)
        cfg.abs_kernel_source = str(tmp_path)
        stage = self._get_stage(cfg)
        cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "none", True)
        assert str(log_disk) in " ".join(cmd)

    def test_no_log_disk_when_absent(self, tmp_path):
        cfg = self._make_cfg()
        cfg.abs_kernel_source = str(tmp_path)
        stage = self._get_stage(cfg)
        cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "none", True)
        assert "log-fat" not in " ".join(cmd)

    def test_network_device_included(self):
        cfg = self._make_cfg()
        stage = self._get_stage(cfg)
        cmd = stage._build_qemu_cmd(cfg, "/fake/disk.img", 512, 2, "none", True)
        assert "-netdev" in cmd
        assert "-device" in cmd
        assert any("ne2k_isa" in a for a in cmd)


# ---------------------------------------------------------------------------
# ExtractStage path resolution
# ---------------------------------------------------------------------------

class TestExtractStagePathResolution:
    def test_missing_image_raises(self, tmp_path):
        from stages.extract import ExtractStage
        cfg = mock.MagicMock()
        cfg.image.output = str(tmp_path / "nonexistent.img")
        cfg.abs_output_dir = str(tmp_path)

        stage = ExtractStage.__new__(ExtractStage)
        stage.config = cfg
        stage.log = mock.MagicMock()
        stage.paths = ["/var/log"]
        stage.output_dir = None
        stage.image_override = None

        with pytest.raises(RuntimeError, match="Disk image not found"):
            stage.run()

    def test_image_override_used(self, tmp_path):
        from stages.extract import ExtractStage
        cfg = mock.MagicMock()
        cfg.image.output = str(tmp_path / "nonexistent.img")
        cfg.abs_output_dir = str(tmp_path)

        override_img = str(tmp_path / "other.img")

        stage = ExtractStage.__new__(ExtractStage)
        stage.config = cfg
        stage.log = mock.MagicMock()
        stage.paths = ["/var/log"]
        stage.output_dir = None
        stage.image_override = override_img

        # Should raise about the override path, not the config path
        with pytest.raises(RuntimeError, match="other.img"):
            stage.run()
