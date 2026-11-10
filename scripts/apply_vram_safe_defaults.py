"""Update only SIGNALDESK's Ollama inference settings in the local .env file.

API tokens, public URLs, and all unrelated environment values are preserved.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
EXAMPLE_FILE = PROJECT_ROOT / ".env.example"

SAFE_SETTINGS = {
    "OLLAMA_TIMEOUT_SECONDS": "240",
    "OLLAMA_BATCH_SIZE": "5",
    "OLLAMA_NUM_CTX": "4096",
    "OLLAMA_NUM_BATCH": "128",
    "OLLAMA_NUM_PREDICT": "512",
    "OLLAMA_KEEP_ALIVE": "5m",
}


def update_env_file(path: Path) -> list[str]:
    if not path.exists():
        if EXAMPLE_FILE.exists():
            shutil.copyfile(EXAMPLE_FILE, path)
            original_lines = path.read_text(encoding="utf-8-sig").splitlines()
        else:
            original_lines = []
    else:
        original_lines = path.read_text(encoding="utf-8-sig").splitlines()

    key_pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
    seen: set[str] = set()
    updated_lines: list[str] = []

    for line in original_lines:
        match = key_pattern.match(line)
        key = match.group(1) if match else None
        if key not in SAFE_SETTINGS:
            updated_lines.append(line)
            continue
        if key in seen:
            # Remove duplicate active definitions so .env parsing is unambiguous.
            continue
        updated_lines.append(f"{key}={SAFE_SETTINGS[key]}")
        seen.add(key)

    for key, value in SAFE_SETTINGS.items():
        if key not in seen:
            updated_lines.append(f"{key}={value}")

    path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")
    return list(SAFE_SETTINGS)


def main() -> None:
    changed = update_env_file(ENV_FILE)
    print(f"Updated {len(changed)} Ollama inference settings in: {ENV_FILE}")
    for key in changed:
        print(f"  {key}={SAFE_SETTINGS[key]}")
    print("Other .env values, including API tokens and public URLs, were preserved.")


if __name__ == "__main__":
    main()
