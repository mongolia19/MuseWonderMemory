#!/usr/bin/env node
/**
 * Claude Code Stop Hook for Muse Wonder
 * Evaluates Agent Declaration Protocol (FOCUS_ADVANCE) and executes periodic memory reconciliation.
 */

import {
  loadMemory,
  saveMemory,
  runFallbackHeuristics,
} from "../core/memory-engine.mjs";
import {
  loadFocusLedger,
  saveFocusLedger,
  evaluateAutonomousAdvancement,
} from "../core/focus-engine.mjs";
import { parseJsonSafe, extractTextFromMessage } from "../core/utils.mjs";

let input = "";
let done = false;

function processStop() {
  if (done) return;
  done = true;

  try {
    const cwd = process.cwd();
    const data = parseJsonSafe(input) || {};
    const assistantText =
      extractTextFromMessage(data.last_assistant_message) ||
      extractTextFromMessage(data.message) ||
      data.text ||
      "";

    const focus = loadFocusLedger(cwd);
    const memory = loadMemory(cwd);

    let focusChanged = false;
    let memoryChanged = false;
    const notifications = [];

    // 1. 评估 Agent 声明式自主推进协议 (Track 2: FOCUS_ADVANCE: <id> | <evidence>)
    if (assistantText) {
      const advanceRes = evaluateAutonomousAdvancement(focus, {
        text: assistantText,
      });

      if (advanceRes.advanced) {
        focusChanged = true;
        notifications.push(
          `🎯 [ACTIVE FOCUS 声明结转] Agent 声明自检通过！子任务 "${advanceRes.completedId}" 已标记完成。`
        );
      }
    }

    // 2. 周期节流与启发式规则提炼 (Heuristic Distillation & Throttle)
    memory.turnsSinceReconcile = (memory.turnsSinceReconcile || 0) + 1;
    memoryChanged = true;

    if (assistantText) {
      const added = runFallbackHeuristics("", assistantText, cwd, memory);
      if (added > 0) {
        memoryChanged = true;
        notifications.push(`🧠 [ACTIVE MEMORY 自动沉淀] 成功提炼沉淀 ${added} 条新工程不变量`);
      }
    }

    if (memory.turnsSinceReconcile >= (memory.reconcileInterval || 3)) {
      memory.turnsSinceReconcile = 0;
      memoryChanged = true;
    }

    if (focusChanged) saveFocusLedger(cwd, focus);
    if (memoryChanged) saveMemory(cwd, memory);

    if (notifications.length > 0) {
      const output = {
        hookSpecificOutput: {
          hookEventName: "Stop",
          additionalContext: notifications.join("\n"),
        },
      };
      process.stdout.write(JSON.stringify(output));
    } else {
      process.stdout.write(JSON.stringify({}));
    }
  } catch (err) {
    process.stdout.write(JSON.stringify({}));
  }
}

process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", processStop);
process.stdin.on("error", () => {
  processStop();
  process.exit(0);
});
setTimeout(() => {
  processStop();
  process.exit(0);
}, 1000).unref();
