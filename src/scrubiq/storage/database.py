"""Encrypted SQLite database for storing scan findings."""

import sqlite3
import os
from pathlib import Path
from typing import Optional, Iterator

from .crypto import Encryptor
from .audit import AuditLog, AuditAction
from ..scanner.results import (
    ScanResult,
)


def get_default_db_path() -> str:
    """Get default database path in user config directory."""
    if os.name == "nt":  # Windows
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    else:  # Unix
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))

    db_dir = os.path.join(base, "scrubiq")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "findings.db")


class FindingsDatabase:
    """
    Encrypted SQLite database for scan findings.

    Sensitive fields (value, context) are AES-encrypted before storage.
    All operations are audit-logged for compliance.

    Usage:
        db = FindingsDatabase()  # Uses default path
        db.store_scan(scan_result)

        for finding in db.get_findings(scan_id="abc123"):
            print(finding)

        db.close()
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        encryptor: Optional[Encryptor] = None,
    ):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database. Uses default if None.
            encryptor: Custom encryptor. Creates default if None.
        """
        self.db_path = db_path or get_default_db_path()
        self.encryptor = encryptor or Encryptor()

        # Audit log lives next to database
        audit_path = str(Path(self.db_path).with_suffix(".audit.jsonl"))
        self.audit = AuditLog(audit_path)

        # Track if this is a new database
        is_new = not os.path.exists(self.db_path)

        # Connect and initialize
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

        # Log database open
        self.audit.log(
            AuditAction.DB_CREATE if is_new else AuditAction.DB_OPEN, {"path": self.db_path}
        )

    def _init_schema(self):
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()

        # Scans table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                scan_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                source_path TEXT NOT NULL,
                source_type TEXT NOT NULL,
                total_files INTEGER DEFAULT 0,
                files_with_matches INTEGER DEFAULT 0,
                files_errored INTEGER DEFAULT 0,
                total_matches INTEGER DEFAULT 0,
                metadata TEXT
            )
        """
        )

        # Files table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id TEXT NOT NULL,
                path TEXT NOT NULL,
                source TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                modified TEXT NOT NULL,
                has_sensitive_data INTEGER NOT NULL,
                label_recommendation TEXT,
                current_label TEXT,
                error TEXT,
                scan_time_ms INTEGER DEFAULT 0,
                FOREIGN KEY (scan_id) REFERENCES scans(scan_id)
            )
        """
        )

        # Matches table - sensitive fields are encrypted
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                scan_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                value_encrypted TEXT NOT NULL,
                value_redacted TEXT NOT NULL,
                start_pos INTEGER NOT NULL,
                end_pos INTEGER NOT NULL,
                confidence REAL NOT NULL,
                confidence_level TEXT NOT NULL,
                detector TEXT NOT NULL,
                context_encrypted TEXT,
                is_test_data INTEGER NOT NULL,
                model_version TEXT,
                FOREIGN KEY (file_id) REFERENCES files(id),
                FOREIGN KEY (scan_id) REFERENCES scans(scan_id)
            )
        """
        )

        # Indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_scan ON files(scan_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_scan ON matches(scan_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_file ON matches(file_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_type ON matches(entity_type)")

        self.conn.commit()

    def store_scan(self, scan_result: ScanResult) -> str:
        """
        Store a complete scan result.

        Args:
            scan_result: The ScanResult to store.

        Returns:
            The scan_id of the stored scan.
        """
        cursor = self.conn.cursor()

        # Insert scan record
        cursor.execute(
            """
            INSERT INTO scans (
                scan_id, started_at, completed_at, source_path, source_type,
                total_files, files_with_matches, files_errored, total_matches
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                scan_result.scan_id,
                scan_result.started_at.isoformat(),
                scan_result.completed_at.isoformat() if scan_result.completed_at else None,
                scan_result.source_path,
                scan_result.source_type,
                scan_result.total_files,
                scan_result.files_with_matches,
                scan_result.files_errored,
                scan_result.total_matches,
            ),
        )

        # Insert file records and their matches
        match_count = 0
        for file_result in scan_result.files:
            cursor.execute(
                """
                INSERT INTO files (
                    scan_id, path, source, size_bytes, modified,
                    has_sensitive_data, label_recommendation, current_label,
                    error, scan_time_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    scan_result.scan_id,
                    str(file_result.path),
                    file_result.source,
                    file_result.size_bytes,
                    file_result.modified.isoformat(),
                    1 if file_result.has_sensitive_data else 0,
                    (
                        file_result.label_recommendation.value
                        if file_result.label_recommendation
                        else None
                    ),
                    file_result.current_label,
                    file_result.error,
                    file_result.scan_time_ms,
                ),
            )

            file_id = cursor.lastrowid

            # Insert matches with encrypted sensitive fields
            for match in file_result.matches:
                cursor.execute(
                    """
                    INSERT INTO matches (
                        file_id, scan_id, entity_type,
                        value_encrypted, value_redacted,
                        start_pos, end_pos, confidence, confidence_level,
                        detector, context_encrypted, is_test_data, model_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        file_id,
                        scan_result.scan_id,
                        match.entity_type.value,
                        self.encryptor.encrypt(match.value),
                        match.redacted_value,
                        match.start,
                        match.end,
                        match.confidence,
                        match.confidence_level.value,
                        match.detector,
                        self.encryptor.encrypt(match.context) if match.context else None,
                        1 if match.is_test_data else 0,
                        match.model_version,
                    ),
                )
                match_count += 1

        self.conn.commit()

        # Audit log
        self.audit.log(
            AuditAction.FINDING_STORE,
            {
                "source_path": scan_result.source_path,
                "total_files": scan_result.total_files,
            },
            record_count=match_count,
            scan_id=scan_result.scan_id,
        )

        return scan_result.scan_id

    def get_scan(self, scan_id: str) -> Optional[dict]:
        """Get scan metadata by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM scans WHERE scan_id = ?", (scan_id,))
        row = cursor.fetchone()

        if not row:
            return None

        self.audit.log(
            AuditAction.FINDING_READ,
            {"scan_id": scan_id, "type": "scan_metadata"},
            scan_id=scan_id,
        )

        return dict(row)

    def list_scans(self, limit: int = 100) -> list[dict]:
        """List recent scans."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM scans 
            ORDER BY started_at DESC 
            LIMIT ?
        """,
            (limit,),
        )

        return [dict(row) for row in cursor.fetchall()]

    def get_files(
        self,
        scan_id: str,
        only_with_matches: bool = False,
    ) -> list[dict]:
        """
        Get all files from a scan.

        Args:
            scan_id: The scan to retrieve files from.
            only_with_matches: If True, only return files with sensitive data.

        Returns:
            List of file dictionaries.
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM files WHERE scan_id = ?"
        params = [scan_id]

        if only_with_matches:
            query += " AND has_sensitive_data = 1"

        query += " ORDER BY path"

        cursor.execute(query, params)

        files = []
        for row in cursor.fetchall():
            file_dict = dict(row)
            # Map 'path' to 'file_path' for consistency
            file_dict["file_path"] = file_dict.pop("path")
            files.append(file_dict)

        return files

    def get_findings(
        self,
        scan_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        min_confidence: float = 0.0,
        include_test_data: bool = False,
        decrypt: bool = True,
    ) -> Iterator[dict]:
        """
        Get findings with optional filters.

        Args:
            scan_id: Filter by scan ID.
            entity_type: Filter by entity type (e.g., "ssn", "email").
            min_confidence: Minimum confidence threshold.
            include_test_data: Include matches flagged as test data.
            decrypt: Decrypt sensitive fields (value, context).

        Yields:
            Finding dictionaries with file path and match details.
        """
        cursor = self.conn.cursor()

        query = """
            SELECT 
                m.*, f.path as file_path, f.source as file_source
            FROM matches m
            JOIN files f ON m.file_id = f.id
            WHERE m.confidence >= ?
        """
        params = [min_confidence]

        if scan_id:
            query += " AND m.scan_id = ?"
            params.append(scan_id)

        if entity_type:
            query += " AND m.entity_type = ?"
            params.append(entity_type)

        if not include_test_data:
            query += " AND m.is_test_data = 0"

        cursor.execute(query, params)

        count = 0
        for row in cursor:
            finding = dict(row)

            # Decrypt sensitive fields if requested
            if decrypt:
                finding["value"] = self.encryptor.decrypt(finding["value_encrypted"])
                if finding["context_encrypted"]:
                    finding["context"] = self.encryptor.decrypt(finding["context_encrypted"])
                else:
                    finding["context"] = ""

            # Remove encrypted fields from output
            del finding["value_encrypted"]
            del finding["context_encrypted"]

            count += 1
            yield finding

        # Audit log (after iteration to get accurate count)
        self.audit.log(
            AuditAction.FINDING_READ,
            {
                "filters": {
                    "scan_id": scan_id,
                    "entity_type": entity_type,
                    "min_confidence": min_confidence,
                },
                "decrypted": decrypt,
            },
            record_count=count,
            scan_id=scan_id,
        )

    def get_findings_by_file(self, file_path: str, decrypt: bool = True) -> list[dict]:
        """Get all findings for a specific file path."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT m.*, f.path as file_path, f.source as file_source
            FROM matches m
            JOIN files f ON m.file_id = f.id
            WHERE f.path = ?
        """,
            (file_path,),
        )

        results = []
        for row in cursor:
            finding = dict(row)

            if decrypt:
                finding["value"] = self.encryptor.decrypt(finding["value_encrypted"])
                if finding["context_encrypted"]:
                    finding["context"] = self.encryptor.decrypt(finding["context_encrypted"])
                else:
                    finding["context"] = ""

            del finding["value_encrypted"]
            del finding["context_encrypted"]
            results.append(finding)

        return results

    def delete_scan(self, scan_id: str) -> int:
        """
        Delete a scan and all its findings.

        Returns number of matches deleted.
        """
        cursor = self.conn.cursor()

        # Count matches first
        cursor.execute("SELECT COUNT(*) FROM matches WHERE scan_id = ?", (scan_id,))
        match_count = cursor.fetchone()[0]

        # Delete in order (matches -> files -> scan)
        cursor.execute("DELETE FROM matches WHERE scan_id = ?", (scan_id,))
        cursor.execute("DELETE FROM files WHERE scan_id = ?", (scan_id,))
        cursor.execute("DELETE FROM scans WHERE scan_id = ?", (scan_id,))

        self.conn.commit()

        self.audit.log(
            AuditAction.FINDING_DELETE,
            {"scan_id": scan_id},
            record_count=match_count,
            scan_id=scan_id,
        )

        return match_count

    def purge_all(self) -> int:
        """
        Delete ALL data from the database.

        Returns total number of matches deleted.
        """
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM matches")
        total_matches = cursor.fetchone()[0]

        cursor.execute("DELETE FROM matches")
        cursor.execute("DELETE FROM files")
        cursor.execute("DELETE FROM scans")

        self.conn.commit()

        self.audit.log(
            AuditAction.FINDING_DELETE,
            {"action": "purge_all"},
            record_count=total_matches,
        )

        return total_matches

    def get_stats(self) -> dict:
        """Get database statistics."""
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM scans")
        scan_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM files")
        file_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM matches")
        match_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM matches WHERE is_test_data = 0")
        real_match_count = cursor.fetchone()[0]

        # Matches by type
        cursor.execute(
            """
            SELECT entity_type, COUNT(*) as count 
            FROM matches 
            WHERE is_test_data = 0
            GROUP BY entity_type
            ORDER BY count DESC
        """
        )
        by_type = {row["entity_type"]: row["count"] for row in cursor}

        return {
            "scans": scan_count,
            "files": file_count,
            "matches": match_count,
            "real_matches": real_match_count,
            "test_data_matches": match_count - real_match_count,
            "by_entity_type": by_type,
        }

    def close(self):
        """Close database connection."""
        self.audit.log(AuditAction.DB_CLOSE, {"path": self.db_path})
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
