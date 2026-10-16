"""Run Alembic migrations programmatically on startup."""

from __future__ import annotations

import subprocess
import sys

from app.utils.logging import get_logger

logger = get_logger(__name__)


def run_migrations() -> bool:
    """Apply pending Alembic revisions. Returns True on success."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            logger.error(
                "migration_failed",
                returncode=result.returncode,
                stderr=result.stderr[-2000:] if result.stderr else "",
                stdout=result.stdout[-2000:] if result.stdout else "",
            )
            return False
        logger.info("migrations_applied")
        return True
    except Exception as e:
        logger.exception("migration_error", error=str(e))
        return False
