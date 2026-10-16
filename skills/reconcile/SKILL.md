---
name: reconcile
description: Force immediate dual-engine contradiction reconciliation and prune obsolete memory rules
argument-hint: ""
---

# `/reconcile` Command

Triggers immediate dual-engine reconciliation across all stored invariants:

1. Loads the memory store.
2. Checks for semantic contradictions, superseded replacements, and token overlap.
3. Updates `supersededBy` pointers and reports changes.
4. Resets `turnsSinceReconcile` to 0.
