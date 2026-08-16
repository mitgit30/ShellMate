import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.db.database import Database


@dataclass(frozen=True)
class User:
    id: str
    email: str


class UserRepository:
    """SQLite repository for local users and opaque login sessions."""

    def __init__(self, database_path: Path | None = None, database: Database | None = None) -> None:
        self._database = database or Database(None, database_path or Path("backend/data/servers.db"))
        if database is None:
            self._database.initialize_schema()

    def ensure_user(self, email: str, password: str) -> User:
        normalized_email = email.strip().lower()
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT id, email FROM users WHERE email = ?", (normalized_email,)
            ).fetchone()
            if row:
                return User(id=row["id"], email=row["email"])

            user_id = secrets.token_urlsafe(16)
            connection.execute(
                "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
                (user_id, normalized_email, hash_password(password)),
            )
            connection.commit()
        return User(id=user_id, email=normalized_email)

    def create_user(self, email: str, password: str) -> User:
        normalized_email = email.strip().lower()
        with self._database.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM users WHERE email = ?", (normalized_email,)
            ).fetchone()
            if existing:
                raise ValueError("An account with this email already exists.")
            user_id = secrets.token_urlsafe(16)
            connection.execute(
                "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
                (user_id, normalized_email, hash_password(password)),
            )
            connection.commit()
        return User(id=user_id, email=normalized_email)

    def authenticate(self, email: str, password: str) -> User | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT id, email, password_hash FROM users WHERE email = ?",
                (email.strip().lower(),),
            ).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            return None
        return User(id=row["id"], email=row["email"])

    def create_session(self, user_id: str, lifetime: timedelta) -> str:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + lifetime
        with self._database.connect() as connection:
            connection.execute(
                "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, user_id, expires_at.isoformat()),
            )
            connection.commit()
        return raw_token

    def get_user_by_token(self, raw_token: str) -> User | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.email, auth_sessions.expires_at
                FROM auth_sessions JOIN users ON users.id = auth_sessions.user_id
                WHERE auth_sessions.token_hash = ?
                """,
                (hash_token(raw_token),),
            ).fetchone()
        if row is None or datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            return None
        return User(id=row["id"], email=row["email"])

    def revoke_session(self, raw_token: str) -> None:
        with self._database.connect() as connection:
            connection.execute(
                "DELETE FROM auth_sessions WHERE token_hash = ?", (hash_token(raw_token),)
            )
            connection.commit()

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
