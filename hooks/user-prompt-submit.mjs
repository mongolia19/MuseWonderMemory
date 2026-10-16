#!/usr/bin/env node
/**
 * Claude Code UserPromptSubmit Hook for Muse Wonder
 * Performs Fast Invariant Recall (<10ms) and Injects Active Focus Frame.
 */

import {
  loadMemory,
  saveMemory,
  matchInvariants,
  formatInvariantsFrame,
  parseReconciliationIntervalDirective,
} from "../core/memory-engine.mjs";
import {
  loadFocusLedger,
  saveFocusLedger,
  buildFocusFrame,
  parseFocusDirectives,
} from "../core/focus-engine.mjs";
import { parseJsonSafe } from "../core/utils.mjs";

let input = "";
let done = false;

function processPrompt() {
  if (done) return;
  done = true;

  try {
    const cwd = process.cwd();
    const data = parseJsonSafe(input) || {};
    const prompt = data.prompt || input.trim() || "";

    const memory = loadMemory(cwd);
    const focus = loadFocusLedger(cwd);

    let memoryChanged = false;
    let focusChanged = false;
    const notificationMessages = [];

    // 1. 解析自然语言记忆与调谐指令
    const newInterval = parseReconciliationIntervalDirective(prompt);
    if (newInterval !== null) {
      memory.reconcileInterval = newInterval;
      memoryChanged = true;
      notificationMessages.push(`冲突检测周期已更新为每 ${newInterval} 轮`);
    }

    // 2. 解析自然语言专注与作用域指令
    const focusRes = parseFocusDirectives(prompt, focus);
    if (focusRes.changed) {
      focusChanged = true;
      if (focusRes.message) notificationMessages.push(focusRes.message);
    }

    // 3. 递增当前子任务驻留轮次
    const activeSub = focus.subgoals.find((s) => s.status === "in_progress");
    if (activeSub) {
      activeSub.turnsSpent = (activeSub.turnsSpent || 0) + 1;
      focusChanged = true;
    }

    // 4. 快速不变量召回 (System 1 Fast Recall, <10ms)
    const matched = matchInvariants(memory.invariants, prompt, 5);
    memoryChanged = true; // hit counts updated

    if (memoryChanged) saveMemory(cwd, memory);
    if (focusChanged) saveFocusLedger(cwd, focus);

    const memoryText = formatInvariantsFrame(matched);
    const focusText = buildFocusFrame(focus);

    const contextParts = [];
    if (notificationMessages.length > 0) {
      contextParts.push(`🔔 [MUSE WONDER 指令生效] ${notificationMessages.join(" | ")}`);
    }
    if (focusText) contextParts.push(focusText);
    if (memoryText) contextParts.push(memoryText);

    const additionalContext = contextParts.join("\n\n");

    const output = {
      hookSpecificOutput: {
        hookEventName: "UserPromptSubmit",
        additionalContext,
      },
    };

    process.stdout.write(JSON.stringify(output));
  } catch (err) {
    process.stdout.write(JSON.stringify({}));
  }
}

process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", processPrompt);
process.stdin.on("error", () => {
  processPrompt();
  process.exit(0);
});
setTimeout(() => {
  processPrompt();
  process.exit(0);
}, 1000).unref();
