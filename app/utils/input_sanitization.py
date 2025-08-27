"""Input sanitization utilities for LLM queries and user inputs.

Provides protection against:
- Prompt injection attacks
- Malicious content
- Excessively long inputs
- Special characters that could cause issues
- PII detection and removal
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from app.utils.logger import get_logger

logger = get_logger("utils.input_sanitization")


@dataclass
class SanitizationResult:
    """Result of input sanitization."""

    sanitized_text: str
    is_safe: bool
    warnings: list[str]
    removed_content: list[str]
    original_length: int
    sanitized_length: int


class InputSanitizer:
    """Comprehensive input sanitization for LLM queries."""

    def __init__(self):
        # Maximum allowed input length
        self.max_length = 10000

        # Patterns that might indicate prompt injection
        self.injection_patterns = [
            # Direct instruction patterns
            r"(?i)\b(ignore|forget|disregard)\s+(all\s+)?(previous|prior|earlier|above)\s+(instructions?|prompts?|rules?)",
            r"(?i)\b(act\s+as|pretend\s+to\s+be|roleplay\s+as)\s+",
            r"(?i)\b(system\s*:|assistant\s*:|user\s*:|human\s*:)",
            r"(?i)\b(end\s+of\s+prompt|stop\s+assistant)",
            # Injection keywords
            r"(?i)\b(jailbreak|hack|bypass|override|escalate)\b",
            r"(?i)\b(sudo|admin|root|privilege)\b",
            # Common prompt manipulation
            r"(?i)(\[|\()?system\s*(\]|\))?:?\s*(you\s+are|act\s+as)",
            r"(?i)new\s+(instructions?|rules?|guidelines?)",
            r"(?i)developer\s+mode",
            # Encoding attempts
            r"(?i)base64|hex|unicode|ascii",
            # Repetitive patterns (potential DoS)
            r"(.{1,10})\1{10,}",  # Same pattern repeated 10+ times
        ]

        # Patterns for PII detection
        self.pii_patterns = [
            # Email addresses
            (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "EMAIL"),
            # Phone numbers (basic patterns)
            (r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "PHONE"),
            (r"\b\(\d{3}\)\s*\d{3}[-.]?\d{4}\b", "PHONE"),
            # Credit card numbers (basic pattern)
            (r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "CREDIT_CARD"),
            # SSN pattern (US)
            (r"\b\d{3}-\d{2}-\d{4}\b", "SSN"),
            # IP addresses
            (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "IP_ADDRESS"),
        ]

        # Characters to escape or remove
        self.dangerous_chars = [
            "\x00",
            "\x01",
            "\x02",
            "\x03",
            "\x04",
            "\x05",
            "\x06",
            "\x07",
            "\x08",
            "\x0e",
            "\x0f",
            "\x10",
            "\x11",
            "\x12",
            "\x13",
            "\x14",
            "\x15",
            "\x16",
            "\x17",
            "\x18",
            "\x19",
            "\x1a",
            "\x1b",
            "\x1c",
            "\x1d",
            "\x1e",
            "\x1f",
        ]

        # Maximum allowed repetition of characters
        self.max_char_repetition = 10

    def _detect_prompt_injection(self, text: str) -> list[str]:
        """Detect potential prompt injection attempts."""
        warnings = []

        for pattern in self.injection_patterns:
            matches = re.findall(pattern, text)
            if matches:
                warnings.append(f"Potential prompt injection detected: pattern '{pattern[:50]}...'")
                logger.warning(f"Prompt injection pattern detected in input: {pattern[:100]}")

        return warnings

    def _detect_pii(self, text: str) -> tuple[str, list[str]]:
        """Detect and optionally redact PII from text."""
        redacted_text = text
        warnings = []

        for pattern, pii_type in self.pii_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                warnings.append(f"PII detected: {pii_type}")
                # Replace with redacted version
                redacted_text = re.sub(pattern, f"[REDACTED_{pii_type}]", redacted_text)

        return redacted_text, warnings

    def _remove_dangerous_chars(self, text: str) -> str:
        """Remove potentially dangerous control characters."""
        for char in self.dangerous_chars:
            text = text.replace(char, "")
        return text

    def _limit_repetition(self, text: str) -> str:
        """Limit excessive character repetition."""

        # Replace sequences of the same character (more than max_repetition)
        def replace_repetition(match):
            char = match.group(1)
            return char * min(len(match.group(0)), self.max_char_repetition)

        pattern = r"(.)\1{" + str(self.max_char_repetition) + r",}"
        return re.sub(pattern, replace_repetition, text)

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace to prevent formatting attacks."""
        # Replace multiple whitespace with single space
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _check_length(self, text: str) -> tuple[str, list[str]]:
        """Check and truncate text if too long."""
        warnings = []

        if len(text) > self.max_length:
            warnings.append(f"Input truncated from {len(text)} to {self.max_length} characters")
            text = text[: self.max_length]

        return text, warnings

    def _detect_encoding_attempts(self, text: str) -> list[str]:
        """Detect attempts to use various encodings to bypass filters."""
        warnings = []

        # Check for common encoding indicators
        encoding_patterns = [
            r"\\x[0-9a-fA-F]{2}",  # Hex encoding
            r"\\u[0-9a-fA-F]{4}",  # Unicode encoding
            r"\\[0-7]{3}",  # Octal encoding
            r"%[0-9a-fA-F]{2}",  # URL encoding
        ]

        for pattern in encoding_patterns:
            if re.search(pattern, text):
                warnings.append(f"Potential encoding bypass detected: {pattern}")

        return warnings

    def sanitize_query(self, text: str, strict_mode: bool = False) -> SanitizationResult:
        """Sanitize user input for LLM queries.

        Args:
            text: Input text to sanitize
            strict_mode: If True, apply more aggressive filtering

        Returns:
            SanitizationResult with sanitized text and metadata
        """
        if not text:
            return SanitizationResult(
                sanitized_text="",
                is_safe=True,
                warnings=[],
                removed_content=[],
                original_length=0,
                sanitized_length=0,
            )

        original_text = text
        original_length = len(text)
        warnings = []
        removed_content = []

        # Step 1: Basic cleaning
        text = html.escape(text)  # Escape HTML
        text = self._remove_dangerous_chars(text)
        text = self._normalize_whitespace(text)

        # Step 2: Length check
        text, length_warnings = self._check_length(text)
        warnings.extend(length_warnings)

        # Step 3: Character repetition limits
        text = self._limit_repetition(text)

        # Step 4: PII detection and redaction
        text, pii_warnings = self._detect_pii(text)
        warnings.extend(pii_warnings)

        # Step 5: Prompt injection detection
        injection_warnings = self._detect_prompt_injection(text)
        warnings.extend(injection_warnings)

        # Step 6: Encoding bypass detection
        encoding_warnings = self._detect_encoding_attempts(text)
        warnings.extend(encoding_warnings)

        # Determine if input is safe
        has_critical_issues = any(
            "injection" in warning.lower() or "bypass" in warning.lower() for warning in warnings
        )

        if strict_mode and warnings:
            is_safe = False
        else:
            is_safe = not has_critical_issues

        # Track what was removed
        if original_text != text:
            removed_content.append(f"Original length: {original_length}, final length: {len(text)}")

        return SanitizationResult(
            sanitized_text=text,
            is_safe=is_safe,
            warnings=warnings,
            removed_content=removed_content,
            original_length=original_length,
            sanitized_length=len(text),
        )

    def sanitize_document_content(self, content: str) -> SanitizationResult:
        """Sanitize document content for ingestion.

        Less strict than query sanitization but still removes dangerous content.
        """
        return self.sanitize_query(content, strict_mode=False)

    def validate_document_metadata(self, metadata: dict) -> tuple[dict, list[str]]:
        """Validate and sanitize document metadata."""
        warnings = []
        sanitized_metadata = {}

        for key, value in metadata.items():
            # Sanitize key
            key_result = self.sanitize_query(str(key), strict_mode=True)
            if not key_result.is_safe:
                warnings.append(f"Metadata key '{key}' contains unsafe content")
                continue

            # Sanitize value
            if isinstance(value, str):
                value_result = self.sanitize_query(value, strict_mode=False)
                sanitized_metadata[key_result.sanitized_text] = value_result.sanitized_text
                warnings.extend(value_result.warnings)
            elif isinstance(value, (int, float, bool)):
                sanitized_metadata[key_result.sanitized_text] = value
            else:
                warnings.append(f"Metadata value for '{key}' has unsupported type: {type(value)}")

        return sanitized_metadata, warnings


# Global sanitizer instance
_sanitizer = InputSanitizer()


def sanitize_llm_query(text: str, strict_mode: bool = False) -> SanitizationResult:
    """Sanitize user query for LLM processing."""
    return _sanitizer.sanitize_query(text, strict_mode)


def sanitize_document_content(content: str) -> SanitizationResult:
    """Sanitize document content for ingestion."""
    return _sanitizer.sanitize_document_content(content)


def validate_document_metadata(metadata: dict) -> tuple[dict, list[str]]:
    """Validate and sanitize document metadata."""
    return _sanitizer.validate_document_metadata(metadata)
