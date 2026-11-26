// debutkit 커뮤니티를 이 PC에서 시험하는 바탕: Cloudflare D1(SQLite)과 KV를 Node 내장 SQLite(22.5 이상)와 메모리로 흉내 낸다.
// 배포에는 쓰지 않는다. 시험(tests/community_worker.test.mjs)과 미리보기 서버(preview.mjs)가 쓴다.
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";

const SCHEMA = new URL("./schema.sql", import.meta.url);

function plain(row) {
  return row === undefined ? null : { ...row };
}

export function fakeD1(path = ":memory:") {
  const sqlite = new DatabaseSync(path);
  sqlite.exec(readFileSync(SCHEMA, "utf8"));
  const statement = (sql, args = []) => ({
    bind: (...values) => statement(sql, values.map((value) => (value === undefined ? null : typeof value === "boolean" ? Number(value) : value))),
    first: async () => plain(sqlite.prepare(sql).get(...args)),
    all: async () => ({ results: sqlite.prepare(sql).all(...args).map(plain) }),
    run: async () => {
      const result = sqlite.prepare(sql).run(...args);
      return { meta: { last_row_id: Number(result.lastInsertRowid), changes: Number(result.changes) } };
    },
  });
  return {
    sqlite,
    prepare: (sql) => statement(sql),
    async batch(list) {
      sqlite.exec("BEGIN");
      try {
        const out = [];
        for (const item of list) out.push(await item.run());
        sqlite.exec("COMMIT");
        return out;
      } catch (error) {
        sqlite.exec("ROLLBACK");
        throw error;
      }
    },
  };
}

export function fakeKV() {
  const store = new Map();
  return {
    store,
    async put(key, value, options = {}) {
      store.set(key, { value: value instanceof Uint8Array ? value.slice().buffer : value, metadata: options.metadata ?? null });
    },
    async getWithMetadata(key) {
      const found = store.get(key);
      return found ? { value: found.value, metadata: found.metadata } : { value: null, metadata: null };
    },
    async delete(key) {
      store.delete(key);
    },
  };
}

export async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function fakeEnv({ adminToken = "dev-token", path = ":memory:", extra = {} } = {}) {
  return { DB: fakeD1(path), FILES: fakeKV(), ADMIN_TOKEN_HASH: await sha256Hex(adminToken), SESSION_KEY: "local-session-key", ...extra };
}
