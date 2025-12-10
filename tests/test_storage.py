"""Tests for encrypted storage and audit logging."""

import pytest
import json
from datetime import datetime, timedelta

from scrubiq.storage.crypto import Encryptor, generate_key
from scrubiq.storage.audit import AuditLog, AuditAction, AuditEntry
from scrubiq.storage.database import FindingsDatabase
from scrubiq import Scanner


class TestEncryptor:
    """Test encryption/decryption."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypted data should decrypt to original."""
        key = generate_key()
        encryptor = Encryptor(key)

        original = "SSN: 078-05-1120"
        ciphertext = encryptor.encrypt(original)
        decrypted = encryptor.decrypt(ciphertext)

        assert decrypted == original

    def test_ciphertext_differs_from_plaintext(self):
        """Ciphertext should not contain plaintext."""
        key = generate_key()
        encryptor = Encryptor(key)

        original = "sensitive data 12345"
        ciphertext = encryptor.encrypt(original)

        assert original not in ciphertext
        assert "12345" not in ciphertext

    def test_empty_string_roundtrip(self):
        """Empty strings should work."""
        key = generate_key()
        encryptor = Encryptor(key)

        assert encryptor.encrypt("") == ""
        assert encryptor.decrypt("") == ""

    def test_different_keys_produce_different_ciphertext(self):
        """Same plaintext with different keys should differ."""
        key1 = generate_key()
        key2 = generate_key()
        enc1 = Encryptor(key1)
        enc2 = Encryptor(key2)

        plaintext = "same text"
        cipher1 = enc1.encrypt(plaintext)
        cipher2 = enc2.encrypt(plaintext)

        assert cipher1 != cipher2

    def test_wrong_key_fails(self):
        """Decryption with wrong key should fail."""
        from cryptography.fernet import InvalidToken

        key1 = generate_key()
        key2 = generate_key()
        enc1 = Encryptor(key1)
        enc2 = Encryptor(key2)

        ciphertext = enc1.encrypt("secret")

        with pytest.raises(InvalidToken):
            enc2.decrypt(ciphertext)

    def test_unicode_roundtrip(self):
        """Unicode characters should work."""
        key = generate_key()
        encryptor = Encryptor(key)

        original = "日本語 emoji 🔒 symbols ñ ü"
        ciphertext = encryptor.encrypt(original)
        decrypted = encryptor.decrypt(ciphertext)

        assert decrypted == original


class TestAuditLog:
    """Test audit logging."""

    @pytest.fixture
    def audit_log(self, tmp_path):
        return AuditLog(str(tmp_path / "audit.jsonl"))

    def test_log_creates_entry(self, audit_log):
        """Should create log entry."""
        entry = audit_log.log(AuditAction.SCAN_START, {"path": "/documents"})

        assert isinstance(entry, AuditEntry)
        assert entry.action == AuditAction.SCAN_START
        assert entry.details == {"path": "/documents"}

    def test_log_persists_to_file(self, audit_log, tmp_path):
        """Entries should be persisted to file."""
        audit_log.log(AuditAction.SCAN_START, {"test": 1})
        audit_log.log(AuditAction.SCAN_COMPLETE, {"test": 2})

        log_file = tmp_path / "audit.jsonl"
        assert log_file.exists()

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_log_entry_format(self, audit_log, tmp_path):
        """Log entries should be valid JSON."""
        audit_log.log(AuditAction.FINDING_STORE, {"count": 5}, record_count=5)

        log_file = tmp_path / "audit.jsonl"
        line = log_file.read_text().strip()
        data = json.loads(line)

        assert data["action"] == "finding_store"
        assert data["record_count"] == 5
        assert "timestamp" in data
        assert "user" in data

    def test_get_entries_returns_all(self, audit_log):
        """Should retrieve all entries."""
        for i in range(5):
            audit_log.log(AuditAction.SCAN_START, {"num": i})

        entries = audit_log.get_entries()
        assert len(entries) == 5

    def test_get_entries_filter_by_action(self, audit_log):
        """Should filter by action type."""
        audit_log.log(AuditAction.SCAN_START, {})
        audit_log.log(AuditAction.SCAN_COMPLETE, {})
        audit_log.log(AuditAction.SCAN_START, {})

        entries = audit_log.get_entries(action=AuditAction.SCAN_START)
        assert len(entries) == 2

    def test_get_entries_filter_by_time(self, audit_log):
        """Should filter by timestamp."""
        audit_log.log(AuditAction.SCAN_START, {})

        future = datetime.now() + timedelta(hours=1)
        entries = audit_log.get_entries(since=future)
        assert len(entries) == 0

        past = datetime.now() - timedelta(hours=1)
        entries = audit_log.get_entries(since=past)
        assert len(entries) == 1

    def test_get_stats(self, audit_log):
        """Should compute statistics."""
        audit_log.log(AuditAction.SCAN_START, {})
        audit_log.log(AuditAction.SCAN_COMPLETE, {})
        audit_log.log(AuditAction.FINDING_STORE, {}, success=False, error="test error")

        stats = audit_log.get_stats()

        assert stats["total_entries"] == 3
        assert stats["errors"] == 1
        assert "scan_start" in stats["by_action"]


class TestFindingsDatabase:
    """Test encrypted database storage."""

    @pytest.fixture
    def db(self, tmp_path):
        db = FindingsDatabase(str(tmp_path / "findings.db"))
        yield db
        db.close()

    @pytest.fixture
    def sample_scan_result(self, tmp_path):
        """Create a sample scan result."""
        # Create actual test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("SSN: 078-05-1120")

        scanner = Scanner()
        return scanner.scan(str(tmp_path))

    def test_store_and_retrieve_scan(self, db, sample_scan_result):
        """Should store and retrieve scan results."""
        scan_id = db.store_scan(sample_scan_result)

        scan = db.get_scan(scan_id)

        assert scan is not None
        assert scan["scan_id"] == scan_id
        assert scan["total_files"] == sample_scan_result.total_files

    def test_findings_encrypted_on_disk(self, db, sample_scan_result, tmp_path):
        """Sensitive values should be encrypted in database."""
        db.store_scan(sample_scan_result)
        db.close()

        # Read raw database
        import sqlite3

        conn = sqlite3.connect(str(tmp_path / "findings.db"))
        cursor = conn.cursor()
        cursor.execute("SELECT value_encrypted FROM matches")
        rows = cursor.fetchall()
        conn.close()

        # Should have encrypted values (not plaintext)
        for row in rows:
            encrypted_value = row[0]
            assert "078-05-1120" not in encrypted_value
            assert len(encrypted_value) > 20  # Ciphertext is longer

    def test_findings_decrypted_on_read(self, db, sample_scan_result):
        """Should decrypt values when reading."""
        db.store_scan(sample_scan_result)

        findings = list(db.get_findings(decrypt=True))

        # Find the SSN match
        ssn_findings = [f for f in findings if f["entity_type"] == "ssn"]
        assert len(ssn_findings) >= 1
        assert ssn_findings[0]["value"] == "078-05-1120"

    def test_get_findings_without_decrypt(self, db, sample_scan_result):
        """Should not include plaintext when decrypt=False."""
        db.store_scan(sample_scan_result)

        findings = list(db.get_findings(decrypt=False))

        # Should not have decrypted value
        for f in findings:
            assert "value" not in f or f.get("value") != "078-05-1120"

    def test_filter_by_entity_type(self, db, sample_scan_result):
        """Should filter findings by entity type."""
        db.store_scan(sample_scan_result)

        ssn_findings = list(db.get_findings(entity_type="ssn"))
        email_findings = list(db.get_findings(entity_type="email"))

        assert len(ssn_findings) >= 1
        assert len(email_findings) == 0

    def test_filter_excludes_test_data(self, db, tmp_path):
        """Should exclude test data by default."""
        # Create file with test SSN
        test_file = tmp_path / "test.txt"
        test_file.write_text("Example: 123-45-6789")

        scanner = Scanner()
        result = scanner.scan(str(tmp_path))
        db.store_scan(result)

        findings = list(db.get_findings(include_test_data=False))

        # Test SSN should be excluded
        assert len(findings) == 0

    def test_delete_scan(self, db, sample_scan_result):
        """Should delete scan and all findings."""
        scan_id = db.store_scan(sample_scan_result)

        # Verify it exists
        assert db.get_scan(scan_id) is not None

        # Delete it
        deleted_count = db.delete_scan(scan_id)

        # Verify it's gone
        assert db.get_scan(scan_id) is None
        assert deleted_count >= 0

    def test_list_scans(self, db, sample_scan_result):
        """Should list recent scans."""
        db.store_scan(sample_scan_result)

        scans = db.list_scans()

        assert len(scans) == 1
        assert scans[0]["scan_id"] == sample_scan_result.scan_id

    def test_get_stats(self, db, sample_scan_result):
        """Should return database statistics."""
        db.store_scan(sample_scan_result)

        stats = db.get_stats()

        assert stats["scans"] == 1
        assert stats["files"] == sample_scan_result.total_files
        assert "by_entity_type" in stats

    def test_context_manager(self, tmp_path):
        """Should work as context manager."""
        with FindingsDatabase(str(tmp_path / "test.db")) as db:
            stats = db.get_stats()
            assert stats["scans"] == 0

        # Should be closed (accessing conn would fail)


class TestAuditIntegration:
    """Test audit logging is triggered correctly."""

    @pytest.fixture
    def db(self, tmp_path):
        db = FindingsDatabase(str(tmp_path / "findings.db"))
        yield db
        db.close()

    def test_db_open_logged(self, tmp_path):
        """Opening database should be logged."""
        db = FindingsDatabase(str(tmp_path / "new.db"))

        entries = db.audit.get_entries(action=AuditAction.DB_CREATE)
        assert len(entries) >= 1

        db.close()

    def test_store_scan_logged(self, db, tmp_path):
        """Storing scan should be logged."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("SSN: 078-05-1120")

        scanner = Scanner()
        result = scanner.scan(str(tmp_path))
        db.store_scan(result)

        entries = db.audit.get_entries(action=AuditAction.FINDING_STORE)
        assert len(entries) >= 1

    def test_read_findings_logged(self, db, tmp_path):
        """Reading findings should be logged."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("SSN: 078-05-1120")

        scanner = Scanner()
        result = scanner.scan(str(tmp_path))
        db.store_scan(result)

        # Read findings
        list(db.get_findings())

        entries = db.audit.get_entries(action=AuditAction.FINDING_READ)
        assert len(entries) >= 1
