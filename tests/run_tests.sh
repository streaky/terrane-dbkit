#!/usr/bin/env bash
set -euo pipefail

TESTS_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PACKAGE_DIR="$(cd -- "$TESTS_DIR/.." && pwd -P)"
ROOT="$(cd -- "$PACKAGE_DIR/../.." && pwd -P)"
STATE_PARENT="$TESTS_DIR/.state"
STATE_DIR="$STATE_PARENT/postgres"
COMPOSE="$TESTS_DIR/compose.postgres.yaml"
LOCK="$STATE_PARENT/postgres-test.lock"
COMPOSE_PROJECT="dbkit-pg-$(printf '%s' "$TESTS_DIR" | sha256sum | cut -c1-12)"
POSTGRES_ONLY=0
VERBOSE=0
COMPILER_INPUT="${TERRANE:-$ROOT/target/release/terrane}"

while (($#)); do
  case "$1" in
    --terrane)
      (($# >= 2)) || { echo "--terrane requires a compiler path" >&2; exit 2; }
      COMPILER_INPUT="$2"
      shift 2
      ;;
    --postgres-only)
      POSTGRES_ONLY=1
      shift
      ;;
    -v|--verbose)
      VERBOSE=1
      shift
      ;;
    *)
      echo "unknown option: $1" >&2
      exit 2
      ;;
  esac
done
COMPILER="$(realpath -- "$COMPILER_INPUT")"
PY_ARGS=(--terrane "$COMPILER")
if (( VERBOSE )); then
  PY_ARGS+=(-v)
fi

# Refuse symlinked state paths before creating the lock or touching data.
[[ ! -L "$STATE_PARENT" && (! -e "$STATE_PARENT" || -d "$STATE_PARENT") ]] || {
  echo "refusing unsafe PostgreSQL state parent: $STATE_PARENT" >&2
  exit 2
}
mkdir -p -- "$STATE_PARENT"
[[ ! -L "$STATE_PARENT" && "$(realpath -- "$STATE_PARENT")" == "$TESTS_DIR/.state" ]] || {
  echo "refusing non-canonical PostgreSQL state parent: $STATE_PARENT" >&2
  exit 2
}
[[ ! -L "$LOCK" && (! -e "$LOCK" || -f "$LOCK") ]] || {
  echo "refusing unsafe PostgreSQL test lock: $LOCK" >&2
  exit 2
}
[[ ! -L "$STATE_DIR" && (! -e "$STATE_DIR" || -d "$STATE_DIR") ]] || {
  echo "refusing unsafe PostgreSQL data directory: $STATE_DIR" >&2
  exit 2
}
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "dbkit tests already running (lock: $LOCK)" >&2
  exit 2
fi

CHILD_PID=""
PORT_OUTPUT=""
STARTING_CHILD=0
PENDING_SIGNAL=""
PENDING_CODE=0
run_owned() {
  STARTING_CHILD=1
  python3 "$TESTS_DIR/run_owned.py" "$@" 9>&- &
  CHILD_PID=$!
  STARTING_CHILD=0
  if [[ -n "$PENDING_SIGNAL" ]]; then
    on_signal "$PENDING_SIGNAL" "$PENDING_CODE"
  fi
  local status=0
  wait "$CHILD_PID" || status=$?
  CHILD_PID=""
  return "$status"
}
reset_state() {
  local expected="$TESTS_DIR/.state/postgres"
  [[ "$STATE_DIR" == "$expected" && ! -L "$STATE_PARENT" && ! -L "$STATE_DIR" ]] || {
    echo "refusing unsafe PostgreSQL data reset: $STATE_DIR" >&2
    return 2
  }
  mkdir -p -- "$STATE_DIR"
  [[ ! -L "$STATE_DIR" && "$(realpath -- "$STATE_DIR")" == "$expected" ]] || {
    echo "refusing non-canonical PostgreSQL data reset: $STATE_DIR" >&2
    return 2
  }
  run_owned docker run --rm --user 0:0 --entrypoint sh \
    -v "$STATE_DIR:/data" postgres:18-bookworm \
    -ec 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +'
}
cleanup() {
  local status=$?
  trap - EXIT
  trap '' INT TERM
  if [[ -n "$PORT_OUTPUT" ]]; then
    rm -f -- "$PORT_OUTPUT"
  fi
  if ! run_owned docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE" down --remove-orphans; then
    echo "failed to stop PostgreSQL Compose project $COMPOSE_PROJECT" >&2
    (( status != 0 )) || status=1
  fi
  exit "$status"
}
on_signal() {
  local signal="$1" code="$2"
  if (( STARTING_CHILD )); then
    PENDING_CODE="$code"
    PENDING_SIGNAL="$signal"
    return
  fi
  trap '' INT TERM
  echo "received $signal; stopping dbkit test run" >&2
  if [[ -n "$CHILD_PID" ]]; then
    kill -TERM -- "$CHILD_PID" 2>/dev/null || :
    wait "$CHILD_PID" 2>/dev/null || :
    CHILD_PID=""
  fi
  exit "$code"
}
trap cleanup EXIT
trap 'on_signal INT 130' INT
trap 'on_signal TERM 143' TERM

# A failed stop must prevent any destructive reset.
run_owned docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE" down --remove-orphans
reset_state
run_owned docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE" up -d --wait
PORT_OUTPUT="$(mktemp)"
if ! run_owned docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE" port postgres 5432 >"$PORT_OUTPUT"; then
  rm -f -- "$PORT_OUTPUT"
  exit 1
fi
PORT="$(awk -F: '{print $NF}' "$PORT_OUTPUT")"
rm -f -- "$PORT_OUTPUT"
PORT_OUTPUT=""
if [[ -z "$PORT" || ! "$PORT" =~ ^[0-9]+$ ]]; then
  echo "could not determine PostgreSQL host port" >&2
  exit 1
fi
export DBKIT_POSTGRES_DSN="postgres://dbkit_test:dbkit_test@127.0.0.1:$PORT/dbkit_test"
export TERRANE="$COMPILER"
if (( ! POSTGRES_ONLY )); then
  run_owned "$COMPILER" test "$PACKAGE_DIR"
  run_owned python3 "$TESTS_DIR/test_database.py" "${PY_ARGS[@]}"
fi
run_owned python3 "$TESTS_DIR/test_postgres.py" "${PY_ARGS[@]}"
