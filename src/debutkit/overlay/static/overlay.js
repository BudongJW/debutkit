// debutkit overlay: 채팅, 후원 사건(/live의 events, 공유 연결 live.js)을 받아 채팅창과 알림을 표시한다. 글은 textContent로만 넣는다.
// live.js가 없으면 /events 에 직접 연결한다. 방송 색(theme)도 같은 연결로 받아 새로고침 없이 바꾼다.
"use strict";

const PLATFORMS = {
  chzzk: { label: "치지직", color: "#00d68f" },
  soop: { label: "SOOP", color: "#3d7bff" },
  twitch: { label: "Twitch", color: "#9146ff" },
  youtube: { label: "YouTube", color: "#ff0033" },
  demo: { label: "테스트", color: "#ff4f8b" },
  system: { label: "알림", color: "#8a8499" },
};

const params = new URLSearchParams(location.search);
const option = (name, fallback) => params.get(name) ?? fallback;
const number = (name, fallback) => {
  const value = Number(params.get(name));
  return Number.isFinite(value) && params.has(name) ? value : fallback;
};

function renderParts(target, parts) {
  for (const part of parts || []) {
    if (part.type === "emote" && typeof part.value === "string" && part.value.startsWith("https://")) {
      const img = document.createElement("img");
      img.className = "emote";
      img.src = part.value;
      img.alt = "";
      img.referrerPolicy = "no-referrer";
      target.appendChild(img);
    } else if (part.type === "text") {
      target.appendChild(document.createTextNode(String(part.value)));
    }
  }
}

function amountText(event) {
  if (!event.amount) return "";
  const n = Number(event.amount).toLocaleString("ko-KR");
  return event.unit === "원" ? `${n}원` : `${n} ${event.unit}`;
}

function badge(event) {
  const info = PLATFORMS[event.platform] || PLATFORMS.system;
  const el = document.createElement("span");
  el.className = "platform";
  el.textContent = info.label;
  el.style.setProperty("--platform", info.color);
  return el;
}

function connect(onEvent) {
  if (window.debutkitLive) {
    // 처음 값은 최근 사건 목록. 다른 화면 때문에 공유 연결이 다시 열려도 목록은 처음 한 번만 그린다(줄 중복 방지)
    let replayed = false;
    return window.debutkitLive.subscribe(["events", "theme"], (feed, data, initial) => {
      if (feed !== "events") return;
      if (Array.isArray(data.history)) {
        if (!replayed) for (const event of data.history) onEvent({ ...event, replay: true });
        replayed = true;
        return;
      }
      if (!initial) onEvent(data);
    });
  }
  const source = new EventSource("/events");
  source.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data));
    } catch (error) {
      console.warn("debutkit: 잘못된 사건", error);
    }
  };
  return () => source.close();
}

// 시청자마다 다른 이름 색(?names=viewer): 이름에서 정한 색(같은 이름은 항상 같은 색)
const VIEWER_COLORS = ["#ff8fb1", "#8fd3ff", "#ffd36e", "#9ff0b8", "#c8a8ff", "#ffb38a", "#7fe3e0", "#f5a3e6", "#b9e769", "#ffa3a3", "#a3c4ff", "#f0d08a"];
function viewerColor(name) {
  let hash = 0;
  for (const ch of String(name)) hash = (hash * 31 + ch.codePointAt(0)) >>> 0;
  return VIEWER_COLORS[hash % VIEWER_COLORS.length];
}

// 방송 스타일 묶음을 화면 하나만 다르게(?look=neon, 알림 꾸미기의 스타일): /theme.css 주소에 style을 붙여 다시 읽음
function useLook(look, fonts) {
  const link = document.querySelector('link[rel="stylesheet"][href^="/theme.css"]');
  if (!link) return;
  const url = new URL(link.href);
  if (look && look !== "auto") url.searchParams.set("style", look);
  else url.searchParams.delete("style");
  if (fonts !== undefined) {
    if (fonts) url.searchParams.delete("fonts");
    else url.searchParams.set("fonts", "0");
  }
  const href = url.pathname + url.search;
  if (link.getAttribute("href") === href) return;
  const next = link.cloneNode();
  next.href = href;
  next.addEventListener("load", () => {
    link.remove();
    if (window.debutkitTheme) window.debutkitTheme.mark();
  });
  link.after(next);
}

function startChat(root) {
  const max = number("max", 12);
  const fade = number("fade", 0);
  const showPlatform = option("platform", "1") !== "0";
  const hidden = new Set(option("hide", "system").split(",").filter(Boolean));
  const theme = option("theme", "shadow");
  const names = option("names", "user");  // user(플랫폼이 준 색), platform(플랫폼 색), theme(방송 색), viewer(시청자마다)
  document.body.dataset.theme = theme;
  document.body.dataset.enter = option("enter", "rise");
  document.body.dataset.align = option("align", "left");
  document.body.dataset.direction = option("direction", "up");
  document.body.dataset.roles = option("roles", "1");
  document.documentElement.style.setProperty("--font-size", `${number("font", 22)}px`);
  document.documentElement.style.setProperty("--emote", `${Math.min(4, Math.max(1, number("emote", 1.4)))}em`);
  if (theme === "style") useLook(option("look", "auto"), true);  // 방송 스타일 카드: 스타일 글꼴까지

  connect((event) => {
    if (hidden.has(event.kind) || hidden.has(event.platform)) return;
    const line = document.createElement("div");
    line.className = `line ${event.kind}${event.role ? " " + event.role : ""}`;
    const platformColor = (PLATFORMS[event.platform] || PLATFORMS.system).color;
    line.style.setProperty("--line-color", platformColor);
    if (showPlatform) line.appendChild(badge(event));
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = event.name;
    if (names === "user" && /^#[0-9a-f]{6}$/i.test(event.color || "")) name.style.color = event.color;
    else if (names === "platform") name.style.color = platformColor;
    else if (names === "viewer" && event.kind !== "system") name.style.color = viewerColor(event.name);
    line.appendChild(name);
    if (event.kind === "donation") {
      const amount = document.createElement("span");
      amount.className = "amount";
      amount.textContent = amountText(event);
      line.appendChild(amount);
    }
    const text = document.createElement("span");
    text.className = "text";
    renderParts(text, event.parts);
    line.appendChild(text);
    root.appendChild(line);
    while (root.children.length > max) root.firstElementChild.remove();
    if (fade > 0) setTimeout(() => line.classList.add("gone"), fade * 1000);
  });
}

// ---------------------------------------------------------------- 후원, 구독 알림
//: 알림 꾸미기(/alerts/control)의 기본값. 서버 설정(/alerts/config)과 주소 뒤 ?style=&layout=&position=&enter=&seconds=&scale= 가 덮어씀
const ALERT_DEFAULTS = { style: "auto", layout: "card", position: "top", enter: "auto", seconds: 6, scale: 100, message: true, platform: true,
  title: "{name} 님, {amount} 후원 감사합니다", member_title: "{name} 님, 구독해 주셔서 감사합니다", sound: "chime", volume: 70, tiers: [], member_image: "" };
//: 원으로 바꾸는 비율(별풍선 1개 100원, draw.py, vts.py와 같은 환산). 없는 단위는 최소 금액 0 구간만
const WON = { "원": 1, "별풍선": 100 };

// 효과음(브라우저에서 합성, 음원 파일 없음). OBS 브라우저 소스의 OBS 오디오 제어를 켠 경우 방송에 나감
let alertAudio = null;
function alertSound(kind, volume) {
  if (!kind || kind === "none" || volume <= 0) return;
  try {
    alertAudio = alertAudio || new (window.AudioContext || window.webkitAudioContext)();
    const now = alertAudio.currentTime;
    const peak = 0.12 * (volume / 100);
    const note = (type, frequency, start, length, level = 1, slide = 0) => {
      const oscillator = alertAudio.createOscillator();
      const gain = alertAudio.createGain();
      oscillator.type = type;
      oscillator.frequency.setValueAtTime(frequency, now + start);
      if (slide) oscillator.frequency.exponentialRampToValueAtTime(frequency * slide, now + start + length);
      gain.gain.setValueAtTime(0.0001, now + start);
      gain.gain.exponentialRampToValueAtTime(peak * level, now + start + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + start + length);
      oscillator.connect(gain).connect(alertAudio.destination);
      oscillator.start(now + start);
      oscillator.stop(now + start + length + 0.05);
    };
    if (kind === "chime") { note("sine", 880, 0, 0.5); note("sine", 1318.5, 0.14, 0.7); }
    else if (kind === "coin") { note("square", 987.8, 0, 0.09, 0.5); note("square", 1318.5, 0.08, 0.35, 0.5); }
    else if (kind === "fanfare") [523.3, 659.3, 784, 1046.5].forEach((frequency, index) => note("triangle", frequency, index * 0.11, index === 3 ? 0.8 : 0.16, 0.9));
    else if (kind === "pop") note("sine", 420, 0, 0.18, 1, 2.4);
    else if (kind === "bell") { note("sine", 1567.98, 0, 1.2, 0.8); note("sine", 3135.96, 0, 0.6, 0.25); }
  } catch (error) {
    // 소리를 낼 수 없는 환경
  }
}

function fillTemplate(target, template, event) {
  for (const piece of String(template).split(/(\{name\}|\{amount\})/)) {
    if (piece === "{name}") {
      const who = document.createElement("span");
      who.className = "who";
      who.textContent = event.name;
      target.appendChild(who);
    } else if (piece === "{amount}") {
      const amount = document.createElement("span");
      amount.className = "amount";
      amount.textContent = amountText(event);
      target.appendChild(amount);
    } else if (piece) {
      target.appendChild(document.createTextNode(piece));
    }
  }
}

function alertTier(event, config) {
  if (event.kind !== "donation") return null;
  const rate = WON[event.unit];
  const won = rate === undefined ? null : Number(event.amount) * rate;
  return (config.tiers || []).find((tier) => tier.min === 0 || (won !== null && won >= tier.min)) || null;
}

function alertEffect(kind) {
  if (kind !== "confetti" && kind !== "sparkle") return;
  const layer = document.createElement("div");
  layer.className = "alert-fx";
  const colors = [themeColor("primary", "#ff4f8b"), themeColor("highlight", "#ffd84d"), "#faf7f5", themeColor("primary-light", "#ffb3cb")];
  for (let index = 0; index < (kind === "confetti" ? 70 : 26); index += 1) {
    const piece = document.createElement(kind === "confetti" ? "i" : "b");
    piece.style.left = `${Math.random() * 100}vw`;
    piece.style.background = colors[index % colors.length];
    if (kind === "confetti") {
      piece.style.setProperty("--fall", `${2 + Math.random() * 1.6}s`);
      piece.style.setProperty("--spin", `${360 + Math.random() * 720}deg`);
      piece.style.animationDelay = `${Math.random() * 0.6}s`;
    } else {
      piece.style.top = `${10 + Math.random() * 60}vh`;
      piece.style.animationDelay = `${Math.random() * 1.2}s`;
      piece.style.fontSize = `${18 + Math.random() * 26}px`;
    }
    layer.appendChild(piece);
  }
  document.body.appendChild(layer);
  setTimeout(() => layer.remove(), 4200);
}

function themeColor(name, fallback) {
  return (window.debutkitTheme && window.debutkitTheme.color(name)) || fallback;
}

// 알림 하나를 그린다. 반환: 보여 줄 시간(초)
function renderAlert(root, event, config) {
  const tier = alertTier(event, config);
  const layout = config.layout || "card";
  const imageId = event.kind === "member" ? config.member_image : tier && tier.image;
  root.dataset.position = config.position || "top";
  root.replaceChildren();
  const scene = document.createElement("div");
  scene.className = "alert-scene";
  if (config.enter && config.enter !== "auto") scene.dataset.enter = config.enter;
  scene.style.setProperty("--alert-scale", String((Number(config.scale) || 100) / 100));
  const emphasis = tier ? tier.emphasis : "none";
  if (["glow", "shake", "bigger"].includes(emphasis)) scene.classList.add(emphasis);
  const card = document.createElement("div");
  card.className = `alert ${event.kind} layout-${layout}`;
  card.dataset.label = event.kind === "member" ? "구독" : "후원";
  if (imageId) {
    const image = document.createElement("img");
    image.className = "alert-image";
    image.alt = "";
    image.src = `/alerts/image?id=${encodeURIComponent(imageId)}`;
    if (layout === "stack") scene.appendChild(image);
    else if (layout !== "big") card.appendChild(image);
    else scene.appendChild(image);
  }
  if (config.platform !== false) card.appendChild(badge(event));
  const title = document.createElement("div");
  title.className = "alert-title";
  fillTemplate(title, event.kind === "member" ? config.member_title : config.title, event);
  card.appendChild(title);
  const text = document.createElement("div");
  text.className = "alert-text";
  if (config.message !== false) renderParts(text, event.parts);
  card.appendChild(text);
  scene.appendChild(card);
  root.appendChild(scene);
  alertEffect(emphasis);
  alertSound(tier && tier.sound ? tier.sound : config.sound, Number(config.volume ?? 70));
  const seconds = (tier && tier.seconds) || Number(config.seconds) || 6;
  setTimeout(() => scene.classList.add("gone"), Math.max(1, seconds - 0.6) * 1000);
  return seconds;
}

function startAlerts(root) {
  const overrides = {};
  for (const name of ["style", "layout", "position", "enter"]) if (params.has(name)) overrides[name] = params.get(name);
  if (params.has("seconds")) overrides.seconds = number("seconds", 6);
  if (params.has("scale")) overrides.scale = number("scale", 100);
  let config = { ...ALERT_DEFAULTS };
  const settings = () => ({ ...config, ...overrides });
  const look = () => useLook(settings().style);
  const queue = [];
  let busy = false;
  let timer = 0;
  let last = null;
  const preview = params.has("preview");
  const next = () => {
    const event = queue.shift() || (preview && last);  // 미리보기는 예시를 되풀이
    if (!event) {
      busy = false;
      return;
    }
    busy = true;
    last = event;
    const seconds = renderAlert(root, event, settings());
    timer = setTimeout(next, (seconds + (preview ? 1.2 : 0)) * 1000);
  };
  // 알림 꾸미기 화면의 미리보기(?preview): 부모 창이 보낸 저장 전 설정과 예시 알림만 그린다(방송 사건은 받지 않음)
  if (preview) {
    addEventListener("message", (message) => {
      if (message.origin !== location.origin || !message.data) return;
      if (message.data.config) {
        config = { ...config, ...message.data.config };
        look();
      }
      if (message.data.event) {
        clearTimeout(timer);
        queue.length = 0;
        queue.push(message.data.event);
        next();
      }
    });
    if (window.parent !== window) window.parent.postMessage({ ready: "alerts" }, location.origin);
    return;
  }
  fetch("/alerts/config").then((response) => response.json()).then((saved) => {
    config = { ...config, ...saved };
    look();
  }).catch(() => {});
  const accept = (event) => {
    if (event.replay || (event.kind !== "donation" && event.kind !== "member")) return;
    queue.push(event);
    if (!busy) next();
  };
  if (window.debutkitLive) {
    window.debutkitLive.subscribe(["events", "theme", "alerts"], (feed, data, initial) => {
      if (feed === "alerts") {
        config = { ...config, ...data };
        look();
      } else if (feed === "events" && !initial && !Array.isArray(data.history)) {
        accept(data);
      }
    });
  } else {
    connect(accept);
  }
}

//: 채팅창 테마 이름과 설명 (설정 화면의 선택 목록)
const THEMES = {
  shadow: "글자 그림자",
  bubble: "말풍선",
  card: "카드(이름 줄 분리)",
  outline: "외곽선 글자",
  light: "밝은 말풍선",
  style: "방송 스타일 카드",
};

window.debutkit = { startChat, startAlerts, renderAlert, renderParts, amountText, badge, PLATFORMS, THEMES };
