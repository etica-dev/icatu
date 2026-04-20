"""Gerenciamento persistente de tokens de acesso por nome de usuário."""
import json
import os
import secrets
import threading
from pathlib import Path

_LOCK = threading.Lock()
_TOKENS_FILE = Path(os.getenv("TOKENS_FILE", "data/tokens.json"))


def _load() -> dict[str, str]:
    """Carrega o mapa {username: token} do arquivo JSON."""
    if not _TOKENS_FILE.is_file():
        return {}
    try:
        return json.loads(_TOKENS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict[str, str]) -> None:
    _TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TOKENS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def create_token(username: str) -> str:
    """Cria (ou renova) o token de um usuário. Retorna o token gerado."""
    username = username.strip().lower()
    if not username:
        raise ValueError("Nome de usuário não pode ser vazio.")
    with _LOCK:
        data = _load()
        token = secrets.token_urlsafe(32)
        data[username] = token
        _save(data)
    return token


def revoke_token(username: str) -> bool:
    """Remove o token de um usuário. Retorna True se existia, False caso contrário."""
    username = username.strip().lower()
    with _LOCK:
        data = _load()
        if username not in data:
            return False
        del data[username]
        _save(data)
    return True


def validate_token(token: str) -> str | None:
    """Verifica se o token é válido. Retorna o username associado ou None."""
    if not token:
        return None
    data = _load()
    for username, stored_token in data.items():
        if secrets.compare_digest(stored_token, token):
            return username
    return None


def list_tokens() -> dict[str, str]:
    """Retorna o mapa completo {username: token}."""
    return _load()
