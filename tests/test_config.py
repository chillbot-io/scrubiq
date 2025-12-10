"""Tests for scrubiq.auth.config module."""

from pathlib import Path
from unittest.mock import patch


class TestConfig:
    """Tests for Config class."""

    def test_default_values(self):
        """Test Config has correct defaults."""
        from scrubiq.auth.config import Config

        config = Config()

        assert config.tenant_id is None
        assert config.client_id is None
        assert config.setup_complete is False
        assert config.labeling.method == "aip_client"
        assert config.labeling.skip_already_labeled is True

    def test_is_configured_false_when_missing_credentials(self):
        """Test is_configured returns False when credentials missing."""
        from scrubiq.auth.config import Config

        config = Config()
        config.tenant_id = "tenant-123"
        config.client_id = "client-456"
        # No secret

        with patch.object(config, "get_client_secret", return_value=None):
            assert not config.is_configured

    def test_is_configured_true_when_all_present(self):
        """Test is_configured returns True when all credentials present."""
        from scrubiq.auth.config import Config

        config = Config()
        config.tenant_id = "tenant-123"
        config.client_id = "client-456"

        with patch.object(config, "get_client_secret", return_value="secret-789"):
            assert config.is_configured

    def test_save_and_load(self, tmp_path):
        """Test saving and loading config."""
        from scrubiq.auth.config import Config

        # Patch CONFIG_FILE to use tmp_path
        test_config_file = tmp_path / "config.json"

        with (
            patch("scrubiq.auth.config.CONFIG_FILE", test_config_file),
            patch("scrubiq.auth.config.CONFIG_DIR", tmp_path),
        ):

            # Create and save
            config = Config()
            config.tenant_id = "my-tenant"
            config.client_id = "my-client"
            config.labeling.method = "graph_api"
            config.save()

            # Load
            loaded = Config.load()

            assert loaded.tenant_id == "my-tenant"
            assert loaded.client_id == "my-client"
            assert loaded.labeling.method == "graph_api"

    def test_environment_override(self, tmp_path):
        """Test environment variables override config file."""
        from scrubiq.auth.config import Config

        test_config_file = tmp_path / "config.json"

        with (
            patch("scrubiq.auth.config.CONFIG_FILE", test_config_file),
            patch("scrubiq.auth.config.CONFIG_DIR", tmp_path),
            patch.dict(
                "os.environ",
                {
                    "SCRUBIQ_TENANT_ID": "env-tenant",
                    "SCRUBIQ_CLIENT_ID": "env-client",
                },
            ),
        ):

            # Create file config
            config = Config()
            config.tenant_id = "file-tenant"
            config.client_id = "file-client"
            config.save()

            # Load should use env vars
            loaded = Config.load()

            assert loaded.tenant_id == "env-tenant"
            assert loaded.client_id == "env-client"

    def test_get_client_secret_from_env(self):
        """Test getting client secret from environment."""
        from scrubiq.auth.config import Config

        config = Config()

        with patch.dict("os.environ", {"SCRUBIQ_CLIENT_SECRET": "env-secret"}):
            assert config.get_client_secret() == "env-secret"

    def test_label_mappings(self):
        """Test label mapping operations."""
        from scrubiq.auth.config import Config

        config = Config()

        # Set mapping
        config.set_label_mapping(
            "highly_confidential",
            label_id="guid-123",
            label_name="Highly Confidential",
        )

        assert config.get_label_id("highly_confidential") == "guid-123"
        assert config.label_mappings["highly_confidential"].label_name == "Highly Confidential"

    def test_label_mapping_skip(self):
        """Test skip flag returns None for label_id."""
        from scrubiq.auth.config import Config

        config = Config()
        config.set_label_mapping("public", skip=True)

        assert config.get_label_id("public") is None

    def test_has_label_mappings(self):
        """Test has_label_mappings property."""
        from scrubiq.auth.config import Config

        config = Config()

        # Default has no real mappings
        assert not config.has_label_mappings

        # Add a mapping
        config.set_label_mapping("confidential", label_id="guid-456")
        assert config.has_label_mappings


class TestLabelMappingConfig:
    """Tests for LabelMappingConfig."""

    def test_default_values(self):
        """Test default values."""
        from scrubiq.auth.config import LabelMappingConfig

        mapping = LabelMappingConfig()

        assert mapping.label_id is None
        assert mapping.label_name is None
        assert mapping.skip is False

    def test_with_values(self):
        """Test with values set."""
        from scrubiq.auth.config import LabelMappingConfig

        mapping = LabelMappingConfig(
            label_id="guid-123",
            label_name="My Label",
            skip=False,
        )

        assert mapping.label_id == "guid-123"
        assert mapping.label_name == "My Label"


class TestLabelingConfig:
    """Tests for LabelingConfig."""

    def test_default_values(self):
        """Test default values."""
        from scrubiq.auth.config import LabelingConfig

        config = LabelingConfig()

        assert config.method == "aip_client"
        assert config.skip_already_labeled is True
        assert config.require_justification is False
        assert "scrubIQ" in config.default_justification


class TestConfigDir:
    """Tests for config directory functions."""

    def test_get_config_dir_returns_path(self):
        """Test get_config_dir returns a Path."""
        from scrubiq.auth.config import get_config_dir

        config_dir = get_config_dir()
        assert isinstance(config_dir, Path)
        assert "scrubiq" in str(config_dir).lower()
