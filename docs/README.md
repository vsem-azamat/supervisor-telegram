# Supervisor Telegram Documentation

This directory is the documentation hub for the project.

## Source Of Truth Hierarchy

Use the docs by decision layer:

1. [Domain](domain/) - current behavioral rules that code and tests must enforce.
2. [Architecture](architecture.md) - code structure, module ownership, and
   technical decisions.
3. [Testing](testing/) - test lanes, verification strategy, and test placement.
4. [Project](project/) - operational learnings and non-canonical notes.

If documents conflict, do not guess:

- Domain docs decide current behavior.
- Architecture docs explain implementation structure.
- Testing docs explain how behavior is verified.
- Project docs record lessons and operational context, but do not override domain
  rules.

## Documentation-Driven TDD

When behavior changes:

1. Update the relevant domain document first.
2. Add or update a failing test that captures the new rule.
3. Implement the minimal code needed to pass the test.
4. Refactor after the documented behavior is protected by tests.

Use this loop for product behavior, auth boundaries, database semantics, and
externally visible API or UI contracts.

## Documentation Structure

| Category | Description |
| --- | --- |
| [Domain](domain/) | Canonical behavior for moderation, publishing, Telegram identities, and the admin web surface |
| [Testing](testing/) | Test lanes and verification rules |
| [Project](project/) | Learning log and operational notes |
| [Reviews](reviews/) | Point-in-time audits and review reports |
| [Archive](archive/) | Historical analysis and superseded material |
| [Superpowers](superpowers/) | Historical specs and implementation plans |

## Quick Navigation

### For Behavior Changes

1. Read the relevant [domain document](domain/).
2. Update that rule first if behavior is changing.
3. Follow the [testing strategy](testing/) when choosing the first failing test.

### For New Contributors

1. Start with the root [README](../README.md).
2. Read [AGENTS.md](../AGENTS.md).
3. Read the [architecture overview](architecture.md).
4. Review the [testing strategy](testing/).
5. Check the [learning log](project/learning.md) for sharp edges.

### For Existing Context

- Historical reviews and implementation plans are useful context, but they are
  not canonical behavior once domain docs or code have moved on.
