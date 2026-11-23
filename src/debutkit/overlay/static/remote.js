// debutkit 휴대폰 조작 화면: 등록한 휴대폰에서 시청자 참여 추첨, 3D 캐릭터 동작을 조작하고 후원 추첨 결과를 본다.
// QR 주소의 # 뒤(기기 번호, 비밀값)는 서버로 보내지 않고 이 브라우저에만 저장한다. 요청마다 비밀값으로 서명(remote-sign.js).

import { confirmCode, nonce, sign } from "/remote-sign.js";

const STORE = "debutkit-remote";
const $ = (id) => document.getElementById(id);
let device = null;
let timer = 0;
let snapshot = null;

function load() {
  const params = new URLSearchParams(location.hash.slice(1));
  if (params.get("d") && params.get("k")) {
    device = { id: params.get("d"), key: params.get("k") };
    try { localStorage.setItem(STORE, JSON.stringify(device)); } catch (error) { /* 저장할 수 없는 브라우저(사생활 보호 모드): 이번 접속만 사용 */ }
    history.replaceState(null, "", location.pathname);  // 주소 표시줄과 방문 기록에서 비밀값 제거
    return;
  }
  try { device = JSON.parse(localStorage.getItem(STORE) || "null"); } catch (error) { device = null; }
}

function forget(message) {
  try { localStorage.removeItem(STORE); } catch (error) { /* 무시 */ }
  device = null;
  clearTimeout(timer);
  show("need");
  if (message) $("need-text").textContent = message;
}

function show(name) {
  for (const id of ["need", "wait", "panel"]) $(id).hidden = id !== name;
  $("forget").hidden = name === "need";
}

function toast(text) {
  const box = $("toast");
  box.textContent = text;
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (box.hidden = true), 3200);
}

async function call(method, path, body) {
  const text = body === undefined ? "" : JSON.stringify(body);
  const stamp = String(Date.now());
  const once = nonce();
  const headers = { "X-Debutkit-Device": device.id, "X-Debutkit-Time": stamp, "X-Debutkit-Nonce": once,
                    "X-Debutkit-Sign": sign(device.key, method, path, stamp, once, text) };
  if (text) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { method, headers, body: text || undefined, cache: "no-store" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `요청 실패(${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function deviceName() {
  const agent = navigator.userAgent;
  return /iPhone/.test(agent) ? "iPhone" : /iPad/.test(agent) ? "iPad" : /Android/.test(agent) ? "Android 휴대폰" : "휴대폰";
}

async function hello() {
  clearTimeout(timer);
  try {
    const answer = await call("POST", "/remote/api/hello", { name: deviceName() });
    $("device-name").textContent = answer.name;
    if (!answer.approved) {
      $("code").textContent = answer.code || confirmCode(device.key);
      show("wait");
      timer = setTimeout(hello, 2000);
      return;
    }
    show("panel");
    refresh();
  } catch (error) {
    if (error.status === 401 && !/시각/.test(error.message)) return forget(`${error.message}. 이 휴대폰의 연결 정보를 지웠습니다.`);
    $("need-text").textContent = error.message;
    show("need");
    timer = setTimeout(hello, 4000);
  }
}

async function refresh() {
  clearTimeout(timer);
  try {
    render(await call("GET", "/remote/api/status"));
  } catch (error) {
    if (error.status === 401 || error.status === 403) return hello();
    toast(`PC에 연결하지 못함: ${error.message}`);
  }
  timer = setTimeout(refresh, 2000);
}

function render(data) {
  snapshot = data;
  const raffle = data.raffle;
  const state = $("raffle-state");
  state.textContent = raffle.open ? `모집 중: 채팅 ${raffle.keyword}, 참가 ${raffle.count}명` : `모집 마감, 참가 ${raffle.count}명`;
  state.className = raffle.open ? "state ok" : "state";
  $("raffle-start").disabled = raffle.open;
  $("raffle-stop").disabled = !raffle.open;
  $("raffle-pick").disabled = $("raffle-order").disabled = raffle.count === 0;
  const result = raffle.last_result;
  const box = $("raffle-result");
  box.replaceChildren();
  if (result) {
    const title = document.createElement("p");
    title.className = "state";
    title.textContent = `${result.mode === "order" ? "순서" : "당첨"}(참가 ${result.total}명)`;
    const list = document.createElement(result.mode === "order" ? "ol" : "ul");
    for (const winner of result.winners) {
      const item = document.createElement("li");
      item.textContent = winner.name;
      list.appendChild(item);
    }
    box.append(title, list);
  }
  const motions = $("motions");
  const buttons = data.motions.map((item) => {
    const button = document.createElement("button");
    button.className = "secondary";
    button.textContent = item.name;
    button.addEventListener("click", () => act("/remote/api/motion", { id: item.id }, `${item.name} 실행`));
    return button;
  });
  if (data.motions.length) {
    const stop = document.createElement("button");
    stop.textContent = "동작 멈춤";
    stop.addEventListener("click", () => act("/remote/api/motion", { stop: true }, "동작 멈춤"));
    buttons.push(stop);
  }
  if (motions.childElementCount !== buttons.length) motions.replaceChildren(...buttons);
  $("motions-empty").hidden = data.motions.length > 0;
  const draws = $("draws");
  draws.replaceChildren(...(data.draws.length ? data.draws.map((item) => {
    const entry = document.createElement("div");
    entry.className = "draw";
    const who = document.createElement("b");
    who.textContent = `${item.name}${item.test ? "(시험)" : ""}`;
    const script = document.createElement("p");
    script.textContent = item.script;
    entry.append(who, script);
    return entry;
  }) : [Object.assign(document.createElement("p"), { className: "dim", textContent: "아직 결과가 없습니다." })]));
}

async function act(path, body, done) {
  try {
    render(await call("POST", path, body));
    toast(done);
  } catch (error) {
    if (error.status === 401 || error.status === 403) return hello();
    toast(error.message);
  }
}

function confirmTwice(button, run) {  // 다시 눌러야 실행(3초 안)
  button.addEventListener("click", () => {
    if (button.classList.contains("armed")) {
      button.classList.remove("armed");
      button.textContent = button.dataset.label;
      run();
      return;
    }
    button.dataset.label = button.textContent;
    button.classList.add("armed");
    button.textContent = "다시 눌러 확정";
    setTimeout(() => {
      if (button.classList.contains("armed")) {
        button.classList.remove("armed");
        button.textContent = button.dataset.label;
      }
    }, 3000);
  });
}

$("raffle-start").addEventListener("click", () => act("/remote/api/raffle/start", {}, "모집 시작"));
$("raffle-stop").addEventListener("click", () => act("/remote/api/raffle/stop", {}, "모집 마감"));
confirmTwice($("raffle-pick"), () => {
  const count = Math.max(1, Math.min(30, parseInt($("raffle-count").value, 10) || 1));
  act("/remote/api/raffle/draw", { mode: "pick", count }, `당첨자 ${count}명 뽑기`);
});
confirmTwice($("raffle-order"), () => act("/remote/api/raffle/draw", { mode: "order" }, "순서 정하기"));
$("forget").addEventListener("click", () => forget("이 휴대폰의 연결 정보를 지웠습니다. 다시 연결할 때는 PC 화면의 QR 코드를 찍으십시오."));
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && device) hello(); });

load();
if (device) hello(); else show("need");
window.debutkitRemote = { render, call, get snapshot() { return snapshot; } };  // 시험용
