"""Tests for the baker CLI entry point."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import baker


class TestCLIParsing:
    """Verify that the argument parser is correctly configured."""

    def _parse(self, args):
        parser = baker.build_parser()
        return parser.parse_args(args)

    def test_prepare_command(self):
        args = self._parse(["prepare"])
        assert args.command == "prepare"

    def test_kernel_command(self):
        args = self._parse(["kernel"])
        assert args.command == "kernel"

    def test_build_command(self):
        args = self._parse(["build"])
        assert args.command == "build"

    def test_package_command(self):
        args = self._parse(["package"])
        assert args.command == "package"

    def test_image_command(self):
        args = self._parse(["image"])
        assert args.command == "image"

    def test_all_command(self):
        args = self._parse(["all"])
        assert args.command == "all"

    def test_clean_command(self):
        args = self._parse(["clean"])
        assert args.command == "clean"

    def test_clean_with_sysroot_flag(self):
        args = self._parse(["clean", "--sysroot"])
        assert args.clean_sysroot is True

    def test_clean_with_output_flag(self):
        args = self._parse(["clean", "--output"])
        assert args.clean_output is True

    def test_clean_all_flag(self):
        args = self._parse(["clean", "--all"])
        assert args.clean_all is True

    def test_config_flag(self):
        args = self._parse(["--config", "custom.yaml", "build"])
        assert args.config == "custom.yaml"

    def test_verbose_flag(self):
        args = self._parse(["--verbose", "build"])
        assert args.verbose is True

    def test_no_command_raises(self):
        parser = baker.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])


class TestMainIntegration:
    """Smoke-test the main() function end-to-end with a minimal config."""

    def test_prepare_exits_zero(self, tmp_path):
        cfg = tmp_path / "baker.yaml"
        cfg.write_text(
            "sysroot: sysroot\noutput_dir: output\nbuild_dir: build\n"
            "sources_dir: src\nkernel_source: src/biscuits\n"
            "network:\n  kernel_repo: ''\n  kernel_branch: main\n"
            "components: []\n"
        )
        rc = baker.main(["--config", str(cfg), "prepare"])
        assert rc == 0

    def test_build_with_no_components(self, tmp_path):
        cfg = tmp_path / "baker.yaml"
        cfg.write_text(
            "sysroot: sysroot\noutput_dir: output\nbuild_dir: build\n"
            "sources_dir: src\nkernel_source: src/biscuits\n"
            "components: []\n"
        )
        rc = baker.main(["--config", str(cfg), "build"])
        # Should complete without error (just warns that no components are enabled)
        assert rc == 0

    def test_clean_exits_zero(self, tmp_path):
        cfg = tmp_path / "baker.yaml"
        cfg.write_text("sysroot: sysroot\noutput_dir: output\nbuild_dir: build\n")
        rc = baker.main(["--config", str(cfg), "clean"])
        assert rc == 0
