"""
helpers/password.py - Root password helper for Baker.

Sets the root password inside a target sysroot by editing
``/etc/shadow`` and ``/etc/passwd``.  Uses Python's ``crypt`` module
(or ``openssl passwd`` as a fallback) to generate the password hash so
that no live chroot is required.

Usage example
-------------
::

    from helpers.password import set_root_password
    set_root_password("/path/to/sysroot", "my-secret-password")
"""

from __future__ import annotations

import logging
import os
import random
import string
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def set_root_password(sysroot: str, password: str) -> None:
    """Set the root password inside *sysroot*.

    This function:
    1. Generates a salted SHA-512 hash of *password*.
    2. Creates/updates ``/etc/shadow`` with the hashed root entry.
    3. Ensures ``/etc/passwd`` has a root entry (creates a minimal one if absent).

    Args:
        sysroot:  Absolute path to the target sysroot directory.
        password: Plain-text password to set for root.

    Raises:
        RuntimeError: If the password hash cannot be generated.
    """
    sysroot = os.path.abspath(sysroot)
    if not os.path.isdir(sysroot):
        raise RuntimeError(f"Sysroot directory not found: {sysroot}")

    etc_dir = os.path.join(sysroot, "etc")
    os.makedirs(etc_dir, exist_ok=True)

    pw_hash = _generate_hash(password)
    logger.debug("Generated root password hash (SHA-512/crypt)")

    _update_shadow(sysroot, pw_hash)
    _ensure_passwd(sysroot)

    logger.info("Root password set in sysroot: %s", sysroot)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def _generate_hash(password: str) -> str:
    """Return a ``$6$…`` (SHA-512) crypt hash for *password*."""
    # Try Python's built-in crypt module first (available in 3.x, deprecated 3.13+)
    try:
        import crypt  # noqa: PLC0415
        salt = crypt.mksalt(crypt.METHOD_SHA512)
        return crypt.crypt(password, salt)
    except (ImportError, AttributeError):
        pass

    # Try the hashlib-based approach available in Python ≥ 3.13
    try:
        from hashlib import scrypt  # noqa: F401 – just checking availability
        # Fall through to openssl which is simpler to invoke
    except ImportError:
        pass

    # Fallback: use openssl on the host
    return _openssl_hash(password)


def _openssl_hash(password: str) -> str:
    """Generate a SHA-512 crypt hash using the host ``openssl`` binary.

    The password is passed via stdin rather than as a command-line argument
    to avoid leaking it through the process list (``ps``/``/proc``).
    """
    salt = _random_salt(16)
    result = subprocess.run(
        ["openssl", "passwd", "-6", "-salt", salt, "-stdin"],
        input=password,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(
            f"openssl passwd failed (exit {result.returncode}): {result.stderr}"
        )
    return result.stdout.strip()


def _random_salt(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "./"
    return "".join(random.SystemRandom().choices(alphabet, k=length))


# ---------------------------------------------------------------------------
# /etc/shadow management
# ---------------------------------------------------------------------------


def _update_shadow(sysroot: str, pw_hash: str) -> None:
    """Write (or update) the root entry in /etc/shadow."""
    shadow_path = os.path.join(sysroot, "etc", "shadow")

    # Build the new root entry (shadow format, 9 colon-separated fields)
    # days_since_epoch=0 means "last change = epoch", all aging fields empty
    new_root_line = f"root:{pw_hash}:0:0:99999:7:::\n"

    if os.path.isfile(shadow_path):
        lines = _read_lines(shadow_path)
        updated = False
        for i, line in enumerate(lines):
            if line.startswith("root:"):
                lines[i] = new_root_line
                updated = True
                break
        if not updated:
            lines.insert(0, new_root_line)
        _write_lines(shadow_path, lines)
        os.chmod(shadow_path, 0o600)
        logger.debug("Updated root entry in %s", shadow_path)
    else:
        _write_lines(shadow_path, [new_root_line])
        os.chmod(shadow_path, 0o600)
        logger.debug("Created %s with root entry", shadow_path)


# ---------------------------------------------------------------------------
# /etc/passwd management
# ---------------------------------------------------------------------------


def _ensure_passwd(sysroot: str) -> None:
    """Ensure /etc/passwd contains a root entry (creates minimal file if absent)."""
    passwd_path = os.path.join(sysroot, "etc", "passwd")
    preferred_shell = "/bin/bash" if os.path.isfile(os.path.join(sysroot, "bin", "bash")) else "/bin/sh"

    # Minimal root passwd line (no password field — auth is via shadow)
    root_line = f"root:x:0:0:root:/root:{preferred_shell}\n"

    if os.path.isfile(passwd_path):
        lines = _read_lines(passwd_path)
        for i, line in enumerate(lines):
            if line.startswith("root:"):
                parts = line.rstrip("\n").split(":")
                if len(parts) >= 7 and parts[6] != preferred_shell:
                    parts[6] = preferred_shell
                    lines[i] = ":".join(parts) + "\n"
                    _write_lines(passwd_path, lines)
                    os.chmod(passwd_path, 0o644)
                    logger.debug("Updated root shell in %s", passwd_path)
                    return
                logger.debug("/etc/passwd already has a root entry; no change needed.")
                return
        # root entry missing — prepend it
        lines.insert(0, root_line)
        _write_lines(passwd_path, lines)
        os.chmod(passwd_path, 0o644)
        logger.debug("Added root entry to %s", passwd_path)
    else:
        _write_lines(passwd_path, [root_line])
        os.chmod(passwd_path, 0o644)
        logger.debug("Created %s with root entry", passwd_path)


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------


def _read_lines(path: str) -> list:
    with open(path, "r", errors="replace") as fh:
        return fh.readlines()


def _write_lines(path: str, lines: list) -> None:
    # Write with O_CREAT | O_WRONLY | O_TRUNC and mode 0o600 for shadow files,
    # then fchmod to ensure correct mode even if an existing file's mode was wider.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.writelines(lines)
    except Exception:
        # fd is already owned by fdopen — do not double-close
        raise
    os.chmod(path, 0o600)
