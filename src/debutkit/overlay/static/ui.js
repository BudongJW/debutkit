// debutkit 조작 화면 공통: 할 일로 묶은 이동 막대, OBS 연결 표시, OBS에 넣기 단추, 용어 풀이, OBS 독 모양, 짧은 알림.
// 이동 막대는 머리말(<header>) 바로 아래에 넣는다. 오버레이(방송 화면)에서는 이 파일 대신 theme.js만 쓴다.
//
// <button data-obs="chat" data-obs-from="chat-url">: 누르면 그 방송 화면을 지금 OBS 장면에 넣는다(POST /obs/add).
//   data-obs-from 은 주소 칸의 id(주소 뒤 설정 값을 함께 보냄). 실패하면 할 일과 끌어다 놓기 링크, 주소 복사를 보여 준다
// <span data-help="브라우저 소스">: 옆에 ? 단추, 누르면 용어 풀이
"use strict";

(() => {
  //: 위쪽 메뉴: 묶음 5개(한 줄). 지금 묶음의 화면만 그 아래 둘째 줄에. [묶음 이름, [[주소, 이름, 설명], ...]]
  const GROUPS = [
    ["시작하기", [["/", "방송 준비", "OBS 연결, OBS에 넣기, 시험 후원"]]],
    ["꾸미기", [["/stage", "방송 화면", "방송 스타일, 색, 글꼴, 게임 배치, 프레임"], ["/alerts/control", "후원 알림", "알림 모양, 위치, 문구, 효과음"],
      ["/decor", "방송 이미지", "프사, 배너, 다시보기 썸네일"], ["/character/sheet", "캐릭터 그림", "3D 캐릭터의 표정 시트, 포즈 그림"]]],
    ["방송 중 놀이", [["/draw/control", "후원 추첨", "후원이 오면 확률로 뽑기"], ["/pick/control", "뽑기판", "칸을 열어 상품 뽑기"],
      ["/wall/control", "후원 벽", "후원 카드 벽, 목표, 순위"], ["/race/control", "참여 레이스", "시청자가 겨루는 게임"],
      ["/board/control", "주사위 판", "칸 미션을 도는 말판 게임"]]],
    ["팬과 함께", [["/community/control", "팬 커뮤니티", "공지, 게시판, 출석"], ["/discord/control", "디스코드 합방", "합방 참여자 화면, 방송 알림"]]],
    ["더 보기", [["/phone", "휴대폰", "휴대폰 얼굴 추적, 카메라, 조작"], ["/broadcast/control", "OBS 없이 방송", "debutkit만으로 바로 송출"],
      ["/logo", "로고 만들기", "채널 로고 그리기"], ["/vmc", "VMC 송신", "얼굴 추적 값을 다른 아바타 프로그램으로"]]],
  ];
  const PAGES = GROUPS.flatMap(([, pages]) => pages);
  //: 처음 쓰는 사람이 막히는 용어(? 단추의 풀이)
  const GLOSSARY = {
    "OBS": "방송 화면을 만들어 치지직, SOOP, YouTube로 보내는 무료 프로그램. debutkit은 OBS에 화면(채팅창, 알림 등)을 넣어 줍니다.",
    "장면": "OBS에서 화면 구성 하나(예: 본방송, 대기 화면). 장면을 바꾸면 방송 화면이 통째로 바뀝니다.",
    "소스": "OBS 장면에 들어가는 재료 하나(게임 화면, 캐릭터, 채팅창 등). 위에 있는 소스가 앞에 보입니다.",
    "브라우저 소스": "웹 화면을 OBS에 보여 주는 소스. debutkit의 채팅창, 알림, 추첨이 모두 브라우저 소스입니다. OBS에 넣기 단추가 대신 만들어 줍니다.",
    "오버레이": "방송 화면 위에 겹쳐 보이는 것(채팅창, 후원 알림, 목표 게이지 등). 배경은 투명합니다.",
    "WebSocket": "다른 프로그램이 OBS를 조작하게 하는 OBS 기능(OBS 28부터 들어 있음). OBS 도구 메뉴의 WebSocket 서버 설정에서 서버 사용을 켜면 debutkit이 장면과 소스를 만들 수 있습니다.",
    "독": "OBS 창 안에 붙이는 작은 조작 창. OBS 독 메뉴의 사용자 지정 브라우저 독에 debutkit 조작 화면 주소를 넣으면 OBS 안에서 바로 누를 수 있습니다.",
    "웹훅": "디스코드 채널에 글을 올리는 주소. 이 주소를 아는 프로그램은 그 채널에 글을 쓸 수 있으므로 남에게 보여 주지 않습니다.",
    "리플레이 버퍼": "OBS가 최근 몇십 초를 늘 기억해 두는 기능. 자동 클립이 이것으로 방금 장면을 저장합니다.",
    "오디오 모니터링": "OBS 소리를 내 헤드폰으로도 듣는 설정. OBS에 넣기는 알림 소리를 방송으로 보내고 나도 들리게 맞춥니다.",
  };
  const params = new URLSearchParams(location.search);
  const docked = () => params.has("dock") || innerWidth < 560;

  function nav() {
    const header = document.querySelector("body > header");
    if (!header || document.querySelector(".dk-nav")) return;
    const LAST = "debutkit-nav-last";
    let last = {};
    try { last = JSON.parse(localStorage.getItem(LAST) || "{}"); } catch (error) { last = {}; }
    const active = GROUPS.find(([, pages]) => pages.some(([path]) => path === location.pathname));
    if (active) { last[active[0]] = location.pathname; localStorage.setItem(LAST, JSON.stringify(last)); }
    // 첫째 줄: 묶음. 누르면 그 묶음에서 마지막으로 본 화면(처음이면 첫 화면)
    const bar = document.createElement("nav");
    bar.className = "dk-nav";
    bar.setAttribute("aria-label", "debutkit 메뉴");
    for (const [group, pages] of GROUPS) {
      const link = document.createElement("a");
      const target = pages.some(([path]) => path === last[group]) ? last[group] : pages[0][0];
      link.href = target;
      link.textContent = group;
      link.title = pages.map(([, label]) => label).join(", ");
      if (active && active[0] === group) link.setAttribute("aria-current", "true");
      bar.appendChild(link);
    }
    header.after(bar);
    // 둘째 줄: 지금 묶음의 화면(둘 이상일 때만)
    if (active && active[1].length > 1) {
      const sub = document.createElement("nav");
      sub.className = "dk-subnav";
      sub.setAttribute("aria-label", `${active[0]} 화면`);
      for (const [path, label, about] of active[1]) {
        const link = document.createElement("a");
        link.href = path;
        link.textContent = label;
        link.title = about;
        if (location.pathname === path) link.setAttribute("aria-current", "page");
        sub.appendChild(link);
      }
      bar.after(sub);
    }
    const home = header.querySelector('a[href="/"]');  // 메뉴에 같은 곳이 있어 머리말의 링크는 숨김
    if (home) home.hidden = true;
  }

  // ------------------------------------------------------------------ OBS 연결 표시
  let obsState = null;
  const obsListeners = [];
  async function obsCheck(fresh = false) {
    try {
      obsState = await (await fetch(`/obs/status${fresh ? "?fresh=1" : ""}`)).json();
    } catch (error) {
      obsState = { connected: false, error: "debutkit 오버레이가 꺼져 있음" };
    }
    paintObs();
    for (const listener of obsListeners) { try { listener(obsState); } catch (error) { /* 화면별 처리 실패 무시 */ } }
    return obsState;
  }

  function paintObs() {
    const chip = document.querySelector(".dk-obs");
    if (!chip || !obsState) return;
    chip.classList.toggle("ok", Boolean(obsState.connected));
    chip.classList.toggle("bad", !obsState.connected);
    chip.textContent = obsState.connected ? `OBS 연결됨: ${obsState.scene || "장면 없음"}` : "OBS 연결 안 됨";
    chip.title = obsState.connected ? "debutkit이 OBS에 화면을 넣을 수 있습니다" : `${obsState.error || ""} (눌러서 다시 확인)`;
  }

  function obsChip() {
    const header = document.querySelector("body > header");
    if (!header || header.querySelector(".dk-obs")) return;
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "dk-obs";
    chip.textContent = "OBS 확인 중";
    chip.addEventListener("click", async () => {
      const state = await obsCheck(true);
      toast(state.connected ? `OBS 연결됨: ${state.scene}` : state.error || "OBS 연결 안 됨", !state.connected);
    });
    header.appendChild(chip);
    obsCheck();
    setInterval(() => { if (!document.hidden) obsCheck(); }, 20000);
  }

  // ------------------------------------------------------------------ OBS에 넣기 단추
  //: OBS에 끌어다 놓을 때의 이름과 크기(OBS 공식 끌어다 놓기: layer-name, layer-width, layer-height)
  const SIZES = { chat: ["채팅", 422, 1016], alerts: ["후원 알림", 1920, 1080], character: ["캐릭터", 720, 900], draw: ["후원 추첨", 1920, 1080],
    pick: ["뽑기판", 1920, 1080], wall: ["후원 벽", 1920, 1080], goal: ["목표 게이지", 1280, 240], rank: ["후원 순위", 560, 720], race: ["참여 레이스", 1920, 1080],
    community: ["커뮤니티", 1920, 1080], "frame-cam": ["캐릭터 프레임", 614, 670], "frame-starting": ["대기 화면 프레임", 1920, 1080] };
  const PATHS = { chat: "/chat", alerts: "/alerts", character: "/character", draw: "/draw", pick: "/pick", wall: "/wall", goal: "/wall/goal", rank: "/wall/rank",
    race: "/race", community: "/community", "frame-cam": "/frame?kind=cam", "frame-starting": "/frame?kind=starting" };

  function queryFrom(button) {
    const source = button.dataset.obsFrom && document.getElementById(button.dataset.obsFrom);
    if (!source || !source.value) return button.dataset.obsQuery || "";
    try { return new URL(source.value, location.origin).search.replace(/^\?/, ""); } catch (error) { return ""; }
  }

  function dragUrl(kind, query) {
    const [name, width, height] = SIZES[kind] || ["debutkit", 1920, 1080];
    const url = new URL(PATHS[kind] || "/", location.origin);
    if (query) for (const [key, value] of new URLSearchParams(query)) url.searchParams.set(key, value);
    url.searchParams.set("layer-name", `[DK] ${name}`);
    url.searchParams.set("layer-width", String(width));
    url.searchParams.set("layer-height", String(height));
    return url.toString();
  }

  function fallback(button, kind, query, message) {
    let box = button.parentElement.querySelector(".dk-obs-help");
    if (!box) {
      box = document.createElement("div");
      box.className = "dk-obs-help";
      button.parentElement.appendChild(box);
    }
    const text = document.createElement("p");
    text.textContent = message;
    const link = document.createElement("a");
    link.href = dragUrl(kind, query);
    link.className = "dk-drag";
    link.textContent = `이 링크를 OBS의 소스 목록으로 끌어다 놓기(${(SIZES[kind] || [""])[0]})`;
    link.addEventListener("click", (event) => event.preventDefault());
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "secondary small";
    copy.textContent = "주소 복사";
    copy.addEventListener("click", () => navigator.clipboard.writeText(link.href.replace(/[?&]layer-[^&]+/g, "").replace(/\?$/, "")).then(() => toast("주소를 복사함")));
    box.replaceChildren(text, link, copy);
  }

  async function addToObs(button) {
    const kind = button.dataset.obs;
    const query = queryFrom(button);
    const before = button.textContent;
    button.disabled = true;
    button.textContent = "넣는 중";
    try {
      const response = await fetch("/obs/add", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind, query }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "OBS에 넣지 못함");
      toast(data.message);
      button.classList.add("done");
      const help = button.parentElement.querySelector(".dk-obs-help");
      if (help) help.remove();
      obsCheck(true);
    } catch (error) {
      toast(error.message, true);
      fallback(button, kind, query, error.message);
    } finally {
      button.disabled = false;
      button.textContent = before;
    }
  }

  // ------------------------------------------------------------------ 용어 풀이
  function helpers(root = document) {
    for (const node of root.querySelectorAll("[data-help]:not([data-help-ready])")) {
      const term = node.dataset.help;
      if (!GLOSSARY[term]) continue;
      node.dataset.helpReady = "1";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "dk-help";
      button.textContent = "?";
      button.setAttribute("aria-label", `${term} 풀이`);
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const open = document.querySelector(".dk-help-pop");
        if (open) { const same = open.dataset.term === term; open.remove(); if (same) return; }
        const pop = document.createElement("div");
        pop.className = "dk-help-pop";
        pop.dataset.term = term;
        const title = document.createElement("b");
        title.textContent = term;
        const text = document.createElement("p");
        text.textContent = GLOSSARY[term];
        pop.append(title, text);
        document.body.appendChild(pop);
        const rect = button.getBoundingClientRect();
        pop.style.left = `${Math.min(innerWidth - 300, Math.max(8, rect.left + scrollX - 20))}px`;
        pop.style.top = `${rect.bottom + scrollY + 6}px`;
      });
      node.after(button);
    }
  }
  document.addEventListener("click", (event) => {
    const button = event.target.closest && event.target.closest("[data-obs]");
    if (button && button.tagName === "BUTTON") { event.preventDefault(); addToObs(button); return; }
    const pop = document.querySelector(".dk-help-pop");
    if (pop && !pop.contains(event.target)) pop.remove();
  });

  // 그림 견본: 방송 화면을 1920x1080으로 그려 작게 줄인 그림(모양 고르기 단추에). debutkitUi.thumb("/alerts?still=1&layout=big")
  // view를 작게 주면(예: 800) 화면 가운데만 잘라 크게 보인다(좁은 칸에서 색과 모양 보기).
  // 화면에 보일 때만 불러오고(loading=lazy), 누르는 것은 바깥 단추가 받는다
  const thumbs = typeof ResizeObserver === "function" ? new ResizeObserver((entries) => {
    for (const entry of entries) {
      const frame = entry.target.querySelector("iframe");
      if (frame) frame.style.transform = `scale(${entry.contentRect.width / (Number(frame.dataset.view) || 1920)})`;
    }
  }) : null;
  function thumb(src, label = "", view = 1920) {
    const box = document.createElement("span");
    box.className = "dk-thumb";
    const frame = document.createElement("iframe");
    frame.src = src;
    if (view !== 1920) {
      frame.dataset.view = String(view);
      frame.style.width = `${view}px`;
      frame.style.height = `${Math.round(view * 9 / 16)}px`;
    }
    frame.loading = "lazy";
    frame.tabIndex = -1;
    frame.title = label || "모양 그림";
    frame.setAttribute("aria-hidden", "true");
    box.appendChild(frame);
    if (thumbs) thumbs.observe(box);
    return box;
  }

  // 마스코트 안내: debutkitUi.mascot("capsule", "아직 추첨 결과 없음") -> 그림과 말풍선 한 줄(빈 화면, 안내)
  const MASCOT_NAMES = { debi: "데비", mai: "마이", cue: "큐", bubbles: "뽀글이들", capsule: "캡슐", dessaengi: "데생이", cuckoo: "뻐꾹" };
  function mascot(name, text, small = false) {
    const box = document.createElement("div");
    box.className = small ? "dk-mascot small" : "dk-mascot";
    const img = document.createElement("img");
    img.src = `/mascot/${name}.png`;
    img.alt = MASCOT_NAMES[name] || "";
    const line = document.createElement("p");
    line.textContent = text;
    box.append(img, line);
    return box;
  }

  // 모양 고르기 단추 묶음(그림 견본 + 이름 + 설명): debutkitUi.looks($("box"), [{ key, label, about, src, view }], 지금 값, (key) => ...)
  // 같은 목록이면 그림을 다시 부르지 않고 눌린 표시만 바꾼다
  function looks(box, items, value, pick) {
    const drawn = items.map((item) => `${item.key}|${item.src || ""}`).join(" ");
    if (box.dataset.drawn !== drawn) {
      box.dataset.drawn = drawn;
      box.classList.add("dk-looks");
      box.replaceChildren(...items.map((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.key = item.key;
        if (item.src) button.appendChild(thumb(item.src, `${item.label} 그림`, item.view || 1920));
        const name = document.createElement("b");
        name.textContent = item.label;
        button.appendChild(name);
        if (item.about) {
          const about = document.createElement("small");
          about.textContent = item.about;
          button.appendChild(about);
        }
        button.addEventListener("click", () => box.dkPick && box.dkPick(item.key));
        return button;
      }));
    }
    box.dkPick = pick;
    for (const button of box.children) button.setAttribute("aria-pressed", String(button.dataset.key === value));
  }

  // 저장하지 않은 변경: const changes = debutkitUi.unsaved($("save"), $("state")); 입력이 바뀌면 changes.touch(), 저장하면 changes.clear()
  function unsaved(button, note) {
    let dirty = false;
    addEventListener("beforeunload", (event) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });
    return {
      touch() {
        if (dirty) return;
        dirty = true;
        if (button) button.classList.add("dirty");
        if (note) note.textContent = "저장하지 않은 변경이 있음";
      },
      clear() {
        dirty = false;
        if (button) button.classList.remove("dirty");
      },
      get dirty() { return dirty; },
    };
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
    timer = setTimeout(() => box.classList.remove("show"), bad ? 5000 : 2600);
  }

  window.debutkitUi = { toast, pages: PAGES, groups: GROUPS, glossary: GLOSSARY, obsCheck, onObs: (listener) => obsListeners.push(listener), helpers, addToObs, unsaved, thumb, looks, mascot };
  const start = () => { nav(); dock(); obsChip(); helpers(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
  addEventListener("resize", dock);
})();
