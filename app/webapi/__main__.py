"""Dev runner: `uv run -m app.webapi` starts the API on :8787 with reload."""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "app.webapi.main:app",
        host="127.0.0.1",
        port=8787,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
