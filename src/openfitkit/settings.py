"""Small, explicit configuration surface; live AI is always opt-in."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import re


def _data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return base / "openfitkit"


@dataclass(frozen=True)
class Settings:
    provider: str = "demo"
    model: str = ""
    api_key: str = field(default="", repr=False)
    data_dir: Path = field(default_factory=_data_dir)
    port: int = 8766

    def __post_init__(self) -> None:
        if self.provider not in {"demo", "openai", "openrouter"}:
            raise ValueError("OPENFITKIT_PROVIDER must be demo, openai, or openrouter.")
        if not isinstance(self.port, int) or isinstance(self.port, bool) or not 1 <= self.port <= 65535:
            raise ValueError("OPENFITKIT_PORT must be an integer from 1 to 65535.")
        if self.provider != "demo" and self.model and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,179}", self.model):
            raise ValueError("OPENFITKIT_MODEL must be a model ID of at most 180 characters.")

    @classmethod
    def from_env(cls) -> "Settings":
        provider = os.environ.get("OPENFITKIT_PROVIDER", "demo").strip().lower()
        try:
            port = int(os.environ.get("OPENFITKIT_PORT", "8766"))
        except ValueError:
            raise ValueError("OPENFITKIT_PORT must be an integer from 1 to 65535.") from None
        return cls(
            provider=provider,
            model=os.environ.get("OPENFITKIT_MODEL", "").strip() if provider != "demo" else "",
            api_key=os.environ.get("OPENFITKIT_API_KEY", "").strip(),
            data_dir=Path(os.environ.get("OPENFITKIT_DATA_DIR") or _data_dir()).expanduser(),
            port=port,
        )

    def public(self) -> dict[str, str | bool]:
        return {
            "provider": self.provider,
            "model": "offline-example" if self.provider == "demo" else self.model,
            "demo": self.provider == "demo",
            "configured": self.provider == "demo" or bool(self.model and self.api_key.strip()),
        }
