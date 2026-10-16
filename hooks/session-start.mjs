#!/usr/bin/env node
/**
 * Claude Code SessionStart Hook for Muse Wonder
 * Initializes Active Memory & Active Focus context at session launch.
 */

import { loadMemory, formatInvariantsFrame } from "../core/memory-engine.mjs";
import { loadFocusLedger, buildFocusFrame } from "../core/focus-engine.mjs";

function main() {
  try {
    const cwd = process.cwd();
    const memory = loadMemory(cwd);
    const focus = loadFocusLedger(cwd);

    const activeInvariants = memory.invariants.filter((i) => !i.supersededBy);
    const memoryText = formatInvariantsFrame(activeInvariants.slice(0, 5));
    const focusText = buildFocusFrame(focus);

    const context = [
      "🧠 [MUSE WONDER ACTIVATED: ACTIVE MEMORY & ACTIVE FOCUS]",
      `已装载 ${activeInvariants.length} 条工程不变量规则与主动专注引擎。`,
      "",
      focusText,
      "",
      memoryText,
    ].filter(Boolean).join("\n");

    const output = {
      hookSpecificOutput: {
        hookEventName: "SessionStart",
        additionalContext: context,
      },
    };

    process.stdout.write(JSON.stringify(output));
  } catch (err) {
    // Never crash on hook failure
    process.stdout.write(JSON.stringify({}));
  }
}

main();
