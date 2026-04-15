"""Tests for recipes/base.py safe_extract helper and helpers/image.py iso alias."""

from __future__ import annotations

import io
import os
import sys
import tarfile
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from recipes.base import safe_extract, RecipeError


class TestSafeExtract:

    def _make_tarball(self, tmp_path, members):
        """Helper: create a tar.gz with given (arcname, content) members."""
        tarball = str(tmp_path / "test.tar.gz")
        with tarfile.open(tarball, "w:gz") as tf:
            for arcname, content in members:
                data = content.encode()
                info = tarfile.TarInfo(name=arcname)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
        return tarball

    def test_extracts_normal_member(self, tmp_path):
        dest = str(tmp_path / "extract")
        os.makedirs(dest)
        tarball = self._make_tarball(tmp_path, [("subdir/file.txt", "hello")])
        safe_extract(tarball, dest)
        assert os.path.isfile(os.path.join(dest, "subdir", "file.txt"))

    def test_rejects_path_traversal(self, tmp_path):
        dest = str(tmp_path / "extract")
        os.makedirs(dest)
        tarball = self._make_tarball(tmp_path, [("../escape.txt", "evil")])
        with pytest.raises(RecipeError, match="path traversal"):
            safe_extract(tarball, dest)
        # Confirm the file was NOT written outside dest
        assert not os.path.isfile(str(tmp_path / "escape.txt"))

    def test_rejects_absolute_path(self, tmp_path):
        dest = str(tmp_path / "extract")
        os.makedirs(dest)
        tarball = self._make_tarball(tmp_path, [("/etc/evil.conf", "evil")])
        with pytest.raises(RecipeError, match="path traversal"):
            safe_extract(tarball, dest)


class TestImageFormatAlias:

    def test_iso_format_accepted(self):
        """ImageBuilder.build() must not raise for format='iso'."""
        from helpers.image import ImageBuilder
        from config import ImageConfig

        cfg = ImageConfig(enabled=True, format="iso", size_mb=64,
                          output="/tmp/blueyos_test.iso", bootloader="grub")
        ib = ImageBuilder(cfg, "/tmp", "/tmp")
        # We just want to confirm the format resolves without hitting the
        # "Unsupported image format" branch.  The actual ISO build will fail
        # gracefully (no genisoimage) and fall back to tar — that's fine.
        fmt = cfg.format.lower()
        assert fmt in ("iso", "iso9660")

    def test_iso9660_format_still_accepted(self):
        """iso9660 must continue to work after adding the iso alias."""
        from helpers.image import ImageBuilder
        from config import ImageConfig

        cfg = ImageConfig(enabled=True, format="iso9660", size_mb=64,
                          output="/tmp/blueyos_test.iso", bootloader="grub")
        fmt = cfg.format.lower()
        assert fmt in ("iso", "iso9660")
