# MuseWonderMemory: Active Memory & Invariant Preservation for Coding Agents

> **Replicating Meta's Muse Wonder Active Memory Paradigm for Autonomous Software Engineering Agents**

[![QA Tests](https://img.shields.io/badge/QA%20Tests-5%2F5%20Passed-brightgreen.svg)](#qa--benchmark-suite)
[![Benchmark Raiden](https://img.shields.io/badge/Raiden%20Benchmark-20%2F20%20Passed-brightgreen.svg)](#qa--benchmark-suite)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 🌟 Background & Motivation

In October 2026, Meta Superintelligence Labs (led by Mark Zuckerberg and Alexandr Wang) announced **Muse Wonder Full**, a frontier foundation model that set new records across SWE-bench and long-horizon software engineering evaluations—substantially outperforming GPT and Claude frontier models in complex, multi-round autonomous coding tasks.

Meta's core architectural breakthrough wasn't just scaling parameter count or brute-force context windows; it was the introduction of **Active Memory** and **Active Focus**. 

### The Problem: Coding Agent "Amnesia" & Context Churn
Traditional LLM coding agents (Claude Code, Cursor, Pi, Aider) operate within sliding context windows or lossy compaction summaries:
- **Rule Erosion**: As conversations stretch past 20–50 turns, architectural constraints set in turn 3 (e.g. *"never modify weapon upgrade rules"*, *"keep canvas 600x800"*) get pruned away or compressed into oblivion.
- **Contradiction Hallucinations**: When users give evolving instructions, models often oscillate between conflicting instructions across rounds without causal tracking.
- **Cost & Latency Waste**: Stuffing tens of thousands of raw conversational tokens on every round drives up token costs and slows down agent reaction times.

**MuseWonderMemory** is a production-grade, open-source replication and implementation of Meta's Active Memory paradigm tailored for interactive coding assistants and autonomous engineering agents.

---

## 🏗️ Architecture & Core Mechanics

The implementation in [`.pi/extensions/active-memory.ts`](file:///.pi/extensions/active-memory.ts) adopts a **Dual-Loop Cognitive Architecture**:

```
                       User Prompt / Action
                               │
                               ▼
        ┌──────────────────────────────────────────────┐
        │  System 1: Fast Invariant Recall (<10ms)     │
        │  • Jaccard Token Overlap & Keyword Matching  │
        │  • Strict Superseded Rule Filtering          │
        │  • Prepend Invariants to Agent Working Frame │
        └──────────────────────┬───────────────────────┘
                               │
                               ▼
                    [ LLM Coding Execution ]
                               │
                               ▼
        ┌──────────────────────────────────────────────┐
        │  System 2: Background Reconciliation Engine  │
        │  • Semantic Deduplication & Clustering       │
        │  • Contradiction Detection & Causal Chains   │
        │  • `supersededBy` / `supersedes` Tracking    │
        │  • Dual Engine: LLM Judge + Rule-based Fallback│
        │  • Periodic Throttle (every N turns)         │
        └──────────────────────┬───────────────────────┘
                               │
                               ▼
                    Persistent Invariants Store
                     (`active-memory.json`)
```

### 1. Invariant Contract (`MemoryInvariant`)
Every piece of preserved memory is structured as a typed invariant:
- `id`: Unique identifier (`inv_<timestamp>_<rand>`).
- `content`: Explicit architectural or behavioral rule.
- `category`: Classification (`architecture`, `gameplay`, `ui`, `tooling`, `fix`).
- `tags`: Indexed keyword tokens for fast sub-millisecond retrieval.
- `createdAt` / `hitCount` / `lastHitAt`: Access and recency tracking.
- `supersededBy`: Pointer to newer rules if this invariant has been formally updated or superseded.
- `supersedes`: Backpointer for causal lineage and auditability.

### 2. Dual-Engine Contradiction Resolution
When new constraints arrive that conflict with historical decisions:
1. **LLM Engine**: Extracts semantic oppositions, determines whether the user intended an explicit replacement or a conditional branch, and writes the causal trace.
2. **Deterministic Fallback Engine**: If the LLM provider fails, times out, or has no quota, rule-based heuristics automatically analyze conflicting predicates and update the causal pointer to guarantee zero downtime.

---

## 🔬 Benchmark: The Raiden Arcade Replication

To rigorously quantify the effect of Active Memory on long-horizon coding tasks, we designed an end-to-end benchmark replicating the classic arcade game **Raiden (雷电)** in Python/Pygame over 20+ sequential feature additions and refactoring rounds:

| Evaluation Dimension | Control Group (Vanilla Agent) | Treatment Group (**Active Memory**) |
| :--- | :---: | :---: |
| **Architectural Invariant Retention** | ❌ Regressed at Round 8 (reverted to single weapon) | ✅ **100% Retained** across all 20 rounds |
| **Weapon Upgrade Discipline** | ❌ Broke 3-consecutive powerup rule | ✅ **Strict 1->2->3 & reset on switch** |
| **Emergency Bomb & Survival** | ❌ Forgot bomb HUD and life reset rule | ✅ **Flawless bomb screen-clear & reset** |
| **Boss Multi-phase Progression** | ❌ Boss entered immediately, skipping waves | ✅ **Timed entry at Wave 18 (frame 4877)** |
| **Headless QA Pass Rate** | 64.7% (11/17) | **100% (20/20 PASS)** |

---

## 🚀 Quickstart

### Prerequisites
- Node.js 22.0+ (with native strip-types support)
- Python 3.9+ & `pygame` (for the benchmark suites)
- `pnpm` or `npm`

### Installation
```bash
git clone https://github.com/mongolia19/MuseWonderMemory.git
cd MuseWonderMemory

# Install dependencies
pnpm install
```

### Running the QA Suite
Run the 5 core lifecycle QA tests (废弃规则过滤、Jaccard 去重、双引擎冲突消解、容灾提取、自然语言指令节流):
```bash
npm test
```

### Running the Raiden Benchmark Self-Tests
Verify both the treatment and control game implementations in headless mode:
```bash
# Treatment group (Active Memory assisted)
python3 experiments/tank_battle_benchmark/treatment_active_memory/raiden_game.py --test

# Control group (Baseline)
python3 experiments/tank_battle_benchmark/control_no_memory/raiden_game.py --test
```

---

## 📁 Repository Structure

```
├── .pi/
│   ├── active-memory.json            # Active invariant persistent memory state
│   └── extensions/
│       └── active-memory.ts          # Core Active Memory extension implementation
├── experiments/
│   ├── pi_active_memory_blog.md      # In-depth technical blog post & architecture paper
│   ├── pi_active_memory_cover.jpg    # Article cover asset
│   └── tank_battle_benchmark/
│       ├── treatment_active_memory/  # Raiden & Tank game (Active Memory treatment)
│       └── control_no_memory/        # Raiden & Tank game (Baseline control)
├── tests/
│   └── test_qa_suite.mjs             # Rigorous 5-point QA test suite
├── package.json
└── README.md
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
