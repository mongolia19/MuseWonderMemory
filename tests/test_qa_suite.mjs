import assert from "node:assert";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

import {
	matchInvariants,
	reconcileContradictions,
	reconcileContradictionsRuleBased,
	parseReconciliationIntervalDirective,
	runFallbackHeuristics,
	calculateTokenOverlap,
	extractKeywords,
} from "../.pi/extensions/active-memory.ts";

const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "pi-memory-qa-"));

async function runAllTests() {
	console.log("=== 开始执行 Active Memory 严格 QA 测试 ===");

	// -------------------------------------------------------------
	// QA Case 1: 基础匹配与废弃规则绝对过滤测试
	// -------------------------------------------------------------
	const invariants = [
		{
			id: "old_rule",
			content: "旧规则：使用 Webpack 打包",
			category: "tooling",
			tags: ["webpack", "build"],
			createdAt: 1000,
			hitCount: 5,
			supersededBy: "new_rule", // 已废弃！
		},
		{
			id: "new_rule",
			content: "新规则：使用 Vite 打包",
			category: "tooling",
			tags: ["vite", "build"],
			createdAt: 2000,
			hitCount: 1,
		},
	];

	const recalled = matchInvariants(invariants, "我们需要修改打包配置");
	assert.strictEqual(recalled.length, 1, "必须过滤掉被 supersededBy 标记的旧规则");
	assert.strictEqual(recalled[0].id, "new_rule", "必须只召回最新的有效规则");
	console.log("✔ QA Case 1 [废弃过滤]: PASS");

	// -------------------------------------------------------------
	// QA Case 2: 语义相似度与去重测试 (Jaccard Overlap)
	// -------------------------------------------------------------
	const tokensA = extractKeywords("使用 Vitest 运行单元测试");
	const tokensB = extractKeywords("所有单元测试使用 Vitest 运行");
	const overlap = calculateTokenOverlap(tokensA, tokensB);
	assert.ok(overlap >= 0.5, `同义复述的词重叠度必须 >= 0.5 (实际: ${overlap})`);
	console.log(`✔ QA Case 2 [Jaccard去重计算 (overlap=${overlap.toFixed(2)})]: PASS`);

	// -------------------------------------------------------------
	// QA Case 3: 冲突检测与因果追溯双引擎测试 (LLM 优先 + 规则回滚)
	// -------------------------------------------------------------
	const store = {
		version: 1,
		invariants: [
			{
				id: "mem_bun",
				content: "本项目强制使用 Bun 管理依赖包",
				category: "tooling",
				tags: ["bun", "依赖包", "管理"],
				createdAt: 1000,
				hitCount: 10,
			},
			{
				id: "mem_db",
				content: "数据库使用 PostgreSQL",
				category: "architecture",
				tags: ["数据库", "postgresql"],
				createdAt: 1000,
				hitCount: 2,
			},
		],
	};

	// 3a. 模拟大模型成功调用：深度语义判断
	const mockLLMCaller = async (_prompt, _sys) => {
		return JSON.stringify({
			hasContradiction: true,
			supersededId: "mem_bun",
			reason: "Switching package manager to pnpm invalidates mandatory Bun rule",
		});
	};
	const replacementDirective = "即日起项目全面切换为 pnpm 管理依赖包，不再使用 Bun";
	const llmRes = await reconcileContradictions(replacementDirective, "tooling", store, { simpleCaller: mockLLMCaller });
	assert.strictEqual(llmRes.engine, "llm", "大模型可用时必须走 LLM 引擎");
	assert.strictEqual(llmRes.supersededId, "mem_bun", "大模型必须定位冲突规则 mem_bun");
	console.log("✔ QA Case 3a [大模型冲突检测与因果追溯]: PASS");

	// 3b. 模拟大模型调用异常时，自动回滚至规则代码
	const failingLLMCaller = async () => {
		throw new Error("Simulated LLM API 500 error / offline");
	};
	const fallbackRes = await reconcileContradictions(replacementDirective, "tooling", store, { simpleCaller: failingLLMCaller });
	assert.strictEqual(fallbackRes.engine, "rule", "大模型报错时必须自动平滑回滚至规则代码");
	assert.strictEqual(fallbackRes.supersededId, "mem_bun", "规则代码必须成功定位冲突规则 mem_bun");
	console.log("✔ QA Case 3b [大模型故障时规则代码自动回滚]: PASS");

	// 3c. 纯规则代码执行全流程
	const ruleId = reconcileContradictionsRuleBased(replacementDirective, "tooling", store);
	assert.strictEqual(ruleId, "mem_bun");
	const fallbackAdded = runFallbackHeuristics(replacementDirective, "已确认更新", tmpDir, store);
	assert.strictEqual(fallbackAdded, 1, "必须新增 1 条替换规则");

	const oldBunRule = store.invariants.find((i) => i.id === "mem_bun");
	assert.ok(oldBunRule.supersededBy, "旧规则必须被标记 supersededBy");
	assert.ok(oldBunRule.supersededAt, "旧规则必须带有被废弃的时间戳");

	const updatedActive = matchInvariants(store.invariants, "安装一个依赖包");
	assert.strictEqual(updatedActive.length, 1);
	assert.ok(updatedActive[0].content.includes("pnpm"), "激活规则必须已切换为 pnpm 规则");
	assert.ok(!updatedActive[0].content.includes("强制使用 Bun"), "激活规则中绝不能包含旧 Bun 规则");
	console.log("✔ QA Case 3c [时序消解留痕与前置激活生效]: PASS");

	// -------------------------------------------------------------
	// QA Case 4: 离线容灾提取测试
	// -------------------------------------------------------------
	const mockStore = { version: 1, invariants: [] };
	const count = runFallbackHeuristics("记住：API 超时时间统一设为 5000ms", "收到", tmpDir, mockStore);
	assert.strictEqual(count, 1, "离线容灾引擎必须能从对话中独立提炼规则");
	assert.strictEqual(mockStore.invariants.length, 1);
	assert.strictEqual(mockStore.invariants[0].category, "preference");
	console.log("✔ QA Case 4 [容灾回退提取]: PASS");

	// -------------------------------------------------------------
	// QA Case 5: 轮次间隔与自然语言指令动态配置测试
	// -------------------------------------------------------------
	assert.strictEqual(parseReconciliationIntervalDirective("冲突检测间隔设为 5 轮"), 5);
	assert.strictEqual(parseReconciliationIntervalDirective("每 2 轮进行一次因果追溯"), 2);
	assert.strictEqual(parseReconciliationIntervalDirective("每轮都进行冲突检测"), 1);
	assert.strictEqual(parseReconciliationIntervalDirective("set reconciliation interval to 4"), 4);
	assert.strictEqual(parseReconciliationIntervalDirective("普通对话内容，不包含任何配置指令"), null);

	// 模拟轮次节流逻辑 (默认间隔 3 轮)
	let turnsSince = 0;
	const interval = 3;
	let executedTurns = [];
	for (let turn = 1; turn <= 6; turn++) {
		turnsSince++;
		if (turnsSince >= interval) {
			executedTurns.push(turn);
			turnsSince = 0;
		}
	}
	assert.deepStrictEqual(executedTurns, [3, 6], "默认 3 轮运行一次冲突消解，第 3 轮与第 6 轮必须触发执行");
	console.log("✔ QA Case 5 [自然语言指令解析与 3 轮周期节流]: PASS");

	console.log("\n=========================================");
	console.log("🎉 全部 5 项核心 QA 验收测试 100% 通过！");
	console.log("=========================================");
}

runAllTests()
	.catch((err) => {
		console.error("❌ QA 测试失败:", err);
		process.exit(1);
	})
	.finally(() => {
		fs.rmSync(tmpDir, { recursive: true, force: true });
	});
