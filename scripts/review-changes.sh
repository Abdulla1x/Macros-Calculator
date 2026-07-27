#!/usr/bin/env bash
#
# Show every uncommitted change in one pass, then the gate commands to run.
#
# This exists because `git diff` is not "the changes": it omits staged edits
# (that's `git diff HEAD`) and it says nothing at all about new files, which is
# how a whole new module gets committed without anyone having read it. Untracked
# files are diffed here against /dev/null so they show up as ordinary additions.
#
#   ./scripts/review-changes.sh                # everything, in a pager
#   ./scripts/review-changes.sh --stat         # counts only
#   ./scripts/review-changes.sh backend        # limit to a path
#   ./scripts/review-changes.sh frontend/src/hooks
#
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

mode=full
paths=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -s | --stat) mode=stat ;;
    -h | --help)
      # The header comment is the help text. Printed by walking comment lines
      # rather than a line range, so editing the header can't desync it.
      awk 'NR>2 && /^#/ { sub(/^#[[:space:]]?/, ""); print; next } NR>2 { exit }' "$0"
      exit 0
      ;;
    -*)
      echo "review-changes: unknown option $1 (try --help)" >&2
      exit 2
      ;;
    *) paths+=("$1") ;;
  esac
  shift
done

pathspec=()
[[ ${#paths[@]} -gt 0 ]] && pathspec=(-- "${paths[@]}")

# Colour and paging only when a human is watching, so piping to a file or to
# grep gives plain text.
if [[ -t 1 ]]; then colour=always; else colour=never; fi

# New files, honouring .gitignore and the same pathspec as the tracked diff.
new_files() {
  git ls-files --others --exclude-standard "${pathspec[@]}"
}

# HEAD, or the empty tree in a repo with no commits yet, so the first commit
# still gets a readable diff.
base() {
  if git rev-parse --verify --quiet HEAD >/dev/null; then
    echo HEAD
  else
    git hash-object -t tree /dev/null
  fi
}

report() {
  local base
  base=$(base)

  echo "=== Uncommitted changes${paths[*]:+ under ${paths[*]}} ==="
  echo
  # --untracked-files=all: the default collapses a new directory to `dir/`,
  # hiding how many files are actually new inside it.
  git -c color.status=$colour status --short --untracked-files=all "${pathspec[@]}"
  echo

  echo "=== Summary ==="
  echo
  # --stat against HEAD covers staged and unstaged together.
  git diff --stat --color=$colour "$base" "${pathspec[@]}"
  if [[ -n "$(new_files)" ]]; then
    echo
    echo "New files (not in the stat above):"
    while IFS= read -r file; do
      printf '  %-60s %s lines\n' "$file" "$(wc -l <"$file")"
    done < <(new_files)
  fi
  echo

  [[ $mode == stat ]] && return 0

  echo "=== Changes to existing files ==="
  echo
  git diff --color=$colour "$base" "${pathspec[@]}"

  if [[ -n "$(new_files)" ]]; then
    echo
    echo "=== New files ==="
    while IFS= read -r file; do
      echo
      # --no-index diffs a path outside the index, so the file is shown without
      # `git add -N` touching the index to get it there.
      git diff --no-index --color=$colour /dev/null "$file" || true
    done < <(new_files)
  fi
}

gates() {
  cat <<'EOF'

=== Before committing ===

  ./scripts/check.sh          # every gate: pytest, ruff, tsc, lint, build

Browser-level checks: see .claude/skills/verify.
EOF
}

if [[ -t 1 ]]; then
  { report; gates; } | ${PAGER:-less -FRX}
else
  report
  gates
fi
