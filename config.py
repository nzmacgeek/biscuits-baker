"""
config.py - Configuration loader for Baker.

Loads and validates baker.yaml, providing a typed Config object used
throughout the Baker pipeline.
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

DEFAULTS: Dict[str, Any] = {
    "arch": "x86_64",
    "kernel_source": "src/biscuits",
    "sysroot": "sysroot",
    "output_dir": "output",
    "build_dir": "build",
    "sources_dir": "src",
    "log_level": "info",
    "kernel": {
        "config": "kernel.config",
        "make_flags": "-j4",
        "install_modules": True,
    },
    "network": {
        "kernel_repo": "https://github.com/nzmacgeek/biscuits-kernel",
        "kernel_branch": "main",
        "extra_repos": [],
    },
    "components": [],
    "exclude": [],
    "image": {
        "enabled": False,
        "format": "ext2",
        "size_mb": 64,
        "output": "output/clawos.img",
        "bootloader": "none",
    },
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class KernelConfig:
    config: str = "kernel.config"
    make_flags: str = "-j4"
    install_modules: bool = True


@dataclass
class NetworkConfig:
    kernel_repo: str = "https://github.com/nzmacgeek/biscuits-kernel"
    kernel_branch: str = "main"
    extra_repos: List[str] = field(default_factory=list)


@dataclass
class ComponentEntry:
    name: str
    enabled: bool = True
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageConfig:
    enabled: bool = False
    format: str = "ext2"
    size_mb: int = 64
    output: str = "output/clawos.img"
    bootloader: str = "none"


@dataclass
class Config:
    arch: str = "x86_64"
    kernel_source: str = "src/biscuits"
    sysroot: str = "sysroot"
    output_dir: str = "output"
    build_dir: str = "build"
    sources_dir: str = "src"
    log_level: str = "info"
    kernel: KernelConfig = field(default_factory=KernelConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    components: List[ComponentEntry] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    image: ImageConfig = field(default_factory=ImageConfig)

    # Resolved absolute paths (populated after load)
    abs_sysroot: str = ""
    abs_output_dir: str = ""
    abs_build_dir: str = ""
    abs_sources_dir: str = ""
    abs_kernel_source: str = ""


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge *override* into a copy of *base*."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str = "baker.yaml") -> Config:
    """Load baker.yaml from *path* and return a validated :class:`Config`."""
    raw: Dict[str, Any] = {}

    if os.path.exists(path):
        with open(path, "r") as fh:
            loaded = yaml.safe_load(fh)
            if isinstance(loaded, dict):
                raw = loaded
        logger.debug("Loaded configuration from %s", path)
    else:
        logger.warning("Configuration file %s not found; using defaults.", path)

    data = _deep_merge(DEFAULTS, raw)

    # --- kernel ---
    k = data.get("kernel", {})
    kernel = KernelConfig(
        config=k.get("config", "kernel.config"),
        make_flags=k.get("make_flags", "-j4"),
        install_modules=bool(k.get("install_modules", True)),
    )

    # --- network ---
    n = data.get("network", {})
    network = NetworkConfig(
        kernel_repo=n.get("kernel_repo", DEFAULTS["network"]["kernel_repo"]),
        kernel_branch=n.get("kernel_branch", "main"),
        extra_repos=list(n.get("extra_repos", [])),
    )

    # --- components ---
    raw_components = data.get("components", [])
    components: List[ComponentEntry] = []
    for entry in raw_components:
        if isinstance(entry, str):
            components.append(ComponentEntry(name=entry))
        elif isinstance(entry, dict):
            name = entry.get("name", "")
            enabled = bool(entry.get("enabled", True))
            options = {k: v for k, v in entry.items() if k not in ("name", "enabled")}
            components.append(ComponentEntry(name=name, enabled=enabled, options=options))

    # --- image ---
    img = data.get("image", {})
    image = ImageConfig(
        enabled=bool(img.get("enabled", False)),
        format=img.get("format", "ext2"),
        size_mb=int(img.get("size_mb", 64)),
        output=img.get("output", "output/clawos.img"),
        bootloader=img.get("bootloader", "none"),
    )

    cfg = Config(
        arch=str(data.get("arch", "x86_64")),
        kernel_source=str(data.get("kernel_source", "src/biscuits")),
        sysroot=str(data.get("sysroot", "sysroot")),
        output_dir=str(data.get("output_dir", "output")),
        build_dir=str(data.get("build_dir", "build")),
        sources_dir=str(data.get("sources_dir", "src")),
        log_level=str(data.get("log_level", "info")),
        kernel=kernel,
        network=network,
        components=components,
        exclude=list(data.get("exclude", [])),
        image=image,
    )

    # Resolve absolute paths relative to the config file's directory
    base_dir = os.path.abspath(os.path.dirname(path)) if path else os.getcwd()
    cfg.abs_sysroot = os.path.join(base_dir, cfg.sysroot)
    cfg.abs_output_dir = os.path.join(base_dir, cfg.output_dir)
    cfg.abs_build_dir = os.path.join(base_dir, cfg.build_dir)
    cfg.abs_sources_dir = os.path.join(base_dir, cfg.sources_dir)
    cfg.abs_kernel_source = os.path.join(base_dir, cfg.kernel_source)

    return cfg
