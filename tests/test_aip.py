"""Tests for scrubiq.labeler.aip module."""

from pathlib import Path
from unittest.mock import patch, MagicMock


class TestAIPClient:
    """Tests for AIPClient class."""

    def test_powershell_path_detection(self):
        """Test PowerShell path detection."""
        from scrubiq.labeler.aip import AIPClient

        client = AIPClient()

        # Should either find PowerShell or return None
        path = client.powershell_path
        assert path is None or isinstance(path, str)

    def test_is_available_without_powershell(self):
        """Test is_available returns False without PowerShell."""
        from scrubiq.labeler.aip import AIPClient

        client = AIPClient()
        client._powershell = None  # Force no PowerShell

        assert not client.is_available()

    def test_is_available_without_aip_module(self):
        """Test is_available returns False when AIP module not installed."""
        from scrubiq.labeler.aip import AIPClient

        client = AIPClient()

        # Mock PowerShell exists but AIP module doesn't
        with (
            patch.object(client, "_powershell", "/usr/bin/pwsh"),
            patch.object(client, "_run_ps") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

            assert not client.is_available()

    def test_is_available_with_aip_module(self):
        """Test is_available returns True when AIP module installed."""
        from scrubiq.labeler.aip import AIPClient

        client = AIPClient()

        module_json = '{"Name": "AzureInformationProtection", "Version": "2.16.0"}'

        with (
            patch.object(client, "_powershell", "/usr/bin/pwsh"),
            patch.object(client, "_run_ps") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=module_json, stderr="")

            assert client.is_available()
            assert client.version == "2.16.0"

    def test_apply_label_requires_aip(self):
        """Test apply_label fails gracefully without AIP."""
        from scrubiq.labeler.aip import AIPClient

        client = AIPClient()
        client._aip_available = False

        success, message = client.apply_label(Path("test.docx"), "label-guid")

        assert not success
        assert "not installed" in message.lower()

    def test_apply_label_file_not_found(self):
        """Test apply_label fails for non-existent file."""
        from scrubiq.labeler.aip import AIPClient

        client = AIPClient()
        client._aip_available = True
        client._powershell = "/usr/bin/pwsh"

        success, message = client.apply_label(Path("/nonexistent/file.docx"), "label-guid")

        assert not success
        assert "not found" in message.lower()

    def test_apply_label_success(self, tmp_path):
        """Test successful label application."""
        from scrubiq.labeler.aip import AIPClient

        # Create a test file
        test_file = tmp_path / "test.docx"
        test_file.write_text("test content")

        client = AIPClient()
        client._aip_available = True
        client._powershell = "/usr/bin/pwsh"

        with patch.object(client, "_run_ps") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            success, message = client.apply_label(test_file, "label-guid")

            assert success
            assert "applied" in message.lower()

            # Verify the command was called correctly
            call_args = mock_run.call_args[0][0]
            assert "Set-AIPFileLabel" in call_args
            assert str(test_file) in call_args
            assert "label-guid" in call_args

    def test_apply_label_with_justification(self, tmp_path):
        """Test label application with justification."""
        from scrubiq.labeler.aip import AIPClient

        test_file = tmp_path / "test.docx"
        test_file.write_text("test content")

        client = AIPClient()
        client._aip_available = True
        client._powershell = "/usr/bin/pwsh"

        with patch.object(client, "_run_ps") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            success, message = client.apply_label(
                test_file, "label-guid", justification="Test justification"
            )

            assert success

            call_args = mock_run.call_args[0][0]
            assert "JustificationMessage" in call_args
            assert "Test justification" in call_args


class TestAIPFileStatus:
    """Tests for AIPFileStatus dataclass."""

    def test_default_values(self):
        """Test default values."""
        from scrubiq.labeler.aip import AIPFileStatus

        status = AIPFileStatus(path="/test/file.docx")

        assert status.path == "/test/file.docx"
        assert status.label_id is None
        assert status.is_labeled is False
        assert status.is_protected is False
        assert status.error is None

    def test_with_label(self):
        """Test with label set."""
        from scrubiq.labeler.aip import AIPFileStatus

        status = AIPFileStatus(
            path="/test/file.docx",
            label_id="guid-123",
            label_name="Confidential",
            is_labeled=True,
        )

        assert status.is_labeled
        assert status.label_name == "Confidential"


class TestGetStatus:
    """Tests for AIPClient.get_status method."""

    def test_get_status_file_not_found(self, tmp_path):
        """Test get_status for non-existent file."""
        from scrubiq.labeler.aip import AIPClient

        client = AIPClient()
        client._aip_available = True
        client._powershell = "/usr/bin/pwsh"

        status = client.get_status(tmp_path / "nonexistent.docx")

        assert not status.is_labeled
        assert status.error is not None
        assert "not found" in status.error.lower()

    def test_get_status_success(self, tmp_path):
        """Test successful status retrieval."""
        from scrubiq.labeler.aip import AIPClient

        test_file = tmp_path / "test.docx"
        test_file.write_text("test")

        client = AIPClient()
        client._aip_available = True
        client._powershell = "/usr/bin/pwsh"

        status_json = """
        {
            "MainLabelId": "guid-123",
            "MainLabelName": "Confidential",
            "Owner": "user@contoso.com",
            "IsProtected": false
        }
        """

        with patch.object(client, "_run_ps") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=status_json, stderr="")

            status = client.get_status(test_file)

            assert status.is_labeled
            assert status.label_id == "guid-123"
            assert status.label_name == "Confidential"
            assert status.owner == "user@contoso.com"


class TestRemoveLabel:
    """Tests for AIPClient.remove_label method."""

    def test_remove_label_success(self, tmp_path):
        """Test successful label removal."""
        from scrubiq.labeler.aip import AIPClient

        test_file = tmp_path / "test.docx"
        test_file.write_text("test")

        client = AIPClient()
        client._aip_available = True
        client._powershell = "/usr/bin/pwsh"

        with patch.object(client, "_run_ps") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            success, message = client.remove_label(test_file)

            assert success
            assert "removed" in message.lower()


class TestGetLabels:
    """Tests for AIPClient.get_labels method."""

    def test_get_labels_success(self):
        """Test successful labels retrieval."""
        from scrubiq.labeler.aip import AIPClient

        client = AIPClient()
        client._aip_available = True
        client._powershell = "/usr/bin/pwsh"

        labels_json = """
        [
            {"Id": "guid-1", "Name": "Public", "Description": "Public data"},
            {"Id": "guid-2", "Name": "Internal", "Description": "Internal only"}
        ]
        """

        with patch.object(client, "_run_ps") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=labels_json, stderr="")

            labels = client.get_labels()

            assert len(labels) == 2
            assert labels[0]["Name"] == "Public"
            assert labels[1]["Name"] == "Internal"

    def test_get_labels_empty(self):
        """Test when no labels available."""
        from scrubiq.labeler.aip import AIPClient

        client = AIPClient()
        client._aip_available = True
        client._powershell = "/usr/bin/pwsh"

        with patch.object(client, "_run_ps") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            labels = client.get_labels()

            assert labels == []


class TestModuleFunction:
    """Tests for module-level functions."""

    def test_is_available_function(self):
        """Test module-level is_available function."""
        from scrubiq.labeler.aip import is_available

        # Should return bool without error
        result = is_available()
        assert isinstance(result, bool)
