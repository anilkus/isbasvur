#!/usr/bin/env bash
# Encrypt your private PDFs before committing them. The public repo only ever sees *.gpg files.
#
# Usage:  DOCS_PASSPHRASE='same-as-github-secret' ./scripts/encrypt_docs.sh cv ~/Desktop/CV.pdf
#         keys: cv transcript degrees publications research_statement teaching_statement references language
set -euo pipefail
key="$1"; src="$2"
: "${DOCS_PASSPHRASE:?Set DOCS_PASSPHRASE first (same value as the GitHub secret)}"
cd "$(dirname "$0")/.."
mkdir -p private
gpg --batch --yes --pinentry-mode loopback --passphrase "$DOCS_PASSPHRASE" \
    --symmetric --cipher-algo AES256 -o "private/${key}.pdf.gpg" "$src"
echo "Saved private/${key}.pdf.gpg (encrypted). Commit and push it."
