# biscuits-baker

A modular build pipeline that bootstraps the [Biscuits](https://github.com/nzmacgeek/biscuits) kernel and the full BlueyOS userland — from source fetch through cross-compiler toolchain, C library, packages, and bootable image.

---

## Contents

- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Pipeline stages](#pipeline-stages)
- [Command reference](#command-reference)
- [Configuration](#configuration)
- [Adding a new package](#adding-a-new-package)
- [Project layout](#project-layout)
- [Running the tests](#running-the-tests)

---

## Prerequisites

Baker requires a POSIX host (Debian/Ubuntu recommended).

**System packages**

```bash
sudo apt-get update
sudo apt-get install -y \
    git make gcc gcc-multilib binutils nasm \
    python3 python3-pip \
    go golang-go \
    zic wget curl \
    grub-pc-bin xorriso
```

**Python dependencies**

```bash
pip install -r requirements.txt
# or install Baker itself
pip install -e .
```

**Optional — for elevated-privilege installs to `/opt/`**

The toolchain stage installs the cross-compiler and musl to `/opt/blueyos-cross` and
`/opt/blueyos-sysroot`. Run Baker with `sudo` or pre-create those directories with the
correct ownership if you want system-wide installs.  
If neither directory is writable Baker falls back to `build/musl` automatically.

---

## Quick start

```bash
# 1. Clone this repo
git clone https://github.com/nzmacgeek/biscuits-baker
cd biscuits-baker

# 2. Run the full pipeline (fetch → kernel → toolchain → build → package → image)
baker all

# 3. Find your bootable ISO
ls output/blueyos.iso

# 4. Find the built .dpk packages
ls core/
```

If you do not have `baker` on PATH yet, replace `baker` with `python baker.py`.

---

## Pipeline stages

Baker runs stages in order. You can run them individually for incremental builds.

| Order | Stage | What it does |
|-------|-------|--------------|
| 1 | **prepare** | Clones/updates all source repos; runs change-detection and reports which repos have new commits |
| 2 | **kernel** | Runs `make tools-host` then `make` inside the biscuits repo; installs `build/kernel/bkernel` + `grub.cfg` to `sysroot/boot/` |
| 3 | **toolchain** | Builds the `i686-elf` cross-compiler via `tools/make-libc-toolchain.sh`; builds and installs musl-blueyos via `tools/build-musl.sh` |
| 4 | **build** | Builds each enabled component recipe in dependency order against musl-blueyos |
| 5 | **package** | Calls each component's `dpkbuild` packaging flow and copies the resulting `.dpk` files to `core/` |
| 6 | **image** | Delegates to biscuits' `make iso` (GRUB-bootable ISO) or `make disk` (raw image) |

### Source repositories fetched during `prepare`

| Repo | Cloned to |
|------|-----------|
| `nzmacgeek/biscuits` | `src/biscuits/` |
| `nzmacgeek/musl-blueyos` | `src/biscuits/musl-blueyos/` |
| `nzmacgeek/dimsim` | `src/dimsim/` |
| `nzmacgeek/claw` | `src/claw/` |
| `nzmacgeek/matey` | `src/matey/` |
| `nzmacgeek/blueyos-bash` | `src/blueyos-bash/` (builds `ncurses`, `readline`, `bash`) |
| `nzmacgeek/blueyos-tzinfo` | `src/blueyos-tzinfo/` |
| `nzmacgeek/blueyos-base` | `src/blueyos-base/` |
| `nzmacgeek/login-tools` | `src/login-tools/` |
| `nzmacgeek/walkies` | `src/walkies/` |
| `nzmacgeek/yap` | `src/yap/` |

---

## Command reference

Global option for one-shot sysroot overrides:

```bash
baker --sysroot-target /path/to/sysroot <command>
```

This forces install/output paths to the given sysroot for that run only,
without editing `baker.yaml`.

### `baker prepare`

Fetch or update all source repositories and detect which ones have changed since the last run.

```bash
baker prepare
```

Baker writes a `.baker_state.json` file to `build/` recording the HEAD commit hash of every
repo. On subsequent runs it reports any repos with new commits — those components will be
rebuilt automatically on the next `baker build`.

---

### `baker kernel`

Build the Biscuits kernel and install it to `sysroot/boot/`.

```bash
baker kernel
```

Internally runs (inside `src/biscuits/`):
1. `make tools-host` — builds BlueyFS host utilities
2. `make -j4` — compiles the i386 ELF kernel
3. Copies `build/kernel/bkernel` and `grub.cfg` to `<sysroot>/boot/`

---

### `baker toolchain`

Build the cross-compiler toolchain and musl-blueyos C library.

```bash
baker toolchain
# or, to avoid sudo, point at a writable prefix:
baker --config baker.yaml toolchain
```

Steps:
1. Runs `tools/make-libc-toolchain.sh` inside the biscuits repo to build
   `i686-elf` binutils + GCC and install to `/opt/blueyos-cross`.
2. Runs `tools/build-musl.sh` to configure, build, and install musl-blueyos to:
   - `build/musl/` — local repo prefix (always writable)
   - `/opt/blueyos-sysroot` — runtime sysroot (skipped if not writable)
   - `/opt/blueyos-cross/musl` — cross-toolchain musl prefix (skipped if not writable)

The toolchain build is skipped if `i686-elf-gcc` is already present in the install prefix.

---

### `baker build`

Build all enabled components in dependency order against musl-blueyos.

```bash
baker build
```

Rebuild a single component repeatedly (fast edit/build loop):

```bash
baker build --component matey
```

Force that install into a specific sysroot target:

```bash
baker --sysroot-target /tmp/blueyos-sysroot build --component matey
```

When `--component` is used, Baker always checks that the component repo's
local `main` is up to date with `origin/main` first (fetch + fast-forward pull).

If you also want to rebuild that component's dependencies:

```bash
baker build --component matey --with-deps
```

Each recipe runs `configure → build → install` into the sysroot. The musl sysroot is
passed via the `MUSL_PREFIX` environment variable so each package's Makefile picks it up
automatically.

---

### `baker package`

Package each component and copy the results to `core/`.

```bash
baker package
```

For each component Baker runs its packaging target with `dpkbuild` and expects a `.dpk`
artifact. If `dpkbuild` is missing, Baker now fails that component's packaging step
explicitly instead of silently producing a `tar.gz`. All produced packages are copied to
`core/` so you can inspect them independently of the output directory.

---

### `baker image`

Assemble a bootable image from the sysroot.

```bash
baker image
```

Delegates to `make iso` (GRUB + xorriso) inside the biscuits source tree, producing
`output/blueyos.iso`. Falls back to `make disk` (BlueyFS raw image) and then to a generic
`ext2`/`tar` fallback for minimal environments.

---

### `baker all`

Run the complete pipeline in order:

```
prepare → kernel → toolchain → build → package → image
```

```bash
baker all
# or with a custom config file:
baker --config /path/to/baker.yaml all
```

---

### `baker passwd`

Set the root password inside the sysroot.

```bash
# Interactive prompt (recommended — password not visible in shell history)
baker passwd

# Non-interactive (for CI)
baker passwd mysecretpassword
```

Baker generates a SHA-512 crypt hash and writes it to `<sysroot>/etc/shadow`. It also
ensures `/etc/passwd` has a root entry. No live `chroot` is required.

---

### `baker clean`

Remove build artefacts.

```bash
baker clean              # remove build/ only
baker clean --sysroot    # also remove sysroot/
baker clean --output     # also remove output/
baker clean --all        # remove build/, sysroot/, and output/
```

---

## Configuration

Baker reads `baker.yaml` (or a path supplied with `--config`). All paths are resolved
relative to the config file's directory.

```yaml
# Target architecture (biscuits defaults to i386)
arch: i386

# Source directories
kernel_source: src/biscuits   # where biscuits is checked out
sources_dir: src              # parent dir for all other repos
build_dir: build              # intermediate build artefacts
sysroot: sysroot              # assembled root filesystem
output_dir: output            # images and packages
core_packages_dir: core       # copy of every built .dpk

# musl-blueyos sysroot used by component builds.
# Leave empty to auto-detect: /opt/blueyos-sysroot if present, else build/musl
musl_prefix: ""

# Cross-compiler install prefix (toolchain stage)
toolchain_prefix: /opt/blueyos-cross

log_level: info   # debug | info | warning | error

kernel:
  config: ""          # path to .config relative to kernel_source; empty = upstream default
  make_flags: "-j4"   # passed to every make invocation
  install_modules: false

network:
  kernel_repo: "https://github.com/nzmacgeek/biscuits"
  kernel_branch: "main"
  musl_blueyos_repo: "https://github.com/nzmacgeek/musl-blueyos"
  dimsim_repo: "https://github.com/nzmacgeek/dimsim"
  package_repos:
    - name: claw
      url: "https://github.com/nzmacgeek/claw"
    - name: matey
      url: "https://github.com/nzmacgeek/matey"
    - name: blueyos-base
      url: "https://github.com/nzmacgeek/blueyos-base"
    - name: login-tools
      url: "https://github.com/nzmacgeek/login-tools"
      branch: "master"
    - name: walkies
      url: "https://github.com/nzmacgeek/walkies"
    # add more repos here ...
  extra_repos: []

components:
  - name: musl-blueyos
    enabled: true
  - name: dimsim
    enabled: true
  - name: claw
    enabled: true
  - name: matey
    enabled: true
  - name: ncurses
    enabled: true
  - name: readline
    enabled: true
  - name: bash
    enabled: true
  - name: blueyos-base
    enabled: true
  - name: login-tools
    enabled: true
  - name: walkies
    enabled: true
  - name: blueyos-tzinfo
    enabled: true

image:
  enabled: true
  format: iso          # iso | disk | ext2 | tar
  output: output/blueyos.iso
  bootloader: grub
```

### musl prefix resolution

Baker resolves `abs_musl_prefix` in this order:

1. Explicit `musl_prefix` in `baker.yaml`
2. `/opt/blueyos-sysroot` if that directory exists on the host
3. `build/musl` (always writeable fallback)

---

## Adding a new package

1. **Create a recipe** in `recipes/yourpkg.py`:

   ```python
   from recipes._musl_package import MuslPackageRecipe

   class YourPkgRecipe(MuslPackageRecipe):
       name = "yourpkg"
       version = "1.0.0"
       dependencies = ["musl-blueyos"]
       binary_name = "yourpkg"
       binary_dest = "usr/bin/yourpkg"
   ```

   For packages that need custom configure/install steps, subclass `BaseRecipe` directly.

2. **Register it** in `recipe_registry.py`:

   ```python
   from recipes.yourpkg import YourPkgRecipe

   RECIPE_CLASSES = [
       ...,
       YourPkgRecipe,
   ]
   ```

3. **Enable it** in `baker.yaml`:

   ```yaml
   network:
     package_repos:
       - name: yourpkg
         url: "https://github.com/yourorg/yourpkg"

   components:
     - name: yourpkg
       enabled: true
   ```

That's it — the prepare stage will clone the repo, the build stage will compile it against
musl-blueyos, the package stage will produce a `.dpk`, and a copy lands in `core/`.

---

## Project layout

```
biscuits-baker/
├── baker.py               CLI entry point
├── baker.yaml             Default configuration
├── config.py              Typed config loader (YAML → dataclasses)
├── deps.py                Dependency DAG with topological sort
├── stage_runner.py        Stage ABC + orchestrator
│
├── stages/
│   ├── prepare.py         Fetch/update all source repos, change detection
│   ├── kernel.py          Build biscuits kernel → sysroot/boot/
│   ├── toolchain.py       Build cross-compiler + musl-blueyos
│   ├── build.py           Build components in dependency order
│   ├── package.py         Package components → output/ and core/
│   ├── image.py           Assemble bootable image
│   └── clean.py           Remove build artefacts
│
├── recipes/
│   ├── base.py            BaseRecipe ABC
│   ├── _musl_package.py   Shared base for musl-linked packages
│   ├── musl_blueyos.py    C library (built by toolchain stage)
│   ├── dimsim.py          Package manager + dpkbuild
│   ├── claw.py            Init system
│   ├── matey.py           Getty
│   ├── ncurses.py         Terminal library from blueyos-bash repo
│   ├── readline.py        GNU Readline from blueyos-bash repo
│   ├── blueyos_bash.py    GNU Bash from blueyos-bash repo
│   ├── blueyos_base.py    Core BlueyOS utilities
│   ├── login_tools.py     Authentication and account tools
│   ├── walkies.py         Network configuration utility
│   └── blueyos_tzinfo.py  Timezone database
│
├── helpers/
│   ├── sysroot.py         SysrootInstaller — install files into sysroot
│   ├── packaging.py       PackageBuilder — produce tar.gz archives
│   ├── image.py           ImageBuilder — ext2/ISO/tar image assembly
│   ├── change_detection.py Git hash-based repo change tracking
│   └── password.py        Set root password inside a sysroot
│
└── tests/                 pytest test suite (81 tests)
```

---

## Running the tests

```bash
pip install pytest pyyaml
python -m pytest tests/ -v
```

No network access or build tools are required to run the test suite — all tests use
temporary directories and mock data.
