#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]] || ! command -v apt-cache >/dev/null; then
  echo "Package validation requires an apt-based Linux system with package metadata." >&2
  exit 2
fi
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mapfile -t packages < <(python3 - "${ROOT_DIR}" <<'PY'
from pathlib import Path
import sys, tomllib
root = Path(sys.argv[1])
names = set()
for path in (root / "config/profiles").glob("*.toml"):
    with path.open("rb") as stream:
        names.update(tomllib.load(stream)["packages"])
print("\n".join(sorted(names)))
PY
)
missing=0
for package in "${packages[@]}"; do
  if ! apt-cache show "${package}" >/dev/null 2>&1; then
    echo "Missing from configured apt repositories: ${package}" >&2
    missing=1
  fi
done
exit "${missing}"
