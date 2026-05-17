"""Create a compressed MySQL backup from a SQLAlchemy DATABASE_URL."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_defaults_file(url: str) -> Path:
    parsed = make_url(url)
    if parsed.get_backend_name() != "mysql":
        raise ValueError("backup_mysql.py only supports mysql/mysql+pymysql URLs")
    if not parsed.database:
        raise ValueError("DATABASE_URL must include a database name")

    fd, raw_path = tempfile.mkstemp(prefix="mysqldump-", suffix=".cnf")
    path = Path(raw_path)
    password = parsed.password or ""
    host = parsed.host or "127.0.0.1"
    port = parsed.port or 3306
    user = parsed.username or "root"
    content = (
        "[client]\n"
        f"user={user}\n"
        f"password={password}\n"
        f"host={host}\n"
        f"port={port}\n"
        "default-character-set=utf8mb4\n"
    )
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
    os.chmod(path, 0o600)
    return path


def create_backup(database_url: str, output_dir: Path) -> Path:
    if not shutil.which("mysqldump"):
        raise RuntimeError("mysqldump was not found in PATH")

    parsed = make_url(database_url)
    database = parsed.database
    if not database:
        raise ValueError("DATABASE_URL must include a database name")

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = output_dir / f"{_safe_name(database)}-mysql-{timestamp}.sql.gz"
    defaults_path = _write_defaults_file(database_url)

    command = [
        "mysqldump",
        f"--defaults-extra-file={defaults_path}",
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        "--set-gtid-purged=OFF",
        database,
    ]

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdout is not None
        with gzip.open(backup_path, "wb") as output:
            for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
                output.write(chunk)
        _, stderr = process.communicate()
        if process.returncode != 0:
            backup_path.unlink(missing_ok=True)
            raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())
    finally:
        defaults_path.unlink(missing_ok=True)

    digest = _sha256(backup_path)
    manifest = {
        "backup_file": backup_path.name,
        "database": database,
        "host": parsed.host,
        "port": parsed.port or 3306,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "bytes": backup_path.stat().st_size,
        "sha256": digest,
    }
    manifest_path = backup_path.with_suffix(backup_path.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return backup_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a gzip-compressed MySQL backup.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="Source MySQL SQLAlchemy URL")
    parser.add_argument("--output-dir", default="backups/db", help="Backup output directory")
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL or --database-url is required")

    backup_path = create_backup(args.database_url, Path(args.output_dir))
    digest = _sha256(backup_path)
    print(f"backup={backup_path}")
    print(f"bytes={backup_path.stat().st_size}")
    print(f"sha256={digest}")


if __name__ == "__main__":
    main()
