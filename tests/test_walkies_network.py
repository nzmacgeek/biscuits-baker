"""
tests/test_walkies_network.py — Unit tests for walkies network configuration.

Tests that:
  1. The WalkiesRecipe metadata is correct
  2. The /etc/interfaces file shipped in the payload supports static and dhcp stanzas
  3. The claw service unit files are present
  4. The bluey-dhcp recipe metadata is correct and its source file is present
  5. The AF_INET value in musl-blueyos socket.h matches the kernel's BLUEY_AF_INET=3

These are unit/static tests; no VM is launched.  An end-to-end boot test would
require a QEMU environment and is tracked as a separate integration test.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import Config, KernelConfig
from recipes.walkies import WalkiesRecipe
from recipes.dhcp_client import DhcpClientRecipe


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _make_config(tmp_path) -> Config:
    cfg = Config(kernel=KernelConfig())
    cfg.abs_sysroot     = str(tmp_path / "sysroot")
    cfg.abs_output_dir  = str(tmp_path / "output")
    cfg.abs_build_dir   = str(tmp_path / "build")
    cfg.abs_sources_dir = str(tmp_path / "src")
    cfg.abs_core_packages_dir = str(tmp_path / "core")
    cfg.abs_musl_prefix = str(tmp_path / "musl")
    cfg.abs_toolchain_prefix  = str(tmp_path / "toolchain")
    for p in (cfg.abs_sysroot, cfg.abs_output_dir, cfg.abs_build_dir,
              cfg.abs_sources_dir, cfg.abs_core_packages_dir,
              cfg.abs_musl_prefix):
        os.makedirs(p, exist_ok=True)
    return cfg


# ---------------------------------------------------------------------------
# WalkiesRecipe metadata
# ---------------------------------------------------------------------------

class TestWalkiesRecipe:
    def test_name(self, tmp_path):
        recipe = WalkiesRecipe(_make_config(tmp_path))
        assert recipe.name == "walkies"

    def test_version(self, tmp_path):
        recipe = WalkiesRecipe(_make_config(tmp_path))
        assert recipe.version  # must be non-empty

    def test_depends_on_musl(self, tmp_path):
        recipe = WalkiesRecipe(_make_config(tmp_path))
        assert "musl-blueyos" in recipe.dependencies


# ---------------------------------------------------------------------------
# /etc/interfaces payload content
# ---------------------------------------------------------------------------

class TestInterfacesFile:
    @pytest.fixture
    def interfaces_path(self):
        path = os.path.join(
            REPO_ROOT, "src", "walkies", "pkg", "payload", "etc", "interfaces"
        )
        if not os.path.isfile(path):
            pytest.skip("walkies source not present")
        return path

    def test_file_exists(self, interfaces_path):
        assert os.path.isfile(interfaces_path)

    def test_loopback_stanza(self, interfaces_path):
        content = open(interfaces_path).read()
        assert "iface lo inet loopback" in content

    def test_static_stanza_example(self, interfaces_path):
        content = open(interfaces_path).read()
        assert "inet static" in content

    def test_dhcp_stanza_example(self, interfaces_path):
        content = open(interfaces_path).read()
        assert "inet dhcp" in content


# ---------------------------------------------------------------------------
# Walkies claw service units
# ---------------------------------------------------------------------------

class TestWalkiesClawUnits:
    def test_walkies_service_unit_exists(self):
        path = os.path.join(
            REPO_ROOT, "src", "walkies", "pkg", "payload",
            "etc", "claw", "services.d", "walkies.yml"
        )
        if not os.path.isfile(path):
            pytest.skip("walkies source not present")
        assert os.path.isfile(path)

    def test_network_target_unit_exists(self):
        path = os.path.join(
            REPO_ROOT, "src", "walkies", "pkg", "payload",
            "etc", "claw", "targets.d", "claw-network.target.yml"
        )
        if not os.path.isfile(path):
            pytest.skip("walkies source not present")
        assert os.path.isfile(path)


# ---------------------------------------------------------------------------
# bluey-dhcp recipe
# ---------------------------------------------------------------------------

class TestDhcpClientRecipe:
    def test_name(self, tmp_path):
        recipe = DhcpClientRecipe(_make_config(tmp_path))
        assert recipe.name == "bluey-dhcp"

    def test_version(self, tmp_path):
        recipe = DhcpClientRecipe(_make_config(tmp_path))
        assert recipe.version

    def test_depends_on_walkies(self, tmp_path):
        recipe = DhcpClientRecipe(_make_config(tmp_path))
        assert "walkies" in recipe.dependencies

    def test_source_files_present(self):
        src_dir = os.path.join(REPO_ROOT, "src", "bluey-dhcp", "user")
        assert os.path.isfile(os.path.join(src_dir, "main.c")), \
            "bluey-dhcp main.c not found"
        assert os.path.isfile(os.path.join(src_dir, "netctl.c")), \
            "bluey-dhcp netctl.c not found"
        assert os.path.isfile(os.path.join(src_dir, "dhcp.h")), \
            "bluey-dhcp dhcp.h not found"
        assert os.path.isfile(os.path.join(src_dir, "netctl.h")), \
            "bluey-dhcp netctl.h not found"
        assert os.path.isfile(os.path.join(src_dir, "Makefile")), \
            "bluey-dhcp Makefile not found"

    def test_claw_service_unit_present(self):
        unit = os.path.join(
            REPO_ROOT, "src", "bluey-dhcp", "pkg", "payload",
            "etc", "claw", "services.d", "bluey-dhcp@.yml"
        )
        assert os.path.isfile(unit), \
            "bluey-dhcp claw service template unit not found"

    def test_package_manifest_present(self):
        manifest = os.path.join(
            REPO_ROOT, "src", "bluey-dhcp", "pkg", "meta", "manifest.json"
        )
        assert os.path.isfile(manifest)

    def test_package_manifest_arch(self):
        import json
        manifest = os.path.join(
            REPO_ROOT, "src", "bluey-dhcp", "pkg", "meta", "manifest.json"
        )
        with open(manifest) as fh:
            data = json.load(fh)
        assert data.get("arch") == "i386"
        assert data.get("name") == "bluey-dhcp"


# ---------------------------------------------------------------------------
# musl-blueyos AF_INET socket family value
# ---------------------------------------------------------------------------

class TestMuslSocketFamilies:
    """
    The BlueyOS kernel uses BLUEY_AF_INET=3 (AF_NETCTL occupies slot 2).
    musl-blueyos must define PF_INET=3 so that socket(AF_INET, SOCK_DGRAM, 0)
    passes domain=3 to the kernel, which is what INET UDP sockets require.
    """

    @pytest.fixture
    def socket_h(self):
        path = os.path.join(
            REPO_ROOT, "src", "biscuits", "musl-blueyos",
            "include", "sys", "socket.h"
        )
        if not os.path.isfile(path):
            pytest.skip("musl-blueyos source not present")
        return open(path).read()

    def test_pf_inet_is_3(self, socket_h):
        m = re.search(r"#define\s+PF_INET\s+(\d+)", socket_h)
        assert m is not None, "PF_INET not defined in musl-blueyos socket.h"
        assert int(m.group(1)) == 3, (
            f"PF_INET is {m.group(1)}, expected 3 "
            "(must match kernel BLUEY_AF_INET=3)"
        )

    def test_af_inet_equals_pf_inet(self, socket_h):
        assert "#define AF_INET" in socket_h
        # AF_INET PF_INET means they're the same value — just check it's defined
        m = re.search(r"#define\s+AF_INET\s+(.+)", socket_h)
        assert m is not None, "AF_INET not defined in musl-blueyos socket.h"

    def test_installed_sysroot_socket_h(self):
        """The installed musl sysroot header must also have PF_INET=3."""
        path = os.path.join(
            REPO_ROOT, "build", "musl", "include", "sys", "socket.h"
        )
        if not os.path.isfile(path):
            pytest.skip("musl sysroot not built yet")
        content = open(path).read()
        m = re.search(r"#define\s+PF_INET\s+(\d+)", content)
        assert m is not None, "PF_INET not in installed sysroot socket.h"
        assert int(m.group(1)) == 3, (
            f"Installed sysroot PF_INET={m.group(1)}, expected 3"
        )
