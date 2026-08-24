import logging
import re
import sys
from typing import Any, Dict
import structlog


# Redaction patterns for tokens, keys, passwords, and sensitive bodies
SENSITIVE_PATTERNS = [
    (re.compile(r"bot\d+:[A-Za-z0-9_-]+", re.IGNORECASE), "bot[REDACTED_TOKEN]"),
    (re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+ PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"PrivateKey\s*=\s*[A-Za-z0-9+/=]+", re.IGNORECASE), "PrivateKey = [REDACTED]"),
    (re.compile(r"PresharedKey\s*=\s*[A-Za-z0-9+/=]+", re.IGNORECASE), "PresharedKey = [REDACTED]"),
    (re.compile(r"password=([^\s&]+)", re.IGNORECASE), "password=[REDACTED]"),
    (re.compile(r"://([^:]+):([^@]+)@", re.IGNORECASE), r"://\1:[REDACTED]@"),
]


def redact_sensitive_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def secret_masking_processor(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    redacted_dict: Dict[str, Any] = {}
    for key, value in event_dict.items():
        if isinstance(value, str):
            redacted_dict[key] = redact_sensitive_text(value)
        elif isinstance(value, dict):
            redacted_dict[key] = {
                k: (redact_sensitive_text(v) if isinstance(v, str) else v)
                for k, v in value.items()
            }
        else:
            redacted_dict[key] = value
    return redacted_dict


def setup_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        secret_masking_processor,
    ]

    if json_logs:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "vpn_bot") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
