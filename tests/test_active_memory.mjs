import assert from "node:assert";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

// Simple test for Active Memory core logic
const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "pi-active-memory-test-"));

try {
	// 1. Verify extraction regex
	const EXTRACTION_PATTERNS = [
		/(?:remember|always|never|prefer|strictly use|from now on|do not use)\s*[:：]?\s*([^.!\n]+[.!\n]?)/i,
		/(?:记住|始终|严禁|必须使用|统一使用|规范要求|切勿)\s*[:：]?\s*([^。！\n]+[。！\n]?)/u,
	];

	function extract(text) {
		const out = [];
		for (const p of EXTRACTION_PATTERNS) {
			const m = text.match(p);
			if (m && m[1]) out.push(m[1].trim());
		}
		return out;
	}

	const candidates = extract("Please remember: always use pnpm instead of npm.");
	assert.ok(candidates.length > 0, "Should extract English rule");
	assert.ok(candidates[0].includes("pnpm"), "Candidate should mention pnpm");

	const candidatesZh = extract("项目规范要求：始终使用 TypeScript 进行类型检查。");
	assert.ok(candidatesZh.length > 0, "Should extract Chinese rule");
	assert.ok(candidatesZh[0].includes("TypeScript"), "Candidate should mention TypeScript");

	// 2. Verify Keyword Matching
	const invariants = [
		{ id: "1", content: "Use pnpm for all packages", category: "tooling", tags: ["pnpm", "package"], hitCount: 0 },
		{ id: "2", content: "Always write unit tests with vitest", category: "architecture", tags: ["vitest", "test"], hitCount: 0 },
	];

	function match(list, prompt) {
		const tokens = new Set(prompt.toLowerCase().split(/\s+/));
		return list.filter(item => item.tags.some(t => tokens.has(t)));
	}

	const matched = match(invariants, "Install lodash package");
	assert.strictEqual(matched.length, 1);
	assert.strictEqual(matched[0].id, "1", "Should match pnpm rule on 'package'");

	console.log("All Active Memory core logic tests passed!");
} finally {
	fs.rmSync(tmpDir, { recursive: true, force: true });
}
