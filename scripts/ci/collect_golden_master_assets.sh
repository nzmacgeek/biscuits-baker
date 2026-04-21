#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <build-number> <release-intent:true|false>" >&2
    exit 2
fi

build_number="$1"
release_intent="$2"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

bundle_root="dist/golden-master"
assets_dir="$bundle_root/assets"
metadata_dir="$bundle_root/metadata"
logs_dir="$bundle_root/logs"

rm -rf "$bundle_root"
mkdir -p "$assets_dir" "$metadata_dir" "$logs_dir"

# Required golden master output: disk image.
img_count=0
while IFS= read -r img; do
    cp -f "$img" "$assets_dir/"
    img_count=$((img_count + 1))
done < <(find output -maxdepth 1 -type f -name '*.img' | sort)

if (( img_count == 0 )); then
    echo "No disk image (*.img) found in output/." >&2
    exit 1
fi

# Include all built packages.
while IFS= read -r pkg; do
    cp -f "$pkg" "$assets_dir/"
done < <(find core -maxdepth 1 -type f -name '*.dpk' | sort)

# Include logs if they exist.
if [[ -d build/logs ]]; then
    cp -a build/logs/. "$logs_dir/"
fi

build_date="$(date -u +%Y-%m-%d)"
release_tag="gm-$(date -u +%Y%m%d)-build${build_number}"
commit_sha="$(git rev-parse HEAD)"

( cd "$assets_dir" && sha256sum * > "$REPO_ROOT/$metadata_dir/SHA256SUMS" )

cat > "$metadata_dir/build-metadata.env" <<EOF
BUILD_NUMBER=$build_number
RELEASE_INTENT=$release_intent
BUILD_DATE=$build_date
RELEASE_TAG=$release_tag
COMMIT_SHA=$commit_sha
EOF

cat > "$metadata_dir/release-notes.md" <<EOF
Golden master build $build_number

- Build date (UTC): $build_date
- Commit: $commit_sha
- Release intent: $release_intent

Attached assets:
- Disk image(s) from output/
- Package files from core/
- SHA256SUMS
EOF

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    {
        echo "bundle_root=$bundle_root"
        echo "assets_dir=$assets_dir"
        echo "metadata_dir=$metadata_dir"
        echo "release_tag=$release_tag"
    } >> "$GITHUB_OUTPUT"
fi

echo "Bundle prepared at $bundle_root"
