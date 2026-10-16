#!/usr/bin/env bash
# Install Muse Wonder plugin into user's Claude Code environment
set -e

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${HOME}/.claude/plugins/marketplaces/muse-wonder-plugin/plugins/muse-wonder"

echo "=== Installing Muse Wonder Plugin for Claude Code ==="
echo "Source: ${PLUGIN_DIR}"
echo "Target: ${TARGET_DIR}"

mkdir -p "$(dirname "${TARGET_DIR}")"
rm -rf "${TARGET_DIR}"
ln -sf "${PLUGIN_DIR}" "${TARGET_DIR}"

echo "✔ Symlinked plugin directory."

# Verify with claude CLI
if command -v claude >/dev/null 2>&1; then
  echo "Validating plugin with claude CLI..."
  claude plugin validate "${PLUGIN_DIR}"
  echo "✔ Validation passed."
fi

echo "🎉 Installation complete! Start a new Claude Code session with 'claude' to use Muse Wonder."
