"""Load the small, repository-local provider configuration."""

from dataclasses import dataclass, field
from pathlib import Path
import re
import tomllib

from .git import git


class ConfigError(Exception):
    pass


@dataclass
class Config:
    provider: str = "heuristic"
    model: str = ""
    timeout: float = 10
    ignore: list[str] = field(default_factory=list)


def load_config() -> Config:
    path = Path(git("rev-parse", "--show-toplevel").strip()) / ".gitmsg.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        options = data.get("gitmsg", {})
        if not isinstance(options, dict) or options.keys() - {"provider", "model", "timeout", "ignore"}:
            raise ValueError
        config = Config(**options)
        if config.provider not in ("heuristic", "anthropic"):
            raise ValueError
        if not isinstance(config.model, str) or (config.model and not re.fullmatch(r"[a-zA-Z0-9._:-]{1,100}", config.model)):
            raise ValueError
        if config.provider == "anthropic" and not config.model:
            raise ValueError
        if type(config.timeout) not in (int, float) or not 0 < config.timeout <= 120:
            raise ValueError
        if not isinstance(config.ignore, list) or any(not isinstance(item, str) or not item for item in config.ignore):
            raise ValueError
        return config
    except (OSError, ValueError, TypeError):
        # Do not echo TOML parser errors: the file might contain a misplaced key.
        raise ConfigError("Invalid .gitmsg.toml; check provider, model, timeout and ignore settings.") from None
