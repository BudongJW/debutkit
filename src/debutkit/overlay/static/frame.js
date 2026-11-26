// debutkit 프레임(/frame): 캐릭터와 캠 테두리, 게임 화면 테두리, 대기, 자리 비움, 엔딩 화면.
// 주소 뒤 ?kind=cam|screen|starting|brb|ending, ?name=이름표(설정보다 우선), ?look=스타일(이 화면만), ?minutes=대기 화면 남은 시간.
// 문구와 이름표는 게임 패키지 설정(/games)에서, 바뀌면 공유 연결(live.js)의 games 항목으로 새로고침 없이 바꾼다. 글은 textContent로만 넣는다.
"use strict";

(() => {
  const params = new URLSearchParams(location.search);
  const KINDS = ["cam", "screen", "starting", "brb", "ending"];
  const kind = KINDS.includes(params.get("kind")) ? params.get("kind") : "cam";
  const root = document.getElementById("frame");
  //: 화면별 기본 문구: [제목, 머리표]
  const TEXT = { starting: ["곧 방송을 시작합니다", "준비 중"], brb: ["잠시 자리를 비웠습니다", "쉬는 시간"], ending: ["시청해 주셔서 감사합니다", "방송 끝"] };
  const opened = Date.now();
  let frames = {};
  let clock = null;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function corners(box) {
    for (const corner of ["tl", "tr", "bl", "br"]) box.appendChild(el("i", corner));
    return box;
  }

  // 이 화면만 다른 방송 스타일(?look=neon): /theme.css 주소에 style을 붙여 다시 읽음
  function useLook(look) {
    const link = document.querySelector('link[rel="stylesheet"][href^="/theme.css"]');
    if (!link || !look || look === "auto") return;
    const next = link.cloneNode();
    next.href = `/theme.css?style=${encodeURIComponent(look)}`;
    next.addEventListener("load", () => { link.remove(); if (window.debutkitTheme) window.debutkitTheme.mark(); });
    link.after(next);
  }

  function minutesLeft() {
    const minutes = Number(params.get("minutes") ?? frames.minutes ?? 0);
    if (kind !== "starting" || !Number.isFinite(minutes) || minutes <= 0) return null;
    return Math.max(0, minutes * 60 - Math.floor((Date.now() - opened) / 1000));
  }

  function tick() {
    if (!clock) return;
    const left = minutesLeft();
    if (left === null) { clock.textContent = ""; return; }
    clock.textContent = left > 0 ? `${String(Math.floor(left / 60)).padStart(2, "0")}:${String(left % 60).padStart(2, "0")}` : "곧 시작";
  }

  function render() {
    const name = params.get("name") ?? frames.name ?? "";
    clock = null;
    if (kind === "cam" || kind === "screen") {
      const wrap = el("div", `fr-${kind}`);
      const box = corners(el("div", "fr-box"));
      const plate = el("div", "fr-plate", name);
      box.append(plate, el("div", "fr-tag", kind === "cam" ? (params.get("tag") ?? frames.tag ?? "") : ""));
      wrap.appendChild(box);
      root.replaceChildren(wrap);
      return;
    }
    const [title, kicker] = TEXT[kind];
    const panel = el("div", "fr-panel");
    clock = el("div", "fr-clock");
    panel.append(el("div", "fr-band top"), el("div", "fr-band"), corners(el("div", "fr-box")),
      el("div", "fr-kicker", kicker), el("h1", "fr-title", frames[kind] || title), el("p", "fr-sub", frames.note || ""), clock, el("div", "fr-name", name));
    root.replaceChildren(panel);
    tick();
  }

  useLook(params.get("look"));
  render();
  setInterval(tick, 1000);
  const apply = (value) => {
    if (!value || typeof value !== "object") return;
    frames = value.frames || {};
    render();
  };
  if (window.debutkitLive) {
    window.debutkitLive.subscribe(["games", "theme"], (feed, data) => { if (feed === "games") apply(data); });
  } else {
    fetch("/games").then((response) => response.json()).then(apply).catch(() => {});
  }
})();
