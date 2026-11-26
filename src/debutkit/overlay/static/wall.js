// debutkit 후원 벽(OBS 브라우저 소스). 주소에 따라 세 화면 중 하나를 그린다.
//   /wall       후원 벽(권장 1920x1080): /live?feeds=wall 로 칸과 카드를 받아 새 카드를 한 장씩 차례로 붙인다
//   /wall/goal  목표 게이지(권장 1280x240), /wall/rank 후원 순위(권장 560x720): 같은 카드로 서버가 계산한 값을 1.5초마다 확인
// 콘셉트 "방송 소품": 잉크, 종이, 핑크, 가장 높은 단계는 금색. 흐림 없는 딱딱한 그림자. 글은 textContent로만 넣는다.
// 동시에 여러 후원이 와도 들어온 순서대로 하나씩 붙이고, 대기 카드가 많으면(설정의 빠른 진행 기준) 짧은 연출로 넘긴다.
// OBS 상호작용(또는 조작 화면 미리보기)에서 칸 머리를 끌어 옮기고 오른쪽 아래 모서리로 크기를 바꾼다. 칸 머리 두 번 누르기는 자동 배치로.
// 주소: ?edit=1 칸 테두리 항상 표시(조작 화면 미리보기), ?bg=dark 또는 ?bg=light 확인용 배경, ?sound 효과음 강제
"use strict";

(() => {
  const params = new URLSearchParams(location.search);
  // 방송 색(/theme.css): 축하 조각 색은 그때그때 읽는다(색을 바꾸면 바로 반영)
  const themed = (name, fallback) => (window.debutkitTheme && window.debutkitTheme.color(name)) || fallback;
  const route = location.pathname.replace(/\/+$/, "");
  const VIEW = route === "/wall/goal" ? "goal" : route === "/wall/rank" ? "rank" : "wall";
  const SHARED = (window.debutkit && window.debutkit.PLATFORMS) || {};
  const platformOf = (key) => SHARED[key] || { label: key || "", color: "#8a8499" };
  const root = document.getElementById("wall-root");
  const NS = "http://www.w3.org/2000/svg";

  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const post = (path, body) => fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }).catch(() => null);
  const fontsReady = document.fonts
    ? Promise.all(['40px "Black Han Sans"', '600 20px "Pretendard"', '700 20px "Pretendard"'].map((font) => document.fonts.load(font))).catch(() => null)
    : Promise.resolve();
  const background = params.get("bg");
  if (background === "dark" || background === "light") document.body.classList.add(`bg-${background}`);

  // 별 조각(반짝 등장, 별가루 오라, 목표 달성). 각도와 거리로 흩어진다
  function burst(className, count, distance, colors) {
    const layer = el("span", className);
    for (let i = 0; i < count; i++) {
      const bit = el("i");
      const angle = (i / count) * Math.PI * 2 + Math.random() * 0.5;
      const reach = distance * (0.65 + Math.random() * 0.5);
      bit.style.setProperty("--x", `${Math.round(Math.cos(angle) * reach)}px`);
      bit.style.setProperty("--y", `${Math.round(Math.sin(angle) * reach * 0.7)}px`);
      bit.style.setProperty("--d", `${Math.round(Math.random() * 120)}ms`);
      bit.style.setProperty("--c", colors[i % colors.length]);
      layer.appendChild(bit);
    }
    return layer;
  }

  // ---------------------------------------------------------------- 효과음(브라우저에서 합성. 음원 파일 없음)
  let audio = null;
  function tone(kind, level = 1) {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const now = audio.currentTime;
      const note = (type, frequency, start, length, peak) => {
        const oscillator = audio.createOscillator();
        const gain = audio.createGain();
        oscillator.type = type;
        oscillator.frequency.setValueAtTime(frequency, now + start);
        gain.gain.setValueAtTime(0.0001, now + start);
        gain.gain.exponentialRampToValueAtTime(peak, now + start + 0.006);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + start + length);
        oscillator.connect(gain).connect(audio.destination);
        oscillator.start(now + start);
        oscillator.stop(now + start + length + 0.03);
      };
      if (kind === "tick") note("square", 1900, 0, 0.022, 0.025);
      else if (kind === "card") { note("triangle", 520, 0, 0.09, 0.07); note("sine", 1040, 0.03, 0.14, 0.035); }
      else if (kind === "aura") [987.8, 1318.5, 1567.98, 1975.5, 2637].slice(0, 1 + level).forEach((frequency, index) => note("sine", frequency, index * 0.07, 1.1, 0.06));
      else if (kind === "signature") { [784, 987.8, 1174.7, 1568].forEach((frequency, index) => note("triangle", frequency, index * 0.06, 0.9, 0.06)); note("sine", 2349, 0.3, 1.4, 0.05); }
      else if (kind === "goal") [523.25, 659.25, 783.99, 1046.5].forEach((frequency, index) => note("triangle", frequency, index * 0.1, 0.8, 0.07));
    } catch (error) {
      // 소리를 낼 수 없는 환경
    }
  }

  if (VIEW === "goal") goalView();
  else if (VIEW === "rank") rankView();
  else wallView();

  // ================================================================ 후원 벽
  function wallView() {
    const ENTRANCES = ["pop", "drop", "sparkle", "stamp", "unfold", "jelly", "trace", "bubble", "flip", "tape"];
    const DURATIONS = { pop: 700, drop: 900, sparkle: 900, stamp: 700, unfold: 900, jelly: 1000, trace: 1100, bubble: 1200, flip: 1000, tape: 800 };
    const LIVE = 80;  // 대기 효과를 주는 최근 카드 수(OBS 부담 줄이기)
    const KEEP = 60;  // 칸 하나에 그려 두는 카드 수(서버의 MAX_SHOWN과 같음)
    const stage = el("div", "wl-stage");
    const empty = el("div", "wl-empty", "후원 카드가 오면 여기에 칸이 생깁니다. 조작 화면의 시험 후원으로 확인할 수 있습니다.");
    stage.appendChild(empty);
    root.appendChild(stage);
    if (params.get("edit") === "1") root.classList.add("edit");

    let scale = 1;
    const fit = () => {
      scale = Math.min(innerWidth / 1920, innerHeight / 1080) || 1;
      stage.style.transform = `scale(${scale})`;
    };
    addEventListener("resize", fit);
    fit();

    const columns = new Map();  // 칸 이름 -> 칸
    const cards = new Map();  // 카드 번호 -> 화면의 카드
    const pending = [];  // 차례를 기다리는 연출 {type: "card", data} 또는 {type: "replay", id}
    let options = { entrance: "pop", idle: "float", fast_after: 6, sound: false, names: true };
    let lastRev = 0;
    let maxId = 0;
    let busy = false;
    let connectedOnce = false;

    function setOptions(next) {
      options = { ...options, ...(next || {}) };
      root.dataset.idle = options.idle;
      root.classList.toggle("no-names", !options.names);
    }
    const soundOn = () => Boolean(options.sound) || params.has("sound");
    const pendingIn = (key) => pending.reduce((sum, job) => sum + (job.type === "card" && job.data.column === key ? 1 : 0), 0);

    // ---------------------------------------------------------- 칸
    function makeColumn(info) {
      const node = el("div", "wl-col");
      const head = el("div", "wl-head");
      const body = el("div", "wl-body");
      const more = el("div", "wl-more");
      more.hidden = true;
      body.appendChild(more);
      const grip = el("div", "wl-grip");
      grip.title = "크기 바꾸기";
      node.append(head, body, grip);
      const col = { key: info.key, info, node, head, body, more, countNode: null, ids: [], shown: false, mark: "", dragging: false };
      head.addEventListener("pointerdown", (event) => drag(col, event, "move"));
      grip.addEventListener("pointerdown", (event) => drag(col, event, "size"));
      head.addEventListener("dblclick", () => post("/wall/layout", { key: col.key, auto: true }));
      stage.appendChild(node);
      columns.set(info.key, col);
      return col;
    }

    function fitText(node, largest, smallest) {
      if (!node) return;
      let size = largest;
      node.style.fontSize = `${size}px`;
      while (node.scrollWidth > node.clientWidth + 1 && size > smallest) {
        size -= 2;
        node.style.fontSize = `${size}px`;
      }
    }

    function renderHead(col) {
      const info = col.info;
      const mark = JSON.stringify([info.kind, info.tag, info.title, info.number, info.suffix, info.hide_number, info.image, info.w]);
      if (mark === col.mark) return;
      col.mark = mark;
      col.node.dataset.kind = info.kind;
      const parts = [];
      if (info.image) {
        const art = el("div", "wl-art");
        const image = el("img");
        image.alt = "";
        image.decoding = "async";
        image.src = info.image;
        art.appendChild(image);
        parts.push(art);
      }
      const plate = el("div", "wl-plate");
      const line = el("div", "wl-line");
      col.countNode = el("span", "wl-count", "");
      line.append(el("span", "wl-tag", info.tag), col.countNode);
      plate.appendChild(line);
      let title = null;
      let number = null;
      if (info.title) {
        title = el("div", "wl-title", info.title);
        plate.appendChild(title);
      }
      if (!info.hide_number) {
        number = el("div", "wl-number", info.number);
        if (info.suffix) number.appendChild(el("small", "", info.suffix));
        plate.appendChild(number);
      }
      parts.push(plate);
      col.head.replaceChildren(...parts);
      const big = info.kind === "sig" ? 46 : 42;
      fitText(title, info.number && !info.hide_number ? 32 : 40, 16);
      fitText(number, title ? 30 : big, 16);
      updateCount(col);
    }

    function place(col) {
      const { x, y, w, h } = col.info;
      Object.assign(col.node.style, { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px` });
      col.node.style.setProperty("--w", `${w}px`);
      col.node.style.setProperty("--h", `${h}px`);
      col.node.classList.toggle("pinned", Boolean(col.info.pinned));
    }

    function updateColumns(list) {
      const seen = new Set();
      for (const info of list) {
        seen.add(info.key);
        const col = columns.get(info.key) || makeColumn(info);
        if (col.dragging) {  // 끄는 중에는 화면의 위치를 유지
          const { x, y, w, h } = col.info;
          col.info = { ...info, x, y, w, h };
        } else {
          col.info = info;
          place(col);
        }
        renderHead(col);
      }
      for (const col of [...columns.values()]) if (!seen.has(col.key)) dropColumn(col);
    }

    function dropColumn(col) {  // 비우기 등: 카드가 차례로 떨어진 뒤 칸이 사라짐
      columns.delete(col.key);
      col.ids.forEach((id, index) => {
        const card = cards.get(id);
        if (!card) return;
        cards.delete(id);
        card.node.style.setProperty("--i", String(Math.min(col.ids.length - index, 30)));
        card.node.classList.add("leave");
      });
      col.node.classList.add("leaving");
      setTimeout(() => col.node.remove(), 1200);
    }

    function updateCount(col, bump) {
      if (!col.countNode) return;
      const total = Math.max(col.ids.length, (col.info.count || 0) - pendingIn(col.key));
      col.countNode.textContent = `${total.toLocaleString("ko-KR")}건`;
      if (bump) {
        col.countNode.classList.remove("bump");
        void col.countNode.offsetWidth;
        col.countNode.classList.add("bump");
      }
    }

    function refresh() {
      for (const col of columns.values()) {
        // 첫 카드를 기다리는 새 칸은 그 카드 차례에 나타남. 카드 없이 미리 세운 시그니처 칸은 바로
        if (!col.shown && (col.ids.length || !pendingIn(col.key))) {
          col.shown = true;
          col.node.classList.add("shown");
        }
        updateCount(col);
        layoutColumn(col);
      }
      empty.hidden = columns.size > 0;
    }

    // 카드 자리: 다 들어가면 간격을 두고, 넘치면 겹쳐(이름 줄만 보이게), 그래도 넘치면 오래된 카드를 접고 위에 +N장
    function layoutColumn(col) {
      const top = col.head.offsetHeight + 12;
      col.body.style.top = `${top}px`;
      const room = Math.max(40, col.info.h - top);
      const cardH = options.names ? 64 : 46;
      const strip = options.names ? 30 : 26;
      const n = col.ids.length;
      const total = Math.max(n, (col.info.count || 0) - pendingIn(col.key));
      let start = total > n ? 30 : 0;
      let space = room - start;
      let step = cardH + 8;
      let visible = n;
      if (n > 1 && n * cardH + (n - 1) * 8 > space) {
        step = (space - cardH) / (n - 1);
        if (step < strip) {
          if (!start) {
            start = 30;
            space -= 30;
          }
          step = strip;
          visible = clamp(Math.floor((space - cardH) / strip) + 1, 1, n);
        }
      }
      const hidden = n - visible;
      col.ids.forEach((id, index) => {
        const card = cards.get(id);
        if (!card) return;
        const slot = index - hidden;
        card.node.classList.toggle("tucked", slot < 0);
        card.node.classList.toggle("covered", slot >= 0 && slot < visible - 1 && step < cardH);
        if (slot >= 0) {
          card.node.style.top = `${Math.round(start + slot * step)}px`;
          card.node.style.zIndex = String(slot + 1);
        }
      });
      const extra = total - visible;
      col.more.hidden = extra <= 0;
      col.more.textContent = extra > 0 ? `+${extra.toLocaleString("ko-KR")}장` : "";
    }

    // ---------------------------------------------------------- 카드
    function stars(count) {
      const layer = el("span", "wl-stars");
      const colors = [themed("highlight", "#ffd84d"), "#faf7f5", themed("primary", "#ff4f8b"), themed("highlight", "#ffd84d")];
      for (let i = 0; i < count; i++) {
        const star = el("i");
        const side = i % 4;
        const along = Math.random() * 100;
        star.style.left = `${side === 0 ? 0 : side === 1 ? 100 : along}%`;
        star.style.top = `${side === 2 ? 0 : side === 3 ? 100 : along}%`;
        star.style.setProperty("--s", `${8 + Math.round(Math.random() * 8)}px`);
        star.style.setProperty("--d", `${(Math.random() * 1.6).toFixed(2)}s`);
        star.style.setProperty("--c", colors[i % colors.length]);
        layer.appendChild(star);
      }
      return layer;
    }

    function makeCard(data, col) {
      const node = el("div", "wl-card");
      node.dataset.id = String(data.id);
      node.style.setProperty("--rot", `${((((data.id * 37) % 9) + 9) % 9 - 4) * 0.35}deg`);
      node.style.setProperty("--seed", (((data.id * 0.6180339) % 1) + 1) % 1 + "");
      const tilt = el("div", "wl-tilt");
      const face = el("div", "wl-face");
      const front = el("div", "wl-front");
      front.style.setProperty("--platform", platformOf(data.platform).color);
      front.appendChild(el("span", "wl-edge"));
      const sameAsColumn = col.info.kind === "sig" && col.info.hide_number && !data.detached;
      if (options.names && data.name) front.appendChild(el("span", "wl-name", data.name));
      if (!(sameAsColumn && options.names && data.name)) front.appendChild(el("span", "wl-amount", data.text));
      else node.classList.add("name-only");
      if (data.test) {
        node.classList.add("test");
        front.appendChild(el("span", "wl-test", "시험"));
      }
      front.appendChild(el("span", "wl-flash"));
      face.appendChild(front);
      if (data.aura) {
        node.classList.add("aura", `aura-${data.aura.effect}`);
        node.style.setProperty("--aura", String(clamp((Number(data.aura.strength) || 100) / 100, 0.3, 2)));
        if (data.aura.effect === "stardust" || data.aura.effect === "gold") face.appendChild(stars(data.aura.effect === "gold" ? 9 : 7));
      }
      tilt.appendChild(face);
      node.appendChild(tilt);
      return { data, node, face, col: col.key, mark: cardMark(data) };
    }
    const cardMark = (data) => JSON.stringify([data.name, data.text, data.test, data.detached, data.aura && data.aura.effect, data.aura && data.aura.strength]);

    function insertId(col, id) {  // 칸 안의 카드는 번호 순서(오래된 것이 위)
      let index = col.ids.length;
      while (index > 0 && col.ids[index - 1] > id) index -= 1;
      col.ids.splice(index, 0, id);
    }

    function trim(col) {
      while (col.ids.length > KEEP) {
        const id = col.ids.shift();
        const card = cards.get(id);
        if (card) {
          card.node.remove();
          cards.delete(id);
        }
      }
    }

    function placeInstant(data) {
      const col = columns.get(data.column);
      if (!col || cards.has(data.id)) return;
      const card = makeCard(data, col);
      card.node.classList.add("settled");
      cards.set(data.id, card);
      insertId(col, data.id);
      col.body.appendChild(card.node);
      trim(col);
    }

    function removeCard(card, animate, index) {
      cards.delete(card.data.id);
      const col = columns.get(card.col);
      if (col) col.ids = col.ids.filter((id) => id !== card.data.id);
      if (!animate) return card.node.remove();
      card.node.style.setProperty("--i", String(Math.min(index || 0, 40)));
      card.node.classList.add("leave");
      setTimeout(() => card.node.remove(), 1000);
    }

    function markLive() {
      const ids = [...cards.keys()].sort((a, b) => b - a);
      ids.forEach((id, index) => cards.get(id).node.classList.toggle("live", index < LIVE));
    }

    function pickEntrance() {
      return ENTRANCES.includes(options.entrance) ? options.entrance : ENTRANCES[Math.floor(Math.random() * ENTRANCES.length)];
    }

    function decorate(card, name) {
      const add = (node, life) => {
        card.face.appendChild(node);
        setTimeout(() => node.remove(), life);
      };
      if (name === "sparkle") add(burst("wl-burst", 10, 120, [themed("highlight", "#ffd84d"), themed("primary", "#ff4f8b"), "#faf7f5"]), 1300);
      else if (name === "stamp") add(el("span", "wl-ring"), 1200);
      else if (name === "drop") {
        const dust = el("span", "wl-dust");
        dust.append(el("i"), el("i"));
        add(dust, 1300);
      } else if (name === "unfold") add(el("span", "wl-crease"), 1000);
      else if (name === "trace") {
        const svg = document.createElementNS(NS, "svg");
        svg.setAttribute("class", "wl-trace");
        svg.setAttribute("preserveAspectRatio", "none");
        const rect = document.createElementNS(NS, "rect");
        rect.setAttribute("rx", "8");
        rect.setAttribute("pathLength", "100");
        Object.assign(rect.style, { x: "2px", y: "2px", width: "calc(100% - 4px)", height: "calc(100% - 4px)" });
        rect.setAttribute("vector-effect", "non-scaling-stroke");
        svg.appendChild(rect);
        add(svg, 1500);
      } else if (name === "bubble") {
        add(el("span", "wl-bubble"), 1400);
        add(burst("wl-drops", 8, 90, ["#ffffff"]), 1500);
      } else if (name === "flip") add(el("span", "wl-back"), 1100);
      else if (name === "tape") {
        const tape = el("span", "wl-tape");
        tape.append(el("i"), el("i"));
        add(tape, 2600);
      }
    }

    function chime(data, fast, col) {
      if (!soundOn()) return;
      if (fast) return tone("tick");
      if (col && col.info.kind === "sig") return tone("signature");
      if (data.aura) return tone("aura", Math.min(4, data.aura.tier || 1));
      tone("card");
    }

    async function animate(card, name, fast) {
      card.node.classList.remove("settled", "live", "enter", ...ENTRANCES.map((item) => `in-${item}`));
      void card.node.offsetWidth;  // 같은 연출 다시 시작
      card.node.style.setProperty("--speed", fast ? "0.42" : "1");
      card.node.classList.add("enter", `in-${name}`);
      if (!fast) {
        decorate(card, name);
        card.node.classList.add("fresh");
        setTimeout(() => card.node.classList.remove("fresh"), 2600);
      }
      await wait(fast ? Math.round(DURATIONS[name] * 0.42) + 40 : DURATIONS[name] + 150);
      card.node.classList.remove("enter", `in-${name}`);
      card.node.classList.add("settled");
    }

    async function playCard(data, fast) {
      const col = columns.get(data.column);
      if (!col || cards.has(data.id)) return;
      if (!col.shown) {  // 새 칸: 칸 머리가 먼저 내려온 뒤 카드
        col.shown = true;
        col.node.classList.add("shown", "reveal");
        setTimeout(() => col.node.classList.remove("reveal"), 900);
        layoutColumn(col);
        await wait(fast ? 140 : 420);
      }
      if (!columns.has(col.key)) return;
      const card = makeCard(data, col);
      cards.set(data.id, card);
      insertId(col, data.id);
      col.body.appendChild(card.node);
      trim(col);
      layoutColumn(col);
      updateCount(col, true);
      empty.hidden = true;
      if (col.info.kind === "sig" && !fast) {
        col.node.classList.remove("hit");
        void col.node.offsetWidth;
        col.node.classList.add("hit");
      }
      chime(data, fast, col);
      await animate(card, pickEntrance(), fast);
      markLive();
    }

    async function replay(id) {
      const card = cards.get(id);
      if (!card || !card.node.isConnected) return;
      chime(card.data, false, columns.get(card.col));
      await animate(card, pickEntrance(), false);
      markLive();
    }

    async function drain() {
      if (busy) return;
      busy = true;
      try {
        while (pending.length) {
          const job = pending.shift();
          const waiting = pending.reduce((sum, item) => sum + (item.type === "card" ? 1 : 0), 0);
          try {
            if (job.type === "replay") await replay(job.id);
            else await playCard(job.data, waiting >= (Number(options.fast_after) || 6));
          } catch (error) {
            console.warn("debutkit 후원 벽", error);
          }
        }
      } finally {
        busy = false;
      }
    }

    // ---------------------------------------------------------- 받은 값 적용
    // 전체 값: 사라진 카드는 빼고(비우기), 칸이 바뀐 카드는 옮기고(따로 세우기, 되돌리기), 본 적 없는 새 번호는 차례로 연출.
    // 처음 연결할 때와 되돌린 카드(이미 본 번호)는 연출 없이 바로
    function applyState(state, initial) {
      setOptions(state.options);
      const list = state.cards || [];
      const incoming = new Map(list.map((card) => [card.id, card]));
      for (let i = pending.length - 1; i >= 0; i--) {
        const job = pending[i];
        if (job.type !== "card") continue;
        const fresh = incoming.get(job.data.id);
        if (fresh) job.data = fresh;
        else pending.splice(i, 1);
      }
      updateColumns(state.columns || []);
      let leaving = 0;
      for (const card of [...cards.values()]) {
        const fresh = incoming.get(card.data.id);
        if (!fresh) {
          removeCard(card, !initial, leaving++);
          continue;
        }
        if (fresh.column !== card.col || cardMark(fresh) !== card.mark || !columns.has(card.col)) {
          removeCard(card, false);
          placeInstant(fresh);
        }
      }
      const queued = new Set(pending.filter((job) => job.type === "card").map((job) => job.data.id));
      for (const data of list) {
        if (cards.has(data.id) || queued.has(data.id)) continue;
        if (initial || data.id <= maxId) placeInstant(data);
        else pending.push({ type: "card", data });
      }
      for (const data of list) maxId = Math.max(maxId, data.id);
      refresh();
      markLive();
      drain();
    }

    function applyAdd(message) {
      setOptions(message.options);
      const data = message.card;
      updateColumns(message.columns || []);
      if (data && !cards.has(data.id) && !pending.some((job) => job.type === "card" && job.data.id === data.id)) {
        pending.push({ type: "card", data });
        maxId = Math.max(maxId, data.id);
      }
      refresh();
      drain();
    }

    async function resync() {
      try {
        applyState(await (await fetch("/wall/view", { cache: "no-store" })).json(), false);
      } catch (error) {
        // 다음 값에서 다시
      }
    }

    function receive(message, first) {
      const gap = !first && typeof message.rev === "number" && message.rev > lastRev + 1;
      if (typeof message.rev === "number") lastRev = first ? message.rev : Math.max(lastRev, message.rev);
      if (message.type === "add") applyAdd(message);
      else if (message.type === "replay") {
        pending.push({ type: "replay", id: message.id });
        drain();
      } else applyState(message, first && !connectedOnce);
      if (first) connectedOnce = true;
      if (gap) resync();  // 놓친 값(멈춘 화면 등)이 있으면 전체를 다시 받음
    }

    // ---------------------------------------------------------- 칸 옮기기, 크기(OBS 상호작용, 조작 화면 미리보기)
    let hotTimer = 0;
    addEventListener("pointermove", () => {
      stage.classList.add("hot");
      clearTimeout(hotTimer);
      hotTimer = setTimeout(() => stage.classList.remove("hot"), 2500);
    });

    function drag(col, event, mode) {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      const target = event.currentTarget;
      const start = { x: event.clientX, y: event.clientY, box: { x: col.info.x, y: col.info.y, w: col.info.w, h: col.info.h } };
      const snap = (value) => Math.round(value / 10) * 10;
      let moved = false;
      col.dragging = true;
      col.node.classList.add("dragging");
      try {
        target.setPointerCapture(event.pointerId);
      } catch (error) {
        // 캡처할 수 없는 환경: 창 전체에서 받음
      }
      const move = (next) => {
        const dx = (next.clientX - start.x) / scale;
        const dy = (next.clientY - start.y) / scale;
        if (!moved && Math.abs(dx) + Math.abs(dy) < 3) return;
        moved = true;
        const box = { ...start.box };
        if (mode === "move") {  // 무대 안에서만(아래로 옮기면 높이를 줄여 맞춤)
          box.x = clamp(snap(box.x + dx), 0, 1920 - box.w);
          box.y = clamp(snap(box.y + dy), 0, 1080 - 160);
          box.h = clamp(box.h, 160, 1080 - box.y);
        } else {
          box.w = clamp(snap(box.w + dx), 120, 1920 - box.x);
          box.h = clamp(snap(box.h + dy), 160, 1080 - box.y);
        }
        Object.assign(col.info, box);
        place(col);
        if (mode === "size") {
          renderHead(col);
          layoutColumn(col);
        }
      };
      const up = () => {
        target.removeEventListener("pointermove", move);
        target.removeEventListener("pointerup", up);
        target.removeEventListener("pointercancel", up);
        col.dragging = false;
        col.node.classList.remove("dragging");
        if (moved) post("/wall/layout", { key: col.key, x: col.info.x, y: col.info.y, w: col.info.w, h: col.info.h });
      };
      target.addEventListener("pointermove", move);
      target.addEventListener("pointerup", up);
      target.addEventListener("pointercancel", up);
    }

    // ---------------------------------------------------------- 연결
    fontsReady.then(() => {
      // 공유 연결(live.js): 연결(다시 연결 포함) 직후의 값(initial)은 지금 상태
      window.debutkitLive.subscribe(["wall", "theme"], (feed, message, initial) => {
        if (feed === "wall" && message) receive(message, initial);
      });
    });
    window.debutkitWall = { columns, cards, pending, applyState, applyAdd, layoutColumn };  // 시험용
  }

  // ================================================================ 공통: 설계 폭에 맞춰 줄이고 1.5초마다 확인
  function scaled(node, width) {
    const fit = () => {
      node.style.transform = `scale(${Math.max(0.2, innerWidth / width)})`;
    };
    addEventListener("resize", fit);
    fit();
  }

  function poll(part, render, every) {
    let shown = "";
    const tick = async () => {
      try {
        const data = await (await fetch(`/wall/view?part=${part}`, { cache: "no-store" })).json();
        const mark = JSON.stringify(data[part]);
        if (mark !== shown) {
          shown = mark;
          render(data[part]);
        }
      } catch (error) {
        // 오버레이가 꺼짐: 마지막 화면 유지
      }
      setTimeout(tick, every);
    };
    fontsReady.then(tick);
    // 방송 색, 방송 스타일, 글꼴은 공유 연결의 theme 항목으로 새로고침 없이(live.js가 debutkitTheme에 넘김)
    if (window.debutkitLive) window.debutkitLive.subscribe(["theme"], () => {});
  }

  function countUp(node, from, to, format) {
    const began = performance.now();
    const step = () => {
      const t = Math.min(1, (performance.now() - began) / 900);
      node.textContent = format(from + (to - from) * (1 - Math.pow(1 - t, 3)));
      if (t < 1) requestAnimationFrame(step);
    };
    if (from === to) node.textContent = format(to);
    else step();
  }
  const whole = (value) => Math.round(value).toLocaleString("ko-KR");

  // ================================================================ 목표 게이지
  function goalView() {
    const box = el("div", "wg");
    const plate = el("div", "wg-plate");
    const head = el("div", "wg-head");
    const tag = el("span", "wg-tag");
    const value = el("span", "wg-value");
    const current = el("span", "", "0");
    const target = el("small");
    value.append(current, target);
    const percent = el("span", "wg-pct", "0%");
    head.append(tag, value, percent);
    const track = el("div", "wg-track");
    const fill = el("div", "wg-fill");
    fill.dataset.empty = "";
    const ticks = el("div");
    track.append(fill, ticks);
    const marks = el("div", "wg-marks");
    plate.append(head, track, marks);
    box.appendChild(plate);
    root.appendChild(box);
    scaled(box, 1280);
    let previous = null;
    let shownMilestones = "";
    let stamp = null;

    function celebrate(anchor, colors) {
      const rect = anchor.getBoundingClientRect();
      const base = box.getBoundingClientRect();
      const factor = rect.width ? anchor.offsetWidth / rect.width : 1;
      const layer = burst("wg-burst", 12, 110, colors);
      layer.style.left = `${(rect.left - base.left + rect.width / 2) * factor}px`;
      layer.style.top = `${(rect.top - base.top + rect.height / 2) * factor}px`;
      box.appendChild(layer);
      setTimeout(() => layer.remove(), 1300);
    }

    function render(goal) {
      tag.textContent = goal.title;
      target.textContent = `/ ${goal.target_text}`;
      const before = previous ? previous.current : goal.current;
      countUp(current, before, goal.current, whole);
      percent.textContent = `${Math.floor(goal.percent)}%`;
      fill.style.width = `${clamp(goal.percent, 0, 100)}%`;
      if (goal.percent > 0) delete fill.dataset.empty;
      else fill.dataset.empty = "";
      box.classList.toggle("done", goal.reached);
      const layout = JSON.stringify(goal.milestones.map((item) => [item.at, item.label, item.position]));
      if (layout !== shownMilestones) {
        shownMilestones = layout;
        ticks.replaceChildren();
        marks.replaceChildren();
        let lastLeft = -100;
        let two = false;
        goal.milestones.forEach((item) => {
          const tick = el("span", "wg-tick");
          tick.style.left = `${item.position}%`;
          ticks.appendChild(tick);
          const mark = el("span", "wg-mark");
          mark.append(el("b", "", item.text));
          if (item.label) mark.append(document.createTextNode(item.label));
          mark.style.left = `${item.position}%`;
          if (item.position < 6) mark.classList.add("edge-left");
          if (item.position > 94) mark.classList.add("edge-right");
          if (item.position - lastLeft < 16) {  // 가까운 중간 목표는 아랫줄로
            mark.classList.add("low");
            two = true;
            lastLeft = -100;
          } else {
            lastLeft = item.position;
          }
          marks.appendChild(mark);
        });
        marks.classList.toggle("two", two);
        marks.hidden = !goal.milestones.length;
      }
      goal.milestones.forEach((item, index) => {
        const mark = marks.children[index];
        const tick = ticks.children[index];
        if (!mark) return;
        mark.classList.toggle("reached", item.reached);
        tick.classList.toggle("reached", item.reached);
        const was = previous && previous.milestones[index] && previous.milestones[index].at === item.at && previous.milestones[index].reached;
        if (previous && item.reached && !was) {  // 새로 닿은 중간 목표
          mark.classList.remove("pop");
          void mark.offsetWidth;
          mark.classList.add("pop");
          setTimeout(() => celebrate(mark, [themed("highlight", "#ffd84d"), themed("primary", "#ff4f8b"), "#faf7f5"]), 900);
          if (params.has("sound")) setTimeout(() => tone("aura", 2), 900);
        }
      });
      if (goal.reached && !stamp) {
        stamp = el("span", "wg-stamp", "달성");
        plate.appendChild(stamp);
        if (previous && !previous.reached) {
          setTimeout(() => celebrate(percent, [themed("highlight", "#ffd84d"), themed("primary", "#ff4f8b"), "#faf7f5", themed("highlight", "#ffd84d")]), 300);
          if (params.has("sound")) tone("goal");
        }
      } else if (!goal.reached && stamp) {
        stamp.remove();
        stamp = null;
      }
      previous = goal;
    }

    poll("goal", render, 1500);
  }

  // ================================================================ 후원 순위
  function rankView() {
    const box = el("div", "wr");
    const head = el("div", "wr-head");
    const tag = el("span", "tag");
    head.append(tag, el("span", "basis", "원 기준"));
    const list = el("div", "wr-list");
    const sub = el("span", "wr-sub", "그 밖의 후원");
    sub.hidden = true;
    const others = el("div", "wr-list wr-others");
    others.hidden = true;
    box.append(head, list, sub, others);
    root.appendChild(box);
    scaled(box, 560);
    const rows = new Map();
    const otherRows = new Map();

    function nameOf(entry) {
      return entry.name || `${platformOf(entry.platform).label} 후원자`;
    }

    function sync(target, map, entries, height, numbered) {
      const seen = new Set();
      let top = 0;
      entries.forEach((entry, index) => {
        seen.add(entry.key);
        let row = map.get(entry.key);
        if (!row) {
          const node = el("div", "wr-row new");
          const rank = el("span", "wr-rank");
          const dot = el("span", "wr-dot");
          const name = el("span", "wr-name");
          const amount = el("span", "wr-amount");
          if (numbered) node.appendChild(rank);
          else node.style.paddingLeft = "14px";
          node.append(dot, name, amount);
          node.style.top = `${index * height}px`;
          target.appendChild(node);
          setTimeout(() => node.classList.remove("new"), 700);
          row = { node, rank, dot, name, amount, text: "" };
          map.set(entry.key, row);
        }
        row.node.classList.remove("gone", "r1", "r2", "r3");
        if (numbered && entry.rank <= 3) row.node.classList.add(`r${entry.rank}`);
        row.rank.textContent = String(entry.rank || index + 1);
        row.dot.style.setProperty("--platform", platformOf(entry.platform).color);
        row.name.textContent = nameOf(entry);
        if (row.text && row.text !== entry.text) {
          row.amount.classList.remove("bump");
          void row.amount.offsetWidth;
          row.amount.classList.add("bump");
        }
        row.text = entry.text;
        row.amount.textContent = entry.text;
        row.node.style.top = `${top}px`;
        top += (numbered && entry.rank === 1 ? height + 8 : height);
      });
      for (const [key, row] of [...map]) {
        if (seen.has(key)) continue;
        map.delete(key);
        row.node.classList.add("gone");
        setTimeout(() => row.node.remove(), 450);
      }
      target.style.height = `${Math.max(0, top - 8)}px`;
    }

    let emptyRow = null;
    function render(rank) {
      tag.textContent = rank.title;
      sync(list, rows, rank.entries, 64, true);
      if (!rank.entries.length && !emptyRow) {
        emptyRow = el("div", "wr-row empty", "아직 후원이 없습니다");
        list.appendChild(emptyRow);
        list.style.height = "56px";
      } else if (rank.entries.length && emptyRow) {
        emptyRow.remove();
        emptyRow = null;
      }
      const showOthers = rank.others_mode === "separate" && rank.others.length > 0;
      sub.hidden = !showOthers;
      others.hidden = !showOthers;
      sync(others, otherRows, showOthers ? rank.others : [], 52, false);
    }

    poll("rank", render, 2000);
  }
})();
