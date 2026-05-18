# Admin Web

The web surface has a public read layer and an authenticated admin layer.

## Core Rules

- Public visitors may access only explicitly public, read-only endpoints.
- The current public endpoint is `GET /api/public/catalog`.
- Public responses must expose only fields intended for anonymous viewers.
- Administrative reads and all mutations require an authenticated admin session.
- Authentication shortcuts or bypass flags are not valid production or remote
  development behavior.
- Magic links are an administrator access mechanism and must be generated only
  through trusted admin-only flows.

## Tests

- Anonymous access tests must prove the public projection is available and does
  not leak admin-only fields.
- Protected endpoint tests must prove anonymous requests are rejected.
- Authenticated tests must prove allowed admin actions still succeed.
- UI tests should preserve the distinction between public browsing and
  authenticated administration.
