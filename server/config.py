"""Runtime configuration for the Abarpay v1 server.

All values come from environment variables. The repository `.env` file is
only read when `ABARPAY_LOAD_DOTENV=1` is set explicitly; tests and the demo
smoke run therefore never depend on the real credentials file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = SERVER_ROOT / "abarpay.db"

_TRUE_VALUES = {"1", "true", "yes", "si", "sí", "on"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE_VALUES


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_repo_dotenv_if_requested() -> None:
    """Optionally load `<repo>/.env` without overriding exported variables.

    Disabled by default on purpose: the hackathon tests and the demo smoke run
    must not read the real PEY credentials. Set `ABARPAY_LOAD_DOTENV=1` for a
    local process that wants the repository file.
    """

    if not _env_bool("ABARPAY_LOAD_DOTENV", False):
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
    except Exception:  # pragma: no cover - dotenv is optional at runtime
        pass


@dataclass(frozen=True)
class Settings:
    """Immutable settings snapshot for one application instance."""

    db_path: Path = DEFAULT_DB_PATH
    owner_pin: str = "1234"
    modo_demo: bool = True
    pey_api_key: str = field(default="", repr=False)
    pey_webhook_secret: str = field(default="", repr=False)
    pey_base_url: str = "https://api.pey.mx"
    pey_timeout_seconds: float = 15.0
    pey_expiration_seconds: int = 900
    demo_charge_cents: int = 1
    timezone: str = "America/Mexico_City"
    static_dir: Path = field(default_factory=lambda: SERVER_ROOT / "static")

    @property
    def pey_configured(self) -> bool:
        return bool(self.pey_api_key)

    @property
    def webhook_configured(self) -> bool:
        return bool(self.pey_webhook_secret)

    @classmethod
    def from_env(cls) -> "Settings":
        load_repo_dotenv_if_requested()

        raw_db = os.getenv("ABARPAY_DB", "").strip()
        if raw_db:
            db_path = Path(raw_db).expanduser()
            if not db_path.is_absolute():
                db_path = (Path.cwd() / db_path).resolve()
        else:
            db_path = DEFAULT_DB_PATH

        owner_pin = os.getenv("OWNER_PIN", "").strip() or "1234"
        pey_api_key = os.getenv("PEY_API_KEY", "").strip()
        pey_secret = os.getenv("PEY_WEBHOOK_SECRET", "").strip()
        base_url = os.getenv("PEY_BASE_URL", "").strip() or "https://api.pey.mx"
        timeout = _env_float("PEY_TIMEOUT_SECONDS", 15.0)
        if timeout <= 0:
            timeout = 15.0
        expiration = _env_int("PEY_EXPIRATION_SECONDS", 900)
        if expiration <= 0:
            expiration = 900
        demo_charge = _env_int("PEY_DEMO_CHARGE_CENTS", 1)
        if demo_charge < 0:
            demo_charge = 1
        tz = os.getenv("ABARPAY_TZ", "").strip() or "America/Mexico_City"

        return cls(
            db_path=db_path,
            owner_pin=owner_pin,
            modo_demo=_env_bool("MODO_DEMO", True),
            pey_api_key=pey_api_key,
            pey_webhook_secret=pey_secret,
            pey_base_url=base_url,
            pey_timeout_seconds=timeout,
            pey_expiration_seconds=expiration,
            demo_charge_cents=demo_charge,
            timezone=tz,
        )
