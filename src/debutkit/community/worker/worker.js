// debutkit 커뮤니티: 스트리머마다 자기 Cloudflare 계정에 올리는 팬 커뮤니티(Cloudflare Worker 하나, 의존 없음).
// 바인딩: DB(D1, schema.sql), FILES(KV, 올린 그림). 비밀값: ADMIN_TOKEN_HASH(debutkit API 토큰의 SHA-256), SESSION_KEY,
// 선택 로그인 CHZZK_CLIENT_ID/SECRET, DISCORD_CLIENT_ID/SECRET, GOOGLE_CLIENT_ID/SECRET.
// 화면은 서버에서 만든 HTML이고 사용자 글은 모두 esc()를 거친다. 글쓰기 요청은 같은 사이트 확인(Origin)과 CSRF 값을 함께 본다.
// 시청자 로그인은 방송 채팅 인증(!인증 숫자, debutkit이 채팅을 보고 알려 줌)과 선택한 플랫폼 로그인.

const DAY = 86400000;
const SESSION_DAYS = 30;
const MAX_IMAGE = 3 * 1024 * 1024;
const LIMITS = { name: 20, title: 80, body: 5000, comment: 1000, reason: 200, link: 300, about: 300, rules: 3000, contact: 100 };
//: 게시판: 이름, 쓸 수 있는 사람(mod 이상 또는 viewer 이상), 그림 필수, 주소 칸
export const BOARDS = {
  notice: { name: "공지", write: "mod" },
  free: { name: "자유", write: "viewer" },
  fanart: { name: "팬아트", write: "viewer", image: true },
  qna: { name: "질문", write: "viewer" },
  clips: { name: "클립", write: "viewer", link: true },
};
//: 포인트: [점수, 하루 한도(횟수)]. 출석은 연속 출석마다 더 줌(streak_bonus씩, 최대 streak_max)
export const POINTS = { attend: [10, 1], chat: [10, 1], post: [3, 3], comment: [1, 10], streak_bonus: 2, streak_max: 10 };
//: 등급: 포인트 이상이면
export const LEVELS = [[0, "새싹"], [100, "단골"], [500, "열성"], [2000, "전설"]];
const ROLES = { banned: -1, viewer: 0, mod: 1, owner: 2 };
const PROVIDERS = {
  chzzk: { name: "치지직", authorize: "https://chzzk.naver.com/account-interlock", token: "https://openapi.chzzk.naver.com/auth/v1/token",
    user: "https://openapi.chzzk.naver.com/open/v1/users/me", scope: "" },
  discord: { name: "디스코드", authorize: "https://discord.com/oauth2/authorize", token: "https://discord.com/api/oauth2/token",
    user: "https://discord.com/api/users/@me", scope: "identify" },
  google: { name: "구글(YouTube)", authorize: "https://accounts.google.com/o/oauth2/v2/auth", token: "https://oauth2.googleapis.com/token",
    user: "https://openidconnect.googleapis.com/v1/userinfo", scope: "openid profile" },
};
const CHAT_PLATFORMS = { chzzk: "치지직", soop: "SOOP", twitch: "Twitch", youtube: "YouTube", demo: "시험" };
const SECURITY = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "same-origin",
  "X-Frame-Options": "DENY",
  "Content-Security-Policy": "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
};

// ------------------------------------------------------------------ 도움 함수

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
}

// 글 본문: 글자를 이스케이프한 뒤 줄바꿈과 http(s) 주소만 살림
export function richText(value) {
  return esc(value).replace(/https?:\/\/[^\s<>"']+/g, (url) => `<a href="${url}" rel="nofollow noopener ugc" target="_blank">${url}</a>`).replace(/\r?\n/g, "<br>");
}

export function kstDay(ms = Date.now()) {
  return new Date(ms + 9 * 3600000).toISOString().slice(0, 10);
}

function clean(value, limit, label, required = true) {
  const text = String(value ?? "").replace(/\r\n/g, "\n").trim();
  if (required && !text) throw new UserError(`${label}을(를) 입력`);
  if (text.length > limit) throw new UserError(`${label}은(는) ${limit}자 이내`);
  return text;
}

function oneLine(value, limit, label, required = true) {
  return clean(String(value ?? "").replace(/\s+/g, " "), limit, label, required);
}

function token(bytes = 24) {
  const raw = crypto.getRandomValues(new Uint8Array(bytes));
  return btoa(String.fromCharCode(...raw)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function sha256(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function hmac(key, text) {
  const secret = await crypto.subtle.importKey("raw", new TextEncoder().encode(key || "debutkit"), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", secret, new TextEncoder().encode(text));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 40);
}

function sameText(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function cookies(request) {
  const found = {};
  for (const pair of (request.headers.get("Cookie") || "").split(";")) {
    const [key, ...rest] = pair.trim().split("=");
    if (key) found[key] = decodeURIComponent(rest.join("="));
  }
  return found;
}

function cookie(name, value, maxAge) {
  return `${name}=${encodeURIComponent(value)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}

class UserError extends Error {
  constructor(message, status = 400) {
    super(message);
    this.status = status;
  }
}

function html(body, status = 200, headers = {}) {
  const response = new Response(body, { status, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", ...SECURITY } });
  for (const [key, value] of Object.entries(headers)) {
    if (Array.isArray(value)) for (const item of value) response.headers.append(key, item);
    else response.headers.set(key, value);
  }
  return response;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...SECURITY } });
}

function redirect(location, cookiesToSet = []) {
  const response = new Response(null, { status: 303, headers: { Location: location, ...SECURITY } });
  for (const item of cookiesToSet) response.headers.append("Set-Cookie", item);
  return response;
}

// ------------------------------------------------------------------ 데이터

const db = {
  one: (env, sql, ...args) => env.DB.prepare(sql).bind(...args).first(),
  all: async (env, sql, ...args) => (await env.DB.prepare(sql).bind(...args).all()).results || [],
  run: (env, sql, ...args) => env.DB.prepare(sql).bind(...args).run(),
};

async function settings(env) {
  const rows = await db.all(env, "SELECT key, value FROM settings");
  const found = { name: "우리 커뮤니티", about: "", rules: "", contact: "", theme: "{}", live: "{}", raffle: "{}", providers: "" };
  for (const row of rows) found[row.key] = row.value;
  for (const key of ["theme", "live", "raffle"]) {
    try { found[key] = JSON.parse(found[key] || "{}"); } catch { found[key] = {}; }
  }
  return found;
}

function putSetting(env, key, value) {
  return db.run(env, "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", key,
    typeof value === "string" ? value : JSON.stringify(value));
}

export function level(points) {
  let found = LEVELS[0][1];
  for (const [minimum, name] of LEVELS) if (points >= minimum) found = name;
  return found;
}

function atLeast(user, role) {
  return Boolean(user) && (ROLES[user.role] ?? -1) >= ROLES[role];
}

// 포인트: 하루 한도 안에서만. 돌려주는 값은 준 점수(0이면 한도)
async function award(env, userId, reason, extra = 0) {
  const [amount, perDay] = POINTS[reason];
  const today = kstDay();
  const used = await db.one(env, "SELECT COUNT(*) AS n FROM points WHERE user_id = ? AND reason = ? AND day = ?", userId, reason, today);
  if ((used?.n || 0) >= perDay) return 0;
  const delta = amount + extra;
  await env.DB.batch([
    env.DB.prepare("INSERT INTO points (user_id, delta, reason, day, created_at) VALUES (?, ?, ?, ?, ?)").bind(userId, delta, reason, today, Date.now()),
    env.DB.prepare("UPDATE users SET points = points + ? WHERE id = ?").bind(delta, userId),
  ]);
  return delta;
}

async function attend(env, user) {
  const today = kstDay();
  if (user.last_attend === today) return { given: 0, streak: user.streak };
  const yesterday = kstDay(Date.now() - DAY);
  const streak = user.last_attend === yesterday ? user.streak + 1 : 1;
  const bonus = Math.min(POINTS.streak_max, (streak - 1) * POINTS.streak_bonus);
  const given = await award(env, user.id, "attend", bonus);
  await db.run(env, "UPDATE users SET last_attend = ?, streak = ? WHERE id = ?", today, streak, user.id);
  return { given, streak };
}

// 계정 찾기 또는 만들기. linkTo가 있으면 그 회원에 이 계정을 붙임
async function account(env, provider, subject, name, { avatar = "", role = "", linkTo = null } = {}) {
  const found = await db.one(env, "SELECT user_id FROM identities WHERE provider = ? AND subject = ?", provider, subject);
  if (found && linkTo && found.user_id !== linkTo) throw new UserError("이 계정은 이미 다른 커뮤니티 회원에 연결됨: 그 회원으로 로그인하거나 탈퇴 뒤 다시 연결", 409);
  let userId = found?.user_id;
  if (!userId && linkTo) {
    userId = linkTo;
    await db.run(env, "INSERT INTO identities (provider, subject, user_id, name) VALUES (?, ?, ?, ?)", provider, subject, userId, name);
  } else if (!userId) {
    const made = await db.run(env, "INSERT INTO users (name, avatar, role, created_at) VALUES (?, ?, 'viewer', ?)", name.slice(0, LIMITS.name) || "시청자", avatar, Date.now());
    userId = made.meta.last_row_id;
    await db.run(env, "INSERT INTO identities (provider, subject, user_id, name) VALUES (?, ?, ?, ?)", provider, subject, userId, name);
  } else {
    await db.run(env, "UPDATE identities SET name = ? WHERE provider = ? AND subject = ?", name, provider, subject);
  }
  // 방송 채팅의 스트리머와 매니저는 커뮤니티에서도 같은 권한(내리지는 않음, 정지한 사람은 그대로)
  const user = await db.one(env, "SELECT * FROM users WHERE id = ?", userId);
  if (role && user.role !== "banned" && ROLES[role] > ROLES[user.role]) await db.run(env, "UPDATE users SET role = ? WHERE id = ?", role, userId);
  return userId;
}

async function startSession(env, userId) {
  const raw = token(32);
  await db.run(env, "INSERT INTO sessions (token, user_id, expires) VALUES (?, ?, ?)", await sha256(raw), userId, Date.now() + SESSION_DAYS * DAY);
  return cookie("dk", raw, SESSION_DAYS * 86400);
}

// ------------------------------------------------------------------ 요청 처리

export default {
  async fetch(request, env) {
    try {
      return await route(request, env);
    } catch (error) {
      if (error instanceof UserError) {
        if (new URL(request.url).pathname.startsWith("/api/") || request.headers.get("Accept")?.includes("application/json")) {
          return json({ error: error.message }, error.status);
        }
        const site = await settings(env).catch(() => ({ name: "커뮤니티", theme: {} }));
        return html(page(site, null, "알림", `<section class="card"><p>${esc(error.message)}</p><p><a href="/">홈으로</a></p></section>`), error.status);
      }
      console.error(error);
      return html("<!doctype html><meta charset=utf-8><p>잠시 문제가 생겼습니다. 잠시 뒤 다시 시도합니다.</p>", 500);
    }
  },
};

async function route(request, env) {
  const url = new URL(request.url);
  const path = url.pathname;
  if (path.startsWith("/api/")) return api(request, env, url);
  if (path === "/app.css") return new Response(CSS, { headers: { "Content-Type": "text/css; charset=utf-8", "Cache-Control": "public, max-age=300", ...SECURITY } });
  if (path === "/app.js") return new Response(SCRIPT, { headers: { "Content-Type": "text/javascript; charset=utf-8", "Cache-Control": "public, max-age=300", ...SECURITY } });
  if (path.startsWith("/img/")) return image(env, path.slice(5));
  const c = await visitor(request, env, url);
  if (request.method === "POST") {
    // 같은 사이트에서 보낸 글쓰기만: Origin(없으면 Sec-Fetch-Site)과 화면에 넣은 CSRF 값을 함께 확인
    const origin = request.headers.get("Origin");
    const fetchSite = request.headers.get("Sec-Fetch-Site");
    if (origin ? origin !== url.origin : fetchSite && !["same-origin", "none"].includes(fetchSite)) throw new UserError("다른 사이트에서 보낸 요청", 403);
    c.form = await request.formData();
    if (!sameText(String(c.form.get("_csrf") || ""), c.csrf)) throw new UserError("화면을 새로고침한 뒤 다시 시도", 403);
  }
  const parts = path.split("/").filter(Boolean);
  const [first, second, third] = parts;
  if (request.method === "GET") {
    if (!first) return home(env, c);
    if (first === "b" && BOARDS[second]) return board(env, c, second, Number(url.searchParams.get("page") || 1));
    if (first === "p" && /^\d+$/.test(second || "")) return post(env, c, Number(second));
    if (first === "write") return writeForm(env, c, url.searchParams.get("board") || "free");
    if (first === "schedule") return schedulePage(env, c);
    if (first === "ranking") return ranking(env, c);
    if (first === "me") return me(env, c);
    if (first === "login" && !second) return loginPage(env, c);
    if (first === "login" && second === "chat") return chatWait(env, c, request);
    if (first === "owner") return ownerEnter(env, c, url.searchParams.get("code") || "");
    if (first === "auth" && PROVIDERS[second] && !third) return oauthStart(env, c, second, url);
    if (first === "auth" && PROVIDERS[second] && third === "callback") return oauthDone(env, c, second, url, request);
    if (first === "admin" && second === "export") {
      need(c, "owner");
      return new Response(JSON.stringify(await exportAll(env), null, 1), { headers: { "Content-Type": "application/json; charset=utf-8",
        "Content-Disposition": `attachment; filename="community-${kstDay()}.json"`, "Cache-Control": "no-store", ...SECURITY } });
    }
    if (first === "admin") return admin(env, c);
    if (first === "rules") return textPage(c, "이용 규칙", c.site.rules || DEFAULT_RULES);
    if (first === "privacy") return textPage(c, "개인정보 처리방침", privacyText(c.site));
    if (first === "login" && second === "chat-check") return chatCheck(env, c, request);
  }
  if (request.method === "POST") {
    if (first === "write") return writeSave(env, c);
    if (first === "p" && /^\d+$/.test(second || "")) return postAction(env, c, Number(second), third);
    if (first === "c" && /^\d+$/.test(second || "")) return commentAction(env, c, Number(second), third);
    if (first === "attend") return attendNow(env, c);
    if (first === "raffle") return raffleJoin(env, c);
    if (first === "login" && second === "chat") return chatStart(env, c);
    if (first === "logout") return logout(env, c, request);
    if (first === "me" && second === "name") return rename(env, c);
    if (first === "me" && second === "leave") return leave(env, c, request);
    if (first === "admin") return adminAction(env, c, second);
  }
  throw new UserError("없는 페이지", 404);
}

async function visitor(request, env, url) {
  const site = await settings(env);
  const raw = cookies(request).dk || "";
  let user = null;
  if (raw) {
    const row = await db.one(env, "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ? AND s.expires > ?", await sha256(raw), Date.now());
    if (row) user = row;
  }
  return { site, user, session: raw, csrf: await hmac(env.SESSION_KEY, `csrf:${raw || cookies(request).dk_wait || "guest"}`), url };
}

function need(c, role = "viewer") {
  if (!c.user) throw new UserError("로그인 필요", 401);
  if (c.user.role === "banned") throw new UserError("이용이 정지된 계정", 403);
  if (!atLeast(c.user, role)) throw new UserError("권한 없음", 403);
  return c.user;
}

function field(c, name) {
  return c.form.get(name);
}

// 짧은 시간 안에 너무 많이 쓰는 것 막기
async function slowDown(env, table, userId, perMinute) {
  const recent = await db.one(env, `SELECT COUNT(*) AS n FROM ${table} WHERE user_id = ? AND created_at > ?`, userId, Date.now() - 60000);
  if ((recent?.n || 0) >= perMinute) throw new UserError("잠시 뒤에 다시 쓰기(1분 동안 너무 많이 씀)", 429);
}

// ------------------------------------------------------------------ 화면

function page(site, c, title, body) {
  const theme = site.theme || {};
  const primary = /^#[0-9a-f]{6}$/i.test(theme.primary || "") ? theme.primary : "#ff4f8b";
  const highlight = /^#[0-9a-f]{6}$/i.test(theme.highlight || "") ? theme.highlight : "#ffd84d";
  const user = c?.user;
  const boards = Object.entries(BOARDS).map(([key, b]) => `<a href="/b/${key}">${esc(b.name)}</a>`).join("");
  const account = user
    ? `<a href="/me" class="me">${esc(user.name)} <small>${esc(level(user.points))}, ${user.points}점</small></a>${atLeast(user, "mod") ? '<a href="/admin">관리</a>' : ""}`
    : '<a href="/login" class="me">로그인</a>';
  const live = site.live && site.live.live
    ? `<a class="live" href="${esc(safeLink(site.live.url))}" rel="noopener" target="_blank">방송 중${site.live.title ? `: ${esc(site.live.title)}` : ""}</a>` : "";
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)} - ${esc(site.name)}</title><link rel="stylesheet" href="/app.css">
<style>:root{--accent:${primary};--gold:${highlight}}</style></head><body>
<header><a class="brand" href="/">${esc(site.name)}</a>${live}<nav>${boards}<a href="/schedule">일정</a><a href="/ranking">순위</a></nav><div class="account">${account}</div></header>
<main>${body}</main>
<footer><a href="/rules">이용 규칙</a>, <a href="/privacy">개인정보 처리방침</a>, debutkit 커뮤니티</footer>
<script src="/app.js"></script></body></html>`;
}

function safeLink(value) {
  const text = String(value || "");
  return /^https:\/\/[^\s"'<>]+$/.test(text) ? text : "#";
}

function csrfField(c) {
  return `<input type="hidden" name="_csrf" value="${esc(c.csrf)}">`;
}

function when(ms) {
  const d = new Date(ms + 9 * 3600000);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getUTCMonth() + 1}.${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

function postRow(row) {
  const mark = row.pinned ? '<span class="pin">고정</span>' : "";
  const thumb = row.image ? `<img class="thumb" src="/img/${esc(row.image)}" alt="" loading="lazy">` : "";
  return `<li>${thumb}<a href="/p/${row.id}">${mark}${esc(row.title)}${row.comments ? ` <small>[${row.comments}]</small>` : ""}</a>
<span class="meta">${esc(row.author || "탈퇴한 사용자")}, ${when(row.created_at)}, 추천 ${row.likes}</span></li>`;
}

async function home(env, c) {
  const notices = await db.all(env, "SELECT p.*, u.name AS author FROM posts p LEFT JOIN users u ON u.id = p.user_id WHERE board = 'notice' AND hidden = 0 ORDER BY pinned DESC, id DESC LIMIT 3");
  const recent = await db.all(env, "SELECT p.*, u.name AS author FROM posts p LEFT JOIN users u ON u.id = p.user_id WHERE board != 'notice' AND hidden = 0 ORDER BY id DESC LIMIT 8");
  const art = await db.all(env, "SELECT id, title, image FROM posts WHERE board = 'fanart' AND hidden = 0 AND image != '' ORDER BY id DESC LIMIT 6");
  const week = await upcoming(env);
  const raffle = c.site.raffle && c.site.raffle.open
    ? `<section class="card raffle"><h2>참여 추첨 모집 중${c.site.raffle.title ? `: ${esc(c.site.raffle.title)}` : ""}</h2>
<form method="post" action="/raffle">${csrfField(c)}<button>${c.user ? "참가하기" : "로그인하고 참가"}</button></form></section>` : "";
  const attendBox = c.user
    ? `<form method="post" action="/attend" class="inline">${csrfField(c)}<button ${c.user.last_attend === kstDay() ? "disabled" : ""}>${c.user.last_attend === kstDay() ? "오늘 출석 완료" : "출석 체크"}</button></form>
<span class="meta">연속 ${c.user.streak}일, ${esc(level(c.user.points))}</span>` : '<a href="/login">로그인하고 출석 체크</a>';
  const body = `${raffle}<section class="hero card"><h1>${esc(c.site.name)}</h1>${c.site.about ? `<p>${richText(c.site.about)}</p>` : ""}<div class="row">${attendBox}</div></section>
<div class="grid"><section class="card"><h2><a href="/b/notice">공지</a></h2><ul class="posts">${notices.map(postRow).join("") || '<li class="empty">공지 없음</li>'}</ul></section>
<section class="card"><h2><a href="/schedule">이번 주 방송</a></h2><ul class="days">${week.map(dayRow).join("") || '<li class="empty">등록한 일정 없음</li>'}</ul></section></div>
${art.length ? `<section class="card"><h2><a href="/b/fanart">팬아트</a></h2><div class="gallery">${art.map((a) => `<a href="/p/${a.id}"><img src="/img/${esc(a.image)}" alt="${esc(a.title)}" loading="lazy"></a>`).join("")}</div></section>` : ""}
<section class="card"><h2>새 글</h2><ul class="posts">${recent.map(postRow).join("") || '<li class="empty">아직 글이 없습니다</li>'}</ul></section>`;
  return html(page(c.site, c, "홈", body));
}

async function board(env, c, key, pageNo) {
  const info = BOARDS[key];
  const size = 20;
  const pageIndex = Math.max(1, Math.min(500, Math.floor(pageNo) || 1));
  const rows = await db.all(env, "SELECT p.*, u.name AS author FROM posts p LEFT JOIN users u ON u.id = p.user_id WHERE board = ? AND hidden = 0 ORDER BY pinned DESC, id DESC LIMIT ? OFFSET ?",
    key, size + 1, (pageIndex - 1) * size);
  const more = rows.length > size;
  const canWrite = c.user && atLeast(c.user, info.write);
  const pager = `<div class="row">${pageIndex > 1 ? `<a href="/b/${key}?page=${pageIndex - 1}">이전</a>` : ""}${more ? `<a href="/b/${key}?page=${pageIndex + 1}">다음</a>` : ""}</div>`;
  const list = key === "fanart"
    ? `<div class="gallery big">${rows.slice(0, size).map((a) => `<a href="/p/${a.id}"><img src="/img/${esc(a.image)}" alt="" loading="lazy"><span>${esc(a.title)}</span></a>`).join("") || '<p class="empty">아직 글이 없습니다</p>'}</div>`
    : `<ul class="posts">${rows.slice(0, size).map(postRow).join("") || '<li class="empty">아직 글이 없습니다</li>'}</ul>`;
  const body = `<section class="card"><div class="head"><h1>${esc(info.name)}</h1>${canWrite ? `<a class="button" href="/write?board=${key}">글쓰기</a>` : ""}</div>${list}${pager}</section>`;
  return html(page(c.site, c, info.name, body));
}

async function post(env, c, id) {
  const row = await db.one(env, "SELECT p.*, u.name AS author, u.points AS author_points FROM posts p LEFT JOIN users u ON u.id = p.user_id WHERE p.id = ?", id);
  const mod = c.user && atLeast(c.user, "mod");
  if (!row || row.hidden === 2 && !mod) throw new UserError("없거나 지운 글", 404);
  if (row.hidden && !mod) {
    if (c.user && c.user.id === row.user_id) {
      return html(page(c.site, c, "가려진 글", `<section class="card"><h1>가려진 글: ${esc(row.title)}</h1><p>신고를 받아 스트리머나 매니저가 이 글을 가렸습니다(임시 조치). 권리 침해 신고에 따른 조치는 최대 30일이며, 이의가 있으면 커뮤니티 운영자에게 알립니다${c.site.contact ? `(${esc(c.site.contact)})` : ""}.</p><p><a href="/">홈으로</a></p></section>`));
    }
    throw new UserError("신고를 받아 가려진 글(임시 조치)", 404);
  }
  const comments = await db.all(env, "SELECT k.*, u.name AS author FROM comments k LEFT JOIN users u ON u.id = k.user_id WHERE post_id = ? AND (hidden = 0 OR ?) ORDER BY id", id, mod ? 1 : 0);
  const mine = c.user && c.user.id === row.user_id;
  const action = (name, label, extra = "") => `<form method="post" action="/p/${id}/${name}" class="inline"${extra}>${csrfField(c)}<button class="ghost">${label}</button></form>`;
  const tools = [
    c.user ? action("like", `추천 ${row.likes}`) : `<span class="meta">추천 ${row.likes}</span>`,
    c.user && !mine ? action("report", "신고", ' data-ask="신고 이유"') : "",
    mine || mod ? action("delete", "지우기", ' data-confirm="이 글을 지울까요?"') : "",
    mod ? action("pin", row.pinned ? "고정 풀기" : "고정") : "",
    mod ? action("hide", row.hidden ? "다시 보이기" : "가리기") : "",
    mod ? action("stage", "방송에 띄우기") : "",
  ].join("");
  const body = `<article class="card post"><p class="meta"><a href="/b/${esc(row.board)}">${esc(BOARDS[row.board]?.name || "")}</a>${row.hidden ? ", 가려진 글" : ""}</p>
<h1>${esc(row.title)}</h1><p class="meta">${esc(row.author || "탈퇴한 사용자")} <small>${esc(level(row.author_points || 0))}</small>, ${when(row.created_at)}</p>
${row.image ? `<img class="art" src="/img/${esc(row.image)}" alt="">` : ""}
${row.link ? `<p><a href="${esc(safeLink(row.link))}" rel="nofollow noopener ugc" target="_blank">${esc(row.link)}</a></p>` : ""}
<div class="body">${richText(row.body)}</div><div class="row tools">${tools}</div></article>
<section class="card"><h2>댓글 ${comments.length}</h2><ul class="comments">${comments.map((k) => `<li${k.hidden ? ' class="hidden"' : ""}><b>${esc(k.author || "탈퇴한 사용자")}</b> <span class="meta">${when(k.created_at)}</span>
<p>${richText(k.body)}</p><div class="row">${c.user && c.user.id !== k.user_id ? `<form method="post" action="/c/${k.id}/report" class="inline" data-ask="신고 이유">${csrfField(c)}<button class="ghost">신고</button></form>` : ""}
${c.user && (c.user.id === k.user_id || mod) ? `<form method="post" action="/c/${k.id}/delete" class="inline" data-confirm="댓글을 지울까요?">${csrfField(c)}<button class="ghost">지우기</button></form>` : ""}
${mod ? `<form method="post" action="/c/${k.id}/hide" class="inline">${csrfField(c)}<button class="ghost">${k.hidden ? "다시 보이기" : "가리기"}</button></form>` : ""}</div></li>`).join("")}</ul>
${c.user ? `<form method="post" action="/p/${id}/comment" class="stack">${csrfField(c)}<textarea name="body" maxlength="${LIMITS.comment}" required placeholder="댓글"></textarea><button>댓글 쓰기</button></form>` : '<p><a href="/login">로그인하고 댓글 쓰기</a></p>'}</section>`;
  return html(page(c.site, c, row.title, body));
}

function writeForm(env, c, key) {
  const user = need(c);
  const info = BOARDS[key] || BOARDS.free;
  if (!atLeast(user, info.write)) throw new UserError(`${info.name} 게시판은 스트리머와 매니저만 쓸 수 있음`, 403);
  const options = Object.entries(BOARDS).filter(([, b]) => atLeast(user, b.write)).map(([k, b]) => `<option value="${k}"${k === key ? " selected" : ""}>${esc(b.name)}</option>`).join("");
  const body = `<section class="card"><h1>글쓰기</h1><form method="post" action="/write" enctype="multipart/form-data" class="stack">${csrfField(c)}
<label>게시판<select name="board">${options}</select></label>
<label>제목<input name="title" maxlength="${LIMITS.title}" required></label>
<label>내용<textarea name="body" maxlength="${LIMITS.body}" rows="10"></textarea></label>
<label>그림(팬아트는 필수, PNG, JPEG, GIF, WebP, 3MB 이하)<input type="file" name="image" accept="image/png,image/jpeg,image/gif,image/webp"></label>
<label>주소(클립, 다시보기 등 https 주소)<input name="link" maxlength="${LIMITS.link}" placeholder="https://"></label>
<button>올리기</button></form></section>`;
  return html(page(c.site, c, "글쓰기", body));
}

const IMAGE_TYPES = [[[0x89, 0x50, 0x4e, 0x47], "image/png"], [[0xff, 0xd8, 0xff], "image/jpeg"], [[0x47, 0x49, 0x46, 0x38], "image/gif"]];

export function imageType(bytes) {
  for (const [magic, type] of IMAGE_TYPES) if (magic.every((b, i) => bytes[i] === b)) return type;
  if (bytes.length > 12 && String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" && String.fromCharCode(...bytes.slice(8, 12)) === "WEBP") return "image/webp";
  return "";
}

async function saveImage(env, file) {
  if (!file || typeof file === "string" || !file.size) return "";
  if (file.size > MAX_IMAGE) throw new UserError("그림은 3MB 이하");
  const bytes = new Uint8Array(await file.arrayBuffer());
  const type = imageType(bytes);
  if (!type) throw new UserError("그림은 PNG, JPEG, GIF, WebP만");
  const key = token(18);
  await env.FILES.put(key, bytes, { metadata: { type } });
  return key;
}

async function writeSave(env, c) {
  const user = need(c);
  const key = String(field(c, "board") || "");
  const info = BOARDS[key];
  if (!info) throw new UserError("없는 게시판");
  if (!atLeast(user, info.write)) throw new UserError(`${info.name} 게시판은 스트리머와 매니저만 쓸 수 있음`, 403);
  await slowDown(env, "posts", user.id, 2);
  const title = oneLine(field(c, "title"), LIMITS.title, "제목");
  const body = clean(field(c, "body"), LIMITS.body, "내용", !info.image);
  const link = oneLine(field(c, "link"), LIMITS.link, "주소", false);
  if (link && safeLink(link) === "#") throw new UserError("주소는 https:// 로 시작");
  const image = await saveImage(env, field(c, "image"));
  if (info.image && !image) throw new UserError("팬아트는 그림이 필요");
  const made = await db.run(env, "INSERT INTO posts (board, user_id, title, body, image, link, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", key, user.id, title, body, image, link, Date.now());
  await award(env, user.id, "post");
  return redirect(`/p/${made.meta.last_row_id}`);
}

async function postAction(env, c, id, action) {
  const user = need(c);
  const row = await db.one(env, "SELECT * FROM posts WHERE id = ?", id);
  if (!row) throw new UserError("없는 글", 404);
  const mod = atLeast(user, "mod");
  if (action === "comment") {
    if (row.hidden && !mod) throw new UserError("가려진 글", 404);
    await slowDown(env, "comments", user.id, 6);
    const body = clean(field(c, "body"), LIMITS.comment, "댓글");
    await env.DB.batch([
      env.DB.prepare("INSERT INTO comments (post_id, user_id, body, created_at) VALUES (?, ?, ?, ?)").bind(id, user.id, body, Date.now()),
      env.DB.prepare("UPDATE posts SET comments = comments + 1 WHERE id = ?").bind(id),
    ]);
    await award(env, user.id, "comment");
  } else if (action === "like") {
    const done = await db.run(env, "INSERT OR IGNORE INTO likes (post_id, user_id) VALUES (?, ?)", id, user.id);
    if (done.meta.changes) await db.run(env, "UPDATE posts SET likes = likes + 1 WHERE id = ?", id);
  } else if (action === "report") {
    const reason = oneLine(field(c, "reason") || "부적절한 글", LIMITS.reason, "신고 이유");
    await db.run(env, "INSERT OR IGNORE INTO reports (kind, target, user_id, reason, created_at) VALUES ('post', ?, ?, ?, ?)", id, user.id, reason, Date.now());
    return redirect(`/p/${id}?reported=1`);
  } else if (action === "delete") {
    if (row.user_id !== user.id && !mod) throw new UserError("권한 없음", 403);
    await db.run(env, "UPDATE posts SET hidden = 2 WHERE id = ?", id);  // 2: 지움(관리 화면에서도 목록에 안 보임)
    if (row.image) await env.FILES.delete(row.image);
    return redirect(`/b/${row.board}`);
  } else if (mod && action === "pin") {
    await db.run(env, "UPDATE posts SET pinned = 1 - pinned WHERE id = ?", id);
  } else if (mod && action === "hide") {
    await db.run(env, "UPDATE posts SET hidden = CASE hidden WHEN 0 THEN 1 ELSE 0 END WHERE id = ? AND hidden != 2", id);
    await db.run(env, "UPDATE reports SET done = 1 WHERE kind = 'post' AND target = ?", id);
  } else if (mod && action === "stage") {
    await db.run(env, "INSERT INTO stage (post_id, created_at) VALUES (?, ?)", id, Date.now());
    return redirect(`/p/${id}?staged=1`);
  } else {
    throw new UserError("없는 동작", 404);
  }
  return redirect(`/p/${id}`);
}

async function commentAction(env, c, id, action) {
  const user = need(c);
  const row = await db.one(env, "SELECT * FROM comments WHERE id = ?", id);
  if (!row) throw new UserError("없는 댓글", 404);
  const mod = atLeast(user, "mod");
  if (action === "report") {
    const reason = oneLine(field(c, "reason") || "부적절한 댓글", LIMITS.reason, "신고 이유");
    await db.run(env, "INSERT OR IGNORE INTO reports (kind, target, user_id, reason, created_at) VALUES ('comment', ?, ?, ?, ?)", id, user.id, reason, Date.now());
  } else if (action === "delete" && (row.user_id === user.id || mod)) {
    await env.DB.batch([
      env.DB.prepare("DELETE FROM comments WHERE id = ?").bind(id),
      env.DB.prepare("UPDATE posts SET comments = MAX(0, comments - 1) WHERE id = ?").bind(row.post_id),
    ]);
  } else if (action === "hide" && mod) {
    await db.run(env, "UPDATE comments SET hidden = 1 - hidden WHERE id = ?", id);
    await db.run(env, "UPDATE reports SET done = 1 WHERE kind = 'comment' AND target = ?", id);
  } else {
    throw new UserError("권한 없음", 403);
  }
  return redirect(`/p/${row.post_id}`);
}

async function attendNow(env, c) {
  const user = need(c);
  await attend(env, user);
  return redirect("/");
}

async function raffleJoin(env, c) {
  if (!c.user) return redirect("/login");
  const user = need(c);
  if (!c.site.raffle || !c.site.raffle.open) throw new UserError("지금은 모집 중인 추첨이 없음");
  await db.run(env, "INSERT OR IGNORE INTO raffle (user_id, name, created_at) VALUES (?, ?, ?)", user.id, user.name, Date.now());
  return html(page(c.site, c, "참여 추첨", '<section class="card"><h1>참가했습니다</h1><p>추첨 결과는 방송에서 알려 줍니다.</p><p><a href="/">홈으로</a></p></section>'));
}

// 방송 일정: 오늘부터 7일
const DAYS = ["월", "화", "수", "목", "금", "토", "일"];

async function upcoming(env) {
  const rows = await db.all(env, "SELECT * FROM schedule ORDER BY time");
  const found = [];
  for (let i = 0; i < 7; i += 1) {
    const ms = Date.now() + i * DAY;
    const date = kstDay(ms);
    const weekday = (new Date(ms + 9 * 3600000).getUTCDay() + 6) % 7;
    const special = rows.filter((r) => r.date === date);
    const items = special.length ? special : rows.filter((r) => r.day === weekday && !r.date);
    if (items.length) found.push({ date, weekday, items });
  }
  return found;
}

function dayRow(day) {
  return `<li><b>${day.date.slice(5).replace("-", ".")} ${DAYS[day.weekday]}</b>${day.items.map((item) => item.off
    ? `<span class="off">휴방${item.note ? `, ${esc(item.note)}` : ""}</span>`
    : `<span>${esc(item.time)} ${esc(item.title)}${item.note ? ` <small>${esc(item.note)}</small>` : ""}</span>`).join("")}</li>`;
}

async function schedulePage(env, c) {
  const week = await upcoming(env);
  const rows = await db.all(env, "SELECT * FROM schedule WHERE date = '' ORDER BY day, time");
  const weekly = DAYS.map((name, i) => {
    const items = rows.filter((r) => r.day === i);
    return `<li><b>${name}</b>${items.map((r) => `<span>${esc(r.time)} ${esc(r.title)}</span>`).join("") || '<span class="off">없음</span>'}</li>`;
  }).join("");
  const body = `<section class="card"><h1>이번 주 방송</h1><ul class="days">${week.map(dayRow).join("") || '<li class="empty">등록한 일정 없음</li>'}</ul></section>
<section class="card"><h2>매주 방송</h2><ul class="days">${weekly}</ul></section>`;
  return html(page(c.site, c, "방송 일정", body));
}

async function ranking(env, c) {
  const rows = await db.all(env, "SELECT name, points, streak FROM users WHERE role != 'banned' AND points > 0 ORDER BY points DESC, id LIMIT 50");
  const body = `<section class="card"><h1>포인트 순위</h1>${rows.length ? `<ol class="rank">${rows.map((r) => `<li><b>${esc(r.name)}</b> <small>${esc(level(r.points))}</small><span>${r.points}점</span></li>`).join("")}</ol>` : '<p class="empty">아직 포인트를 받은 회원이 없습니다</p>'}
<p class="meta">출석 ${POINTS.attend[0]}점(연속 출석은 하루 ${POINTS.streak_bonus}점씩 더, 최대 ${POINTS.streak_max}점), 방송 채팅 !출석 ${POINTS.chat[0]}점, 글 ${POINTS.post[0]}점(하루 ${POINTS.post[1]}번), 댓글 ${POINTS.comment[0]}점(하루 ${POINTS.comment[1]}번). 등급: ${LEVELS.map(([m, n]) => `${esc(n)} ${m}점`).join(", ")}. 포인트는 활동 기록이며 사고팔거나 다른 사람에게 줄 수 없고 현금 가치가 없습니다.</p></section>`;
  return html(page(c.site, c, "순위", body));
}

async function me(env, c) {
  const user = need(c);
  const links = await db.all(env, "SELECT provider, name FROM identities WHERE user_id = ?", user.id);
  const log = await db.all(env, "SELECT delta, reason, created_at FROM points WHERE user_id = ? ORDER BY id DESC LIMIT 10", user.id);
  const reasons = { attend: "출석", chat: "방송 채팅 출석", post: "글", comment: "댓글" };
  const body = `<section class="card"><h1>${esc(user.name)}</h1><p>${esc(level(user.points))}, ${user.points}점, 연속 출석 ${user.streak}일</p>
<form method="post" action="/me/name" class="row">${csrfField(c)}<input name="name" maxlength="${LIMITS.name}" value="${esc(user.name)}" required><button>이름 바꾸기</button></form></section>
<section class="card"><h2>연결한 계정</h2><ul>${links.map((l) => `<li>${esc(CHAT_PLATFORMS[l.provider] || PROVIDERS[l.provider]?.name || (l.provider === "owner" ? "스트리머" : l.provider))} ${esc(l.name)}</li>`).join("")}</ul>
<p class="meta">방송 채팅으로 인증하면 그 플랫폼 계정이 이 계정에 붙어 방송 중 !출석 포인트를 받습니다.</p>
<form method="post" action="/login/chat" class="inline">${csrfField(c)}<input type="hidden" name="agree" value="1"><input type="hidden" name="age" value="1"><button class="ghost">방송 채팅 계정 연결</button></form>
${loginButtons(c.site, "연결")}</section>
<section class="card"><h2>최근 포인트</h2><ul>${log.map((p) => `<li>${esc(reasons[p.reason] || p.reason)} +${p.delta} <span class="meta">${when(p.created_at)}</span></li>`).join("") || '<li class="empty">없음</li>'}</ul></section>
<section class="card"><form method="post" action="/logout" class="inline">${csrfField(c)}<button class="ghost">로그아웃</button></form>
<form method="post" action="/me/leave" class="inline" data-confirm="탈퇴하면 계정, 연결, 포인트가 지워지고 쓴 글은 탈퇴한 사용자로 남습니다. 탈퇴할까요?">${csrfField(c)}<button class="ghost danger">탈퇴</button></form></section>`;
  return html(page(c.site, c, "내 정보", body));
}

async function rename(env, c) {
  const user = need(c);
  const name = oneLine(field(c, "name"), LIMITS.name, "이름");
  await db.run(env, "UPDATE users SET name = ? WHERE id = ?", name, user.id);
  return redirect("/me");
}

async function leave(env, c, request) {
  const user = need(c);
  if (user.role === "owner") throw new UserError("스트리머 계정은 탈퇴할 수 없음");
  await env.DB.batch([
    env.DB.prepare("DELETE FROM identities WHERE user_id = ?").bind(user.id),
    env.DB.prepare("DELETE FROM sessions WHERE user_id = ?").bind(user.id),
    env.DB.prepare("DELETE FROM points WHERE user_id = ?").bind(user.id),
    env.DB.prepare("DELETE FROM likes WHERE user_id = ?").bind(user.id),
    env.DB.prepare("DELETE FROM raffle WHERE user_id = ?").bind(user.id),
    env.DB.prepare("DELETE FROM users WHERE id = ?").bind(user.id),
  ]);
  return redirect("/", [cookie("dk", "", 0)]);
}

async function logout(env, c) {
  if (c.session) await db.run(env, "DELETE FROM sessions WHERE token = ?", await sha256(c.session));
  return redirect("/", [cookie("dk", "", 0)]);
}

function textPage(c, title, text) {
  return html(page(c.site, c, title, `<section class="card"><h1>${esc(title)}</h1><div class="body">${richText(text)}</div></section>`));
}

const DEFAULT_RULES = `1. 서로 존중합니다. 욕설, 혐오, 차별, 괴롭힘은 가립니다.
2. 개인정보(실명, 연락처, 주소, 얼굴 사진)를 올리지 않습니다.
3. 다른 사람이 만든 그림과 영상은 출처를 밝히고, 허락 없는 재업로드는 하지 않습니다.
4. 광고, 도배, 불법 정보는 가리고 이용을 정지할 수 있습니다.
5. 신고한 글은 스트리머와 매니저가 확인합니다.`;

function privacyText(site) {
  return `${site.name}(이하 커뮤니티)은 스트리머가 운영하는 팬 커뮤니티이며 아래와 같이 개인정보를 처리합니다.

1. 수집 항목: 연결한 플랫폼 계정 번호와 닉네임(치지직, SOOP, Twitch, YouTube, 디스코드, 구글 중 사용한 것), 프로필 그림 주소, 커뮤니티 안의 이름, 쓴 글과 댓글, 포인트와 출석 기록, 로그인 상태 정보(쿠키). 이메일, 실명, 전화번호는 받지 않습니다.
2. 목적: 회원 구분, 글과 댓글 작성, 출석과 포인트, 방송 중 참여(추첨, 방송 화면 표시), 부정 이용 방지.
3. 보관: 탈퇴할 때까지. 탈퇴하면 계정, 연결, 포인트 기록을 바로 지우며 쓴 글은 작성자 없이 남습니다(지우려면 탈퇴 전에 지우기).
4. 제3자 제공: 하지 않습니다.
5. 처리 위탁과 국외 이전: 커뮤니티는 Cloudflare, Inc.(미국)의 서버(Workers, D1, KV)에서 운영되며 위 정보가 Cloudflare의 국외 데이터센터에 저장될 수 있습니다. 로그인 시 선택한 플랫폼(네이버, 디스코드, 구글)과 계정 확인 정보를 주고받습니다.
6. 만 14세 미만은 가입하지 않습니다.
7. 권리: 내 정보에서 이름 변경, 탈퇴로 삭제를 직접 할 수 있고, 그 밖의 요청은 아래 연락처로 합니다.
8. 개인정보 담당: ${site.contact || "스트리머(연락처는 커뮤니티 공지 참고)"}`;
}

// ------------------------------------------------------------------ 로그인

function loginButtons(site, verb = "로그인") {
  const enabled = String(site.providers || "").split(",").filter((key) => PROVIDERS[key]);
  return enabled.map((key) => `<a class="button ghost" href="/auth/${key}">${esc(PROVIDERS[key].name)} ${verb}</a>`).join(" ");
}

function loginPage(env, c) {
  if (c.user) return redirect("/me");
  const body = `<section class="card"><h1>로그인</h1>
<h2>방송 채팅으로 인증</h2><p>방송 중에 채팅창에 숫자를 입력하면 그 채팅 계정으로 가입합니다(치지직, SOOP, YouTube, Twitch). 비밀번호와 이메일이 필요 없습니다.</p>
<form method="post" action="/login/chat" class="stack">${csrfField(c)}
<label class="check"><input type="checkbox" name="agree" value="1" required> <span><a href="/rules" target="_blank">이용 규칙</a>과 <a href="/privacy" target="_blank">개인정보 처리방침</a>에 동의</span></label>
<label class="check"><input type="checkbox" name="age" value="1" required> 만 14세 이상입니다</label>
<button>인증 숫자 받기</button></form>
${loginButtons(c.site) ? `<h2>다른 계정으로 로그인</h2><p class="row">${loginButtons(c.site)}</p><p class="meta">처음 로그인하면 이용 규칙과 개인정보 처리방침에 동의하고 만 14세 이상인 것으로 봅니다.</p>` : ""}</section>`;
  return html(page(c.site, c, "로그인", body));
}

async function chatStart(env, c) {
  if (field(c, "agree") !== "1" || field(c, "age") !== "1") throw new UserError("이용 규칙과 개인정보 처리방침 동의, 만 14세 이상 확인이 필요");
  const waiter = token(24);
  let code = "";
  for (let i = 0; i < 5 && !code; i += 1) {
    const candidate = String(crypto.getRandomValues(new Uint32Array(1))[0] % 900000 + 100000);
    const taken = await db.one(env, "SELECT code FROM pending WHERE code = ? AND expires > ?", candidate, Date.now());
    if (!taken) code = candidate;
  }
  if (!code) throw new UserError("잠시 뒤에 다시 시도", 503);
  await db.run(env, "DELETE FROM pending WHERE expires < ?", Date.now());
  await db.run(env, "INSERT OR REPLACE INTO pending (code, kind, waiter, user_id, expires) VALUES (?, 'chat', ?, ?, ?)", code, await sha256(waiter), c.user?.id ?? null, Date.now() + 10 * 60000);
  return redirect("/login/chat", [cookie("dk_wait", waiter, 600)]);
}

async function chatWait(env, c, request) {
  const waiter = cookies(request).dk_wait || "";
  const row = waiter ? await db.one(env, "SELECT * FROM pending WHERE waiter = ? AND kind = 'chat' AND expires > ?", await sha256(waiter), Date.now()) : null;
  if (!row) return redirect(c.user ? "/me" : "/login");
  const body = `<section class="card center" id="chat-wait" data-check="/login/chat-check"><h1>방송 채팅에 입력</h1><p class="code">!인증 ${esc(row.code)}</p>
<p>방송 중인 채팅창에 위 글을 그대로 입력하면 이 화면이 저절로 넘어갑니다(10분 안). 방송이 꺼져 있거나 스트리머의 debutkit이 켜져 있지 않으면 인증할 수 없습니다.</p>
<p class="meta" id="chat-state">기다리는 중</p></section>`;
  return html(page(c.site, c, "채팅 인증", body));
}

async function chatCheck(env, c, request) {
  const waiter = cookies(request).dk_wait || "";
  const row = waiter ? await db.one(env, "SELECT * FROM pending WHERE waiter = ? AND kind = 'chat' AND expires > ?", await sha256(waiter), Date.now()) : null;
  if (!row) return json({ done: false, expired: true });
  if (!row.provider) return json({ done: false });
  let userId;
  try {
    userId = await account(env, row.provider, row.subject, row.name, { role: row.role, linkTo: row.user_id });
  } finally {
    await db.run(env, "DELETE FROM pending WHERE code = ?", row.code);
  }
  const set = [cookie("dk_wait", "", 0)];
  if (!c.user || c.user.id !== userId) set.push(await startSession(env, userId));
  const response = json({ done: true, next: c.user ? "/me" : "/" });
  for (const item of set) response.headers.append("Set-Cookie", item);
  return response;
}

async function ownerEnter(env, c, code) {
  const row = code ? await db.one(env, "SELECT * FROM pending WHERE code = ? AND kind = 'owner' AND expires > ?", await sha256(code), Date.now()) : null;
  if (!row) throw new UserError("접속 주소가 만료됨: debutkit의 커뮤니티 화면에서 관리 화면 열기를 다시 누르기", 403);
  await db.run(env, "DELETE FROM pending WHERE code = ?", row.code);
  // 스트리머 계정이 이미 있으면 그 계정으로, 처음이면 지금 로그인한 계정(채팅 인증한 스트리머 계정 등)에 붙이거나 새로 만듦
  const known = await db.one(env, "SELECT user_id FROM identities WHERE provider = 'owner' AND subject = 'owner'");
  const userId = known?.user_id ?? await account(env, "owner", "owner", c.site.owner_name || "스트리머", { role: "owner", linkTo: c.user?.id ?? null });
  await db.run(env, "UPDATE users SET role = 'owner' WHERE id = ?", userId);
  return redirect("/admin", [await startSession(env, userId)]);
}

function oauthStart(env, c, key, url) {
  const provider = PROVIDERS[key];
  const id = env[`${key.toUpperCase()}_CLIENT_ID`];
  if (!id || !String(c.site.providers || "").split(",").includes(key)) throw new UserError(`${provider.name} 로그인을 쓰지 않는 커뮤니티`, 404);
  const state = token(18);
  const redirectUri = `${url.origin}/auth/${key}/callback`;
  const query = key === "chzzk"
    ? new URLSearchParams({ clientId: id, redirectUri, state })
    : new URLSearchParams({ client_id: id, redirect_uri: redirectUri, response_type: "code", scope: provider.scope, state, prompt: key === "google" ? "select_account" : "consent" });
  return redirect(`${provider.authorize}?${query}`, [cookie("dk_state", state, 600)]);
}

async function oauthDone(env, c, key, url, request) {
  const provider = PROVIDERS[key];
  const state = url.searchParams.get("state") || "";
  if (!state || !sameText(state, cookies(request).dk_state || "")) throw new UserError("로그인 요청이 만료됨: 다시 시도", 403);
  const code = url.searchParams.get("code");
  if (!code) throw new UserError(`${provider.name} 로그인을 취소함`);
  const id = env[`${key.toUpperCase()}_CLIENT_ID`];
  const secret = env[`${key.toUpperCase()}_CLIENT_SECRET`];
  const redirectUri = `${url.origin}/auth/${key}/callback`;
  let accessToken = "";
  if (key === "chzzk") {
    const answer = await (await fetch(provider.token, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ grantType: "authorization_code", clientId: id, clientSecret: secret, code, state }) })).json();
    accessToken = answer?.content?.accessToken || "";
  } else {
    const answer = await (await fetch(provider.token, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ client_id: id, client_secret: secret, grant_type: "authorization_code", code, redirect_uri: redirectUri }) })).json();
    accessToken = answer?.access_token || "";
  }
  if (!accessToken) throw new UserError(`${provider.name} 로그인 실패`, 502);
  const profile = await (await fetch(provider.user, { headers: { Authorization: `Bearer ${accessToken}` } })).json();
  let subject = "";
  let name = "";
  let avatar = "";
  if (key === "chzzk") {
    subject = profile?.content?.channelId || "";
    name = profile?.content?.channelName || "";
  } else if (key === "discord") {
    subject = profile?.id || "";
    name = profile?.global_name || profile?.username || "";
    avatar = profile?.avatar ? `https://cdn.discordapp.com/avatars/${profile.id}/${profile.avatar}.png?size=64` : "";
  } else {
    subject = profile?.sub || "";
    name = profile?.name || "";
    avatar = /^https:\/\//.test(profile?.picture || "") ? profile.picture : "";
  }
  if (!subject) throw new UserError(`${provider.name} 계정 정보를 받지 못함`, 502);
  const userId = await account(env, key, String(subject), String(name || provider.name).slice(0, 40), { avatar, linkTo: c.user?.id ?? null });
  const set = [cookie("dk_state", "", 0)];
  if (!c.user) set.push(await startSession(env, userId));
  return redirect(c.user ? "/me" : "/", set);
}

// ------------------------------------------------------------------ 관리

async function admin(env, c) {
  const user = need(c, "mod");
  const reports = await db.all(env, `SELECT r.kind, r.target, COUNT(*) AS n, GROUP_CONCAT(r.reason, ' / ') AS reasons,
    COALESCE(p.title, k.body) AS text, COALESCE(p.id, k.post_id) AS post
    FROM reports r LEFT JOIN posts p ON r.kind = 'post' AND p.id = r.target LEFT JOIN comments k ON r.kind = 'comment' AND k.id = r.target
    WHERE r.done = 0 GROUP BY r.kind, r.target ORDER BY n DESC LIMIT 50`);
  const hidden = await db.all(env, "SELECT id, title FROM posts WHERE hidden = 1 ORDER BY id DESC LIMIT 20");
  const users = await db.all(env, "SELECT id, name, role, points FROM users ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'mod' THEN 1 WHEN 'banned' THEN 3 ELSE 2 END, id DESC LIMIT 100");
  const schedule = await db.all(env, "SELECT * FROM schedule ORDER BY date, day, time");
  const owner = user.role === "owner";
  const roleForm = (u) => owner && u.role !== "owner" ? `<form method="post" action="/admin/role" class="inline">${csrfField(c)}<input type="hidden" name="user" value="${u.id}">
<select name="role">${["viewer", "mod", "banned"].map((r) => `<option value="${r}"${u.role === r ? " selected" : ""}>${{ viewer: "시청자", mod: "매니저", banned: "정지" }[r]}</option>`).join("")}</select><button class="ghost">바꾸기</button></form>`
    : user.role === "mod" && ["viewer", "banned"].includes(u.role) ? `<form method="post" action="/admin/role" class="inline">${csrfField(c)}<input type="hidden" name="user" value="${u.id}"><input type="hidden" name="role" value="${u.role === "banned" ? "viewer" : "banned"}"><button class="ghost">${u.role === "banned" ? "정지 풀기" : "정지"}</button></form>` : "";
  const body = `<section class="card"><h1>관리</h1><p class="meta">신고는 확인한 뒤 가리거나 넘깁니다. 정보통신망법의 권리 침해 신고(명예훼손, 사생활 침해)는 받은 뒤 바로 가리고(임시 조치) 당사자에게 알립니다.</p></section>
<section class="card"><h2>신고 ${reports.length}</h2><ul>${reports.map((r) => `<li><a href="/p/${r.post}">${esc(String(r.text || "").slice(0, 60))}</a> <span class="meta">${r.kind === "post" ? "글" : "댓글"}, ${r.n}건, ${esc(r.reasons)}</span>
<form method="post" action="/admin/dismiss" class="inline">${csrfField(c)}<input type="hidden" name="kind" value="${esc(r.kind)}"><input type="hidden" name="target" value="${r.target}"><button class="ghost">문제 없음</button></form></li>`).join("") || '<li class="empty">없음</li>'}</ul></section>
<section class="card"><h2>가린 글</h2><ul>${hidden.map((p) => `<li><a href="/p/${p.id}">${esc(p.title)}</a></li>`).join("") || '<li class="empty">없음</li>'}</ul></section>
<section class="card"><h2>방송 일정</h2><ul>${schedule.map((s) => `<li>${s.date ? esc(s.date) : `매주 ${DAYS[s.day] || ""}`} ${esc(s.time)} ${s.off ? "휴방" : esc(s.title)} ${s.note ? `<small>${esc(s.note)}</small>` : ""}
<form method="post" action="/admin/schedule-remove" class="inline">${csrfField(c)}<input type="hidden" name="id" value="${s.id}"><button class="ghost">지우기</button></form></li>`).join("") || '<li class="empty">없음</li>'}</ul>
<form method="post" action="/admin/schedule-add" class="row">${csrfField(c)}<select name="day"><option value="-1">그날만</option>${DAYS.map((d, i) => `<option value="${i}">매주 ${d}</option>`).join("")}</select>
<input type="date" name="date"><input type="time" name="time"><input name="title" maxlength="${LIMITS.title}" placeholder="방송 제목(휴방이면 비움)"><input name="note" maxlength="60" placeholder="메모">
<label class="check"><input type="checkbox" name="off" value="1"> 휴방</label><button>추가</button></form></section>
<section class="card"><h2>회원</h2><ul class="users">${users.map((u) => `<li><b>${esc(u.name)}</b> <span class="meta">${{ owner: "스트리머", mod: "매니저", viewer: "시청자", banned: "정지" }[u.role]}, ${u.points}점</span> ${roleForm(u)}</li>`).join("")}</ul></section>
${owner ? `<section class="card"><h2>커뮤니티 설정</h2><form method="post" action="/admin/settings" class="stack">${csrfField(c)}
<label>이름<input name="name" maxlength="40" value="${esc(c.site.name)}" required></label>
<label>소개<textarea name="about" maxlength="${LIMITS.about}">${esc(c.site.about)}</textarea></label>
<label>이용 규칙(비우면 기본 규칙)<textarea name="rules" maxlength="${LIMITS.rules}" rows="6">${esc(c.site.rules)}</textarea></label>
<label>개인정보 담당 연락처(이메일 등)<input name="contact" maxlength="${LIMITS.contact}" value="${esc(c.site.contact)}"></label><button>저장</button></form></section>
<section class="card"><h2>데이터 내보내기</h2><p class="meta">회원, 글, 댓글, 일정, 포인트를 JSON 파일로 받습니다. 커뮤니티를 옮기거나 닫을 때 보관용입니다(회원 정보가 들어 있으니 안전하게 보관).</p><a class="button ghost" href="/admin/export">내보내기</a></section>` : ""}`;
  return html(page(c.site, c, "관리", body));
}

async function adminAction(env, c, action) {
  const user = need(c, "mod");
  if (action === "dismiss") {
    await db.run(env, "UPDATE reports SET done = 1 WHERE kind = ? AND target = ?", String(field(c, "kind")), Number(field(c, "target")));
  } else if (action === "role") {
    const target = await db.one(env, "SELECT * FROM users WHERE id = ?", Number(field(c, "user")));
    const role = String(field(c, "role"));
    if (!target || target.role === "owner" || !["viewer", "mod", "banned"].includes(role)) throw new UserError("바꿀 수 없음");
    if (user.role !== "owner" && (role === "mod" || target.role === "mod")) throw new UserError("매니저 지정은 스트리머만", 403);
    await db.run(env, "UPDATE users SET role = ? WHERE id = ?", role, target.id);
    if (role === "banned") await db.run(env, "DELETE FROM sessions WHERE user_id = ?", target.id);
  } else if (action === "schedule-add") {
    await addSchedule(env, { day: Number(field(c, "day")), date: field(c, "date"), time: field(c, "time"), title: field(c, "title"), note: field(c, "note"), off: field(c, "off") === "1" });
  } else if (action === "schedule-remove") {
    await db.run(env, "DELETE FROM schedule WHERE id = ?", Number(field(c, "id")));
  } else if (action === "settings" && user.role === "owner") {
    await putSetting(env, "name", oneLine(field(c, "name"), 40, "이름"));
    await putSetting(env, "about", clean(field(c, "about"), LIMITS.about, "소개", false));
    await putSetting(env, "rules", clean(field(c, "rules"), LIMITS.rules, "이용 규칙", false));
    await putSetting(env, "contact", oneLine(field(c, "contact"), LIMITS.contact, "연락처", false));
  } else {
    throw new UserError("권한 없음", 403);
  }
  return redirect("/admin");
}

// 일정 하나 확인: [day, date, time, title, note, off]. 틀리면 UserError
export function checkSchedule(item) {
  item = item && typeof item === "object" ? item : {};
  const day = Number.isInteger(item.day) && item.day >= -1 && item.day <= 6 ? item.day : -1;
  const date = String(item.date || "");
  if (day === -1 && !/^\d{4}-\d\d-\d\d$/.test(date)) throw new UserError("매주 요일을 고르거나 날짜를 입력");
  if (day >= 0 && date) throw new UserError("매주 일정은 날짜 없이");
  const time = String(item.time || "");
  if (time && !/^\d\d:\d\d$/.test(time)) throw new UserError("시간은 21:00 형식");
  const off = Boolean(item.off);
  const title = off ? oneLine(item.title || "휴방", LIMITS.title, "제목", false) : oneLine(item.title, LIMITS.title, "방송 제목");
  const note = oneLine(item.note, 60, "메모", false);
  return [day, day >= 0 ? "" : date, time, title, note, off ? 1 : 0];
}

const INSERT_SCHEDULE = "INSERT INTO schedule (day, date, time, title, note, off) VALUES (?, ?, ?, ?, ?, ?)";

async function addSchedule(env, item) {
  await db.run(env, INSERT_SCHEDULE, ...checkSchedule(item));
}

// ------------------------------------------------------------------ debutkit API(Authorization: Bearer 토큰)

async function api(request, env, url) {
  const auth = request.headers.get("Authorization") || "";
  const given = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!given || !env.ADMIN_TOKEN_HASH || !sameText(await sha256(given), env.ADMIN_TOKEN_HASH)) return json({ error: "debutkit 토큰이 맞지 않음" }, 401);
  const path = url.pathname.slice(5);
  const body = request.method === "POST" ? await request.json().catch(() => ({})) : {};
  if (request.method === "GET" && path === "state") {
    const site = await settings(env);
    const count = async (sql, ...args) => (await db.one(env, sql, ...args))?.n || 0;
    return json({ name: site.name, users: await count("SELECT COUNT(*) AS n FROM users"), posts: await count("SELECT COUNT(*) AS n FROM posts WHERE hidden = 0"),
      reports: await count("SELECT COUNT(*) AS n FROM reports WHERE done = 0"), attended: await count("SELECT COUNT(*) AS n FROM users WHERE last_attend = ?", kstDay()),
      live: site.live, raffle: site.raffle, providers: site.providers, version: 1 });
  }
  if (request.method !== "POST") return json({ error: "없는 요청" }, 404);
  if (path === "settings") {
    if (body.name !== undefined) await putSetting(env, "name", oneLine(body.name, 40, "이름"));
    if (body.about !== undefined) await putSetting(env, "about", clean(body.about, LIMITS.about, "소개", false));
    if (body.contact !== undefined) await putSetting(env, "contact", oneLine(body.contact, LIMITS.contact, "연락처", false));
    if (body.owner_name !== undefined) await putSetting(env, "owner_name", oneLine(body.owner_name, LIMITS.name, "스트리머 이름"));
    if (body.theme && typeof body.theme === "object") {
      const theme = {};
      for (const key of ["primary", "highlight"]) if (/^#[0-9a-f]{6}$/i.test(body.theme[key] || "")) theme[key] = body.theme[key];
      await putSetting(env, "theme", theme);
    }
    if (body.providers !== undefined) await putSetting(env, "providers", String(body.providers).split(",").filter((key) => PROVIDERS[key]).join(","));
    return json({ ok: true });
  }
  if (path === "owner-link") {
    const code = token(24);
    await db.run(env, "INSERT INTO pending (code, kind, expires) VALUES (?, 'owner', ?)", await sha256(code), Date.now() + 10 * 60000);
    return json({ url: `${url.origin}/owner?code=${encodeURIComponent(code)}` });
  }
  if (path === "chat") return apiChat(env, body);
  if (path === "export") return json(await exportAll(env));
  if (path === "post") {
    const board = BOARDS[body.board] ? body.board : "notice";
    const owner = await account(env, "owner", "owner", (await settings(env)).owner_name || "스트리머", { role: "owner" });
    const title = oneLine(body.title, LIMITS.title, "제목");
    const text = clean(body.body, LIMITS.body, "내용", false);
    const link = oneLine(body.link, LIMITS.link, "주소", false);
    const made = await db.run(env, "INSERT INTO posts (board, user_id, title, body, link, pinned, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
      board, owner, title, text, safeLink(link) === "#" ? "" : link, body.pinned ? 1 : 0, Date.now());
    return json({ id: made.meta.last_row_id, url: `${url.origin}/p/${made.meta.last_row_id}` });
  }
  if (path === "schedule") {
    if (!Array.isArray(body.items) || body.items.length > 60) throw new UserError("일정은 60개까지의 목록");
    const rows = body.items.map(checkSchedule);  // 모두 확인한 뒤에 바꿈(틀린 일정 때문에 기존 일정이 지워지지 않게)
    await env.DB.batch([env.DB.prepare("DELETE FROM schedule"), ...rows.map((row) => env.DB.prepare(INSERT_SCHEDULE).bind(...row))]);
    return json({ ok: true, count: rows.length });
  }
  if (path === "live") {
    const live = { live: Boolean(body.live), title: oneLine(body.title, LIMITS.title, "제목", false), url: safeLink(body.url) === "#" ? "" : body.url, since: body.live ? Date.now() : 0 };
    await putSetting(env, "live", live);
    return json({ ok: true, live });
  }
  if (path === "raffle") {
    const raffle = { open: Boolean(body.open), title: oneLine(body.title, 40, "추첨 이름", false) };
    if (raffle.open && body.reset !== false) await db.run(env, "DELETE FROM raffle");
    await putSetting(env, "raffle", raffle);
    return json({ ok: true, raffle });
  }
  if (path === "raffle-entries") {
    const since = Number(body.since || 0);
    const rows = await db.all(env, "SELECT user_id AS id, name, created_at AS at FROM raffle WHERE created_at > ? ORDER BY created_at LIMIT 500", since);
    return json({ entries: rows });
  }
  if (path === "stage") {
    const rows = await db.all(env, `SELECT s.id, p.id AS post, p.board, p.title, p.body, p.image, u.name AS author FROM stage s JOIN posts p ON p.id = s.post_id
      LEFT JOIN users u ON u.id = p.user_id WHERE p.hidden = 0 ORDER BY s.id LIMIT 10`);
    if (rows.length) await db.run(env, "DELETE FROM stage WHERE id <= ?", rows[rows.length - 1].id);
    return json({ items: rows.map((r) => ({ post: r.post, board: r.board, title: r.title, body: String(r.body).slice(0, 200), author: r.author || "",
      image: r.image ? `${url.origin}/img/${r.image}` : "", url: `${url.origin}/p/${r.post}` })) });
  }
  return json({ error: "없는 요청" }, 404);
}

// 방송 채팅 명령: !인증 숫자(계정 연결), !출석(포인트). debutkit이 채팅을 보고 보냄
async function apiChat(env, body) {
  const platform = String(body.platform || "");
  if (!CHAT_PLATFORMS[platform]) throw new UserError("플랫폼은 chzzk, soop, twitch, youtube");
  const name = oneLine(body.name, 40, "닉네임");
  const subject = String(body.user || "").slice(0, 64) || `name:${name}`;
  const role = body.role === "owner" ? "owner" : body.role === "moderator" ? "mod" : "";
  if (body.command === "verify") {
    const code = String(body.code || "").trim();
    const row = /^\d{6}$/.test(code) ? await db.one(env, "SELECT * FROM pending WHERE code = ? AND kind = 'chat' AND expires > ?", code, Date.now()) : null;
    if (!row) return json({ ok: false, reason: "없는 인증 숫자" });
    await db.run(env, "UPDATE pending SET provider = ?, subject = ?, name = ?, role = ? WHERE code = ?", platform, subject, name, role, code);
    return json({ ok: true });
  }
  if (body.command === "attend") {
    const found = await db.one(env, "SELECT u.* FROM identities i JOIN users u ON u.id = i.user_id WHERE i.provider = ? AND i.subject = ?", platform, subject);
    if (!found || found.role === "banned") return json({ ok: false, linked: false });
    const given = await award(env, found.id, "chat");
    return json({ ok: true, linked: true, name: found.name, given, points: found.points + given });
  }
  throw new UserError("없는 채팅 명령");
}

// 전체 데이터(로그인 상태, 대기 코드 제외). 그림은 주소만(파일은 /img/ 에서)
export async function exportAll(env) {
  const tables = ["settings", "users", "identities", "posts", "comments", "likes", "reports", "schedule", "points"];
  const found = { exported_at: new Date().toISOString(), format: "debutkit-community-1" };
  for (const table of tables) found[table] = await db.all(env, `SELECT * FROM ${table}`);
  return found;
}

async function image(env, key) {
  if (!/^[A-Za-z0-9_-]{8,64}$/.test(key)) return new Response("없음", { status: 404 });
  const found = await env.FILES.getWithMetadata(key, { type: "arrayBuffer" });
  if (!found || !found.value) return new Response("없음", { status: 404 });
  const type = ["image/png", "image/jpeg", "image/gif", "image/webp"].includes(found.metadata?.type) ? found.metadata.type : "application/octet-stream";
  return new Response(found.value, { headers: { "Content-Type": type, "Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox" } });
}

// ------------------------------------------------------------------ 모양과 동작

const CSS = `*{box-sizing:border-box}body{margin:0;background:#f5f2ee;color:#1e2327;font:15px/1.6 "Pretendard","Malgun Gothic","Apple SD Gothic Neo",sans-serif}
a{color:inherit}header{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;padding:10px 18px;background:#1e2327;color:#faf7f5}
.brand{font-weight:800;font-size:18px;text-decoration:none}header nav{display:flex;flex-wrap:wrap;gap:4px 12px}header nav a{text-decoration:none;opacity:.85}header nav a:hover{opacity:1}
.account{margin-left:auto;display:flex;gap:10px;align-items:center}.account a{text-decoration:none}.me small{opacity:.7}
.live{padding:2px 10px;border-radius:999px;background:var(--accent);color:#fff;font-weight:700;text-decoration:none;animation:pulse 2s infinite}
@keyframes pulse{50%{opacity:.75}}main{max-width:980px;margin:0 auto;padding:18px 14px 40px}footer{text-align:center;color:#6b747b;font-size:13px;padding:20px}
.card{background:#fff;border:1px solid #e3dfdb;border-radius:8px;padding:16px 18px;margin-bottom:14px}.card h1{font-size:22px;margin:0 0 10px}.card h2{font-size:16px;margin:0 0 8px}
.card h2 a{text-decoration:none}.hero{border-top:5px solid var(--accent)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}.grid .card{margin:0 0 14px}
.posts{list-style:none;padding:0;margin:0}.posts li{display:flex;flex-wrap:wrap;align-items:center;gap:2px 10px;padding:8px 0;border-bottom:1px solid #f0ece8}.posts li a{text-decoration:none;font-weight:600;flex:1 1 60%}
.meta{color:#6b747b;font-size:13px}.pin{display:inline-block;margin-right:6px;padding:0 6px;border-radius:4px;background:var(--accent);color:#fff;font-size:12px}
.thumb{width:44px;height:44px;object-fit:cover;border-radius:4px}.empty{color:#8a9299}.days{list-style:none;padding:0;margin:0}.days li{display:flex;flex-wrap:wrap;gap:4px 12px;padding:6px 0;border-bottom:1px solid #f0ece8}
.days b{min-width:70px}.off{color:#a4442f}.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px}.gallery a{display:block;text-decoration:none}
.gallery img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:6px;background:#eee}.gallery.big span{display:block;font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:8px}.stack{display:grid;gap:10px}.stack label{display:grid;gap:4px;font-size:14px;color:#3a4249}
.check{display:flex!important;align-items:center;gap:6px}input,select,textarea{font:inherit;padding:7px 9px;border:1px solid #cfc8c1;border-radius:5px;background:#fff;min-width:0}
textarea{min-height:90px}button,.button{display:inline-block;padding:7px 14px;border:1px solid var(--accent);border-radius:5px;background:var(--accent);color:#fff;font:inherit;font-weight:700;cursor:pointer;text-decoration:none}
button:disabled{opacity:.5;cursor:default}.ghost{background:#fff;color:#1e2327;border-color:#cfc8c1;font-weight:600}.danger{color:#b3261e}.inline{display:inline}
.head{display:flex;justify-content:space-between;align-items:center}.post .art{max-width:100%;border-radius:6px;margin:8px 0}.body{word-break:break-word}.tools{border-top:1px solid #f0ece8;padding-top:10px}
.comments{list-style:none;padding:0;margin:0 0 12px}.comments li{padding:8px 0;border-bottom:1px solid #f0ece8}.comments p{margin:4px 0}.comments .hidden{opacity:.5}
.rank{padding-left:22px}.rank li{padding:5px 0}.rank span{float:right;font-weight:700}.center{text-align:center}.code{font-size:34px;font-weight:800;letter-spacing:.06em;color:var(--accent);margin:12px 0}
.raffle{border:2px solid var(--gold)}.users li{padding:4px 0}`;

const SCRIPT = `document.addEventListener("submit",function(e){var f=e.target;if(f.dataset.confirm&&!confirm(f.dataset.confirm)){e.preventDefault();return}
if(f.dataset.ask){var r=prompt(f.dataset.ask,"");if(r===null){e.preventDefault();return}var i=document.createElement("input");i.type="hidden";i.name="reason";i.value=r;f.appendChild(i)}});
var w=document.getElementById("chat-wait");if(w){var t=setInterval(function(){fetch(w.dataset.check,{headers:{Accept:"application/json"},credentials:"same-origin"}).then(function(r){return r.json()}).then(function(d){
if(d.done){clearInterval(t);location.href=d.next||"/"}else if(d.error||d.expired){clearInterval(t);document.getElementById("chat-state").textContent=d.error||"시간이 지남: 다시 시도"}})},2500)}`;
