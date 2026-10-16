/**
 * Active Memory Engine for Claude Code Plugin
 *
 * Implements Meta Muse Wonder Active Memory paradigm:
 * 1. Fast Invariant Recall (<10ms, System 1) with Jaccard token overlap & recency bonus.
 * 2. Strict Superseded Rule Filtering (100% exclusion of superseded directives).
 * 3. Dual-Engine Contradiction Reconciliation (System 2): LLM Causal Judge + Local Heuristic Fallback.
 * 4. Automatic Rule Distillation & Candidate Extraction.
 * 5. Natural Language Directives & Dynamic Interval Throttling.
 */

import * as fs from "node:fs";
import * as crypto from "node:crypto";
import {
  getMemoryFilePath,
  extractKeywords,
  calculateTokenOverlap,
  parseJsonSafe,
} from "./utils.mjs";

export function loadMemory(cwd = process.cwd()) {
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

export function saveMemory(cwd = process.cwd(), store) {
  const file = getMemoryFilePath(cwd);
  fs.writeFileSync(file, JSON.stringify(store, null, 2), "utf-8");
}

export function parseReconciliationIntervalDirective(text) {
  if (!text) return null;
  const m = text.match(/(?:冲突检测|因果追溯|矛盾消解).*?(\d+)\s*轮|(\d+)\s*轮.*?(?:冲突检测|因果追溯|矛盾消解)/u);
  if (m) return parseInt(m[1] || m[2], 10);
  if (/(?:每轮|每次|实时).*?(?:冲突检测|因果追溯|矛盾消解)/u.test(text)) return 1;
  const mEn = text.match(/(?:reconciliation|conflict\s+detection)\s+(?:interval\s+)?(?:to\s+|every\s+)?(\d+)/i);
  return mEn ? parseInt(mEn[1], 10) : null;
}

export function matchInvariants(invariants, promptText, topK = 5) {
  // 绝对过滤已废弃/被替代的旧规则
  const active = invariants.filter((inv) => !inv.supersededBy);
  if (active.length === 0) return [];
  const promptTokens = new Set(extractKeywords(promptText));

  const scored = active.map((inv) => {
    let score = 0;
    const invTags = Array.isArray(inv.tags) ? inv.tags : [];
    for (const tag of invTags) {
      if (promptTokens.has(tag.toLowerCase())) score += 2;
    }
    for (const token of extractKeywords(inv.content)) {
      if (promptTokens.has(token)) score += 1;
    }
    // 时序与命中加权：越新创建或越常命中的规则获得优先级提升
    const recencyBonus = (inv.createdAt / 1e12) * 0.01;
    const hitBonus = Math.min((inv.hitCount || 0) * 0.1, 1.0);
    return { inv, score: score + recencyBonus + hitBonus, rawScore: score };
  });

  const matched = scored.filter((s) => s.rawScore > 0).sort((a, b) => b.score - a.score);
  if (matched.length > 0) {
    const selected = matched.slice(0, topK).map((s) => s.inv);
    // 更新命中计数
    for (const item of selected) {
      item.hitCount = (item.hitCount || 0) + 1;
      item.lastHitAt = Date.now();
    }
    return selected;
  }
  // 回退：返回最新的 top-3 条活跃基础不变量
  return active.sort((a, b) => b.createdAt - a.createdAt).slice(0, Math.min(3, topK));
}

export function formatInvariantsFrame(invariants) {
  if (!invariants || invariants.length === 0) return "";
  const lines = [
    "=== [ACTIVE INVARIANTS: 活跃不变量约束 (前置注入)] ===",
    "以下为当前项目必须严格遵守的架构决策、工具链与编码规范不变量，违背将导致自检失败：",
  ];
  for (const inv of invariants) {
    const cat = (inv.category || "RULE").toUpperCase();
    lines.push(`• [${cat}] (ID: ${inv.id}) ${inv.content}`);
  }
  lines.push("==================================================");
  return lines.join("\n");
}

export function reconcileContradictionsRuleBased(newContent, newCategory, store, now = Date.now()) {
  const CONTRADICTION_TRIGGERS = [
    /改用|切换为|替换为|废除|不再使用|不再支持|迁移到|更新为/u,
    /switch\s+to|replace|instead\s+of|migrate\s+to|deprecated|no\s+longer\s+use/i,
  ];

  const isReplacement = CONTRADICTION_TRIGGERS.some((re) => re.test(newContent));
  if (!isReplacement) return null;

  const newTokens = extractKeywords(newContent);

  for (const existing of store.invariants) {
    if (existing.supersededBy) continue;
    const existingTokens = extractKeywords(existing.content);
    const overlap = calculateTokenOverlap(newTokens, existingTokens);

    if (existing.category === newCategory && overlap >= 0.2) {
      return existing.id;
    }
  }
  return null;
}

export async function reconcileContradictions(newContent, newCategory, store, llmCaller = null, now = Date.now()) {
  const activeInvariants = store.invariants.filter((i) => !i.supersededBy);
  if (activeInvariants.length === 0) {
    return { supersededId: null, engine: "rule" };
  }

  // 1. 大模型因果冲突检测
  if (llmCaller && typeof llmCaller === "function") {
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

      const rawText = await llmCaller(promptContent, systemPrompt);
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
    } catch {}
  }

  // 2. 规则代码回滚降级
  const fallbackId = reconcileContradictionsRuleBased(newContent, newCategory, store, now);
  return {
    supersededId: fallbackId,
    engine: "rule",
    reason: fallbackId ? "Rule-based pattern and token overlap match" : undefined,
  };
}

const EXTRACTION_PATTERNS = [
  /(?:remember|always|never|prefer|strictly use|from now on|do not use)\s*[:：]?\s*([^.!\n]+[.!\n]?)/i,
  /(?:记住|始终|严禁|必须使用|统一使用|规范要求|切勿|即日起|全面切换为)\s*[:：]?\s*([^。！\n]+[。！\n]?)/u,
  /(?:architecture decision|project rule)\s*[:：]\s*([^.!\n]+)/i,
];

export function extractCandidateRules(text) {
  if (!text) return [];
  const results = [];
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

export function runFallbackHeuristics(userText = "", assistantText = "", cwd = process.cwd(), store) {
  const candidates = [...extractCandidateRules(userText), ...extractCandidateRules(assistantText)];
  if (candidates.length === 0) return 0;
  let added = 0;
  const now = Date.now();

  for (const candidate of candidates) {
    const candidateTokens = extractKeywords(candidate);
    const isTooling = /bun|npm|pnpm|yarn|cargo|pip|uv|brew/i.test(candidate);
    const isPitfall = /bug|pitfall|issue|error|fail|avoid|切勿|小心|坑/i.test(candidate);
    const isArchitecture = /architecture|framework|database|protocol|schema|架构|数据库|协议/i.test(candidate);
    const category = isTooling ? "tooling" : isPitfall ? "pitfall" : isArchitecture ? "architecture" : "preference";

    // 冲突消解
    const supersededId = reconcileContradictionsRuleBased(candidate, category, store, now);
    if (supersededId) {
      const oldInv = store.invariants.find((i) => i.id === supersededId);
      const newId = "inv_" + now + "_" + crypto.randomBytes(3).toString("hex");
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
        hitCount: 1,
        supersedes: supersededId,
      });
      added++;
      continue;
    }

    // 检查重复
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
        id: "inv_" + now + "_" + crypto.randomBytes(3).toString("hex"),
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
