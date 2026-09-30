"""Each path the webui serves goes to the backend or build that owns it.

Reads the Caddyfile as Caddy itself understands it (`caddy adapt` output on
stdin), walks the routes the way Caddy picks them, and checks where a sample
path of each kind lands. By behaviour rather than by matcher shape: a path
sent to the wrong place comes back 404 or as the wrong app, and nothing else
in CI would notice.

Usage: caddy adapt ... | python3 docker/check-routes.py <catalog host>
"""

import fnmatch
import json
import sys

WEBAPI = "webapi:8787"
APP = "/srv/app"
CONSOLE = "/srv/console"


def expectations(catalog: str) -> dict[str, str]:
    """Sample path → where it must end up: a proxy dial or a file root."""
    return {
        # The catalog's API: the help screens, profiles, requests.
        "/api/v1/me": f"{catalog}:443",
        "/healthz": f"{catalog}:443",
        # Everything else under /api is this repository's webapi.
        "/api/public/catalog": WEBAPI,
        "/api/auth/telegram": WEBAPI,
        # The Svelte console, until it is rebuilt inside the app.
        "/admin": CONSOLE,
        "/admin/chats": CONSOLE,
        "/_app/immutable/entry/start.js": CONSOLE,
        # The Mini App owns every other path, its client-side routes included.
        "/": APP,
        "/chats": APP,
        "/join": APP,
        "/assets/index-abc123.js": APP,
    }


def routes(config: dict) -> list[dict]:
    servers = config["apps"]["http"]["servers"]
    (server,) = servers.values()
    return server["routes"]


def matches(route: dict, path: str) -> bool:
    """Whether Caddy would pick this route for `path`. No matcher matches all."""
    if not route.get("match"):
        return True
    patterns = [p for match in route["match"] for p in match.get("path", [])]
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def handlers(route: dict) -> list[dict]:
    """Every handler under a route, however deeply nested in subroutes."""
    out: list[dict] = []
    stack = list(route.get("handle", []))
    while stack:
        handler = stack.pop()
        out.append(handler)
        for sub in handler.get("routes", []):
            stack.extend(sub.get("handle", []))
    return out


def destination(route: dict) -> tuple[str | None, bool]:
    """Where a route sends a request, and whether a proxy there speaks TLS."""
    found = handlers(route)
    for handler in found:
        if handler.get("handler") == "reverse_proxy":
            dials = [u.get("dial") for u in handler.get("upstreams", [])]
            return ",".join(dials), "tls" in handler.get("transport", {})
    roots = [h["root"] for h in found if h.get("handler") == "vars" and "root" in h]
    serves = any(h.get("handler") == "file_server" for h in found)
    return (roots[0] if roots and serves else None), False


def main() -> int:
    catalog = sys.argv[1]
    # `handle` blocks share a group and exactly one of them runs: the first
    # whose matcher fits. Routes outside a group (encode) pass through.
    terminal = [r for r in routes(json.load(sys.stdin)) if "group" in r]
    failed = False
    for path, expected in expectations(catalog).items():
        chosen = next((r for r in terminal if matches(r, path)), None)
        where, tls = destination(chosen) if chosen else (None, False)
        if where != expected:
            print(f"{path} goes to {where or 'nothing'}, not {expected}", file=sys.stderr)
            failed = True
        elif expected.endswith(":443") and not tls:
            print(f"{path} is proxied to {expected} without TLS", file=sys.stderr)
            failed = True
        else:
            print(f"{path} → {where}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
