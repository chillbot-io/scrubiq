"""Email message (.eml) extraction."""

import email
from email import policy
from pathlib import Path

from .base import Extractor, ExtractionError


class EmlExtractor(Extractor):
    """Extract text from .eml email files."""

    @property
    def extensions(self) -> list[str]:
        return [".eml"]

    def extract(self, path: Path) -> str:
        """Extract headers, body, and attachment names."""
        try:
            with open(path, "rb") as f:
                msg = email.message_from_binary_file(f, policy=policy.default)

            text_parts = []

            # Headers
            if msg["From"]:
                text_parts.append(f"From: {msg['From']}")
            if msg["To"]:
                text_parts.append(f"To: {msg['To']}")
            if msg["Cc"]:
                text_parts.append(f"CC: {msg['Cc']}")
            if msg["Subject"]:
                text_parts.append(f"Subject: {msg['Subject']}")
            if msg["Date"]:
                text_parts.append(f"Date: {msg['Date']}")

            text_parts.append("")  # Blank line

            # Body
            body = self._get_body(msg)
            if body:
                text_parts.append(body)

            # Attachment names
            attachments = self._get_attachment_names(msg)
            if attachments:
                text_parts.append("")
                text_parts.append("[Attachments]")
                for name in attachments:
                    text_parts.append(f"- {name}")

            return "\n".join(text_parts)

        except Exception as e:
            raise ExtractionError(f"Failed to extract from {path}: {e}")

    def _get_body(self, msg: email.message.EmailMessage) -> str:
        """Extract body text, preferring plain text over HTML."""
        # Try to get plain text body
        body = msg.get_body(preferencelist=("plain", "html"))
        if body:
            content = body.get_content()
            if isinstance(content, str):
                return content

        # Fallback: walk through parts
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset)
                    except (UnicodeDecodeError, LookupError):
                        return payload.decode("latin-1")

        return ""

    def _get_attachment_names(self, msg: email.message.EmailMessage) -> list[str]:
        """Get list of attachment filenames."""
        names = []
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                filename = part.get_filename()
                if filename:
                    names.append(filename)
        return names
