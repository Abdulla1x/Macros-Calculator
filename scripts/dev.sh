#!/usr/bin/env bash
#
# Boot the whole app locally so you can click through it in a browser.
#
# Starts the FastAPI backend on :8000 and the Vite dev server on :5173, waits
# until both actually answer, prints the URL, and streams both logs. Ctrl-C
# stops both -- no orphaned uvicorn holding port 8000 afterwards.
#
#   ./scripts/dev.sh                     # http://localhost:5173
#   ./scripts/dev.sh --fresh             # throwaway empty database
#   ./scripts/dev.sh --banner "AI is down"   # exercise the status banner
#
# The backend has no dotenv loader, so env vars must be passed explicitly --
# which is why running uvicorn by hand tends to produce an app that boots and
# then behaves oddly. This passes the ones that matter and sources backend/.env
# first if you keep one (for GEMINI_API_KEY).
#
set -uo pipefail

cd "$(git rev-parse --show-toplevel)"

fresh=0
banner=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fresh) fresh=1 ;;
    --banner)
      banner=${2:-}
      shift
      ;;
    -h | --help)
      awk 'NR>2 && /^#/ { sub(/^#[[:space:]]?/, ""); print; next } NR>2 { exit }' "$0"
      exit 0
      ;;
    *)
      echo "dev: unknown option $1 (try --help)" >&2
      exit 2
      ;;
  esac
  shift
done

if [[ -t 1 ]]; then
  bold=$'\033[1m' dim=$'\033[2m' red=$'\033[31m' green=$'\033[32m' reset=$'\033[0m'
else
  bold='' dim='' red='' green='' reset=''
fi

die() {
  printf '%sdev: %s%s\n' "$red" "$1" "$reset" >&2
  exit 1
}

port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

for port in 8000 5173; do
  port_busy $port && die "port $port is already in use — stop whatever is on it first"
done

[[ -x backend/venv/bin/python ]] || die "backend/venv is missing"
[[ -d frontend/node_modules ]] || die "frontend/node_modules is missing — run npm ci in frontend/"

# Optional, for the AI features. Sourced before the defaults below so a value
# set here can be overridden where it would be actively wrong (see DATABASE_URL).
if [[ -f backend/.env ]]; then
  echo "${dim}Loading backend/.env${reset}"
  set -a
  # shellcheck disable=SC1091
  . backend/.env
  set +a
fi

logdir="${TMPDIR:-/tmp}/macros-dev"
mkdir -p "$logdir"

# NEVER fall through to the repo-root macros.db: that is the pre-multi-user
# single-user database, kept for reference, with no user_id columns. An empty
# DATABASE_URL in .env would silently point the app at it.
if [[ $fresh == 1 ]]; then
  db="$logdir/fresh-$(date +%s).db"
  echo "${dim}Fresh database: $db${reset}"
else
  db="$PWD/backend/dev-test.db"
fi
export DATABASE_URL="sqlite:///$db"

# A fixed dev secret, so a restart doesn't invalidate the token in your browser
# and log you out mid-test. Never used anywhere but here.
export JWT_SECRET="${JWT_SECRET:-dev-0123456789abcdef0123456789abcdef}"
[[ -n $banner ]] && export STATUS_BANNER="$banner"

backend_pid=""
frontend_pid=""

cleanup() {
  echo
  echo "${dim}Stopping…${reset}"
  # Kill the process group so uvicorn's --reload child and vite's esbuild
  # workers go with it, rather than surviving to hold the ports.
  [[ -n $backend_pid ]] && kill -- "-$backend_pid" 2>/dev/null
  [[ -n $frontend_pid ]] && kill -- "-$frontend_pid" 2>/dev/null
  wait 2>/dev/null
}
trap cleanup EXIT INT TERM

printf '\n%s▶ backend%s  → %s/backend.log\n' "$bold" "$reset" "$logdir"
setsid backend/venv/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 --reload --app-dir backend \
  >"$logdir/backend.log" 2>&1 </dev/null &
backend_pid=$!

printf '%s▶ frontend%s → %s/frontend.log\n' "$bold" "$reset" "$logdir"
setsid npm --prefix frontend run dev \
  >"$logdir/frontend.log" 2>&1 </dev/null &
frontend_pid=$!

wait_for() {
  local what=$1 port=$2 tries=60
  until port_busy "$port"; do
    ((tries--)) || {
      echo
      echo "${red}$what never came up. Last 20 log lines:${reset}" >&2
      tail -20 "$logdir/${what}.log" >&2
      exit 1
    }
    sleep 0.5
  done
}

wait_for backend 8000
wait_for frontend 5173

# Port open is not the same as serving: confirm the API actually responds.
health=$(curl -fsS --max-time 5 http://127.0.0.1:8000/api/health 2>/dev/null || echo FAILED)
[[ $health == *'"ok"'* ]] || {
  echo "${red}Backend is listening but /api/health returned: $health${reset}" >&2
  tail -20 "$logdir/backend.log" >&2
  exit 1
}

cat <<EOF

${green}${bold}App is running: http://localhost:5173${reset}

  API          http://localhost:8000/api/health
  API docs     http://localhost:8000/docs
  Database     $db
  Logs         $logdir/{backend,frontend}.log
EOF
[[ -n $banner ]] && echo "  Status banner set — it shows on /login and above every page."
[[ -n ${GEMINI_API_KEY:-} ]] || echo "  ${dim}No GEMINI_API_KEY: AI analysis and voice notes will 503.${reset}"
cat <<EOF

  Sign up for an account -- data is per-user, so a fresh database starts empty.
  To see the "what's new" modal again: devtools → Application → Local Storage,
  delete macros_seen_announcements (and macros_dismissed_banner for the banner).

${dim}Ctrl-C to stop both. Backend reloads on save; so does the frontend.${reset}

EOF

# Stream both logs until interrupted. One tail over both files, in the
# foreground: a backgrounded `tail | sed` pipeline per log looks nicer but
# survives the cleanup trap (kill hits sed, not tail) and then hangs the script
# on `wait` forever. Ctrl-C reaches this directly, and the EXIT trap stops the
# servers on the way out. tail prints a ==> header when it switches files.
tail -n 0 -F "$logdir/backend.log" "$logdir/frontend.log"
