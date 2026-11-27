// debutkit 커뮤니티 Worker 시험(Node 22.5 이상, node --test). pytest의 test_community.py가 함께 실행한다.
import assert from "node:assert/strict";
import { test } from "node:test";
import worker, { BOARDS, esc, imageType, level, richText } from "../src/debutkit/community/worker/worker.js";
import { fakeEnv } from "../src/debutkit/community/worker/local.mjs";

const ORIGIN = "https://fan.example.workers.dev";
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]);

// 브라우저 하나: 쿠키를 기억하고 화면의 CSRF 값을 꺼내 쓴다
function browser(env) {
  const jar = new Map();
  let csrf = "";
  async function send(path, { method = "GET", form = null, headers = {} } = {}) {
    const cookie = [...jar].map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("; ");
    let body;
    if (form) {
      body = new FormData();
      for (const [key, value] of Object.entries({ _csrf: csrf, ...form })) body.append(key, value);
    }
    const response = await worker.fetch(new Request(ORIGIN + path, { method, body, headers: { Cookie: cookie, Origin: ORIGIN, ...headers } }), env);
    for (const line of response.headers.getSetCookie()) {
      const [pair] = line.split(";");
      const [key, ...rest] = pair.split("=");
      const value = decodeURIComponent(rest.join("="));
      if (/Max-Age=0/.test(line)) jar.delete(key); else jar.set(key, value);
    }
    const text = response.headers.get("Content-Type")?.startsWith("text/html") ? await response.text() : null;
    const found = text && text.match(/name="_csrf" value="([^"]+)"/);
    if (found) csrf = found[1];
    return { response, text, jar };
  }
  return { send, jar, get csrf() { return csrf; }, set csrf(value) { csrf = value; } };
}

async function api(env, path, body, token = "dev-token") {
  const response = await worker.fetch(new Request(`${ORIGIN}/api/${path}`, {
    method: body === undefined ? "GET" : "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }), env);
  return { status: response.status, data: await response.json() };
}

// 채팅 인증으로 가입: 브라우저가 숫자를 받고, debutkit이 채팅에서 본 숫자를 알리면 로그인
async function joinByChat(env, { platform = "chzzk", user = "abc123", name = "도토리", role = "" } = {}) {
  const b = browser(env);
  await b.send("/login");
  const started = await b.send("/login/chat", { method: "POST", form: { agree: "1", age: "1" } });
  assert.equal(started.response.status, 303);
  const wait = await b.send("/login/chat");
  const code = wait.text.match(/!인증 (\d{6})/)[1];
  assert.equal((await api(env, "chat", { command: "verify", platform, user, name, role, code })).data.ok, true);
  const check = await b.send("/login/chat-check", { headers: { Accept: "application/json" } });
  assert.equal((await check.response.json()).done, true);
  assert.ok(b.jar.has("dk"));
  return b;
}

test("escape and safe text", () => {
  assert.equal(esc(`<img src=x onerror="a">'`), "&lt;img src=x onerror=&quot;a&quot;&gt;&#39;");
  const rendered = richText("hi <script>alert(1)</script>\njavascript:alert(1) https://chzzk.naver.com/a?b=1");
  assert.ok(!rendered.includes("<script>") && rendered.includes("&lt;script&gt;") && rendered.includes("<br>"));
  assert.ok(rendered.includes('<a href="https://chzzk.naver.com/a?b=1"') && !rendered.includes('href="javascript'));
  assert.equal(imageType(PNG), "image/png");
  assert.equal(imageType(new TextEncoder().encode("<svg onload=1>")), "");
  assert.equal(level(0), "새싹");
  assert.equal(level(2500), "전설");
  assert.deepEqual(Object.keys(BOARDS), ["notice", "free", "fanart", "qna", "clips"]);
});

test("debutkit API needs the token", async () => {
  const env = await fakeEnv();
  assert.equal((await api(env, "state", undefined, "wrong")).status, 401);
  const state = await api(env, "state");
  assert.equal(state.status, 200);
  assert.equal(state.data.users, 0);
});

test("chat verification signs up, links and gives attendance points", async () => {
  const env = await fakeEnv();
  const b = await joinByChat(env);
  const me = await b.send("/me");
  assert.match(me.text, /도토리/);
  assert.match(me.text, /치지직/);
  // 출석: 하루 한 번, 방송 채팅 출석은 따로 한 번
  await b.send("/attend", { method: "POST", form: {} });
  await b.send("/attend", { method: "POST", form: {} });
  const chat1 = await api(env, "chat", { command: "attend", platform: "chzzk", user: "abc123", name: "도토리닉변경" });
  const chat2 = await api(env, "chat", { command: "attend", platform: "chzzk", user: "abc123", name: "도토리" });
  assert.equal(chat1.data.given, 10);
  assert.equal(chat2.data.given, 0);
  assert.equal((await api(env, "chat", { command: "attend", platform: "soop", user: "nobody", name: "x" })).data.linked, false);
  const user = await env.DB.prepare("SELECT points, streak FROM users").bind().first();
  assert.deepEqual(user, { points: 20, streak: 1 });
  // 틀린 숫자, 다른 사람이 이미 연결한 채팅 계정
  assert.equal((await api(env, "chat", { command: "verify", platform: "chzzk", user: "x", name: "x", code: "000000" })).data.ok, false);
});

test("same chat account cannot be linked to a second member", async () => {
  const env = await fakeEnv();
  await joinByChat(env, { platform: "youtube", user: "UC1", name: "첫째" });
  const other = await joinByChat(env, { platform: "twitch", user: "777", name: "둘째" });
  await other.send("/me");
  await other.send("/login/chat", { method: "POST", form: { agree: "1", age: "1" } });
  const wait = await other.send("/login/chat");
  const code = wait.text.match(/!인증 (\d{6})/)[1];
  await api(env, "chat", { command: "verify", platform: "youtube", user: "UC1", name: "첫째", code });
  const check = await other.send("/login/chat-check", { headers: { Accept: "application/json" } });
  assert.equal(check.response.status, 409);
  assert.match((await check.response.json()).error, /이미 다른/);
});

test("posts, comments, likes, reports, moderation and stage", async () => {
  const env = await fakeEnv();
  const viewer = await joinByChat(env, { user: "v1", name: "시청자" });
  await viewer.send("/write?board=free");
  const made = await viewer.send("/write", { method: "POST", form: { board: "free", title: "<b>안녕</b>", body: "첫 글 <script>x</script>" } });
  assert.equal(made.response.status, 303);
  const postPath = made.response.headers.get("Location");
  const page = await viewer.send(postPath);
  assert.ok(page.text.includes("&lt;b&gt;안녕&lt;/b&gt;") && !page.text.includes("<script>x"));
  const id = postPath.split("/").pop();
  await viewer.send(`/p/${id}/comment`, { method: "POST", form: { body: "댓글" } });
  await viewer.send(`/p/${id}/like`, { method: "POST", form: {} });
  await viewer.send(`/p/${id}/like`, { method: "POST", form: {} });
  const row = await env.DB.prepare("SELECT likes, comments FROM posts WHERE id = ?").bind(Number(id)).first();
  assert.deepEqual(row, { likes: 1, comments: 1 });
  // 공지는 매니저 이상만
  const notice = await viewer.send("/write", { method: "POST", form: { board: "notice", title: "공지", body: "x" } });
  assert.equal(notice.response.status, 403);
  // CSRF 값이 없거나 다른 사이트 요청은 거절
  const saved = viewer.csrf;
  viewer.csrf = "nope";
  assert.equal((await viewer.send("/write", { method: "POST", form: { board: "free", title: "t", body: "b" } })).response.status, 403);
  viewer.csrf = saved;
  assert.equal((await viewer.send("/attend", { method: "POST", form: {}, headers: { Origin: "https://evil.example" } })).response.status, 403);
  // 매니저(채팅 매니저 역할로 인증)가 신고 확인, 가리기, 방송에 띄우기
  const reporter = await joinByChat(env, { user: "r1", name: "신고자" });
  await reporter.send(`/p/${id}`);
  await reporter.send(`/p/${id}/report`, { method: "POST", form: { reason: "광고" } });
  const mod = await joinByChat(env, { user: "m1", name: "매니저", role: "moderator" });
  const adminPage = await mod.send("/admin");
  assert.match(adminPage.text, /신고 1/);
  await mod.send(`/p/${id}/stage`, { method: "POST", form: {} });
  const stage = await api(env, "stage", {});
  assert.equal(stage.data.items.length, 1);
  assert.equal(stage.data.items[0].title, "<b>안녕</b>");
  assert.equal((await api(env, "stage", {})).data.items.length, 0);
  await mod.send(`/p/${id}/hide`, { method: "POST", form: {} });
  assert.equal((await reporter.send(`/p/${id}`)).response.status, 404);
  assert.equal((await mod.send("/admin")).text.includes("신고 0"), true);
  // 정지한 사람은 글을 못 씀
  const target = await env.DB.prepare("SELECT id FROM users WHERE name = '신고자'").bind().first();
  await env.DB.prepare("UPDATE users SET role = 'banned' WHERE id = ?").bind(target.id).run();
  assert.equal((await reporter.send("/write", { method: "POST", form: { board: "free", title: "t", body: "b" } })).response.status, 403);
});

test("fan art needs a real image and is served safely", async () => {
  const env = await fakeEnv();
  const b = await joinByChat(env);
  await b.send("/write?board=fanart");
  const noImage = await b.send("/write", { method: "POST", form: { board: "fanart", title: "그림", body: "" } });
  assert.equal(noImage.response.status, 400);
  const fake = await b.send("/write", { method: "POST", form: { board: "fanart", title: "그림", image: new File([new TextEncoder().encode("<svg/>")], "a.svg", { type: "image/svg+xml" }) } });
  assert.equal(fake.response.status, 400);
  const ok = await b.send("/write", { method: "POST", form: { board: "fanart", title: "그림", image: new File([PNG], "a.png", { type: "image/png" }) } });
  assert.equal(ok.response.status, 303);
  const post = await env.DB.prepare("SELECT image FROM posts").bind().first();
  const served = await worker.fetch(new Request(`${ORIGIN}/img/${post.image}`), env);
  assert.equal(served.headers.get("Content-Type"), "image/png");
  assert.match(served.headers.get("Content-Security-Policy"), /sandbox/);
});

test("owner link, notices, schedule, live, raffle", async () => {
  const env = await fakeEnv();
  await api(env, "settings", { name: "도토리 커뮤니티", owner_name: "도토리", theme: { primary: "#19b8b0", highlight: "#c9a86a" }, providers: "discord,evil" });
  const link = (await api(env, "owner-link", {})).data.url;
  const owner = browser(env);
  const entered = await owner.send(new URL(link).pathname + new URL(link).search);
  assert.equal(entered.response.status, 303);
  assert.match((await owner.send("/admin")).text, /커뮤니티 설정/);
  assert.equal((await browser(env).send(new URL(link).pathname + new URL(link).search)).response.status, 403);  // 한 번만
  const notice = await api(env, "post", { board: "notice", title: "오늘 방송 쉽니다", body: "내일 봐요", pinned: true });
  assert.ok(notice.data.url.endsWith(`/p/${notice.data.id}`));
  const today = new Date(Date.now() + 9 * 3600000);
  const weekday = (today.getUTCDay() + 6) % 7;
  const schedule = await api(env, "schedule", { items: [{ day: weekday, time: "20:00", title: "저녁 게임 방송" }, { day: -1, date: "2099-01-01", off: true }] });
  assert.equal(schedule.data.count, 2);
  assert.equal((await api(env, "schedule", { items: [{ day: 9, time: "x", title: "" }] })).status, 400);
  await api(env, "live", { live: true, title: "발로란트", url: "https://chzzk.naver.com/live/x" });
  const home = await owner.send("/");
  assert.ok(home.text.includes("도토리 커뮤니티") && home.text.includes("오늘 방송 쉽니다") && home.text.includes("저녁 게임 방송") && home.text.includes("방송 중"));
  assert.ok(home.text.includes("--accent:#19b8b0"));
  assert.equal((await api(env, "state")).data.providers, "discord");
  // 참여 추첨: 열면 커뮤니티에 참가 버튼, debutkit이 참가자를 가져감
  await api(env, "raffle", { open: true, title: "굿즈 추첨" });
  const viewer = await joinByChat(env, { user: "v9", name: "참가자" });
  await viewer.send("/");
  await viewer.send("/raffle", { method: "POST", form: {} });
  await viewer.send("/raffle", { method: "POST", form: {} });
  const entries = await api(env, "raffle-entries", { since: 0 });
  assert.deepEqual(entries.data.entries.map((e) => e.name), ["참가자"]);
});

test("leaving removes the account but keeps posts anonymous", async () => {
  const env = await fakeEnv();
  const b = await joinByChat(env, { user: "bye", name: "떠나는사람" });
  await b.send("/write?board=free");
  const made = await b.send("/write", { method: "POST", form: { board: "free", title: "남는 글", body: "x" } });
  await b.send("/me");
  await b.send("/me/leave", { method: "POST", form: {} });
  assert.equal((await env.DB.prepare("SELECT COUNT(*) AS n FROM users").bind().first()).n, 0);
  assert.equal((await env.DB.prepare("SELECT COUNT(*) AS n FROM identities").bind().first()).n, 0);
  const page = await browser(env).send(made.response.headers.get("Location"));
  assert.match(page.text, /탈퇴한 사용자/);
});

test("hidden post tells its author, owner can export everything", async () => {
  const env = await fakeEnv();
  const author = await joinByChat(env, { user: "a1", name: "작성자" });
  await author.send("/write?board=free");
  const made = await author.send("/write", { method: "POST", form: { board: "free", title: "문제 글", body: "x" } });
  const path = made.response.headers.get("Location");
  await env.DB.prepare("UPDATE posts SET hidden = 1").bind().run();
  const seen = await author.send(path);
  assert.equal(seen.response.status, 200);
  assert.match(seen.text, /임시 조치/);
  assert.equal((await browser(env).send(path)).response.status, 404);
  const link = (await api(env, "owner-link", {})).data.url;
  const owner = browser(env);
  await owner.send(new URL(link).pathname + new URL(link).search);
  const exported = await owner.send("/admin/export");
  const data = JSON.parse(await exported.response.text());
  assert.equal(data.format, "debutkit-community-1");
  assert.equal(data.posts.length, 1);
  assert.ok(!("sessions" in data) && !("pending" in data));
  assert.equal((await author.send("/admin/export")).response.status, 403);
  assert.equal((await api(env, "export", {})).data.users.length, 2);
});
