// debutkit 뽑기판(OBS 브라우저 소스, 권장 1920x1080, 평소 투명). /live?feeds=pick 으로 판 상태를 받아 그리고, 칸이 열리면 하나씩 차례로 연출한다.
// 콘셉트 "방송 소품": 잉크 외곽선과 흐림 없는 딱딱한 그림자, 종이 바탕, 테마 색 하나에서 나온 덮개와 당첨 띠, 금색은 희귀 상품 전용.
// 연출 순서: 칸 집중, 덮개 열림(테마마다 다름), 결과 카드와 효과, 소리, 정리(칸은 열린 채로 남음).
// 열리지 않은 칸의 상품은 서버가 보내지 않는다(이 화면은 열린 칸만 안다). 글은 textContent로만 넣는다.
// 주소: ?bg=dark, ?bg=light, ?bg=checker 미리보기 배경(이 화면에서만), ?mute 소리 끔
// 조작 화면도 이 파일을 불러 소리 미리 듣기(window.debutkitPick.preview)에 쓴다(#pick이 없으면 연출은 시작하지 않음)
"use strict";

(() => {
  const params = new URLSearchParams(location.search);
  const NS = "http://www.w3.org/2000/svg";
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const rand = (low, high) => low + Math.random() * (high - low);
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const svgEl = (tag, attributes) => {
    const node = document.createElementNS(NS, tag);
    for (const [name, value] of Object.entries(attributes || {})) node.setAttribute(name, String(value));
    return node;
  };

  // ---------------------------------------------------------------- 소리(브라우저에서 합성. 음원 파일 없음)
  let audio = null;
  let master = null;
  let soundOn = false;
  let volume = 0.7;

  function context() {
    if (!audio) {
      audio = new (window.AudioContext || window.webkitAudioContext)();
      master = audio.createGain();
      master.connect(audio.destination);
    }
    master.gain.setValueAtTime(volume, audio.currentTime);
    if (audio.state === "suspended") audio.resume().catch(() => null);
    return audio;
  }

  function note(type, frequency, start, length, peak, options = {}) {
    const now = audio.currentTime + start;
    const oscillator = audio.createOscillator();
    const gain = audio.createGain();
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(frequency, now);
    if (options.to) oscillator.frequency.exponentialRampToValueAtTime(options.to, now + length);
    if (options.vibrato) {
      const lfo = audio.createOscillator();
      const depth = audio.createGain();
      lfo.frequency.value = options.vibrato[0];
      depth.gain.value = options.vibrato[1];
      lfo.connect(depth).connect(oscillator.frequency);
      lfo.start(now);
      lfo.stop(now + length + 0.05);
    }
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(peak, now + 0.008);
    gain.gain.setValueAtTime(peak, now + Math.min(length * 0.5, options.hold || 0));
    gain.gain.exponentialRampToValueAtTime(0.0001, now + length);
    oscillator.connect(gain);
    if (options.filter) {
      const filter = audio.createBiquadFilter();
      filter.type = "lowpass";
      filter.frequency.value = options.filter;
      gain.connect(filter).connect(master);
    } else {
      gain.connect(master);
    }
    oscillator.start(now);
    oscillator.stop(now + length + 0.05);
  }

  function noise(start, length, peak, from, to) {
    const now = audio.currentTime + start;
    const size = Math.max(1, Math.floor(audio.sampleRate * length));
    const buffer = audio.createBuffer(1, size, audio.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < size; i++) data[i] = Math.random() * 2 - 1;
    const source = audio.createBufferSource();
    source.buffer = buffer;
    const filter = audio.createBiquadFilter();
    filter.type = "bandpass";
    filter.Q.value = 1.1;
    filter.frequency.setValueAtTime(from, now);
    filter.frequency.exponentialRampToValueAtTime(to, now + length);
    const gain = audio.createGain();
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(peak, now + length * 0.25);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + length);
    source.connect(filter).connect(gain).connect(master);
    source.start(now);
    source.stop(now + length + 0.02);
  }

  const SOUNDS = {
    whoosh: () => noise(0, 0.34, 0.5, 400, 2600),
    scratch: () => [0, 0.15, 0.3, 0.45, 0.6].forEach((at) => noise(at + 0.12, 0.13, 0.45, 2200 + Math.random() * 900, 4200)),
    flip: () => { note("triangle", 880, 0, 0.07, 0.12); note("triangle", 1320, 0.04, 0.06, 0.08); },
    pop: () => { note("sine", 900, 0, 0.2, 0.32, { to: 220 }); note("triangle", 2093, 0.1, 0.28, 0.06); },
    fanfare: () => {
      [392, 523.25, 659.25].forEach((frequency, index) => note("square", frequency, index * 0.1, 0.12, 0.07, { filter: 2400 }));
      [523.25, 659.25, 783.99, 1046.5].forEach((frequency) => note("square", frequency, 0.32, 0.8, 0.055, { filter: 2600, hold: 0.25 }));
    },
    chime: () => { note("triangle", 659.25, 0, 0.5, 0.06); [1318.5, 1975.5, 2637].forEach((frequency, index) => note("sine", frequency, index * 0.08, 1.4, 0.12)); },
    coin: () => { note("triangle", 1046.5, 0, 0.08, 0.16); note("triangle", 1568, 0.07, 0.5, 0.16, { hold: 0.08 }); },
    shimmer: () => [2093, 2349.3, 2637, 3136, 3520].forEach((frequency, index) => note("sine", frequency, 0.45 + index * 0.07, 0.55, 0.05)),
    boing: () => note("sine", 380, 0, 0.6, 0.3, { to: 140, vibrato: [14, 32] }),
    buzzer: () => { note("sawtooth", 116, 0, 0.5, 0.13, { filter: 900, hold: 0.35 }); note("sawtooth", 123, 0, 0.5, 0.13, { filter: 900, hold: 0.35 }); },
    slide: () => {
      [392, 370, 349.2].forEach((frequency, index) => note("sawtooth", frequency, index * 0.3, 0.28, 0.12, { filter: 1300, hold: 0.18 }));
      note("sawtooth", 330, 0.9, 0.95, 0.12, { filter: 1300, to: 294, vibrato: [5.5, 7], hold: 0.5 });
    },
  };

  function sound(name) {
    if (!soundOn || !SOUNDS[name]) return;
    try {
      context();
      SOUNDS[name]();
    } catch (error) {
      // 소리를 낼 수 없는 환경
    }
  }

  // 조작 화면의 미리 듣기(그 화면에서만 재생. 방송에 나가지 않음)
  window.debutkitPick = {
    preview(name, level) {
      const before = [soundOn, volume];
      soundOn = true;
      volume = Math.max(0, Math.min(1, Number(level ?? 70) / 100));
      sound(name);
      [soundOn, volume] = before;
    },
    sounds: Object.keys(SOUNDS),
  };

  const root = document.getElementById("pick");
  if (!root) return;
  const resultLayer = document.getElementById("pick-result");
  const fxLayer = document.getElementById("pick-fx");
  if (["dark", "light", "checker"].includes(params.get("bg"))) document.body.classList.add(`bg-${params.get("bg")}`);
  const muted = params.has("mute");
  const PLATFORMS = (window.debutkit && window.debutkit.PLATFORMS) || {};

  const FONTS = {
    blackhan: ['"Black Han Sans", "Malgun Gothic", sans-serif', 400],
    pretendard: ['"Pretendard", "Malgun Gothic", sans-serif', 700],
    malgun: ['"Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo", sans-serif', 700],
    serif: ['"Batang", "바탕", "Noto Serif KR", "AppleMyungjo", serif', 700],
  };
  const OPEN_MS = { card: 680, ticket: 1080, envelope: 1020, capsule: 900, door: 780, sticker: 1080, memo: 980 };
  const OPEN_SOUND = { card: "flip", ticket: "scratch", envelope: "whoosh", capsule: "pop", door: "whoosh", sticker: "whoosh", memo: "whoosh" };
  const ASPECT = { card: 63 / 88, ticket: 1.22, envelope: 1.42, capsule: 1, door: 0.74, sticker: 1, memo: 1 };  // 가로 / 세로
  const TIER = { win: "당첨", rare: "대박", miss: "다음 기회에" };
  const WIN_EFFECTS = ["confetti", "stars", "ribbons", "rays", "coins", "hearts", "notes", "rings", "sparkle", "pixels"];

  // 글꼴을 다 불러온 뒤 그림(글자 크기 계산과 공개 도중 글꼴이 바뀌어 보이지 않게)
  const fontsReady = document.fonts
    ? Promise.all(['40px "Black Han Sans"', '600 20px "Pretendard"', '700 20px "Pretendard"'].map((font) => document.fonts.load(font))).catch(() => null)
    : Promise.resolve();

  // ---------------------------------------------------------------- 색, 무늬
  function svgUrl(body, width, height) {
    const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${width}' height='${height}' viewBox='0 0 ${width} ${height}'>${body}</svg>`;
    return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
  }

  function starPath(cx, cy, outer, inner = outer * 0.45, points = 5) {
    const parts = [];
    for (let i = 0; i < points * 2; i++) {
      const radius = i % 2 ? inner : outer;
      const angle = -Math.PI / 2 + (i * Math.PI) / points;
      parts.push(`${(cx + Math.cos(angle) * radius).toFixed(2)},${(cy + Math.sin(angle) * radius).toFixed(2)}`);
    }
    return `M${parts.join("L")}Z`;
  }

  const HEART = "M0 6 C-9 0 -7 -8 0 -4 C7 -8 9 0 0 6 Z";

  function applyDisplay(display) {
    const palette = display.palette;
    const [family, weight] = FONTS[display.font] || FONTS.blackhan;
    const styles = display.styles;
    const vars = {
      "--ink": palette.ink, "--paper": palette.paper, "--cover": palette.cover, "--cover-deep": palette.cover_deep, "--cover-light": palette.cover_light,
      "--on-cover": palette.on_cover, "--board": palette.board, "--board-deep": palette.board_deep, "--text": palette.text, "--win": palette.win,
      "--on-win": palette.on_win, "--gold": palette.gold, "--gold-deep": palette.gold_deep, "--miss": palette.miss, "--muted": palette.muted,
      "--display": family, "--display-weight": weight,
      "--title-size": `${styles.title.size}px`, "--title-line": styles.title.line / 100, "--title-align": styles.title.align,
      "--caption-size": `${styles.caption.size}px`, "--caption-line": styles.caption.line / 100, "--caption-align": styles.caption.align,
      "--rs": styles.result.size / 100, "--result-align": styles.result.align,
      "--pat-stars": svgUrl(`<path d='${starPath(11, 11, 8)}' fill='${palette.cover_deep}'/><path d='${starPath(31, 31, 5.5)}' fill='${palette.cover_light}'/>`, 42, 42),
      "--pat-hearts": svgUrl(`<path d='${HEART}' transform='translate(10 11) scale(0.9)' fill='${palette.cover_deep}'/>`
        + `<path d='${HEART}' transform='translate(30 31) scale(0.65)' fill='${palette.cover_light}'/>`, 40, 40),
      "--pat-waves": svgUrl(`<path d='M-2 11 Q 9 2 20 11 T 42 11' fill='none' stroke='${palette.cover_deep}' stroke-width='3.2'/>`, 40, 20),
      "--ray": hexAlpha(palette.win, 0.34),
    };
    const rootStyle = document.documentElement.style;
    for (const [name, value] of Object.entries(vars)) rootStyle.setProperty(name, String(value));
    for (const [part, name] of [["title", "--title-color"], ["caption", "--caption-color"], ["result", "--result-color"]]) {
      if (styles[part].color) rootStyle.setProperty(name, styles[part].color);
      else rootStyle.removeProperty(name);
    }
  }

  function hexAlpha(hex, alpha) {
    const value = parseInt(String(hex).slice(1), 16);
    return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
  }

  // 고양이 귀 마이크 문양(debutkit 기호, 추첨 카드 뒷면과 같은 도형)
  function emblem(body, eyes) {
    const svg = svgEl("svg", { viewBox: "30 4 60 82", class: "pk-emblem", "aria-hidden": "true" });
    svg.appendChild(svgEl("path", { d: "M38 32 L42 9 L56 21 Z M82 32 L78 9 L64 21 Z", fill: body, stroke: body, "stroke-width": 6, "stroke-linejoin": "round" }));
    svg.appendChild(svgEl("rect", { x: 36, y: 18, width: 48, height: 64, rx: 24, fill: body }));
    svg.appendChild(svgEl("rect", { x: 45.5, y: 40, width: 8, height: 13, rx: 4, fill: eyes }));
    svg.appendChild(svgEl("rect", { x: 66.5, y: 40, width: 8, height: 13, rx: 4, fill: eyes }));
    return svg;
  }

  function bow(palette) {  // 선물 포장의 리본 매듭
    const svg = svgEl("svg", { viewBox: "0 0 100 60", class: "pk-bow", "aria-hidden": "true" });
    const style = { fill: palette.cover_light, stroke: palette.ink, "stroke-width": 5, "stroke-linejoin": "round" };
    svg.appendChild(svgEl("path", { d: "M50 34 C34 8 8 6 10 26 C12 44 36 42 50 34 Z", ...style }));
    svg.appendChild(svgEl("path", { d: "M50 34 C66 8 92 6 90 26 C88 44 64 42 50 34 Z", ...style }));
    svg.appendChild(svgEl("rect", { x: 40, y: 24, width: 20, height: 20, rx: 6, ...style }));
    return svg;
  }

  // ---------------------------------------------------------------- 판 그리기
  let boardEl = null;
  let metrics = { w: 100, h: 100, u: 100 };
  let shownKey = "";

  function grid(count, columns, width, height, aspect) {
    let best = null;
    const options = columns ? [Math.min(columns, count)] : Array.from({ length: Math.min(count, 20) }, (_, index) => index + 1);
    for (const cols of options) {
      const rows = Math.ceil(count / cols);
      const ratio = 0.13;
      const byWidth = width / (cols + (cols - 1) * ratio);
      const byHeight = height / (rows + (rows - 1) * ratio);
      let w = Math.min(byWidth, byHeight * aspect);
      w = Math.min(w, 250 * Math.min(1, aspect), 250 * aspect);
      const score = w - (cols * rows - count) * 0.8;
      if (!best || score > best.score) best = { cols, rows, w, h: w / aspect, score };
    }
    best.gap = Math.max(8, Math.min(30, best.w * 0.13));
    return best;
  }

  function textUnits(text) {
    let units = 0;
    for (const char of text) units += /[ᄀ-ᇿ㄰-㆏가-힯一-鿿]/.test(char) ? 1 : char === " " ? 0.35 : 0.6;
    return Math.max(1, units);
  }

  function fitSize(text, width, height) {  // 칸 안에 들어가는 가장 큰 글자 크기와 줄 수(1줄에서 3줄)
    const units = textUnits(text);
    const words = text.split(" ").length;
    const most = words > 1 ? Math.min(3, words) : units > 7 ? 2 : 1;  // 띄어쓰기 없는 짧은 이름은 한 줄(성대모 / 사 처럼 끊지 않음)
    let best = { size: 0, lines: 1 };
    [[1, 0.36], [2, 0.25], [3, 0.19]].filter(([lines]) => lines <= most).forEach(([lines, limit]) => {
      const size = Math.min(height * limit, width / ((units / lines) * (lines > 1 ? 1.18 : 1.04)));
      if (size > best.size * 1.04) best = { size, lines };
    });
    return { size: Math.max(9, Math.round(best.size)), lines: best.lines };
  }

  function balance(text, lines) {  // 띄어쓰기가 있으면 줄 길이가 비슷하게 나눔(예: 노래 / 한 곡)
    const words = text.split(" ");
    if (lines < 2 || words.length < 2) return text;
    const target = textUnits(text) / lines;
    const rows = [];
    let row = [];
    for (const word of words) {
      if (row.length && rows.length < lines - 1 && textUnits([...row, word].join(" ")) > target * 1.15) {
        rows.push(row.join(" "));
        row = [];
      }
      row.push(word);
    }
    rows.push(row.join(" "));
    return rows.join("\n");
  }

  function fillPrize(node, info, number, display) {
    node.className = `pk-prize t-${info.tier}`;
    const roomy = display.theme === "capsule" ? 0.64 : display.theme === "ticket" ? 0.72 : 0.84;
    const fit = fitSize(info.prize, metrics.w * roomy, metrics.h * (display.theme === "ticket" ? 0.62 : 0.78));
    const name = el("span", "pk-name", balance(info.prize, fit.lines));
    name.style.fontSize = `${fit.size}px`;
    node.replaceChildren(name, el("span", "pk-pn", String(number)));
    if (info.by && metrics.u >= 120) node.appendChild(el("span", "pk-by", info.by));
    if (display.theme === "ticket") node.appendChild(el("span", "pk-tag", `No.${String(number).padStart(2, "0")}`));
  }

  function coverNode(number, display) {
    const cover = el("div", "pk-cover");
    const kind = display.cover;
    const pattern = `pat-${kind}`;
    const theme = display.theme;
    if (theme === "ticket") {
      const face = el("div", "pk-face");
      for (let k = 0; k < 5; k++) {
        const strip = el("div", `pk-strip ${pattern}`);
        strip.style.setProperty("--k", k);
        face.appendChild(strip);
      }
      cover.appendChild(face);
    } else if (theme === "capsule") {
      cover.append(el("div", "pk-face"), el("div", "pk-half pk-bottom"), el("div", `pk-half pk-top ${pattern}`));
    } else {
      cover.appendChild(el("div", `pk-face ${pattern}`));
      if (theme === "envelope") {
        const flap = el("div", "pk-flap");
        flap.appendChild(el("i"));
        cover.appendChild(flap);
      } else if (theme === "door") {
        cover.appendChild(el("span", "pk-knob"));
      } else if (theme === "sticker") {
        const curl = el("div", "pk-curl");
        curl.appendChild(el("i"));
        cover.appendChild(curl);
      } else if (theme === "memo") {
        cover.appendChild(el("span", "pk-tape"));
      }
    }
    if (kind === "emblem") cover.appendChild(emblem(display.palette.on_cover, display.palette.cover));
    if (kind === "gift") cover.appendChild(bow(display.palette));
    if (kind === "question") cover.appendChild(el("span", "pk-q", "?"));
    if (display.show_numbers) {
      const corner = ["emblem", "gift", "question"].includes(kind);
      cover.appendChild(el("span", `pk-num${kind === "number" ? " big" : corner ? " corner" : ""}`, String(number)));
    }
    return cover;
  }

  function cellNode(cell, covered, display) {
    const node = el("div", "pk-cell");
    node.dataset.n = String(cell.n);
    node.style.setProperty("--i", String(cell.n - 1));
    const inner = el("div", "pk-inner");
    const prize = el("div", "pk-prize");
    inner.append(prize, coverNode(cell.n, display));
    node.appendChild(inner);
    if (cell.prize !== undefined && !(cell.open && covered.has(cell.n))) {
      fillPrize(prize, cell, cell.n, display);
      node.classList.add(cell.open ? "open" : "revealed");
    } else if (display.theme === "ticket") {
      node.querySelector(".pk-prize").appendChild(el("span", "pk-tag", `No.${String(cell.n).padStart(2, "0")}`));
    }
    return node;
  }

  function foot(snapshot, covered) {
    const display = snapshot.display;
    const box = el("div", "pk-foot");
    if (snapshot.help && snapshot.help.length) {
      const help = el("div", "pk-help");
      for (const line of snapshot.help) help.appendChild(el("span", "", line));
      box.appendChild(help);
    }
    if (display.show_remaining && Array.isArray(snapshot.remaining)) {
      // 연출을 기다리는 칸의 상품은 아직 남은 것으로 센다(공개 전에 요약이 먼저 바뀌지 않게)
      const waiting = new Map();
      for (const cell of snapshot.cells) if (cell.open && covered.has(cell.n)) waiting.set(cell.prize, (waiting.get(cell.prize) || 0) + 1);
      const left = el("div", "pk-left");
      for (const item of snapshot.remaining) {
        const count = Math.min(item.total, item.left + (waiting.get(item.name) || 0));
        const chip = el("span", `t-${item.tier}${count ? "" : " gone"}`, item.name);
        chip.appendChild(el("b", "", `${count}/${item.total}`));
        left.appendChild(chip);
      }
      box.appendChild(left);
    }
    const meta = el("div", "pk-meta");
    const hiding = snapshot.cells.filter((cell) => cell.open && covered.has(cell.n)).length;
    meta.appendChild(el("span", "count", `${snapshot.opened - hiding}/${snapshot.total}`));
    if (display.show_hash) {
      const commit = snapshot.commit;
      if (commit.revealed) {
        meta.appendChild(el("span", "done", "배치 공개"));
        meta.appendChild(el("span", "hash", `소금값 ${commit.salt}`));
      }
      meta.appendChild(el("span", "hash", `SHA-256 ${commit.hash}${commit.round > 1 ? ` (배치 ${commit.round})` : ""}`));
    }
    box.appendChild(meta);
    return box;
  }

  function render(snapshot, covered = new Set(), enter = false) {
    const display = snapshot.display;
    applyDisplay(display);
    root.dataset.position = display.position;
    root.classList.toggle("hidden", !snapshot.visible);
    const stage = el("div", `pk-stage theme-${display.theme}`);
    stage.style.setProperty("--scale", String(display.scale / 100));
    const panel = el("div", `pk-panel ${display.frame ? "framed" : "bare"}`);
    const head = el("div", "pk-head");
    if (display.title) head.appendChild(el("h1", "pk-title", display.title));
    if (display.caption) head.appendChild(el("p", "pk-caption", display.caption));
    const board = el("div", "pk-board");
    const bottom = foot(snapshot, covered);
    panel.append(head, board, bottom);
    stage.appendChild(panel);
    root.replaceChildren(stage);
    // 남은 공간에 맞춰 칸 크기 계산(1920x1080 기준, 크기 설정은 무대 전체를 확대, 축소)
    const used = head.offsetHeight + bottom.offsetHeight + (display.frame ? 26 + 20 + 8 + 28 : 28);
    const width = (display.position === "center" ? 1760 : 1500) - (display.frame ? 72 : 0);
    const plan = grid(snapshot.total, display.columns, width, Math.max(160, 970 - used), ASPECT[display.theme] || 1);
    metrics = { w: plan.w, h: plan.h, u: Math.min(plan.w, plan.h) };
    const vars = { "--cols": plan.cols, "--cw": `${plan.w.toFixed(1)}px`, "--ch": `${plan.h.toFixed(1)}px`, "--gap": `${plan.gap.toFixed(1)}px`,
      "--u": `${metrics.u.toFixed(1)}px`, "--line": Math.max(2, Math.min(4, Math.round(metrics.u * 0.028))) };
    for (const [name, value] of Object.entries(vars)) stage.style.setProperty(name, String(value));
    board.append(...snapshot.cells.map((cell) => cellNode(cell, covered, display)));
    boardEl = board;
    const key = `${snapshot.board.id}:${snapshot.commit.round}`;
    if (enter || key !== shownKey) stage.classList.add("enter");
    shownKey = key;
    root.setAttribute("aria-label", `${display.title} ${snapshot.opened}/${snapshot.total}`);
  }

  // ---------------------------------------------------------------- 효과(Web Animations, 흐림 없는 외곽선 소품)
  function spawn(node, x, y, keyframes, options) {
    node.classList.add("fx");
    node.style.left = `${x}px`;
    node.style.top = `${y}px`;
    fxLayer.appendChild(node);
    const total = options.duration + (options.delay || 0);
    try {
      const animation = node.animate(keyframes, { fill: "both", ...options });
      animation.onfinish = () => node.remove();
    } catch (error) {
      // 애니메이션을 지원하지 않는 환경
    }
    setTimeout(() => node.remove(), total + 400);
  }

  const center = (box) => ({ x: box.left + box.width / 2, y: box.top + box.height / 2 });

  function svgShape(width, height, viewBox, paths) {
    const svg = svgEl("svg", { width, height, viewBox });
    for (const { tag, ...attributes } of paths) svg.appendChild(svgEl(tag || "path", attributes));
    return svg;
  }

  const EFFECTS = {
    confetti(box, palette) {
      const { x, y } = center(box);
      const colors = [palette.win, palette.gold, palette.paper, palette.cover_light];
      for (let i = 0; i < 72; i++) {
        const bit = el("div", "bit");
        bit.style.background = colors[i % colors.length];
        const angle = -Math.PI / 2 + rand(-1.25, 1.25);
        const speed = rand(260, 620);
        const dx = Math.cos(angle) * speed;
        const peak = Math.sin(angle) * speed;
        const spin = rand(-900, 900);
        spawn(bit, x, y - box.height * 0.2, [
          { transform: "translate(-50%, -50%) rotate(0deg)", opacity: 1 },
          { transform: `translate(${dx * 0.7}px, ${peak}px) rotate(${spin * 0.4}deg)`, opacity: 1, offset: 0.35 },
          { transform: `translate(${dx * 0.95}px, ${rand(300, 520)}px) rotate(${spin * 0.85}deg)`, opacity: 1, offset: 0.82 },
          { transform: `translate(${dx}px, ${rand(560, 700)}px) rotate(${spin}deg)`, opacity: 0 },
        ], { duration: rand(1700, 2400), delay: rand(0, 160), easing: "cubic-bezier(0.25, 0.7, 0.5, 1)" });
      }
    },
    stars(box, palette) {
      const { x, y } = center(box);
      for (let i = 0; i < 16; i++) {
        const size = rand(40, 76);
        const star = svgShape(size, size, "-12 -12 24 24", [{ d: starPath(0, 0, 11, 5), fill: i % 3 ? palette.gold : palette.win, stroke: palette.ink, "stroke-width": 1.6,
          "stroke-linejoin": "round" }]);
        const angle = (i / 16) * Math.PI * 2 + rand(-0.15, 0.15);
        const distance = rand(380, 620);
        spawn(star, x - size / 2, y - size / 2, [
          { transform: "translate(0, 0) scale(0.3) rotate(0deg)", opacity: 1 },
          { transform: `translate(${Math.cos(angle) * distance * 0.75}px, ${Math.sin(angle) * distance * 0.75}px) scale(1.15) rotate(140deg)`, opacity: 1, offset: 0.6 },
          { transform: `translate(${Math.cos(angle) * distance}px, ${Math.sin(angle) * distance + 60}px) scale(0.7) rotate(220deg)`, opacity: 0 },
        ], { duration: rand(1100, 1400), easing: "cubic-bezier(0.15, 0.8, 0.3, 1)" });
      }
    },
    ribbons(box, palette) {
      const colors = [palette.win, palette.gold, palette.cover_light, palette.paper];
      for (let i = 0; i < 16; i++) {
        const ribbon = svgShape(30, 200, "0 0 30 200", [{ d: "M15 0 Q 29 25 15 50 T 15 100 T 15 150 T 15 200", fill: "none", stroke: palette.ink, "stroke-width": 13,
          "stroke-linecap": "round" }, { d: "M15 0 Q 29 25 15 50 T 15 100 T 15 150 T 15 200", fill: "none", stroke: colors[i % colors.length], "stroke-width": 8,
          "stroke-linecap": "round" }]);
        ribbon.classList.add("ribbon");
        const startX = (i + 0.5) * (1920 / 16) + rand(-40, 40);
        const sway = rand(-120, 120);
        spawn(ribbon, startX, -240, [
          { transform: `translate(0, 0) rotate(${rand(-30, 30)}deg)` },
          { transform: `translate(${sway}px, 700px) rotate(${rand(-40, 40)}deg)`, offset: 0.55 },
          { transform: `translate(${-sway * 0.5}px, 1400px) rotate(${rand(-60, 60)}deg)` },
        ], { duration: rand(2600, 3400), delay: rand(0, 700), easing: "cubic-bezier(0.3, 0.2, 0.6, 1)" });
      }
    },
    rays(box) {
      const rays = el("div", "pk-rays");
      resultLayer.insertBefore(rays, resultLayer.firstChild);
      try {
        rays.animate([
          { transform: "scale(0.5) rotate(0deg)", opacity: 0 },
          { transform: "scale(1) rotate(12deg)", opacity: 1, offset: 0.2 },
          { transform: "scale(1.05) rotate(40deg)", opacity: 1, offset: 0.8 },
          { transform: "scale(1.1) rotate(50deg)", opacity: 0 },
        ], { duration: 2600, easing: "ease-out", fill: "both" }).onfinish = () => rays.remove();
      } catch (error) {
        // 애니메이션을 지원하지 않는 환경
      }
      setTimeout(() => rays.remove(), 3000);
      EFFECTS.sparkle(box, null, 10);
    },
    coins(box, palette) {
      for (let i = 0; i < 30; i++) {
        const size = rand(42, 62);
        const holder = el("div");
        const coin = svgShape(size, size, "-20 -20 40 40", [
          { tag: "circle", r: 18, fill: palette.gold, stroke: palette.ink, "stroke-width": 3 },
          { tag: "circle", r: 11.5, fill: "none", stroke: palette.gold_deep, "stroke-width": 2.5 },
          { d: starPath(0, 0, 6, 2.8), fill: palette.gold_deep },
        ]);
        holder.appendChild(coin);
        const startX = rand(360, 1560);
        spawn(holder, startX, -80, [{ transform: "translateY(0)" }, { transform: `translateY(${rand(1180, 1260)}px)` }],
          { duration: rand(1500, 2300), delay: rand(0, 900), easing: "cubic-bezier(0.5, 0, 0.9, 0.7)" });
        try {
          coin.animate([{ transform: "scaleX(1)" }, { transform: "scaleX(0.12)" }, { transform: "scaleX(1)" }], { duration: rand(380, 620), iterations: Infinity });
        } catch (error) {
          // 애니메이션을 지원하지 않는 환경
        }
      }
    },
    hearts(box, palette) {
      const { x } = center(box);
      for (let i = 0; i < 20; i++) {
        const size = rand(36, 70);
        const heart = svgShape(size, size, "-11 -10 22 20", [{ d: HEART, fill: i % 3 === 0 ? palette.paper : palette.win, stroke: palette.ink, "stroke-width": 1.5,
          "stroke-linejoin": "round" }]);
        const startX = x + rand(-box.width * 0.55, box.width * 0.55);
        const drift = rand(-80, 80);
        spawn(heart, startX - size / 2, box.bottom - 20, [
          { transform: "translate(0, 0) scale(0.4)", opacity: 0 },
          { transform: `translate(${drift}px, -160px) scale(1)`, opacity: 1, offset: 0.25 },
          { transform: `translate(${-drift}px, -420px) scale(1.05) rotate(${rand(-20, 20)}deg)`, opacity: 1, offset: 0.7 },
          { transform: `translate(${drift * 0.5}px, -560px) scale(0.9)`, opacity: 0 },
        ], { duration: rand(2000, 2600), delay: rand(0, 700), easing: "ease-out" });
      }
    },
    notes(box, palette) {
      const glyphs = [
        [{ tag: "ellipse", cx: -4, cy: 12, rx: 6, ry: 4.5, transform: "rotate(-20 -4 12)" }, { d: "M1 11 V-13 Q 9 -9 11 -2", fill: "none" }],
        [{ tag: "ellipse", cx: -8, cy: 12, rx: 5.5, ry: 4, transform: "rotate(-20 -8 12)" }, { tag: "ellipse", cx: 9, cy: 8, rx: 5.5, ry: 4, transform: "rotate(-20 9 8)" },
          { d: "M-3 11 V-12 L14 -16 V7", fill: "none" }],
      ];
      for (let i = 0; i < 16; i++) {
        const size = rand(46, 78);
        const parts = glyphs[i % 2].map((part) => ({ fill: part.fill === "none" ? "none" : i % 3 ? palette.win : palette.paper, stroke: palette.ink, "stroke-width": 2.6,
          "stroke-linecap": "round", "stroke-linejoin": "round", ...part }));
        const noteSvg = svgShape(size, size, "-20 -20 40 40", parts);
        const side = i % 2 ? 1 : -1;
        const startX = center(box).x + side * rand(box.width * 0.3, box.width * 0.6);
        spawn(noteSvg, startX - size / 2, box.top + rand(0, box.height), [
          { transform: "translate(0, 0) rotate(0deg) scale(0.5)", opacity: 0 },
          { transform: `translate(${side * 60}px, -120px) rotate(${side * -12}deg) scale(1)`, opacity: 1, offset: 0.3 },
          { transform: `translate(${side * 20}px, -260px) rotate(${side * 10}deg) scale(1)`, opacity: 1, offset: 0.7 },
          { transform: `translate(${side * 90}px, -380px) rotate(${side * -8}deg) scale(0.9)`, opacity: 0 },
        ], { duration: rand(1900, 2500), delay: rand(0, 600), easing: "ease-in-out" });
      }
    },
    rings(box) {
      const { x, y } = center(box);
      for (let i = 0; i < 4; i++) {
        const ring = el("div", "ring");
        ring.style.width = "900px";
        ring.style.height = "900px";
        spawn(ring, x - 450, y - 450, [{ transform: "scale(0.15)", opacity: 1 }, { transform: "scale(1.7)", opacity: 0 }],
          { duration: 1100, delay: i * 170, easing: "cubic-bezier(0.2, 0.7, 0.3, 1)" });
      }
    },
    sparkle(box, palette, count = 26) {
      const { x, y } = center(box);
      const fill = palette ? [palette.gold, palette.paper] : ["#ffd84d", "#faf7f5"];
      for (let i = 0; i < count; i++) {
        const size = rand(30, 64);
        const angle = rand(0, Math.PI * 2);
        const distance = rand(Math.max(box.width, box.height) * 0.55, Math.max(box.width, box.height) * 0.85);
        const spark = svgShape(size, size, "-12 -12 24 24", [{ d: starPath(0, 0, 11, 2.6, 4), fill: fill[i % 2], stroke: "#1e2327", "stroke-width": 1.4,
          "stroke-linejoin": "round" }]);
        spawn(spark, x + Math.cos(angle) * distance - size / 2, y + Math.sin(angle) * distance * 0.7 - size / 2, [
          { transform: "scale(0) rotate(0deg)", opacity: 1 },
          { transform: "scale(1.2) rotate(45deg)", opacity: 1, offset: 0.45 },
          { transform: "scale(0) rotate(90deg)", opacity: 1 },
        ], { duration: rand(600, 900), delay: rand(0, 1300), easing: "ease-in-out" });
      }
    },
    pixels(box, palette) {
      const { x, y } = center(box);
      const colors = [palette.win, palette.gold, palette.paper, palette.cover];
      for (let i = 0; i < 48; i++) {
        const pixel = el("div", "pixel");
        pixel.style.background = colors[i % colors.length];
        const angle = rand(0, Math.PI * 2);
        const speed = rand(260, 560);
        const frames = [];
        for (let step = 0; step <= 6; step++) {
          const t = step / 6;
          frames.push({ transform: `translate(${Math.cos(angle) * speed * t}px, ${Math.sin(angle) * speed * t + 420 * t * t}px)`, opacity: step === 6 ? 0 : 1 });
        }
        spawn(pixel, x - 8, y - 8, frames, { duration: rand(1000, 1400), easing: "steps(14, end)" });
      }
    },
  };

  const MISS = {
    dust(box) {
      for (let i = 0; i < 10; i++) {
        const size = rand(46, 92);
        const puff = el("div", "puff");
        puff.style.width = `${size}px`;
        puff.style.height = `${size}px`;
        const side = i % 2 ? 1 : -1;
        spawn(puff, center(box).x + side * rand(0, box.width * 0.45) - size / 2, box.bottom - size * 0.6, [
          { transform: "translate(0, 0) scale(0.3)", opacity: 1 },
          { transform: `translate(${side * rand(40, 140)}px, ${rand(-40, 10)}px) scale(1)`, opacity: 0.9, offset: 0.5 },
          { transform: `translate(${side * rand(120, 220)}px, ${rand(-80, -20)}px) scale(1.2)`, opacity: 0 },
        ], { duration: rand(800, 1100), delay: rand(0, 120), easing: "cubic-bezier(0.2, 0.8, 0.4, 1)" });
      }
    },
    cloud(box, palette) {
      const { x } = center(box);
      const cloud = svgShape(260, 130, "0 0 260 130", [{ d: "M40 110 C10 110 6 70 36 64 C30 30 76 18 96 42 C108 10 162 8 172 44 C200 26 240 46 226 76 C254 84 248 112 220 112 Z",
        fill: palette.muted, stroke: palette.ink, "stroke-width": 6, "stroke-linejoin": "round" }]);
      const top = box.top - 150;
      spawn(cloud, x - 130, top, [{ transform: "translateY(-60px)", opacity: 0 }, { transform: "translateY(0)", opacity: 1, offset: 0.15 },
        { transform: "translateY(0)", opacity: 1, offset: 0.85 }, { transform: "translateY(-30px)", opacity: 0 }], { duration: 2200, easing: "ease-out" });
      for (let i = 0; i < 16; i++) {
        const drop = el("div", "drop");
        spawn(drop, x + rand(-100, 100), top + 110, [{ transform: "translateY(0)", opacity: 1 }, { transform: "translateY(150px)", opacity: 0 }],
          { duration: 520, delay: 300 + i * 95, easing: "ease-in" });
      }
    },
  };

  function runEffect(entry, display, card) {
    const box = card.getBoundingClientRect();
    try {
      if (entry.tier === "miss") {
        if (MISS[display.miss_effect]) MISS[display.miss_effect](box, display.palette);
        return;
      }
      let name = display.effect === "random" ? WIN_EFFECTS[Math.floor(Math.random() * WIN_EFFECTS.length)] : display.effect;
      if (EFFECTS[name]) EFFECTS[name](box, display.palette);
      if (entry.tier === "rare" && name !== "sparkle" && name !== "none") EFFECTS.sparkle(box, display.palette, 14);
    } catch (error) {
      console.warn("debutkit 뽑기판 효과", error);
    }
  }

  // ---------------------------------------------------------------- 결과 카드
  function amountText(entry) {
    const count = Number(entry.amount || 0).toLocaleString("ko-KR");
    if (entry.unit === "원") return `${count}원`;
    if (entry.unit === "별풍선" || entry.unit === "애드벌룬") return `${entry.unit} ${count}개`;
    return `${count} ${entry.unit || ""}`.trim();
  }

  function nameSize(text) {
    const units = textUnits(text);
    return units <= 4 ? 128 : units <= 6 ? 112 : units <= 9 ? 92 : units <= 13 ? 72 : 58;
  }

  function showResult(entry, display) {
    const card = el("div", `pk-result t-${entry.tier}`);
    const band = el("div", "pk-rband");
    band.append(el("span", "pk-rnum", `${entry.cell}번`), el("span", "pk-rtier", TIER[entry.tier] || TIER.win));
    const name = el("div", "pk-rname", entry.prize);
    name.style.setProperty("--rname-size", `${Math.round(nameSize(entry.prize) * (display.styles.result.size / 100))}px`);
    card.append(band, name);
    if (entry.by) {
      const by = el("div", "pk-rby");
      by.appendChild(el("span", "", `${entry.by} 님`));
      const platform = PLATFORMS[entry.platform];
      if (platform && entry.platform !== "demo") {
        const chip = el("span", "platform", platform.label);
        chip.style.setProperty("--platform", platform.color);
        by.appendChild(chip);
      }
      if (entry.source === "donation") by.appendChild(el("span", "", amountText(entry)));
      card.appendChild(by);
    }
    resultLayer.replaceChildren(card);
    return card;
  }

  // ---------------------------------------------------------------- 차례로 연출
  let state = null;
  const pending = [];
  let busy = false;
  let epoch = 0;

  const coveredCells = (extra) => {
    const found = new Set(pending.filter((item) => !item.replay).map((item) => item.entry.cell));
    if (extra) found.add(extra);
    return found;
  };

  async function playOne(item) {
    const mine = epoch;
    const { entry, snapshot } = item;
    const display = snapshot.display;
    soundOn = Boolean(display.sound) && !muted;
    volume = Math.max(0, Math.min(1, display.volume / 100));
    if (!snapshot.visible) {
      render(snapshot, coveredCells());
      return;
    }
    if (!item.replay) {
      render(snapshot, coveredCells(entry.cell));
      const node = boardEl.querySelector(`.pk-cell[data-n="${entry.cell}"]`);
      if (node) {
        fillPrize(node.querySelector(".pk-prize"), entry, entry.cell, display);
        boardEl.classList.add("focusing");
        node.classList.add("focus");
        await wait(320);
        if (mine !== epoch) return;
        node.classList.add("opening");
        sound(OPEN_SOUND[display.theme]);
        await wait(OPEN_MS[display.theme] || 900);
        if (mine !== epoch) return;
        node.classList.remove("opening");
        node.classList.add("open");
        const bottom = root.querySelector(".pk-foot");  // 남은 상품, 열린 칸 수는 공개와 함께 바꿈
        if (bottom) bottom.replaceWith(foot(snapshot, coveredCells()));
      }
    }
    const card = showResult(entry, display);
    await wait(40);
    runEffect(entry, display, card);
    if (entry.tier === "miss") sound(display.miss_sound);
    else {
      sound(display.win_sound);
      if (entry.tier === "rare") sound("shimmer");
    }
    root.setAttribute("aria-label", entry.script || `${entry.cell}번 ${entry.prize}`);
    const waiting = pending.length;
    await wait(waiting ? Math.min(2600, display.seconds * 1000) : display.seconds * 1000);  // 기다리는 칸이 있으면 짧게
    if (mine !== epoch) return;
    card.classList.add("leave");
    await wait(330);
    if (mine !== epoch) return;
    resultLayer.replaceChildren();
    render(item.replay ? state : snapshot, coveredCells());
  }

  async function drain() {
    if (busy) return;
    busy = true;
    while (pending.length) {  // 후원 추첨 등 가운데 연출과는 무대 차례(live.js의 cue)로 번갈아
      const release = window.debutkitLive ? await window.debutkitLive.cue("pick") : () => {};
      try {
        await playOne(pending.shift());
      } catch (error) {
        console.warn("debutkit 뽑기판 연출", error);
        resultLayer.replaceChildren();
      } finally {
        release();
      }
    }
    busy = false;
    if (state) render(state, coveredCells());
  }

  function abort() {  // 되돌리기, 섞기, 초기화, 판 바꾸기: 진행 중인 연출을 멈추고 지금 상태로
    epoch += 1;
    pending.length = 0;
    resultLayer.replaceChildren();
    fxLayer.replaceChildren();
  }

  let first = true;
  async function accept(data) {
    await fontsReady;
    const event = data.event || {};
    if (first) {  // 연결할 때(다시 연결 포함) 받는 첫 값은 지금 상태: 연출 없이 그림
      first = false;
      abort();
      state = data;
      render(state, new Set(), true);
      return;
    }
    if (event.type === "replay") {
      pending.push({ entry: event.entry, snapshot: state || data, replay: true });
      drain();
      return;
    }
    state = data;
    if (event.type === "open" && event.entry) {
      pending.push({ entry: event.entry, snapshot: data });
      drain();
      return;
    }
    if (["undo", "reshuffle", "reset", "board"].includes(event.type)) {
      abort();
      render(state, new Set(), event.type !== "undo");
      return;
    }
    if (!busy) render(state, coveredCells());
  }

  let chain = Promise.resolve();  // 받은 순서대로 처리(글꼴 기다림 포함)
  if (params.has("sample")) {
    // 그림 견본(?sample&theme=ticket&cover=stars): 지금 판의 색과 글꼴로 디자인과 덮개 무늬만 바꿔 12칸을 그린다
    // (3번은 당첨, 8번은 꽝으로 열린 모습. 이 화면에서만, 실제 판의 상품은 쓰지 않음)
    fontsReady.then(() => fetch("/pick/state", { cache: "no-store" })).then((response) => response.json()).then((snapshot) => {
      const display = { ...snapshot.display, columns: 0, show_remaining: false };
      if (OPEN_MS[params.get("theme")]) display.theme = params.get("theme");
      if (/^[a-z]{1,20}$/.test(params.get("cover") || "")) display.cover = params.get("cover");
      const cells = Array.from({ length: 12 }, (_, index) => ({ n: index + 1, open: false }));
      cells[2] = { n: 3, open: true, prize: "노래 한 곡", tier: "win" };
      cells[7] = { n: 8, open: true, prize: "꽝", tier: "miss" };
      first = false;
      state = { ...snapshot, display, visible: true, finished: false, opened: 2, total: 12, cells, event: null };
      render(state, new Set(), false);
    }).catch((error) => console.warn("debutkit 뽑기판 그림 견본", error));
  } else {
    // 공유 연결(live.js): 연결(다시 연결 포함) 직후의 값(initial)은 지금 상태라 연출 없이 그린다
    window.debutkitLive.subscribe(["pick", "theme"], (feed, data, initial) => {
      if (feed === "theme" && !initial && !busy) location.reload();  // 방송 색을 쓰는 판의 색은 서버가 정해서 새로 불러옴
      if (feed !== "pick" || !data || !data.display) return;
      if (initial) first = true;
      chain = chain.then(() => accept(data)).catch((error) => console.warn("debutkit 뽑기판", error));
    });
  }
  window.debutkitPick.overlay = { render, grid, fitSize, get state() { return state; }, pending };  // 시험용
})();
