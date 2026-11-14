#!/usr/bin/env bash
# Provision a local PostgreSQL role/database for PGClock production.
# Usage: sudo bash scripts/setup_postgres.sh [db_name] [db_user] [db_password]
#
# Design (learned from VPS failures through v11.0.12):
# - Hex-only passwords applied via SQL DO + format(%L) — never psql -v / :'var'.
# - Loopback HBA uses scram-sha-256 first; never leave scram-first HBA with an
#   md5-stored password (v11.0.4 mismatch). Trust on localhost is last resort.
# - ALWAYS pin admin + TCP + restart to ONE cluster (prefer online on 5432).
#   Bare `psql` / `_cluster_from_etc` newest / restart of a different cluster
#   caused: socket password OK + TCP auth fail + trust fallback fail.
# - Clear PG* env (PGHOST/PGPORT/PGCLUSTER) so root's shell cannot redirect
#   socket tests to a different cluster than TCP 127.0.0.1:5432.
# - Restart must succeed; reload alone is not enough on some images.
# - Never emit Unix-socket DATABASE_URL — asyncpg hits Errno 2 on common VPS.
#
# Optional: set PGCLOCK_EMIT_URL_FILE to a path; the DATABASE_URL is written
# there (mode 0600) for the installer to consume without scraping stdout.
set -euo pipefail

DB_NAME="${1:-pgclock}"
DB_USER="${2:-pgclock}"
DB_PASS="${3:-}"
AUTH_MODE="scram" # scram | trust (set after verify). Never "socket" — app needs TCP.

# Libpq env must not steer us onto a different cluster than TCP loopback.
unset PGHOST PGHOSTADDR PGPORT PGCLUSTER PGDATABASE PGUSER PGPASSWORD PGPASSFILE PGSERVICE PGSERVICEFILE || true
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

if [[ -z "$DB_PASS" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    DB_PASS="$(openssl rand -hex 24)"
  else
    DB_PASS="$(head -c 48 /dev/urandom | xxd -p | tr -d '\n' | head -c 48)"
  fi
fi

# Strip accidental whitespace/newlines from password generators / paste.
DB_PASS="$(printf '%s' "$DB_PASS" | tr -d '[:space:]')"

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql not found. Install postgresql + postgresql-client first." >&2
  exit 1
fi

# Identifiers: SQL-safe. Password: hex-only so it is safe to embed in SQL.
if [[ ! "$DB_NAME" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || [[ ! "$DB_USER" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "ERROR: db_name and db_user must be simple SQL identifiers (letters, digits, underscore)." >&2
  exit 1
fi
if [[ ! "$DB_PASS" =~ ^[0-9a-fA-F]{16,128}$ ]]; then
  echo "ERROR: db password must be 16–128 hex chars (got length ${#DB_PASS})." >&2
  exit 1
fi

# Frozen after _resolve_target_cluster. All ops use these — never re-resolve mid-script.
CLUSTER_VER=""
CLUSTER_NAME=""
CLUSTER_PORT="5432"
CLUSTER_SPEC="" # "16/main"

_cluster_from_etc() {
  # Prefer cluster whose postgresql.conf port = 5432; else newest main.
  local d conf port
  for d in $(ls -1d /etc/postgresql/*/main 2>/dev/null | sort -V); do
    conf="${d}/postgresql.conf"
    [[ -f "$conf" ]] || continue
    port="$(awk -F= '/^[[:space:]]*port[[:space:]]*=/{gsub(/[[:space:]#'\''"]/,"",$2); print $2; exit}' "$conf" 2>/dev/null || true)"
    if [[ -z "$port" || "$port" == "5432" ]]; then
      printf '%s %s %s\n' "$(basename "$(dirname "$d")")" "$(basename "$d")" "${port:-5432}"
      return 0
    fi
  done
  for d in $(ls -1d /etc/postgresql/*/* 2>/dev/null | sort -V); do
    conf="${d}/postgresql.conf"
    [[ -f "$conf" ]] || continue
    port="$(awk -F= '/^[[:space:]]*port[[:space:]]*=/{gsub(/[[:space:]#'\''"]/,"",$2); print $2; exit}' "$conf" 2>/dev/null || true)"
    if [[ "$port" == "5432" ]]; then
      printf '%s %s %s\n' "$(basename "$(dirname "$d")")" "$(basename "$d")" "$port"
      return 0
    fi
  done
  d="$(ls -1d /etc/postgresql/*/main 2>/dev/null | sort -V | tail -n1 || true)"
  if [[ -z "$d" ]]; then
    d="$(ls -1d /etc/postgresql/*/* 2>/dev/null | sort -V | tail -n1 || true)"
  fi
  [[ -n "$d" ]] || return 1
  conf="${d}/postgresql.conf"
  port="$(awk -F= '/^[[:space:]]*port[[:space:]]*=/{gsub(/[[:space:]#'\''"]/,"",$2); print $2; exit}' "$conf" 2>/dev/null || true)"
  printf '%s %s %s\n' "$(basename "$(dirname "$d")")" "$(basename "$d")" "${port:-5432}"
}

_resolve_target_cluster() {
  local line ver name port
  if command -v pg_lsclusters >/dev/null 2>&1; then
    line="$(pg_lsclusters --no-header 2>/dev/null | awk '$4=="online" && $3=="5432"{print; exit}')"
    if [[ -z "$line" ]]; then
      line="$(pg_lsclusters --no-header 2>/dev/null | awk '$4=="online"{print; exit}')"
    fi
    if [[ -z "$line" ]]; then
      line="$(pg_lsclusters --no-header 2>/dev/null | awk 'NR==1{print; exit}')"
    fi
    if [[ -n "$line" ]]; then
      ver="$(awk '{print $1}' <<<"$line")"
      name="$(awk '{print $2}' <<<"$line")"
      port="$(awk '{print $3}' <<<"$line")"
    fi
  fi
  if [[ -z "${ver:-}" || -z "${name:-}" ]]; then
    line="$(_cluster_from_etc || true)"
    ver="$(awk '{print $1}' <<<"$line")"
    name="$(awk '{print $2}' <<<"$line")"
    port="$(awk '{print $3}' <<<"$line")"
  fi
  if [[ -z "${ver:-}" || -z "${name:-}" ]]; then
    echo "ERROR: could not resolve a PostgreSQL cluster (pg_lsclusters /etc/postgresql)." >&2
    return 1
  fi
  CLUSTER_VER="$ver"
  CLUSTER_NAME="$name"
  CLUSTER_PORT="${port:-5432}"
  CLUSTER_SPEC="${CLUSTER_VER}/${CLUSTER_NAME}"
  echo "Using PostgreSQL cluster ${CLUSTER_SPEC} (port ${CLUSTER_PORT})." >&2
}

# Admin psql always pinned to CLUSTER_SPEC (never bare default socket).
_as_postgres() {
  if [[ -n "$CLUSTER_SPEC" ]] && psql --help 2>&1 | grep -q -- '--cluster'; then
    sudo -u postgres env -u PGHOST -u PGHOSTADDR -u PGPORT -u PGCLUSTER -u PGPASSWORD \
      psql --cluster "$CLUSTER_SPEC" "$@"
  elif [[ -n "$CLUSTER_SPEC" ]]; then
    sudo -u postgres env -u PGHOST -u PGHOSTADDR -u PGPORT -u PGPASSWORD \
      PGCLUSTER="$CLUSTER_SPEC" psql "$@"
  else
    sudo -u postgres env -u PGHOST -u PGHOSTADDR -u PGPORT -u PGCLUSTER -u PGPASSWORD \
      psql "$@"
  fi
}

_pg_socket_ready() {
  command -v pg_isready >/dev/null 2>&1 || return 1
  if [[ -n "$CLUSTER_SPEC" ]] && pg_isready --help 2>&1 | grep -q -- '--cluster'; then
    sudo -u postgres pg_isready --cluster "$CLUSTER_SPEC" -q 2>/dev/null && return 0
  fi
  pg_isready -h /var/run/postgresql -p "${CLUSTER_PORT}" -q 2>/dev/null && return 0
  return 1
}

_pg_tcp_ready() {
  command -v pg_isready >/dev/null 2>&1 || return 1
  pg_isready -h 127.0.0.1 -p "${CLUSTER_PORT}" -q 2>/dev/null
}

_restart_postgres() {
  local out rc=1
  out="$(mktemp)"
  if [[ -n "${CLUSTER_VER}" && -n "${CLUSTER_NAME}" ]] && command -v pg_ctlcluster >/dev/null 2>&1; then
    if pg_ctlcluster "$CLUSTER_VER" "$CLUSTER_NAME" restart >"$out" 2>&1; then
      rm -f "$out"
      return 0
    fi
    rc=$?
    echo "WARNING: pg_ctlcluster ${CLUSTER_SPEC} restart failed (rc=${rc}):" >&2
    cat "$out" >&2 || true
  fi
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl restart "postgresql@${CLUSTER_VER}-${CLUSTER_NAME}" >"$out" 2>&1 \
      || systemctl restart postgresql >"$out" 2>&1; then
      rm -f "$out"
      return 0
    fi
    echo "WARNING: systemctl restart postgresql failed:" >&2
    cat "$out" >&2 || true
  fi
  # Last resort: pg_ctl directly.
  if [[ -n "$CLUSTER_SPEC" ]] && command -v pg_ctl >/dev/null 2>&1; then
    local data
    data="/var/lib/postgresql/${CLUSTER_VER}/${CLUSTER_NAME}"
    if [[ -d "$data" ]]; then
      if sudo -u postgres pg_ctl -D "$data" restart -m fast >"$out" 2>&1; then
        rm -f "$out"
        return 0
      fi
    fi
  fi
  rm -f "$out"
  echo "ERROR: could not restart PostgreSQL cluster ${CLUSTER_SPEC:-?}." >&2
  return 1
}

_start_postgres() {
  if [[ -n "${CLUSTER_VER}" && -n "${CLUSTER_NAME}" ]] && command -v pg_ctlcluster >/dev/null 2>&1; then
    pg_ctlcluster "$CLUSTER_VER" "$CLUSTER_NAME" start >/dev/null 2>&1 || true
  fi
  if command -v systemctl >/dev/null 2>&1; then
    systemctl start "postgresql@${CLUSTER_VER}-${CLUSTER_NAME}" >/dev/null 2>&1 || true
    systemctl start postgresql >/dev/null 2>&1 || true
  fi
}

_ensure_cluster_up() {
  local i
  _start_postgres
  for i in $(seq 1 45); do
    if _pg_socket_ready || _pg_tcp_ready; then
      return 0
    fi
    _start_postgres
    sleep 1
  done
  echo "ERROR: PostgreSQL cluster ${CLUSTER_SPEC} is not ready (pg_isready failed)." >&2
  return 1
}

_hba_path() {
  local hba
  hba="$(_as_postgres -tAc "SHOW hba_file" 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ -n "$hba" && -f "$hba" ]]; then
    printf '%s' "$hba"
    return 0
  fi
  if [[ -n "$CLUSTER_VER" && -n "$CLUSTER_NAME" \
    && -f "/etc/postgresql/${CLUSTER_VER}/${CLUSTER_NAME}/pg_hba.conf" ]]; then
    printf '%s' "/etc/postgresql/${CLUSTER_VER}/${CLUSTER_NAME}/pg_hba.conf"
    return 0
  fi
  local cand
  for cand in /etc/postgresql/*/main/pg_hba.conf; do
    if [[ -f "$cand" ]]; then
      printf '%s' "$cand"
      return 0
    fi
  done
  return 1
}

# Write loopback rules. $1 = scram | trust
#
# Order matters (first match wins):
#   1) local postgres peer  — so sudo -u postgres psql always works
#   2) our role trust/scram (scoped) on local + 127.0.0.1/::1
#   3) host all scram on loopback
#   4) remainder of prior file (without stale managed/loopback password lines)
_write_hba() {
  local mode="${1:-scram}"
  local hba tmp method
  hba="$(_hba_path)" || {
    echo "WARNING: could not locate pg_hba.conf" >&2
    return 1
  }
  method="scram-sha-256"
  if [[ "$mode" == "trust" ]]; then
    method="trust"
  fi
  tmp="$(mktemp)"
  {
    echo "# PGClockBot — loopback auth (managed; mode=${mode})"
    echo "local   all             postgres                                peer"
    echo "local   ${DB_NAME}      ${DB_USER}                              ${method}"
    echo "host    ${DB_NAME}      ${DB_USER}      127.0.0.1/32            ${method}"
    echo "host    ${DB_NAME}      ${DB_USER}      ::1/128                 ${method}"
    # hostnossl twin: some images negotiate SSL and miss plain `host` unexpectedly.
    echo "hostnossl ${DB_NAME}    ${DB_USER}      127.0.0.1/32            ${method}"
    echo "hostnossl ${DB_NAME}    ${DB_USER}      ::1/128                 ${method}"
    echo "host    all             all             127.0.0.1/32            scram-sha-256"
    echo "host    all             all             ::1/128                 scram-sha-256"
    echo
    grep -v -E \
      '^# PGClockBot — loopback|^[[:space:]]*hostnossl[[:space:]]+'"${DB_NAME}"'[[:space:]]+'"${DB_USER}"'[[:space:]]+(127\.0\.0\.1/32|::1/128)[[:space:]]+(scram-sha-256|md5|trust)[[:space:]]*$|^[[:space:]]*host[[:space:]]+all[[:space:]]+all[[:space:]]+(127\.0\.0\.1/32|::1/128)[[:space:]]+(scram-sha-256|md5|trust)[[:space:]]*$|^[[:space:]]*host[[:space:]]+'"${DB_NAME}"'[[:space:]]+'"${DB_USER}"'[[:space:]]+(127\.0\.0\.1/32|::1/128)[[:space:]]+(scram-sha-256|md5|trust)[[:space:]]*$|^[[:space:]]*local[[:space:]]+all[[:space:]]+postgres[[:space:]]+peer[[:space:]]*$|^[[:space:]]*local[[:space:]]+'"${DB_NAME}"'[[:space:]]+'"${DB_USER}"'[[:space:]]+(scram-sha-256|md5|trust|peer)[[:space:]]*$' \
      "$hba" 2>/dev/null || true
  } > "$tmp"

  if ! cmp -s "$tmp" "$hba"; then
    cp "$hba" "${hba}.bak.pgclock.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
    cat "$tmp" > "$hba"
    chown postgres:postgres "$hba" 2>/dev/null || true
    chmod 640 "$hba" 2>/dev/null || true
    echo "Updated pg_hba.conf (mode=${mode}) at ${hba}." >&2
  fi
  rm -f "$tmp"
}

_wait_tcp() {
  local i
  for i in $(seq 1 45); do
    if _pg_tcp_ready; then
      return 0
    fi
    sleep 1
  done
  return 1
}

_ensure_tcp_listener_and_hba() {
  local listen

  listen="$(_as_postgres -tAc "SHOW listen_addresses" 2>/dev/null | tr -d '[:space:]' || true)"
  case ",${listen}," in
    *,localhost,*|*,127.0.0.1,*|*,\*,*|*,::1,*)
      ;;
    *)
      echo "Configuring listen_addresses=localhost (was: '${listen:-empty}')…" >&2
      _as_postgres -v ON_ERROR_STOP=1 -c "ALTER SYSTEM SET listen_addresses = 'localhost'" >/dev/null
      ;;
  esac

  # Confirm we are on the intended port.
  local live_port
  live_port="$(_as_postgres -tAc "SHOW port" 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ -n "$live_port" && "$live_port" != "$CLUSTER_PORT" ]]; then
    echo "WARNING: cluster ${CLUSTER_SPEC} reports port=${live_port}, expected ${CLUSTER_PORT} — using live port." >&2
    CLUSTER_PORT="$live_port"
  fi

  _as_postgres -c "ALTER SYSTEM SET password_encryption = 'scram-sha-256'" >/dev/null 2>&1 || true
  _write_hba scram

  echo "Restarting PostgreSQL ${CLUSTER_SPEC} to apply listen/hba…" >&2
  _restart_postgres
  if ! _wait_tcp; then
    echo "ERROR: PostgreSQL is not accepting TCP on 127.0.0.1:${CLUSTER_PORT}." >&2
    echo "  listen_addresses=$(_as_postgres -tAc "SHOW listen_addresses" 2>/dev/null || echo '?')" >&2
    echo "  cluster=${CLUSTER_SPEC}" >&2
    return 1
  fi
  # Best-effort: also reload so HBA is definitely live even if restart was a no-op.
  _as_postgres -c "SELECT pg_reload_conf()" >/dev/null 2>&1 || true
}

_set_role_password_and_db() {
  # Force SCRAM hash (never md5) so it matches scram-sha-256 HBA lines.
  _as_postgres -v ON_ERROR_STOP=1 <<SQL
SET password_encryption = 'scram-sha-256';
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', '${DB_USER}', '${DB_PASS}');
  ELSE
    EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', '${DB_USER}', '${DB_PASS}');
  END IF;
END
\$\$;
SELECT format('CREATE DATABASE %I OWNER %I', '${DB_NAME}', '${DB_USER}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
SQL

  _as_postgres -d "$DB_NAME" -v ON_ERROR_STOP=1 <<SQL
GRANT ALL ON SCHEMA public TO ${DB_USER};
ALTER DATABASE ${DB_NAME} OWNER TO ${DB_USER};
SET password_encryption = 'scram-sha-256';
DO \$\$
BEGIN
  EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', '${DB_USER}', '${DB_PASS}');
END
\$\$;
SQL
}

_rolpassword_prefix() {
  _as_postgres -tAc \
    "SELECT COALESCE(left(rolpassword, 10), '<null>') FROM pg_authid WHERE rolname='${DB_USER}'" \
    2>/dev/null | tr -d '[:space:]' || echo '?'
}

# Run psql TCP; print stderr to fd 3 if provided via caller redirect pattern.
# Usage: _tcp_psql_cmd with env; returns psql rc. Captures stderr to $1 if set.
_try_tcp() {
  local errf="${1:-}"
  local rc
  set +e
  if [[ -n "$errf" ]]; then
    PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -p "$CLUSTER_PORT" -U "$DB_USER" -d "$DB_NAME" \
      -w -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>"$errf"
    rc=$?
  else
    PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -p "$CLUSTER_PORT" -U "$DB_USER" -d "$DB_NAME" \
      -w -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>&1
    rc=$?
  fi
  set -e
  return "$rc"
}

_try_socket_password() {
  local errf="${1:-}"
  local rc
  set +e
  if [[ -n "$CLUSTER_SPEC" ]] && psql --help 2>&1 | grep -q -- '--cluster'; then
    if [[ -n "$errf" ]]; then
      PGPASSWORD="$DB_PASS" psql --cluster "$CLUSTER_SPEC" -U "$DB_USER" -d "$DB_NAME" \
        -w -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>"$errf"
      rc=$?
    else
      PGPASSWORD="$DB_PASS" psql --cluster "$CLUSTER_SPEC" -U "$DB_USER" -d "$DB_NAME" \
        -w -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>&1
      rc=$?
    fi
  else
    if [[ -n "$errf" ]]; then
      PGPASSWORD="$DB_PASS" psql -h /var/run/postgresql -p "$CLUSTER_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -w -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>"$errf"
      rc=$?
    else
      PGPASSWORD="$DB_PASS" psql -h /var/run/postgresql -p "$CLUSTER_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -w -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>&1
      rc=$?
    fi
  fi
  set -e
  return "$rc"
}

_try_tcp_trust() {
  local errf="${1:-}"
  local rc
  set +e
  # Explicitly clear password so scram-in-memory cannot be confused with trust.
  if [[ -n "$errf" ]]; then
    env -u PGPASSWORD -u PGPASSFILE psql -h 127.0.0.1 -p "$CLUSTER_PORT" -U "$DB_USER" -d "$DB_NAME" \
      -w -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>"$errf"
    rc=$?
  else
    env -u PGPASSWORD -u PGPASSFILE psql -h 127.0.0.1 -p "$CLUSTER_PORT" -U "$DB_USER" -d "$DB_NAME" \
      -w -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>&1
    rc=$?
  fi
  set -e
  return "$rc"
}

_enable_trust_fallback() {
  echo "WARNING: password auth still failing — enabling localhost trust for ${DB_USER} only…" >&2
  _write_hba trust
  _restart_postgres || {
    echo "WARNING: restart after trust HBA failed — trying pg_reload_conf…" >&2
    _as_postgres -c "SELECT pg_reload_conf()" >/dev/null 2>&1 || true
  }
  _wait_tcp || true
  _as_postgres -c "SELECT pg_reload_conf()" >/dev/null 2>&1 || true
  # Keep a scram password on the role for later hardening; trust ignores it.
  _set_role_password_and_db >/dev/null 2>&1 || true
}

_verify_tcp_password() {
  local err prefix
  err="$(mktemp)"

  if _try_tcp "$err"; then
    rm -f "$err"
    AUTH_MODE="scram"
    return 0
  fi

  prefix="$(_rolpassword_prefix)"
  echo "WARNING: TCP scram auth failed on 127.0.0.1:${CLUSTER_PORT} (rolpassword prefix=${prefix})." >&2
  echo "--- psql error ---" >&2
  cat "$err" >&2 || true
  echo "------------------" >&2

  # Re-stamp SCRAM password + full restart (clears stale md5 hashes from older installs).
  echo "Re-applying SCRAM password and restarting cluster ${CLUSTER_SPEC}…" >&2
  _write_hba scram
  _set_role_password_and_db
  _restart_postgres || true
  _as_postgres -c "SELECT pg_reload_conf()" >/dev/null 2>&1 || true
  sleep 1

  if _try_tcp "$err"; then
    rm -f "$err"
    echo "TCP password auth OK after SCRAM re-apply." >&2
    AUTH_MODE="scram"
    return 0
  fi

  # Socket-only success is NOT enough for the app: asyncpg with
  # ?host=/var/run/postgresql fails on many VPS images (Errno 2). Always prefer
  # a TCP DATABASE_URL. If password TCP is broken, fall through to trust.
  if _try_socket_password "$err"; then
    echo "Unix-socket password auth OK on ${CLUSTER_SPEC} — but the panel needs TCP; enabling localhost trust…" >&2
  else
    echo "WARNING: socket password auth also failed on ${CLUSTER_SPEC}." >&2
    cat "$err" >&2 || true
  fi

  _enable_trust_fallback
  if _try_tcp_trust "$err"; then
    rm -f "$err"
    echo "Localhost trust auth OK for ${DB_USER} on ${CLUSTER_SPEC} (PG not exposed remotely)." >&2
    AUTH_MODE="trust"
    return 0
  fi

  echo "WARNING: trust TCP still failing — retrying restart + trust HBA…" >&2
  cat "$err" >&2 || true
  _write_hba trust
  _restart_postgres || true
  _wait_tcp || true
  _as_postgres -c "SELECT pg_reload_conf()" >/dev/null 2>&1 || true
  sleep 1
  if _try_tcp_trust "$err"; then
    rm -f "$err"
    echo "Localhost trust auth OK for ${DB_USER} after second restart." >&2
    AUTH_MODE="trust"
    return 0
  fi

  # Last attempt: scram over TCP again after trust HBA rewrite + password stamp.
  _write_hba scram
  _set_role_password_and_db
  _restart_postgres || true
  _as_postgres -c "SELECT pg_reload_conf()" >/dev/null 2>&1 || true
  sleep 1
  if _try_tcp "$err"; then
    rm -f "$err"
    echo "TCP password auth OK on final retry." >&2
    AUTH_MODE="scram"
    return 0
  fi

  echo "ERROR: Cannot connect as ${DB_USER} via TCP (127.0.0.1:${CLUSTER_PORT})." >&2
  echo "--- psql error ---" >&2
  cat "$err" >&2 || true
  echo "------------------" >&2
  echo "listen_addresses=$(_as_postgres -tAc "SHOW listen_addresses" 2>/dev/null || echo '?')" >&2
  echo "hba_file=$(_hba_path 2>/dev/null || echo '?')" >&2
  echo "cluster=${CLUSTER_SPEC} port=${CLUSTER_PORT}" >&2
  echo "rolpassword_prefix=$(_rolpassword_prefix)" >&2
  echo "pg_lsclusters:" >&2
  pg_lsclusters 2>&1 >&2 || true
  echo "--- pg_hba head ---" >&2
  head -n 24 "$(_hba_path 2>/dev/null || echo /dev/null)" >&2 || true
  rm -f "$err"
  return 1
}

# ── main ────────────────────────────────────────────────
_resolve_target_cluster
_ensure_cluster_up
_ensure_tcp_listener_and_hba
_set_role_password_and_db
_verify_tcp_password

DB_PASS_ENC="$(
  DB_PASS="$DB_PASS" python3 - <<'PY'
import os, urllib.parse
print(urllib.parse.quote(os.environ["DB_PASS"], safe=""))
PY
)"

# Always TCP. Never emit Unix-socket URLs — asyncpg hits Errno 2 on common VPS layouts.
DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS_ENC}@127.0.0.1:${CLUSTER_PORT}/${DB_NAME}"

if [[ -n "${PGCLOCK_EMIT_URL_FILE:-}" ]]; then
  umask 077
  rm -f "${PGCLOCK_EMIT_URL_FILE}"
  printf '%s\n' "$DATABASE_URL" > "${PGCLOCK_EMIT_URL_FILE}"
  chmod 600 "${PGCLOCK_EMIT_URL_FILE}" 2>/dev/null || true
fi

echo
echo "PostgreSQL ready (auth=${AUTH_MODE}, cluster=${CLUSTER_SPEC}, port=${CLUSTER_PORT})."
echo "Add to .env:"
echo "DATABASE_URL=\"${DATABASE_URL}\""
echo
echo "Then: .venv/bin/python -c 'import asyncio; from app.db.session import init_db; asyncio.run(init_db())'"
