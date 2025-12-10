"""Encryption utilities using Fernet (AES-128-CBC with HMAC)."""

from cryptography.fernet import Fernet
from typing import Optional
import base64
import os

# Try to import keyring, gracefully degrade if not available
try:
    import keyring

    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False


SERVICE_NAME = "scrubiq"
KEY_NAME = "findings-encryption-key"


def _get_fallback_key_path() -> str:
    """Get path for fallback key file when keyring unavailable."""
    # Use platform-appropriate config directory
    if os.name == "nt":  # Windows
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    else:  # Unix
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))

    config_dir = os.path.join(base, "scrubiq")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, ".key")


def generate_key() -> bytes:
    """Generate a new Fernet encryption key."""
    return Fernet.generate_key()


def get_or_create_key() -> bytes:
    """
    Get encryption key from OS keyring, or create if doesn't exist.

    Falls back to file-based storage if keyring unavailable,
    with restrictive file permissions.
    """
    if HAS_KEYRING:
        try:
            # Try to get existing key
            key_str = keyring.get_password(SERVICE_NAME, KEY_NAME)
            if key_str:
                return key_str.encode()

            # Generate and store new key
            key = generate_key()
            keyring.set_password(SERVICE_NAME, KEY_NAME, key.decode())
            return key
        except Exception:
            # Keyring failed, fall back to file
            pass

    # Fallback: file-based key storage
    key_path = _get_fallback_key_path()

    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            return f.read()

    # Generate new key and save with restrictive permissions
    key = generate_key()

    # Create file with restrictive permissions (owner read/write only)
    old_umask = os.umask(0o077)
    try:
        with open(key_path, "wb") as f:
            f.write(key)
    finally:
        os.umask(old_umask)

    return key


def delete_key() -> bool:
    """
    Delete the encryption key.

    WARNING: This makes all encrypted data unrecoverable!
    Returns True if key was deleted.
    """
    deleted = False

    if HAS_KEYRING:
        try:
            keyring.delete_password(SERVICE_NAME, KEY_NAME)
            deleted = True
        except Exception:
            pass

    # Also try to delete fallback file
    key_path = _get_fallback_key_path()
    if os.path.exists(key_path):
        os.remove(key_path)
        deleted = True

    return deleted


class Encryptor:
    """
    Encrypt and decrypt sensitive data.

    Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
    Key is stored in OS keyring or secure file.

    Usage:
        encryptor = Encryptor()
        ciphertext = encryptor.encrypt("sensitive data")
        plaintext = encryptor.decrypt(ciphertext)
    """

    def __init__(self, key: Optional[bytes] = None):
        """
        Initialize encryptor.

        Args:
            key: Optional encryption key. If None, retrieves from keyring.
        """
        self._key = key or get_or_create_key()
        self._fernet = Fernet(self._key)

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a string.

        Returns base64-encoded ciphertext safe for database storage.
        """
        if not plaintext:
            return ""

        ciphertext = self._fernet.encrypt(plaintext.encode("utf-8"))
        return base64.urlsafe_b64encode(ciphertext).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a string.

        Raises InvalidToken if decryption fails (wrong key or corrupted data).
        """
        if not ciphertext:
            return ""

        raw_ciphertext = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        plaintext = self._fernet.decrypt(raw_ciphertext)
        return plaintext.decode("utf-8")

    def rotate_key(self, new_key: Optional[bytes] = None) -> bytes:
        """
        Rotate to a new encryption key.

        Returns the new key. Existing data must be re-encrypted separately.
        """
        new_key = new_key or generate_key()

        if HAS_KEYRING:
            try:
                keyring.set_password(SERVICE_NAME, KEY_NAME, new_key.decode())
            except Exception:
                pass

        # Also update fallback file
        key_path = _get_fallback_key_path()
        old_umask = os.umask(0o077)
        try:
            with open(key_path, "wb") as f:
                f.write(new_key)
        finally:
            os.umask(old_umask)

        self._key = new_key
        self._fernet = Fernet(new_key)
        return new_key
