#!/usr/bin/env python3
"""Create the private, environment-only configuration used by staging.

The production TOML remains the source for shared provider credentials, but
production-only delivery credentials, the database account and the session
signing key are never copied.  Repeated runs preserve the generated staging
database password and session secret while synchronizing safe shared values.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tomllib
from urllib.parse import quote, unquote, urlsplit, urlunsplit


DEFAULT_SOURCE = Path("deployment/secrets/app_secrets.toml")
DEFAULT_OUTPUT = Path("deployment/runtime/staging.env")
STAGING_USER = "investment_staging"
STAGING_DATABASE = "investment_engine_staging"
STAGING_REDIRECT_URI = "https://formacaodoinvestidor.com.br/testefdi/oauth2callback"
EXCLUDED_TOP_LEVEL = {
    "DATABASE_URL",
    "DATABASE_ADMIN_URL",
    "SESSION_SECRET",
    "SESSION_COOKIE_NAME",
    "BACKTEST_CALLBACK_TOKEN",
    "GITHUB_ACTIONS_TOKEN",
}
SAFE_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _read_toml(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(f"Arquivo de producao nao localizado: {path}")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _decode_env_value(value: str) -> str:
    clean = value.strip()
    if clean.startswith('"'):
        return str(json.loads(clean))
    if len(clean) >= 2 and clean[0] == clean[-1] == "'":
        return clean[1:-1]
    return clean


def _read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if SAFE_KEY.fullmatch(key):
            result[key] = _decode_env_value(value)
    return result


def _database_url(source_url: str, password: str) -> str:
    parsed = urlsplit(str(source_url or "").strip())
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"} or not parsed.hostname:
        raise RuntimeError("DATABASE_URL de producao invalida; a configuracao nao foi alterada.")
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{quote(STAGING_USER, safe='')}:{quote(password, safe='')}@{host}{port}"
    return urlunsplit((parsed.scheme, netloc, f"/{STAGING_DATABASE}", parsed.query, ""))


def _render_env_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if any(character in text for character in ("\r", "\n", "\0")):
        raise RuntimeError("Valor de segredo com quebra de linha nao e suportado.")
    # Single-quoted env-file values are literal in Docker Compose, including
    # dollar signs. Provider secrets virtually never contain a single quote;
    # JSON quoting remains a safe fallback for that exceptional case.
    if "'" not in text:
        return f"'{text}'"
    return json.dumps(text.replace("$", "$$"), ensure_ascii=False)


def _staging_payload(source: dict, existing: dict[str, str]) -> dict[str, object]:
    source_url = str(source.get("DATABASE_URL") or "")
    existing_url = str(existing.get("DATABASE_URL") or "")
    existing_password = unquote(urlsplit(existing_url).password or "") if existing_url else ""
    database_password = existing_password or secrets.token_urlsafe(36)
    session_secret = str(existing.get("SESSION_SECRET") or "")
    if len(session_secret) < 32:
        session_secret = secrets.token_urlsafe(48)

    payload: dict[str, object] = {}
    for raw_key, value in source.items():
        key = str(raw_key).upper()
        if key in EXCLUDED_TOP_LEVEL or not SAFE_KEY.fullmatch(key):
            continue
        if isinstance(value, (str, int, float, bool)):
            payload[key] = value

    auth = source.get("auth") if isinstance(source.get("auth"), dict) else {}
    aliases = {
        "client_id": "GOOGLE_CLIENT_ID",
        "client_secret": "GOOGLE_CLIENT_SECRET",
        "server_metadata_url": "GOOGLE_SERVER_METADATA_URL",
    }
    for source_key, destination in aliases.items():
        value = auth.get(source_key)
        if value:
            payload[destination] = value

    payload.update({
        "DATABASE_URL": _database_url(source_url, database_password),
        "APP_AUTH_REQUIRED": "true",
        "SESSION_SECRET": session_secret,
        "SESSION_COOKIE_NAME": "fdi_staging_session",
        "OAUTH_REDIRECT_URI": STAGING_REDIRECT_URI,
    })
    return payload


def _write_private(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Gerado localmente. Nao publicar nem copiar para a producao.",
        "# O banco, a sessao e o cookie abaixo pertencem somente ao staging.",
    ]
    lines.extend(f"{key}={_render_env_value(payload[key])}" for key in sorted(payload))
    content = "\n".join(lines) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _database_fields(path: Path) -> int:
    payload = _read_env(path)
    parsed = urlsplit(payload.get("DATABASE_URL", ""))
    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    database = parsed.path.lstrip("/")
    if username != STAGING_USER or database != STAGING_DATABASE or not password:
        raise RuntimeError("Configuracao privada do banco de staging e invalida.")
    # Used only through process substitution by refresh-staging-db.sh; the
    # command never echoes these fields to deployment logs.
    sys.stdout.write(f"{username}\t{password}\t{database}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--database-fields", action="store_true")
    args = parser.parse_args()
    if args.database_fields:
        return _database_fields(args.output)

    source = _read_toml(args.source)
    existing = _read_env(args.output)
    payload = _staging_payload(source, existing)
    _write_private(args.output, payload)
    print(f"Configuracao isolada do staging pronta: {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, tomllib.TOMLDecodeError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        raise SystemExit(1)
