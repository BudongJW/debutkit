// debutkit 방송 이미지 만들기의 꾸미기: 테두리, 파티클, 자막 스타일, 캐릭터 움직임, 완성 프리셋, 손그림 펜.
// 모두 캔버스에 직접 그림(바깥 그림 파일 없음). t는 움짤 장면 위치(0에서 1, 한 바퀴), 멈춘 그림은 null.
"use strict";

(() => {
  const TAU = Math.PI * 2;
  const wave = (t, offset = 0, speed = 1) => (t === null ? 0 : Math.sin((t * speed + offset) * TAU));

  //: 이름표(조작 화면 목록 순서)
  const BORDERS = {
    ring: "단색 링", double: "이중 링", dashed: "점선", gradient: "그라데이션", neon: "네온", stars: "별 테두리", hearts: "하트 테두리",
    scallop: "꽃잎 테두리", lace: "레이스", ribbon: "리본", wreath: "겨울 리스", snowcrown: "눈꽃 화관", none: "없음",
  };
  const PARTICLES = {
    none: "없음", sparkle: "반짝 별", hearts: "하트", petals: "꽃잎", snow: "눈송이", notes: "음표", bubbles: "방울", confetti: "색종이",
    glitter: "반짝 가루", fireflies: "빛 방울",
  };
  const CAPTIONS = {
    band: "강조 띠", pill: "두 색 알약", bubble: "말풍선", ribbon: "리본 띠", neon: "네온 글자", outline: "굵은 테두리 글자", shadow: "그림자 글자",
    memo: "메모지", highlighter: "형광펜 밑줄", sticker: "스티커",
  };
  const MOTIONS = { float: "둥실", bounce: "통통", sway: "흔들흔들", pulse: "두근두근", pop: "톡 등장", slide: "옆에서 등장", shake: "부르르", none: "멈춤" };
  const PENS = { pen: "펜", highlighter: "형광펜", neon: "네온", cream: "크림(흰 테두리)", dotted: "점선" };
  //: 완성 프리셋: 이름과 고를 값(테두리, 파티클, 자막, 움직임, 배경 무늬, 제목 글꼴, 글 글꼴)
  const PRESETS = {
    basic: { name: "기본", border: "ring", particles: "none", caption: "band", motion: "float", pattern: "stars", title: "blackhan", text: "pretendard" },
    night: { name: "별밤", border: "stars", particles: "sparkle", caption: "neon", motion: "float", pattern: "stars", title: "yeonsung", text: "gowundodum" },
    heart: { name: "핑크 하트", border: "hearts", particles: "hearts", caption: "bubble", motion: "pulse", pattern: "dots", title: "jua", text: "cute" },
    winter: { name: "겨울 눈꽃", border: "snowcrown", particles: "snow", caption: "ribbon", motion: "sway", pattern: "none", title: "dohyeon", text: "gowundodum" },
    xmas: { name: "크리스마스", border: "wreath", particles: "confetti", caption: "sticker", motion: "bounce", pattern: "dots", title: "bagel", text: "jua" },
    neon: { name: "네온", border: "neon", particles: "fireflies", caption: "neon", motion: "pulse", pattern: "stripes", title: "dohyeon", text: "stylish" },
    spring: { name: "봄 꽃잎", border: "scallop", particles: "petals", caption: "memo", motion: "sway", pattern: "none", title: "gamja", text: "gamja" },
    music: { name: "노래 방송", border: "double", particles: "notes", caption: "pill", motion: "bounce", pattern: "dots", title: "jua", text: "sunflower" },
    diary: { name: "다이어리", border: "lace", particles: "glitter", caption: "highlighter", motion: "float", pattern: "dots", title: "gaegu", text: "gaegu" },
  };

  function random(seed) {
    let value = seed % 2147483647 || 7;
    return () => ((value = (value * 16807) % 2147483647) / 2147483647);
  }

  // ---------------------------------------------------------------- 작은 그림
  function starPath(ctx, x, y, r, points = 5, inner = 0.45) {
    ctx.beginPath();
    for (let k = 0; k < points * 2; k += 1) {
      const angle = (k * Math.PI) / points - Math.PI / 2;
      const radius = k % 2 ? r * inner : r;
      ctx[k ? "lineTo" : "moveTo"](x + Math.cos(angle) * radius, y + Math.sin(angle) * radius);
    }
    ctx.closePath();
  }

  function heartPath(ctx, x, y, r) {
    ctx.beginPath();
    ctx.moveTo(x, y + r * 0.9);
    ctx.bezierCurveTo(x - r * 1.5, y - r * 0.1, x - r * 0.75, y - r * 1.15, x, y - r * 0.45);
    ctx.bezierCurveTo(x + r * 0.75, y - r * 1.15, x + r * 1.5, y - r * 0.1, x, y + r * 0.9);
    ctx.closePath();
  }

  function snowflake(ctx, x, y, r, width) {
    ctx.save();
    ctx.lineWidth = width;
    ctx.lineCap = "round";
    ctx.beginPath();
    for (let k = 0; k < 6; k += 1) {
      const angle = (k * Math.PI) / 3;
      const ex = x + Math.cos(angle) * r, ey = y + Math.sin(angle) * r;
      ctx.moveTo(x, y);
      ctx.lineTo(ex, ey);
      for (const side of [-1, 1]) {  // 가지
        const bx = x + Math.cos(angle) * r * 0.6, by = y + Math.sin(angle) * r * 0.6;
        ctx.moveTo(bx, by);
        ctx.lineTo(bx + Math.cos(angle + side * 0.7) * r * 0.32, by + Math.sin(angle + side * 0.7) * r * 0.32);
      }
    }
    ctx.stroke();
    ctx.restore();
  }

  function note(ctx, x, y, r) {  // 음표(머리, 기둥, 꼬리)
    ctx.beginPath();
    ctx.ellipse(x, y, r * 0.55, r * 0.4, -0.4, 0, TAU);
    ctx.fill();
    ctx.fillRect(x + r * 0.38, y - r * 1.9, r * 0.16, r * 1.9);
    ctx.beginPath();
    ctx.moveTo(x + r * 0.54, y - r * 1.9);
    ctx.quadraticCurveTo(x + r * 1.3, y - r * 1.5, x + r * 0.9, y - r * 0.8);
    ctx.quadraticCurveTo(x + r * 1.05, y - r * 1.35, x + r * 0.54, y - r * 1.5);
    ctx.fill();
  }

  function leaf(ctx, x, y, r, angle) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);
    ctx.beginPath();
    ctx.moveTo(-r, 0);
    ctx.quadraticCurveTo(0, -r * 0.7, r, 0);
    ctx.quadraticCurveTo(0, r * 0.7, -r, 0);
    ctx.fill();
    ctx.restore();
  }

  // ---------------------------------------------------------------- 모양(테두리를 그릴 자리)
  // shape: { type: "circle", cx, cy, r }, { type: "rect", x, y, w, h, r }, { type: "poly", cx, cy, r, points: [[x, y]] }(하트, 별, 배지)
  //: 시그니처 판 모양
  const SHAPES = { card: "둥근 카드", circle: "원", heart: "하트", star: "별", badge: "꽃 배지" };

  // 판 모양(가운데 cx, cy, 반지름 r)을 테두리 그릴 자리로
  function shapeOf(kind, cx, cy, r) {
    if (kind === "circle") return { type: "circle", cx, cy, r };
    if (kind === "card" || !SHAPES[kind]) return { type: "rect", x: cx - r, y: cy - r, w: r * 2, h: r * 2, r: r * 0.28 };
    const points = [];
    const n = 160;
    for (let k = 0; k < n; k += 1) {
      const a = (k / n) * TAU;
      if (kind === "heart") {  // 하트 곡선(크기를 r에 맞춤)
        const x = 16 * Math.sin(a) ** 3, y = -(13 * Math.cos(a) - 5 * Math.cos(2 * a) - 2 * Math.cos(3 * a) - Math.cos(4 * a));
        points.push([cx + (x / 17) * r, cy + ((y + 2.5) / 17) * r]);
      } else if (kind === "star") {  // 끝이 둥근 별
        const radius = r * (0.78 + 0.22 * Math.cos(5 * (a + Math.PI / 2)));
        points.push([cx + Math.cos(a) * radius, cy + Math.sin(a) * radius]);
      } else {  // badge: 꽃잎 가장자리 원
        const radius = r * (0.93 + 0.07 * Math.cos(16 * a));
        points.push([cx + Math.cos(a) * radius, cy + Math.sin(a) * radius]);
      }
    }
    return { type: "poly", cx, cy, r, points };
  }

  function outline(ctx, shape, inset = 0) {
    ctx.beginPath();
    if (shape.type === "poly") {  // 가운데 쪽으로 inset만큼 줄인 다각형
      const scale = Math.max(0.01, 1 - inset / shape.r);
      shape.points.forEach(([x, y], index) => ctx[index ? "lineTo" : "moveTo"](shape.cx + (x - shape.cx) * scale, shape.cy + (y - shape.cy) * scale));
      ctx.closePath();
      return;
    }
    if (shape.type === "circle") {
      ctx.arc(shape.cx, shape.cy, Math.max(1, shape.r - inset), 0, TAU);
      return;
    }
    const x = shape.x + inset, y = shape.y + inset, w = shape.w - inset * 2, h = shape.h - inset * 2;
    const r = Math.max(0, Math.min(shape.r - inset, w / 2, h / 2));
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  const size = (shape) => (shape.type === "rect" ? Math.min(shape.w, shape.h) : shape.r * 2);

  // 둘레를 따라 같은 간격의 점 n개: [x, y, 바깥 방향 각도]
  function along(shape, n, inset = 0) {
    const points = [];
    if (shape.type === "poly") {  // 둘레 길이를 따라 고르게
      const scale = Math.max(0.01, 1 - inset / shape.r);
      const ring = shape.points.map(([x, y]) => [shape.cx + (x - shape.cx) * scale, shape.cy + (y - shape.cy) * scale]);
      const lengths = ring.map(([x, y], index) => Math.hypot(ring[(index + 1) % ring.length][0] - x, ring[(index + 1) % ring.length][1] - y));
      const total = lengths.reduce((sum, value) => sum + value, 0);
      let segment = 0, walked = 0;
      for (let k = 0; k < n; k += 1) {
        const target = (k / n) * total;
        while (walked + lengths[segment] < target) walked += lengths[segment++];
        const [x0, y0] = ring[segment], [x1, y1] = ring[(segment + 1) % ring.length];
        const f = lengths[segment] ? (target - walked) / lengths[segment] : 0;
        const x = x0 + (x1 - x0) * f, y = y0 + (y1 - y0) * f;
        points.push([x, y, Math.atan2(y - shape.cy, x - shape.cx)]);
      }
      return points;
    }
    if (shape.type === "circle") {
      for (let k = 0; k < n; k += 1) {
        const angle = (k / n) * TAU - Math.PI / 2;
        points.push([shape.cx + Math.cos(angle) * (shape.r - inset), shape.cy + Math.sin(angle) * (shape.r - inset), angle]);
      }
      return points;
    }
    const x = shape.x + inset, y = shape.y + inset, w = shape.w - inset * 2, h = shape.h - inset * 2;
    const total = 2 * (w + h);
    for (let k = 0; k < n; k += 1) {
      let d = (k / n) * total;
      if (d < w) points.push([x + d, y, -Math.PI / 2]);
      else if ((d -= w) < h) points.push([x + w, y + d, 0]);
      else if ((d -= h) < w) points.push([x + w - d, y + h, Math.PI / 2]);
      else points.push([x, y + h - (d - w), Math.PI]);
    }
    return points;
  }

  // ---------------------------------------------------------------- 테두리
  function border(ctx, kind, shape, c, t) {
    if (!kind || kind === "none") return;
    const s = size(shape);
    const line = s * 0.035;
    ctx.save();
    if (kind === "ring" || kind === "ribbon" || kind === "snowcrown") {
      ctx.lineWidth = line;
      ctx.strokeStyle = kind === "snowcrown" ? "#ffffff" : c.highlight;
      ctx.shadowColor = c.highlight;
      ctx.shadowBlur = t === null ? 0 : s * (0.02 + 0.02 * wave(t));
      outline(ctx, shape, line / 2);
      ctx.stroke();
      ctx.shadowBlur = 0;
      if (kind === "ribbon") bow(ctx, shape, c, s, t);
      if (kind === "snowcrown") {  // 위쪽 둘레에 눈꽃
        ctx.strokeStyle = "#ffffff";
        ctx.fillStyle = "#ffffff";
        for (const [x, y] of along(shape, 26, line / 2)) {
          if (y > (shape.type === "rect" ? shape.y + shape.h * 0.2 : shape.cy - shape.r * 0.35)) continue;
          snowflake(ctx, x, y, s * 0.034 * (1 + 0.12 * wave(t, x / s)), s * 0.006);
        }
      }
    } else if (kind === "double") {
      ctx.lineWidth = line;
      ctx.strokeStyle = c.highlight;
      outline(ctx, shape, line / 2);
      ctx.stroke();
      ctx.lineWidth = line * 0.32;
      ctx.strokeStyle = "#ffffff";
      outline(ctx, shape, line * 1.55);
      ctx.stroke();
    } else if (kind === "dashed") {
      ctx.lineWidth = line * 0.7;
      ctx.strokeStyle = "#ffffff";
      ctx.setLineDash([line * 1.6, line * 1.1]);
      ctx.lineDashOffset = t === null ? 0 : -t * line * 2.7 * 4;  // 움짤: 점선이 둘레를 따라 흐름
      outline(ctx, shape, line);
      ctx.stroke();
    } else if (kind === "gradient") {
      const angle = (t || 0) * TAU;
      const cx = shape.type === "rect" ? shape.x + shape.w / 2 : shape.cx, cy = shape.type === "rect" ? shape.y + shape.h / 2 : shape.cy;
      const g = ctx.createLinearGradient(cx - Math.cos(angle) * s / 2, cy - Math.sin(angle) * s / 2, cx + Math.cos(angle) * s / 2, cy + Math.sin(angle) * s / 2);
      g.addColorStop(0, c.highlight);
      g.addColorStop(0.5, "#ffffff");
      g.addColorStop(1, c.primary);
      ctx.lineWidth = line * 1.2;
      ctx.strokeStyle = g;
      outline(ctx, shape, line * 0.6);
      ctx.stroke();
    } else if (kind === "neon") {
      const glow = 0.75 + 0.25 * wave(t);
      ctx.lineWidth = line * 0.9;
      ctx.strokeStyle = c.highlight;
      ctx.shadowColor = c.highlight;
      ctx.shadowBlur = s * 0.05 * glow;
      ctx.globalAlpha = glow;
      outline(ctx, shape, line);
      ctx.stroke();
      ctx.stroke();
      ctx.lineWidth = line * 0.28;
      ctx.strokeStyle = "#ffffff";
      ctx.shadowBlur = 0;
      ctx.stroke();
    } else if (kind === "stars" || kind === "hearts") {
      ctx.lineWidth = line * 0.4;
      ctx.strokeStyle = "#ffffff";
      outline(ctx, shape, line * 1.1);
      ctx.stroke();
      const points = along(shape, shape.type === "rect" ? 30 : 22, line * 1.1);
      points.forEach(([x, y], index) => {
        const r = s * (index % 2 ? 0.022 : 0.032) * (1 + 0.18 * wave(t, index / points.length, 2));
        ctx.fillStyle = index % 2 ? "#ffffff" : c.highlight;
        if (kind === "stars") starPath(ctx, x, y, r);
        else heartPath(ctx, x, y, r * 0.9);
        ctx.fill();
      });
    } else if (kind === "scallop") {
      const points = along(shape, shape.type === "rect" ? 40 : 30, line * 0.6);
      const r = s * (shape.type === "rect" ? 0.04 : 0.055);
      points.forEach(([x, y], index) => {
        ctx.fillStyle = index % 2 ? c.light : "#ffffff";
        ctx.beginPath();
        ctx.arc(x, y, r, 0, TAU);
        ctx.fill();
      });
    } else if (kind === "lace") {
      ctx.lineWidth = line * 0.3;
      ctx.strokeStyle = "#ffffff";
      outline(ctx, shape, line * 0.9);
      ctx.stroke();
      const points = along(shape, shape.type === "rect" ? 64 : 48, line * 0.9);
      ctx.fillStyle = "#ffffff";
      points.forEach(([x, y, angle], index) => {
        ctx.beginPath();
        if (index % 2) {
          ctx.arc(x, y, s * 0.008, 0, TAU);
          ctx.fill();
        } else {
          ctx.arc(x - Math.cos(angle) * s * 0.012, y - Math.sin(angle) * s * 0.012, s * 0.016, 0, TAU);
          ctx.lineWidth = s * 0.004;
          ctx.stroke();
        }
      });
    } else if (kind === "wreath") {
      const points = along(shape, shape.type === "rect" ? 72 : 56, line);
      points.forEach(([x, y, angle], index) => {
        ctx.fillStyle = index % 3 === 0 ? "#2f8f5b" : index % 3 === 1 ? "#3fae6e" : "#1f6e45";
        leaf(ctx, x, y, s * 0.034, angle + Math.PI / 2 + (index % 2 ? 0.6 : -0.6));
      });
      points.forEach(([x, y], index) => {
        if (index % 5) return;
        ctx.fillStyle = "#e23b4e";
        ctx.beginPath();
        ctx.arc(x, y, s * 0.012 * (1 + 0.15 * wave(t, index / points.length)), 0, TAU);
        ctx.fill();
      });
      bow(ctx, shape, { ...c, highlight: "#e23b4e", deep: "#9e1b2c" }, s, t);
    }
    ctx.restore();
  }

  function bow(ctx, shape, c, s, t) {  // 위쪽 가운데 리본
    const x = shape.type === "rect" ? shape.x + shape.w / 2 : shape.cx;
    const y = shape.type === "rect" ? shape.y + s * 0.03 : shape.cy - shape.r + s * 0.03;
    const r = s * 0.075;
    const lift = r * 0.06 * wave(t);
    ctx.save();
    ctx.fillStyle = c.highlight;
    ctx.strokeStyle = c.deep;
    ctx.lineWidth = s * 0.006;
    for (const side of [-1, 1]) {
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.bezierCurveTo(x + side * r * 1.4, y - r * 0.9 + lift, x + side * r * 1.5, y + r * 0.6, x, y);
      ctx.fill();
      ctx.stroke();
      ctx.beginPath();  // 꼬리
      ctx.moveTo(x, y);
      ctx.lineTo(x + side * r * 0.55, y + r * 1.25);
      ctx.lineTo(x + side * r * 0.2, y + r * 1.05);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.arc(x, y, r * 0.28, 0, TAU);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }

  // ---------------------------------------------------------------- 파티클(움짤에서는 한 바퀴에 꼭 맞게 돌아 이음매가 없음)
  function particles(ctx, kind, width, height, c, t, seed = 7) {
    if (!kind || kind === "none") return;
    const rnd = random(seed * 7919 + kind.length * 104729);
    const unit = Math.min(width, height);
    const count = Math.round(Math.min(48, Math.max(14, (width * height) / (unit * unit) * 22)));
    const colors = [c.highlight, "#ffffff", c.light, c.primary];
    ctx.save();
    for (let k = 0; k < count; k += 1) {
      const x0 = rnd(), y0 = rnd(), offset = rnd(), r = unit * (0.014 + rnd() * 0.022), spin = rnd() * TAU;
      const time = t === null ? 0 : t;
      const fall = ["snow", "petals", "confetti"].includes(kind);
      const rise = ["hearts", "notes", "bubbles"].includes(kind);
      let y = y0;
      if (fall) y = (y0 + time) % 1;
      if (rise) y = (y0 - time + 1) % 1;
      const x = x0 * width + unit * 0.03 * wave(t, offset) + (fall || rise ? unit * 0.02 * Math.sin((y + offset) * TAU) : 0);
      const py = y * (height + r * 4) - r * 2;
      const twinkle = t === null ? 0.8 : 0.55 + 0.45 * wave(t, offset);
      ctx.globalAlpha = kind === "glitter" || kind === "sparkle" || kind === "fireflies" ? twinkle : 0.92;
      ctx.fillStyle = colors[k % colors.length];
      ctx.strokeStyle = ctx.fillStyle;
      if (kind === "sparkle") { starPath(ctx, x, py, r * 1.2, 4, 0.32); ctx.fill(); }
      else if (kind === "glitter") { starPath(ctx, x, py, r * 0.55, 4, 0.3); ctx.fill(); }
      else if (kind === "hearts") { ctx.fillStyle = k % 2 ? c.highlight : "#ff6b9a"; heartPath(ctx, x, py, r); ctx.fill(); }
      else if (kind === "snow") { ctx.strokeStyle = "#ffffff"; snowflake(ctx, x, py, r, r * 0.16); }
      else if (kind === "notes") { note(ctx, x, py, r * 0.9); }
      else if (kind === "bubbles") {
        ctx.lineWidth = r * 0.16;
        ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
        ctx.beginPath(); ctx.arc(x, py, r, 0, TAU); ctx.stroke();
        ctx.fillStyle = "rgba(255, 255, 255, 0.8)";
        ctx.beginPath(); ctx.arc(x - r * 0.35, py - r * 0.35, r * 0.22, 0, TAU); ctx.fill();
      } else if (kind === "petals") {
        ctx.fillStyle = k % 2 ? "#ffc4d6" : "#ffe1ea";
        leaf(ctx, x, py, r, spin + time * TAU);
      } else if (kind === "confetti") {
        ctx.save();
        ctx.translate(x, py);
        ctx.rotate(spin + time * TAU * 2);
        ctx.fillRect(-r * 0.6, -r * 0.3, r * 1.2, r * 0.6);
        ctx.restore();
      } else if (kind === "fireflies") {
        const g = ctx.createRadialGradient(x, py, 0, x, py, r * 1.6);
        g.addColorStop(0, "#ffffff");
        g.addColorStop(0.35, c.highlight);
        g.addColorStop(1, "rgba(255, 255, 255, 0)");
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(x, py, r * 1.6, 0, TAU); ctx.fill();
      }
    }
    ctx.restore();
  }

  // ---------------------------------------------------------------- 자막(한 줄 소개, 방송 제목)
  function roundRect(ctx, x, y, w, h, r) {
    outline(ctx, { type: "rect", x, y, w, h, r });
  }

  // (x, y)는 글자 줄의 기준(align 쪽 끝). px는 글자 크기, font는 { css, weight }
  function caption(ctx, kind, text, x, y, px, align, c, font, t) {
    ctx.save();
    ctx.font = `${font.weight} ${px}px ${font.css}`;
    const width = ctx.measureText(text).width;
    const padX = px * 0.6;
    const boxW = width + padX * 2, boxH = px * 1.6;
    const left = align === "center" ? x - boxW / 2 : align === "right" ? x - boxW : x;
    const top = y;
    const baseline = top + px * 1.15;
    ctx.textAlign = "left";
    const write = (fill) => { ctx.fillStyle = fill; ctx.fillText(text, left + padX, baseline); };
    if (kind === "pill") {
      ctx.fillStyle = c.highlight;
      roundRect(ctx, left, top, boxW, boxH, boxH / 2);
      ctx.fill();
      ctx.lineWidth = px * 0.14;
      ctx.strokeStyle = c.deep;
      ctx.stroke();
      ctx.fillStyle = c.deep;
      ctx.beginPath(); ctx.arc(left + boxH / 2 - px * 0.15, top + boxH / 2, px * 0.18, 0, TAU); ctx.fill();
      ctx.fillStyle = c.onHighlight;
      ctx.fillText(text, left + padX + px * 0.2, baseline);
    } else if (kind === "bubble") {
      ctx.fillStyle = "#ffffff";
      ctx.strokeStyle = c.deep;
      ctx.lineWidth = px * 0.1;
      roundRect(ctx, left, top, boxW, boxH, px * 0.5);
      ctx.fill();
      ctx.stroke();
      ctx.beginPath();  // 꼬리
      ctx.moveTo(left + boxW * 0.22, top + boxH - 1);
      ctx.lineTo(left + boxW * 0.16, top + boxH + px * 0.55);
      ctx.lineTo(left + boxW * 0.34, top + boxH - 1);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(left + boxW * 0.2, top + boxH - ctx.lineWidth * 1.5, boxW * 0.15, ctx.lineWidth * 2);
      write(c.ink);
    } else if (kind === "ribbon") {
      const notch = px * 0.55;
      ctx.fillStyle = c.deep;
      for (const side of [-1, 1]) {  // 접힌 끝
        const edge = side < 0 ? left : left + boxW;
        ctx.beginPath();
        ctx.moveTo(edge, top + px * 0.3);
        ctx.lineTo(edge + side * notch * 1.4, top + px * 0.3);
        ctx.lineTo(edge + side * notch * 0.8, top + px * 0.3 + boxH / 2);
        ctx.lineTo(edge + side * notch * 1.4, top + px * 0.3 + boxH);
        ctx.lineTo(edge, top + px * 0.3 + boxH);
        ctx.fill();
      }
      ctx.fillStyle = c.highlight;
      ctx.fillRect(left, top, boxW, boxH);
      write(c.onHighlight);
    } else if (kind === "neon") {
      const glow = 0.8 + 0.2 * wave(t, 0, 2);
      ctx.shadowColor = c.highlight;
      ctx.shadowBlur = px * 0.6 * glow;
      ctx.lineWidth = px * 0.12;
      ctx.strokeStyle = c.highlight;
      ctx.strokeText(text, left + padX, baseline);
      write("#ffffff");
      ctx.shadowBlur = px * 0.25;
      write("#ffffff");
    } else if (kind === "outline") {
      ctx.lineJoin = "round";
      ctx.lineWidth = px * 0.28;
      ctx.strokeStyle = c.deep;
      ctx.strokeText(text, left + padX, baseline);
      write("#ffffff");
    } else if (kind === "shadow") {
      ctx.fillStyle = c.deep;
      ctx.fillText(text, left + padX + px * 0.09, baseline + px * 0.09);
      write("#ffffff");
    } else if (kind === "memo") {
      ctx.translate(left + boxW / 2, top + boxH / 2);
      ctx.rotate(-0.04);
      ctx.translate(-(left + boxW / 2), -(top + boxH / 2));
      ctx.shadowColor = "rgba(30, 20, 50, 0.3)";
      ctx.shadowBlur = px * 0.3;
      ctx.shadowOffsetY = px * 0.12;
      ctx.fillStyle = "#fff3a6";
      ctx.fillRect(left, top - px * 0.15, boxW, boxH + px * 0.3);
      ctx.shadowColor = "transparent";
      ctx.fillStyle = "rgba(255, 255, 255, 0.55)";  // 테이프
      ctx.fillRect(left + boxW / 2 - px * 0.9, top - px * 0.45, px * 1.8, px * 0.55);
      write(c.ink);
    } else if (kind === "highlighter") {
      ctx.fillStyle = c.highlight;
      ctx.globalAlpha = 0.75;
      ctx.fillRect(left + padX * 0.6, top + boxH * 0.52, width + padX * 0.8, boxH * 0.38);
      ctx.globalAlpha = 1;
      ctx.lineJoin = "round";
      ctx.lineWidth = px * 0.16;
      ctx.strokeStyle = c.deep;
      ctx.strokeText(text, left + padX, baseline);
      write("#ffffff");
    } else if (kind === "sticker") {
      ctx.translate(left + boxW / 2, top + boxH / 2);
      ctx.rotate(0.03);
      ctx.translate(-(left + boxW / 2), -(top + boxH / 2));
      ctx.shadowColor = "rgba(30, 20, 50, 0.35)";
      ctx.shadowBlur = px * 0.25;
      ctx.shadowOffsetY = px * 0.1;
      ctx.fillStyle = "#ffffff";
      roundRect(ctx, left - px * 0.18, top - px * 0.18, boxW + px * 0.36, boxH + px * 0.36, px * 0.55);
      ctx.fill();
      ctx.shadowColor = "transparent";
      ctx.fillStyle = c.primary;
      roundRect(ctx, left, top, boxW, boxH, px * 0.42);
      ctx.fill();
      write("#ffffff");
    } else {  // band: 강조 색 띠
      ctx.fillStyle = c.highlight;
      roundRect(ctx, left, top, boxW, boxH, px * 0.8);
      ctx.fill();
      write(c.onHighlight);
    }
    ctx.restore();
  }

  // ---------------------------------------------------------------- 캐릭터 움직임: 발밑 가운데 기준 { dx, dy, scale, rotate } (tall은 캐릭터 높이)
  function motion(kind, t, tall) {
    const moved = { dx: 0, dy: 0, scale: 1, rotate: 0 };
    if (t === null || !kind || kind === "none") return moved;
    const ease = (value) => 1 - (1 - value) ** 3;
    if (kind === "float") moved.dy = tall * 0.012 * wave(t);
    else if (kind === "bounce") moved.dy = -Math.abs(Math.sin(t * TAU)) * tall * 0.05;
    else if (kind === "sway") moved.rotate = 0.05 * wave(t);
    else if (kind === "pulse") moved.scale = 1 + 0.035 * Math.max(0, wave(t, 0, 2));
    else if (kind === "shake") moved.dx = tall * 0.012 * Math.sin(t * TAU * 6);
    else if (kind === "pop") {
      const p = Math.min(1, t / 0.28);
      moved.scale = p < 1 ? Math.max(0.01, ease(p) * (1 + 0.12 * Math.sin(p * Math.PI))) : 1;
    } else if (kind === "slide") {
      const p = Math.min(1, t / 0.3);
      moved.dx = (1 - ease(p)) * -tall * 0.9;
    }
    return moved;
  }

  // ---------------------------------------------------------------- 손그림 펜: 획 { pen, color, size(그림 짧은 변 대비), points: [[x, y] 0~1] }
  function strokes(ctx, list, width, height) {
    const unit = Math.min(width, height);
    for (const stroke of list) {
      if (!stroke.points.length) continue;
      const w = Math.max(1, stroke.size * unit);
      const path = () => {
        ctx.beginPath();
        stroke.points.forEach(([x, y], index) => ctx[index ? "lineTo" : "moveTo"](x * width, y * height));
        if (stroke.points.length === 1) ctx.lineTo(stroke.points[0][0] * width + 0.1, stroke.points[0][1] * height);
      };
      ctx.save();
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      if (stroke.pen === "highlighter") {
        ctx.globalAlpha = 0.38;
        ctx.lineCap = "butt";
        ctx.lineWidth = w * 2.6;
        ctx.strokeStyle = stroke.color;
        path(); ctx.stroke();
      } else if (stroke.pen === "neon") {
        ctx.shadowColor = stroke.color;
        ctx.shadowBlur = w * 2.2;
        ctx.lineWidth = w * 1.4;
        ctx.strokeStyle = stroke.color;
        path(); ctx.stroke();
        ctx.shadowBlur = 0;
        ctx.lineWidth = w * 0.45;
        ctx.strokeStyle = "#ffffff";
        ctx.stroke();
      } else if (stroke.pen === "cream") {
        ctx.lineWidth = w * 2.2;
        ctx.strokeStyle = "#ffffff";
        path(); ctx.stroke();
        ctx.lineWidth = w;
        ctx.strokeStyle = stroke.color;
        ctx.stroke();
      } else if (stroke.pen === "dotted") {
        ctx.setLineDash([0.1, w * 2.2]);
        ctx.lineWidth = w * 1.3;
        ctx.strokeStyle = stroke.color;
        path(); ctx.stroke();
      } else {
        ctx.lineWidth = w;
        ctx.strokeStyle = stroke.color;
        path(); ctx.stroke();
      }
      ctx.restore();
    }
  }

  // ---------------------------------------------------------------- 방셀 액자(사진 둘레 꾸밈): 사진 자리와 둘레 그림
  const FRAMES = {
    gold: "매트 금선", double: "이중선", film: "필름", lace: "레이스", pearl: "진주", tape: "마스킹 테이프", arch: "아치 창",
    xmas: "크리스마스", night: "밤하늘", cafe: "디저트 카페",
  };

  // 사진 자리 { x, y, w, h, arch }. 아래 여백은 글 한 줄 자리로 조금 더 넓게
  function frameLayout(kind, width, height) {
    const unit = Math.min(width, height);
    const m = unit * (kind === "film" ? 0.1 : kind === "tape" ? 0.07 : 0.075);
    const bottom = m + unit * 0.06;
    if (kind === "film" && width >= height) return { x: m * 0.5, y: m, w: width - m, h: height - m * 2, arch: false };
    if (kind === "film") return { x: m, y: m * 0.5, w: width - m * 2, h: height - m, arch: false };
    return { x: m, y: m, w: width - m * 2, h: height - m - bottom, arch: kind === "arch" };
  }

  // 사진 자리를 자르는 길(아치 창은 위가 둥근 창)
  function framePath(ctx, rect, fresh = true) {  // fresh가 거짓이면 지금 길에 이어 붙임(둘레 자르기)
    if (fresh) ctx.beginPath();
    if (rect.arch) {
      const r = Math.min(rect.w / 2, rect.h * 0.5);
      ctx.moveTo(rect.x, rect.y + rect.h);
      ctx.lineTo(rect.x, rect.y + r);
      ctx.arc(rect.x + rect.w / 2, rect.y + r, rect.w / 2, Math.PI, 0);
      ctx.lineTo(rect.x + rect.w, rect.y + rect.h);
      ctx.closePath();
    } else {
      ctx.rect(rect.x, rect.y, rect.w, rect.h);
    }
  }

  function fillRound(ctx, x, y, w, h, r) {
    outline(ctx, { type: "rect", x, y, w, h, r });
    ctx.fill();
  }

  // 사진 바깥(둘레)과 꾸밈. 사진은 먼저 그려 둔 상태
  function frame(ctx, kind, width, height, rect, c, t) {
    const unit = Math.min(width, height);
    const papers = { gold: "#f6f1e7", double: "#ffffff", film: "#1b1b1f", lace: c.light, pearl: "#f7f2f6", tape: "#fbf8f2", arch: "#f4eee6",
      xmas: "#1f5c3d", night: "#151a3a", cafe: "#ffffff" };
    const paper = papers[kind] || "#ffffff";
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, width, height);
    framePath(ctx, rect, false);
    ctx.clip("evenodd");
    ctx.fillStyle = paper;
    ctx.fillRect(0, 0, width, height);
    if (kind === "cafe") {  // 분홍 깅엄 체크
      const cell = unit * 0.045;
      ctx.fillStyle = "rgba(255, 140, 170, 0.35)";
      for (let x = 0; x < width; x += cell * 2) ctx.fillRect(x, 0, cell, height);
      for (let y = 0; y < height; y += cell * 2) ctx.fillRect(0, y, width, cell);
    } else if (kind === "night") {  // 별과 초승달
      const rnd = random(31);
      ctx.fillStyle = "#ffffff";
      for (let k = 0; k < 70; k += 1) {
        ctx.globalAlpha = 0.4 + 0.6 * Math.abs(wave(t, rnd()));
        starPath(ctx, rnd() * width, rnd() * height, unit * (0.004 + rnd() * 0.01), 4, 0.35);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      ctx.fillStyle = "#ffe9a8";
      ctx.beginPath();
      ctx.arc(width - unit * 0.07, unit * 0.07, unit * 0.04, 0, TAU);
      ctx.fill();
      ctx.fillStyle = paper;
      ctx.beginPath();
      ctx.arc(width - unit * 0.055, unit * 0.06, unit * 0.036, 0, TAU);
      ctx.fill();
    } else if (kind === "xmas") {  // 눈 내리는 초록 바탕
      const rnd = random(17);
      ctx.strokeStyle = "#ffffff";
      for (let k = 0; k < 40; k += 1) {
        const x = rnd() * width, y = ((rnd() + (t || 0)) % 1) * height;
        snowflake(ctx, x, y, unit * (0.008 + rnd() * 0.01), unit * 0.0025);
      }
    } else if (kind === "film") {  // 필름 구멍
      ctx.fillStyle = "#f4f1ea";
      const hole = unit * 0.028, gap = hole * 2.2;
      if (width >= height) {
        for (let x = gap / 2; x < width; x += gap) {
          for (const y of [rect.y / 2, height - rect.y / 2]) fillRound(ctx, x - hole / 2, y - hole * 0.35, hole, hole * 0.7, hole * 0.15);
        }
      } else {
        for (let y = gap / 2; y < height; y += gap) {
          for (const x of [rect.x / 2, width - rect.x / 2]) fillRound(ctx, x - hole * 0.35, y - hole / 2, hole * 0.7, hole, hole * 0.15);
        }
      }
    }
    ctx.restore();
    ctx.save();  // 사진 둘레 선과 장식
    const around = (gap) => ({ type: "rect", x: rect.x - gap, y: rect.y - gap, w: rect.w + gap * 2, h: rect.h + gap * 2, r: 0 });
    if (kind === "gold") {
      ctx.strokeStyle = "#c9a44c";
      ctx.lineWidth = unit * 0.006;
      ctx.strokeRect(rect.x - unit * 0.012, rect.y - unit * 0.012, rect.w + unit * 0.024, rect.h + unit * 0.024);
      ctx.lineWidth = unit * 0.002;
      ctx.strokeRect(rect.x - unit * 0.024, rect.y - unit * 0.024, rect.w + unit * 0.048, rect.h + unit * 0.048);
    } else if (kind === "double") {
      ctx.strokeStyle = c.primary;
      ctx.lineWidth = unit * 0.008;
      ctx.strokeRect(rect.x - unit * 0.012, rect.y - unit * 0.012, rect.w + unit * 0.024, rect.h + unit * 0.024);
      ctx.strokeRect(rect.x - unit * 0.032, rect.y - unit * 0.032, rect.w + unit * 0.064, rect.h + unit * 0.064);
    } else if (kind === "lace" || kind === "pearl") {
      const shape = around(unit * 0.02);
      const count = Math.round((shape.w + shape.h) / (unit * (kind === "lace" ? 0.011 : 0.015)));
      for (const [x, y] of along(shape, count, 0)) {
        if (kind === "lace") {
          ctx.fillStyle = "#ffffff";
          ctx.beginPath(); ctx.arc(x, y, unit * 0.012, 0, TAU); ctx.fill();
          ctx.fillStyle = c.light;
          ctx.beginPath(); ctx.arc(x, y, unit * 0.004, 0, TAU); ctx.fill();
        } else {
          const g = ctx.createRadialGradient(x - unit * 0.004, y - unit * 0.004, 0, x, y, unit * 0.012);
          g.addColorStop(0, "#ffffff");
          g.addColorStop(1, "#d9cfd8");
          ctx.fillStyle = g;
          ctx.beginPath(); ctx.arc(x, y, unit * 0.011, 0, TAU); ctx.fill();
        }
      }
    } else if (kind === "tape") {
      const tape = (x, y, angle, color) => {
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(angle);
        ctx.globalAlpha = 0.82;
        ctx.fillStyle = color;
        ctx.fillRect(-unit * 0.1, -unit * 0.028, unit * 0.2, unit * 0.056);
        ctx.globalAlpha = 0.25;
        ctx.fillStyle = "#ffffff";
        for (let k = -4; k <= 4; k += 2) ctx.fillRect(k * unit * 0.022, -unit * 0.028, unit * 0.011, unit * 0.056);
        ctx.restore();
      };
      tape(rect.x + unit * 0.03, rect.y + unit * 0.01, -0.7, c.highlight);
      tape(rect.x + rect.w - unit * 0.03, rect.y + unit * 0.01, 0.7, c.light);
      tape(rect.x + rect.w - unit * 0.03, rect.y + rect.h - unit * 0.01, -0.7, c.highlight);
      tape(rect.x + unit * 0.03, rect.y + rect.h - unit * 0.01, 0.7, c.light);
    } else if (kind === "arch") {
      ctx.strokeStyle = "#b8936a";
      ctx.lineWidth = unit * 0.01;
      framePath(ctx, rect);
      ctx.stroke();
    } else if (kind === "xmas") {
      border(ctx, "wreath", around(unit * 0.02), { ...c, highlight: "#e23b4e", deep: "#9e1b2c" }, t);
    } else if (kind === "night") {
      ctx.strokeStyle = "#ffe9a8";
      ctx.lineWidth = unit * 0.004;
      ctx.strokeRect(rect.x - unit * 0.01, rect.y - unit * 0.01, rect.w + unit * 0.02, rect.h + unit * 0.02);
    } else if (kind === "cafe") {
      const rnd = random(5);
      const colors = ["#ff8fb1", "#ffd166", "#7ad3c4", "#b69cff", "#ffffff"];
      for (let k = 0; k < 90; k += 1) {  // 스프링클(사진 위는 피함)
        const x = rnd() * width, y = rnd() * height, angle = rnd() * TAU;
        if (x > rect.x - 4 && x < rect.x + rect.w + 4 && y > rect.y - 4 && y < rect.y + rect.h + 4) continue;
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(angle);
        ctx.fillStyle = colors[k % colors.length];
        fillRound(ctx, -unit * 0.012, -unit * 0.004, unit * 0.024, unit * 0.008, unit * 0.004);
        ctx.restore();
      }
      ctx.strokeStyle = "#ff8fb1";
      ctx.lineWidth = unit * 0.006;
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
    }
    ctx.restore();
    return paper;
  }

  window.debutkitDecorFx = { BORDERS, PARTICLES, CAPTIONS, MOTIONS, PENS, PRESETS, SHAPES, FRAMES, border, particles, caption, motion, strokes, outline, shapeOf, along,
    starPath, heartPath, snowflake, leaf, frameLayout, framePath, frame };
})();
