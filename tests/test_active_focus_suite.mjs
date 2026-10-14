import assert from "node:assert";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

import {
  loadFocusLedger,
  saveFocusLedger,
  buildFocusFrame,
  checkScopeViolation,
  evaluateAutonomousAdvancement,
  parseFocusDirectives,
  recordExecutionHealth,
  DEFAULT_FOCUS_LEDGER,
} from "../.pi/extensions/active-focus.ts";

async function runAllFocusTests() {
  console.log("=== 开始执行 Active Focus (主动专注) 严格 QA 测试 ===");

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "pi-focus-qa-"));
  const tmpLedgerPath = path.join(tmpDir, "active-focus.json");

  // -------------------------------------------------------------
  // QA Case 1: 强目标锚定与工作帧生成测试
  // -------------------------------------------------------------
  const ledger = JSON.parse(JSON.stringify(DEFAULT_FOCUS_LEDGER));
  ledger.rootGoal = {
    id: "g1",
    description: "开发纵向卷轴射击游戏雷电第一关",
    status: "active",
    successCriteria: ["20/20 passed"],
  };
  ledger.subgoals = [
    {
      id: "s1",
      title: "三系弹药升级逻辑",
      status: "completed",
      order: 1,
      turnsSpent: 2,
    },
    {
      id: "s2",
      title: "实现敌机6种轨迹与弹幕",
      status: "in_progress",
      order: 2,
      turnsSpent: 3,
      criteria: { matchPattern: "t_enemy_bullet_patterns", expectedExitCode: 0 },
    },
  ];
  ledger.scopeGuard.forbiddenPatterns = ["package.json", "control_no_memory/**"];

  const frame = buildFocusFrame(ledger);
  assert.ok(frame.includes("ACTIVE FOCUS FRAME"), "必须包含专注框架前缀");
  assert.ok(frame.includes("开发纵向卷轴射击游戏雷电第一关"), "必须置顶根目标");
  assert.ok(frame.includes("实现敌机6种轨迹与弹幕"), "必须明确当前攻坚子任务");
  assert.ok(frame.includes("滞留预警"), "停留 >= 3 轮必须输出滞留预警提示");
  assert.ok(frame.includes("control_no_memory/**"), "必须声明防越界禁改模式");
  console.log("✔ QA Case 1 [目标锚定与工作帧生成]: PASS");

  // -------------------------------------------------------------
  // QA Case 2: 作用域守卫（Scope Guard）拦截测试
  // -------------------------------------------------------------
  ledger.scopeGuard = {
    enabled: true,
    allowedPatterns: ["experiments/treatment/**", "tests/**"],
    forbiddenPatterns: ["package.json", "experiments/control/**"],
    strictEnforce: true,
  };

  // 允许的白名单修改
  const checkAllowed = checkScopeViolation(ledger, "experiments/treatment/raiden_game.py");
  assert.strictEqual(checkAllowed.violated, false, "白名单内文件应该放行");

  // 黑名单违规修改
  const checkForbidden = checkScopeViolation(ledger, "package.json");
  assert.strictEqual(checkForbidden.violated, true, "黑名单文件必须拦截");
  assert.ok(checkForbidden.reason.includes("命中禁改模式"), "必须说明拦截原因");

  // 超出白名单修改
  const checkOutOfScope = checkScopeViolation(ledger, "src/other_service.py");
  assert.strictEqual(checkOutOfScope.violated, true, "超出白名单范围必须拦截");
  console.log("✔ QA Case 2 [作用域白名单与黑名单拦截]: PASS");

  // -------------------------------------------------------------
  // QA Case 3: 确定性自检验收与自主目标推进 (Track 1)
  // -------------------------------------------------------------
  const advanceLedger = JSON.parse(JSON.stringify(DEFAULT_FOCUS_LEDGER));
  advanceLedger.subgoals = [
    {
      id: "sub_a",
      title: "玩家基础控制与生命数",
      status: "in_progress",
      order: 1,
      turnsSpent: 1,
      criteria: {
        matchPattern: "SELFTEST: OK",
        expectedExitCode: 0,
      },
    },
    {
      id: "sub_b",
      title: "敌机与弹幕系统",
      status: "pending",
      order: 2,
      turnsSpent: 0,
    },
  ];

  // 模拟测试未通过或报错
  const resFail = evaluateAutonomousAdvancement(advanceLedger, {
    output: "AssertionError: weapon level mismatched",
    exitCode: 1,
  });
  assert.strictEqual(resFail.advanced, false, "测试未通过绝不能推进目标");
  assert.strictEqual(advanceLedger.subgoals[0].status, "in_progress", "状态必须保持 in_progress");

  // 模拟测试自检通过 (输出包含 SELFTEST: OK 且退出码为 0)
  const resPass = evaluateAutonomousAdvancement(advanceLedger, {
    output: "All 20 checks passed\nSELFTEST: OK",
    exitCode: 0,
  });
  assert.strictEqual(resPass.advanced, true, "自检通过必须自动推进目标");
  assert.strictEqual(resPass.completedId, "sub_a", "应完成 sub_a");
  assert.strictEqual(resPass.nextId, "sub_b", "应激活 sub_b");
  assert.strictEqual(advanceLedger.subgoals[0].status, "completed", "原任务状态必须转为 completed");
  assert.strictEqual(advanceLedger.subgoals[1].status, "in_progress", "下一任务必须自动置为 in_progress");
  console.log("✔ QA Case 3 [确定性证据自主验收与状态推进]: PASS");

  // -------------------------------------------------------------
  // QA Case 4: Agent 自主指令推进协议 (Track 2: FOCUS_ADVANCE)
  // -------------------------------------------------------------
  const directiveLedger = JSON.parse(JSON.stringify(DEFAULT_FOCUS_LEDGER));
  directiveLedger.subgoals = [
    {
      id: "refactor_clean",
      title: "重构游戏视差滚动与数学库计算",
      status: "in_progress",
      order: 1,
      turnsSpent: 1,
    },
    {
      id: "next_boss",
      title: "Boss 多阶段设计",
      status: "pending",
      order: 2,
      turnsSpent: 0,
    },
  ];

  const agentText = "代码已完成精简，重构验证完毕。\nFOCUS_ADVANCE: refactor_clean | 视差滚动平滑无锯齿，已消除外部依赖";
  const agentRes = evaluateAutonomousAdvancement(directiveLedger, { text: agentText });
  assert.strictEqual(agentRes.advanced, true, "必须识别 FOCUS_ADVANCE 指令");
  assert.strictEqual(directiveLedger.subgoals[0].status, "completed", "目标应转为完成");
  assert.strictEqual(directiveLedger.subgoals[1].status, "in_progress", "下一阶段应自动启动");
  assert.ok(directiveLedger.subgoals[0].completionEvidence.includes("视差滚动平滑"), "必须留存完成证据");
  console.log("✔ QA Case 4 [Agent 主动声明指令协议自主推进]: PASS");

  // -------------------------------------------------------------
  // QA Case 5: 连续失败防死循环与熔断预警
  // -------------------------------------------------------------
  const healthLedger = JSON.parse(JSON.stringify(DEFAULT_FOCUS_LEDGER));
  healthLedger.health.maxFailureThreshold = 3;

  assert.strictEqual(recordExecutionHealth(healthLedger, false, "run_command").loopDetected, false);
  assert.strictEqual(healthLedger.health.consecutiveFailures, 1);

  assert.strictEqual(recordExecutionHealth(healthLedger, false, "run_command").loopDetected, false);
  assert.strictEqual(healthLedger.health.consecutiveFailures, 2);

  // 第 3 次失败触发熔断报警
  const alertRes = recordExecutionHealth(healthLedger, false, "run_command");
  assert.strictEqual(alertRes.loopDetected, true, "达到阈值必须触发死循环报警");
  assert.strictEqual(healthLedger.health.consecutiveFailures, 3);

  // 成功后必须清零
  recordExecutionHealth(healthLedger, true);
  assert.strictEqual(healthLedger.health.consecutiveFailures, 0, "成功执行必须重置失败计数");
  console.log("✔ QA Case 5 [连续失败防死循环与熔断重置]: PASS");

  // -------------------------------------------------------------
  // QA Case 6: 自然语言口语化控制与零配置持久化
  // -------------------------------------------------------------
  const nlLedger = JSON.parse(JSON.stringify(DEFAULT_FOCUS_LEDGER));
  nlLedger.subgoals = [
    { id: "1", title: "任务一", status: "in_progress", order: 1, turnsSpent: 0 },
    { id: "2", title: "任务二", status: "pending", order: 2, turnsSpent: 0 },
  ];

  parseFocusDirectives("请帮我设定目标：复刻完整雷电街机第一关", nlLedger);
  assert.strictEqual(nlLedger.rootGoal.description, "复刻完整雷电街机第一关");

  parseFocusDirectives("只允许修改：experiments/treatment, tests", nlLedger);
  assert.deepStrictEqual(nlLedger.scopeGuard.allowedPatterns, ["experiments/treatment", "tests"]);

  parseFocusDirectives("推进到下一个子任务", nlLedger);
  assert.strictEqual(nlLedger.subgoals[0].status, "completed");
  assert.strictEqual(nlLedger.subgoals[1].status, "in_progress");

  saveFocusLedger(tmpLedgerPath, nlLedger);
  const reloaded = loadFocusLedger(tmpLedgerPath);
  assert.strictEqual(reloaded.rootGoal.description, "复刻完整雷电街机第一关");
  assert.strictEqual(reloaded.subgoals[1].status, "in_progress");
  console.log("✔ QA Case 6 [自然语言口语化指令与零配置持久化]: PASS");

  // 清理临时文件
  fs.rmSync(tmpDir, { recursive: true, force: true });

  console.log("\n=========================================");
  console.log("🎉 全部 6 项 Active Focus 验收测试 100% 通过！");
  console.log("=========================================");
}

runAllFocusTests().catch((err) => {
  console.error("Focus QA 测试失败:", err);
  process.exit(1);
});
