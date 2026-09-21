"""Off-site database backups — the one thing here that `git` can't recover.

Code lives in GitHub; guardians, students, attendance history, and billing
records only ever exist in Postgres. A bad migration, an accidental DROP,
or a Railway-side incident would lose all of it unless a copy exists
somewhere other than Railway itself — that's what this does: pg_dump the
platform database and every tenant database, gzip each, and upload to an
S3-compatible bucket (Cloudflare R2 by default; see Settings.backup_s3_*
in app/core/config.py). Old backups past BACKUP_RETENTION_DAYS are pruned
so storage cost doesn't grow forever.

Meant to be invoked daily by app/core/scheduler.py, or run by hand:
    python -m app.jobs.backup_databases

To restore a backup:
    gunzip -c dump.sql.gz | psql "postgresql://user:pass@host:port/dbname"
(For the platform DB, that's PLATFORM_DATABASE_URL's own database — for a
tenant, first `CREATE DATABASE <tenant_db_name>`, matching
app/db/tenant.py's provision_tenant_database, then restore into it.)
"""

from __future__ import annotations

import datetime as dt
import gzip
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.platform import SessionLocal as PlatformSessionLocal
from app.db.tenant import tenant_url
from app.models.platform import School

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.backup_s3_endpoint_url,
        region_name=settings.backup_s3_region,
        aws_access_key_id=settings.backup_s3_access_key_id,
        aws_secret_access_key=settings.backup_s3_secret_access_key,
        config=BotoConfig(signature_version="s3v4"),
    )


def _pg_dump_to_gzip(db_url: str, gz_path: Path) -> None:
    """Streams pg_dump's stdout straight into a gzip file rather than
    buffering the whole dump in memory first — fine for a tiny school's
    database today, but there's no reason to hold an ever-growing dump
    in RAM as schools and history accumulate.
    """
    url = make_url(db_url)
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = url.password
    cmd = [
        "pg_dump",
        "--no-owner",
        "--no-privileges",
        "-h", url.host or "localhost",
        "-p", str(url.port or 5432),
        "-U", url.username or "postgres",
        "-d", url.database,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        with gzip.open(gz_path, "wb") as f_out:
            assert proc.stdout is not None
            for chunk in iter(lambda: proc.stdout.read(_CHUNK_SIZE), b""):
                f_out.write(chunk)
    finally:
        if proc.stdout:
            proc.stdout.close()
        stderr = proc.stderr.read() if proc.stderr else b""
        if proc.stderr:
            proc.stderr.close()
        returncode = proc.wait()

    if returncode != 0:
        raise RuntimeError(f"pg_dump exited {returncode}: {stderr.decode(errors='replace')[:2000]}")


def _dump_and_upload(client, db_url: str, key_prefix: str, today: str, tmp_dir: Path) -> None:
    gz_path = tmp_dir / f"{key_prefix.replace('/', '_')}.sql.gz"
    try:
        _pg_dump_to_gzip(db_url, gz_path)
        key = f"{key_prefix}/{today}.sql.gz"
        client.upload_file(str(gz_path), settings.backup_s3_bucket, key)
        logger.info("backup_databases: uploaded %s (%d bytes)", key, gz_path.stat().st_size)
    finally:
        gz_path.unlink(missing_ok=True)


def _prune_old_backups(client, key_prefix: str) -> int:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=settings.backup_retention_days)
    pruned = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.backup_s3_bucket, Prefix=f"{key_prefix}/"):
        for obj in page.get("Contents", []):
            if obj["LastModified"] < cutoff:
                client.delete_object(Bucket=settings.backup_s3_bucket, Key=obj["Key"])
                pruned += 1
    return pruned


def backup_all_databases() -> dict:
    """Never lets one school's dump failure stop the rest — every
    success/failure is collected so nothing fails silently, and the
    caller (scheduler or CLI) gets a full picture in one summary.
    """
    if not settings.backup_s3_bucket:
        logger.info("backup_databases: BACKUP_S3_BUCKET not set, skipping (no-op)")
        return {"skipped": True}

    client = _s3_client()
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    succeeded: list[str] = []
    failed: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        try:
            _dump_and_upload(client, settings.platform_database_url, "platform", today, tmp_dir)
            succeeded.append("platform")
        except Exception:
            logger.exception("backup_databases: platform DB dump failed")
            failed.append("platform")

        platform_db = PlatformSessionLocal()
        try:
            schools = platform_db.query(School).all()
        finally:
            platform_db.close()

        for school in schools:
            try:
                _dump_and_upload(
                    client, tenant_url(school.tenant_db_name), f"tenants/{school.tenant_db_name}", today, tmp_dir
                )
                succeeded.append(school.tenant_db_name)
            except Exception:
                logger.exception("backup_databases: tenant DB dump failed for %s", school.tenant_db_name)
                failed.append(school.tenant_db_name)

    pruned_total = 0
    prefixes = ["platform"] + [f"tenants/{s.tenant_db_name}" for s in schools]
    for prefix in prefixes:
        try:
            pruned_total += _prune_old_backups(client, prefix)
        except Exception:
            logger.exception("backup_databases: pruning failed for %s", prefix)

    logger.info(
        "backup_databases: %d succeeded, %d failed, %d old backup(s) pruned",
        len(succeeded), len(failed), pruned_total,
    )
    return {"succeeded": succeeded, "failed": failed, "pruned": pruned_total}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(backup_all_databases())
