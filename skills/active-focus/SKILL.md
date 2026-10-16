---
name: active-focus
description: Use when executing multi-step tasks, advancing through ordered subgoals, preventing goal drift, obeying scope guard boundaries, or breaking out of execution loops.
version: 1.0.0
---

# Active Focus (主动专注与目标锚定引擎)

The `active-focus` skill enforces task boundary discipline and goal anchoring based on Meta's Muse Wonder Active Focus architecture.

## Core Principles

1. **The Focus Frame (`[ACTIVE FOCUS FRAME]`)**:
   - The top of the context frame contains the **Root Goal**, the **Current Active Subgoal**, the **Scope Guard**, and the **Health Status**.
   - Focus all attention and tool calls exclusively on resolving the current active subgoal. Do not skip ahead or perform unrequested tangential refactoring.

2. **Dual-Track Autonomous Advancement**:
   - **Track 1 (Deterministic Criteria)**: When a command or test output matches the subgoal's `criteria.matchPattern` or `expectedExitCode`, the engine automatically advances to the next subgoal.
   - **Track 2 (Agent Protocol)**: When you have verified your implementation via tests or inspection, output:
     `FOCUS_ADVANCE: <subgoal_id> | <concrete verification evidence>`
     or `FOCUS_ADVANCE: current | <evidence>`.
     The `Stop` hook will parse this declaration, mark the subgoal as completed, and advance the ledger.

3. **Scope Guard Boundaries**:
   - The Scope Guard prevents unauthorized modifications outside allowed glob patterns.
   - If an edit is denied or warned, do not attempt to bypass it by hacking alternative paths. Ask the user or use natural language: *"只允许修改: <paths>"* or *"限制作用域: <paths>"*.

4. **Anti-Loop Circuit Breaker**:
   - If a tool fails repeatedly (>= 3 consecutive failures), the breaker trips.
   - When tripped: Stop repeating the failed tool call. Re-read error output, formulate an alternative hypothesis, and explain your updated strategy.

5. **Available MCP Tools**:
   - `focus_status()`: Inspect full ledger, active subgoal, and execution health.
   - `focus_set_goal(root_goal, subgoals, scope_allow, scope_deny)`: Initialize or reorganize task plans.
   - `focus_advance(evidence)`: Explicitly advance the active subgoal.
   - `focus_set_scope(allowed_patterns, forbidden_patterns, strict_enforce)`: Configure scope guard.
