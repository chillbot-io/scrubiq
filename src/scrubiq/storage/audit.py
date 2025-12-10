"""Audit logging for compliance and traceability."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
import getpass
import json
import os


class AuditAction(Enum):
    """Types of auditable actions."""

    # Database operations
    DB_CREATE = "db_create"
    DB_OPEN = "db_open"
    DB_CLOSE = "db_close"

    # Scan operations
    SCAN_START = "scan_start"
    SCAN_COMPLETE = "scan_complete"

    # Data operations
    FINDING_STORE = "finding_store"
    FINDING_READ = "finding_read"
    FINDING_DELETE = "finding_delete"
    FINDING_EXPORT = "finding_export"

    # Review operations
    REVIEW_START = "review_start"
    REVIEW_VERDICT = "review_verdict"

    # Key operations
    KEY_CREATE = "key_create"
    KEY_ROTATE = "key_rotate"
    KEY_DELETE = "key_delete"

    # Export operations
    REPORT_GENERATE = "report_generate"
    DATA_EXPORT = "data_export"


@dataclass
class AuditEntry:
    """Single audit log entry."""

    timestamp: datetime
    action: AuditAction
    user: str
    details: dict
    record_count: int = 0
    scan_id: Optional[str] = None
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "action": self.action.value,
            "user": self.user,
            "details": self.details,
            "record_count": self.record_count,
            "scan_id": self.scan_id,
            "success": self.success,
            "error": self.error,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class AuditLog:
    """
    Append-only audit log for compliance.

    Logs all sensitive data access operations.
    Stored as JSON lines file alongside the database.

    Usage:
        audit = AuditLog("/path/to/scrubiq-audit.jsonl")
        audit.log(AuditAction.SCAN_START, {"path": "/documents"})
        audit.log(AuditAction.FINDING_STORE, {"file": "doc.xlsx"}, record_count=5)
    """

    def __init__(self, log_path: str):
        """
        Initialize audit log.

        Args:
            log_path: Path to the audit log file (JSON lines format).
        """
        self.log_path = log_path
        self._user = self._get_current_user()

        # Ensure directory exists
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)

    def _get_current_user(self) -> str:
        """Get current OS username."""
        try:
            return getpass.getuser()
        except Exception:
            return "unknown"

    def log(
        self,
        action: AuditAction,
        details: Optional[dict] = None,
        record_count: int = 0,
        scan_id: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> AuditEntry:
        """
        Log an action.

        Args:
            action: The type of action being logged.
            details: Additional context (paths, counts, etc).
            record_count: Number of records affected.
            scan_id: Associated scan ID if applicable.
            success: Whether the operation succeeded.
            error: Error message if failed.

        Returns:
            The created AuditEntry.
        """
        entry = AuditEntry(
            timestamp=datetime.now(),
            action=action,
            user=self._user,
            details=details or {},
            record_count=record_count,
            scan_id=scan_id,
            success=success,
            error=error,
        )

        # Append to log file
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(entry.to_json() + "\n")

        return entry

    def get_entries(
        self,
        since: Optional[datetime] = None,
        action: Optional[AuditAction] = None,
        scan_id: Optional[str] = None,
        limit: int = 1000,
    ) -> list[AuditEntry]:
        """
        Read audit log entries with optional filters.

        Args:
            since: Only entries after this timestamp.
            action: Filter by action type.
            scan_id: Filter by scan ID.
            limit: Maximum entries to return.

        Returns:
            List of matching AuditEntry objects.
        """
        entries = []

        if not os.path.exists(self.log_path):
            return entries

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                    entry_time = datetime.fromisoformat(data["timestamp"])

                    # Apply filters
                    if since and entry_time < since:
                        continue
                    if action and data["action"] != action.value:
                        continue
                    if scan_id and data.get("scan_id") != scan_id:
                        continue

                    entries.append(
                        AuditEntry(
                            timestamp=entry_time,
                            action=AuditAction(data["action"]),
                            user=data["user"],
                            details=data["details"],
                            record_count=data.get("record_count", 0),
                            scan_id=data.get("scan_id"),
                            success=data.get("success", True),
                            error=data.get("error"),
                        )
                    )

                    if len(entries) >= limit:
                        break

                except (json.JSONDecodeError, KeyError, ValueError):
                    continue  # Skip malformed entries

        return entries

    def get_stats(self) -> dict:
        """Get aggregate statistics from the audit log."""
        stats = {
            "total_entries": 0,
            "by_action": {},
            "by_user": {},
            "errors": 0,
            "first_entry": None,
            "last_entry": None,
        }

        if not os.path.exists(self.log_path):
            return stats

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                    stats["total_entries"] += 1

                    action = data["action"]
                    stats["by_action"][action] = stats["by_action"].get(action, 0) + 1

                    user = data["user"]
                    stats["by_user"][user] = stats["by_user"].get(user, 0) + 1

                    if not data.get("success", True):
                        stats["errors"] += 1

                    timestamp = data["timestamp"]
                    if stats["first_entry"] is None:
                        stats["first_entry"] = timestamp
                    stats["last_entry"] = timestamp

                except (json.JSONDecodeError, KeyError):
                    continue

        return stats
