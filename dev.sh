#!/usr/bin/env bash
# dev.sh — starts the full RAG Chat stack (backend + frontend)
# Safe to run repeatedly; skips steps that are already complete.
set -euo pipefail

# ── colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}[info]${RESET}  $*"; }
success() { echo -e "${GREEN}[ok]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[warn]${RESET}  $*"; }
error()   { echo -e "${RED}[error]${RESET} $*" >&2; }
step()    { echo -e "\n${BOLD}━━  $*${RESET}"; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT/frontend"
VENV_DIR="$ROOT/venv"
LOG_DIR="$ROOT/.logs"
mkdir -p "$LOG_DIR"

BACKEND_PORT=8000
FRONTEND_PORT=5173

# ── cleanup on exit ────────────────────────────────────────────────────────────
PIDS=()
cleanup() {
  echo ""
  info "Shutting down…"
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  success "All processes stopped."
}
trap cleanup EXIT INT TERM

# ── helpers ────────────────────────────────────────────────────────────────────
command_exists() { command -v "$1" &>/dev/null; }

require() {
  local cmd="$1" install_hint="$2"
  if ! command_exists "$cmd"; then
    error "Required command '$cmd' not found."
    error "Install it with: $install_hint"
    exit 1
  fi
}

port_in_use() { lsof -i :"$1" -sTCP:LISTEN -t &>/dev/null; }

wait_for_port() {
  local name="$1" port="$2" timeout=30 elapsed=0
  while ! lsof -i :"$port" -sTCP:LISTEN -t &>/dev/null; do
    sleep 1
    elapsed=$((elapsed + 1))
    if [[ $elapsed -ge $timeout ]]; then
      error "$name did not start on port $port within ${timeout}s. Check $LOG_DIR/$name.log"
      return 1
    fi
  done
}

# ── system requirements ────────────────────────────────────────────────────────
step "Checking system requirements"

require python3 "https://www.python.org/downloads/"
require node    "https://nodejs.org  (or: brew install node)"
require npm     "https://nodejs.org  (or: brew install node)"

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
NODE_VERSION=$(node --version | sed 's/v//')
NODE_MAJOR=${NODE_VERSION%%.*}

if [[ $(echo "$PYTHON_VERSION < 3.10" | bc -l 2>/dev/null || python3 -c "print(1 if tuple(map(int,'$PYTHON_VERSION'.split('.'))) < (3,10) else 0)") == "1" ]]; then
  error "Python 3.10+ required (found $PYTHON_VERSION). Upgrade at https://www.python.org/downloads/"
  exit 1
fi

if [[ "$NODE_MAJOR" -lt 18 ]]; then
  error "Node 18+ required (found $NODE_VERSION). Upgrade at https://nodejs.org"
  exit 1
fi

success "Python $PYTHON_VERSION  ·  Node $NODE_VERSION"

# ── .env check ────────────────────────────────────────────────────────────────
step "Checking environment configuration"

if [[ ! -f "$ROOT/.env" ]]; then
  warn ".env not found — copying .env.example to .env"
  if [[ -f "$ROOT/.env.example" ]]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    warn "Edit $ROOT/.env and fill in your API keys, then re-run this script."
    exit 1
  else
    error "No .env or .env.example found. Create $ROOT/.env with your keys."
    error "Required keys: OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX, MONGODB_URI, REDIS_URL, JWT_SECRET"
    exit 1
  fi
fi

# Warn about any placeholder values still present
PLACEHOLDERS=("your_super_secret" "your-openai" "your-pinecone" "change_me" "changeme")
for placeholder in "${PLACEHOLDERS[@]}"; do
  if grep -qi "$placeholder" "$ROOT/.env" 2>/dev/null; then
    warn ".env still contains placeholder value matching '$placeholder' — update it before first use."
  fi
done

success ".env present"

# ── Python virtualenv ─────────────────────────────────────────────────────────
step "Setting up Python virtual environment"

if [[ ! -d "$VENV_DIR" ]]; then
  info "Creating virtualenv at $VENV_DIR …"
  python3 -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
success "Virtualenv active"

# ── Python dependencies ───────────────────────────────────────────────────────
step "Installing Python dependencies"

pip install --upgrade pip -q

# Ensure pip-tools is available for compiling requirements.in → requirements.txt
if ! command_exists pip-compile; then
  info "Installing pip-tools …"
  pip install pip-tools -q
fi

IN_HASH_FILE="$VENV_DIR/.requirements_in_hash"
TXT_HASH_FILE="$VENV_DIR/.requirements_txt_hash"
CURRENT_IN_HASH=$(md5 -q "$ROOT/requirements.in" 2>/dev/null || md5sum "$ROOT/requirements.in" 2>/dev/null | awk '{print $1}')

if [[ ! -f "$IN_HASH_FILE" ]] || [[ "$(cat "$IN_HASH_FILE")" != "$CURRENT_IN_HASH" ]]; then
  info "requirements.in changed — compiling to requirements.txt …"
  pip-compile "$ROOT/requirements.in" --output-file "$ROOT/requirements.txt" --quiet --strip-extras
  echo "$CURRENT_IN_HASH" > "$IN_HASH_FILE"
  success "requirements.txt regenerated"
fi

CURRENT_TXT_HASH=$(md5 -q "$ROOT/requirements.txt" 2>/dev/null || md5sum "$ROOT/requirements.txt" 2>/dev/null | awk '{print $1}')

if [[ ! -f "$TXT_HASH_FILE" ]] || [[ "$(cat "$TXT_HASH_FILE")" != "$CURRENT_TXT_HASH" ]]; then
  info "requirements.txt changed — syncing packages …"
  pip-sync "$ROOT/requirements.txt"
  # Keep pip-tools itself after pip-sync (which removes unlisted packages)
  pip install pip-tools -q
  echo "$CURRENT_TXT_HASH" > "$TXT_HASH_FILE"
  success "Python packages installed"
else
  success "Python packages up-to-date"
fi

# ── Node dependencies ─────────────────────────────────────────────────────────
step "Installing Node dependencies"

LOCK_HASH_FILE="$FRONTEND_DIR/node_modules/.package_lock_hash"
CURRENT_LOCK_HASH=$(md5 -q "$FRONTEND_DIR/package-lock.json" 2>/dev/null || md5sum "$FRONTEND_DIR/package-lock.json" 2>/dev/null | awk '{print $1}' || echo "none")

if [[ ! -d "$FRONTEND_DIR/node_modules" ]] || \
   [[ ! -f "$LOCK_HASH_FILE" ]] || \
   [[ "$(cat "$LOCK_HASH_FILE")" != "$CURRENT_LOCK_HASH" ]]; then
  info "Running npm install in $FRONTEND_DIR …"
  npm install --prefix "$FRONTEND_DIR"
  echo "$CURRENT_LOCK_HASH" > "$LOCK_HASH_FILE"
  success "Node packages installed"
else
  success "Node packages up-to-date (package-lock.json unchanged)"
fi

# ── port availability ─────────────────────────────────────────────────────────
step "Checking ports"

free_port() {
  local port="$1" name="$2"
  if port_in_use "$port"; then
    local pids
    pids=$(lsof -i :"$port" -sTCP:LISTEN -t 2>/dev/null || true)
    warn "Port $port ($name) is in use by PID(s): $pids"
    if [[ -t 0 ]]; then
      read -r -p "    Kill and reclaim port $port? [y/N] " answer
      if [[ "$answer" =~ ^[Yy]$ ]]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
        success "Port $port freed"
      else
        error "Cannot start $name — port $port is occupied. Free it and retry."
        exit 1
      fi
    else
      # Non-interactive (CI / piped): kill automatically
      warn "Non-interactive mode — killing PID(s) $pids on port $port"
      echo "$pids" | xargs kill -9 2>/dev/null || true
      sleep 1
    fi
  fi
}

free_port "$BACKEND_PORT"  "backend"
free_port "$FRONTEND_PORT" "frontend"

# ── start backend ─────────────────────────────────────────────────────────────
step "Starting backend (FastAPI + uvicorn)"

(
  cd "$ROOT"
  source "$VENV_DIR/bin/activate"
  exec uvicorn main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" \
    >> "$LOG_DIR/backend.log" 2>&1
) &
PIDS+=($!)
info "Backend PID $!  →  log: $LOG_DIR/backend.log"

info "Waiting for backend on port $BACKEND_PORT …"
wait_for_port "backend" "$BACKEND_PORT"
success "Backend ready at http://localhost:$BACKEND_PORT"
success "API docs at   http://localhost:$BACKEND_PORT/docs"

# ── start frontend ─────────────────────────────────────────────────────────────
step "Starting frontend (Vite dev server)"

(
  cd "$FRONTEND_DIR"
  exec npm run dev -- --port "$FRONTEND_PORT" --host \
    >> "$LOG_DIR/frontend.log" 2>&1
) &
PIDS+=($!)
info "Frontend PID $!  →  log: $LOG_DIR/frontend.log"

info "Waiting for frontend on port $FRONTEND_PORT …"
wait_for_port "frontend" "$FRONTEND_PORT"
success "Frontend ready at http://localhost:$FRONTEND_PORT"

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  ${GREEN}${BOLD}RAG Chat is running${RESET}"
echo -e "  Frontend  →  ${BLUE}http://localhost:$FRONTEND_PORT${RESET}"
echo -e "  Backend   →  ${BLUE}http://localhost:$BACKEND_PORT${RESET}"
echo -e "  API docs  →  ${BLUE}http://localhost:$BACKEND_PORT/docs${RESET}"
echo -e "  Logs      →  ${BLUE}$LOG_DIR/${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  Press ${BOLD}Ctrl+C${RESET} to stop everything."
echo ""

# ── tail logs until killed ────────────────────────────────────────────────────
# Show interleaved live output from both processes
tail -f "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log" &
PIDS+=($!)

wait
