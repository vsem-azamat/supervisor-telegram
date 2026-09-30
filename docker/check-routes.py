"""Each path the webui serves goes to the backend or build that owns it.

Reads the Caddyfile as Caddy itself understands it (`caddy adapt` output on
stdin), walks the routes the way Caddy picks them, and checks where a sample
path of each kind lands. By behaviour rather than by matcher shape: a path
sent to the wrong place comes back 404 or as the wrong app, and nothing else
in CI would notice. The same goes for a route that falls back to the page
where it must not, or the other way round, and for a cookie leaving for the
catalog.

Usage: caddy adapt ... | python3 docker/check-routes.py
"""

import fnmatch
import json
import re
import sys

WEBAPI = "webapi:8787"
CATALOG = "catalog-api:8000"
APP = "/srv/app"


# Paths whose route falls back to the page when no file matches: a client-side
# route reloaded must get the app, and a missing asset must get a 404, never
# the page (which would then be cached as that asset).
FALLS_BACK = {"/", "/chats", "/join", "/console", "/console/chats/-100123", "/administrator"}


def expectations() -> dict[str, str]:
    """Sample path → where it must end up: a proxy dial or a file root."""
    return {
        # The catalog's API: the help screens, profiles, requests.
        "/api/v1/me": CATALOG,
        "/healthz": CATALOG,
        # Everything else under /api is this repository's webapi.
        "/api/public/catalog": WEBAPI,
        "/api/auth/telegram": WEBAPI,
        # The console is the app's now; the old console's addresses lead there.
        "/console": APP,
        "/console/chats/-100123": APP,
        "/admin": "301 /console",
        "/admin/chats": "301 /console/chats",
        "/admin/chats/-100123": "301 /console/chats/-100123",
        "/admin/chats/graph": "301 /console/chats",
        "/admin/hierarchy": "301 /console/chats",
        "/admin/catalog": "301 /console/chats",
        "/admin/settings": "301 /console/system",
        "/admin/settings/": "301 /console/system",
        "/admin/": "301 /console",
        # Not the old console's, and the app's to answer.
        "/administrator": APP,
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
    """Whether Caddy would pick this route for `path`. No matcher matches all.

    Path globs and path_regexp, the two kinds this Caddyfile uses; Caddy
    compares paths case-insensitively, and so does this.
    """
    if not route.get("match"):
        return True
    for match in route["match"]:
        if any(fnmatch.fnmatch(path.lower(), p.lower()) for p in match.get("path", [])):
            return True
        regexp = match.get("path_regexp")
        if regexp and re.search(regexp["pattern"], path):
            return True
    return False


def expand(location: str, route: dict, path: str) -> str:
    """Fill a redirect's `{http.regexp.<name>.<n>}` from the path it matched."""
    for match in route.get("match", []):
        regexp = match.get("path_regexp")
        found = regexp and re.search(regexp["pattern"], path)
        if found:
            for index, group in enumerate(found.groups(), start=1):
                location = location.replace(f"{{http.regexp.{regexp['name']}.{index}}}", group)
    return location


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


def falls_back(route: dict) -> bool:
    """Whether a route rewrites a missing file to the page (`try_files`)."""
    return any(
        "try_files" in match.get("file", {})
        for handler in handlers(route)
        for sub in handler.get("routes", [])
        for match in sub.get("match", [])
    )


def cookie_free(proxy: dict) -> bool:
    """Whether a proxy drops cookies in both directions."""
    headers = proxy.get("headers", {})
    return "Cookie" in headers.get("request", {}).get("delete", []) and "Set-Cookie" in (
        headers.get("response", {}).get("delete", [])
    )


def problems(route: dict, path: str, expected: str) -> list[str]:
    """What is wrong with how `route` serves `path`, if anything."""
    found = handlers(route)
    proxy = next((h for h in found if h.get("handler") == "reverse_proxy"), None)
    redirect = next((h for h in found if h.get("handler") == "static_response"), None)
    if redirect and not proxy:
        location = expand(redirect.get("headers", {}).get("Location", ["?"])[0], route, path)
        where = f"{redirect.get('status_code')} {location}"
        return [] if where == expected else [f"goes to {where}, not {expected}"]
    if proxy:
        where = ",".join(u.get("dial") for u in proxy.get("upstreams", []))
    else:
        roots = [h["root"] for h in found if h.get("handler") == "vars" and "root" in h]
        serves = any(h.get("handler") == "file_server" for h in found)
        where = roots[0] if roots and serves else None
    if where != expected:
        return [f"goes to {where or 'nothing'}, not {expected}"]
    out = []
    if expected == CATALOG and not cookie_free(proxy):
        # The console's session is valid on this whole origin, and the
        # catalog authenticates by initData alone: not its to receive.
        out.append("is proxied with cookies")
    if not proxy and falls_back(route) != (path in FALLS_BACK):
        out.append("falls back to the page" if falls_back(route) else "does not fall back to the page")
    return out


def main() -> int:
    # `handle` blocks share a group and exactly one of them runs: the first
    # whose matcher fits. Routes outside a group (encode) pass through.
    terminal = [r for r in routes(json.load(sys.stdin)) if "group" in r]
    failed = False
    for path, expected in expectations().items():
        chosen = next((r for r in terminal if matches(r, path)), None)
        found = problems(chosen, path, expected) if chosen else ["is handled by nothing"]
        for problem in found:
            print(f"{path} {problem}", file=sys.stderr)
        failed = failed or bool(found)
        if not found:
            print(f"{path} → {expected}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
