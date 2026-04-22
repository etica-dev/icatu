"""Gerenciamento persistente de tokens de acesso por nome de usuário."""
import json
import os
import secrets
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.logger import get_logger

log = get_logger("token_store")

_LOCK = threading.Lock()
_TOKENS_FILE = Path(os.getenv("TOKENS_FILE", "data/tokens.json"))


# ---------------------------------------------------------------------------
# Formato interno: {username: {token, created_at, expires_at|null}}
# ---------------------------------------------------------------------------

def _load() -> dict[str, dict]:
    if not _TOKENS_FILE.is_file():
        return {}
    try:
        raw = json.loads(_TOKENS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    # Migração automática do formato antigo {username: "token_string"}
    migrated = {}
    changed = False
    for username, value in raw.items():
        if isinstance(value, str):
            migrated[username] = {
                "token": value,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": None,
            }
            changed = True
        else:
            migrated[username] = value
    if changed:
        _save(migrated)
        log.info("Tokens migrados para o novo formato com metadados.")
    return migrated


def _save(data: dict) -> None:
    _TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TOKENS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _is_expired(entry: dict) -> bool:
    expires_at = entry.get("expires_at")
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at)
        return datetime.now(timezone.utc) > exp
    except Exception:
        return False


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def create_token(username: str, expires_days: int | None = None) -> dict:
    """Cria (ou renova) o token de um usuário.

    Args:
        username: Nome de identificação do usuário.
        expires_days: Dias até expirar. None = sem expiração.

    Returns:
        Dict com token, created_at, expires_at.
    """
    username = username.strip().lower()
    if not username:
        raise ValueError("Nome de usuário não pode ser vazio.")
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=expires_days)).isoformat() if expires_days else None
    entry = {
        "token": secrets.token_urlsafe(32),
        "created_at": now.isoformat(),
        "expires_at": expires_at,
    }
    with _LOCK:
        data = _load()
        data[username] = entry
        _save(data)
    log.info(
        "Token criado para '%s' (expira: %s)",
        username,
        expires_at or "nunca",
    )
    return entry


def revoke_token(username: str) -> bool:
    """Remove o token de um usuário. Retorna True se existia."""
    username = username.strip().lower()
    with _LOCK:
        data = _load()
        if username not in data:
            return False
        del data[username]
        _save(data)
    log.info("Token de '%s' revogado.", username)
    return True


def validate_token(token: str) -> str | None:
    """Valida o token. Retorna o username associado ou None se inválido/expirado."""
    if not token:
        return None
    data = _load()
    for username, entry in data.items():
        if secrets.compare_digest(entry["token"], token):
            if _is_expired(entry):
                log.warning("Token de '%s' usado após expiração.", username)
                return None
            return username
    return None


def list_tokens() -> list[dict]:
    """Retorna lista de {username, created_at, expires_at, expired} sem expor o token."""
    data = _load()
    result = []
    for username, entry in data.items():
        result.append({
            "username": username,
            "token": entry["token"],
            "created_at": entry.get("created_at"),
            "expires_at": entry.get("expires_at"),
            "expired": _is_expired(entry),
        })
    return result
