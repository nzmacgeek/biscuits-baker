#!/usr/bin/env python3
"""
baker - The bootstrapper for the Biscuits kernel and ClawOS system.

Usage:
    baker [--config FILE] [--verbose] <command>

Commands:
    prepare   Fetch/update source repositories
    kernel    Build the Biscuits kernel
    build     Build all enabled components (or one component)
    package   Package built components into distributable archives
    image     Assemble a bootable filesystem image
    vm        Boot the disk image in QEMU for interactive testing
    extract   Extract diagnostic files from the disk image
    all       Run prepare → kernel → build → package → image in order
    clean     Remove build artifacts

Run 'baker <command> --help' for command-specific options.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Ensure the repo root is on sys.path so imports work when baker.py is run
# directly (e.g. ./baker.py or python baker.py).
_repo_root = os.path.dirname(os.path.abspath(__file__))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from config import load_config
from stage_runner import StageRunner
from stages.prepare import PrepareStage
from stages.kernel import KernelStage
from stages.toolchain import ToolchainStage
from stages.build import BuildStage
from stages.package import PackageStage
from stages.image import ImageStage
from stages.vm import VmStage
from stages.extract import ExtractStage
from stages.clean import CleanStage

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

_LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def setup_logging(level: str) -> None:
    numeric = _LOG_LEVELS.get(level.lower(), logging.INFO)
    # Set root logger to DEBUG so per-recipe file handlers (also at DEBUG) can
    # receive propagated records.  The StreamHandler level controls what the
    # user actually sees on the console.
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(numeric)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            datefmt="%H:%M:%S",
        ))
        root.addHandler(handler)
    else:
        for h in root.handlers:
            h.setLevel(numeric)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baker",
        description="Baker – bootstrapper for the Biscuits kernel and ClawOS system.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--config",
        metavar="FILE",
        default="baker.yaml",
        help="Path to the Baker configuration file (default: baker.yaml)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug-level logging",
    )
    parser.add_argument(
        "--sysroot-target",
        "--force-sysroot",
        dest="sysroot_target",
        metavar="PATH",
        default=None,
        help="Force install/output sysroot target for this run (overrides baker.yaml sysroot)",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # prepare
    sub_prepare = subparsers.add_parser(
        "prepare",
        help="Fetch/update kernel and component source repositories",
    )

    # kernel
    sub_kernel = subparsers.add_parser(
        "kernel",
        help="Configure and build the Biscuits kernel",
    )

    # toolchain
    sub_toolchain = subparsers.add_parser(
        "toolchain",
        help="Build cross-compiler toolchain and musl-blueyos C library",
    )

    # build
    sub_build = subparsers.add_parser(
        "build",
        help="Build all enabled components in dependency order",
    )
    sub_build.add_argument(
        "--component", "-c",
        dest="build_component",
        metavar="NAME",
        default=None,
        help="Build only one enabled component by name",
    )
    sub_build.add_argument(
        "--with-deps",
        action="store_true",
        dest="build_with_deps",
        help="When used with --component, also rebuild that component's dependencies",
    )

    # package
    sub_package = subparsers.add_parser(
        "package",
        help="Package built components into distributable archives",
    )

    # image
    sub_image = subparsers.add_parser(
        "image",
        help="Assemble a bootable filesystem image from the sysroot",
    )

    # all
    sub_all = subparsers.add_parser(
        "all",
        help="Run the full pipeline: prepare → kernel → toolchain → build → package → image",
    )

    # passwd
    sub_passwd = subparsers.add_parser(
        "passwd",
        help="Set the root password inside the sysroot",
    )
    sub_passwd.add_argument(
        "password",
        nargs="?",
        default=None,
        help="New root password (prompted interactively if omitted)",
    )

    # vm
    sub_vm = subparsers.add_parser(
        "vm",
        help="Boot the disk image in QEMU for interactive testing",
    )
    sub_vm.add_argument(
        "--build",
        action="store_true",
        dest="vm_build",
        help="Rebuild the disk image before launching",
    )
    sub_vm.add_argument(
        "--no-snapshot",
        action="store_true",
        dest="vm_no_snapshot",
        help="Disable snapshot mode (disk image will be modified by this run)",
    )
    sub_vm.add_argument(
        "--ram",
        type=int,
        metavar="MB",
        dest="vm_ram",
        default=None,
        help="RAM in megabytes (overrides vm.ram_mb in config)",
    )
    sub_vm.add_argument(
        "--cpus",
        type=int,
        metavar="N",
        dest="vm_cpus",
        default=None,
        help="Virtual CPU count (overrides vm.cpus in config)",
    )
    sub_vm.add_argument(
        "--display",
        choices=["none", "gtk"],
        dest="vm_display",
        default=None,
        help="Display mode: none (headless serial) or gtk (graphical window)",
    )

    # extract
    sub_extract = subparsers.add_parser(
        "extract",
        help="Extract diagnostic files from the disk image (e.g. /var/log, /etc)",
    )
    sub_extract.add_argument(
        "--paths",
        nargs="+",
        metavar="PATH",
        dest="extract_paths",
        default=None,
        help="Absolute paths to extract from the image (default: /var/log /etc)",
    )
    sub_extract.add_argument(
        "--output",
        metavar="DIR",
        dest="extract_output",
        default=None,
        help="Output directory (default: output/extract-<timestamp>)",
    )
    sub_extract.add_argument(
        "--image",
        metavar="FILE",
        dest="extract_image",
        default=None,
        help="Disk image to read (default: image.output from config)",
    )

    # clean
    sub_clean = subparsers.add_parser(
        "clean",
        help="Remove build artifacts",
    )
    sub_clean.add_argument(
        "--sysroot",
        action="store_true",
        dest="clean_sysroot",
        help="Also remove the sysroot directory",
    )
    sub_clean.add_argument(
        "--output",
        action="store_true",
        dest="clean_output",
        help="Also remove the output directory",
    )
    sub_clean.add_argument(
        "--all",
        action="store_true",
        dest="clean_all",
        help="Remove build directory, sysroot, and output directory",
    )

    return parser


# ---------------------------------------------------------------------------
# Stage pipeline helpers
# ---------------------------------------------------------------------------

# Ordered list of stages for the 'all' command
ALL_STAGES = ["prepare", "kernel", "toolchain", "build", "package", "image"]


def _register_all_stages(runner: StageRunner) -> None:
    runner.register_many(
        PrepareStage,
        KernelStage,
        ToolchainStage,
        BuildStage,
        PackageStage,
        ImageStage,
        VmStage,
        ExtractStage,
        CleanStage,
    )


def _run_passwd(cfg, args) -> int:
    """Set the root password inside the sysroot."""
    import getpass
    from helpers.password import set_root_password

    password = getattr(args, "password", None)
    if not password:
        try:
            password = getpass.getpass(f"New root password for sysroot ({cfg.abs_sysroot}): ")
            confirm = getpass.getpass("Confirm password: ")
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.", file=sys.stderr)
            return 1
        if password != confirm:
            print("Passwords do not match.", file=sys.stderr)
            return 1
    if not password:
        print("Password cannot be empty.", file=sys.stderr)
        return 1

    logger = logging.getLogger("baker.passwd")
    try:
        set_root_password(cfg.abs_sysroot, password)
        logger.info("Root password set successfully in %s", cfg.abs_sysroot)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to set root password: %s", exc)
        return 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Load configuration
    cfg = load_config(args.config)

    # Optional one-shot sysroot override from CLI
    if args.sysroot_target:
        config_dir = os.path.abspath(os.path.dirname(args.config))
        forced = args.sysroot_target
        forced_abs = forced if os.path.isabs(forced) else os.path.abspath(os.path.join(config_dir, forced))
        cfg.abs_sysroot = forced_abs
        cfg.sysroot = forced_abs

    # Set up logging (CLI --verbose overrides config file)
    log_level = "debug" if args.verbose else cfg.log_level
    setup_logging(log_level)

    logger = logging.getLogger("baker")
    logger.info("Baker starting  (config: %s, arch: %s)", args.config, cfg.arch)

    # Build the stage runner
    runner = StageRunner(cfg)
    _register_all_stages(runner)

    # Dispatch to the requested command
    command = args.command

    if command == "prepare":
        results = runner.run_stages(["prepare"])

    elif command == "kernel":
        results = runner.run_stages(["kernel"])

    elif command == "toolchain":
        results = runner.run_stages(["toolchain"])

    elif command == "build":
        BuildStage.target_component = getattr(args, "build_component", None)
        BuildStage.include_dependencies = bool(getattr(args, "build_with_deps", False))
        BuildStage.check_main_updates = BuildStage.target_component is not None
        results = runner.run_stages(["build"])

    elif command == "package":
        results = runner.run_stages(["package"])

    elif command == "image":
        results = runner.run_stages(["image"])

    elif command == "vm":
        VmStage.build_image_first = getattr(args, "vm_build", False)
        # --no-snapshot explicitly disables snapshot; otherwise None means "use config"
        VmStage.snapshot_override = False if getattr(args, "vm_no_snapshot", False) else None
        VmStage.ram_override = getattr(args, "vm_ram", None)
        VmStage.cpus_override = getattr(args, "vm_cpus", None)
        VmStage.display_override = getattr(args, "vm_display", None)
        results = runner.run_stages(["vm"])

    elif command == "extract":
        from stages.extract import DEFAULT_PATHS
        ExtractStage.paths = getattr(args, "extract_paths", None) or DEFAULT_PATHS
        ExtractStage.output_dir = getattr(args, "extract_output", None)
        ExtractStage.image_override = getattr(args, "extract_image", None)
        results = runner.run_stages(["extract"])

    elif command == "all":
        results = runner.run_stages(ALL_STAGES)

    elif command == "passwd":
        return _run_passwd(cfg, args)

    elif command == "clean":
        # Patch CleanStage flags based on CLI args
        if getattr(args, "clean_all", False):
            CleanStage.clean_build = True
            CleanStage.clean_sysroot = True
            CleanStage.clean_output = True
        else:
            CleanStage.clean_sysroot = getattr(args, "clean_sysroot", False)
            CleanStage.clean_output = getattr(args, "clean_output", False)
        results = runner.run_stages(["clean"])

    else:
        parser.print_help()
        return 1

    runner.print_summary()

    return 0 if runner.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
