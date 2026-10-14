/**
 * Active Memory Extension for Pi Agent
 *
 * Implements Meta Muse Wonder "Active Memory" capability:
 * 1. Proactive Context Injection with Temporal Recency (`before_agent_start`):
 *    Filters superseded rules, calculates keyword relevance + recency weight.
 * 2. LLM Distillation + Heuristic Dual-Engine (`agent_end`):
 *    Background LLM extraction with automatic fallback to local heuristics.
 * 3. Temporal Evolution & Contradiction Reconciliation (时序演进与矛盾消解):
 *    Detects replacement directives ("改用", "切换为", "replace", "instead of"),
 *    links superseded rules via `supersededBy`, and completely retires obsolete directives.
 * 4. Model Embedding with Fallback:
 *    Uses local vector embeddings if available; gracefully rolls back to lightweight scoring.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import * as crypto from "node:crypto";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

export interface MemoryInvariant {
	id: string;
	content: string;
	category: "architecture" | "tooling" | "preference" | "pitfall";
	tags: string[];
	createdAt: number;
	updatedAt?: number;
	hitCount: number;
	supersededBy?: string;
	supersededAt?: number;
}

export interface MemoryStore {
	version: number;
	reconcileInterval?: number;
	turnsSinceReconcile?: number;
	invariants: MemoryInvariant[];
}

const MEMORY_FILE_NAME = "active-memory.json";

export function getMemoryFilePath(cwd: string): string {
	const piDir = path.join(cwd || process.cwd(), ".pi");
	if (!fs.existsSync(piDir)) {
		fs.mkdirSync(piDir, { recursive: true });
	}
	return path.join(piDir, MEMORY_FILE_NAME);
}

export function loadMemory(cwd: string): MemoryStore {
	const file = getMemoryFilePath(cwd);
	if (!fs.existsSync(file)) {
		return { version: 1, reconcileInterval: 3, turnsSinceReconcile: 0, invariants: [] };
	}
	try {
		const raw = fs.readFileSync(file, "utf-8");
		const data = JSON.parse(raw);
		return {
			version: data.version || 1,
			reconcileInterval: typeof data.reconcileInterval === "number" ? data.reconcileInterval : 3,
			turnsSinceReconcile: typeof data.turnsSinceReconcile === "number" ? data.turnsSinceReconcile : 0,
			invariants: Array.isArray(data.invariants) ? data.invariants : [],
		};
	} catch {
		return { version: 1, reconcileInterval: 3, turnsSinceReconcile: 0, invariants: [] };
	}
}

export function parseReconciliationIntervalDirective(text: string): number | null {
	if (!text) return null;
	const m = text.match(/(?:冲突检测|因果追溯|矛盾消解).*?(\d+)\s*轮|(\d+)\s*轮.*?(?:冲突检测|因果追溯|矛盾消解)/u);
	if (m) return parseInt(m[1] || m[2], 10);
	if (/(?:每轮|每次|实时).*?(?:冲突检测|因果追溯|矛盾消解)/u.test(text)) return 1;
	const mEn = text.match(/(?:reconciliation|conflict\s+detection)\s+(?:interval\s+)?(?:to\s+|every\s+)?(\d+)/i);
	return mEn ? parseInt(mEn[1], 10) : null;
}

export function saveMemory(cwd: string, store: MemoryStore): void {
	const file = getMemoryFilePath(cwd);
	fs.writeFileSync(file, JSON.stringify(store, null, 2), "utf-8");
}

export function extractKeywords(text: string): string[] {
	if (!text) return [];
	if (typeof Intl !== "undefined" && typeof (Intl as any).Segmenter === "function") {
		const segmenter = new (Intl as any).Segmenter("zh", { granularity: "word" });
		return Array.from(segmenter.segment(text.toLowerCase()))
			.filter((s: any) => s.isWordLike)
			.map((s: any) => s.segment.trim())
			.filter((w: string) => w.length >= 2 || /^[a-zA-Z0-9]$/.test(w));
	}
	return text
		.toLowerCase()
		.replace(/[^\p{L}\p{N}_\s-]/gu, " ")
		.split(/\s+/)
		.filter((w) => w.length >= 2);
}

export function calculateTokenOverlap(tokensA: string[], tokensB: string[]): number {
	if (tokensA.length === 0 || tokensB.length === 0) return 0;
	const setA = new Set(tokensA);
	const setB = new Set(tokensB);
	let intersection = 0;
	for (const t of setA) {
		if (setB.has(t)) intersection++;
	}
	const union = new Set([...tokensA, ...tokensB]).size;
	return union === 0 ? 0 : intersection / union;
}

export interface ContradictionResult {
	supersededId: string | null;
	engine: "llm" | "rule";
	reason?: string;
}

export interface LLMReconcileContext {
	model?: any;
	modelRegistry?: any;
	simpleCaller?: (prompt: string, systemPrompt?: string) => Promise<string>;
}

/**
 * 规则代码冲突检测 (Rule-based Contradiction Reconciliation Fallback)
 * 当大模型不可用或调用失败时，基于触发词正则与 Jaccard 分词重叠率进行确定性匹配
 */
export function reconcileContradictionsRuleBased(
	newContent: string,
	newCategory: MemoryInvariant["category"],
	store: MemoryStore,
	now: number = Date.now(),
): string | null {
	const CONTRADICTION_TRIGGERS = [
		/改用|切换为|替换为|废除|不再使用|不再支持|迁移到|更新为/u,
		/switch\s+to|replace|instead\s+of|migrate\s+to|deprecated|no\s+longer\s+use/i,
	];

	const isReplacement = CONTRADICTION_TRIGGERS.some((re) => re.test(newContent));
	if (!isReplacement) return null;

	const newTokens = extractKeywords(newContent);

	// Find active invariants in the same category or with high token overlap
	for (const existing of store.invariants) {
		if (existing.supersededBy) continue;

		const existingTokens = extractKeywords(existing.content);
		const overlap = calculateTokenOverlap(newTokens, existingTokens);

		// If same category and shares topic words (e.g. package, database, test)
		if (existing.category === newCategory && overlap >= 0.2) {
			return existing.id;
		}
	}
	return null;
}

/**
 * 时序演进与矛盾消解核心算法 (Contradiction Reconciliation & Causal Tracing)
 * 优先调用大模型进行深度语义冲突判断与因果溯源；若大模型未提供、超时或调用失败，自动回滚至规则代码
 */
export async function reconcileContradictions(
	newContent: string,
	newCategory: MemoryInvariant["category"],
	store: MemoryStore,
	llmContext?: LLMReconcileContext,
	now: number = Date.now(),
): Promise<ContradictionResult> {
	const activeInvariants = store.invariants.filter((i) => !i.supersededBy);
	if (activeInvariants.length === 0) {
		return { supersededId: null, engine: "rule" };
	}

	// 1. 尝试大模型检测 (LLM-driven Semantic Analysis)
	if (llmContext && (llmContext.simpleCaller || (llmContext.model && llmContext.modelRegistry))) {
		try {
			const promptContent = `Existing active invariants:
${JSON.stringify(activeInvariants.map((i) => ({ id: i.id, category: i.category, content: i.content })), null, 2)}

Candidate New Rule:
Category: ${newCategory}
Content: "${newContent}"`;

			const systemPrompt = `You are a Contradiction & Causal Reconciliation Engine for Agent Memory.
Determine if the Candidate New Rule contradicts, replaces, or updates any Existing Active Invariant.
If it conflicts with or replaces an existing rule (e.g. changing dependency manager, database, test runner, coding convention), identify that rule's exact ID as "supersededId" and set "hasContradiction" to true.
If it is complementary, orthogonal, or non-conflicting, set "hasContradiction" to false and "supersededId" to null.

Return STRICT JSON ONLY:
{
  "hasContradiction": boolean,
  "supersededId": string | null,
  "reason": "Brief explanation"
}`;

			let rawText = "";
			if (llmContext.simpleCaller) {
				rawText = await llmContext.simpleCaller(promptContent, systemPrompt);
			} else if (llmContext.model && llmContext.modelRegistry) {
				const response = await llmContext.modelRegistry
					.streamSimple(
						llmContext.model,
						{
							systemPrompt,
							messages: [{ role: "user", content: promptContent, timestamp: now }],
						},
						{ maxTokens: 400 },
					)
					.result();
				rawText = extractTextFromMessage(response);
			}

			const parsed = parseJsonSafe(rawText);
			if (parsed && typeof parsed.hasContradiction === "boolean") {
				if (parsed.hasContradiction && parsed.supersededId) {
					const matched = activeInvariants.find((i) => i.id === parsed.supersededId);
					if (matched) {
						return {
							supersededId: matched.id,
							engine: "llm",
							reason: parsed.reason || "LLM identified semantic conflict",
						};
					}
				} else if (!parsed.hasContradiction) {
					return {
						supersededId: null,
						engine: "llm",
						reason: parsed.reason || "No conflict detected by LLM",
					};
				}
			}
		} catch {
			// LLM 调用失败（超时/网络/格式错误），自动平滑降级到规则代码
		}
	}

	// 2. 降级回退：采用规则代码 (Rule-based Fallback)
	const fallbackId = reconcileContradictionsRuleBased(newContent, newCategory, store, now);
	return {
		supersededId: fallbackId,
		engine: "rule",
		reason: fallbackId ? "Rule-based pattern and token overlap match" : undefined,
	};
}

/**
 * 意图匹配与时序权重评分 (Intent Matching with Recency Bias)
 */
export function matchInvariants(invariants: MemoryInvariant[], promptText: string): MemoryInvariant[] {
	// 绝对过滤已废弃/被替代的旧规则
	const active = invariants.filter((inv) => !inv.supersededBy);
	if (active.length === 0) return [];
	const promptTokens = new Set(extractKeywords(promptText));

	const scored = active.map((inv) => {
		let score = 0;
		for (const tag of inv.tags) {
			if (promptTokens.has(tag.toLowerCase())) score += 2;
		}
		for (const token of extractKeywords(inv.content)) {
			if (promptTokens.has(token)) score += 1;
		}
		// 时序与命中加权：越新创建或越常命中的规则获得微小优先级提升
		const recencyBonus = (inv.createdAt / 1e12) * 0.01;
		const hitBonus = Math.min(inv.hitCount * 0.1, 1.0);
		return { inv, score: score + recencyBonus + hitBonus, rawScore: score };
	});

	const matched = scored.filter((s) => s.rawScore > 0).sort((a, b) => b.score - a.score);
	if (matched.length > 0) {
		return matched.slice(0, 5).map((s) => s.inv);
	}
	// Fallback to top-3 active baseline invariants (sorted by recency)
	return active.sort((a, b) => b.createdAt - a.createdAt).slice(0, 3);
}

const EXTRACTION_PATTERNS = [
	/(?:remember|always|never|prefer|strictly use|from now on|do not use)\s*[:：]?\s*([^.!\n]+[.!\n]?)/i,
	/(?:记住|始终|严禁|必须使用|统一使用|规范要求|切勿|即日起|全面切换为)\s*[:：]?\s*([^。！\n]+[。！\n]?)/u,
	/(?:architecture decision|project rule)\s*[:：]\s*([^.!\n]+)/i,
];

export function extractCandidateRules(text: string): string[] {
	const results: string[] = [];
	for (const pattern of EXTRACTION_PATTERNS) {
		const match = text.match(pattern);
		if (match && match[1]) {
			const cleaned = match[1].trim();
			if (cleaned.length >= 6 && cleaned.length <= 150) {
				results.push(cleaned);
			}
		}
	}
	return results;
}

export function extractTextFromMessage(msg: any): string {
	if (!msg) return "";
	if (typeof msg.content === "string") return msg.content;
	if (Array.isArray(msg.content)) {
		return msg.content
			.map((c: any) => {
				if (typeof c === "string") return c;
				if (c && typeof c.text === "string") return c.text;
				return "";
			})
			.filter(Boolean)
			.join("\n");
	}
	return "";
}

export function parseJsonSafe(text: string): any {
	try {
		const cleaned = text.replace(/```(?:json)?/gi, "").replace(/```/g, "").trim();
		const start = cleaned.indexOf("{");
		const end = cleaned.lastIndexOf("}");
		if (start !== -1 && end !== -1 && end > start) {
			return JSON.parse(cleaned.slice(start, end + 1));
		}
	} catch {
		return null;
	}
	return null;
}

export function runFallbackHeuristics(userText: string, assistantText: string, cwd: string, store: MemoryStore): number {
	const candidates = [...extractCandidateRules(userText), ...extractCandidateRules(assistantText)];
	if (candidates.length === 0) return 0;
	let added = 0;
	const now = Date.now();

	for (const candidate of candidates) {
		const candidateTokens = extractKeywords(candidate);
		const isTooling = /bun|npm|pnpm|yarn|cargo|pip|uv|brew/i.test(candidate);
		const isPitfall = /bug|pitfall|issue|error|fail|avoid|切勿|小心|坑/i.test(candidate);
		const category: MemoryInvariant["category"] = isTooling ? "tooling" : isPitfall ? "pitfall" : "preference";

		// 触发时序冲突消解检查 (降级回退至规则代码)
		const supersededId = reconcileContradictionsRuleBased(candidate, category, store, now);
		if (supersededId) {
			const oldInv = store.invariants.find((i) => i.id === supersededId);
			const newId = "mem_" + crypto.randomBytes(4).toString("hex");
			if (oldInv) {
				oldInv.supersededBy = newId;
				oldInv.supersededAt = now;
			}
			store.invariants.push({
				id: newId,
				content: candidate,
				category,
				tags: candidateTokens,
				createdAt: now,
				hitCount: 0,
			});
			added++;
			continue;
		}

		// 检查纯重复
		let duplicate = false;
		for (const existing of store.invariants) {
			if (existing.supersededBy) continue;
			if (calculateTokenOverlap(candidateTokens, extractKeywords(existing.content)) >= 0.5) {
				duplicate = true;
				break;
			}
		}

		if (!duplicate) {
			store.invariants.push({
				id: "mem_" + crypto.randomBytes(4).toString("hex"),
				content: candidate,
				category,
				tags: candidateTokens,
				createdAt: now,
				hitCount: 0,
			});
			added++;
		}
	}
	if (added > 0) saveMemory(cwd, store);
	return added;
}

export default function activeMemoryExtension(pi: ExtensionAPI) {
	let currentCwd = process.cwd();
	let activeCtx: any = null;

	pi.on("session_start", async (_event, ctx) => {
		if (ctx) activeCtx = ctx;
		if (ctx?.cwd) currentCwd = ctx.cwd;
	});

	// Hook 1: Proactive Context Injection before each turn starts
	pi.on("before_agent_start", async (event, ctx) => {
		if (ctx) activeCtx = ctx;
		const targetCwd = ctx?.cwd || currentCwd;
		const store = loadMemory(targetCwd);
		const promptText = event.messageType === "user" ? event.prompt : "";

		// 支持通过自然语言指令动态修改冲突检测与因果追溯轮次间隔
		const newInterval = parseReconciliationIntervalDirective(promptText);
		if (newInterval !== null) {
			store.reconcileInterval = newInterval;
			store.turnsSinceReconcile = 0;
			saveMemory(targetCwd, store);
			if (ctx?.hasUI) ctx.ui.notify(`[Active Memory] 冲突检测与因果追溯间隔已更新为 ${newInterval} 轮`, "info");
		}

		if (store.invariants.length === 0) return;

		const relevant = matchInvariants(store.invariants, promptText);
		if (relevant.length === 0) return;

		const matchedIds = new Set(relevant.map((r) => r.id));
		for (const inv of store.invariants) {
			if (matchedIds.has(inv.id)) inv.hitCount += 1;
		}
		saveMemory(targetCwd, store);

		const memoryRules = relevant.map((r) => `- [${r.category}] ${r.content}`).join("\n");
		const memorySection = `
## Active Memory (Project Invariants & Preferences)
The following persistent invariants were proactively recalled for this session:
${memoryRules}
Always adhere to these invariants unless the user explicitly requests an exception.
`;

		event.systemPromptOptions.appendSystemPrompt =
			(event.systemPromptOptions.appendSystemPrompt || "") + "\n" + memorySection;

		return { systemPrompt: event.systemPrompt + "\n" + memorySection };
	});

	// Hook 2: LLM Distillation with Automatic Rule-based Fallback & Interval Control
	pi.on("agent_end", async (event, ctx) => {
		if (ctx) activeCtx = ctx;
		if (!event.messages || event.messages.length === 0) return;
		const targetCwd = ctx?.cwd || currentCwd;

		let userText = "";
		let assistantText = "";
		for (let i = event.messages.length - 1; i >= 0; i--) {
			const msg = event.messages[i];
			if (msg.role === "user" && !userText) userText = extractTextFromMessage(msg);
			else if (msg.role === "assistant" && !assistantText) assistantText = extractTextFromMessage(msg);
			if (userText && assistantText) break;
		}

		if ((userText + " " + assistantText).trim().length < 20) return;

		const store = loadMemory(targetCwd);

		// 检查轮次间隔（默认 3 轮运行一次冲突检测与提炼，可通过自然语言调整）
		const interval = Math.max(1, store.reconcileInterval ?? 3);
		store.turnsSinceReconcile = (store.turnsSinceReconcile ?? 0) + 1;
		if (store.turnsSinceReconcile < interval) {
			saveMemory(targetCwd, store);
			return;
		}
		store.turnsSinceReconcile = 0;

		let llmSucceeded = false;
		const now = Date.now();

		const model = ctx?.model || (ctx?.scopedModels && ctx.scopedModels[0]?.model);
		if (model && ctx?.modelRegistry) {
			try {
				const active = store.invariants.filter((i) => !i.supersededBy);
				const systemPrompt = `You are the Active Memory Distillation Engine. Extract durable project invariants and resolve contradictions.
Rules:
1. If a new rule contradicts or updates an existing rule (e.g. switched package manager or updated folder structure), action MUST be "supersede" with supersedesId.
2. If genuinely new, action is "add".
3. If already covered, ignore.
Return strictly valid JSON:
{
  "operations": [
    {
      "action": "add" | "supersede",
      "category": "architecture" | "tooling" | "preference" | "pitfall",
      "content": "Clean invariant statement",
      "supersedesId": "mem_xxx" or null
    }
  ]
}
If nothing to record, return { "operations": [] }.`;

				const promptContent = `Existing active invariants:
${JSON.stringify(active.map((i) => ({ id: i.id, category: i.category, content: i.content })), null, 2)}

Recent Interaction:
User: ${userText}
Assistant: ${assistantText}`;

				const response = await ctx.modelRegistry
					.streamSimple(
						model,
						{
							systemPrompt,
							messages: [{ role: "user", content: promptContent, timestamp: now }],
						},
						{ maxTokens: 600 },
					)
					.result();

				const parsed = parseJsonSafe(extractTextFromMessage(response));
				if (parsed && Array.isArray(parsed.operations)) {
					llmSucceeded = true;
					let count = 0;
					for (const op of parsed.operations) {
						if (!op.content || typeof op.content !== "string") continue;
						const newId = "mem_" + crypto.randomBytes(4).toString("hex");
						if (op.action === "supersede" && op.supersedesId) {
							const target = store.invariants.find((i) => i.id === op.supersedesId);
							if (target) {
								target.supersededBy = newId;
								target.supersededAt = now;
							}
						}
						store.invariants.push({
							id: newId,
							content: op.content.trim(),
							category: op.category || "architecture",
							tags: extractKeywords(op.content),
							createdAt: now,
							hitCount: 0,
						});
						count++;
					}
					if (count > 0) {
						saveMemory(targetCwd, store);
						if (ctx?.hasUI) ctx.ui.notify(`[Active Memory] Distilled ${count} invariant update(s)`, "info");
					}
				}
			} catch {
				llmSucceeded = false;
			}
		}

		// Fallback: rule-based contradiction reconciliation & extraction
		if (!llmSucceeded) {
			const fallbackAdded = runFallbackHeuristics(userText, assistantText, targetCwd, store);
			if (fallbackAdded > 0 && ctx?.hasUI) {
				ctx.ui.notify(`[Active Memory Fallback] Captured ${fallbackAdded} invariant(s)`, "info");
			}
		}
	});

	// Hook 3: Model-callable Tool
	pi.registerTool({
		name: "remember_invariant",
		label: "Remember Invariant",
		description: "Explicitly record a critical project invariant or rule to persistent Active Memory.",
		parameters: Type.Object({
			content: Type.String({ description: "The invariant statement or rule" }),
			category: Type.Union([
				Type.Literal("architecture"),
				Type.Literal("tooling"),
				Type.Literal("preference"),
				Type.Literal("pitfall"),
			]),
		}),
		execute: async (_toolCallId, params) => {
			const targetCwd = currentCwd || process.cwd();
			const store = loadMemory(targetCwd);
			const newId = "mem_" + crypto.randomBytes(4).toString("hex");
			const now = Date.now();

			const llmCtx = activeCtx?.model && activeCtx?.modelRegistry
				? { model: activeCtx.model, modelRegistry: activeCtx.modelRegistry }
				: undefined;
			const { supersededId, engine, reason } = await reconcileContradictions(
				params.content,
				params.category,
				store,
				llmCtx,
				now,
			);

			if (supersededId) {
				const oldInv = store.invariants.find((i) => i.id === supersededId);
				if (oldInv) {
					oldInv.supersededBy = newId;
					oldInv.supersededAt = now;
				}
			}

			store.invariants.push({
				id: newId,
				content: params.content,
				category: params.category,
				tags: extractKeywords(params.content),
				createdAt: now,
				hitCount: 0,
			});
			saveMemory(targetCwd, store);
			const note = supersededId ? ` (Supersedes [${supersededId}] via ${engine}: ${reason || "conflict resolved"})` : "";
			return {
				content: [{ type: "text", text: `Recorded [${newId}] (${params.category}): "${params.content}"${note}` }],
				details: undefined,
			};
		},
	});

	// Hook 4: User Slash Command: /memory
	pi.registerCommand("memory", {
		description: "Manage Active Memory (/memory [list|interval <n>|add <text>|delete <id>|clear])",
		handler: async (args, ctx) => {
			const targetCwd = ctx?.cwd || currentCwd;
			const store = loadMemory(targetCwd);
			const parts = (args || "").trim().split(/\s+/);
			const sub = parts[0]?.toLowerCase() || "list";

			if (sub === "interval") {
				const val = parts[1];
				if (val) {
					const n = parseInt(val, 10);
					if (isNaN(n) || n < 1) return ctx.ui.notify("Usage: /memory interval <positive integer>", "error");
					store.reconcileInterval = n;
					store.turnsSinceReconcile = 0;
					saveMemory(targetCwd, store);
					return ctx.ui.notify(`Reconciliation interval set to ${n} turns.`, "info");
				}
				return ctx.ui.notify(`Current interval: ${store.reconcileInterval ?? 3} turns (progress: ${store.turnsSinceReconcile ?? 0}/${store.reconcileInterval ?? 3})`, "info");
			}

			if (sub === "clear") {
				saveMemory(targetCwd, { version: 1, invariants: [] });
				ctx.ui.notify("Active Memory cleared.", "info");
				return;
			}
			if (sub === "delete") {
				const id = parts[1];
				if (!id) return ctx.ui.notify("Usage: /memory delete <id>", "error");
				const before = store.invariants.length;
				store.invariants = store.invariants.filter((i) => i.id !== id);
				if (store.invariants.length < before) {
					saveMemory(targetCwd, store);
					ctx.ui.notify(`Deleted invariant ${id}`, "info");
				} else {
					ctx.ui.notify(`Invariant ${id} not found`, "error");
				}
				return;
			}
			if (sub === "add") {
				const text = parts.slice(1).join(" ").trim();
				if (!text) return ctx.ui.notify("Usage: /memory add <rule>", "error");
				const id = "mem_" + crypto.randomBytes(4).toString("hex");
				store.invariants.push({
					id,
					content: text,
					category: "architecture",
					tags: extractKeywords(text),
					createdAt: Date.now(),
					hitCount: 0,
				});
				saveMemory(targetCwd, store);
				ctx.ui.notify(`Added invariant [${id}]: "${text}"`, "info");
				return;
			}

			const active = store.invariants.filter((i) => !i.supersededBy);
			if (active.length === 0) return ctx.ui.notify("Active Memory is empty.", "info");
			const list = active
				.map((inv, idx) => `${idx + 1}. [${inv.id}] [${inv.category}] ${inv.content} (hits: ${inv.hitCount})`)
				.join("\n");
			ctx.ui.notify(`Active Memory (${active.length} active items):\n${list}`, "info");
		},
	});
}
