#!/usr/bin/env bash
set -euo pipefail

# Computes the next build number from existing golden-master tags.
# Falls back to BUILD_NUMBER file when no matching tags exist.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

git fetch --tags --force >/dev/null 2>&1 || true

max_tag_build=""
while IFS= read -r tag; do
    n="$(printf '%s' "$tag" | sed -n 's/^gm-.*-build\([0-9][0-9]*\)$/\1/p')"
    if [[ -n "$n" ]]; then
        if [[ -z "$max_tag_build" ]] || (( n > max_tag_build )); then
            max_tag_build="$n"
        fi
    fi
done < <(git tag -l 'gm-*-build*')

file_build=""
if [[ -f BUILD_NUMBER ]]; then
    raw="$(tr -d '[:space:]' < BUILD_NUMBER)"
    if [[ "$raw" =~ ^[0-9]+$ ]]; then
        file_build="$raw"
    fi
fi

base=0
if [[ -n "$max_tag_build" ]]; then
    base="$max_tag_build"
elif [[ -n "$file_build" ]]; then
    base="$file_build"
fi

build_number=$((base + 1))
printf '%s\n' "$build_number" > BUILD_NUMBER

build_date="$(date -u +%Y-%m-%d)"
short_sha="$(git rev-parse --short=12 HEAD)"
release_tag="gm-$(date -u +%Y%m%d)-build${build_number}"

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    {
        echo "build_number=$build_number"
        echo "build_date=$build_date"
        echo "short_sha=$short_sha"
        echo "release_tag=$release_tag"
    } >> "$GITHUB_OUTPUT"
fi

echo "build_number=$build_number"
echo "release_tag=$release_tag"
