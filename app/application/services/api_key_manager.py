"""API key management with context managers."""

import os
from collections.abc import Generator
from contextlib import contextmanager


@contextmanager
def with_api_key(api_key: str, base_url: str | None = None) -> Generator[None, None, None]:
    """
    Context manager for safely setting OpenAI API key and base URL.

    This prevents environment variable pollution by properly restoring
    the original values after the context exits.

    Args:
        api_key: OpenAI compatible API key
        base_url: Optional base URL for the API

    Yields:
        None
    """
    # Store original values
    original_api_key = os.environ.get("OPENAI_API_KEY")
    original_base_url = os.environ.get("OPENAI_BASE_URL")

    try:
        # Set new values
        os.environ["OPENAI_API_KEY"] = api_key
        if base_url:
            os.environ["OPENAI_BASE_URL"] = base_url
        elif "OPENAI_BASE_URL" in os.environ:
            # Remove base URL if it was set but we don't want it now
            del os.environ["OPENAI_BASE_URL"]

        yield

    finally:
        # Restore original values
        if original_api_key is not None:
            os.environ["OPENAI_API_KEY"] = original_api_key
        else:
            os.environ.pop("OPENAI_API_KEY", None)

        if original_base_url is not None:
            os.environ["OPENAI_BASE_URL"] = original_base_url
        else:
            os.environ.pop("OPENAI_BASE_URL", None)
