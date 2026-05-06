# utils/cache.py

import json
import hashlib
from pathlib import Path

def prompt_hash(payload: dict) -> str:
    canon = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()

class Cache:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str):
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def set(self, key: str, value: dict):
        path = self.cache_dir / f"{key}.json"
        with open(path, "w") as f:
            json.dump(value, f, indent=2)