"""Tests for helpers/musl.py."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from helpers.musl import (
    ensure_musl_dynlinker,
    ensure_musl_specs,
    generate_musl_specs,
    repair_musl_wrapper,
    resolve_musl_include_dir,
    resolve_musl_lib_dir,
)


def _make_musl_layout(root, lib_subdir="lib"):
    """Create a minimal musl sysroot layout under *root*."""
    include_dir = root / "include"
    include_dir.mkdir(parents=True, exist_ok=True)
    (include_dir / "stdio.h").write_text("/* stub */\n")

    lib_dir = root / lib_subdir
    lib_dir.mkdir(parents=True, exist_ok=True)
    (lib_dir / "libc.a").write_bytes(b"AR")
    (lib_dir / "crt1.o").write_bytes(b"\x7fELF")
    (lib_dir / "crti.o").write_bytes(b"\x7fELF")
    (lib_dir / "crtn.o").write_bytes(b"\x7fELF")
    return include_dir, lib_dir


class TestResolveMulLibDir:
    def test_finds_usr_lib_when_both_exist(self, tmp_path):
        _make_musl_layout(tmp_path, "lib")
        _make_musl_layout(tmp_path, "usr/lib")
        assert resolve_musl_lib_dir(str(tmp_path)) == str(tmp_path / "usr" / "lib")

    def test_falls_back_to_lib_when_usr_lib_absent(self, tmp_path):
        _make_musl_layout(tmp_path, "lib")
        assert resolve_musl_lib_dir(str(tmp_path)) == str(tmp_path / "lib")

    def test_returns_none_without_crt1(self, tmp_path):
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "libc.a").write_bytes(b"AR")
        # No crt1.o
        assert resolve_musl_lib_dir(str(tmp_path)) is None

    def test_returns_none_without_libc_a(self, tmp_path):
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "crt1.o").write_bytes(b"\x7fELF")
        assert resolve_musl_lib_dir(str(tmp_path)) is None

    def test_returns_none_for_empty_prefix(self, tmp_path):
        assert resolve_musl_lib_dir(str(tmp_path)) is None


class TestResolveMulIncludeDir:
    def test_found_when_include_exists(self, tmp_path):
        (tmp_path / "include").mkdir()
        assert resolve_musl_include_dir(str(tmp_path)) == str(tmp_path / "include")

    def test_none_when_include_absent(self, tmp_path):
        assert resolve_musl_include_dir(str(tmp_path)) is None


class TestGenerateMulSpecs:
    def test_contains_nostdinc(self, tmp_path):
        specs = generate_musl_specs("/musl/include", "/musl/lib")
        assert "-nostdinc" in specs

    def test_contains_include_dir(self, tmp_path):
        specs = generate_musl_specs("/musl/include", "/musl/usr/lib")
        assert "-isystem /musl/include" in specs

    def test_contains_lib_dir_in_link_libgcc(self):
        specs = generate_musl_specs("/inc", "/mylib")
        assert "-L/mylib" in specs

    def test_contains_crt1_in_startfile(self):
        specs = generate_musl_specs("/inc", "/mylib")
        assert "/mylib/crt1.o" in specs
        assert "/mylib/crti.o" in specs

    def test_contains_crtn_in_endfile(self):
        specs = generate_musl_specs("/inc", "/mylib")
        assert "/mylib/crtn.o" in specs

    def test_contains_elf_i386_link_flag(self):
        specs = generate_musl_specs("/inc", "/lib")
        assert "-m elf_i386" in specs

    def test_contains_musl_dynamic_linker(self):
        specs = generate_musl_specs("/inc", "/lib")
        assert "ld-musl-i386.so.1" in specs

    def test_dynamic_linker_is_conditional_on_not_static(self):
        specs = generate_musl_specs("/inc", "/lib")
        # The dynamic linker must be guarded so -static binaries are not
        # linked against it.  Without this guard musl-gcc ignores -static.
        assert "%{!static:-dynamic-linker /lib/ld-musl-i386.so.1}" in specs

    def test_renames_cpp_options(self):
        specs = generate_musl_specs("/inc", "/lib")
        assert "%rename cpp_options old_cpp_options" in specs

    def test_brace_escape_in_startfile(self):
        specs = generate_musl_specs("/inc", "/lib")
        # %{!shared:...} must appear literally (not as a Python format artifact)
        assert "%{!shared:" in specs

    def test_contains_libssp_nonshared_in_libgcc(self):
        specs = generate_musl_specs("/inc", "/lib")
        assert "libssp_nonshared.a%s" in specs


class TestEnsureMulSpecs:
    def test_no_op_when_specs_already_up_to_date(self, tmp_path):
        """An up-to-date specs file (with %{!static:}) is left unchanged."""
        _make_musl_layout(tmp_path, "usr/lib")
        specs_path = tmp_path / "lib" / "musl-gcc.specs"
        specs_path.parent.mkdir(parents=True, exist_ok=True)
        good_content = "*link:\n-m elf_i386 %{!static:-dynamic-linker /lib/ld-musl-i386.so.1}\n"
        specs_path.write_text(good_content)
        assert ensure_musl_specs(str(tmp_path)) is True
        assert specs_path.read_text() == good_content

    def test_migrates_stale_specs_missing_static_guard(self, tmp_path):
        """Stale specs without %{!static:} are detected and regenerated."""
        _make_musl_layout(tmp_path, "usr/lib")
        specs_path = tmp_path / "lib" / "musl-gcc.specs"
        specs_path.parent.mkdir(parents=True, exist_ok=True)
        specs_path.write_text("*link:\n-m elf_i386 -dynamic-linker /lib/ld-musl-i386.so.1\n")
        assert ensure_musl_specs(str(tmp_path)) is True
        new_content = specs_path.read_text()
        assert "%{!static:" in new_content

    def test_generates_when_missing(self, tmp_path):
        _make_musl_layout(tmp_path, "usr/lib")
        specs_path = tmp_path / "lib" / "musl-gcc.specs"
        assert not specs_path.exists()
        result = ensure_musl_specs(str(tmp_path))
        assert result is True
        assert specs_path.exists()
        content = specs_path.read_text()
        assert "-nostdinc" in content

    def test_specs_points_to_correct_lib_dir(self, tmp_path):
        _make_musl_layout(tmp_path, "usr/lib")
        ensure_musl_specs(str(tmp_path))
        specs = (tmp_path / "lib" / "musl-gcc.specs").read_text()
        assert str(tmp_path / "usr" / "lib") in specs

    def test_returns_false_when_include_missing(self, tmp_path):
        # No include dir — layout is incomplete
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "libc.a").write_bytes(b"AR")
        (lib_dir / "crt1.o").write_bytes(b"\x7fELF")
        assert ensure_musl_specs(str(tmp_path)) is False

    def test_returns_false_when_lib_dir_missing(self, tmp_path):
        (tmp_path / "include").mkdir()
        assert ensure_musl_specs(str(tmp_path)) is False

    def test_returns_false_on_permission_error(self, tmp_path, monkeypatch):
        _make_musl_layout(tmp_path, "usr/lib")

        def raise_permission(*args, **kwargs):
            raise PermissionError("read-only")

        monkeypatch.setattr("builtins.open", raise_permission)
        assert ensure_musl_specs(str(tmp_path)) is False


class TestRepairMulWrapper:
    def _make_wrapper(self, prefix, content="#!/bin/sh\nexec gcc -specs /bad/path \"$@\"\n"):
        wrapper = prefix / "bin" / "musl-gcc"
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        wrapper.write_text(content)
        wrapper.chmod(0o755)
        return wrapper

    def test_no_op_when_wrapper_absent(self, tmp_path):
        # Should not raise
        repair_musl_wrapper(str(tmp_path))

    def test_generates_specs_when_missing(self, tmp_path, monkeypatch):
        _make_musl_layout(tmp_path, "usr/lib")
        self._make_wrapper(tmp_path)
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/gcc" if name in ("gcc", "i686-linux-gnu-gcc") else None)

        repair_musl_wrapper(str(tmp_path))

        specs_path = tmp_path / "lib" / "musl-gcc.specs"
        assert specs_path.exists()
        assert "-nostdinc" in specs_path.read_text()

    def test_rewrites_wrapper_with_correct_gcc(self, tmp_path, monkeypatch):
        _make_musl_layout(tmp_path, "usr/lib")
        self._make_wrapper(tmp_path)
        monkeypatch.setattr(
            "shutil.which",
            lambda name: "/usr/bin/i686-linux-gnu-gcc" if name == "i686-linux-gnu-gcc" else None,
        )

        repair_musl_wrapper(str(tmp_path))

        wrapper_content = (tmp_path / "bin" / "musl-gcc").read_text()
        assert "/usr/bin/i686-linux-gnu-gcc" in wrapper_content
        assert "musl-gcc.specs" in wrapper_content

    def test_wrapper_print_file_name_uses_resolved_lib_dir(self, tmp_path, monkeypatch):
        _make_musl_layout(tmp_path, "usr/lib")
        self._make_wrapper(tmp_path)
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/gcc" if name in ("gcc", "i686-linux-gnu-gcc") else None)

        repair_musl_wrapper(str(tmp_path))

        wrapper_content = (tmp_path / "bin" / "musl-gcc").read_text()
        # The -print-file-name lookup must use usr/lib (where libc.a actually is)
        assert str(tmp_path / "usr" / "lib") in wrapper_content

    def test_skips_when_layout_incomplete(self, tmp_path, monkeypatch):
        # Wrapper exists but no include/lib layout
        self._make_wrapper(tmp_path)
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/gcc" if name == "gcc" else None)

        repair_musl_wrapper(str(tmp_path))

        # Specs should NOT have been generated
        assert not (tmp_path / "lib" / "musl-gcc.specs").exists()

    def test_skips_when_no_host_gcc(self, tmp_path, monkeypatch):
        _make_musl_layout(tmp_path, "usr/lib")
        self._make_wrapper(tmp_path)
        monkeypatch.setattr("shutil.which", lambda name: None)

        # Should not raise
        repair_musl_wrapper(str(tmp_path))

    def test_prefers_i686_linux_gnu_gcc_over_plain_gcc(self, tmp_path, monkeypatch):
        _make_musl_layout(tmp_path, "usr/lib")
        self._make_wrapper(tmp_path)
        monkeypatch.setattr(
            "shutil.which",
            lambda name: {
                "i686-linux-gnu-gcc": "/usr/bin/i686-linux-gnu-gcc",
                "gcc": "/usr/bin/gcc",
            }.get(name),
        )

        repair_musl_wrapper(str(tmp_path))

        wrapper_content = (tmp_path / "bin" / "musl-gcc").read_text()
        assert "i686-linux-gnu-gcc" in wrapper_content
        # Plain gcc should NOT appear in the exec line when cross-compiler is found
        assert "/usr/bin/gcc" not in wrapper_content


class TestEnsureMuslDynlinker:
    def _make_usr_lib(self, root):
        usr_lib = root / "usr" / "lib"
        usr_lib.mkdir(parents=True, exist_ok=True)
        (usr_lib / "libc.so").write_bytes(b"\x7fELF")
        return usr_lib

    def test_creates_symlink_when_absent(self, tmp_path):
        self._make_usr_lib(tmp_path)
        result = ensure_musl_dynlinker(str(tmp_path))
        assert result is True
        dynlinker = tmp_path / "lib" / "ld-musl-i386.so.1"
        assert dynlinker.is_symlink()
        assert os.readlink(str(dynlinker)) == "../usr/lib/libc.so"

    def test_no_op_when_symlink_already_correct(self, tmp_path):
        self._make_usr_lib(tmp_path)
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir(parents=True, exist_ok=True)
        dynlinker = lib_dir / "ld-musl-i386.so.1"
        dynlinker.symlink_to("../usr/lib/libc.so")
        result = ensure_musl_dynlinker(str(tmp_path))
        assert result is True
        assert os.readlink(str(dynlinker)) == "../usr/lib/libc.so"

    def test_repairs_dangling_symlink(self, tmp_path):
        self._make_usr_lib(tmp_path)
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir(parents=True, exist_ok=True)
        dynlinker = lib_dir / "ld-musl-i386.so.1"
        dynlinker.symlink_to("/nonexistent/path")
        result = ensure_musl_dynlinker(str(tmp_path))
        assert result is True
        assert os.readlink(str(dynlinker)) == "../usr/lib/libc.so"

    def test_repairs_wrong_target_symlink(self, tmp_path):
        usr_lib = self._make_usr_lib(tmp_path)
        (usr_lib / "other.so").write_bytes(b"\x7fELF")
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir(parents=True, exist_ok=True)
        dynlinker = lib_dir / "ld-musl-i386.so.1"
        dynlinker.symlink_to("../usr/lib/other.so")
        result = ensure_musl_dynlinker(str(tmp_path))
        assert result is True
        assert os.readlink(str(dynlinker)) == "../usr/lib/libc.so"

    def test_leaves_regular_file_untouched(self, tmp_path):
        self._make_usr_lib(tmp_path)
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir(parents=True, exist_ok=True)
        dynlinker = lib_dir / "ld-musl-i386.so.1"
        dynlinker.write_bytes(b"\x7fELF")
        result = ensure_musl_dynlinker(str(tmp_path))
        assert result is True
        assert not dynlinker.is_symlink()

    def test_returns_false_when_libc_so_absent(self, tmp_path):
        (tmp_path / "usr" / "lib").mkdir(parents=True)
        result = ensure_musl_dynlinker(str(tmp_path))
        assert result is False
        assert not (tmp_path / "lib" / "ld-musl-i386.so.1").exists()

    def test_accepts_ld_musl_i386_so1_as_target(self, tmp_path):
        usr_lib = tmp_path / "usr" / "lib"
        usr_lib.mkdir(parents=True, exist_ok=True)
        (usr_lib / "ld-musl-i386.so.1").write_bytes(b"\x7fELF")
        result = ensure_musl_dynlinker(str(tmp_path))
        assert result is True
        dynlinker = tmp_path / "lib" / "ld-musl-i386.so.1"
        assert dynlinker.is_symlink()
