import re
import urllib.parse
from typing import ClassVar, Protocol

from app.core.errors import ValidationError


class FileStorageService(Protocol):
    """Protocol interface for file storage implementations."""

    def validate_file_url(self, file_url: str) -> str:
        """Validates that the file URL is structurally safe and properly formed."""
        ...

    def generate_safe_url(self, file_path_or_key: str) -> str:
        """Generates a sanitized / signed URL for client access."""
        ...


class SafeUrlStorageService:
    """
    Decoupled storage validation service for Phase 3.
    Validates document URLs, enforces permissible URL schemes and formats,
    and prevents arbitrary URL injection or unsafe path traversal.
    """

    ALLOWED_SCHEMES: ClassVar[set[str]] = {"http", "https", "s3", "gs"}
    ALLOWED_EXTENSIONS: ClassVar[set[str]] = {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    }
    MAX_URL_LENGTH = 1024

    def validate_file_url(self, file_url: str) -> str:
        clean_url = file_url.strip()
        if not clean_url:
            raise ValidationError(
                message="File URL cannot be empty.",
                code="STORAGE_INVALID_URL",
                details={"field": "file_url"},
            )

        if len(clean_url) > self.MAX_URL_LENGTH:
            raise ValidationError(
                message=(
                    f"File URL exceeds maximum length of "
                    f"{self.MAX_URL_LENGTH} characters."
                ),
                code="STORAGE_URL_TOO_LONG",
                details={"max_length": self.MAX_URL_LENGTH},
            )

        parsed = urllib.parse.urlparse(clean_url)
        if not parsed.scheme or parsed.scheme.lower() not in self.ALLOWED_SCHEMES:
            raise ValidationError(
                message=(
                    f"Invalid URL scheme '{parsed.scheme}'. "
                    f"Allowed schemes: {sorted(self.ALLOWED_SCHEMES)}."
                ),
                code="STORAGE_INVALID_SCHEME",
                details={"allowed_schemes": list(self.ALLOWED_SCHEMES)},
            )

        if not parsed.netloc and parsed.scheme in {"http", "https"}:
            raise ValidationError(
                message="HTTP/HTTPS URLs must include a valid host domain.",
                code="STORAGE_INVALID_HOST",
            )

        # Validate file extension
        path = parsed.path.lower()
        has_valid_ext = any(path.endswith(ext) for ext in self.ALLOWED_EXTENSIONS)
        if not has_valid_ext:
            raise ValidationError(
                message=(
                    f"Unsupported document format. Allowed extensions: "
                    f"{sorted(self.ALLOWED_EXTENSIONS)}."
                ),
                code="STORAGE_INVALID_EXTENSION",
                details={"allowed_extensions": list(self.ALLOWED_EXTENSIONS)},
            )

        # Check for path traversal attempts
        if ".." in path or "//" in path:
            normalized_path = re.sub(r"/+", "/", path)
            if ".." in normalized_path:
                raise ValidationError(
                    message=(
                        "Directory traversal patterns are not permitted in file URL."
                    ),
                    code="STORAGE_PATH_TRAVERSAL",
                )

        return clean_url

    def generate_safe_url(self, file_path_or_key: str) -> str:
        return self.validate_file_url(file_path_or_key)


storage_service = SafeUrlStorageService()
