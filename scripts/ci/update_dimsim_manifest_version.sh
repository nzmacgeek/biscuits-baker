#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <build-number>" >&2
    exit 2
fi

build_number="$1"
if [[ ! "$build_number" =~ ^[0-9]+$ ]]; then
    echo "build number must be numeric" >&2
    exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

manifest=""
if [[ -f "src/dimsim/pkg/meta/manifest.json" ]]; then
    manifest="src/dimsim/pkg/meta/manifest.json"
else
    # Fallback search for repos that keep the package under a different path.
    while IFS= read -r path; do
        manifest="$path"
        break
    done < <(find src/dimsim -maxdepth 6 -type f -path '*/pkg/meta/manifest.json' 2>/dev/null | sort)
fi

if [[ -z "$manifest" ]]; then
    echo "No dimsim pkg/meta/manifest.json found; skipping version update."
    exit 0
fi

python3 - "$manifest" "$build_number" <<'PY'
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
build_number = sys.argv[2]

data = json.loads(manifest_path.read_text(encoding="utf-8"))
current = str(data.get("version", "0.1.0"))
base = current.split("+", 1)[0]
data["version"] = f"{base}+{build_number}"
manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(f"Updated {manifest_path} version: {current} -> {data['version']}")
PY
