import structlog
from src.app.utils.logging import redact_sensitive_text, secret_masking_processor, setup_logging, get_logger


def test_redact_sensitive_text():
    sample = "bot123456:ABC-DEF1234ghIkl and PrivateKey = abc123def456 and password=secret123 and postgresql+asyncpg://user:mypassword@localhost/db"
    redacted = redact_sensitive_text(sample)
    assert "ABC-DEF" not in redacted
    assert "abc123def456" not in redacted
    assert "secret123" not in redacted
    assert "mypassword" not in redacted


def test_secret_masking_processor():
    event_dict = {
        "event": "user connected with bot123456:ABC-DEF",
        "nested": {"token": "bot999:xyz", "count": 5},
        "num": 42,
    }
    processed = secret_masking_processor(None, "info", event_dict)
    assert "ABC-DEF" not in processed["event"]
    assert "xyz" not in processed["nested"]["token"]
    assert processed["num"] == 42


def test_setup_logging_and_get_logger():
    setup_logging(log_level="DEBUG", json_logs=True)
    logger = get_logger("test")
    assert logger is not None
    setup_logging(log_level="INFO", json_logs=False)
