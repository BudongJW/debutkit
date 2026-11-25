// debutkit 실시간 항목 공유 연결(SharedWorker): 같은 브라우저(OBS 브라우저 소스끼리 포함)의 여러 화면이 /live 연결 하나를 함께 쓴다.
// 브라우저는 같은 주소에 동시 연결을 6개까지만 열어, 화면마다 연결을 열면 방송 연출 화면이 늘었을 때 일부 화면이 멈춘다.
// 화면(live.js)이 받을 항목을 알려 오면 모든 화면이 원하는 항목을 합쳐 연결을 하나만 유지하고, 받은 값을 원하는 화면에만 나눠 준다.
// 연결(다시 연결 포함) 직후 항목마다 처음 오는 값은 현재 상태라 initial 표시를 붙인다(화면은 지난 연출을 다시 재생하지 않음).
// 나중에 연 화면에는 항목마다 마지막 값을 initial로 보낸다. events(채팅, 후원)는 최근 30개 목록으로.
// 무대 차례(cue): 화면 가운데를 크게 쓰는 연출이 겹치지 않도록 먼저 요청한 화면부터 하나씩 허락한다(live.js의 cue).
"use strict";

const CUE_LIMIT = 40000;  // 한 연출이 무대를 잡을 수 있는 최대 시간(ms). 화면이 멈추거나 닫혀도 다음 차례로
const cues = [];  // 기다리는 차례 {port, id}
let holder = null;  // 지금 무대를 쓰는 차례 {port, id, at}

const HISTORY = 30;
const ports = new Map();  // 화면 연결 -> 받을 항목 Set
const last = new Map();  // 항목 -> 마지막 값
const fresh = new Set();  // 연결 뒤 아직 첫 값을 받지 않은 항목
let history = [];
let source = null;
let joined = "";
let opened = false;

function union() {
  const all = new Set();
  for (const feeds of ports.values()) for (const feed of feeds) all.add(feed);
  return [...all].sort();
}

function send(port, message) {
  try { port.postMessage(message); } catch (error) { ports.delete(port); }
}

function remember(feed, data, initial) {
  if (feed !== "events") {
    last.set(feed, data);
    return data;
  }
  if (initial && Array.isArray(data.history)) history = data.history.slice(-HISTORY);
  else history = [...history, { ...data, replay: true }].slice(-HISTORY);
  return data;
}

function deliver(feed, data) {
  const initial = fresh.delete(feed);
  remember(feed, data, initial);
  for (const [port, feeds] of ports) if (feeds.has(feed)) send(port, { feed, data, initial });
}

function snapshot(feed) {
  if (feed === "events") return { history };
  return last.get(feed);
}

function connect() {
  const wanted = union();
  const key = wanted.join(",");
  if (key === joined) return;
  joined = key;
  if (source) source.close();
  source = null;
  opened = false;
  if (!wanted.length) return;
  source = new EventSource(`/live?feeds=${encodeURIComponent(key)}`);
  for (const feed of wanted) {
    source.addEventListener(feed, (event) => {
      try { deliver(feed, JSON.parse(event.data)); } catch (error) { /* 잘못된 값은 버림 */ }
    });
  }
  source.onopen = () => {
    opened = true;
    for (const feed of wanted) fresh.add(feed);
    for (const port of ports.keys()) send(port, { state: "open" });
  };
  source.onerror = () => {
    opened = false;
    for (const port of ports.keys()) send(port, { state: "retry" });
  };
}

function grant() {
  if (holder && Date.now() - holder.at > CUE_LIMIT) holder = null;
  while (!holder && cues.length) {
    const next = cues.shift();
    if (!ports.has(next.port)) continue;
    holder = { ...next, at: Date.now() };
    send(next.port, { cue: next.id });
  }
}

function release(port, id) {
  if (holder && holder.port === port && (id === undefined || holder.id === id)) holder = null;
  for (let index = cues.length - 1; index >= 0; index -= 1) {
    if (cues[index].port === port && (id === undefined || cues[index].id === id)) cues.splice(index, 1);
  }
  grant();
}

setInterval(grant, 2000);

self.onconnect = (event) => {
  const port = event.ports[0];
  ports.set(port, new Set());
  port.onmessage = (message) => {
    const request = message.data || {};
    if (request.close) {
      ports.delete(port);
      release(port);
      connect();
      return;
    }
    if (typeof request.cue === "string") {
      cues.push({ port, id: request.cue });
      grant();
      return;
    }
    if (typeof request.release === "string") {
      release(port, request.release);
      return;
    }
    if (Array.isArray(request.subscribe)) {
      const feeds = ports.get(port) || new Set();
      const added = request.subscribe.filter((feed) => /^[a-z]{2,20}$/.test(feed) && !feeds.has(feed));
      for (const feed of added) feeds.add(feed);
      ports.set(port, feeds);
      const before = joined;
      connect();
      send(port, { state: opened ? "open" : "connecting" });
      if (joined === before) {  // 이미 받는 항목: 기억한 값을 바로. 새 연결이면 서버가 현재 값을 보낸다
        for (const feed of added) {
          const value = snapshot(feed);
          if (value !== undefined && !fresh.has(feed)) send(port, { feed, data: value, initial: true });
        }
      }
    }
  };
  port.start();
};
