"""Authentication and Microsoft Graph API client."""

from .graph import GraphClient, GraphAuthError, GraphAPIError, DriveItem, is_available
from .config import Config, LabelMappingConfig, LabelingConfig, get_config_dir, CONFIG_DIR
from .setup import AzureSetupWizard, ManualSetupGuide, SetupResult

__all__ = [
    # Graph client
    "GraphClient",
    "GraphAuthError",
    "GraphAPIError",
    "DriveItem",
    "is_available",
    # Config
    "Config",
    "LabelMappingConfig",
    "LabelingConfig",
    "get_config_dir",
    "CONFIG_DIR",
    # Setup
    "AzureSetupWizard",
    "ManualSetupGuide",
    "SetupResult",
]
