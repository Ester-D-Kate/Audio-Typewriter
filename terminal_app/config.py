import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG: Dict[str, Any] = {
    "hotkeys": {
        "start": "ctrl+shift+l",
        "stop": "ctrl+alt+s",
        "pause": "ctrl+shift+space",
        "cancel": "ctrl+shift+esc",
        "prompt": "ctrl+shift+alt+p",
    },
    "ui": {
        "width": 360,
        "height": 120,
    },
    "transcription": {
        "workers": 2,
        "max_retries": 3,
    },
}


def load_config() -> Dict[str, Any]:
    cfg_path = Path(__file__).resolve().parent.parent / "config.json"
    if not cfg_path.exists():
        return DEFAULT_CONFIG
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            user_cfg = json.load(fh)
    except Exception:
        return DEFAULT_CONFIG
    cfg = DEFAULT_CONFIG.copy()
    cfg.update(user_cfg)
    # Merge nested hotkeys/ui dicts if provided
    for section in ("hotkeys", "ui"):
        if section in user_cfg and isinstance(user_cfg[section], dict):
            merged = DEFAULT_CONFIG.get(section, {}).copy()
            merged.update(user_cfg[section])
            cfg[section] = merged
    return cfg
