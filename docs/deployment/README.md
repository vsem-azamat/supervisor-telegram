# Deployment

This section covers production runtime operations and deployment contracts.

- [Production Credentials](production-credentials.md) - where production
  credentials live, which values must be real production values, and how to
  rotate or audit them without printing secrets.
- [Agent Runtime MCP](agent-runtime-mcp.md) - configuring the MCP endpoint, why
  it is not published to the internet, and client setup.
- [Database Handover](database-handover.md) - the database is now part of the
  stack, so the first deploy starts an empty one; how to carry the production
  rows across, and what the copy deliberately leaves behind.
