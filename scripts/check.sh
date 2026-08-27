#!/usr/bin/env bash
#
# Run every pre-commit gate in one pass: backend tests and lint, frontend
# typecheck, lint and build.
#
# Deliberately does not stop at the first failure. `a && b && c` hides whether
# the frontend is also broken once the backend fails, which turns one fix-and-
# rerun cycle into three. Every gate runs, then a summary says which failed, and
# the exit status is non-zero if any did.
#
#   ./scripts/check.sh              # everything
#   ./scripts/check.sh --backend    # pytest + ruff only
#   ./scripts/check.sh --frontend   # tsc + lint + build only
#
set -uo pipefail

cd "$(git rev-parse --show-toplevel)"

want_backend=1
want_frontend=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    -b | --backend) want_frontend=0 ;;
    -f | --frontend) want_backend=0 ;;
    -h | --help)
      awk 'NR>2 && /^#/ { sub(/^#[[:space:]]?/, ""); print; next } NR>2 { exit }' "$0"
      exit 0
      ;;
    *)
      echo "check: unknown option $1 (try --help)" >&2
      exit 2
      ;;
  esac
  shift
done

if [[ -t 1 ]]; then
  bold=$'\033[1m' red=$'\033[31m' green=$'\033[32m' reset=$'\033[0m'
else
  bold='' red='' green='' reset=''
fi

results=()
failed=0

run() {
  local name=$1 command=$2 start=$SECONDS
  printf '\n%s▶ %s%s\n' "$bold" "$name" "$reset"
  if bash -c "$command"; then
    results+=("${green}PASS${reset}  $name ($((SECONDS - start))s)")
  else
    results+=("${red}FAIL${reset}  $name ($((SECONDS - start))s)")
    failed=1
  fi
}

# The venv is the project's documented way to run the backend; without it the
# failure would otherwise read as "pytest not found", which sends you looking in
# the wrong place.
if [[ $want_backend == 1 && ! -x backend/venv/bin/python ]]; then
  echo "check: backend/venv is missing — create it before running backend gates" >&2
  exit 2
fi

if [[ $want_backend == 1 ]]; then
  run "backend: pytest" "cd backend && venv/bin/python -m pytest -q"
  run "backend: ruff" "cd backend && venv/bin/python -m ruff check app tests scripts"
fi

if [[ $want_frontend == 1 ]]; then
  # Matches CI: typecheck the app project explicitly, then lint, then build.
  run "frontend: tsc" "cd frontend && npx tsc --noEmit -p tsconfig.app.json"
  run "frontend: lint" "cd frontend && npm run lint"
  run "frontend: build" "cd frontend && npm run build"
fi

printf '\n%s=== Gates ===%s\n' "$bold" "$reset"
printf '%s\n' "${results[@]}"

if [[ $failed == 1 ]]; then
  printf '\n%sSome gates failed.%s\n' "$red" "$reset"
else
  printf '\n%sAll gates passed.%s Browser-level checks: scripts/dom-snapshot.mjs.\n' \
    "$green" "$reset"
fi
exit $failed
