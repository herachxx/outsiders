"""Private, reproducible credentials for a single-operator local instance.

Never store the operator's cleartext password in a config or in a git checkout.
This is intentionally *local development* configuration, not cloud IAM.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

SCHEME = 'pbkdf2-sha256'
ITERATIONS = 480_000


def password_record(password: str) -> dict:
    if len(password) < 12:
        raise ValueError('Пароль должен содержать не менее 12 символов.')
    salt = secrets.token_bytes(24)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
    return {'scheme': SCHEME, 'iterations': ITERATIONS, 'salt': salt.hex(), 'digest': digest.hex()}


def verify_password(password: str, record: dict) -> bool:
    try:
        if record['scheme'] != SCHEME:
            return False
        iterations = int(record['iterations'])
        if iterations < 200_000 or iterations > 2_000_000:
            return False
        salt = bytes.fromhex(record['salt'])
        digest = bytes.fromhex(record['digest'])
        if len(salt) < 16 or len(digest) != 32:
            return False
        expected = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return hmac.compare_digest(expected, digest)
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def read_config(path: str | Path) -> dict | None:
    target = Path(path)
    try:
        if target.is_symlink() or not target.is_file() or target.stat().st_size > 4096:
            return None
        if os.name != 'nt' and target.stat().st_mode & 0o077:
            return None
        data = json.loads(target.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or len(data.get('session_secret', '')) < 40 or not isinstance(data.get('password'), dict):
            return None
        return data
    except (OSError, ValueError, TypeError):
        return None


def write_config(path: str | Path, password: str, *, previous: dict | None = None) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != 'nt':
        os.chmod(target.parent, 0o700)
    data = {
        'version': 1,
        'session_secret': previous['session_secret'] if previous else secrets.token_urlsafe(48),
        'password': password_record(password),
    }
    # Create via exclusive creation and atomic replace. No plaintext or temp env secrets.
    tmp = target.with_name('.' + target.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(data, out, ensure_ascii=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, target)
        if os.name != 'nt':
            os.chmod(target, 0o600)
    finally:
        tmp.unlink(missing_ok=True)
