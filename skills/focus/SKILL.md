---
name: focus
description: Inspect and manage active focus goals, subgoals ledger, and scope guard
argument-hint: "[status | set <root_goal> | advance <evidence> | scope <paths>]"
---

# `/focus` Command

Manage and inspect the Active Focus ledger:

1. If no arguments or `status`:
   - Call `focus_status` and display the formatted Active Focus Frame, root goal, subgoals, scope guard, and health counters.

2. If `set <goal_description>`:
   - Update the root goal using `focus_set_goal`.

3. If `advance <evidence>`:
   - Advance the current subgoal using `focus_advance`.

4. If `scope <paths>`:
   - Configure allowed scope patterns using `focus_set_scope`.
