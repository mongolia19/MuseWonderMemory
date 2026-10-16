#!/usr/bin/env node
/**
 * Muse Wonder MCP Server for Claude Code
 * Implements JSON-RPC 2.0 stdio MCP protocol for explicit tool access to
 * Active Memory and Active Focus engines.
 */

import * as readline from "node:readline";
import * as crypto from "node:crypto";
import {
  loadMemory,
  saveMemory,
  matchInvariants,
  reconcileContradictionsRuleBased,
} from "../core/memory-engine.mjs";
import {
  loadFocusLedger,
  saveFocusLedger,
  buildFocusFrame,
} from "../core/focus-engine.mjs";
import { extractKeywords } from "../core/utils.mjs";

const TOOLS = [
  {
    name: "memory_recall",
    description: "Fast recall of active invariants matching a query using Jaccard token overlap & recency scoring.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query or task description" },
        top_k: { type: "number", description: "Maximum number of invariants to return", default: 5 },
      },
      required: ["query"],
    },
  },
  {
    name: "memory_save",
    description: "Save a new invariant rule with automatic contradiction reconciliation and deduplication.",
    inputSchema: {
      type: "object",
      properties: {
        content: { type: "string", description: "The architectural, tooling, or behavioral rule" },
        category: {
          type: "string",
          enum: ["architecture", "tooling", "preference", "pitfall", "gameplay", "ui", "fix"],
          description: "Category of the invariant",
          default: "preference",
        },
        tags: { type: "array", items: { type: "string" }, description: "Optional search tags" },
      },
      required: ["content"],
    },
  },
  {
    name: "memory_supersede",
    description: "Explicitly supersede an obsolete invariant with a new rule, recording the causal lineage.",
    inputSchema: {
      type: "object",
      properties: {
        old_id: { type: "string", description: "ID of the obsolete invariant to supersede" },
        new_content: { type: "string", description: "The replacement rule" },
        reason: { type: "string", description: "Reason for replacing this rule" },
      },
      required: ["old_id", "new_content"],
    },
  },
  {
    name: "memory_list",
    description: "List all invariants in the active memory store (active and/or superseded).",
    inputSchema: {
      type: "object",
      properties: {
        include_superseded: { type: "boolean", description: "Whether to include superseded rules", default: false },
        category: { type: "string", description: "Optional category filter" },
      },
    },
  },
  {
    name: "focus_status",
    description: "Inspect the current active focus frame, root goal, subgoals, scope guard, and health status.",
    inputSchema: {
      type: "object",
      properties: {},
    },
  },
  {
    name: "focus_set_goal",
    description: "Set or update the root goal, subgoals, and scope constraints in the active focus ledger.",
    inputSchema: {
      type: "object",
      properties: {
        root_goal: { type: "string", description: "Description of the main goal" },
        subgoals: {
          type: "array",
          items: {
            type: "object",
            properties: {
              id: { type: "string" },
              title: { type: "string" },
              matchPattern: { type: "string" },
              testCommand: { type: "string" },
            },
            required: ["title"],
          },
          description: "Ordered list of subgoals",
        },
        scope_allow: { type: "array", items: { type: "string" } },
        scope_deny: { type: "array", items: { type: "string" } },
      },
    },
  },
  {
    name: "focus_advance",
    description: "Advance the current active subgoal to completed status with verification evidence, activating the next subgoal.",
    inputSchema: {
      type: "object",
      properties: {
        goal_id: { type: "string", description: "Optional specific subgoal ID (defaults to currently active)" },
        evidence: { type: "string", description: "Verification evidence or test output justifying advancement" },
      },
      required: ["evidence"],
    },
  },
  {
    name: "focus_set_scope",
    description: "Configure Scope Guard allowed and forbidden glob patterns.",
    inputSchema: {
      type: "object",
      properties: {
        allowed_patterns: { type: "array", items: { type: "string" } },
        forbidden_patterns: { type: "array", items: { type: "string" } },
        strict_enforce: { type: "boolean" },
      },
    },
  },
];

async function handleToolCall(name, args) {
  const cwd = process.cwd();
  const memory = loadMemory(cwd);
  const focus = loadFocusLedger(cwd);

  switch (name) {
    case "memory_recall": {
      const query = args.query || "";
      const topK = args.top_k || 5;
      const results = matchInvariants(memory.invariants, query, topK);
      saveMemory(cwd, memory); // update hit counts
      return {
        count: results.length,
        invariants: results.map((r) => ({
          id: r.id,
          category: r.category,
          content: r.content,
          hitCount: r.hitCount,
        })),
      };
    }

    case "memory_save": {
      const content = args.content;
      const category = args.category || "preference";
      const tags = args.tags || extractKeywords(content);
      const now = Date.now();

      const supersededId = reconcileContradictionsRuleBased(content, category, memory, now);
      const newId = "inv_" + now + "_" + crypto.randomBytes(3).toString("hex");

      if (supersededId) {
        const oldInv = memory.invariants.find((i) => i.id === supersededId);
        if (oldInv) {
          oldInv.supersededBy = newId;
          oldInv.supersededAt = now;
        }
      }

      const newInv = {
        id: newId,
        content,
        category,
        tags,
        createdAt: now,
        hitCount: 0,
        supersedes: supersededId || undefined,
      };

      memory.invariants.push(newInv);
      saveMemory(cwd, memory);

      return {
        success: true,
        id: newId,
        supersededId: supersededId || null,
        message: supersededId
          ? `已保存新规则并因果推翻旧规则 (${supersededId})`
          : "已成功保存工程不变量规则",
      };
    }

    case "memory_supersede": {
      const oldId = args.old_id;
      const newContent = args.new_content;
      const now = Date.now();

      const oldInv = memory.invariants.find((i) => i.id === oldId);
      if (!oldInv) {
        throw new Error(`未找到 ID 为 "${oldId}" 的不变量规则`);
      }

      const newId = "inv_" + now + "_" + crypto.randomBytes(3).toString("hex");
      oldInv.supersededBy = newId;
      oldInv.supersededAt = now;

      const newInv = {
        id: newId,
        content: newContent,
        category: oldInv.category,
        tags: extractKeywords(newContent),
        createdAt: now,
        hitCount: 1,
        supersedes: oldId,
      };

      memory.invariants.push(newInv);
      saveMemory(cwd, memory);

      return {
        success: true,
        old_id: oldId,
        new_id: newId,
        message: `规则 ${oldId} 已废弃，由新规则 ${newId} 承接因果关系。`,
      };
    }

    case "memory_list": {
      const includeSuperseded = Boolean(args.include_superseded);
      const category = args.category;
      let list = memory.invariants;
      if (!includeSuperseded) {
        list = list.filter((i) => !i.supersededBy);
      }
      if (category) {
        list = list.filter((i) => i.category === category);
      }
      return {
        total: list.length,
        invariants: list,
      };
    }

    case "focus_status": {
      return {
        frame: buildFocusFrame(focus),
        rootGoal: focus.rootGoal,
        activeSubgoal: focus.subgoals.find((s) => s.status === "in_progress") || null,
        subgoals: focus.subgoals,
        scopeGuard: focus.scopeGuard,
        health: focus.health,
      };
    }

    case "focus_set_goal": {
      if (args.root_goal) {
        focus.rootGoal.description = args.root_goal;
        focus.rootGoal.status = "active";
      }
      if (Array.isArray(args.subgoals)) {
        focus.subgoals = args.subgoals.map((s, idx) => ({
          id: s.id || `subgoal_${idx + 1}`,
          title: s.title,
          status: idx === 0 ? "in_progress" : "pending",
          order: idx + 1,
          criteria: {
            matchPattern: s.matchPattern,
            testCommand: s.testCommand,
          },
          turnsSpent: 0,
        }));
      }
      if (args.scope_allow) focus.scopeGuard.allowedPatterns = args.scope_allow;
      if (args.scope_deny) focus.scopeGuard.forbiddenPatterns = args.scope_deny;
      saveFocusLedger(cwd, focus);
      return {
        success: true,
        rootGoal: focus.rootGoal.description,
        subgoalCount: focus.subgoals.length,
        activeSubgoal: focus.subgoals[0]?.title || null,
      };
    }

    case "focus_advance": {
      const activeIdx = focus.subgoals.findIndex((s) => s.status === "in_progress");
      if (activeIdx === -1) {
        throw new Error("当前无进行中的子任务可供结转");
      }
      const current = focus.subgoals[activeIdx];
      current.status = "completed";
      current.completedAt = Date.now();
      current.completionEvidence = args.evidence;

      let nextTitle = null;
      const nextIdx = focus.subgoals.findIndex((s, idx) => idx > activeIdx && s.status === "pending");
      if (nextIdx !== -1) {
        focus.subgoals[nextIdx].status = "in_progress";
        nextTitle = focus.subgoals[nextIdx].title;
      }
      saveFocusLedger(cwd, focus);
      return {
        success: true,
        completedGoal: current.title,
        nextActiveGoal: nextTitle,
        allCompleted: nextIdx === -1,
      };
    }

    case "focus_set_scope": {
      if (args.allowed_patterns) focus.scopeGuard.allowedPatterns = args.allowed_patterns;
      if (args.forbidden_patterns) focus.scopeGuard.forbiddenPatterns = args.forbidden_patterns;
      if (typeof args.strict_enforce === "boolean") focus.scopeGuard.strictEnforce = args.strict_enforce;
      saveFocusLedger(cwd, focus);
      return {
        success: true,
        scopeGuard: focus.scopeGuard,
      };
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

function sendResponse(id, result, error = null) {
  const msg = { jsonrpc: "2.0", id };
  if (error) {
    msg.error = { code: -32000, message: error.message || String(error) };
  } else {
    msg.result = result;
  }
  process.stdout.write(JSON.stringify(msg) + "\n");
}

function startServer() {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false,
  });

  rl.on("line", async (line) => {
    if (!line.trim()) return;
    try {
      const req = JSON.parse(line);
      const { id, method, params } = req;

      if (method === "initialize") {
        sendResponse(id, {
          protocolVersion: "2024-11-05",
          serverInfo: {
            name: "muse-wonder",
            version: "1.0.0",
          },
          capabilities: {
            tools: {},
          },
        });
      } else if (method === "tools/list") {
        sendResponse(id, { tools: TOOLS });
      } else if (method === "tools/call") {
        try {
          const res = await handleToolCall(params.name, params.arguments || {});
          sendResponse(id, {
            content: [
              {
                type: "text",
                text: JSON.stringify(res, null, 2),
              },
            ],
          });
        } catch (toolErr) {
          sendResponse(id, {
            isError: true,
            content: [
              {
                type: "text",
                text: `Error: ${toolErr.message}`,
              },
            ],
          });
        }
      } else {
        sendResponse(id, null, { message: `Method not found: ${method}` });
      }
    } catch (parseErr) {
      // Invalid JSON-RPC
    }
  });
}

startServer();
