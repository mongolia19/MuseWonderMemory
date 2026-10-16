#!/usr/bin/env node
/**
 * Claude Code PostToolUse Hook for Muse Wonder
 * Tracks execution health (anti-loop breaker) and evaluates deterministic autonomous advancement.
 */

import {
  loadFocusLedger,
  saveFocusLedger,
  evaluateAutonomousAdvancement,
  recordExecutionHealth,
} from "../core/focus-engine.mjs";
import { parseJsonSafe } from "../core/utils.mjs";

let input = "";
let done = false;

function processPostTool() {
  if (done) return;
  done = true;

  try {
    const cwd = process.cwd();
    const data = parseJsonSafe(input) || {};
    const toolName = data.tool_name || "";
    const toolResult = typeof data.tool_result === "string" ? data.tool_result : JSON.stringify(data.tool_result || "");
    const exitCode = typeof data.exit_code === "number" ? data.exit_code : (data.error ? 1 : 0);
    const hasError = Boolean(data.error) || exitCode !== 0;

    const focus = loadFocusLedger(cwd);
    let changed = false;
    const messages = [];

    // 1. 记录工具执行健康度 (防死循环熔断器)
    const healthRes = recordExecutionHealth(focus, !hasError, toolName);
    changed = true;

    if (healthRes.loopDetected) {
      messages.push(
        `🚨 [ACTIVE FOCUS 熔断预警] 工具 "${toolName}" 已连续失败 ${healthRes.count} 次！请立即停止机械重试，检查根本原因或调整方案。`
      );
    }

    // 2. 自动化确定性证据结转检测 (Track 1)
    const advanceRes = evaluateAutonomousAdvancement(focus, {
      output: toolResult,
      exitCode,
    });

    if (advanceRes.advanced) {
      changed = true;
      messages.push(
        `🎯 [ACTIVE FOCUS 自动推进] 子任务 "${advanceRes.completedId}" 自验证通过并已结转！${
          advanceRes.nextId ? `已激活下一项攻坚目标: "${advanceRes.nextId}"` : "所有分层子任务已完成！"
        }`
      );
    }

    if (changed) {
      saveFocusLedger(cwd, focus);
    }

    if (messages.length > 0) {
      const output = {
        hookSpecificOutput: {
          hookEventName: "PostToolUse",
          additionalContext: messages.join("\n"),
        },
        systemMessage: messages.join("\n"),
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
process.stdin.on("end", processPostTool);
process.stdin.on("error", () => {
  processPostTool();
  process.exit(0);
});
setTimeout(() => {
  processPostTool();
  process.exit(0);
}, 1000).unref();
