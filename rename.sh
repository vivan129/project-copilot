#!/bin/bash
# ─────────────────────────────────────────────
# Project Copilot — Rename Script
# Usage: bash rename.sh <new-name>
# Example: bash rename.sh buildmate
# ─────────────────────────────────────────────

set -e

if [ -z "$1" ]; then
  echo "❌ Please provide a new name."
  echo "   Usage: bash rename.sh <new-name>"
  exit 1
fi

OLD_NAME=$(cat .name)
NEW_NAME=$1

echo "🔄 Renaming project from '$OLD_NAME' to '$NEW_NAME'..."

# Update all occurrences in key config files
find . -type f \( \
  -name "*.json" -o \
  -name "*.ts" -o \
  -name "*.tsx" -o \
  -name "*.env" -o \
  -name "*.md" -o \
  -name "*.toml" -o \
  -name "*.yaml" -o \
  -name "*.yml" \
\) \
  ! -path "*/node_modules/*" \
  ! -path "*/.git/*" \
  ! -path "*/__pycache__/*" \
  -exec sed -i '' "s/$OLD_NAME/$NEW_NAME/g" {} +

# Update .name file
echo "$NEW_NAME" > .name

# Rename the parent folder itself
cd ..
mv "$OLD_NAME" "$NEW_NAME"

echo "✅ Done! Your project is now called '$NEW_NAME'"
echo "   cd ../$NEW_NAME to enter it"
