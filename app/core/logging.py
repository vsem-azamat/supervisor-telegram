"""Structured logging configuration."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.core.config import settings


def add_severity_level(_logger: Any, _method_name: str, event_dict: EventDict) -> EventDict:
    """Add severity level to log event."""
    event_dict["severity"] = event_dict.get("level", "info").upper()
    return event_dict


def add_timestamp(_logger: Any, _method_name: str, event_dict: EventDict) -> EventDict:
    """Add timestamp to log event."""
    return event_dict


def setup_logging() -> None:
    """Setup structured logging with both console and file output."""

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.logging.level.upper(), logging.INFO),
    )

    # Setup file logging if path is provided
    if settings.logging.file_path:
        log_file = Path(settings.logging.file_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=settings.logging.max_bytes,
            backupCount=settings.logging.backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, settings.logging.level.upper(), logging.INFO))

        # Add file handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)

    # Configure processors based on environment
    processors: list[Processor] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_severity_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Use JSON formatter in production, colored console in development
    if settings.environment == "production":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a configured logger instance."""
    return structlog.get_logger(name)


# Bot-specific logging helpers
class BotLogger:
    """Bot-specific logger with common context."""

    def __init__(self, logger_name: str) -> None:
        self.logger = get_logger(logger_name)

    def log_user_action(self, user_id: int, action: str, chat_id: int | None = None, **kwargs: Any) -> None:
        """Log user action with context."""
        context = {"user_id": user_id, "action": action, **kwargs}
        if chat_id is not None:
            context["chat_id"] = chat_id

        self.logger.info("User action", **context)

    def log_moderation_action(
        self,
        admin_id: int,
        target_user_id: int,
        action: str,
        chat_id: int,
        reason: str | None = None,
        duration: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Log moderation action with context."""
        context = {
            "admin_id": admin_id,
            "target_user_id": target_user_id,
            "action": action,
            "chat_id": chat_id,
            **kwargs,
        }
        if reason:
            context["reason"] = reason
        if duration:
            context["duration"] = duration

        self.logger.info("Moderation action", **context)

    def log_telegram_error(
        self, operation: str, error: str, chat_id: int | None = None, user_id: int | None = None, **kwargs: Any
    ) -> None:
        """Log Telegram API error with context."""
        context = {"operation": operation, "error": error, "error_type": "telegram_api", **kwargs}
        if chat_id is not None:
            context["chat_id"] = chat_id
        if user_id is not None:
            context["user_id"] = user_id

        self.logger.error("Telegram API error", **context)

    def log_database_error(self, operation: str, error: str, table: str | None = None, **kwargs: Any) -> None:
        """Log database error with context."""
        context = {"operation": operation, "error": error, "error_type": "database", **kwargs}
        if table:
            context["table"] = table

        self.logger.error("Database error", **context)
