---
name: active-memory
description: Use when preserving or modifying project invariants, handling architectural constraints, reconciling conflicting user instructions, or recalling past engineering decisions under long-horizon sessions.
version: 1.0.0
---

# Active Memory (主动记忆认知引擎)

The `active-memory` skill provides continuous architectural and behavioral invariant preservation for coding agents based on Meta's Muse Wonder Active Memory architecture.

## Core Principles

1. **Invariants are Non-Negotiable**:
   - Invariants injected in `[ACTIVE INVARIANTS]` represent explicit user and architectural constraints.
   - Never break an active invariant unless explicitly instructed by the user to change or supersede it.

2. **Causal Lineage & Contradiction Reconciliation**:
   - When the user asks to switch technologies or replace a rule (e.g. *"switch from npm to pnpm"*, *"change weapon upgrade rules"*), the old invariant is **superseded** rather than deleted.
   - The engine automatically links `supersededBy` and `supersedes` to maintain causal auditability.
   - Superseded rules are **100% excluded** from the active context frame to prevent model oscillation.

3. **Available MCP Tools**:
   - `memory_recall(query, top_k)`: Retrieve invariants matching specific keywords or concepts.
   - `memory_save(content, category, tags)`: Register a newly agreed architectural or behavioral rule.
   - `memory_supersede(old_id, new_content, reason)`: Formally replace an existing obsolete rule with a new rule.
   - `memory_list(include_superseded, category)`: Inspect all active and superseded rules.

4. **Natural Language Directives**:
   - The user can adjust the background reconciliation interval at any time by saying:
     - *"把冲突检测间隔设为5轮"* or *"set reconciliation interval to 5 turns"*
