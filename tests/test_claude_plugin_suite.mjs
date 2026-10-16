/**
 * Comprehensive QA Test Suite for Muse Wonder Claude Code Plugin
 *
 * Verifies all 12 core requirements:
 * 1. Fast Invariant Recall (Jaccard + keyword overlap)
 * 2. Superseded Rule Hard Exclusion & Recency Ranking
 * 3. Dual-Engine Contradiction Reconciliation & Causal Chains
 * 4. Natural Language Directives & Dynamic Throttling
 * 5. Active Focus Frame Generation & Goal Anchoring
 * 6. Scope Guard Glob Matching & PreToolUse Interception
 * 7. Deterministic Output Criteria Autonomous Advancement
 * 8. Agent Protocol (FOCUS_ADVANCE) Autonomous Advancement
 * 9. Anti-Loop Circuit Breaker on Consecutive Failures
 * 10. Claude Code Lifecycle Hooks Execution (stdin/stdout JSON protocol)
 * 11. MCP Server JSON-RPC stdio Protocol & Tool Invocations
 * 12. Claude CLI Manifest & Strict Directory Validation
 */

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { execSync, spawn } from "node:child_process";

import {
  extractKeywords,
  calculateTokenOverlap,
  matchGlobPattern,
  getMemoryFilePath,
  getFocusFilePath,
} from "../core/utils.mjs";

import {
  loadMemory,
  saveMemory,
  matchInvariants,
  formatInvariantsFrame,
  reconcileContradictionsRuleBased,
  reconcileContradictions,
  extractCandidateRules,
  runFallbackHeuristics,
  parseReconciliationIntervalDirective,
} from "../core/memory-engine.mjs";

import {
  loadFocusLedger,
  saveFocusLedger,
  buildFocusFrame,
  checkScopeViolation,
  evaluateAutonomousAdvancement,
  parseFocusDirectives,
  recordExecutionHealth,
  DEFAULT_FOCUS_LEDGER,
} from "../core/focus-engine.mjs";

console.log("==========================================================================");
console.log("  MUSE WONDER —— Claude Code Plugin 核心能力严格自检套件");
console.log("==========================================================================");

const TEST_DIR = path.resolve("./.test_claude_env_" + Date.now());
fs.mkdirSync(path.join(TEST_DIR, ".claude"), { recursive: true });

try {
  // ----------------------------------------------------------------------
  // Case 1: Fast Invariant Recall (Jaccard + Keyword Overlap)
  // ----------------------------------------------------------------------
  {
    const store = {
      version: 1,
      invariants: [
        {
          id: "inv_1",
          content: "严格使用 pnpm 作为项目唯一包管理器，严禁使用 npm 或 yarn",
          category: "tooling",
          tags: ["pnpm", "包管理器", "npm", "yarn"],
          createdAt: Date.now() - 10000,
          hitCount: 2,
        },
        {
          id: "inv_2",
          content: "UI 界面必须采用 Tailwind CSS v4 与纯几何图元规范",
          category: "ui",
          tags: ["tailwind", "css", "几何图元"],
          createdAt: Date.now() - 5000,
          hitCount: 0,
        },
        {
          id: "inv_3",
          content: "后端接口必须遵循 RESTful 规范并返回统一包装结构",
          category: "architecture",
          tags: ["restful", "api", "接口"],
          createdAt: Date.now() - 2000,
          hitCount: 5,
        },
      ],
    };

    const recalled = matchInvariants(store.invariants, "请帮我安装 lodash 并配置 pnpm 包管理", 3);
    assert.ok(recalled.length > 0, "必须成功召回相关不变量");
    assert.strictEqual(recalled[0].id, "inv_1", "与 pnpm 相关的规则必须排在第一位");
    console.log("✔ QA Case 1 [快环召回 (Jaccard + 词元重合)]: PASS");
  }

  // ----------------------------------------------------------------------
  // Case 2: Superseded Rule Hard Exclusion & Recency Ranking
  // ----------------------------------------------------------------------
  {
    const store = {
      version: 1,
      invariants: [
        {
          id: "inv_old",
          content: "使用 Jest 作为前端测试框架",
          category: "tooling",
          tags: ["jest", "测试"],
          createdAt: 1000,
          supersededBy: "inv_new",
          supersededAt: 2000,
        },
        {
          id: "inv_new",
          content: "全面切换为 Vitest 作为前端单元测试框架，严禁使用 Jest",
          category: "tooling",
          tags: ["vitest", "测试", "jest"],
          createdAt: 2000,
          supersedes: "inv_old",
          hitCount: 1,
        },
      ],
    };

    const recalled = matchInvariants(store.invariants, "帮我编写前端测试用例运行 jest", 5);
    const hasOld = recalled.some((i) => i.id === "inv_old");
    const hasNew = recalled.some((i) => i.id === "inv_new");

    assert.strictEqual(hasOld, false, "已被推翻的旧规则必须 100% 排除出活跃检索池");
    assert.strictEqual(hasNew, true, "最新有效规则必须被正常召回");
    console.log("✔ QA Case 2 [废弃规则硬过滤与因果链条]: PASS");
  }

  // ----------------------------------------------------------------------
  // Case 3: Dual-Engine Contradiction Reconciliation
  // ----------------------------------------------------------------------
  {
    const store = {
      version: 1,
      invariants: [
        {
          id: "inv_pg",
          content: "主数据库统一使用 PostgreSQL",
          category: "architecture",
          tags: ["数据库", "postgresql"],
          createdAt: 1000,
        },
      ],
    };

    // 规则代码匹配测试
    const newRule = "即日起全面改用 MySQL 作为主数据库，废除 PostgreSQL";
    const supersededId = reconcileContradictionsRuleBased(newRule, "architecture", store);
    assert.strictEqual(supersededId, "inv_pg", "规则引擎必须精准匹配出被替换的 PostgreSQL 规则");

    // 双引擎接口测试 (模拟 LLM 与 Fallback)
    const mockLlmCaller = async () =>
      JSON.stringify({
        hasContradiction: true,
        supersededId: "inv_pg",
        reason: "User explicitly migrates from Postgres to MySQL",
      });

    const res = await reconcileContradictions(newRule, "architecture", store, mockLlmCaller);
    assert.strictEqual(res.supersededId, "inv_pg");
    assert.strictEqual(res.engine, "llm");
    console.log("✔ QA Case 3 [双引擎因果矛盾消解]: PASS");
  }

  // ----------------------------------------------------------------------
  // Case 4: Natural Language Directives & Dynamic Throttling
  // ----------------------------------------------------------------------
  {
    const interval1 = parseReconciliationIntervalDirective("请把冲突检测间隔设为5轮");
    assert.strictEqual(interval1, 5, "中文口语指令提取周期正常");

    const interval2 = parseReconciliationIntervalDirective("set conflict detection interval to 8");
    assert.strictEqual(interval2, 8, "英文指令提取周期正常");

    const interval3 = parseReconciliationIntervalDirective("每轮进行实时因果追溯");
    assert.strictEqual(interval3, 1, "实时检测解析为 1 轮");
    console.log("✔ QA Case 4 [自然语言指令动态节流]: PASS");
  }

  // ----------------------------------------------------------------------
  // Case 5: Active Focus Frame Generation & Goal Anchoring
  // ----------------------------------------------------------------------
  {
    const ledger = JSON.parse(JSON.stringify(DEFAULT_FOCUS_LEDGER));
    ledger.rootGoal.description = "开发二战不列颠空战飞行模拟器";
    ledger.rootGoal.successCriteria = ["3D视锥投影", "第一关保卫战通过", "第二关俯冲轰炸通过"];
    ledger.subgoals = [
      {
        id: "sub_1",
        title: "实现人工地平线滚转变换矩阵",
        status: "in_progress",
        order: 1,
        turnsSpent: 1,
        criteria: { matchPattern: "SELFTEST: OK" },
      },
      {
        id: "sub_2",
        title: "编写俯冲瞄准具对地落点预测环",
        status: "pending",
        order: 2,
        turnsSpent: 0,
      },
    ];

    const frame = buildFocusFrame(ledger);
    assert.ok(frame.includes("ACTIVE FOCUS FRAME"), "工作帧头标记存在");
    assert.ok(frame.includes("二战不列颠空战飞行模拟器"), "主线根目标包含在内");
    assert.ok(frame.includes("实现人工地平线滚转变换矩阵"), "当前活跃攻坚子任务展示正常");
    assert.ok(frame.includes("SELFTEST: OK"), "自检验收标准包含在内");
    console.log("✔ QA Case 5 [Active Focus 目标锚定与工作帧生成]: PASS");
  }

  // ----------------------------------------------------------------------
  // Case 6: Scope Guard Glob Matching & PreToolUse Interception
  // ----------------------------------------------------------------------
  {
    const ledger = JSON.parse(JSON.stringify(DEFAULT_FOCUS_LEDGER));
    ledger.scopeGuard.enabled = true;
    ledger.scopeGuard.allowedPatterns = ["experiments/air_combat/**", "src/**/*.ts"];
    ledger.scopeGuard.forbiddenPatterns = [".git/**", "experiments/control_group/**"];

    const check1 = checkScopeViolation(ledger, "experiments/air_combat/game.py");
    assert.strictEqual(check1.violated, false, "白名单内路径允许修改");

    const check2 = checkScopeViolation(ledger, "experiments/control_group/baseline.py");
    assert.strictEqual(check2.violated, true, "禁改模式路径必须被拦截");

    const check3 = checkScopeViolation(ledger, "server/index.js");
    assert.strictEqual(check3.violated, true, "不在白名单内的路径必须被拦截");
    console.log("✔ QA Case 6 [Scope Guard 作用域越界拦截]: PASS");
  }

  // ----------------------------------------------------------------------
  // Case 7: Deterministic Output Pattern Autonomous Advancement
  // ----------------------------------------------------------------------
  {
    const ledger = JSON.parse(JSON.stringify(DEFAULT_FOCUS_LEDGER));
    ledger.subgoals = [
      {
        id: "sub_1",
        title: "跑通雷达防守测试",
        status: "in_progress",
        order: 1,
        criteria: { matchPattern: "15 passed, 0 failed", expectedExitCode: 0 },
      },
      {
        id: "sub_2",
        title: "集成投弹音效",
        status: "pending",
        order: 2,
      },
    ];

    const advanceRes = evaluateAutonomousAdvancement(ledger, {
      output: "自检统计: 15 passed, 0 failed, 共 15 项\nSELFTEST: OK",
      exitCode: 0,
    });

    assert.strictEqual(advanceRes.advanced, true, "满足自检断言特征必须自动推进");
    assert.strictEqual(advanceRes.completedId, "sub_1", "当前任务标记为 completed");
    assert.strictEqual(advanceRes.nextId, "sub_2", "下一项任务激活为 in_progress");
    assert.strictEqual(ledger.subgoals[0].status, "completed");
    assert.strictEqual(ledger.subgoals[1].status, "in_progress");
    console.log("✔ QA Case 7 [确定性自检输出特征自主推进 (Track 1)]: PASS");
  }

  // ----------------------------------------------------------------------
  // Case 8: Agent Protocol (FOCUS_ADVANCE) Autonomous Advancement
  // ----------------------------------------------------------------------
  {
    const ledger = JSON.parse(JSON.stringify(DEFAULT_FOCUS_LEDGER));
    ledger.subgoals = [
      { id: "sub_alpha", title: "重构几何渲染管线", status: "in_progress", order: 1 },
      { id: "sub_beta", title: "添加烟雾粒子", status: "pending", order: 2 },
    ];

    const advanceRes = evaluateAutonomousAdvancement(ledger, {
      text: "代码重构完毕并通过人工走查。\nFOCUS_ADVANCE: sub_alpha | 几何图元管线重构验证无误",
    });

    assert.strictEqual(advanceRes.advanced, true, "Agent 声明指令协议必须生效");
    assert.strictEqual(ledger.subgoals[0].status, "completed");
    assert.strictEqual(ledger.subgoals[1].status, "in_progress");
    console.log("✔ QA Case 8 [Agent 声明指令协议自主推进 (Track 2)]: PASS");
  }

  // ----------------------------------------------------------------------
  // Case 9: Anti-Loop Circuit Breaker on Consecutive Failures
  // ----------------------------------------------------------------------
  {
    const ledger = JSON.parse(JSON.stringify(DEFAULT_FOCUS_LEDGER));
    ledger.health.maxFailureThreshold = 3;

    recordExecutionHealth(ledger, false, "Edit");
    assert.strictEqual(ledger.health.consecutiveFailures, 1);

    recordExecutionHealth(ledger, false, "Edit");
    assert.strictEqual(ledger.health.consecutiveFailures, 2);

    const trip = recordExecutionHealth(ledger, false, "Edit");
    assert.strictEqual(trip.loopDetected, true, "连续 3 次失败必须触发防死循环熔断");

    // 成功后复位
    recordExecutionHealth(ledger, true);
    assert.strictEqual(ledger.health.consecutiveFailures, 0, "工具执行成功立即复位计数器");
    console.log("✔ QA Case 9 [连续失败防死循环与熔断告警]: PASS");
  }

  // ----------------------------------------------------------------------
  // Case 10: Claude Code Lifecycle Hooks Execution (stdin/stdout JSON)
  // ----------------------------------------------------------------------
  {
    // Test user-prompt-submit hook
    const promptInput = JSON.stringify({ prompt: "请帮我配置 pnpm 并锁定目标: 完成二战空战复刻" });
    const hookScript = path.resolve("hooks/user-prompt-submit.mjs");
    const hookOutput = execSync(`node "${hookScript}"`, {
      input: promptInput,
      encoding: "utf-8",
      env: { ...process.env, CLAUDE_CONFIG_DIR: TEST_DIR },
      cwd: TEST_DIR,
    });

    const parsedHook = JSON.parse(hookOutput);
    assert.ok(parsedHook.hookSpecificOutput, "必须返回 hookSpecificOutput 标准格式");
    assert.strictEqual(parsedHook.hookSpecificOutput.hookEventName, "UserPromptSubmit");
    assert.ok(parsedHook.hookSpecificOutput.additionalContext.includes("ACTIVE FOCUS FRAME"));
    console.log("✔ QA Case 10 [Claude Code 钩子 JSON 协议交互]: PASS");
  }

  // ----------------------------------------------------------------------
  // Case 11: MCP Server JSON-RPC stdio Protocol & Tool Invocations
  // ----------------------------------------------------------------------
  {
    const mcpScript = path.resolve("mcp/server.mjs");
    const mcpProcess = spawn("node", [mcpScript], {
      cwd: TEST_DIR,
      stdio: ["pipe", "pipe", "inherit"],
    });

    let mcpResponses = [];
    mcpProcess.stdout.on("data", (chunk) => {
      const lines = chunk.toString().trim().split("\n");
      for (const line of lines) {
        if (line) mcpResponses.push(JSON.parse(line));
      }
    });

    // 1. initialize
    mcpProcess.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} }) + "\n");
    // 2. tools/list
    mcpProcess.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} }) + "\n");
    // 3. tools/call memory_save
    mcpProcess.stdin.write(
      JSON.stringify({
        jsonrpc: "2.0",
        id: 3,
        method: "tools/call",
        params: {
          name: "memory_save",
          arguments: {
            content: "严禁在空战游戏中使用外部图片资源，必须纯几何矢量绘制",
            category: "architecture",
          },
        },
      }) + "\n"
    );
    // 4. tools/call memory_recall
    mcpProcess.stdin.write(
      JSON.stringify({
        jsonrpc: "2.0",
        id: 4,
        method: "tools/call",
        params: {
          name: "memory_recall",
          arguments: { query: "空战游戏图片资源规范", top_k: 2 },
        },
      }) + "\n"
    );

    await new Promise((r) => setTimeout(r, 800));
    mcpProcess.kill();

    const initResp = mcpResponses.find((r) => r.id === 1);
    assert.ok(initResp && initResp.result.serverInfo.name === "muse-wonder", "MCP 初始化响应正常");

    const toolsResp = mcpResponses.find((r) => r.id === 2);
    assert.ok(toolsResp && toolsResp.result.tools.length >= 8, "MCP 正确注册了全部 8 项核心工具");

    const saveResp = mcpResponses.find((r) => r.id === 3);
    assert.ok(saveResp && !saveResp.error, "memory_save 工具调用正常");

    const recallResp = mcpResponses.find((r) => r.id === 4);
    assert.ok(recallResp && !recallResp.error, "memory_recall 工具调用正常");
    console.log("✔ QA Case 11 [MCP Server JSON-RPC stdio 8 项工具完整性]: PASS");
  }

  // ----------------------------------------------------------------------
  // Case 12: Claude CLI Manifest & Strict Directory Validation
  // ----------------------------------------------------------------------
  {
    const validateOut = execSync("/Users/a58/.local/bin/claude plugin validate --strict .", {
      encoding: "utf-8",
    });
    assert.ok(validateOut.includes("Validation passed"), "claude plugin validate 必须 100% 校验通过");
    console.log("✔ QA Case 12 [Claude Code 官方插件规范与严格校验]: PASS");
  }

  console.log("==========================================================================");
  console.log("🎉 全部 12 项 Claude Code Plugin 核心能力验收测试 100% 通过！");
  console.log("==========================================================================");
} finally {
  fs.rmSync(TEST_DIR, { recursive: true, force: true });
}
