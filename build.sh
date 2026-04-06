#!/usr/bin/env bash
# build.sh — create a distributable zip of the email-manager plugin
# Usage: ./build.sh [version]
# Output: dist/email-manager-<version>.zip

set -euo pipefail

VERSION="${1:-$(date +%Y%m%d)}"
DIST_DIR="dist"
PLUGIN_NAME="email-manager"
OUT_ZIP="${DIST_DIR}/${PLUGIN_NAME}-${VERSION}.zip"

echo "Building ${PLUGIN_NAME} v${VERSION}..."

# Clean
rm -rf "${DIST_DIR}"
mkdir -p "${DIST_DIR}"

# Files to include
INCLUDE=(
  ".claude-plugin/"
  "email_manager/"
  "config/accounts.example.yaml"
  "run.py"
  "requirements.txt"
  "README.md"
)

# Exclude patterns
EXCLUDE=(
  "*.pyc"
  "__pycache__"
  "*.egg-info"
  ".DS_Store"
  "config/accounts.yaml"   # never bundle real credentials
  "*.env"
)

# Build exclude args for zip
EXCLUDE_ARGS=()
for pat in "${EXCLUDE[@]}"; do
  EXCLUDE_ARGS+=("--exclude=*${pat}*")
done

zip -r "${OUT_ZIP}" "${INCLUDE[@]}" "${EXCLUDE_ARGS[@]}"

SIZE=$(du -sh "${OUT_ZIP}" | cut -f1)
echo ""
echo "✓ Built: ${OUT_ZIP} (${SIZE})"
echo ""
echo "To install locally:"
echo "  unzip ${OUT_ZIP} -d ~/.claude/plugins/${PLUGIN_NAME}"
echo ""
echo "To publish on GitHub: push a tag v${VERSION} and the release workflow will attach this zip."
