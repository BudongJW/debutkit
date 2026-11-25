// debutkit 조작 화면 공통: 이동 막대, OBS 독 모양, 방송 색 적용 도움 함수, 짧은 알림.
// 이동 막대는 머리말(<header>) 바로 아래에 넣는다. 오버레이(방송 화면)에서는 이 파일 대신 theme.js만 쓴다.
"use strict";

(() => {
  const PAGES = [
    ["/", "설정 화면"],
    ["/stage", "방송 화면 미리보기"],
    ["/draw/control", "추첨"],
    ["/pick/control", "뽑기판"],
    ["/wall/control", "후원 벽"],
    ["/race/control", "참여 레이스"],
    ["/phone", "휴대폰"],
    ["/broadcast/control", "바로 방송"],
    ["/logo", "로고"],
    ["/vmc", "VMC"],
  ];
  const params = new URLSearchParams(location.search);
  const docked = () => params.has("dock") || innerWidth < 560;

  function nav() {
    const header = document.querySelector("body > header");
    if (!header || document.querySelector(".dk-nav")) return;
    const bar = document.createElement("nav");
    bar.className = "dk-nav";
    bar.setAttribute("aria-label", "debutkit 화면");
    for (const [path, label] of PAGES) {
      const link = document.createElement("a");
      link.href = path;
      link.textContent = label;
      if (location.pathname === path) link.setAttribute("aria-current", "page");
      bar.appendChild(link);
    }
    header.after(bar);
    const home = header.querySelector('a[href="/"]');  // 이동 막대에 같은 곳이 있어 머리말의 링크는 숨김
    if (home) home.hidden = true;
  }

  function dock() {
    document.body.classList.toggle("dock", docked());
  }

  // 짧은 알림: debutkitUi.toast("저장함") 또는 toast("실패", true)
  let timer = 0;
  function toast(text, bad) {
    let box = document.querySelector(".dk-toast");
    if (!box) {
      box = document.createElement("div");
      box.className = "dk-toast";
      box.setAttribute("role", "status");
      document.body.appendChild(box);
    }
    box.textContent = text;
    box.classList.toggle("bad", Boolean(bad));
    box.classList.add("show");
    clearTimeout(timer);
    timer = setTimeout(() => box.classList.remove("show"), 2200);
  }

  window.debutkitUi = { toast, pages: PAGES };
  const start = () => { nav(); dock(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
  addEventListener("resize", dock);
})();
