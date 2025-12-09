"""Outlook message (.msg) extraction."""

from pathlib import Path

from .base import Extractor, ExtractionError

try:
    import extract_msg

    HAS_MSG = True
except ImportError:
    HAS_MSG = False


class MsgExtractor(Extractor):
    """Extract text from Outlook .msg files."""

    @property
    def extensions(self) -> list[str]:
        return [".msg"]

    def extract(self, path: Path) -> str:
        """Extract headers, body, and attachment names."""
        if not HAS_MSG:
            raise ExtractionError("extract-msg not installed. Run: pip install extract-msg")

        try:
            msg = extract_msg.Message(path)
            text_parts = []

            # Headers
            if msg.sender:
                text_parts.append(f"From: {msg.sender}")
            if msg.to:
                text_parts.append(f"To: {msg.to}")
            if msg.cc:
                text_parts.append(f"CC: {msg.cc}")
            if msg.subject:
                text_parts.append(f"Subject: {msg.subject}")
            if msg.date:
                text_parts.append(f"Date: {msg.date}")

            text_parts.append("")  # Blank line

            # Body
            if msg.body:
                text_parts.append(msg.body)

            # Note attachment names (might contain sensitive info)
            if msg.attachments:
                text_parts.append("")
                text_parts.append("[Attachments]")
                for att in msg.attachments:
                    if hasattr(att, "longFilename") and att.longFilename:
                        text_parts.append(f"- {att.longFilename}")
                    elif hasattr(att, "shortFilename") and att.shortFilename:
                        text_parts.append(f"- {att.shortFilename}")

            msg.close()
            return "\n".join(text_parts)

        except Exception as e:
            raise ExtractionError(f"Failed to extract from {path}: {e}")
