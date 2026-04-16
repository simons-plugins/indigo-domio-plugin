---
parent: Decisions
nav_order: 1
title: "ADR-0001: Adopt ADRs for indigo-domio-plugin"
status: "accepted"
date: 2026-04-16
decision-makers: solo (Simon)
consulted: none
informed: none
---
# ADR-0001: Adopt ADRs for indigo-domio-plugin

## Context and Problem Statement

indigo-domio-plugin is the Indigo Python plugin that fires push and
silent-refresh notifications from Indigo triggers through the Cloudflare
relay to iOS clients. Architectural decisions (plugin lifecycle, trigger
configuration schema, HMAC auth, retry behaviour) have accumulated in
commit messages and in my head. The workspace-level ADR practice is
established; this ADR adopts the same practice scoped to this repo.

## Decision Drivers

* Decisions specific to this plugin (IOM usage, Indigo device hooks, plugin
  preferences) belong next to the code that implements them.
* Decisions spanning the push flow (payload contract with domio-code and
  domio-push-relay, HMAC scheme) live at the workspace level.
* AI coding agents should read repo-local ADRs first, then consult
  workspace ADRs for cross-cutting concerns.

## Considered Options

* Adopt ADRs in docs/adr/ using MADR 4.0.0 (matches workspace pattern).
* Keep all ADRs at the workspace level.
* Ad-hoc Markdown under docs/ with no format.

## Decision Outcome

Chosen option: "Adopt ADRs in docs/adr/ using MADR 4.0.0".

### Consequences

* Good, because repo-local decisions travel with the repo.
* Good, because AGENTS.md can point agents at local docs/adr/INDEX.md first.
* Bad, because cross-cutting decisions require a judgement call about where
  they belong.

### Confirmation

Considered implemented when docs/adr/INDEX.md is generated and at least
one non-meta ADR has been written from a real decision in this repo.

## More Information

- Template: docs/adr/0000-template.md
- Workspace ADR practice: ~/vsCodeProjects/Indigo/docs/adr/0001-record-architecture-decisions.md

## For AI agents
- DO: Read docs/adr/INDEX.md before architectural changes in this repo.
- DO: Also read ~/vsCodeProjects/Indigo/docs/adr/INDEX.md for workspace-wide
  concerns (push contract, HMAC scheme, shared auth).
- DO: Propose a new ADR when a decision is architecturally significant.
- DON'T: Silently contradict an Accepted ADR.
- DON'T: Edit an Accepted ADR; supersede it with a new one instead.
