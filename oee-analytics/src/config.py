from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]

def load_config(path: str | Path | None = None) -> dict:
    target = Path(path) if path else ROOT / "config" / "config.yaml"
    with target.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict) or "scales" not in config:
        raise ValueError(f"Invalid configuration: {target}")
    return config
