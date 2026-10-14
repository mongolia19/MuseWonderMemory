import * as fs from "node:fs";
import * as path from "node:path";

export interface RootGoal {
  id: string;
  description: string;
  status: "active" | "completed" | "blocked" | "superseded";
  successCriteria: string[];
}

export interface SubgoalCriteria {
  testCommand?: string;
  matchPattern?: string;
  expectedExitCode?: number;
  requiredFiles?: string[];
}

export interface Subgoal {
  id: string;
  title: string;
  status: "pending" | "in_progress" | "completed" | "skipped";
  order: number;
  targetPaths?: string[];
  criteria?: SubgoalCriteria;
  turnsSpent: number;
  completedAt?: number;
  completionEvidence?: string;
}

export interface ScopeGuard {
  enabled: boolean;
  allowedPatterns: string[];
  forbiddenPatterns: string[];
  strictEnforce: boolean;
}

export interface ExecutionHealth {
  consecutiveFailures: number;
  maxFailureThreshold: number;
  lastFailedTool?: string;
}

export interface GoalLedger {
  version: "1.0.0";
  updatedAt: number;
  rootGoal: RootGoal;
  subgoals: Subgoal[];
  scopeGuard: ScopeGuard;
  health: ExecutionHealth;
}

export const DEFAULT_FOCUS_LEDGER: GoalLedger = {
  version: "1.0.0",
  updatedAt: Date.now(),
  rootGoal: {
    id: "goal_default",
    description: "当前开发主线任务",
    status: "active",
    successCriteria: [],
  },
  subgoals: [],
  scopeGuard: {
    enabled: true,
    allowedPatterns: ["**/*"],
    forbiddenPatterns: [".git/**", "node_modules/**"],
    strictEnforce: false,
  },
  health: {
    consecutiveFailures: 0,
    maxFailureThreshold: 3,
  },
};

export function loadFocusLedger(storagePath: string): GoalLedger {
  try {
    if (fs.existsSync(storagePath)) {
      const raw = fs.readFileSync(storagePath, "utf-8");
      return JSON.parse(raw);
    }
  } catch {}
  return JSON.parse(JSON.stringify(DEFAULT_FOCUS_LEDGER));
}

export function saveFocusLedger(storagePath: string, ledger: GoalLedger): void {
  ledger.updatedAt = Date.now();
  const dir = path.dirname(storagePath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(storagePath, JSON.stringify(ledger, null, 2), "utf-8");
}

export function buildFocusFrame(ledger: GoalLedger): string {
  const root = ledger.rootGoal;
  const activeSub = ledger.subgoals.find((s) => s.status === "in_progress");
  const pendingCount = ledger.subgoals.filter((s) => s.status === "pending").length;
  const completedCount = ledger.subgoals.filter((s) => s.status === "completed").length;
  const totalCount = ledger.subgoals.length;

  const lines: string[] = [
    "=== [ACTIVE FOCUS FRAME: 强目标锚定与防漂移] ===",
    `🎯 核心主线目标: ${root.description} [${root.status.toUpperCase()}]`,
  ];

  if (root.successCriteria.length > 0) {
    lines.push(`   验收指标: ${root.successCriteria.join("; ")}`);
  }

  if (activeSub) {
    lines.push(
      `📍 当前攻坚子任务 (${completedCount + 1}/${totalCount}): [${activeSub.title}] (已耗费 ${activeSub.turnsSpent} 轮)`
    );
    if (activeSub.criteria?.matchPattern) {
      lines.push(`   自检验收模式: 输出需包含 "${activeSub.criteria.matchPattern}"`);
    }
    if (activeSub.turnsSpent >= 3) {
      lines.push("   ⚠️ 滞留预警: 该子任务已停留 >= 3 轮，请自检证据后声明 FOCUS_ADVANCE 或推进");
    }
  } else if (pendingCount === 0 && totalCount > 0) {
    lines.push("🎉 所有分层子任务均已完成！请执行全局验证准备交付。");
  } else {
    lines.push("📍 当前无活跃子任务，请设定或激活下一项任务。");
  }

  if (ledger.scopeGuard.enabled && ledger.scopeGuard.forbiddenPatterns.length > 0) {
    lines.push(`🛡️ 作用域守卫: 禁止越界修改 [${ledger.scopeGuard.forbiddenPatterns.join(", ")}]`);
  }

  if (ledger.health.consecutiveFailures > 0) {
    lines.push(
      `⚠️ 连续失败警报: 当前工具已连续失败 ${ledger.health.consecutiveFailures}/${ledger.health.maxFailureThreshold} 次！请切换方案避免死循环。`
    );
  }

  lines.push("==================================================");
  return lines.join("\n");
}

export function matchGlobPattern(filePath: string, pattern: string): boolean {
  const normalized = filePath.replace(/\\/g, "/").replace(/^\.\//, "");
  const p = pattern.replace(/\\/g, "/").replace(/^\.\//, "");
  if (p === "**/*" || p === "*") return true;
  if (p.endsWith("/**")) {
    const prefix = p.slice(0, -3);
    return normalized === prefix || normalized.startsWith(prefix + "/");
  }
  if (p.endsWith("/*")) {
    const prefix = p.slice(0, -2);
    const rest = normalized.slice(prefix.length + 1);
    return normalized.startsWith(prefix + "/") && !rest.includes("/");
  }
  return normalized === p || normalized.includes(p);
}

export function checkScopeViolation(
  ledger: GoalLedger,
  filePath: string
): { violated: boolean; reason?: string } {
  if (!ledger.scopeGuard.enabled) return { violated: false };
  const normalized = filePath.replace(/\\/g, "/");

  for (const forbidden of ledger.scopeGuard.forbiddenPatterns) {
    if (matchGlobPattern(normalized, forbidden)) {
      return {
        violated: true,
        reason: `修改被拦截：路径 "${filePath}" 命中禁改模式 "${forbidden}"`,
      };
    }
  }

  if (ledger.scopeGuard.allowedPatterns.length > 0) {
    const isAllowed = ledger.scopeGuard.allowedPatterns.some((pattern) =>
      matchGlobPattern(normalized, pattern)
    );
    if (!isAllowed) {
      return {
        violated: true,
        reason: `修改被拦截：路径 "${filePath}" 不在允许的作用域白名单中`,
      };
    }
  }

  return { violated: false };
}

export function evaluateAutonomousAdvancement(
  ledger: GoalLedger,
  context: { output?: string; exitCode?: number; text?: string }
): { advanced: boolean; completedId?: string; nextId?: string; evidence?: string } {
  const activeIdx = ledger.subgoals.findIndex((s) => s.status === "in_progress");
  if (activeIdx === -1) return { advanced: false };

  const current = ledger.subgoals[activeIdx];
  let satisfied = false;
  let evidence = "";

  // 轨道 1: 确定性自检验收匹配 (Command Output / Exit Code)
  if (current.criteria) {
    const exitOk =
      current.criteria.expectedExitCode === undefined ||
      context.exitCode === current.criteria.expectedExitCode;
    const patternOk =
      !current.criteria.matchPattern ||
      (context.output && context.output.includes(current.criteria.matchPattern));

    if (exitOk && patternOk && (context.exitCode !== undefined || context.output)) {
      satisfied = true;
      evidence = `自动化自检通过 (exitCode=${context.exitCode ?? 0}, pattern=${current.criteria.matchPattern ?? "none"})`;
    }
  }

  // 轨道 2: Agent 自主指令推进协议 (FOCUS_ADVANCE: <id> | <evidence>)
  if (!satisfied && context.text) {
    const match = context.text.match(/FOCUS_ADVANCE:\s*([^\s|]+)(?:\s*\|\s*([^\n\r]+))?/i);
    if (match) {
      const targetId = match[1].trim();
      if (targetId === current.id || targetId === "current") {
        satisfied = true;
        evidence = match[2]?.trim() || "Agent 声明自检通过并主动推进";
      }
    }
  }

  if (satisfied) {
    current.status = "completed";
    current.completedAt = Date.now();
    current.completionEvidence = evidence;

    // 自动激活下一序位子任务
    const nextIdx = ledger.subgoals.findIndex(
      (s, idx) => idx > activeIdx && s.status === "pending"
    );
    let nextId: string | undefined;
    if (nextIdx !== -1) {
      ledger.subgoals[nextIdx].status = "in_progress";
      nextId = ledger.subgoals[nextIdx].id;
    }

    return {
      advanced: true,
      completedId: current.id,
      nextId,
      evidence,
    };
  }

  return { advanced: false };
}

export function parseFocusDirectives(
  text: string,
  ledger: GoalLedger
): { changed: boolean; message?: string } {
  let changed = false;
  const messages: string[] = [];

  // 1. 设定或修改根目标: 锁定目标[:：] <目标描述>
  const goalMatch = text.match(/(?:锁定目标|设定目标|根目标)[:：]\s*([^\n\r]+)/);
  if (goalMatch) {
    ledger.rootGoal.description = goalMatch[1].trim();
    ledger.rootGoal.status = "active";
    changed = true;
    messages.push(`根目标已锁定为: "${ledger.rootGoal.description}"`);
  }

  // 2. 限制作用域: 限制作用域[:：] <路径> 或 只允许修改[:：] <路径>
  const scopeMatch = text.match(/(?:限制作用域|只允许修改|仅限目录)[:：]\s*([^\n\r]+)/);
  if (scopeMatch) {
    const rawPaths = scopeMatch[1].split(/[,，\s]+/).filter(Boolean);
    ledger.scopeGuard.allowedPatterns = rawPaths;
    ledger.scopeGuard.enabled = true;
    changed = true;
    messages.push(`作用域白名单已更新为: [${rawPaths.join(", ")}]`);
  }

  // 3. 禁止修改: 禁止修改[:：] <路径>
  const forbidMatch = text.match(/(?:禁止修改|不能碰|禁改路径)[:：]\s*([^\n\r]+)/);
  if (forbidMatch) {
    const rawPaths = forbidMatch[1].split(/[,，\s]+/).filter(Boolean);
    ledger.scopeGuard.forbiddenPatterns = rawPaths;
    ledger.scopeGuard.enabled = true;
    changed = true;
    messages.push(`禁改黑名单已更新为: [${rawPaths.join(", ")}]`);
  }

  // 4. 手动推进任务: 推进目标 / 下一个子任务 / 完成当前任务
  if (/(?:推进目标|推进到下一个|完成当前子任务|下一个任务)/.test(text)) {
    const activeIdx = ledger.subgoals.findIndex((s) => s.status === "in_progress");
    if (activeIdx !== -1) {
      ledger.subgoals[activeIdx].status = "completed";
      ledger.subgoals[activeIdx].completedAt = Date.now();
      ledger.subgoals[activeIdx].completionEvidence = "用户自然语言指令手动推进";
      const nextIdx = ledger.subgoals.findIndex(
        (s, idx) => idx > activeIdx && s.status === "pending"
      );
      if (nextIdx !== -1) {
        ledger.subgoals[nextIdx].status = "in_progress";
        messages.push(`子任务 "${ledger.subgoals[activeIdx].title}" 完成，已激活下一项`);
      } else {
        messages.push(`子任务 "${ledger.subgoals[activeIdx].title}" 完成，所有任务已就绪`);
      }
      changed = true;
    }
  }

  return {
    changed,
    message: messages.join("; "),
  };
}

export function recordExecutionHealth(
  ledger: GoalLedger,
  success: boolean,
  toolName?: string
): { loopDetected: boolean; count: number } {
  if (success) {
    ledger.health.consecutiveFailures = 0;
    ledger.health.lastFailedTool = undefined;
    return { loopDetected: false, count: 0 };
  }

  ledger.health.consecutiveFailures += 1;
  ledger.health.lastFailedTool = toolName;
  const loopDetected = ledger.health.consecutiveFailures >= ledger.health.maxFailureThreshold;

  return {
    loopDetected,
    count: ledger.health.consecutiveFailures,
  };
}

// -------------------------------------------------------------
// Pi Extension 插件入口挂载
// -------------------------------------------------------------
export default function piActiveFocusExtension(pi: any) {
  const storagePath = path.resolve(".pi/active-focus.json");

  pi.on("before_agent_start", (event: any) => {
    const ledger = loadFocusLedger(storagePath);
    const userInput = event.prompt || "";

    // 解析用户口语指令
    const directiveRes = parseFocusDirectives(userInput, ledger);
    if (directiveRes.changed) {
      saveFocusLedger(storagePath, ledger);
    }

    // 推进当前子任务驻留轮次
    const activeSub = ledger.subgoals.find((s) => s.status === "in_progress");
    if (activeSub) {
      activeSub.turnsSpent += 1;
      saveFocusLedger(storagePath, ledger);
    }

    // 强提示框架前置注入
    const focusFrame = buildFocusFrame(ledger);
    event.systemPrompt = `${focusFrame}\n\n${event.systemPrompt || ""}`;
  });

  pi.on("tool_call", (event: any) => {
    const ledger = loadFocusLedger(storagePath);
    if (ledger.scopeGuard.enabled && event.toolName === "write_to_file") {
      const target = event.args?.TargetFile || event.args?.path;
      if (target) {
        const check = checkScopeViolation(ledger, target);
        if (check.violated && ledger.scopeGuard.strictEnforce) {
          throw new Error(`[ACTIVE FOCUS SCOPE GUARD] ${check.reason}`);
        }
      }
    }
  });

  pi.on("agent_end", (event: any) => {
    const ledger = loadFocusLedger(storagePath);

    // 自动化验收结转检测
    const advanceRes = evaluateAutonomousAdvancement(ledger, {
      output: event.lastToolOutput,
      exitCode: event.lastToolExitCode,
      text: event.agentResponse,
    });

    if (advanceRes.advanced) {
      saveFocusLedger(storagePath, ledger);
    }
  });
}
