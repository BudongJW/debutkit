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

function startChat(root) {
  const max = number("max", 12);
  const fade = number("fade", 0);
  const showPlatform = option("platform", "1") !== "0";
  const hidden = new Set(option("hide", "system").split(",").filter(Boolean));
  document.body.dataset.theme = option("theme", "shadow");
  document.documentElement.style.setProperty("--font-size", `${number("font", 22)}px`);

  connect((event) => {
    if (hidden.has(event.kind) || hidden.has(event.platform)) return;
    const line = document.createElement("div");
    line.className = `line ${event.kind}${event.role ? " " + event.role : ""}`;
    line.style.setProperty("--line-color", (PLATFORMS[event.platform] || PLATFORMS.system).color);
    if (showPlatform) line.appendChild(badge(event));
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = event.name;
    if (/^#[0-9a-f]{6}$/i.test(event.color || "")) name.style.color = event.color;
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

function startAlerts(root) {
  const seconds = number("seconds", 6);
  document.body.dataset.style = option("style", "prop");
  const queue = [];
  let busy = false;
  const next = () => {
    const event = queue.shift();
    if (!event) {
      busy = false;
      return;
    }
    busy = true;
    root.replaceChildren();
    const card = document.createElement("div");
    card.className = `alert ${event.kind}`;
    card.dataset.label = event.kind === "member" ? "구독" : "후원";
    card.appendChild(badge(event));
    // 제목: 이름(방송 색), 금액(형광펜), 인사. 글은 textContent로만
    const title = document.createElement("div");
    title.className = "alert-title";
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = event.name;
    title.append(who, " 님, ");
    if (event.kind === "member") {
      title.append("구독해 주셔서 감사합니다");
    } else {
      const amount = document.createElement("span");
      amount.className = "amount";
      amount.textContent = amountText(event);
      title.append(amount, " 후원 감사합니다");
    }
    card.appendChild(title);
    const text = document.createElement("div");
    text.className = "alert-text";
    renderParts(text, event.parts);
    card.appendChild(text);
    root.appendChild(card);
    setTimeout(() => card.classList.add("gone"), (seconds - 0.6) * 1000);
    setTimeout(next, seconds * 1000);
  };
  connect((event) => {
    if (event.replay || (event.kind !== "donation" && event.kind !== "member")) return;
    queue.push(event);
    if (!busy) next();
  });
}

//: 채팅창 테마 이름과 설명 (설정 화면의 선택 목록)
const THEMES = {
  shadow: "글자 그림자",
  bubble: "말풍선",
  card: "카드(이름 줄 분리)",
  outline: "외곽선 글자",
  light: "밝은 말풍선",
};

window.debutkit = { startChat, startAlerts, renderParts, amountText, badge, PLATFORMS, THEMES };
