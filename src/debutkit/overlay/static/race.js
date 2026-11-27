// debutkit 참여 레이스 화면(OBS 브라우저 소스, 1920x1080, 투명 배경). /live?feeds=race 로 서버가 정한 계획을 받아 그린다.
// 계획: 게임, 시드, 조별 이름과 도착 순서, 도착 시각(서바이벌은 탈락 시각), 시작 시각, 재생 속도, 연출 설정.
// 장면은 (시드, 순위, 경과 시간)만으로 정해진다: 같은 계획이면 방송 화면과 미리보기가 같은 장면, 중간에 연 화면은 지금 장면부터.
// 깜짝 요소(바람, 번개, 넘어짐 등)는 시드로 정한 연출이며 도착 순서는 바꾸지 않는다. 그림은 모두 캔버스 도형(외부 이미지 없음).
// 이름은 캔버스 fillText와 textContent로만 넣는다. 효과음은 브라우저에서 합성(음원 파일 없음).
// 주소: ?preview=1 조작 화면 미리보기(연습 경기 표시, 효과음은 '조작 화면에서 듣기'를 켠 경우만), ?practice=1 연습 경기도 표시, ?mute 소리 끔
//      ?sample=marble|run|survival 예시 장면(이 화면에서만): &t=12(경주 초에 멈춤, t=end 끝 장면, 음수는 출발 전) &n=24 &heat=0
//      &still(그림 견본: 멈춘 장면을 그린 뒤 그리기 멈춤)
//      &course= &design= &color= &font= &format= &surprise= &rank= &seed=
"use strict";

(() => {
  const W = 1920;
  const H = 1080;
  const TAU = Math.PI * 2;
  const params = new URLSearchParams(location.search);
  const preview = params.has("preview");
  const sampleGame = params.get("sample");
  const showPractice = preview || params.has("practice") || Boolean(sampleGame);
  const stage = document.getElementById("stage");
  const canvas = document.getElementById("race-canvas");
  const ctx = canvas.getContext("2d");
  const heatCard = document.getElementById("race-heat");
  const winCard = document.getElementById("race-win");
  const UI = '"Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif';
  const DISPLAY = '"Black Han Sans", "Malgun Gothic", sans-serif';
  const INK = "#1e2327";
  //: 줄을 나눠 겨루는 게임(달리기, 수영): 조별 경기와 같은 그리기
  const LANE_GAMES = ["run", "swim"];

  // ---------------------------------------------------------------- 화면 맞춤(OBS 1920x1080은 그대로, 미리보기 창은 비율 유지 축소)
  function fit() {
    const scale = Math.min(innerWidth / W, innerHeight / H) || 1;
    stage.style.transform = `translate(${(innerWidth - W * scale) / 2}px, ${(innerHeight - H * scale) / 2}px) scale(${scale})`;
  }
  addEventListener("resize", fit);
  fit();

  // ---------------------------------------------------------------- 수학, 난수(시드 고정)
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const lerp = (a, b, u) => a + (b - a) * u;
  const smooth = (u) => {
    const v = clamp(u, 0, 1);
    return v * v * (3 - 2 * v);
  };
  const easeOut = (u) => 1 - Math.pow(1 - clamp(u, 0, 1), 3);
  const easeIn = (u) => Math.pow(clamp(u, 0, 1), 2);
  const window01 = (t, start, length, edge = 0.18) => {  // 시작과 끝을 부드럽게 한 0..1..0 구간
    if (t < start || t > start + length) return 0;
    const u = (t - start) / length;
    return smooth(u / edge) * smooth((1 - u) / edge);
  };
  function mulberry32(seed) {
    let a = seed >>> 0;
    return () => {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function hashOf(...parts) {
    let h = 2166136261;
    for (const part of parts) {
      const text = String(part);
      for (let i = 0; i < text.length; i++) {
        h ^= text.charCodeAt(i);
        h = Math.imul(h, 16777619);
      }
      h ^= 124;
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }
  const between = (rng, low, high) => low + (high - low) * rng();
  const pickOne = (rng, list) => list[Math.floor(rng() * list.length) % list.length];

  // ---------------------------------------------------------------- 색: 기본 색 하나에서 재질별 색표를 만든다
  function hexRgb(hex) {
    const value = parseInt(String(hex).replace("#", ""), 16) || 0;
    return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
  }
  function rgbHsl([r, g, b]) {
    r /= 255;
    g /= 255;
    b /= 255;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const l = (max + min) / 2;
    if (max === min) return [0, 0, l];
    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    const h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return [h * 60, s, l];
  }
  function hslRgb(h, s, l) {
    const hue = (((h % 360) + 360) % 360) / 360;
    s = clamp(s, 0, 1);
    l = clamp(l, 0, 1);
    if (s === 0) return [l * 255, l * 255, l * 255];
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    const f = (t) => {
      t = (t + 1) % 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };
    return [f(hue + 1 / 3) * 255, f(hue) * 255, f(hue - 1 / 3) * 255];
  }
  const hsl = (h, s, l, a = 1) => `hsla(${(((h % 360) + 360) % 360).toFixed(1)}, ${(clamp(s, 0, 1) * 100).toFixed(1)}%, ${(clamp(l, 0, 1) * 100).toFixed(1)}%, ${a})`;
  const luminance = ([r, g, b]) => (0.299 * r + 0.587 * g + 0.114 * b) / 255;

  function makePalette(design, hex) {
    const [h, s, l] = rgbHsl(hexRgb(hex));
    const base = {
      design, hue: h, sat: s, light: l, accent: hex, ink: INK, gold: "#ffd84d", silver: "#cfd6dc", bronze: "#d99a5e",
      accentDark: hsl(h, s, l * 0.62), accentLight: hsl(h, s * 0.85, l + (1 - l) * 0.6), accentSoft: hsl(h, s * 0.55, l + (1 - l) * 0.84),
      onAccent: luminance(hexRgb(hex)) > 0.62 ? INK : "#ffffff", glow: hsl(h, Math.max(s, 0.6), Math.max(l, 0.55), 0.85),
    };
    if (design === "metal") {
      return {
        ...base, bg: "#1d2227", bgHi: "#2c333a", plate: "#22282e", plateLine: "rgba(255, 255, 255, 0.035)", frame: "#8f9aa5",
        track: "rgba(160, 200, 230, 0.12)", wall: hsl(h, Math.max(s, 0.55), Math.max(l, 0.55)), wallLo: hsl(h, s, l * 0.45),
        peg: "#e9eef2", pegLo: "#5d6872", text: "#eef2f5", sub: "#9eabb6", panel: "#22282e", line: "rgba(255, 255, 255, 0.75)",
        shadow: "rgba(0, 0, 0, 0.55)", laneA: "#262c33", laneB: "#2b323a", veil: "rgba(10, 12, 15, 0.55)",
      };
    }
    if (design === "paper") {
      return {
        ...base, bg: hsl(h, s * 0.4, 0.9), bgHi: hsl(h, s * 0.35, 0.94), plate: "#fffdf8", plateLine: hsl(h, s * 0.3, 0.82), frame: INK,
        track: "#fffdf8", wall: hsl(h, s * 0.9, clamp(l + 0.06, 0.45, 0.66)), wallLo: INK,
        peg: "#fffdf8", pegLo: INK, text: INK, sub: "#5b6670", panel: "#fffdf8", line: INK,
        shadow: "rgba(30, 35, 39, 0.85)", laneA: "#fffdf8", laneB: hsl(h, s * 0.4, 0.93), veil: "rgba(255, 253, 248, 0.55)",
      };
    }
    return {
      ...base, bg: "#e7c08a", bgHi: "#f0d3a5", plate: "#f1d9b1", plateLine: "rgba(122, 74, 34, 0.15)", frame: "#7a4b2a",
      track: "#f8e9cd", wall: hsl(h, s * 0.8, Math.min(0.56, l)), wallLo: hsl(h, s * 0.8, Math.min(0.56, l) * 0.6),
      peg: "#f8eedc", pegLo: "#8a5a33", text: "#2d1f14", sub: "#6b5240", panel: "#f7ecd9", line: "rgba(255, 252, 245, 0.92)",
      shadow: "rgba(70, 38, 14, 0.38)", laneA: "#e6bf88", laneB: "#dcb27a", veil: "rgba(60, 35, 15, 0.45)",
    };
  }

  // 참가자 색: 기본 색에서 150도씩 돌린 12색, 13번째부터는 어둡게, 밝게
  function runnerColors(P, n) {
    const sat = P.design === "metal" ? 0.78 : P.design === "paper" ? 0.66 : 0.62;
    const light = P.design === "metal" ? 0.56 : P.design === "paper" ? 0.62 : 0.55;
    const list = [];
    for (let i = 0; i < n; i++) {
      const hue = (P.hue + (i % 12) * 150) % 360;
      const l = clamp(light + [0, -0.16, 0.14][Math.floor(i / 12) % 3], 0.25, 0.82);
      const rgb = hslRgb(hue, sat, l);
      list.push({ fill: hsl(hue, sat, l), dark: hsl(hue, sat, l * 0.58), light: hsl(hue, sat * 0.8, l + (1 - l) * 0.55),
                  text: luminance(rgb) > 0.6 ? INK : "#ffffff", hue });
    }
    return list;
  }

  // ---------------------------------------------------------------- 그리기 도구
  function roundRect(g, x, y, w, h, r) {
    const rr = Math.max(0, Math.min(r, w / 2, h / 2));
    g.beginPath();
    g.moveTo(x + rr, y);
    g.arcTo(x + w, y, x + w, y + h, rr);
    g.arcTo(x + w, y + h, x, y + h, rr);
    g.arcTo(x, y + h, x, y, rr);
    g.arcTo(x, y, x + w, y, rr);
    g.closePath();
  }
  const fitCache = new Map();
  function fitText(g, text, max) {
    const key = `${g.font}|${max}|${text}`;
    let value = fitCache.get(key);
    if (value !== undefined) return value;
    value = text;
    if (g.measureText(text).width > max) {
      const chars = Array.from(text);
      let low = 0;
      let high = chars.length;
      while (low < high) {
        const mid = (low + high + 1) >> 1;
        if (g.measureText(chars.slice(0, mid).join("") + "...").width <= max) low = mid;
        else high = mid - 1;
      }
      value = chars.slice(0, low).join("") + "...";
    }
    if (fitCache.size > 5000) fitCache.clear();
    fitCache.set(key, value);
    return value;
  }
  function outlined(g, text, x, y, fill, stroke, width) {
    g.lineJoin = "round";
    g.lineWidth = width;
    g.strokeStyle = stroke;
    g.strokeText(text, x, y);
    g.fillStyle = fill;
    g.fillText(text, x, y);
  }
  const glyphOf = (name) => (Array.from(String(name).replace(/^[\s_\-.#]+/, ""))[0] || "?").toUpperCase();
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function star(g, x, y, r, points = 5, inner = 0.45) {
    g.beginPath();
    for (let k = 0; k < points * 2; k++) {
      const radius = k % 2 ? r * inner : r;
      const angle = -Math.PI / 2 + (k * Math.PI) / points;
      g.lineTo(x + Math.cos(angle) * radius, y + Math.sin(angle) * radius);
    }
    g.closePath();
  }

  // 재질 무늬(나무결, 금속 결, 종이 섬유)
  function grain(g, x, y, w, h, P, seed) {
    const rng = mulberry32(seed);
    g.save();
    g.beginPath();
    g.rect(x, y, w, h);
    g.clip();
    if (P.design === "wood") {
      g.strokeStyle = P.plateLine;
      g.lineWidth = 1.4;
      for (let yy = y + 5; yy < y + h; yy += 8 + rng() * 9) {
        const amp = 1.2 + rng() * 3;
        const freq = 0.003 + rng() * 0.009;
        const phase = rng() * TAU;
        g.beginPath();
        for (let xx = x; xx <= x + w + 24; xx += 24) g.lineTo(xx, yy + Math.sin(xx * freq + phase) * amp);
        g.stroke();
      }
      for (let k = 0; k < Math.floor((w * h) / 260000); k++) {
        const kx = x + rng() * w;
        const ky = y + rng() * h;
        g.beginPath();
        g.ellipse(kx, ky, 12 + rng() * 10, 3.5 + rng() * 3, 0, 0, TAU);
        g.stroke();
        g.beginPath();
        g.ellipse(kx, ky, 20 + rng() * 10, 6 + rng() * 3, 0, 0, TAU);
        g.stroke();
      }
    } else if (P.design === "metal") {
      g.fillStyle = P.plateLine;
      for (let yy = y; yy < y + h; yy += 2) if (rng() < 0.45) g.fillRect(x, yy, w, 1);
    } else {
      g.fillStyle = "rgba(30, 35, 39, 0.05)";
      for (let k = 0; k < (w * h) / 650; k++) g.fillRect(x + rng() * w, y + rng() * h, 1.6, 1.6);
    }
    g.restore();
  }
  function screw(g, x, y, r, P) {
    g.save();
    if (P.design === "metal") {
      const shade = g.createRadialGradient(x - r * 0.3, y - r * 0.3, 0.5, x, y, r);
      shade.addColorStop(0, "#f2f5f7");
      shade.addColorStop(1, "#6d7882");
      g.fillStyle = shade;
    } else {
      g.fillStyle = "#c9a56f";
    }
    g.beginPath();
    g.arc(x, y, r, 0, TAU);
    g.fill();
    g.strokeStyle = P.design === "metal" ? "rgba(0, 0, 0, 0.45)" : "#5a3a20";
    g.lineWidth = 1.2;
    g.stroke();
    g.beginPath();
    g.moveTo(x - r * 0.6, y - r * 0.2);
    g.lineTo(x + r * 0.6, y + r * 0.2);
    g.stroke();
    g.restore();
  }
  function tape(g, P, x, y, angle) {
    g.save();
    g.translate(x, y);
    g.rotate(angle);
    g.globalAlpha = 0.82;
    g.fillStyle = P.accentLight;
    g.fillRect(-58, -15, 116, 30);
    g.globalAlpha = 0.25;
    g.fillStyle = "#ffffff";
    for (let k = -54; k < 58; k += 9) g.fillRect(k, -15, 3, 30);
    g.restore();
  }

  // 패널: 나무(테두리와 나사), 금속(경사 테두리와 빛나는 선), 종이(잉크 외곽선, 딱딱한 그림자, 테이프)
  function panel(g, P, x, y, w, h, options = {}) {
    const seed = options.seed || 7;
    g.save();
    if (P.design === "wood") {
      const r = options.radius ?? 18;
      const inset = options.inset ?? 12;
      g.fillStyle = P.shadow;
      roundRect(g, x + 5, y + 7, w, h, r);
      g.fill();
      const rim = g.createLinearGradient(x, y, x, y + h);
      rim.addColorStop(0, "#a8703f");
      rim.addColorStop(1, P.frame);
      g.fillStyle = rim;
      roundRect(g, x, y, w, h, r);
      g.fill();
      g.strokeStyle = "#4f2f18";
      g.lineWidth = 2;
      g.stroke();
      grain(g, x, y, w, h, { ...P, plateLine: "rgba(40, 20, 6, 0.22)" }, seed + 1);
      const ir = Math.max(4, r - inset + 4);
      g.fillStyle = options.fill || P.panel;
      roundRect(g, x + inset, y + inset, w - inset * 2, h - inset * 2, ir);
      g.fill();
      grain(g, x + inset, y + inset, w - inset * 2, h - inset * 2, P, seed);
      g.strokeStyle = "rgba(60, 30, 10, 0.4)";
      g.lineWidth = 2;
      roundRect(g, x + inset, y + inset, w - inset * 2, h - inset * 2, ir);
      g.stroke();
      if (options.screws) {
        const m = inset / 2 + 1;
        for (const [sx, sy] of [[x + m + 3, y + m + 3], [x + w - m - 3, y + m + 3], [x + m + 3, y + h - m - 3], [x + w - m - 3, y + h - m - 3]]) screw(g, sx, sy, 4.5, P);
      }
    } else if (P.design === "metal") {
      const r = options.radius ?? 14;
      const inset = options.inset ?? 8;
      g.shadowColor = "rgba(0, 0, 0, 0.5)";
      g.shadowBlur = 18;
      g.shadowOffsetY = 6;
      const rim = g.createLinearGradient(x, y, x, y + h);
      rim.addColorStop(0, "#aab4bd");
      rim.addColorStop(0.45, "#5d6770");
      rim.addColorStop(1, "#353c43");
      g.fillStyle = rim;
      roundRect(g, x, y, w, h, r);
      g.fill();
      g.shadowColor = "transparent";
      const ir = Math.max(3, r - inset);
      const face = g.createLinearGradient(x, y, x, y + h);
      face.addColorStop(0, options.fill || P.bgHi);
      face.addColorStop(1, options.fill || P.bg);
      g.fillStyle = face;
      roundRect(g, x + inset, y + inset, w - inset * 2, h - inset * 2, ir);
      g.fill();
      grain(g, x + inset, y + inset, w - inset * 2, h - inset * 2, P, seed);
      g.strokeStyle = "rgba(255, 255, 255, 0.16)";
      g.lineWidth = 1.5;
      roundRect(g, x + inset, y + inset, w - inset * 2, h - inset * 2, ir);
      g.stroke();
      if (!options.plain) {
        g.strokeStyle = P.glow;
        g.globalAlpha = 0.5;
        g.lineWidth = 2;
        g.shadowColor = P.glow;
        g.shadowBlur = 12;
        roundRect(g, x + inset + 4, y + inset + 4, w - inset * 2 - 8, h - inset * 2 - 8, Math.max(2, ir - 3));
        g.stroke();
        g.shadowColor = "transparent";
        g.globalAlpha = 1;
      }
      if (options.screws) {
        const m = inset / 2 + 1;
        for (const [sx, sy] of [[x + m + 2, y + m + 2], [x + w - m - 2, y + m + 2], [x + m + 2, y + h - m - 2], [x + w - m - 2, y + h - m - 2]]) screw(g, sx, sy, 3.2, P);
      }
    } else {
      const r = options.radius ?? 5;
      g.fillStyle = P.shadow;
      roundRect(g, x + 8, y + 8, w, h, r);
      g.fill();
      g.fillStyle = options.fill || P.plate;
      roundRect(g, x, y, w, h, r);
      g.fill();
      grain(g, x, y, w, h, P, seed);
      g.strokeStyle = INK;
      g.lineWidth = 3;
      roundRect(g, x, y, w, h, r);
      g.stroke();
      if (options.tape) {
        tape(g, P, x + 70, y + 2, -0.08);
        tape(g, P, x + w - 70, y + 2, 0.07);
      }
    }
    g.restore();
  }
  function pill(g, P, x, y, w, h, fill, text, color, font) {
    g.save();
    if (P.design === "paper") {
      g.fillStyle = INK;
      g.fillRect(x + 4, y + 4, w, h);
      g.fillStyle = fill;
      g.fillRect(x, y, w, h);
      g.strokeStyle = INK;
      g.lineWidth = 3;
      g.strokeRect(x, y, w, h);
    } else {
      g.fillStyle = fill;
      roundRect(g, x, y, w, h, P.design === "metal" ? h / 2 : 10);
      if (P.design === "metal") {
        g.shadowColor = fill;
        g.shadowBlur = 16;
      }
      g.fill();
      g.shadowColor = "transparent";
      if (P.design === "wood") {
        g.fillStyle = "rgba(0, 0, 0, 0.16)";
        roundRect(g, x, y + h - 6, w, 6, 4);
        g.fill();
      }
    }
    g.fillStyle = color;
    g.font = font;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillText(text, x + w / 2, y + h / 2 + 2);
    g.restore();
  }

  // ---------------------------------------------------------------- 효과음(브라우저에서 합성)
  const sound = { on: false, volume: 0.7, audio: null, master: null, lastTick: 0 };
  function audio() {
    if (!sound.audio) {
      sound.audio = new (window.AudioContext || window.webkitAudioContext)();
      sound.master = sound.audio.createGain();
      sound.master.connect(sound.audio.destination);
    }
    if (sound.audio.state === "suspended") sound.audio.resume().catch(() => {});
    sound.master.gain.value = sound.volume;
    return sound.audio;
  }
  function play(kind) {
    if (!sound.on || sound.volume <= 0) return;
    try {
      const a = audio();
      const now = a.currentTime;
      const note = (type, frequency, start, length, peak, slide) => {
        const oscillator = a.createOscillator();
        const gain = a.createGain();
        oscillator.type = type;
        oscillator.frequency.setValueAtTime(frequency, now + start);
        if (slide) oscillator.frequency.exponentialRampToValueAtTime(slide, now + start + length);
        gain.gain.setValueAtTime(0.0001, now + start);
        gain.gain.exponentialRampToValueAtTime(peak, now + start + 0.008);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + start + length);
        oscillator.connect(gain).connect(sound.master);
        oscillator.start(now + start);
        oscillator.stop(now + start + length + 0.03);
      };
      const noise = (start, length, peak, frequency) => {
        const buffer = a.createBuffer(1, Math.ceil(a.sampleRate * length), a.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / data.length);
        const node = a.createBufferSource();
        node.buffer = buffer;
        const filter = a.createBiquadFilter();
        filter.type = "lowpass";
        filter.frequency.value = frequency;
        const gain = a.createGain();
        gain.gain.value = peak;
        node.connect(filter).connect(gain).connect(sound.master);
        node.start(now + start);
      };
      if (kind === "count") note("square", 660, 0, 0.12, 0.07);
      else if (kind === "go") {
        note("square", 990, 0, 0.32, 0.06);
        note("triangle", 1320, 0, 0.36, 0.06);
      } else if (kind === "tick") note("triangle", 1700 + Math.random() * 1100, 0, 0.035, 0.03);
      else if (kind === "step") note("sine", 150 + Math.random() * 40, 0, 0.06, 0.05);
      else if (kind === "splash") noise(0, 0.22, 0.12, 1400 + Math.random() * 900);
      else if (kind === "whoosh") noise(0, 0.7, 0.18, 700);
      else if (kind === "zap") {
        noise(0, 0.35, 0.3, 4000);
        note("sawtooth", 140, 0, 0.5, 0.06, 50);
      } else if (kind === "rumble") noise(0, 1.4, 0.35, 160);
      else if (kind === "boost") note("square", 330, 0, 0.3, 0.05, 1100);
      else if (kind === "slow") note("triangle", 700, 0, 0.4, 0.06, 160);
      else if (kind === "pop") {
        note("sine", 480, 0, 0.14, 0.08, 1500);
        noise(0, 0.08, 0.1, 2500);
      } else if (kind === "shine") [1318.5, 1760].forEach((frequency, index) => note("sine", frequency, index * 0.07, 0.35, 0.05));
      else if (kind === "finish") {
        note("triangle", 1046.5, 0, 0.16, 0.07);
        note("triangle", 1568, 0.08, 0.24, 0.06);
      } else if (kind === "heat") {
        note("sine", 784, 0, 0.25, 0.07);
        note("sine", 1046.5, 0.12, 0.4, 0.07);
      } else if (kind === "fanfare") {
        [523.25, 659.25, 783.99, 1046.5].forEach((frequency, index) => note("triangle", frequency, index * 0.12, index === 3 ? 0.9 : 0.16, 0.08));
        note("sine", 1318.5, 0.48, 1.0, 0.05);
      }
    } catch (error) {
      // 소리를 낼 수 없는 환경
    }
  }

  // ---------------------------------------------------------------- 속도 곡선: 도착 시각은 서버가 정한 값 그대로, 중간 순위만 출렁인다
  const DT = 0.05;
  function buildProfiles(n, times, rng) {
    const end = Math.max(...times);
    const steps = Math.ceil(end / DT) + 3;
    const profile = { steps, times, speed: [], cum: [] };
    for (let i = 0; i < n; i++) {
      const v = new Float32Array(steps);
      const waves = [0, 1, 2].map(() => ({ a: between(rng, 0.07, 0.22), f: between(rng, 0.035, 0.3), p: between(rng, 0, TAU) }));
      const ramp = between(rng, 0.5, 1.5);
      for (let k = 0; k < steps; k++) {
        const t = k * DT;
        let value = 1;
        for (const wave of waves) value += wave.a * Math.sin(wave.p + t * wave.f * TAU);
        v[k] = Math.max(0.08, value) * (0.12 + 0.88 * smooth(t / ramp));
      }
      profile.speed.push(v);
      integrate(profile, i);
    }
    return profile;
  }
  function integrate(profile, i) {
    const v = profile.speed[i];
    const cum = new Float32Array(profile.steps);
    let total = 0;
    for (let k = 1; k < profile.steps; k++) {
      total += (v[k - 1] + v[k]) * 0.5 * DT;
      cum[k] = total;
    }
    const at = sample(cum, profile.times[i] / DT) || 1;
    for (let k = 0; k < profile.steps; k++) cum[k] /= at;
    profile.cum[i] = cum;
  }
  function sample(values, x) {
    if (x <= 0) return values[0];
    const k = Math.floor(x);
    if (k >= values.length - 1) return values[values.length - 1];
    return values[k] + (values[k + 1] - values[k]) * (x - k);
  }
  function progressOf(profile, i, t) {
    if (t <= 0) return 0;
    if (t >= profile.times[i]) return 1;
    return Math.min(0.9995, sample(profile.cum[i], t / DT));
  }
  function scaleSpeed(profile, i, start, length, factor) {
    const v = profile.speed[i];
    const first = Math.max(0, Math.floor(start / DT));
    const last = Math.min(profile.steps - 1, Math.ceil((start + length) / DT));
    for (let k = first; k <= last; k++) v[k] *= lerp(1, factor, window01(k * DT, start, length, 0.2));
    integrate(profile, i);
  }
  function orderAt(profile, n, t) {  // 지금 앞선 순서(도착한 참가자는 도착 순서대로 앞)
    const lanes = Array.from({ length: n }, (_, i) => i);
    const p = lanes.map((i) => progressOf(profile, i, t));
    return lanes.sort((a, b) => {
      const fa = t >= profile.times[a];
      const fb = t >= profile.times[b];
      if (fa && fb) return profile.times[a] - profile.times[b];
      if (fa !== fb) return fa ? -1 : 1;
      return p[b] - p[a];
    });
  }

  // ---------------------------------------------------------------- 깜짝 요소 계획(시드로 정함, 도착 순서는 그대로)
  function eventSlots(rng, level, horizon, first = 0.12, span = 0.7) {
    const count = level === "many" ? 7 : level === "some" ? 3 : 0;
    return Array.from({ length: count }, (_, k) => horizon * (first + (span * (k + between(rng, 0.2, 0.8))) / count));
  }
  function marbleEvents(env, profile, n) {
    const kinds = env.events;
    if (!kinds.length) return [];
    const { rng, heat } = env;
    const horizon = Math.min(...profile.times);
    const list = [];
    const nameOf = (lane) => heat.names[lane];
    for (const t of eventSlots(rng, env.level, horizon)) {
      const kind = pickOne(rng, kinds);
      const order = orderAt(profile, n, t).filter((lane) => t < profile.times[lane]);
      if (order.length < 2) continue;
      const event = { kind, t, dur: 2, targets: [], factors: [], text: "", sound: "whoosh", seed: Math.floor(rng() * 1e9) };
      if (kind === "wind") {
        event.dur = 3.2;
        event.dir = rng() < 0.5 ? -1 : 1;
        event.targets = order;
        event.factors = order.map(() => (rng() < 0.5 ? between(rng, 0.55, 0.75) : between(rng, 1.25, 1.45)));
        event.text = "돌풍! 구슬이 흔들립니다";
      } else if (kind === "lightning") {
        event.dur = 1.4;
        event.targets = [order[0]];
        event.factors = [0.03];
        event.text = `번개! 선두 ${nameOf(order[0])} 잠시 멈춤`;
        event.sound = "zap";
      } else if (kind === "quake") {
        event.dur = 1.6;
        event.targets = order.filter(() => rng() < 0.4);
        event.factors = event.targets.map(() => 0.3);
        event.text = "지진! 트랙이 흔들립니다";
        event.sound = "rumble";
      } else if (kind === "comeback") {
        const lane = order[order.length - 1];
        event.dur = 2.4;
        event.targets = [lane];
        event.factors = [2.3];
        event.text = `꼴찌 가속! ${nameOf(lane)} 추격`;
        event.sound = "boost";
      } else if (kind === "check") {
        event.dur = 2.2;
        event.targets = [order[0]];
        event.factors = [0.42];
        event.text = `선두 견제! ${nameOf(order[0])} 감속`;
        event.sound = "slow";
      } else if (kind === "item") {
        const lane = order[Math.floor(between(rng, 0.25, 0.85) * order.length)];
        const good = rng() < 0.6;
        event.dur = 1.9;
        event.targets = [lane];
        event.factors = [good ? 2.1 : 0.4];
        event.good = good;
        event.text = `아이템 상자! ${nameOf(lane)} ${good ? "가속" : "감속"}`;
        event.sound = good ? "boost" : "slow";
      } else if (kind === "gate") {
        const picks = order.filter(() => rng() < 0.5).slice(0, 3);
        if (!picks.length) picks.push(order[Math.floor(order.length / 2)]);
        event.dur = 1.9;
        event.targets = picks;
        event.factors = picks.map(() => (rng() < 0.5 ? 1.9 : 0.5));
        event.text = `운명의 문! ${picks.length}개 구슬의 속도가 바뀝니다`;
        event.sound = "shine";
      } else if (kind === "switch") {
        event.dur = 2.3;
        event.targets = order.filter(() => rng() < 0.22);
        if (!event.targets.length) event.targets = [order[order.length - 1]];
        event.factors = event.targets.map(() => 0.55);
        event.text = `갈림길 전환! ${event.targets.length}개 구슬이 돌아갑니다`;
      }
      event.targets.forEach((lane, index) => scaleSpeed(profile, lane, t, event.dur, event.factors[index]));
      list.push(event);
    }
    return list;
  }
  function runEvents(env, profile, n) {
    const kinds = env.events;
    if (!kinds.length) return [];
    const { rng, heat } = env;
    const swim = env.race.game === "swim";
    const count = env.level === "many" ? 4 : env.level === "some" ? 2 : 0;
    const horizon = Math.min(...profile.times);
    const used = new Set();
    const list = [];
    for (let k = 0; k < count; k++) {
      const kind = pickOne(rng, kinds);
      let lane = Math.floor(rng() * n);
      for (let tries = 0; tries < n && used.has(lane); tries++) lane = (lane + 1) % n;
      used.add(lane);
      const name = heat.names[lane];
      let t = horizon * (0.18 + (0.6 * (k + between(rng, 0.15, 0.85))) / count);
      const event = { kind, t, dur: 1.5, targets: [lane], factors: [1], text: "", sound: "whoosh", seed: Math.floor(rng() * 1e9) };
      if (kind === "sprint") {
        event.factors = [1.85];
        event.text = swim ? `${name} 스퍼트!` : `${name} 질주!`;
        event.sound = "boost";
      } else if (kind === "stumble") {
        event.dur = 1.15;
        event.factors = [0.05];
        event.text = `${name} 넘어짐!`;
        event.sound = "slow";
      } else if (kind === "cramp") {
        event.dur = 2.0;
        event.factors = [0.45];
        event.text = `${name} 다리에 쥐!`;
        event.sound = "slow";
      } else if (kind === "wave") {
        event.dur = 1.6;
        event.factors = [0.4];
        event.text = `${name} 물살에 밀림!`;
        event.sound = "splash";
      } else if (kind === "dive" && swim) {  // 잠영 대시: 물속으로 빠르게
        event.dur = 1.0;
        event.factors = [1.7];
        event.text = `${name} 잠영 대시!`;
        event.sound = "boost";
      } else if (kind === "dive") {
        t = Math.max(0.5, profile.times[lane] - 0.75);
        event.t = t;
        event.dur = 0.75;
        event.factors = [1.6];
        event.text = `${name} 막판 다이빙!`;
        event.sound = "boost";
      }
      scaleSpeed(profile, lane, event.t, event.dur, event.factors[0]);
      list.push(event);
    }
    return list.sort((a, b) => a.t - b.t);
  }

  // ---------------------------------------------------------------- 구슬 레이스: 코스(레일, 굽은 길, 핀 숲, 계단, 낙하)
  function rail(x0, y0, x1, y1) {
    const dx = x1 - x0;
    const dy = y1 - y0;
    const len = Math.hypot(dx, dy);
    const nx = -dy / len;
    const ny = dx / len;
    const angle = Math.atan2(dy, dx);
    return { kind: "rail", len, x0, y0, x1, y1, at: (u, off) => [x0 + dx * u + nx * off, y0 + dy * u + ny * off, angle, nx, ny] };
  }
  function bend(cx, cy, r, a0, a1) {
    const len = Math.abs(a1 - a0) * r;
    const dir = Math.sign(a1 - a0);
    return { kind: "bend", len, cx, cy, r, a0, a1, at: (u, off) => {
      const angle = a0 + (a1 - a0) * u;
      const rr = r + off * dir;
      return [cx + Math.cos(angle) * rr, cy + Math.sin(angle) * rr, angle + dir * Math.PI / 2, Math.cos(angle) * dir, Math.sin(angle) * dir];
    } };
  }
  const pegWidth = (u) => (u < 0.16 ? lerp(58, 540, smooth(u / 0.16)) : u > 0.84 ? lerp(540, 52, smooth((u - 0.84) / 0.16)) : 540);
  function pegField(cx, y0, y1, rows) {
    return { kind: "pegs", len: 1150, cx, y0, y1, rows, width: pegWidth, at: (u, off) => [cx + off, y0 + (y1 - y0) * u, Math.PI / 2, 1, 0] };
  }
  function steps(x0, y0, x1, y1, count) {
    const stepW = (x1 - x0) / count;
    const stepH = (y1 - y0) / count;
    const len = Math.abs(x1 - x0) + Math.abs(y1 - y0) * 1.5;
    return { kind: "steps", len, x0, y0, x1, y1, count, stepW, stepH, at: (u) => {
      const s = clamp(u, 0, 0.99999) * count;
      const k = Math.floor(s);
      const f = s - k;
      const fall = f > 0.62 ? easeIn((f - 0.62) / 0.38) : 0;
      return [x0 + stepW * (k + f), y0 + stepH * (k + fall), stepW > 0 ? 0 : Math.PI, 0, 1];
    } };
  }
  function drop(x0, y0, x1, y1) {
    return { kind: "drop", len: 170, x0, y0, x1, y1, at: (u) => [lerp(x0, x1, u) + Math.sin(Math.PI * u) * 22, lerp(y0, y1, easeIn(u)), Math.PI / 2, 1, 0] };
  }

  function makeCourse(kind) {
    const segs = [];
    let hopper;
    const H0 = { y: 128, w: 404, h: 124 };
    if (kind === "pegs") {
      hopper = { x: 529, ...H0, exit: [731, 278] };
      segs.push({ kind: "hopper", len: 150, end: [731, 292] });
      segs.push(pegField(731, 292, 650, 11));
      segs.push(rail(731, 672, 1320, 722));
      segs.push(bend(1320, 792, 70, -Math.PI / 2, Math.PI / 2));
      segs.push(rail(1320, 862, 250, 912));
    } else if (kind === "mix") {  // 계단, 레일, 굽은 길, 핀 숲을 차례로
      hopper = { x: 62, ...H0, exit: [244, 278] };
      segs.push({ kind: "hopper", len: 150, end: [244, 300] });
      segs.push(steps(244, 300, 860, 470, 7));
      segs.push(rail(860, 470, 1320, 520));
      segs.push(bend(1320, 590, 70, -Math.PI / 2, Math.PI / 2));
      segs.push(rail(1320, 660, 820, 690));
      segs.push(pegField(820, 690, 862, 4));
      segs.push(rail(820, 862, 250, 918));
    } else if (kind === "stairs") {
      hopper = { x: 62, ...H0, exit: [244, 278] };
      segs.push({ kind: "hopper", len: 150, end: [244, 302] });
      segs.push(steps(244, 302, 1320, 562, 11));
      segs.push(drop(1320, 562, 1320, 652));
      segs.push(steps(1320, 652, 250, 912, 11));
    } else {
      hopper = { x: 62, ...H0, exit: [244, 278] };
      segs.push({ kind: "hopper", len: 150, end: [244, 300] });
      segs.push(rail(244, 300, 1320, 350));
      segs.push(bend(1320, 420, 70, -Math.PI / 2, Math.PI / 2));
      segs.push(rail(1320, 490, 200, 540));
      segs.push(bend(200, 610, 70, -Math.PI / 2, -Math.PI * 1.5));
      segs.push(rail(200, 680, 1320, 730));
      segs.push(bend(1320, 800, 70, -Math.PI / 2, Math.PI / 2));
      segs.push(rail(1320, 870, 250, 920));
    }
    const starts = [];
    let total = 0;
    for (const seg of segs) {
      starts.push(total);
      total += seg.len;
    }
    const last = segs[segs.length - 1];
    const [fx, fy] = last.at(1, 0);
    // 장식 위치(켜진 깜짝 요소만 표시)
    const anchors = kind === "pegs"
      ? { cloud: [1110, 215], vane: [1330, 200], items: [[1372, 330], [1372, 420], [1372, 510]], gate: [560, 900], lever: [1395, 792] }
      : kind === "stairs"
        ? { cloud: [1100, 225], vane: [1330, 200], items: [[560, 250], [780, 300], [1000, 350]], gate: [790, 795], lever: [1395, 607] }
        : kind === "mix"
          ? { cloud: [1100, 215], vane: [1330, 200], items: [[950, 480], [1100, 496], [1250, 512]], gate: [520, 889], lever: [1395, 590] }
        : { cloud: [1100, 215], vane: [1330, 200], items: [[520, 402], [760, 420], [1000, 438]], gate: [760, 705], lever: [125, 610] };
    return { kind, segs, starts, total, hopper, finish: [fx, fy], anchors };
  }

  function chutePath(segs) {
    const path = new Path2D();
    let started = false;
    for (const seg of segs) {
      if (seg.kind === "rail") {
        if (!started) path.moveTo(seg.x0, seg.y0);
        path.lineTo(seg.x1, seg.y1);
        started = true;
      } else if (seg.kind === "bend") {
        path.arc(seg.cx, seg.cy, seg.r, seg.a0, seg.a1, seg.a1 < seg.a0);
      }
    }
    return path;
  }
  function strokePath(g, path, width, style, cap = "round") {
    g.lineWidth = width;
    g.strokeStyle = style;
    g.lineCap = cap;
    g.lineJoin = "round";
    g.stroke(path);
  }
  function drawChute(g, P, path, hw) {
    g.save();
    if (P.design === "wood") {
      g.save();
      g.translate(5, 7);
      strokePath(g, path, hw * 2 + 20, P.shadow);
      g.restore();
      strokePath(g, path, hw * 2 + 18, P.wallLo);
      strokePath(g, path, hw * 2 + 12, P.wall);
      strokePath(g, path, hw * 2, P.track);
      strokePath(g, path, hw * 2 - 6, "rgba(122, 74, 34, 0.08)");
      g.setLineDash([2, 46]);
      strokePath(g, path, hw * 2 + 12, "rgba(40, 20, 6, 0.28)", "butt");
      g.setLineDash([]);
    } else if (P.design === "metal") {
      g.save();
      g.translate(0, 8);
      strokePath(g, path, hw * 2 + 14, "rgba(0, 0, 0, 0.4)");
      g.restore();
      strokePath(g, path, hw * 2 + 14, "rgba(225, 240, 255, 0.55)");
      strokePath(g, path, hw * 2 + 9, "rgba(24, 30, 36, 0.92)");
      strokePath(g, path, hw * 2 + 9, P.track);
      g.save();
      g.shadowColor = P.glow;
      g.shadowBlur = 14;
      g.setLineDash([18, 16]);
      strokePath(g, path, 2.5, P.glow, "butt");
      g.restore();
      g.save();
      g.translate(-2, -hw * 0.55);
      strokePath(g, path, 3, "rgba(255, 255, 255, 0.22)");
      g.restore();
    } else {
      g.save();
      g.translate(7, 7);
      strokePath(g, path, hw * 2 + 12, P.shadow);
      g.restore();
      strokePath(g, path, hw * 2 + 12, INK);
      strokePath(g, path, hw * 2 + 6, P.wall);
      strokePath(g, path, hw * 2 - 6, P.track);
      g.setLineDash([10, 12]);
      strokePath(g, path, 2, "rgba(30, 35, 39, 0.3)", "butt");
      g.setLineDash([]);
    }
    g.restore();
  }
  function drawPeg(g, P, x, y, r) {
    if (P.design === "metal") {
      const shade = g.createRadialGradient(x - r * 0.35, y - r * 0.35, 0.5, x, y, r);
      shade.addColorStop(0, "#ffffff");
      shade.addColorStop(0.5, "#c4ccd3");
      shade.addColorStop(1, "#56616b");
      g.fillStyle = shade;
      g.beginPath();
      g.arc(x, y, r, 0, TAU);
      g.fill();
      return;
    }
    if (P.design === "paper") {
      g.fillStyle = INK;
      g.beginPath();
      g.arc(x + 2.5, y + 2.5, r, 0, TAU);
      g.fill();
      g.fillStyle = P.accentLight;
      g.beginPath();
      g.arc(x, y, r, 0, TAU);
      g.fill();
      g.strokeStyle = INK;
      g.lineWidth = 2;
      g.stroke();
      return;
    }
    g.fillStyle = "rgba(70, 38, 14, 0.35)";
    g.beginPath();
    g.arc(x + 2, y + 3, r, 0, TAU);
    g.fill();
    g.fillStyle = P.peg;
    g.beginPath();
    g.arc(x, y, r, 0, TAU);
    g.fill();
    g.strokeStyle = P.pegLo;
    g.lineWidth = 1.6;
    g.stroke();
    g.fillStyle = P.wall;
    g.beginPath();
    g.arc(x, y, r * 0.38, 0, TAU);
    g.fill();
  }
  function pegPositions(seg) {
    const found = [];
    const rowH = (seg.y1 - seg.y0) / seg.rows;
    for (let k = 0; k < seg.rows; k++) {
      const u = (k + 0.5) / seg.rows;
      const y = seg.y0 + rowH * (k + 0.5);
      const half = seg.width(u) - 16;
      const offset = k % 2 ? 28 : 0;
      for (let x = -560 + offset; x <= 560; x += 56) if (Math.abs(x) <= half) found.push([seg.cx + x, y]);
    }
    return found;
  }
  function drawSteps(g, P, seg) {
    const depth = 30;
    const dir = Math.sign(seg.stepW);
    for (let k = 0; k < seg.count; k++) {
      const xa = seg.x0 + seg.stepW * k;
      const xb = xa + seg.stepW;
      const left = Math.min(xa, xb) - 2;
      const width = Math.abs(seg.stepW) + 4;
      const y = seg.y0 + seg.stepH * k;
      if (P.design === "paper") {
        g.fillStyle = P.shadow;
        g.fillRect(left + 6, y + 6, width, depth);
        g.fillStyle = k % 2 ? P.wall : P.accentLight;
        g.fillRect(left, y, width, depth);
        g.strokeStyle = INK;
        g.lineWidth = 2.5;
        g.strokeRect(left, y, width, depth);
      } else if (P.design === "metal") {
        const face = g.createLinearGradient(0, y, 0, y + depth);
        face.addColorStop(0, "#77838e");
        face.addColorStop(1, "#2c333a");
        g.fillStyle = face;
        g.fillRect(left, y, width, depth);
        g.fillStyle = P.glow;
        g.fillRect(left, y, width, 2.5);
        g.fillStyle = "rgba(255, 255, 255, 0.35)";
        g.fillRect(left, y + 3, width, 1);
      } else {
        g.fillStyle = P.shadow;
        g.fillRect(left + 4, y + 6, width, depth);
        g.fillStyle = k % 2 ? P.wall : P.wallLo;
        g.fillRect(left, y + 6, width, depth - 6);
        g.fillStyle = P.track;
        g.fillRect(left, y, width, 7);
        g.strokeStyle = "rgba(60, 30, 10, 0.45)";
        g.lineWidth = 1.5;
        g.strokeRect(left, y, width, depth);
      }
      // 계단 끝 모서리 표시(구슬이 떨어지는 곳)
      g.fillStyle = P.design === "metal" ? "rgba(255, 255, 255, 0.5)" : "rgba(30, 35, 39, 0.25)";
      g.fillRect(dir > 0 ? xb - 3 : xb, y, 3, 6);
    }
  }
  function drawWaterfall(g, P, seg, t) {
    const x = seg.x0 + 10;
    g.save();
    g.globalAlpha = P.design === "metal" ? 0.55 : 0.7;
    for (let k = 0; k < 7; k++) {
      const offset = ((t * 160 + k * 37) % 90);
      g.strokeStyle = k % 2 ? "#7cc6f2" : "#b9e3fb";
      g.lineWidth = 4;
      g.beginPath();
      g.moveTo(x + k * 7, seg.y0 + offset * 0.4);
      g.lineTo(x + k * 7 + 4, seg.y0 + offset);
      g.stroke();
    }
    g.restore();
  }
  function drawCloud(g, P, x, y) {
    g.save();
    g.fillStyle = P.design === "metal" ? "#4b5560" : P.design === "paper" ? "#ffffff" : "#f4ead8";
    g.strokeStyle = P.design === "metal" ? "rgba(255,255,255,0.35)" : INK;
    g.lineWidth = P.design === "wood" ? 2 : 2.5;
    g.beginPath();
    g.arc(x - 30, y + 6, 22, Math.PI * 0.5, Math.PI * 1.5);
    g.arc(x - 6, y - 12, 26, Math.PI, Math.PI * 1.9);
    g.arc(x + 26, y - 2, 22, Math.PI * 1.3, Math.PI * 0.5);
    g.closePath();
    g.fill();
    g.stroke();
    g.fillStyle = P.gold;
    g.beginPath();
    g.moveTo(x - 4, y + 18);
    g.lineTo(x + 8, y + 18);
    g.lineTo(x + 1, y + 32);
    g.lineTo(x + 12, y + 32);
    g.lineTo(x - 8, y + 54);
    g.lineTo(x - 2, y + 38);
    g.lineTo(x - 12, y + 38);
    g.closePath();
    g.fill();
    g.strokeStyle = INK;
    g.lineWidth = 1.5;
    g.stroke();
    g.restore();
  }
  function drawVane(g, P, x, y, angle = 0) {
    g.save();
    g.strokeStyle = P.design === "metal" ? "#c4ccd3" : "#5a3a20";
    g.lineWidth = 4;
    g.beginPath();
    g.moveTo(x, y);
    g.lineTo(x, y + 70);
    g.stroke();
    g.translate(x, y);
    g.rotate(angle);
    for (let k = 0; k < 4; k++) {
      g.rotate(TAU / 4);
      g.fillStyle = k % 2 ? P.accent : P.accentLight;
      g.beginPath();
      g.moveTo(0, 0);
      g.lineTo(30, -6);
      g.lineTo(26, 10);
      g.closePath();
      g.fill();
      g.strokeStyle = INK;
      g.lineWidth = 1.5;
      g.stroke();
    }
    g.fillStyle = INK;
    g.beginPath();
    g.arc(0, 0, 4, 0, TAU);
    g.fill();
    g.restore();
  }
  function drawItemBox(g, P, x, y, size = 30, alpha = 1) {
    g.save();
    g.globalAlpha = alpha;
    g.fillStyle = P.design === "paper" ? INK : "rgba(0, 0, 0, 0.3)";
    g.fillRect(x - size / 2 + 3, y - size / 2 + 4, size, size);
    g.fillStyle = P.gold;
    g.fillRect(x - size / 2, y - size / 2, size, size);
    g.strokeStyle = INK;
    g.lineWidth = 2;
    g.strokeRect(x - size / 2, y - size / 2, size, size);
    g.fillStyle = INK;
    g.font = `${Math.round(size * 0.72)}px ${DISPLAY}`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillText("?", x, y + 2);
    g.restore();
  }
  function drawGate(g, P, x, y) {
    g.save();
    g.strokeStyle = P.design === "metal" ? P.gold : "#c9971c";
    g.lineWidth = 7;
    if (P.design === "metal") {
      g.shadowColor = P.gold;
      g.shadowBlur = 14;
    }
    g.beginPath();
    g.moveTo(x - 34, y + 30);
    g.lineTo(x - 34, y - 26);
    g.arc(x, y - 26, 34, Math.PI, 0);
    g.lineTo(x + 34, y + 30);
    g.stroke();
    g.shadowColor = "transparent";
    g.strokeStyle = INK;
    g.lineWidth = 1.5;
    g.stroke();
    g.fillStyle = P.gold;
    star(g, x, y - 58, 9);
    g.fill();
    g.stroke();
    g.restore();
  }
  function drawLever(g, P, x, y, flipped) {
    g.save();
    g.translate(x, y);
    g.fillStyle = P.design === "metal" ? "#77838e" : "#8a5a33";
    roundRect(g, -16, 4, 32, 14, 4);
    g.fill();
    g.strokeStyle = INK;
    g.lineWidth = 1.5;
    g.stroke();
    g.rotate(flipped ? 0.5 : -0.5);
    g.strokeStyle = P.design === "metal" ? "#dfe5ea" : "#5a3a20";
    g.lineWidth = 5;
    g.beginPath();
    g.moveTo(0, 8);
    g.lineTo(0, -26);
    g.stroke();
    g.fillStyle = P.accent;
    g.beginPath();
    g.arc(0, -28, 8, 0, TAU);
    g.fill();
    g.strokeStyle = INK;
    g.lineWidth = 1.5;
    g.stroke();
    g.restore();
  }
  function finishBand(g, x, y, angle, length, thick = 16) {
    g.save();
    g.translate(x, y);
    g.rotate(angle);
    const cells = Math.max(2, Math.round(length / (thick / 2)));
    const size = length / cells;
    for (let row = 0; row < 2; row++) {
      for (let k = 0; k < cells; k++) {
        g.fillStyle = (k + row) % 2 ? INK : "#ffffff";
        g.fillRect(-thick / 2 + row * (thick / 2), -length / 2 + k * size, thick / 2, size);
      }
    }
    g.strokeStyle = INK;
    g.lineWidth = 2;
    g.strokeRect(-thick / 2, -length / 2, thick, length);
    g.restore();
  }

  function marbleSprite(P, color, name, r, font) {
    const size = Math.ceil(r * 2 + 6);
    const c = document.createElement("canvas");
    c.width = size;
    c.height = size;
    const g = c.getContext("2d");
    const m = size / 2;
    if (P.design === "metal") {
      const shade = g.createRadialGradient(m - r * 0.35, m - r * 0.4, r * 0.1, m, m, r);
      shade.addColorStop(0, color.light);
      shade.addColorStop(0.55, color.fill);
      shade.addColorStop(1, color.dark);
      g.fillStyle = shade;
      g.beginPath();
      g.arc(m, m, r, 0, TAU);
      g.fill();
      g.save();
      g.beginPath();
      g.arc(m, m, r, 0, TAU);
      g.clip();
      g.strokeStyle = "rgba(255, 255, 255, 0.3)";
      g.lineWidth = r * 0.3;
      g.beginPath();
      g.arc(m + r * 0.55, m + r * 0.25, r * 0.95, Math.PI * 0.9, Math.PI * 1.55);
      g.stroke();
      g.restore();
      g.strokeStyle = "rgba(255, 255, 255, 0.6)";
      g.lineWidth = 1.2;
      g.beginPath();
      g.arc(m, m, r - 0.6, 0, TAU);
      g.stroke();
    } else if (P.design === "paper") {
      g.fillStyle = color.fill;
      g.beginPath();
      g.arc(m, m, r, 0, TAU);
      g.fill();
      g.strokeStyle = INK;
      g.lineWidth = 2;
      g.stroke();
      g.strokeStyle = "rgba(30, 35, 39, 0.16)";
      g.lineWidth = 1;
      g.beginPath();
      g.moveTo(m - r * 0.7, m + r * 0.7);
      g.lineTo(m + r * 0.7, m - r * 0.7);
      g.stroke();
    } else {
      const shade = g.createRadialGradient(m - r * 0.3, m - r * 0.35, r * 0.15, m, m, r);
      shade.addColorStop(0, color.light);
      shade.addColorStop(0.6, color.fill);
      shade.addColorStop(1, color.dark);
      g.fillStyle = shade;
      g.beginPath();
      g.arc(m, m, r, 0, TAU);
      g.fill();
      g.strokeStyle = color.dark;
      g.lineWidth = 1.5;
      g.stroke();
      g.strokeStyle = "rgba(255, 255, 255, 0.22)";
      g.lineWidth = r * 0.16;
      g.beginPath();
      g.arc(m, m, r * 0.64, 0, TAU);
      g.stroke();
    }
    g.fillStyle = color.text;
    g.font = `${Math.round(r * 1.08)}px ${font}`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillText(glyphOf(name), m, m + r * 0.07);
    return c;
  }
  function shineSprite(P, r) {
    const size = Math.ceil(r * 2 + 6);
    const c = document.createElement("canvas");
    c.width = size;
    c.height = size;
    if (P.design === "paper") return c;
    const g = c.getContext("2d");
    const m = size / 2;
    g.fillStyle = `rgba(255, 255, 255, ${P.design === "metal" ? 0.75 : 0.55})`;
    g.beginPath();
    g.ellipse(m - r * 0.38, m - r * 0.42, r * 0.32, r * 0.2, -0.6, 0, TAU);
    g.fill();
    return c;
  }
  // 이름표. placed(이미 놓은 이름표 영역)를 주면 겹치지 않게 위로 올리고 가는 선으로 잇는다
  function nameTag(g, P, text, x, y, size, rankColor, placed) {
    g.font = `700 ${size}px ${UI}`;
    const label = fitText(g, text, 220);
    const w = g.measureText(label).width + 18;
    const h = size + 10;
    const anchor = y;
    if (placed) {
      for (let tries = 0; tries < 6; tries++) {
        const hit = placed.find((box) => x - w / 2 < box[2] && x + w / 2 > box[0] && y - h < box[3] && y > box[1]);
        if (!hit) break;
        y = hit[1] - 4;
      }
      placed.push([x - w / 2, y - h, x + w / 2, y]);
    }
    g.save();
    const back = P.design === "paper" ? "#fffdf8" : "rgba(20, 24, 28, 0.86)";
    if (y < anchor) {
      g.strokeStyle = P.design === "paper" ? INK : "rgba(20, 24, 28, 0.86)";
      g.lineWidth = 1.5;
      g.beginPath();
      g.moveTo(x, y);
      g.lineTo(x, anchor);
      g.stroke();
    }
    g.fillStyle = back;
    roundRect(g, x - w / 2, y - h, w, h, P.design === "paper" ? 3 : h / 2);
    g.fill();
    if (P.design === "paper") {
      g.strokeStyle = INK;
      g.lineWidth = 2;
      g.stroke();
    }
    if (rankColor) {
      g.fillStyle = rankColor;
      g.fillRect(x - w / 2 + (P.design === "paper" ? 2 : h / 2 - 2), y - 4, w - (P.design === "paper" ? 4 : h - 4), 3);
    }
    if (y >= anchor) {
      g.beginPath();
      g.moveTo(x - 6, y);
      g.lineTo(x + 6, y);
      g.lineTo(x, y + 7);
      g.closePath();
      g.fillStyle = P.design === "paper" ? INK : "rgba(20, 24, 28, 0.86)";
      g.fill();
    }
    g.fillStyle = P.design === "paper" ? INK : "#ffffff";
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillText(label, x, y - h / 2 + 1);
    g.restore();
  }
  const MEDALS = (P) => [P.gold, P.silver, P.bronze];

  // 오른쪽 순위판(구슬): 지금 순위 12명. 꼴찌 당첨이면 뒤쪽, 지정 순위면 그 주변
  function drawRanking(g, env, list, finishedAt, sprites, started, footer) {
    const { P, race, font } = env;
    const x = 1490;
    const top = 196;
    const rowH = 62;
    const rows = Math.min(12, list.length);
    const n = list.length;
    let first = 0;
    if (race.rank === "last") first = n - rows;
    else if (race.rank === "custom") first = clamp(race.winner.place - 7, 0, n - rows);
    g.save();
    g.textBaseline = "middle";
    for (let row = 0; row < rows; row++) {
      const place = first + row;
      const lane = list[place];
      const y = top + row * rowH;
      const done = finishedAt(lane);
      if (row % 2 === 0) {
        g.fillStyle = P.design === "metal" ? "rgba(255, 255, 255, 0.04)" : "rgba(30, 35, 39, 0.05)";
        g.fillRect(x, y, 370, rowH - 4);
      }
      const medal = !started ? null : place < 3 && race.rank !== "last" ? MEDALS(P)[place] : race.rank === "last" && place === n - 1 ? P.accent : null;
      if (medal) {
        g.fillStyle = medal;
        g.beginPath();
        g.arc(x + 26, y + rowH / 2 - 2, 20, 0, TAU);
        g.fill();
        g.strokeStyle = P.design === "metal" ? "rgba(255, 255, 255, 0.4)" : INK;
        g.lineWidth = 2;
        g.stroke();
      }
      g.fillStyle = medal ? INK : P.text;
      g.font = `${place + 1 >= 100 ? 19 : 26}px ${font}`;
      g.textAlign = "center";
      g.fillText(String(place + 1), x + 26, y + rowH / 2);
      const sprite = sprites[lane];
      g.drawImage(sprite, x + 56, y + rowH / 2 - 2 - sprite.height / 2 * (26 / sprite.height) * 2 / 2, 26 * (sprite.width / sprite.height), 26);
      g.textAlign = "left";
      g.fillStyle = P.text;
      g.font = `25px ${font}`;
      g.fillText(fitText(g, env.heat.names[lane], done !== null ? 196 : 270), x + 94, y + rowH / 2);
      if (done !== null) {
        g.textAlign = "right";
        g.font = `700 21px ${UI}`;
        g.fillStyle = P.sub;
        g.fillText(done, x + 362, y + rowH / 2);
      }
    }
    g.textAlign = "center";
    g.font = `700 22px ${UI}`;
    g.fillStyle = P.sub;
    g.fillText(footer, x + 185, top + 12 * rowH + 14);
    g.restore();
  }

  function marbleSim(env) {
    const { heat, P, colors, rng, font } = env;
    const n = heat.names.length;
    const r = n <= 16 ? 15 : n <= 40 ? 12 : 10;
    const hw = Math.max(26, r * 2.7);
    const course = makeCourse(env.race.course || "zigzag");
    const profile = buildProfiles(n, heat.times, rng);
    const events = marbleEvents(env, profile, n);
    const place = [];
    heat.order.forEach((lane, index) => (place[lane] = index));
    const phase = Array.from({ length: n }, () => between(rng, 0, TAU));
    const sprites = heat.names.map((name, i) => marbleSprite(P, colors[i], name, r, font));
    const shine = shineSprite(P, r);
    const half = sprites[0].width / 2;
    // 출발 통(아래 줄부터 채움)
    const cols = Math.floor((course.hopper.w - 20) / (r * 2 + 1));
    const slots = Array.from({ length: n }, (_, k) => {
      const row = Math.floor(k / cols);
      const col = k % cols;
      const offset = row % 2 ? r : 0;
      return [course.hopper.x + 14 + r + col * (r * 2 + 1) + offset, course.hopper.y + course.hopper.h - 6 - r - row * r * 1.76];
    });
    // 도착 칸(도착 순서대로)
    const trayX = 104;
    const trayW = 1322;
    const pitch = r * 2 + 4;
    const perRow = Math.floor((trayW - 24) / pitch);
    const trayRows = Math.ceil(n / perRow);
    const trayY = 1032 - trayRows * pitch - 14;
    const traySlot = (k) => [trayX + 12 + r + (k % perRow) * pitch, trayY + 8 + r + Math.floor(k / perRow) * pitch];
    // 핀 숲의 좌우 이동(줄마다 왼쪽 또는 오른쪽, 벽에서 튕김)
    const pegSeg = course.segs.find((seg) => seg.kind === "pegs");
    const walks = pegSeg ? heat.names.map((_, i) => {
      const walk = mulberry32(hashOf(env.race.seed, env.index, "peg", i));
      const values = [((i * 0.618) % 1 - 0.5) * 60];
      for (let k = 1; k <= pegSeg.rows; k++) {
        const limit = pegSeg.width(k / pegSeg.rows) - r - 8;
        let next = values[k - 1] + (walk() < 0.5 ? -28 : 28) + (walk() - 0.5) * 10;
        if (next > limit) next = limit - (next - limit);
        if (next < -limit) next = -limit + (-limit - next);
        values.push(clamp(next, -limit, limit));
      }
      return values;
    }) : [];
    const wind = events.filter((event) => event.kind === "wind");
    const X = new Float32Array(n);
    const Y = new Float32Array(n);
    const A = new Float32Array(n);
    const NX = new Float32Array(n);
    const NY = new Float32Array(n);
    const OFF = new Float32Array(n);
    const MODE = new Uint8Array(n);  // 0 출발 통, 1 레일, 2 핀 숲, 3 도착, 4 계단과 낙하
    const D = new Float32Array(n);
    const queue = [];
    const SEG = new Int16Array(n);

    function positions(t) {
      let windPush = 0;
      for (const event of wind) windPush += event.dir * window01(t, event.t, event.dur, 0.25);
      for (let i = 0; i < n; i++) {
        const T = profile.times[i];
        if (t >= T) {  // 도착: 결승선에서 아래로 떨어진 뒤 도착 칸으로
          const [sx, sy] = traySlot(place[i]);
          const u = (t - T) / 1.3;
          const [fx, fy] = course.finish;
          if (u < 0.3) {
            X[i] = fx - 10 * (u / 0.3);
            Y[i] = lerp(fy - r, sy, easeIn(u / 0.3));
          } else {
            const v = easeOut((u - 0.3) / 0.7);
            X[i] = lerp(fx - 10, sx, v);
            Y[i] = sy;
          }
          A[i] = (course.total + (u < 1 ? Math.abs(X[i] - fx) : Math.abs(sx - fx))) / r;
          MODE[i] = 3;
          continue;
        }
        const p = progressOf(profile, i, t);
        const d = p * course.total;
        let s = 0;
        while (s < course.segs.length - 1 && d >= course.starts[s + 1]) s++;
        const seg = course.segs[s];
        const u = (d - course.starts[s]) / seg.len;
        SEG[i] = s;
        A[i] = d / r * 0.9;
        if (seg.kind === "hopper") {
          const [sx, sy] = slots[i];
          const [ex, ey] = course.hopper.exit;
          if (u < 0.65) {
            const v = easeIn(u / 0.65);
            X[i] = lerp(sx, ex, v);
            Y[i] = lerp(sy, ey, v);
          } else {
            const v = (u - 0.65) / 0.35;
            X[i] = lerp(ex, seg.end[0], v);
            Y[i] = lerp(ey, seg.end[1] - r, v);
          }
          MODE[i] = 0;
          continue;
        }
        if (seg.kind === "pegs") {
          const walk = walks[i];
          const row = u * seg.rows;
          const k = Math.min(seg.rows - 1, Math.floor(row));
          const f = row - k;
          X[i] = seg.cx + lerp(walk[k], walk[k + 1], smooth(f));
          Y[i] = seg.y0 + (seg.y1 - seg.y0) * u - Math.sin(Math.PI * f) * 7;
          MODE[i] = 2;
          continue;
        }
        if (seg.kind === "steps" || seg.kind === "drop") {
          D[i] = d;
          MODE[i] = 4;
          continue;
        }
        const lane = 0.55 * Math.sin(phase[i] + d * 0.0055 + t * 0.35) + windPush * 0.45;
        OFF[i] = clamp(lane, -1, 1) * (hw - r - 2);
        const [x, y, angle, nx, ny] = seg.at(u, 0);
        X[i] = x;
        Y[i] = y;
        NX[i] = nx;
        NY[i] = ny;
        MODE[i] = 1;
        void angle;
      }
      // 계단과 낙하 구간은 한 줄: 앞 구슬과 지름만큼 띄워 뒤로 줄 세운다(순서는 그대로, 최대 구슬 8개 길이)
      queue.length = 0;
      for (let i = 0; i < n; i++) if (MODE[i] === 4) queue.push(i);
      queue.sort((a, b) => D[b] - D[a]);
      let ahead = Infinity;
      for (const i of queue) {
        const d = Math.max(course.starts[1], D[i] - r * 16, Math.min(D[i], ahead - r * 2.1));
        ahead = d;
        let s = 0;
        while (s < course.segs.length - 1 && d >= course.starts[s + 1]) s++;
        const seg = course.segs[s];
        const u = clamp((d - course.starts[s]) / seg.len, 0, 1);
        if (seg.kind === "steps" || seg.kind === "drop") {
          const [x, y] = seg.at(u, 0);
          X[i] = x;
          Y[i] = y - r;
        } else {
          const [x, y] = seg.at(u, 0);
          X[i] = x;
          Y[i] = y;
        }
      }
      // 레일 위 구슬 겹침 풀기(진행 방향은 그대로, 옆으로만)
      const limit = hw - r - 2;
      for (let pass = 0; pass < 3; pass++) {
        for (let i = 0; i < n; i++) {
          if (MODE[i] !== 1) continue;
          for (let j = i + 1; j < n; j++) {
            if (MODE[j] !== 1 || SEG[j] !== SEG[i]) continue;
            const ax = X[i] + NX[i] * OFF[i];
            const ay = Y[i] + NY[i] * OFF[i];
            const bx = X[j] + NX[j] * OFF[j];
            const by = Y[j] + NY[j] * OFF[j];
            const dist = Math.hypot(ax - bx, ay - by);
            if (dist >= r * 1.9) continue;
            const along = Math.abs((ax - bx) * NY[i] - (ay - by) * NX[i]);
            if (along >= r * 1.9) continue;
            const need = Math.sqrt(Math.max(0, (r * 1.9) ** 2 - along * along)) - Math.abs(OFF[i] - OFF[j]);
            if (need <= 0) continue;
            const sign = OFF[i] >= OFF[j] ? 1 : -1;
            OFF[i] = clamp(OFF[i] + (sign * need) / 2, -limit, limit);
            OFF[j] = clamp(OFF[j] - (sign * need) / 2, -limit, limit);
          }
        }
      }
      for (let i = 0; i < n; i++) {
        if (MODE[i] === 1) {
          X[i] += NX[i] * OFF[i];
          Y[i] += NY[i] * OFF[i];
        }
      }
    }

    function finishedAt(t) {
      return (lane) => (t >= profile.times[lane] ? `${profile.times[lane].toFixed(2)}초` : null);
    }

    function drawStatic(g) {
      panel(g, P, 40, 112, 1410, 940, { seed: 11, screws: true, fill: P.plate, tape: true });
      // 출발 통
      const hop = course.hopper;
      g.save();
      const funnel = new Path2D();
      funnel.moveTo(hop.x, hop.y);
      funnel.lineTo(hop.x + hop.w, hop.y);
      funnel.lineTo(hop.x + hop.w, hop.y + hop.h);
      funnel.lineTo(hop.exit[0] + r + 8, hop.exit[1]);
      funnel.lineTo(hop.exit[0] - r - 8, hop.exit[1]);
      funnel.lineTo(hop.x, hop.y + hop.h);
      funnel.closePath();
      if (P.design === "paper") {
        g.save();
        g.translate(7, 7);
        g.fillStyle = P.shadow;
        g.fill(funnel);
        g.restore();
      }
      g.fillStyle = P.design === "metal" ? "rgba(160, 200, 230, 0.1)" : P.design === "paper" ? P.accentSoft : "rgba(255, 245, 225, 0.75)";
      g.fill(funnel);
      g.lineWidth = P.design === "paper" ? 3 : 6;
      g.strokeStyle = P.design === "paper" ? INK : P.design === "metal" ? "rgba(225, 240, 255, 0.6)" : P.wallLo;
      g.stroke(funnel);
      g.font = `22px ${font}`;
      g.fillStyle = P.design === "metal" ? P.sub : P.text;
      g.textAlign = "left";
      g.textBaseline = "top";
      g.fillText("출발", hop.x + hop.w + 14, hop.y + 4);
      g.restore();
      // 레일
      const path = chutePath(course.segs);
      drawChute(g, P, path, hw);
      for (const seg of course.segs) {
        if (seg.kind === "pegs") {
          g.save();
          const field = new Path2D();
          const edge = 12;
          for (let k = 0; k <= 24; k++) field.lineTo(seg.cx - seg.width(k / 24) - edge, seg.y0 + (seg.y1 - seg.y0) * (k / 24));
          for (let k = 24; k >= 0; k--) field.lineTo(seg.cx + seg.width(k / 24) + edge, seg.y0 + (seg.y1 - seg.y0) * (k / 24));
          field.closePath();
          if (P.design !== "metal") {
            g.save();
            g.translate(P.design === "paper" ? 7 : 4, P.design === "paper" ? 7 : 6);
            g.fillStyle = P.shadow;
            g.fill(field);
            g.restore();
          }
          g.fillStyle = P.design === "metal" ? "rgba(160, 200, 230, 0.08)" : P.track;
          g.fill(field);
          g.lineWidth = P.design === "paper" ? 3 : 7;
          g.strokeStyle = P.design === "paper" ? INK : P.design === "metal" ? "rgba(225, 240, 255, 0.55)" : P.wall;
          g.stroke(field);
          for (const [px, py] of pegPositions(seg)) drawPeg(g, P, px, py, 6);
          g.restore();
        } else if (seg.kind === "steps") {
          drawSteps(g, P, seg);
        }
      }
      // 장식(켜진 깜짝 요소)
      const on = new Set(env.events);
      const a = course.anchors;
      if (on.has("lightning")) drawCloud(g, P, a.cloud[0], a.cloud[1]);
      if (on.has("item")) for (const [ix, iy] of a.items) drawItemBox(g, P, ix, iy, 28);
      if (on.has("gate")) drawGate(g, P, a.gate[0], a.gate[1]);
      // 도착 칸
      g.save();
      if (P.design === "paper") {
        g.fillStyle = P.shadow;
        g.fillRect(trayX + 6, trayY + 6, trayW, trayRows * pitch + 16);
      }
      g.fillStyle = P.design === "metal" ? "rgba(0, 0, 0, 0.3)" : P.design === "paper" ? "#ffffff" : "rgba(122, 74, 34, 0.18)";
      roundRect(g, trayX, trayY, trayW, trayRows * pitch + 16, P.design === "paper" ? 3 : 12);
      g.fill();
      g.strokeStyle = P.design === "paper" ? INK : P.design === "metal" ? "rgba(255, 255, 255, 0.25)" : "rgba(80, 45, 20, 0.45)";
      g.lineWidth = P.design === "paper" ? 3 : 2;
      g.stroke();
      for (let k = 0; k < n; k++) {
        const [sx, sy] = traySlot(k);
        g.fillStyle = P.design === "metal" ? "rgba(255, 255, 255, 0.06)" : "rgba(30, 35, 39, 0.08)";
        g.beginPath();
        g.arc(sx, sy, r + 1, 0, TAU);
        g.fill();
      }
      g.restore();
      // 결승선
      const last = course.segs[course.segs.length - 1];
      const [fx, fy, angle] = last.at(0.985, 0);
      if (last.kind === "steps") finishBand(g, fx, fy - r - 6, 0, r * 2 + 18, 12);
      else finishBand(g, fx, fy, angle, hw * 2 + 12, 14);
      g.save();
      g.font = `24px ${font}`;
      g.textAlign = "center";
      g.fillStyle = P.design === "metal" ? P.text : P.text;
      g.fillText("결승", fx, fy - hw - 28);
      g.restore();
      // 오른쪽 순위판
      panel(g, P, 1470, 112, 410, 940, { seed: 12, fill: P.panel });
      g.save();
      g.font = `30px ${font}`;
      g.fillStyle = P.text;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText(env.race.rank === "last" ? "꼴찌 경쟁" : "실시간 순위", 1675, 158);
      g.restore();
    }

    function draw(g, t) {
      positions(t);
      // 바람: 판 위로 지나가는 선
      for (const event of wind) {
        const amount = window01(t, event.t, event.dur, 0.25);
        if (!amount) continue;
        const lines = mulberry32(event.seed);
        g.save();
        g.globalAlpha = amount * 0.55;
        g.strokeStyle = P.design === "metal" ? "#cfe8ff" : P.design === "paper" ? INK : "#ffffff";
        g.lineWidth = 3;
        g.lineCap = "round";
        for (let k = 0; k < 24; k++) {
          const y = 150 + lines() * 860;
          const speed = 700 + lines() * 600;
          const length = 60 + lines() * 120;
          const x = event.dir > 0 ? 60 + ((lines() * 1400 + (t - event.t) * speed) % 1380) : 1440 - ((lines() * 1400 + (t - event.t) * speed) % 1380);
          g.beginPath();
          g.moveTo(x, y);
          g.lineTo(x - event.dir * length, y + 6);
          g.stroke();
        }
        g.restore();
      }
      // 계단 폭포 물
      for (const seg of course.segs) if (seg.kind === "drop") drawWaterfall(g, P, seg, t);
      // 갈림길 레버, 바람개비(움직임)
      const on = new Set(env.events);
      if (on.has("switch")) {
        const flipped = events.some((event) => event.kind === "switch" && t >= event.t && t < event.t + event.dur);
        drawLever(g, P, course.anchors.lever[0], course.anchors.lever[1], flipped);
      }
      if (on.has("wind")) {
        let spin = t * 1.5;
        for (const event of wind) spin += Math.max(0, Math.min(t, event.t + event.dur) - event.t) * 10;
        drawVane(g, P, course.anchors.vane[0], course.anchors.vane[1], spin);
      }
      // 그림자와 구슬
      if (P.design !== "metal") {
        g.fillStyle = P.design === "paper" ? "rgba(30, 35, 39, 0.3)" : "rgba(60, 30, 10, 0.25)";
        for (let i = 0; i < n; i++) {
          g.beginPath();
          g.ellipse(X[i] + 3, Y[i] + r * 0.8, r * 0.85, r * 0.3, 0, 0, TAU);
          g.fill();
        }
      }
      for (let i = 0; i < n; i++) {
        g.save();
        g.translate(X[i], Y[i]);
        g.rotate(A[i]);
        g.drawImage(sprites[i], -half, -half);
        g.restore();
        g.drawImage(shine, X[i] - half, Y[i] - half);
      }
      // 깜짝 요소 표시
      for (const event of events) {
        const since = t - event.t;
        if (since < 0 || since > event.dur + 0.4) continue;
        const amount = window01(t, event.t, event.dur + 0.4, 0.15);
        event.targets.forEach((lane, index) => {
          if (t >= profile.times[lane]) return;
          const x = X[lane];
          const y = Y[lane];
          g.save();
          if (event.kind === "lightning") {
            if (since < 0.45) {
              const bolt = mulberry32(event.seed);
              g.strokeStyle = P.gold;
              g.lineWidth = 7;
              g.shadowColor = "#fff6c2";
              g.shadowBlur = 18;
              g.beginPath();
              g.moveTo(course.anchors.cloud[0], course.anchors.cloud[1] + 30);
              for (let k = 1; k <= 6; k++) {
                const u = k / 6;
                g.lineTo(lerp(course.anchors.cloud[0], x, u) + (k < 6 ? (bolt() - 0.5) * 60 : 0), lerp(course.anchors.cloud[1] + 30, y, u));
              }
              g.stroke();
              g.strokeStyle = "#ffffff";
              g.lineWidth = 2.5;
              g.stroke();
            }
            for (let k = 0; k < 3; k++) {
              const angle = t * 6 + (k * TAU) / 3;
              g.fillStyle = P.gold;
              star(g, x + Math.cos(angle) * (r + 9), y - r - 4 + Math.sin(angle) * 5, 6);
              g.fill();
              g.strokeStyle = INK;
              g.lineWidth = 1.2;
              g.stroke();
            }
          } else if (event.kind === "comeback" || (event.kind === "item" && event.good) || (event.factors[index] > 1 && event.kind === "gate")) {
            g.globalAlpha = amount;
            const flicker = 0.75 + 0.25 * Math.sin(t * 40 + lane);
            const back = Math.atan2(NY[lane] || 0, NX[lane] || 1);
            void back;
            for (let k = 3; k >= 1; k--) {
              g.fillStyle = k === 3 ? "rgba(255, 120, 40, 0.55)" : k === 2 ? "rgba(255, 190, 60, 0.75)" : "rgba(255, 245, 190, 0.95)";
              g.beginPath();
              g.ellipse(x - (r + k * 6) * flicker * (A[lane] > 0 ? 1 : 1), y, r * 0.5 * k * flicker, r * 0.35 * k, 0, 0, TAU);
              g.fill();
            }
          } else if (event.kind === "check" || (event.kind === "item" && !event.good) || (event.kind === "gate" && event.factors[index] < 1)) {
            g.globalAlpha = amount;
            g.strokeStyle = "#e5484d";
            g.lineWidth = 4;
            g.beginPath();
            g.arc(x, y, r + 7, 0, TAU);
            g.stroke();
            g.fillStyle = "#e5484d";
            g.font = `22px ${DISPLAY}`;
            g.textAlign = "center";
            g.fillText("!", x, y - r - 12);
          } else if (event.kind === "switch" || event.kind === "quake") {
            g.globalAlpha = amount * 0.9;
            g.setLineDash([5, 5]);
            g.strokeStyle = event.kind === "quake" ? P.text : P.accent;
            g.lineWidth = 2.5;
            g.beginPath();
            g.arc(x, y, r + 6, t * 3, t * 3 + TAU);
            g.stroke();
          }
          if (event.kind === "gate") {
            g.globalAlpha = amount;
            g.setLineDash([]);
            g.strokeStyle = P.gold;
            g.lineWidth = 3;
            g.beginPath();
            g.arc(x, y, r + 12 + 4 * Math.sin(t * 8), 0, TAU);
            g.stroke();
          }
          if (event.kind === "item" && since < 0.7) {
            const pop = since / 0.7;
            drawItemBox(g, P, x, y - r - 20 - pop * 30, 26 * (1 + pop * 0.4), 1 - pop);
          }
          g.restore();
        });
      }
      // 번개 섬광
      for (const event of events) {
        if (event.kind !== "lightning") continue;
        const since = t - event.t;
        if (since >= 0 && since < 0.3) {
          g.fillStyle = `rgba(255, 255, 240, ${0.35 * (1 - since / 0.3)})`;
          g.fillRect(52, 124, 1386, 916);
        }
      }
      // 이름표: 선두 3명(꼴찌 당첨이면 뒤 3명), 12명 이하면 모두
      const order = orderAt(profile, n, t);
      const running = order.filter((lane) => t < profile.times[lane]);
      const tagged = t <= 0 ? [] : n <= 12 ? running : env.race.rank === "last" ? running.slice(-3) : running.slice(0, 3);
      const medals = MEDALS(P);
      const placed = [];
      for (const lane of tagged) {
        const index = order.indexOf(lane);
        const medal = env.race.rank !== "last" && index < 3 ? medals[index] : null;
        nameTag(g, P, `${index + 1} ${heat.names[lane]}`, X[lane], Y[lane] - r - 6, n <= 12 ? 16 : 18, medal, placed);
      }
      const finished = order.filter((lane) => t >= profile.times[lane]).length;
      drawRanking(g, env, order, finishedAt(t), sprites, t > 0, t > 0 ? `참가 ${n}명, 도착 ${finished}명` : `참가 ${n}명, 출발 대기`);
    }

    function shake(t) {
      let amount = 0;
      for (const event of events) if (event.kind === "quake") amount += window01(t, event.t, event.dur, 0.15);
      return amount ? [Math.sin(t * 57) * 7 * amount, Math.cos(t * 43) * 5 * amount] : [0, 0];
    }

    return { drawStatic, draw, shake, events, end: heat.end, finishes: heat.order.map((lane) => profile.times[lane]), tick: "tick" };
  }

  // ---------------------------------------------------------------- 달리기 경주: 마스코트 마이(리본 마이크, 은색 망 머리와 코랄 불)
  function drawRunner(g, P, x, y, S, color, phase, pose, t, number, font) {
    // x, y: 발 아래 땅, S: 키
    g.save();
    g.translate(x, y);
    const bob = pose === "fallen" ? 0 : -Math.abs(Math.sin(phase)) * S * 0.07;
    g.fillStyle = P.design === "metal" ? "rgba(0, 0, 0, 0.45)" : "rgba(40, 25, 10, 0.25)";
    g.beginPath();
    g.ellipse(0, 0, S * (pose === "fallen" || pose === "dive" ? 0.5 : 0.3), S * 0.07, 0, 0, TAU);
    g.fill();
    const outline = P.design === "metal" ? "rgba(255, 255, 255, 0.75)" : INK;
    const line = Math.max(1.5, S * 0.035);
    const legs = (hipX, hipY, swing, length) => {
      g.strokeStyle = outline;
      g.lineWidth = Math.max(2.5, S * 0.07);
      g.lineCap = "round";
      for (const side of [1, -1]) {
        const angle = Math.sin(phase + (side > 0 ? 0 : Math.PI)) * swing;
        g.beginPath();
        g.moveTo(hipX, hipY);
        g.lineTo(hipX + Math.sin(angle) * length, hipY + Math.cos(angle) * length);
        g.stroke();
      }
    };
    let tilt = 0.12;
    if (pose === "sprint") tilt = 0.32;
    if (pose === "limp") tilt = -0.05 + Math.sin(t * 9) * 0.08;
    if (pose === "dive") tilt = 1.25;
    if (pose === "fallen") tilt = 1.55;
    if (pose === "idle") tilt = 0;
    if (pose === "cheer") tilt = Math.sin(t * 7) * 0.12;
    const bodyW = S * 0.62;
    const bodyH = S * 0.64;
    const bodyY = pose === "fallen" ? -bodyW * 0.5 : pose === "dive" ? -S * 0.32 : -S * 0.28 - bodyH * 0.5 + bob;
    if (pose !== "fallen" && pose !== "dive") {
      if (pose === "limp") {
        g.strokeStyle = outline;
        g.lineWidth = Math.max(2.5, S * 0.07);
        g.lineCap = "round";
        g.beginPath();
        g.moveTo(-S * 0.06, -S * 0.3 + bob);
        g.lineTo(-S * 0.02, 0);
        g.moveTo(S * 0.06, -S * 0.3 + bob);
        g.lineTo(S * 0.18, -S * 0.12);
        g.stroke();
      } else {
        legs(0, -S * 0.3 + bob, pose === "idle" || pose === "cheer" ? 0.15 : pose === "sprint" ? 1.05 : 0.8, S * 0.3);
      }
    }
    g.translate(0, bodyY);
    g.rotate(tilt);
    // 꼭대기 불(마이의 코랄 불): 몸 뒤에서 위로 조금 나옴
    g.fillStyle = "#ff6f6f";
    g.strokeStyle = outline;
    g.lineWidth = line;
    g.beginPath();
    g.arc(0, -bodyH * 0.53, Math.max(2, bodyW * 0.1), 0, TAU);
    g.fill();
    g.stroke();
    // 몸(마이: 리본 마이크 모양). 몸 색은 참가자마다 다름
    const shade = g.createLinearGradient(0, -bodyH / 2, 0, bodyH / 2);
    shade.addColorStop(0, P.design === "paper" ? color.fill : color.light);
    shade.addColorStop(0.45, color.fill);
    shade.addColorStop(1, P.design === "paper" ? color.fill : color.dark);
    g.fillStyle = shade;
    roundRect(g, -bodyW / 2, -bodyH / 2, bodyW, bodyH, bodyW * 0.48);
    g.fill();
    // 망 머리: 몸 윗부분을 은색으로, 망 두 줄과 경계선. 눈과 겹치지 않도록 경계선은 눈 위쪽에 여유를 둠
    const capBottom = -bodyH * 0.25;
    g.save();
    roundRect(g, -bodyW / 2, -bodyH / 2, bodyW, bodyH, bodyW * 0.48);
    g.clip();
    const metal = g.createLinearGradient(0, -bodyH / 2, 0, capBottom);
    metal.addColorStop(0, "#f4f1fb");
    metal.addColorStop(1, "#cfc8e6");
    g.fillStyle = metal;
    g.fillRect(-bodyW / 2, -bodyH / 2, bodyW, capBottom + bodyH / 2);
    g.strokeStyle = "rgba(74, 60, 134, 0.7)";
    g.lineWidth = Math.max(1, S * 0.02);
    for (const k of [0.41, 0.33]) {
      g.beginPath();
      g.moveTo(-bodyW / 2, -bodyH * k);
      g.lineTo(bodyW / 2, -bodyH * k);
      g.stroke();
    }
    g.strokeStyle = outline;
    g.lineWidth = line;
    g.beginPath();
    g.moveTo(-bodyW / 2, capBottom);
    g.lineTo(bodyW / 2, capBottom);
    g.stroke();
    g.restore();
    g.strokeStyle = outline;
    g.lineWidth = line;
    roundRect(g, -bodyW / 2, -bodyH / 2, bodyW, bodyH, bodyW * 0.48);
    g.stroke();
    // 눈(오른쪽을 봄). 망 머리 경계선 아래
    const eyeY = -bodyH * 0.03;
    g.fillStyle = "#ffffff";
    g.beginPath();
    g.ellipse(bodyW * 0.2, eyeY, S * 0.07, S * 0.085, 0, 0, TAU);
    g.ellipse(-bodyW * 0.02, eyeY, S * 0.055, S * 0.075, 0, 0, TAU);
    g.fill();
    g.fillStyle = INK;
    if (pose === "fallen") {
      g.lineWidth = Math.max(1.5, S * 0.03);
      g.strokeStyle = INK;
      for (const ex of [bodyW * 0.2, -bodyW * 0.02]) {
        g.beginPath();
        g.moveTo(ex - S * 0.035, eyeY - S * 0.035);
        g.lineTo(ex + S * 0.035, eyeY + S * 0.035);
        g.moveTo(ex + S * 0.035, eyeY - S * 0.035);
        g.lineTo(ex - S * 0.035, eyeY + S * 0.035);
        g.stroke();
      }
    } else {
      g.beginPath();
      g.arc(bodyW * 0.23, eyeY + S * 0.01, S * 0.035, 0, TAU);
      g.arc(0.01 * bodyW, eyeY + S * 0.01, S * 0.03, 0, TAU);
      g.fill();
    }
    // 볼
    g.fillStyle = "rgba(255, 120, 150, 0.45)";
    g.beginPath();
    g.ellipse(bodyW * 0.3, eyeY + S * 0.1, S * 0.05, S * 0.03, 0, 0, TAU);
    g.fill();
    // 번호표
    if (S >= 34) {
      const bibW = bodyW * 0.42;
      const bibH = bodyH * 0.26;
      g.fillStyle = "#ffffff";
      g.fillRect(-bibW * 0.7, bodyH * 0.1, bibW, bibH);
      g.strokeStyle = INK;
      g.lineWidth = Math.max(1, line * 0.6);
      g.strokeRect(-bibW * 0.7, bodyH * 0.1, bibW, bibH);
      g.fillStyle = INK;
      g.font = `${Math.round(bibH * 0.86)}px ${font}`;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText(String(number), -bibW * 0.2, bodyH * 0.1 + bibH * 0.55);
    }
    // 팔
    g.strokeStyle = outline;
    g.lineWidth = Math.max(2, S * 0.055);
    g.lineCap = "round";
    if (pose === "dive") {
      g.beginPath();
      g.moveTo(bodyW * 0.1, -bodyH * 0.45);
      g.lineTo(bodyW * 0.05, -bodyH * 0.85);
      g.stroke();
    } else if (pose === "cheer") {
      g.beginPath();
      g.moveTo(bodyW * 0.38, -bodyH * 0.05);
      g.lineTo(bodyW * 0.6, -bodyH * 0.55);
      g.moveTo(-bodyW * 0.38, -bodyH * 0.05);
      g.lineTo(-bodyW * 0.6, -bodyH * 0.55);
      g.stroke();
    } else if (pose !== "fallen") {
      const swing = Math.sin(phase + Math.PI) * (pose === "sprint" ? 0.9 : 0.6);
      g.beginPath();
      g.moveTo(bodyW * 0.3, bodyH * 0.05);
      g.lineTo(bodyW * 0.3 + Math.sin(swing) * S * 0.18, bodyH * 0.05 + Math.cos(swing) * S * 0.14);
      g.stroke();
    }
    g.restore();
    // 넘어짐 별, 쥐 땀방울
    if (pose === "fallen") {
      for (let k = 0; k < 3; k++) {
        const angle = t * 5 + (k * TAU) / 3;
        g.fillStyle = P.gold;
        star(g, x + Math.cos(angle) * S * 0.35, y - S * 0.62 + Math.sin(angle) * S * 0.08, Math.max(4, S * 0.07));
        g.fill();
        g.strokeStyle = INK;
        g.lineWidth = 1;
        g.stroke();
      }
    } else if (pose === "limp") {
      g.fillStyle = "#7cc6f2";
      g.strokeStyle = INK;
      g.lineWidth = 1;
      const dropY = y - S * 0.95 + ((t * 30) % 10);
      g.beginPath();
      g.moveTo(x - S * 0.3, dropY - S * 0.08);
      g.quadraticCurveTo(x - S * 0.24, dropY, x - S * 0.3, dropY + S * 0.03);
      g.quadraticCurveTo(x - S * 0.36, dropY, x - S * 0.3, dropY - S * 0.08);
      g.fill();
      g.stroke();
    } else if (pose === "sprint") {
      g.strokeStyle = P.design === "metal" ? P.glow : "rgba(30, 35, 39, 0.5)";
      g.lineWidth = Math.max(2, S * 0.04);
      g.lineCap = "round";
      for (let k = 0; k < 3; k++) {
        const ly = y - S * (0.35 + k * 0.17);
        g.beginPath();
        g.moveTo(x - S * (0.5 + k * 0.06), ly);
        g.lineTo(x - S * (0.95 + k * 0.1), ly);
        g.stroke();
      }
    }
  }

  // ---------------------------------------------------------------- 수영: 위에서 본 수영 선수(오른쪽으로 헤엄). cy는 줄 가운데, L은 줄 높이
  function drawSwimmer(g, P, x, cy, L, color, phase, pose, t, number, font) {
    // 위에서 본 자유형 선수(오른쪽으로 헤엄). s는 줄 높이 1/100 단위. 물속 부분(다리, 끌어당기는 팔)은 물빛을 덮어 흐리게
    const s = L / 100;
    x -= 32 * s;  // 앞으로 뻗은 손끝이 경기 위치(결승 벽에 손이 닿게)
    const suit = color.fill || color, suitDark = color.dark || "#1e2327", suitLight = color.light || "#ffffff", mark = color.text || "#ffffff";
    const SKIN = "#f3c9a5", SKIN_DARK = "#d9a27c", water = P.design === "metal" ? "rgba(12, 60, 90, 0.42)" : "rgba(40, 150, 200, 0.38)";
    const swimming = pose === "run" || pose === "sprint" || pose === "wave" || pose === "limp";
    const stroke = swimming ? phase * 0.9 : 0;
    const roll = swimming ? Math.sin(stroke) : 0;  // 몸 돌림(-1에서 1): 위로 올라온 쪽이 밝음
    const sx = x + 2 * s;  // 어깨 줄
    const hx = x + 19 * s;  // 머리 가운데
    const limb = (points, width, fill) => {  // 끝이 둥근 팔다리(관절 점들)
      g.strokeStyle = fill;
      g.lineWidth = width;
      g.lineCap = "round";
      g.lineJoin = "round";
      g.beginPath();
      points.forEach(([px, py], index) => g[index ? "lineTo" : "moveTo"](px, py));
      g.stroke();
    };
    g.save();
    if (pose === "dive") g.globalAlpha = 0.55;  // 잠영: 물속

    // 그림자(물 밑)
    g.fillStyle = "rgba(0, 40, 70, 0.16)";
    g.beginPath();
    g.ellipse(x - 10 * s, cy + 6 * s, 40 * s, 12 * s, 0, 0, TAU);
    g.fill();

    // 물결: 뒤로 퍼지는 V자와 발차기 거품
    if (swimming) {
      g.strokeStyle = "rgba(255, 255, 255, 0.55)";
      g.lineWidth = Math.max(1.2, 1.8 * s);
      for (let k = 0; k < 3; k++) {
        const back = x - (68 + k * 16) * s;
        const open = (14 + k * 7) * s;
        g.globalAlpha = (pose === "dive" ? 0.3 : 0.7) - k * 0.18;
        g.beginPath();
        g.moveTo(back + 12 * s, cy - open);
        g.quadraticCurveTo(back, cy, back + 12 * s, cy + open);
        g.stroke();
      }
      g.globalAlpha = pose === "dive" ? 0.55 : 1;
      g.fillStyle = "rgba(255, 255, 255, 0.9)";
      const kicks = pose === "limp" ? 2 : pose === "wave" ? 12 : 7;
      for (let k = 0; k < kicks; k++) {
        const a = stroke * 2.2 + k * 1.9;
        g.beginPath();
        g.arc(x - (60 + 8 * Math.abs(Math.sin(a * 0.7))) * s, cy + Math.sin(a) * 9 * s, (1.4 + 1.6 * Math.abs(Math.cos(a))) * s, 0, TAU);
        g.fill();
      }
    }

    // 다리(물속, 번갈아 차기): 반투명으로 물이 비쳐 보이게
    g.save();
    g.globalAlpha *= 0.72;
    for (const side of [-1, 1]) {
      const kick = pose === "limp" && side > 0 ? 0 : swimming ? Math.sin(stroke * 2.2 + (side > 0 ? 0 : Math.PI)) * 4 * s : 0;
      const hip = [x - 30 * s, cy + side * 5.5 * s];
      const knee = [x - 45 * s, cy + side * 6.5 * s + kick * 0.5];
      const foot = [x - 58 * s, cy + side * 6 * s + kick];
      limb([hip, knee, foot], 8.5 * s, SKIN_DARK);
      limb([hip, knee, foot], 6.5 * s, SKIN);
      g.fillStyle = SKIN;
      g.beginPath();
      g.ellipse(foot[0] - 3 * s, foot[1], 4.5 * s, 2.6 * s, 0, 0, TAU);
      g.fill();
    }
    g.restore();

    // 팔: 물속으로 당기는 팔(흐림)과 물 위로 돌아오는 팔(팔꿈치 높이)
    const arm = (side, a) => {
      const shoulder = [sx, cy + side * 14 * s * (1 - 0.12 * side * roll)];
      if (pose === "idle" || pose === "dive") {  // 출발 전, 잠영: 두 팔을 앞으로 모음
        const hand = [x + 42 * s, cy + side * 3 * s];
        limb([shoulder, [x + 22 * s, cy + side * 7 * s], hand], 7 * s, SKIN_DARK);
        limb([shoulder, [x + 22 * s, cy + side * 7 * s], hand], 5.4 * s, SKIN);
        return;
      }
      const cycle = ((a % TAU) + TAU) % TAU;
      if (cycle < Math.PI) {  // 당기기(물속)
        const f = cycle / Math.PI;
        const hand = [lerp(x + 40 * s, x - 24 * s, f), cy + side * lerp(7, 12, Math.sin(f * Math.PI)) * s];
        const elbow = [(shoulder[0] + hand[0]) / 2, cy + side * (15 + 4 * Math.sin(f * Math.PI)) * s];
        g.save();
        g.globalAlpha *= 0.5;  // 물속이라 흐림
        limb([shoulder, elbow, hand], 6.4 * s, SKIN_DARK);
        limb([shoulder, elbow, hand], 5 * s, SKIN);
        g.restore();
      } else {  // 돌아오기(물 위, 팔꿈치를 높게)
        const f = (cycle - Math.PI) / Math.PI;
        const hand = [lerp(x - 22 * s, x + 40 * s, f), cy + side * (17 - 6 * Math.sin(f * Math.PI)) * s];
        const elbow = [lerp(x - 4 * s, x + 16 * s, f), cy + side * (23 + 3 * Math.sin(f * Math.PI)) * s];
        g.save();
        g.shadowColor = "rgba(0, 40, 70, 0.3)";
        g.shadowBlur = 4 * s;
        g.shadowOffsetY = 3 * s;
        limb([shoulder, elbow, hand], 7.5 * s, SKIN_DARK);
        g.restore();
        limb([shoulder, elbow, hand], 5.8 * s, SKIN);
        g.fillStyle = SKIN;
        g.beginPath();
        g.ellipse(hand[0] + 2 * s, hand[1], 4.6 * s, 3.4 * s, 0, 0, TAU);
        g.fill();
        if (f > 0.82 && swimming) {  // 손이 물에 들어가는 물보라
          g.fillStyle = "rgba(255, 255, 255, 0.95)";
          for (let k = 0; k < 5; k++) {
            const angle = (k / 5) * TAU + stroke;
            g.beginPath();
            g.arc(hand[0] + 6 * s + Math.cos(angle) * 5 * s, hand[1] + Math.sin(angle) * 4 * s, 1.6 * s, 0, TAU);
            g.fill();
          }
        }
      }
    };
    const pulling = (a) => (((a % TAU) + TAU) % TAU) < Math.PI;
    const arms = [[-1, stroke], [1, stroke + Math.PI]];
    for (const [side, a] of arms) if (pulling(a) || pose === "idle" || pose === "dive") arm(side, a);  // 물속 팔 먼저

    // 몸통(등): 둥근 어깨에서 허리로 좁아지고 엉덩이에서 조금 넓어짐. 돌림에 따라 한쪽 어깨가 올라와 밝고 넓게
    const w = (side) => 1 + 0.08 * side * roll;  // 올라온 쪽 어깨가 조금 넓게 보임
    const torso = new Path2D();
    torso.moveTo(sx + 7 * s, cy - 5 * s);  // 목
    torso.quadraticCurveTo(sx + 6 * s, cy - 13 * s * w(-1), sx + 1 * s, cy - 16 * s * w(-1));  // 왼쪽 어깨
    torso.bezierCurveTo(sx - 5 * s, cy - 18 * s * w(-1), x - 14 * s, cy - 12 * s, x - 21 * s, cy - 9.5 * s);  // 겨드랑이, 허리
    torso.bezierCurveTo(x - 27 * s, cy - 9 * s, x - 32 * s, cy - 11 * s, x - 36 * s, cy - 6 * s);  // 엉덩이
    torso.quadraticCurveTo(x - 39 * s, cy, x - 36 * s, cy + 6 * s);
    torso.bezierCurveTo(x - 32 * s, cy + 11 * s, x - 27 * s, cy + 9 * s, x - 21 * s, cy + 9.5 * s);
    torso.bezierCurveTo(x - 14 * s, cy + 12 * s, sx - 5 * s, cy + 18 * s * w(1), sx + 1 * s, cy + 16 * s * w(1));
    torso.quadraticCurveTo(sx + 6 * s, cy + 13 * s * w(1), sx + 7 * s, cy + 5 * s);
    torso.closePath();
    const back = g.createLinearGradient(0, cy - 18 * s, 0, cy + 18 * s);  // 등의 빛(올라온 쪽이 밝음)
    back.addColorStop(0, roll < 0 ? "#fbe0c8" : SKIN_DARK);
    back.addColorStop(0.5, SKIN);
    back.addColorStop(1, roll < 0 ? SKIN_DARK : "#fbe0c8");
    g.save();
    g.shadowColor = "rgba(0, 40, 70, 0.28)";
    g.shadowBlur = 5 * s;
    g.shadowOffsetY = 3 * s;
    g.fillStyle = back;
    g.fill(torso);
    g.restore();
    g.save();
    g.clip(torso);
    const suitShade = g.createLinearGradient(0, cy - 14 * s, 0, cy + 14 * s);  // 수영복(등 가운데부터 엉덩이까지)
    suitShade.addColorStop(0, roll < 0 ? suitLight : suitDark);
    suitShade.addColorStop(0.5, suit);
    suitShade.addColorStop(1, roll < 0 ? suitDark : suitLight);
    g.fillStyle = suitShade;
    g.beginPath();
    g.moveTo(sx - 9 * s, cy - 20 * s);
    g.quadraticCurveTo(sx - 15 * s, cy, sx - 9 * s, cy + 20 * s);
    g.lineTo(x - 45 * s, cy + 20 * s);
    g.lineTo(x - 45 * s, cy - 20 * s);
    g.closePath();
    g.fill();
    g.strokeStyle = suitDark;  // 어깨끈
    g.lineWidth = 2.4 * s;
    for (const side of [-1, 1]) {
      g.beginPath();
      g.moveTo(sx + 2 * s, cy + side * 6 * s);
      g.quadraticCurveTo(sx - 4 * s, cy + side * 8 * s, sx - 10 * s, cy + side * 7 * s);
      g.stroke();
    }
    const sink = g.createLinearGradient(x - 40 * s, 0, x - 22 * s, 0);  // 엉덩이 쪽은 물에 잠겨 물빛으로
    sink.addColorStop(0, water);
    sink.addColorStop(1, "rgba(40, 150, 200, 0)");
    g.fillStyle = sink;
    g.fillRect(x - 42 * s, cy - 20 * s, 22 * s, 40 * s);
    g.restore();
    g.strokeStyle = "rgba(120, 70, 40, 0.45)";
    g.lineWidth = Math.max(1, 1.2 * s);
    g.stroke(torso);

    // 물 위로 돌아오는 팔
    for (const [side, a] of arms) if (!pulling(a) && pose !== "idle" && pose !== "dive") arm(side, a);

    // 도착: 한 팔을 들어 흔듦(위에서 보면 짧아 보이는 팔과 주먹, 둘레 물결)
    if (pose === "cheer") {
      const wave = Math.sin(t * 8) * 3 * s;
      const fist = [sx + 8 * s + wave, cy - 26 * s];
      limb([[sx, cy - 14 * s], fist], 7.5 * s, SKIN_DARK);
      limb([[sx, cy - 14 * s], fist], 5.8 * s, SKIN);
      g.fillStyle = SKIN;
      g.beginPath();
      g.arc(fist[0], fist[1], 5 * s, 0, TAU);
      g.fill();
      g.strokeStyle = "rgba(255, 255, 255, 0.7)";
      g.lineWidth = 1.6 * s;
      g.beginPath();
      g.ellipse(fist[0], fist[1] + 4 * s, 11 * s, 5 * s, 0, 0, TAU);
      g.stroke();
    }

    // 머리 앞 물결(뱃머리 물결)
    if (swimming) {
      g.strokeStyle = "rgba(255, 255, 255, 0.8)";
      g.lineWidth = 2.2 * s;
      g.beginPath();
      g.moveTo(hx + 4 * s, cy - 15 * s);
      g.quadraticCurveTo(hx + 18 * s, cy, hx + 4 * s, cy + 15 * s);
      g.stroke();
    }

    // 머리: 수영모(참가자 색, 윗면 빛), 물안경(끈과 렌즈), 숨 쉴 때 고개를 옆으로
    const breathe = swimming && Math.sin(stroke) > 0.85 ? 4 * s : 0;
    const cap = g.createRadialGradient(hx - 3 * s, cy - 4 * s + breathe, 1 * s, hx, cy + breathe, 13 * s);
    cap.addColorStop(0, suitLight);
    cap.addColorStop(0.45, suit);
    cap.addColorStop(1, suitDark);
    g.fillStyle = cap;
    g.beginPath();
    g.ellipse(hx, cy + breathe, 12.5 * s, 10.5 * s, 0, 0, TAU);
    g.fill();
    g.strokeStyle = suitDark;
    g.lineWidth = Math.max(1, 1.4 * s);
    g.stroke();
    g.strokeStyle = "#20262c";  // 물안경 끈
    g.lineWidth = 2 * s;
    g.beginPath();
    g.ellipse(hx + 1 * s, cy + breathe, 11.5 * s, 10 * s, 0, -0.9, 0.9);
    g.stroke();
    for (const side of [-1, 1]) {  // 렌즈
      g.fillStyle = "#20262c";
      g.beginPath();
      g.ellipse(hx + 10 * s, cy + breathe + side * 4.6 * s, 2.6 * s, 3.4 * s, 0, 0, TAU);
      g.fill();
      g.fillStyle = "rgba(255, 255, 255, 0.85)";
      g.beginPath();
      g.arc(hx + 10.6 * s, cy + breathe + side * 4.6 * s - 1.2 * s, 0.9 * s, 0, TAU);
      g.fill();
    }
    if (L >= 40) {  // 수영모 뒤쪽 번호
      g.fillStyle = mark;
      g.font = `${Math.round(9 * s)}px ${font}`;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText(String(number), hx - 3 * s, cy + breathe + 0.5 * s);
    }
    if (pose === "dive") {  // 공기 방울
      g.fillStyle = "rgba(255, 255, 255, 0.95)";
      for (let k = 0; k < 5; k++) {
        const b = (t * 1.6 + k * 0.23) % 1;
        g.beginPath();
        g.arc(hx - (10 + b * 60) * s, cy - 8 * s + Math.sin(k * 2 + t * 4) * 7 * s, (1.4 + b * 1.8) * s, 0, TAU);
        g.fill();
      }
    }
    if (pose === "limp") {  // 다리 쥐: 종아리 옆 찌릿 표시
      g.strokeStyle = "#ffd84d";
      g.lineWidth = 2 * s;
      g.beginPath();
      g.moveTo(x - 46 * s, cy + 14 * s);
      g.lineTo(x - 42 * s, cy + 19 * s);
      g.lineTo(x - 47 * s, cy + 21 * s);
      g.lineTo(x - 43 * s, cy + 27 * s);
      g.stroke();
    }
    g.restore();
  }

  // 수영장 줄: 물, 줄 사이 부표 줄, 줄 가운데 바닥 선(T자 끝)
  function drawPool(g, P, n, laneY, laneH, x0, x1, finishX) {
    const water = P.design === "metal" ? ["#0f3e5c", "#124a6c"] : P.design === "paper" ? ["#bfe6f5", "#ade0f2"] : ["#3fb6d9", "#37a9cc"];
    for (let i = 0; i < n; i++) {
      const y = laneY(i);
      const grad = g.createLinearGradient(0, y, 0, y + laneH);
      grad.addColorStop(0, water[i % 2]);
      grad.addColorStop(1, water[(i + 1) % 2]);
      g.fillStyle = grad;
      g.fillRect(x0, y, x1 - x0, laneH);
      g.fillStyle = P.design === "metal" ? "rgba(255, 255, 255, 0.12)" : "rgba(15, 50, 80, 0.32)";  // 바닥 선
      const lineH = Math.max(3, laneH * 0.07);
      g.fillRect(x0 + 60, y + laneH / 2 - lineH / 2, finishX - x0 - 100, lineH);
      g.fillRect(finishX - 46, y + laneH * 0.3, lineH, laneH * 0.4);
      g.strokeStyle = "rgba(255, 255, 255, 0.16)";  // 물결 빛
      g.lineWidth = 2;
      for (let k = 0; k < 7; k++) {
        const wx = x0 + 120 + ((k * 263 + i * 97) % (x1 - x0 - 200));
        g.beginPath();
        g.moveTo(wx, y + laneH * 0.25);
        g.quadraticCurveTo(wx + 30, y + laneH * 0.12, wx + 60, y + laneH * 0.25);
        g.stroke();
      }
    }
    const buoy = Math.max(3, Math.min(9, laneH * 0.09));
    for (let i = 0; i <= n; i++) {  // 부표 줄(끝 쪽은 진한 색)
      const y = laneY(i);
      for (let bx = x0 + buoy; bx < x1; bx += buoy * 2.4) {
        const near = bx < x0 + 160 || bx > finishX - 160;
        g.fillStyle = near ? P.accent : bx % (buoy * 4.8) < buoy * 2.4 ? "#ffffff" : P.accentLight;
        g.beginPath();
        g.arc(bx, y, buoy, 0, TAU);
        g.fill();
      }
    }
  }

  function runSim(env) {
    const { heat, P, colors, rng, font } = env;
    const n = heat.names.length;
    const area = n > 8 ? { top: 160, height: 860 } : { top: 136, height: 872 };
    const laneH = Math.min(104, area.height / n);
    const lanesTop = area.top + (area.height - laneH * n) / 2;
    const startX = 400;
    const finishX = 1730;
    const endX = 1835;
    const S = laneH * (n <= 8 ? 0.78 : 0.84);
    const profile = buildProfiles(n, heat.times, rng);
    const events = runEvents(env, profile, n);
    const place = [];
    heat.order.forEach((lane, index) => (place[lane] = index));
    const laneY = (i) => lanesTop + i * laneH;
    const nameSize = clamp(Math.round(laneH * 0.52), 15, 30);
    const swim = env.race.game === "swim";

    function drawStatic(g) {
      panel(g, P, 40, 112, 1840, 940, { seed: 21, screws: true, fill: P.plate, tape: true });
      if (swim) {  // 수영장: 물, 부표 줄, 출발대, 도착 벽
        g.save();
        drawPool(g, P, n, laneY, laneH, startX - 46, endX, finishX);
        g.fillStyle = P.design === "metal" ? "#dfe5ea" : "#fffaf0";
        g.fillRect(startX - 60, laneY(0), 14, laneH * n);
        finishBand(g, finishX, laneY(0) + (laneH * n) / 2, 0, laneH * n, 18);
        g.font = `22px ${font}`;
        g.fillStyle = P.text;
        g.textAlign = "center";
        g.fillText("출발", startX - 53, laneY(0) - 14);
        g.fillText("도착", finishX, laneY(0) - 14);
        g.restore();
        return;
      }
      g.save();
      // 줄
      for (let i = 0; i < n; i++) {
        const y = laneY(i);
        g.fillStyle = i % 2 ? P.laneB : P.laneA;
        g.fillRect(startX - 46, y, endX - startX + 46, laneH);
        if (P.design === "wood") grain(g, startX - 46, y, endX - startX + 46, laneH, P, 300 + i);
      }
      g.strokeStyle = P.design === "metal" ? P.glow : P.design === "paper" ? INK : P.line;
      g.lineWidth = P.design === "paper" ? 2 : 3;
      if (P.design === "paper") g.setLineDash([12, 10]);
      if (P.design === "metal") {
        g.shadowColor = P.glow;
        g.shadowBlur = 8;
        g.globalAlpha = 0.6;
      }
      for (let i = 0; i <= n; i++) {
        const y = laneY(i);
        g.beginPath();
        g.moveTo(startX - 46, y);
        g.lineTo(endX, y);
        g.stroke();
      }
      g.setLineDash([]);
      g.shadowColor = "transparent";
      g.globalAlpha = 1;
      // 거리 표시
      g.strokeStyle = P.design === "metal" ? "rgba(255, 255, 255, 0.18)" : "rgba(30, 35, 39, 0.16)";
      g.lineWidth = 2;
      for (let k = 1; k < 4; k++) {
        const x = lerp(startX, finishX, k / 4);
        g.setLineDash([6, 10]);
        g.beginPath();
        g.moveTo(x, laneY(0));
        g.lineTo(x, laneY(n));
        g.stroke();
      }
      g.setLineDash([]);
      // 출발선, 결승선
      g.fillStyle = P.design === "metal" ? "#dfe5ea" : P.design === "paper" ? INK : "#fffaf0";
      g.fillRect(startX - 3, laneY(0), 6, laneH * n);
      finishBand(g, finishX, laneY(0) + (laneH * n) / 2, 0, laneH * n, 18);
      g.font = `22px ${font}`;
      g.fillStyle = P.text;
      g.textAlign = "center";
      g.fillText("출발", startX, laneY(0) - 14);
      g.fillText("결승", finishX, laneY(0) - 14);
      g.restore();
    }

    function draw(g, t) {
      const medals = MEDALS(P);
      for (let i = 0; i < n; i++) {
        const y = laneY(i);
        const T = profile.times[i];
        const p = progressOf(profile, i, t);
        let x = lerp(startX - S * 0.35, finishX, p);
        let pose = t <= 0 ? "idle" : "run";
        const distance = p * (finishX - startX);
        let phase = distance / (S * 0.55);
        if (t >= T) {
          const u = (t - T) / 1.6;
          x = finishX + 50 * easeOut(u);
          phase = (finishX - startX) / (S * 0.55) + easeOut(u) * 6;
          pose = u >= 1 ? (place[i] === 0 || (env.race.rank === "last" && heat.final && place[i] === n - 1) ? "cheer" : "idle") : "run";
        } else {
          for (const event of events) {
            if (event.targets[0] !== i || t < event.t || t > event.t + event.dur) continue;
            pose = { sprint: "sprint", stumble: "fallen", cramp: "limp", dive: "dive", wave: "wave" }[event.kind] || pose;
          }
        }
        // 줄 이름 칸
        const labelX = 64;
        const cy = y + laneH / 2;
        const badge = Math.min(laneH * 0.36, 22);
        const done = t >= T;
        const medal = done && place[i] < 3 ? medals[place[i]] : null;
        g.save();
        g.fillStyle = medal || (done ? P.accent : P.design === "metal" ? "#3a434c" : P.design === "paper" ? "#ffffff" : "#f8ecd6");
        g.beginPath();
        g.arc(labelX + badge, cy, badge, 0, TAU);
        g.fill();
        g.strokeStyle = P.design === "metal" ? "rgba(255, 255, 255, 0.45)" : INK;
        g.lineWidth = 2;
        g.stroke();
        g.fillStyle = medal ? INK : done ? P.onAccent : P.design === "metal" ? "#ffffff" : INK;
        g.font = `${Math.round(badge * 1.1)}px ${font}`;
        g.textAlign = "center";
        g.textBaseline = "middle";
        g.fillText(String(done ? place[i] + 1 : i + 1), labelX + badge, cy + 1);
        g.textAlign = "left";
        g.font = `${nameSize}px ${font}`;
        g.fillStyle = P.text;
        const nameX = labelX + badge * 2 + 12;
        const timeW = done && laneH >= 26 ? 82 : 0;
        g.fillText(fitText(g, heat.names[i], startX - 60 - nameX - timeW), nameX, cy + 1);
        if (timeW) {
          g.textAlign = "right";
          g.font = `700 ${clamp(Math.round(laneH * 0.26), 12, 20)}px ${UI}`;
          g.fillStyle = P.sub;
          g.fillText(`${T.toFixed(2)}초`, startX - 52, cy + 1);
        }
        g.restore();
        if (heat.advance.includes(i) && t >= heat.end + 0.3) {
          g.save();
          g.fillStyle = P.accent;
          g.globalAlpha = 0.18;
          g.fillRect(startX - 46, y, endX - startX + 46, laneH);
          g.restore();
        }
        if (swim) drawSwimmer(g, P, x, y + laneH / 2, laneH, colors[i], phase, pose, t, i + 1, font);
        else drawRunner(g, P, x, y + laneH * 0.9, S, colors[i], phase, pose, t, i + 1, font);
      }
      // 도착 순위(결승선 옆)
      for (let i = 0; i < n; i++) {
        if (t < profile.times[i] || laneH < 26) continue;
        const y = laneY(i) + laneH / 2;
        const medal = place[i] < 3 ? medals[place[i]] : null;
        const size = Math.min(laneH * 0.32, 20);
        g.save();
        g.globalAlpha = smooth((t - profile.times[i]) / 0.25);
        g.fillStyle = medal || (P.design === "metal" ? "#3a434c" : "#ffffff");
        g.beginPath();
        g.arc(finishX + 106, y - laneH * 0.12, size, 0, TAU);
        g.fill();
        g.strokeStyle = P.design === "metal" ? "rgba(255, 255, 255, 0.5)" : INK;
        g.lineWidth = 2;
        g.stroke();
        g.fillStyle = medal ? INK : P.text;
        g.font = `${Math.round(size * 1.15)}px ${font}`;
        g.textAlign = "center";
        g.textBaseline = "middle";
        g.fillText(String(place[i] + 1), finishX + 106, y - laneH * 0.12 + 1);
        g.restore();
      }
    }

    return { drawStatic, draw, shake: () => [0, 0], events, end: heat.end, finishes: heat.order.map((lane) => profile.times[lane]), tick: swim ? "splash" : "step" };
  }

  // ---------------------------------------------------------------- 서바이벌: 원형 경기장, 좁아지는 구역, 말랑이
  function drawBlob(g, P, x, y, R, color, t, i, options = {}) {
    const squish = 1 + 0.06 * Math.sin(t * 6 + i * 1.7);
    const scale = options.scale || 1;
    const rx = R * squish * scale;
    const ry = (R / squish) * 0.92 * scale;
    g.save();
    if (options.alpha !== undefined) g.globalAlpha = options.alpha;
    g.fillStyle = P.design === "metal" ? "rgba(0, 0, 0, 0.45)" : "rgba(40, 25, 10, 0.22)";
    g.beginPath();
    g.ellipse(x + 2, y + ry * 0.85, rx * 0.9, ry * 0.28, 0, 0, TAU);
    g.fill();
    const outline = P.design === "metal" ? "rgba(255, 255, 255, 0.7)" : INK;
    g.lineWidth = Math.max(1.5, R * 0.08);
    g.strokeStyle = outline;
    g.fillStyle = options.gray ? "#9aa3ab" : color.fill;
    for (const side of [-1, 1]) {
      g.beginPath();
      g.moveTo(x + side * rx * 0.7, y - ry * 0.45);
      g.lineTo(x + side * rx * 0.62, y - ry * 1.12);
      g.lineTo(x + side * rx * 0.12, y - ry * 0.78);
      g.closePath();
      g.fill();
      g.stroke();
    }
    const shade = g.createRadialGradient(x - rx * 0.3, y - ry * 0.4, R * 0.1, x, y, R * 1.1 * scale);
    shade.addColorStop(0, options.gray ? "#c6ccd1" : P.design === "paper" ? color.fill : color.light);
    shade.addColorStop(0.6, options.gray ? "#9aa3ab" : color.fill);
    shade.addColorStop(1, options.gray ? "#6d767e" : P.design === "paper" ? color.fill : color.dark);
    g.fillStyle = shade;
    g.beginPath();
    g.ellipse(x, y, rx, ry, 0, 0, TAU);
    g.fill();
    g.stroke();
    if (P.design !== "paper") {
      g.fillStyle = "rgba(255, 255, 255, 0.45)";
      g.beginPath();
      g.ellipse(x - rx * 0.38, y - ry * 0.45, rx * 0.22, ry * 0.13, -0.5, 0, TAU);
      g.fill();
    }
    const look = options.look || 0;
    g.fillStyle = "#ffffff";
    g.beginPath();
    g.ellipse(x - rx * 0.24 + look * rx * 0.1, y - ry * 0.05, R * 0.17, R * 0.21, 0, 0, TAU);
    g.ellipse(x + rx * 0.24 + look * rx * 0.1, y - ry * 0.05, R * 0.17, R * 0.21, 0, 0, TAU);
    g.fill();
    g.fillStyle = INK;
    g.beginPath();
    g.arc(x - rx * 0.24 + look * rx * 0.16, y - ry * 0.02, R * 0.09, 0, TAU);
    g.arc(x + rx * 0.24 + look * rx * 0.16, y - ry * 0.02, R * 0.09, 0, TAU);
    g.fill();
    if (options.glyph && R >= 15) {
      g.fillStyle = color.text;
      g.font = `${Math.round(R * 0.6)}px ${options.font}`;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText(options.glyph, x, y + ry * 0.45);
    }
    g.restore();
  }

  // 말랑이 그림을 미리 그려 두고(2배 해상도) 매 장면에는 늘이고 줄이기만 한다(100명도 매끄럽게)
  function blobDrawer(P, R, font) {
    const cache = new Map();
    const w = Math.ceil(R * 2.5 + 8);
    const h = Math.ceil(R * 2.6 + 8);
    const cx = w / 2;
    const cy = h / 2;
    return (g, x, y, color, t, i, options = {}) => {
      const key = `${i}:${options.gray ? 1 : 0}`;
      let sprite = cache.get(key);
      if (!sprite) {
        sprite = document.createElement("canvas");
        sprite.width = w * 2;
        sprite.height = h * 2;
        const s = sprite.getContext("2d");
        s.scale(2, 2);
        drawBlob(s, P, cx, cy, R, color, 0, 0, { gray: options.gray, glyph: options.glyph, font, look: 0.45 });
        cache.set(key, sprite);
      }
      const squish = 1 + 0.06 * Math.sin(t * 6 + i * 1.7);
      const scale = options.scale || 1;
      const sx = squish * scale;
      const sy = scale / squish;
      if (options.alpha !== undefined) g.globalAlpha = clamp(options.alpha, 0, 1);
      g.drawImage(sprite, x - cx * sx, y - cy * sy, w * sx, h * sy);
      if (options.alpha !== undefined) g.globalAlpha = 1;
    };
  }

  function survivalSim(env) {
    const { heat, P, colors, rng, font } = env;
    const n = heat.names.length;
    const end = heat.end;
    const C = [744, 584];
    const R0 = 420;
    const br = n <= 12 ? 30 : n <= 30 ? 24 : n <= 60 ? 18 : 15;
    const blob = blobDrawer(P, br, font);
    const on = new Set(env.events);
    const zoneOn = on.has("zone");
    const E = heat.times.slice();
    const winner = heat.order[0];
    const place = [];
    heat.order.forEach((lane, index) => (place[lane] = index));
    const phases = zoneOn ? [[0.18, 0.3, 1, 0.8], [0.45, 0.56, 0.8, 0.6], [0.7, 0.8, 0.6, 0.4]] : [];
    const radius = (t) => {
      let value = 1;
      for (const [a, b, from, to] of phases) {
        if (t >= end * b) value = to;
        else if (t > end * a) value = lerp(from, to, smooth((t / end - a) / (b - a)));
      }
      return R0 * value;
    };
    const wander = heat.names.map(() => ({
      a0: between(rng, 0, TAU), wa: between(rng, 0.6, 1.6), fa: between(rng, 0.15, 0.45), pa: between(rng, 0, TAU), drift: between(rng, -0.22, 0.22),
      rb: Math.sqrt(between(rng, 0.05, 0.9)), ra: between(rng, 0.08, 0.25), fr: between(rng, 0.2, 0.6), pr: between(rng, 0, TAU),
    }));
    const base = (i, t) => {
      const w = wander[i];
      const angle = w.a0 + w.wa * Math.sin(w.fa * t + w.pa) + w.drift * t;
      const rad = clamp(w.rb + w.ra * Math.sin(w.fr * t + w.pr), 0.04, 0.96);
      const room = Math.max(0, radius(t) - br - 8);
      return [C[0] + Math.cos(angle) * rad * room, C[1] + Math.sin(angle) * rad * room];
    };
    // 깜짝 요소(회복, 보호막, 힘, 가시 함정)와 탈락 원인
    const events = [];
    const kinds = env.events.filter((kind) => kind !== "zone");
    const alive = (t) => heat.names.map((_, i) => i).filter((i) => E[i] > t);
    const cause = new Array(n).fill("hit");
    const target = new Array(n).fill(null);
    const attacker = new Array(n).fill(-1);
    if (kinds.length) {
      for (const t of eventSlots(rng, env.level, end, 0.08, 0.72)) {
        const kind = pickOne(rng, kinds);
        const need = { heal: 2, shield: 4.5, power: 3.5, spikes: 0 }[kind];
        const pool = alive(t + need).filter((i) => i !== winner || kind !== "spikes");
        if (!pool.length) continue;
        const event = { kind, t, dur: { heal: 1.8, shield: 4, power: 3, spikes: 6 }[kind], targets: [], text: "", sound: "shine", seed: Math.floor(rng() * 1e9) };
        if (kind === "spikes") {
          const angle = between(rng, 0, TAU);
          const rad = between(rng, 0.15, 0.55) * radius(t);
          event.point = [C[0] + Math.cos(angle) * rad, C[1] + Math.sin(angle) * rad];
          const victims = alive(t + 1.4).filter((i) => i !== winner && E[i] <= t + event.dur && cause[i] === "hit").slice(0, 2);
          for (const victim of victims) {
            cause[victim] = "spikes";
            target[victim] = event.point;
          }
          event.text = "가시 함정 등장";
          event.sound = "slow";
        } else {
          const lane = pickOne(rng, pool);
          event.targets = [lane];
          event.text = `${heat.names[lane]} ${{ heal: "회복", shield: "보호막", power: "힘 키우기" }[kind]}`;
          event.sound = kind === "power" ? "boost" : "shine";
        }
        events.push(event);
      }
    }
    for (const [a] of phases) events.push({ kind: "zone", t: end * a, dur: end * 0.1, targets: [], text: "구역이 좁아집니다", sound: "rumble" });
    events.sort((a, b) => a.t - b.t);
    for (let i = 0; i < n; i++) {
      if (i === winner || cause[i] !== "hit") continue;
      if (zoneOn && E[i] > end * 0.2 && rng() < 0.35) {
        cause[i] = "zone";
        const [bx, by] = base(i, E[i]);
        const angle = Math.atan2(by - C[1], bx - C[0]);
        target[i] = [C[0] + Math.cos(angle) * (radius(E[i]) + br * 1.3), C[1] + Math.sin(angle) * (radius(E[i]) + br * 1.3)];
        continue;
      }
      const [vx, vy] = base(i, E[i] - 0.9);
      let best = -1;
      let bestDistance = Infinity;
      for (let j = 0; j < n; j++) {
        if (j === i || E[j] <= E[i]) continue;
        const [ox, oy] = base(j, E[i] - 0.9);
        const distance = Math.hypot(ox - vx, oy - vy);
        if (distance < bestDistance) {
          bestDistance = distance;
          best = j;
        }
      }
      attacker[i] = best;
      const [ax, ay] = base(best, E[i]);
      const [bx, by] = base(i, E[i]);
      const gap = Math.hypot(bx - ax, by - ay) || 1;
      target[i] = [ax + ((bx - ax) / gap) * br * 1.7, ay + ((by - ay) / gap) * br * 1.7];
    }
    const attacks = heat.names.map(() => []);
    attacker.forEach((who, victim) => {
      if (who >= 0) attacks[who].push(victim);
    });
    const CAUSES = { hit: "부딪힘", zone: "구역 밖", spikes: "가시 함정" };
    const X = new Float32Array(n);
    const Y = new Float32Array(n);
    const LOCK = new Uint8Array(n);

    function positions(t) {
      for (let i = 0; i < n; i++) {
        let [x, y] = base(i, Math.max(0, t));
        LOCK[i] = 0;
        if (t > E[i] - 1.1 && target[i]) {
          const v = smooth((t - (E[i] - 1.1)) / 1.1);
          x = lerp(x, target[i][0], v);
          y = lerp(y, target[i][1], v);
          LOCK[i] = 1;
        }
        for (const victim of attacks[i]) {
          const s = t - E[victim];
          if (s < -0.55 || s > 0.4) continue;
          const amount = s < 0 ? smooth((s + 0.55) / 0.55) * 0.5 : (1 - smooth(s / 0.4)) * 0.5;
          x = lerp(x, target[victim][0], amount);
          y = lerp(y, target[victim][1], amount);
          LOCK[i] = 1;
        }
        X[i] = x;
        Y[i] = y;
      }
      const room = radius(t) - br - 6;
      for (let pass = 0; pass < 2; pass++) {
        for (let i = 0; i < n; i++) {
          if (E[i] <= t || LOCK[i]) continue;
          for (let j = i + 1; j < n; j++) {
            if (E[j] <= t || LOCK[j]) continue;
            const dx = X[j] - X[i];
            const dy = Y[j] - Y[i];
            const distance = Math.hypot(dx, dy);
            const need = br * 1.85;
            if (distance >= need || distance < 0.01) continue;
            const push = (need - distance) / 2;
            X[i] -= (dx / distance) * push;
            Y[i] -= (dy / distance) * push;
            X[j] += (dx / distance) * push;
            Y[j] += (dy / distance) * push;
          }
          const dx = X[i] - C[0];
          const dy = Y[i] - C[1];
          const distance = Math.hypot(dx, dy);
          if (distance > room && distance > 0) {
            X[i] = C[0] + (dx / distance) * room;
            Y[i] = C[1] + (dy / distance) * room;
          }
        }
      }
    }

    function drawStatic(g) {
      panel(g, P, 40, 112, 1410, 940, { seed: 31, screws: true, fill: P.plate, tape: true });
      g.save();
      // 경기장 바닥
      if (P.design !== "metal") {
        g.fillStyle = P.shadow;
        g.beginPath();
        g.arc(C[0] + (P.design === "paper" ? 9 : 6), C[1] + (P.design === "paper" ? 9 : 9), R0 + 16, 0, TAU);
        g.fill();
      }
      g.fillStyle = P.design === "metal" ? "#3b444c" : P.design === "paper" ? INK : P.frame;
      g.beginPath();
      g.arc(C[0], C[1], R0 + 16, 0, TAU);
      g.fill();
      const floor = g.createRadialGradient(C[0], C[1] - 80, 40, C[0], C[1], R0);
      floor.addColorStop(0, P.design === "metal" ? "#36404a" : P.design === "paper" ? "#fffdf8" : "#f6e3c0");
      floor.addColorStop(1, P.design === "metal" ? "#232a31" : P.design === "paper" ? P.accentSoft : "#e2bf8c");
      g.fillStyle = floor;
      g.beginPath();
      g.arc(C[0], C[1], R0, 0, TAU);
      g.fill();
      g.save();
      g.beginPath();
      g.arc(C[0], C[1], R0, 0, TAU);
      g.clip();
      grain(g, C[0] - R0, C[1] - R0, R0 * 2, R0 * 2, P, 77);
      g.strokeStyle = P.design === "metal" ? "rgba(255, 255, 255, 0.08)" : "rgba(30, 35, 39, 0.1)";
      g.lineWidth = 2;
      for (const k of [0.25, 0.5, 0.75]) {
        g.beginPath();
        g.arc(C[0], C[1], R0 * k, 0, TAU);
        g.stroke();
      }
      g.beginPath();
      g.moveTo(C[0] - R0, C[1]);
      g.lineTo(C[0] + R0, C[1]);
      g.moveTo(C[0], C[1] - R0);
      g.lineTo(C[0], C[1] + R0);
      g.stroke();
      g.restore();
      if (P.design === "metal") {
        g.strokeStyle = P.glow;
        g.lineWidth = 3;
        g.shadowColor = P.glow;
        g.shadowBlur = 16;
        g.beginPath();
        g.arc(C[0], C[1], R0 + 2, 0, TAU);
        g.stroke();
        g.shadowColor = "transparent";
        for (let k = 0; k < 24; k++) screw(g, C[0] + Math.cos((k * TAU) / 24) * (R0 + 9), C[1] + Math.sin((k * TAU) / 24) * (R0 + 9), 3, P);
      } else if (P.design === "wood") {
        for (let k = 0; k < 16; k++) screw(g, C[0] + Math.cos((k * TAU) / 16) * (R0 + 8), C[1] + Math.sin((k * TAU) / 16) * (R0 + 8), 3.5, P);
      }
      g.restore();
      panel(g, P, 1470, 112, 410, 940, { seed: 32, fill: P.panel });
      g.save();
      g.font = `30px ${font}`;
      g.fillStyle = P.text;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText("생존", 1675, 158);
      g.restore();
    }

    function draw(g, t) {
      positions(t);
      const zone = radius(t);
      // 구역 밖(위험 지역)
      if (zone < R0 - 1) {
        g.save();
        g.beginPath();
        g.arc(C[0], C[1], R0, 0, TAU);
        g.arc(C[0], C[1], zone, 0, TAU, true);
        g.fillStyle = "rgba(229, 72, 77, 0.22)";
        g.fill();
        g.clip();
        g.strokeStyle = "rgba(229, 72, 77, 0.35)";
        g.lineWidth = 6;
        for (let k = -R0 * 2; k < R0 * 2; k += 26) {
          g.beginPath();
          g.moveTo(C[0] + k, C[1] - R0);
          g.lineTo(C[0] + k + R0 * 2, C[1] + R0);
          g.stroke();
        }
        g.restore();
      }
      if (zoneOn) {
        g.save();
        g.strokeStyle = zone < R0 - 1 ? "#e5484d" : P.accent;
        g.lineWidth = 4;
        g.setLineDash([16, 12]);
        g.lineDashOffset = -t * 30;
        g.beginPath();
        g.arc(C[0], C[1], zone, 0, TAU);
        g.stroke();
        g.restore();
      }
      // 가시 함정
      for (const event of events) {
        if (event.kind !== "spikes" || t < event.t - 0.6 || t > event.t + event.dur) continue;
        const appear = smooth((t - event.t + 0.6) / 0.6) * (1 - smooth((t - event.t - event.dur + 0.5) / 0.5));
        const [px, py] = event.point;
        g.save();
        g.globalAlpha = appear;
        g.fillStyle = "rgba(229, 72, 77, 0.2)";
        g.beginPath();
        g.arc(px, py, br * 1.6, 0, TAU);
        g.fill();
        for (let k = 0; k < 7; k++) {
          const angle = (k * TAU) / 7;
          const sx = px + Math.cos(angle) * br * 0.9;
          const sy = py + Math.sin(angle) * br * 0.9;
          g.fillStyle = P.design === "metal" ? "#cfd6dc" : "#59626a";
          g.beginPath();
          g.moveTo(sx - 7, sy + 6);
          g.lineTo(sx, sy - 12 * appear);
          g.lineTo(sx + 7, sy + 6);
          g.closePath();
          g.fill();
          g.strokeStyle = INK;
          g.lineWidth = 1.5;
          g.stroke();
        }
        g.restore();
      }
      // 말랑이
      const order = heat.names.map((_, i) => i).filter((i) => E[i] > t - 0.6).sort((a, b) => Y[a] - Y[b]);
      const survivors = heat.names.map((_, i) => i).filter((i) => E[i] > t || i === winner);
      for (const i of order) {
        const since = t - E[i];
        if (since >= 0 && i !== winner) {  // 탈락: 터지며 사라짐
          const u = since / 0.6;
          blob(g, X[i], Y[i], colors[i], t, i, { scale: 1 + u * 0.5, alpha: 1 - u, gray: cause[i] === "zone", glyph: glyphOf(heat.names[i]) });
          const sparks = mulberry32(hashOf("pop", i));
          for (let k = 0; k < 9; k++) {
            const angle = sparks() * TAU;
            const distance = br * (1 + u * 2.4) * (0.7 + sparks() * 0.6);
            g.fillStyle = k % 2 ? colors[i].fill : P.gold;
            g.globalAlpha = 1 - u;
            g.beginPath();
            g.arc(X[i] + Math.cos(angle) * distance, Y[i] + Math.sin(angle) * distance, br * 0.16 * (1 - u * 0.5), 0, TAU);
            g.fill();
            g.globalAlpha = 1;
          }
          continue;
        }
        let scale = 1;
        for (const event of events) {
          if (event.targets[0] !== i || t < event.t || t > event.t + event.dur) continue;
          if (event.kind === "power") scale = 1 + 0.35 * window01(t, event.t, event.dur, 0.2);
        }
        const won = t >= end && i === winner;
        const hop = won ? -Math.abs(Math.sin(t * 6)) * br * 0.5 : 0;
        blob(g, X[i], Y[i] + hop, colors[i], t, i, { scale: won ? 1.6 : scale, glyph: glyphOf(heat.names[i]) });
        for (const event of events) {
          if (event.targets[0] !== i || t < event.t || t > event.t + event.dur) continue;
          const amount = window01(t, event.t, event.dur, 0.15);
          g.save();
          g.globalAlpha = amount;
          if (event.kind === "shield") {
            g.strokeStyle = "#7cc6f2";
            g.fillStyle = "rgba(124, 198, 242, 0.18)";
            g.lineWidth = 3;
            g.beginPath();
            g.arc(X[i], Y[i], br * scale * 1.45, 0, TAU);
            g.fill();
            g.stroke();
          } else if (event.kind === "heal") {
            g.fillStyle = "#3ccf7a";
            g.font = `${Math.round(br * 0.8)}px ${DISPLAY}`;
            g.textAlign = "center";
            for (let k = 0; k < 3; k++) {
              const rise = ((t - event.t) * 40 + k * 14) % 42;
              g.fillText("+", X[i] - br * 0.8 + k * br * 0.8, Y[i] - br - rise);
            }
          } else if (event.kind === "power") {
            g.fillStyle = P.gold;
            star(g, X[i], Y[i] - br * scale * 1.35, br * 0.4);
            g.fill();
            g.strokeStyle = INK;
            g.lineWidth = 1.5;
            g.stroke();
          }
          g.restore();
        }
        if (won) {  // 왕관
          const cx = X[i];
          const cy = Y[i] + hop - br * 1.6 * 1.1;
          g.save();
          g.fillStyle = P.gold;
          g.strokeStyle = INK;
          g.lineWidth = 2;
          g.beginPath();
          g.moveTo(cx - br * 0.7, cy + br * 0.3);
          g.lineTo(cx - br * 0.8, cy - br * 0.35);
          g.lineTo(cx - br * 0.35, cy);
          g.lineTo(cx, cy - br * 0.5);
          g.lineTo(cx + br * 0.35, cy);
          g.lineTo(cx + br * 0.8, cy - br * 0.35);
          g.lineTo(cx + br * 0.7, cy + br * 0.3);
          g.closePath();
          g.fill();
          g.stroke();
          g.restore();
        }
      }
      // 부딪힘 표시
      for (let i = 0; i < n; i++) {
        const since = t - E[i];
        if (i === winner || since < 0 || since > 0.35 || cause[i] !== "hit") continue;
        g.save();
        g.globalAlpha = 1 - since / 0.35;
        g.fillStyle = "#ffffff";
        star(g, X[i], Y[i], br * (1 + since * 3), 8, 0.5);
        g.fill();
        g.strokeStyle = INK;
        g.lineWidth = 2;
        g.stroke();
        g.restore();
      }
      // 이름: 24명 이하이거나 남은 인원 12명 이하
      if (n <= 24 || survivors.length <= 12) {
        const placed = [];
        const tagged = survivors.filter((i) => E[i] > t || i === winner).sort((a, b) => Y[b] - Y[a]);
        for (const i of tagged) {
          nameTag(g, P, heat.names[i], X[i], Y[i] - br * (t >= end && i === winner ? 2.9 : 1.25), n <= 12 || survivors.length <= 6 ? 18 : 15,
                  t >= end && i === winner ? P.gold : null, placed);
        }
      }
      // 떠오르는 탈락 이름(겹치면 위로 쌓음)
      const floating = [];
      for (let i = 0; i < n; i++) {
        const since = t - E[i];
        if (i === winner || since < 0 || since > 1.4) continue;
        g.save();
        g.globalAlpha = 1 - smooth((since - 0.9) / 0.5);
        const size = n <= 30 ? 22 : 18;
        g.font = `${size}px ${font}`;
        g.textAlign = "center";
        const text = `${fitText(g, heat.names[i], 200)} 탈락`;
        const half = g.measureText(text).width / 2 + 4;
        const x = target[i] ? target[i][0] : X[i];
        let y = Y[i] - br - 12 - since * 40;
        for (let tries = 0; tries < 5; tries++) {
          const hit = floating.find((box) => x - half < box[2] && x + half > box[0] && y - size < box[3] && y > box[1]);
          if (!hit) break;
          y = hit[1] - 3;
        }
        floating.push([x - half, y - size, x + half, y]);
        outlined(g, text, x, y, "#ffffff", P.design === "paper" ? INK : "rgba(20, 24, 28, 0.9)", 5);
        g.restore();
      }
      // 오른쪽: 생존 인원, 탈락 기록
      g.save();
      const left = survivors.filter((i) => E[i] > t || (i === winner)).length;
      g.textBaseline = "alphabetic";
      g.textAlign = "left";
      g.font = `86px ${font}`;
      const bigW = g.measureText(String(left)).width;
      g.font = `30px ${font}`;
      const rest = ` / ${n}명`;
      const restW = g.measureText(rest).width;
      const startX = 1675 - (bigW + restW) / 2;
      g.font = `86px ${font}`;
      if (P.design === "paper") outlined(g, String(left), startX, 282, P.accent, INK, 6);
      else {
        g.fillStyle = P.design === "metal" ? P.glow : P.accent;
        g.fillText(String(left), startX, 282);
      }
      g.font = `30px ${font}`;
      g.fillStyle = P.sub;
      g.fillText(rest, startX + bigW, 280);
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.font = `700 20px ${UI}`;
      g.fillStyle = P.sub;
      g.fillText("탈락 기록", 1675, 330);
      g.strokeStyle = P.design === "metal" ? "rgba(255, 255, 255, 0.15)" : "rgba(30, 35, 39, 0.18)";
      g.lineWidth = 2;
      g.beginPath();
      g.moveTo(1500, 348);
      g.lineTo(1850, 348);
      g.stroke();
      const out = heat.names.map((_, i) => i).filter((i) => i !== winner && E[i] <= t).sort((a, b) => E[b] - E[a]).slice(0, 11);
      out.forEach((i, row) => {
        const y = 382 + row * 56;
        g.globalAlpha = row === 0 ? smooth((t - E[i]) / 0.3) : 1;
        g.fillStyle = colors[i].fill;
        g.beginPath();
        g.arc(1512, y, 10, 0, TAU);
        g.fill();
        g.strokeStyle = P.design === "metal" ? "rgba(255,255,255,0.5)" : INK;
        g.lineWidth = 1.5;
        g.stroke();
        g.textAlign = "left";
        g.font = `24px ${font}`;
        g.fillStyle = P.text;
        g.fillText(fitText(g, heat.names[i], 190), 1534, y);
        g.textAlign = "right";
        g.font = `700 18px ${UI}`;
        g.fillStyle = P.sub;
        g.fillText(`${place[i] + 1}위, ${CAUSES[cause[i]]}`, 1858, y);
        g.globalAlpha = 1;
      });
      g.restore();
    }

    const finishes = heat.order.slice(1).map((lane) => E[lane]);
    return { drawStatic, draw, shake: () => [0, 0], events, end, finishes, pops: finishes, tick: null };
  }

  // ---------------------------------------------------------------- 제목 띠, 출발 숫자, 안내 띠, 결과 카드
  function drawTitle(g, env) {
    const { race, heat, index, P, font } = env;
    panel(g, P, 40, 20, 1840, 80, { radius: P.design === "paper" ? 5 : 16, inset: P.design === "wood" ? 8 : 6, seed: 3, plain: true });
    g.save();
    g.font = `36px ${font}`;
    const label = race.game_label;
    const pillW = g.measureText(label).width + 46;
    pill(g, P, 64, 35, pillW, 50, P.accent, label, P.onAccent, `36px ${font}`);
    const goal = race.rank === "last" ? "꼴찌가 당첨" : race.rank === "custom" ? `${race.winner.place}등이 당첨` : "1등이 우승";
    const parts = [race.course_label, heat.label, race.heats.length > 1 ? `${index + 1}/${race.heats.length}경기` : "", goal].filter(Boolean);
    g.font = `700 27px ${UI}`;
    g.fillStyle = P.text;
    g.textBaseline = "middle";
    g.textAlign = "left";
    let cursor = 64 + pillW + 24;
    parts.forEach((part, k) => {  // 항목 사이는 작은 점(글자 대신 도형)
      if (k) {
        g.beginPath();
        g.arc(cursor + 14, 62, 3.5, 0, TAU);
        g.fill();
        cursor += 28;
      }
      g.fillText(part, cursor, 61);
      cursor += g.measureText(part).width;
    });
    g.textAlign = "right";
    g.font = `30px ${font}`;
    g.fillText(`참가 ${race.count}명`, 1850, 61);
    const people = g.measureText(`참가 ${race.count}명`).width;
    g.font = `700 19px ${UI}`;
    g.fillStyle = P.sub;
    const seed = `시드 ${race.seed}`;
    g.fillText(seed, 1850 - people - 22, 63);
    if (race.practice) {
      const seedW = g.measureText(seed).width;
      pill(g, P, 1850 - people - 22 - seedW - 16 - 62, 44, 62, 34, P.gold, "연습", INK, `22px ${font}`);
    }
    g.restore();
  }
  function drawCountdown(g, cur, t) {
    const remain = -t / cur.speed;
    if (remain > 0 && remain <= cur.countdown + 0.05) {
      const number = Math.ceil(remain);
      const u = 1 - (remain - Math.floor(remain));
      g.save();
      g.translate(W / 2 - (LANE_GAMES.includes(cur.race.game) ? 0 : 235), H / 2 + 20);
      g.scale(1 + 0.15 * (1 - u), 1 + 0.15 * (1 - u));
      g.fillStyle = cur.env.P.design === "paper" ? "#fffdf8" : "rgba(20, 24, 28, 0.86)";
      g.beginPath();
      g.arc(0, 0, 110, 0, TAU);
      g.fill();
      g.strokeStyle = cur.env.P.accent;
      g.lineWidth = 10;
      g.beginPath();
      g.arc(0, 0, 100, -Math.PI / 2, -Math.PI / 2 + TAU * u);
      g.stroke();
      if (cur.env.P.design === "paper") {
        g.strokeStyle = INK;
        g.lineWidth = 3;
        g.beginPath();
        g.arc(0, 0, 110, 0, TAU);
        g.stroke();
      }
      g.fillStyle = cur.env.P.design === "paper" ? INK : "#ffffff";
      g.font = `120px ${cur.env.font}`;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText(String(number), 0, 8);
      g.restore();
    } else if (t >= 0 && t < 0.9 * cur.speed) {
      const u = t / (0.9 * cur.speed);
      g.save();
      g.globalAlpha = 1 - smooth((u - 0.6) / 0.4);
      g.translate(W / 2 - (LANE_GAMES.includes(cur.race.game) ? 0 : 235), H / 2 + 20);
      g.scale(1 + u * 0.3, 1 + u * 0.3);
      g.font = `150px ${cur.env.font}`;
      g.textAlign = "center";
      g.textBaseline = "middle";
      outlined(g, "출발!", 0, 0, cur.env.P.accent, cur.env.P.design === "metal" ? "#ffffff" : INK, 10);
      g.restore();
    }
  }
  function drawBanners(g, cur, t) {
    const live = cur.sim.events.filter((event) => event.text && t >= event.t && t < event.t + 2.6);
    live.slice(-2).forEach((event, index) => {
      const u = t - event.t;
      const alpha = smooth(u / 0.2) * (1 - smooth((u - 2.2) / 0.4));
      const P = cur.env.P;
      g.save();
      g.globalAlpha = alpha;
      g.font = `30px ${cur.env.font}`;
      const text = fitText(g, event.text, 980);
      const w = g.measureText(text).width + 60;
      const x = (LANE_GAMES.includes(cur.race.game) ? W / 2 : 745) - w / 2;
      const y = 126 + index * 62 - (1 - smooth(u / 0.2)) * 14;
      if (P.design === "paper") {
        g.fillStyle = INK;
        g.fillRect(x + 5, y + 5, w, 52);
        g.fillStyle = P.gold;
        g.fillRect(x, y, w, 52);
        g.strokeStyle = INK;
        g.lineWidth = 3;
        g.strokeRect(x, y, w, 52);
      } else {
        g.fillStyle = P.design === "metal" ? "rgba(20, 24, 28, 0.92)" : P.gold;
        roundRect(g, x, y, w, 52, 26);
        g.fill();
        g.strokeStyle = P.design === "metal" ? P.gold : INK;
        g.lineWidth = 3;
        g.stroke();
      }
      g.fillStyle = P.design === "metal" ? P.gold : INK;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText(text, x + w / 2, y + 28);
      g.restore();
    });
  }
  function drawConfetti(g, cur, since) {
    if (since < 0 || since > 6) return;
    const P = cur.env.P;
    const pieces = mulberry32(hashOf(cur.race.seed, "confetti"));
    const palette = [P.accent, P.gold, P.accentLight, "#7cc6f2", "#ffffff"];
    g.save();
    for (let k = 0; k < 140; k++) {
      const x0 = pieces() * W;
      const delay = pieces() * 1.2;
      const speed = 240 + pieces() * 260;
      const sway = 20 + pieces() * 40;
      const spin = pieces() * 8;
      const color = palette[k % palette.length];
      const s = since - delay;
      if (s < 0) continue;
      const y = -30 + s * speed;
      if (y > H + 30) continue;
      g.save();
      g.globalAlpha = 1 - smooth((since - 5) / 1);
      g.translate(x0 + Math.sin(s * 2 + k) * sway, y);
      g.rotate(s * spin);
      g.fillStyle = color;
      g.fillRect(-6, -9, 12, 18);
      g.strokeStyle = INK;
      g.lineWidth = 1.2;
      g.strokeRect(-6, -9, 12, 18);
      g.restore();
    }
    g.restore();
  }
  function buildCards(cur) {
    const { race, heat, index } = cur;
    heatCard.replaceChildren();
    winCard.replaceChildren();
    const survival = race.game === "survival";
    if (!heat.final) {
      heatCard.append(el("div", "kicker", `${heat.label} 결과`));
      const list = el("ol", "rows");
      heat.order.forEach((lane, place) => {
        const advance = heat.advance.includes(lane);
        const item = el("li", advance ? "advance" : "");
        item.style.setProperty("--i", String(place));
        item.append(el("b", "", String(place + 1)), el("span", "who", heat.names[lane]), el("small", "", `${heat.times[lane].toFixed(2)}초`));
        item.append(advance ? el("em", "", race.rank === "last" ? "꼴찌 결승 진출" : "진출") : el("span", ""));
        list.append(item);
      });
      heatCard.append(list);
      const next = race.heats[index + 1];
      heatCard.append(el("div", "foot", next ? `다음 경기: ${next.label}` : ""));
      return;
    }
    winCard.append(el("div", "kicker", race.rank_label), el("div", "name", race.winner.name));
    if (race.winner.comment) winCard.append(el("div", "comment", race.winner.comment));  // 후원 뒤 처음 쓴 채팅
    const meta = el("div", "meta");
    for (const part of [race.practice ? "연습" : "", race.game_label, race.course_label, `${race.count}명`, `시드 ${race.seed}`].filter(Boolean)) {
      meta.append(el("span", "", part));
    }
    winCard.append(meta);
    const standing = race.standing || [];
    const show = race.rank === "last" ? standing.map((name, k) => [k, name]).slice(-5).reverse() : standing.map((name, k) => [k, name]).slice(0, 5);
    const podium = el("ol", "podium");
    for (const [k, name] of show) {
      if (name === race.winner.name) continue;
      const item = el("li");
      item.append(el("b", "", survival && k === 0 ? "생존" : `${k + 1}`), el("span", "", name));
      podium.append(item);
    }
    if (podium.children.length) winCard.append(podium);
  }
  function updateCards(cur, t) {
    const due = t >= cur.heat.end + 0.6;
    heatCard.hidden = !(due && !cur.heat.final);
    winCard.hidden = !(due && cur.heat.final);
  }

  // ---------------------------------------------------------------- 그리기 반복
  let current = null;
  let fixedT = null;
  let token = 0;
  async function loadFonts(font) {
    if (!document.fonts) return;
    try {
      await Promise.race([
        Promise.all([document.fonts.load(`40px ${font}`, "가A1"), document.fonts.load(`700 20px ${UI}`, "가A1"), document.fonts.load(`40px ${DISPLAY}`, "가A1")]),
        new Promise((resolve) => setTimeout(resolve, 1500)),
      ]);
    } catch (error) {
      // 글꼴을 불러오지 못해도 기본 글꼴로 진행
    }
  }
  async function build(state) {
    const race = state.race;
    const index = clamp(state.heat || 0, 0, race.heats.length - 1);
    const heat = race.heats[index];
    const options = race.options || {};
    const font = options.font_css || DISPLAY;
    await loadFonts(font);
    const P = makePalette(options.design || "wood", options.color_hex || "#ff4f8b");
    const env = {
      race, heat, index, P, font, colors: runnerColors(P, heat.names.length), rng: mulberry32(hashOf(race.seed, index, race.game, heat.names.length)),
      events: options.surprise === "none" ? [] : options.events || [], level: options.surprise || "none",
    };
    const sim = race.game === "marble" ? marbleSim(env) : LANE_GAMES.includes(race.game) ? runSim(env) : survivalSim(env);
    const board = document.createElement("canvas");
    board.width = W;
    board.height = H;
    const g = board.getContext("2d");
    sim.drawStatic(g);
    drawTitle(g, env);
    stage.dataset.design = P.design;
    stage.style.setProperty("--accent", P.accent);
    stage.style.setProperty("--accent-dark", P.accentDark);
    stage.style.setProperty("--accent-light", P.accentLight);
    stage.style.setProperty("--accent-glow", P.glow);
    stage.style.setProperty("--on-accent", P.onAccent);
    stage.style.setProperty("--font", font);
    const cur = { key: `${state.id}:${index}:${state.started}`, state, race, heat, index, env, sim, board, started: state.started,
                  speed: options.speed || 1, countdown: state.countdown ?? 3, lastT: undefined };
    buildCards(cur);
    return cur;
  }
  function render(cur, t) {
    ctx.clearRect(0, 0, W, H);
    const [sx, sy] = cur.sim.shake(t);
    ctx.save();
    ctx.translate(sx, sy);
    ctx.drawImage(cur.board, 0, 0);
    cur.sim.draw(ctx, t);
    ctx.restore();
    drawBanners(ctx, cur, t);
    drawCountdown(ctx, cur, t);
    const since = t - cur.heat.end - 0.6;
    if (since >= 0) {
      ctx.fillStyle = cur.env.P.veil;
      ctx.globalAlpha = smooth(since / 0.4);
      ctx.fillRect(40, 112, 1840, 940);
      ctx.globalAlpha = 1;
      if (cur.heat.final) drawConfetti(ctx, cur, since / cur.speed);
    }
    updateCards(cur, t);
  }
  function sounds(cur, t) {
    const previous = cur.lastT;
    cur.lastT = t;
    if (!sound.on || fixedT !== null || previous === undefined || t < previous || t - previous > 0.8 * cur.speed) return;
    const crossed = (time) => previous < time && t >= time;
    for (let k = 1; k < cur.countdown; k++) if (crossed(-(cur.countdown - k) * cur.speed)) play("count");
    if (crossed(0)) play("go");
    for (const event of cur.sim.events) if (crossed(event.t)) play(event.sound);
    cur.sim.finishes.forEach((time, place) => {
      if (crossed(time)) play(cur.race.game === "survival" ? "pop" : place < 3 ? "finish" : "tick");
    });
    if (crossed(cur.heat.end + 0.6)) play(cur.heat.final ? "fanfare" : "heat");
    const racing = t > 0 && t < cur.heat.end;
    if (racing && cur.sim.tick) {
      const now = performance.now();
      const gap = cur.sim.tick === "step" ? 160 : 110;
      if (now - sound.lastTick > gap && Math.random() < 0.6) {
        sound.lastTick = now;
        play(cur.sim.tick);
      }
    }
  }
  // 그림 견본(?still&t=8): 멈춘 장면을 1초쯤 그린 뒤 그리기를 멈춘다(작은 그림 여러 개가 계속 그리지 않게)
  const still = params.has("still");
  let stillFrames = 0;
  function frame() {
    const cur = current;
    if (still && cur && fixedT !== null && ++stillFrames > 60) return;
    requestAnimationFrame(frame);
    if (!cur) return;
    const t = fixedT !== null ? fixedT : (Date.now() / 1000 - cur.started - cur.countdown) * cur.speed;
    render(cur, t);
    sounds(cur, t);
  }
  function clearStage() {
    current = null;
    ctx.clearRect(0, 0, W, H);
    heatCard.hidden = true;
    winCard.hidden = true;
  }
  async function accept(state) {
    const listen = state.sound || {};
    sound.on = Boolean(listen.on) && (!preview || Boolean(listen.listen)) && !params.has("mute");
    sound.volume = clamp(Number(listen.volume ?? 70) / 100, 0, 1);
    if (sound.master) sound.master.gain.value = sound.volume;
    if (!state.race || state.state === "idle" || (state.race.practice && !showPractice)) {
      token += 1;
      clearStage();
      return;
    }
    const key = `${state.id}:${state.heat}:${state.started}`;
    if (current && current.key === key) {
      current.state = state;
      return;
    }
    const mine = ++token;
    const built = await build(state);
    if (mine === token) current = built;
  }
  requestAnimationFrame(frame);

  if (sampleGame) {
    // 예시 장면: 저장한 설정과 예시 이름으로 서버가 만든 계획(방송 화면에는 나가지 않음)
    document.body.classList.add("sample");
    const query = new URLSearchParams();
    query.set("game", sampleGame);
    for (const name of ["n", "seed", "heat", "course", "design", "color", "font", "format", "surprise", "rank", "length", "speed"]) {
      if (params.has(name)) query.set(name, params.get(name));
    }
    fetch(`/race/sample?${query}`).then((response) => response.json()).then(async (state) => {
      if (state.error) throw new Error(state.error);
      if (params.has("sound")) state.sound = { on: true, volume: 70, listen: true };
      const value = params.get("t");
      if (value !== null) {
        const heat = state.race.heats[clamp(state.heat || 0, 0, state.race.heats.length - 1)];
        fixedT = value === "end" ? heat.end + 3 : Number(value) || 0;
      } else {
        state.started = Date.now() / 1000;
      }
      await accept(state);
    }).catch((error) => console.warn("debutkit: 예시 장면을 만들지 못함", error));
  } else {
    // 연결할 때(다시 연결 포함) 받는 첫 값이 지금 상태: 진행 중이면 지금 장면부터 이어 그린다
    // 공유 연결(live.js). 처리 실패는 live.js가 콘솔에 남긴다
    window.debutkitLive.subscribe(["race", "theme"], (feed, data) => {
      if (feed === "race") accept(data);
    });
  }
  window.debutkitRace = { accept, makePalette, buildProfiles, progressOf };  // 시험용
})();
