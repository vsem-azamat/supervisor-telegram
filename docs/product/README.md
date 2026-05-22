# Product Documentation

This section is the canonical product and business reference for Supervisor
Telegram.

Use it to answer:

- who the product is for;
- which jobs it exists to help with;
- which business outcomes matter;
- which capabilities belong to the product;
- what is explicitly in scope and out of scope;
- which statements are product promises versus technical enablers.

## Documents

- [Product Overview](overview.md) - target users, jobs-to-be-done, outcomes,
  capabilities, promises, enablers, and scope boundaries.
- [Sponsored Ads](sponsored-ads.md) - product intent for detecting ad-spam and
  redirecting would-be advertisers to an external paid-placement article.

## Relationship To Other Docs

- Product docs define business intent and scope.
- [Domain docs](../domain/) define current behavior that code and tests must
  enforce.
- [Architecture](../architecture.md) explains implementation structure.
- [Testing](../testing/) explains verification strategy.

When business intent changes, update the product docs first. When current
behavior changes, update the relevant domain doc before tests and
implementation.
