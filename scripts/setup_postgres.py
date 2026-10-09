"""Create/reuse private credentials for the project-local Docker Compose database."""

import json
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(text)
    path.chmod(0o600)


def main():
    config = ROOT / "config/postgresql.json"
    password_file = ROOT / "var/postgres-password"
    settings = dict(host="127.0.0.1", port=15432, dbname="qihuang", user="qihuang_import",
                    connect_timeout=10, sslmode="disable")
    if config.exists():
        existing = json.loads(config.read_text())
        if any(existing.get(k) != settings[k] for k in ("host", "port", "dbname", "user")):
            raise ValueError("Existing config does not match compose.yaml; keep it and configure Compose manually")
        password = existing.get("password")
        if not isinstance(password, str) or not password.strip():
            raise ValueError("Existing config requires a nonempty password")
        if password_file.exists() and password_file.read_text().strip() != password:
            raise ValueError("Private config and Compose secret differ; refusing to change existing credentials")
        settings = existing
    else:
        password = password_file.read_text().strip() if password_file.exists() else secrets.token_urlsafe(32)
        if not password:
            raise ValueError("Existing Compose password file is empty")
        settings["password"] = password
        private_write(config, json.dumps(settings, indent=2) + "\n")
    private_write(password_file, password + "\n")
    config.chmod(0o600)
    print("Ready: config/postgresql.json and var/postgres-password (private, reused on rerun)")


if __name__ == "__main__":
    main()
