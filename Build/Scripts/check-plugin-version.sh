#!/usr/bin/env bash
set -euo pipefail
TAGS=$(git tag --points-at HEAD | sed -nE 's/^v?([0-9]+\.[0-9]+\.[0-9]+)$/\1/p' || true)
[[ -z "${TAGS}" ]] && exit 0
PLUGIN_VERSION=$(python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])")
if [[ -z "${PLUGIN_VERSION}" ]]; then
    echo "ERROR: Could not extract version from .claude-plugin/plugin.json" >&2
    exit 1
fi
if ! echo "${TAGS}" | grep -qFx "${PLUGIN_VERSION}"; then
    echo "ERROR: .claude-plugin/plugin.json version (${PLUGIN_VERSION}) does not match any semver tag at HEAD." >&2
    echo "Tags found at HEAD:" >&2
    echo "${TAGS}" >&2
    exit 1
fi
