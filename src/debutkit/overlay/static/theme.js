// debutkit 방송 색 도움 함수(방송 화면과 조작 화면 공통). /theme.css가 처음 색을 정하고,
// 화면이 이미 받고 있는 /live 연결에 theme 항목을 더해 바뀐 색을 받으면 debutkitTheme.apply(값)으로 새로고침 없이 바꾼다.
// 브라우저는 같은 주소에 동시 연결을 6개까지만 열어(OBS 브라우저 소스끼리도 공유) 색만 받으려고 연결을 따로 열지 않는다.
"use strict";

(() => {
  const NAMES = ["primary", "primary-light", "primary-deep", "on-primary", "highlight", "highlight-deep", "on-highlight", "ink", "paper"];
  const listeners = [];

  function apply(value) {
    const palette = value && value.palette;
    if (!palette) return;
    for (const name of NAMES) {
      if (/^#[0-9a-f]{6}$/i.test(palette[name] || "")) document.documentElement.style.setProperty(`--dk-${name}`, palette[name]);
    }
    for (const listener of listeners) {
      try { listener(palette); } catch (error) { /* 화면별 처리 실패는 무시 */ }
    }
  }

  // 현재 값(CSS 변수)을 읽는다: debutkitTheme.color("primary")
  function color(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(`--dk-${name}`).trim();
  }

  window.debutkitTheme = { apply, color, onChange: (listener) => listeners.push(listener) };
})();
