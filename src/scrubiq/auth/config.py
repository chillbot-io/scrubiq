"""Configuration management for scrubIQ.

Handles:
- Microsoft 365 credentials (tenant_id, client_id)
- Label mappings (scrubIQ recommendation → Microsoft label ID)
- Labeling preferences
- Secure credential storage via keyring

Config file location:
- Linux/Mac: ~/.config/scrubiq/config.json
- Windows: %LOCALAPPDATA%/scrubiq/config.json

Secrets (client_secret) are stored in system keyring, not config file.
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def get_config_dir() -> Path:
    """Get platform-specific config directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", "~"))
    elif sys.platform == "darwin":
        base = Path("~/Library/Application Support")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config"))

    return base.expanduser() / "scrubiq"


CONFIG_DIR = get_config_dir()
CONFIG_FILE = CONFIG_DIR / "config.json"
KEYRING_SERVICE = "scrubiq"


@dataclass
class LabelMappingConfig:
    """Mapping from scrubIQ recommendation to Microsoft label."""

    label_id: Optional[str] = None
    label_name: Optional[str] = None
    skip: bool = False  # If True, don't apply any label for this recommendation


@dataclass
class LabelingConfig:
    """Labeling behavior configuration."""

    method: str = "aip_client"  # "aip_client" or "graph_api"
    skip_already_labeled: bool = True
    require_justification: bool = False
    default_justification: str = "Applied by scrubIQ based on content classification"


@dataclass
class Config:
    """scrubIQ configuration."""

    # Microsoft 365 credentials
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    # client_secret stored in keyring, not here

    # Label mappings
    label_mappings: dict[str, LabelMappingConfig] = field(
        default_factory=lambda: {
            "highly_confidential": LabelMappingConfig(),
            "confidential": LabelMappingConfig(),
            "internal": LabelMappingConfig(),
            "public": LabelMappingConfig(skip=True),  # Default: don't label public
        }
    )

    # Labeling behavior
    labeling: LabelingConfig = field(default_factory=LabelingConfig)

    # Setup metadata
    setup_complete: bool = False
    app_created_by_setup: bool = False  # True if we created the app registration

    @classmethod
    def load(cls) -> "Config":
        """Load config from file + environment + keyring."""
        config = cls()

        # Load from file if exists
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    data = json.load(f)
                config = cls._from_dict(data)
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")

        # Override with environment variables
        if os.environ.get("SCRUBIQ_TENANT_ID"):
            config.tenant_id = os.environ["SCRUBIQ_TENANT_ID"]
        if os.environ.get("SCRUBIQ_CLIENT_ID"):
            config.client_id = os.environ["SCRUBIQ_CLIENT_ID"]

        return config

    @classmethod
    def _from_dict(cls, data: dict) -> "Config":
        """Create Config from dictionary."""
        config = cls()

        config.tenant_id = data.get("tenant_id")
        config.client_id = data.get("client_id")
        config.setup_complete = data.get("setup_complete", False)
        config.app_created_by_setup = data.get("app_created_by_setup", False)

        # Label mappings
        if "label_mappings" in data:
            for key, value in data["label_mappings"].items():
                if isinstance(value, dict):
                    config.label_mappings[key] = LabelMappingConfig(
                        label_id=value.get("label_id"),
                        label_name=value.get("label_name"),
                        skip=value.get("skip", False),
                    )

        # Labeling config
        if "labeling" in data:
            lb = data["labeling"]
            config.labeling = LabelingConfig(
                method=lb.get("method", "aip_client"),
                skip_already_labeled=lb.get("skip_already_labeled", True),
                require_justification=lb.get("require_justification", False),
                default_justification=lb.get(
                    "default_justification", config.labeling.default_justification
                ),
            )

        return config

    def save(self):
        """Save config to file."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "setup_complete": self.setup_complete,
            "app_created_by_setup": self.app_created_by_setup,
            "label_mappings": {
                key: {
                    "label_id": mapping.label_id,
                    "label_name": mapping.label_name,
                    "skip": mapping.skip,
                }
                for key, mapping in self.label_mappings.items()
            },
            "labeling": {
                "method": self.labeling.method,
                "skip_already_labeled": self.labeling.skip_already_labeled,
                "require_justification": self.labeling.require_justification,
                "default_justification": self.labeling.default_justification,
            },
        }

        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)

        logger.debug(f"Config saved to {CONFIG_FILE}")

    def get_client_secret(self) -> Optional[str]:
        """Get client secret from keyring or environment."""
        # Environment takes precedence
        secret = os.environ.get("SCRUBIQ_CLIENT_SECRET")
        if secret:
            return secret

        # Try keyring
        try:
            import keyring

            secret = keyring.get_password(KEYRING_SERVICE, "client_secret")
            return secret
        except Exception:
            return None

    def set_client_secret(self, secret: str):
        """Store client secret in keyring."""
        try:
            import keyring

            keyring.set_password(KEYRING_SERVICE, "client_secret", secret)
            logger.debug("Client secret stored in keyring")
        except Exception as e:
            logger.warning(f"Failed to store secret in keyring: {e}")
            raise

    def delete_client_secret(self):
        """Remove client secret from keyring."""
        try:
            import keyring

            keyring.delete_password(KEYRING_SERVICE, "client_secret")
        except Exception:
            pass

    @property
    def is_configured(self) -> bool:
        """Check if Microsoft 365 credentials are configured."""
        return bool(self.tenant_id and self.client_id and self.get_client_secret())

    @property
    def has_label_mappings(self) -> bool:
        """Check if any label mappings are configured."""
        return any(m.label_id is not None for m in self.label_mappings.values() if not m.skip)

    def get_label_id(self, recommendation: str) -> Optional[str]:
        """Get label ID for a recommendation, or None if should skip."""
        mapping = self.label_mappings.get(recommendation)
        if not mapping or mapping.skip:
            return None
        return mapping.label_id

    def set_label_mapping(
        self,
        recommendation: str,
        label_id: Optional[str] = None,
        label_name: Optional[str] = None,
        skip: bool = False,
    ):
        """Set label mapping for a recommendation."""
        self.label_mappings[recommendation] = LabelMappingConfig(
            label_id=label_id,
            label_name=label_name,
            skip=skip,
        )


def ensure_config_dir():
    """Create config directory if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def reset_config():
    """Delete all configuration and credentials."""
    config = Config.load()
    config.delete_client_secret()

    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()

    logger.info("Configuration reset")
