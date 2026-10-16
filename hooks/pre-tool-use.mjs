#!/usr/bin/env node
/**
 * Claude Code PreToolUse Hook for Muse Wonder
 * Enforces Active Focus Scope Guard on file modifications.
 */

import { loadFocusLedger, checkScopeViolation } from "../core/focus-engine.mjs";
import { parseJsonSafe } from "../core/utils.mjs";

let input = "";
let done = false;

function processPreTool() {
  if (done) return;
  done = true;

  try {
    const cwd = process.cwd();
    const data = parseJsonSafe(input) || {};
    const toolName = data.tool_name || "";
    const toolInput = data.tool_input || {};

    const focus = loadFocusLedger(cwd);

    // 检查文件修改工具作用域
    if (["Edit", "Write", "MultiEdit", "NotebookEdit"].includes(toolName)) {
      const targetPath =
        toolInput.file_path ||
        toolInput.path ||
        toolInput.target_file ||
        toolInput.TargetFile ||
        "";

      if (targetPath) {
        const check = checkScopeViolation(focus, targetPath);
        if (check.violated) {
          const isStrict = focus.scopeGuard.strictEnforce || true;
          if (isStrict) {
            const output = {
              hookSpecificOutput: {
                hookEventName: "PreToolUse",
                permissionDecision: "deny",
              },
              systemMessage: `🛡️ [ACTIVE FOCUS SCOPE GUARD 拦截]\n${check.reason}\n如确需修改该路径，请先在对话中输入指令：“只允许修改: <路径>” 调整作用域白名单。`,
            };
            process.stdout.write(JSON.stringify(output));
            return;
          }
        }
      }
    }

    process.stdout.write(JSON.stringify({}));
  } catch (err) {
    process.stdout.write(JSON.stringify({}));
  }
}

process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", processPreTool);
process.stdin.on("error", () => {
  processPreTool();
  process.exit(0);
});
setTimeout(() => {
  processPreTool();
  process.exit(0);
}, 1000).unref();
