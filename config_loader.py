from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

def load_dotenv_file(dotenv_path: str = ".env") -> None:
    path = Path(dotenv_path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, val = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip("'").strip('"'))

def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    load_dotenv_file()
    path = Path(config_path)
    config = json.loads(path.read_text(encoding="utf-8-sig"))

    env_key_name = config["ai"].get("api_key_env", "GEMINI_API_KEY")
    env_val = os.environ.get(env_key_name, "")
    if env_val and not env_val.startswith("여기에_"):
        config["ai"]["api_key"] = env_val

    Path(config["storage"]["db_path"]).parent.mkdir(parents=True, exist_ok=True)
    Path(config["storage"]["output_dir"]).mkdir(parents=True, exist_ok=True)
    return config

def setup_logging(log_dir: str = "logs", level: int = logging.INFO) -> logging.Logger:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("news_pipeline")
    logger.setLevel(level)
    if logger.handlers:
        return logger

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    file_handler = logging.FileHandler(Path(log_dir) / "pipeline.log", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger