/**
 * Core Utilities for Muse Wonder Claude Code Plugin (Pure Vanilla ESM)
 */

import * as fs from "node:fs";
import * as path from "node:path";

export function getClaudeDir(cwd = process.cwd()) {
  const localClaude = path.join(cwd, ".claude");
  if (fs.existsSync(localClaude)) return localClaude;

  const localPi = path.join(cwd, ".pi");
  if (fs.existsSync(localPi)) return localPi;

  if (!fs.existsSync(localClaude)) {
    try {
      fs.mkdirSync(localClaude, { recursive: true });
    } catch {}
  }
  return localClaude;
}

export function getMemoryFilePath(cwd = process.cwd()) {
  const dir = getClaudeDir(cwd);
  return path.join(dir, "active-memory.json");
}

export function getFocusFilePath(cwd = process.cwd()) {
  const dir = getClaudeDir(cwd);
  return path.join(dir, "active-focus.json");
}

export function extractKeywords(text) {
  if (!text) return [];
  if (typeof Intl !== "undefined" && typeof Intl.Segmenter === "function") {
    try {
      const segmenter = new Intl.Segmenter("zh", { granularity: "word" });
      return Array.from(segmenter.segment(text.toLowerCase()))
        .filter((s) => s.isWordLike)
        .map((s) => s.segment.trim())
        .filter((w) => w.length >= 2 || /^[a-zA-Z0-9]$/.test(w));
    } catch {}
  }
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}_\s-]/gu, " ")
    .split(/\s+/)
    .filter((w) => w.length >= 2);
}

export function calculateTokenOverlap(tokensA, tokensB) {
  if (!tokensA || !tokensB || tokensA.length === 0 || tokensB.length === 0) return 0;
  const setA = new Set(tokensA);
  const setB = new Set(tokensB);
  let intersection = 0;
  for (const t of setA) {
    if (setB.has(t)) intersection++;
  }
  const union = new Set([...tokensA, ...tokensB]).size;
  return union === 0 ? 0 : intersection / union;
}

export function parseJsonSafe(text) {
  if (!text) return null;
  try {
    const cleaned = text.replace(/```(?:json)?/gi, "").replace(/```/g, "").trim();
    const start = cleaned.indexOf("{");
    const end = cleaned.lastIndexOf("}");
    if (start !== -1 && end !== -1 && end > start) {
      return JSON.parse(cleaned.slice(start, end + 1));
    }
  } catch {}
  return null;
}

export function extractTextFromMessage(msg) {
  if (!msg) return "";
  if (typeof msg === "string") return msg;
  if (typeof msg.content === "string") return msg.content;
  if (Array.isArray(msg.content)) {
    return msg.content
      .map((c) => {
        if (typeof c === "string") return c;
        if (c && typeof c.text === "string") return c.text;
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }
  return "";
}

export function matchGlobPattern(filePath, pattern) {
  if (!filePath || !pattern) return false;
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
  if (p.startsWith("*.") && !p.includes("/")) {
    const ext = p.slice(1);
    return normalized.endsWith(ext);
  }
  return normalized === p || normalized.includes(p);
}
