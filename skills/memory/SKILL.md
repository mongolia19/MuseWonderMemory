---
name: memory
description: Inspect and manage active memory invariants, view superseded history, or register architectural rules
argument-hint: "[list | save <content> | supersede <id> <content>]"
---

# `/memory` Command

Manage and inspect Active Memory invariants for the current project:

1. If no arguments provided:
   - Call `memory_list` to show all currently active invariants grouped by category.
   - Display the current reconciliation interval.

2. If `save <content>`:
   - Save the specified invariant rule using `memory_save`.

3. If `supersede <id> <new_content>`:
   - Supersede the specified invariant rule using `memory_supersede`.

4. If `history` or `all`:
   - List all invariants including historical superseded rules showing the causal link (`supersededBy` -> `id`).
