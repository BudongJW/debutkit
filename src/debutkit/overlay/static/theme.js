// debutkit 방송 색과 방송 스타일 도움 함수(방송 화면과 조작 화면 공통). /theme.css가 처음 색, 모양, 글꼴을 정하고,
// 화면이 이미 받고 있는 공유 연결(live.js)의 theme 항목으로 바뀐 값을 받으면 debutkitTheme.apply(값)이 새로고침 없이 바꾼다:
// 색은 바로 CSS 변수로, 방송 스타일과 글꼴은 /theme.css 를 다시 읽어서.
// 브라우저는 같은 주소에 동시 연결을 6개까지만 열어(OBS 브라우저 소스끼리도 공유) 색만 받으려고 연결을 따로 열지 않는다.
// 문서의 data-dk-style 에 지금 방송 스타일 이름(--dk-style)을 적어 화면별 CSS가 스타일마다 다르게 꾸밀 수 있게 한다.
"use strict";

(() => {
  const NAMES = ["primary", "primary-light", "primary-deep", "on-primary", "highlight", "highlight-deep", "on-highlight", "ink", "paper"];
  const listeners = [];
  let shown = "";

  function mark() {
    const style = getComputedStyle(document.documentElement).getPropertyValue("--dk-style").trim();
    if (style) document.documentElement.dataset.dkStyle = style;
  }

  function reload(seq) {
    for (const link of document.querySelectorAll('link[rel="stylesheet"][href^="/theme.css"]')) {
      const url = new URL(link.href);
      url.searchParams.set("v", String(seq));
      const next = link.cloneNode();
      next.href = url.pathname + url.search;
      next.addEventListener("load", () => { link.remove(); mark(); });
      link.after(next);
    }
  }

  function apply(value, initial) {
    const palette = value && value.palette;
    if (!palette) return;
    for (const name of NAMES) {
      if (/^#[0-9a-f]{6}$/i.test(palette[name] || "")) document.documentElement.style.setProperty(`--dk-${name}`, palette[name]);
    }
    // 방송 스타일, 글꼴이 바뀌면 /theme.css 를 다시 읽는다(처음 값은 이미 불러온 것과 같음)
    const key = JSON.stringify([value.style, value.display_font, value.text_font, (value.fonts || []).map((font) => font.id)]);
    if (!initial && shown && key !== shown) reload(value.seq || Date.now());
    shown = key;
    for (const listener of listeners) {
      try { listener(palette, value); } catch (error) { /* 화면별 처리 실패는 무시 */ }
    }
  }

  // 현재 값(CSS 변수)을 읽는다: debutkitTheme.color("primary")
  function color(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(`--dk-${name}`).trim();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mark);
  else mark();
  window.debutkitTheme = { apply, color, mark, onChange: (listener) => listeners.push(listener) };
})();
