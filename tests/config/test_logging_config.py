"""Tests for config/logging_config.py."""

import json
import logging
from pathlib import Path

from loguru import logger

from free_claude_code.config.logging_config import configure_logging


def test_configure_logging_creates_parent_directories(tmp_path) -> None:
    """Nested log path: parent directories are created before truncating."""
    log_file = tmp_path / "nested" / "dir" / "app.log"
    configure_logging(str(log_file), force=True)
    assert log_file.is_file()


def test_configure_logging_writes_json_to_file(tmp_path):
    """configure_logging writes JSON lines to the specified file."""
    log_file = str(tmp_path / "test.log")
    configure_logging(log_file, force=True)

    # Emit a log via stdlib (intercepted to loguru)
    logger = logging.getLogger("test.module")
    logger.info("Test message for JSON")

    # Force flush - loguru may buffer
    from loguru import logger as loguru_logger

    loguru_logger.complete()

    content = Path(log_file).read_text(encoding="utf-8")
    lines = [line for line in content.strip().split("\n") if line]
    assert len(lines) >= 1

    # Each line should be valid JSON
    for line in lines:
        record = json.loads(line)
        assert "text" in record or "message" in record or "record" in record


def test_configure_logging_idempotent(tmp_path):
    """configure_logging is idempotent - safe to call twice with force."""
    log_file = str(tmp_path / "test.log")
    configure_logging(log_file, force=True)
    configure_logging(log_file, force=True)  # Should not raise

    logger = logging.getLogger("test.idempotent")
    logger.info("After second configure")


def test_configure_logging_skips_when_already_configured(tmp_path):
    """Without force, second call is a no-op (avoids reconfig on hot reload)."""
    log_file = str(tmp_path / "test.log")
    configure_logging(log_file, force=True)
    # Second call without force - should skip; no exception, log file unchanged
    configure_logging(str(tmp_path / "other.log"), force=False)
    # Logs still go to first file
    logger = logging.getLogger("test.skip")
    logger.info("Still goes to first file")
    from loguru import logger as loguru_logger

    loguru_logger.complete()
    assert (tmp_path / "test.log").exists()
    assert "Still goes to first file" in (tmp_path / "test.log").read_text(
        encoding="utf-8"
    )


def test_telegram_bot_token_redacted_in_message_field(tmp_path) -> None:
    log_file = str(tmp_path / "redact.log")
    configure_logging(log_file, force=True, verbose_third_party=False)
    token = "123456:ABCDEF-ghij-klm"
    logger.info("Calling {}", f"https://api.telegram.org/bot{token}/getMe")
    logger.complete()
    text = Path(log_file).read_text(encoding="utf-8")
    assert token not in text
    assert "bot<redacted>/" in text or "redacted" in text


def test_bearer_substring_redacted_in_log_file(tmp_path) -> None:
    log_file = str(tmp_path / "bearer.log")
    configure_logging(log_file, force=True, verbose_third_party=False)
    secret = "ya29.secret-token-abc"
    logger.info("Request headers: Authorization: Bearer {}", secret)
    logger.complete()
    text = Path(log_file).read_text(encoding="utf-8")
    assert secret not in text
    assert "Bearer" in text


def test_httpx_logger_quieted_when_not_verbose_third_party(tmp_path) -> None:
    log_file = str(tmp_path / "quiet.log")
    configure_logging(log_file, force=True, verbose_third_party=False)
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING


def test_httpx_resets_to_notset_when_verbose_third_party(tmp_path) -> None:
    log_file = str(tmp_path / "verbose.log")
    configure_logging(log_file, force=True, verbose_third_party=True)
    assert logging.getLogger("httpx").level == logging.NOTSET


def test_log_level_filters_below_configured(tmp_path) -> None:
    """Log entries below the configured level are suppressed."""
    log_file = str(tmp_path / "level.log")
    configure_logging(log_file, level="WARNING", force=True)

    # Emit DEBUG (should be suppressed)
    logger.debug("Debug noise")
    # Emit INFO (should be suppressed)
    logger.info("Info noise")
    # Emit WARNING (should appear)
    logger.warning("Warning message")
    # Emit ERROR (should appear)
    logger.error("Error message")

    logger.complete()
    content = Path(log_file).read_text(encoding="utf-8")

    assert "Debug noise" not in content
    assert "Info noise" not in content
    assert "Warning message" in content
    assert "Error message" in content


def test_log_level_defaults_to_debug(tmp_path) -> None:
    """When no level is passed, DEBUG is the default (backward compat)."""
    log_file = str(tmp_path / "default.log")
    configure_logging(log_file, force=True)

    logger.debug("Debug entry")
    logger.complete()
    assert "Debug entry" in Path(log_file).read_text(encoding="utf-8")
