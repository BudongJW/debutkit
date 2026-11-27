// debutkit 후원 추첨 소품 연출: 캡슐 뽑기, 즉석 복권, 티켓 출력, 추첨기, 타로. draw.js보다 먼저 불러오고, draw.js가 공통 도구(kit)를 넘겨
// 연출 함수를 받는다. 카드, 룰렛과 같은 "방송 소품" 재질(크림 종이, 슬레이트 잉크, 핑크 인쇄, 금색은 희귀 전용, 딱딱한 그림자와 외곽선)과
// 같은 연출 순서(시작, 예고, 공개, 정리, 퇴장)를 따른다. 예고는 실제 결과와 같고(희귀만 금색), 희귀는 마지막에 천천히 공개(보여 주는 순서만 바꿈).
// 글은 textContent로만 넣는다. 단계 사이 시간은 kit.beat, 움직임 시간은 ms()로 빠른 모드를 반영. 움직임은 Web Animations(element.animate)
"use strict";

window.debutkitDrawProps = (kit) => {
  const { el, svgEl, beat, tone, emblemShapes, confetti, shake, nextFrame, revealOrder, INK, PAPER, GOLD, PINK } = kit;
  const PINK_LIGHT = kit.PINK_LIGHT || "#ffb3cb";
  const SLATE = "#3a4249";
  const ms = (value) => value * kit.pace();
  const tierOf = (item) => (item.rare ? "rare" : item.miss ? "miss" : "normal");
  const BAND = { rare: "희귀", miss: "꽝", normal: "일반" };
  const pad = (number) => String(number).padStart(2, "0");
  const chooseDesign = (value, designs) => (designs.includes(value) ? value : designs[0]);

  // 상품 이름 글자 크기(px): 칸 너비와 높이에 맞춰 한 줄 또는 두 줄. 설정의 크기 배율은 CSS(--name-scale)에서 곱함
  function fit(name, width, height, max, lines = 2) {
    const count = Math.max(1, [...name].length);
    let best = 0;
    for (let rows = 1; rows <= lines; rows++) best = Math.max(best, Math.min(width / Math.ceil(count / rows) / 1.04, height / (rows * 1.2)));
    return Math.max(9, Math.min(max, Math.floor(best)));
  }

  // 작은 글씨(17px 미만)는 획이 뭉치지 않게 본문 글꼴(굵은 제목 글꼴을 고른 경우만, CSS --name-small-font)
  function nameEl(name, width, height, max, lines = 2) {
    const size = fit(name, width, height, max, lines);
    const node = el("b", `dk-name fit${size < 17 ? " tiny" : ""}`, name);
    node.style.setProperty("--fit", `${size}px`);
    node.style.setProperty("--lines", String(lines));
    return node;
  }

  // 결과 칸 배치. table 항목: [최대 개수, 칸 너비, 칸 높이, 한 줄 개수, 소품 지름]
  function grid(count, table) {
    const [, w, h, perRow, d] = table.find((entry) => count <= entry[0]) || table[table.length - 1];
    return { w, h, d, cols: Math.min(perRow, count), rows: Math.ceil(count / perRow), big: count === 1 };
  }

  function tray(plan, className) {
    const node = el("div", `dk-tray ${className}`);
    for (const [name, value] of [["cols", plan.cols], ["cw", `${plan.w}px`], ["ch", `${plan.h}px`], ["d", `${plan.d || 0}px`]]) node.style.setProperty(`--${name}`, String(value));
    return node;
  }

  // 한 요소에서 다른 요소 자리로 날아갈 때 시작 위치(장면 표시 크기 반영). [x, y, 크기 비율]
  function offset(from, to) {
    const a = from.getBoundingClientRect();
    const b = to.getBoundingClientRect();
    const scale = kit.scale();
    return [(a.left + a.width / 2 - (b.left + b.width / 2)) / scale, (a.top + a.height / 2 - (b.top + b.height / 2)) / scale, a.width / Math.max(1, b.width)];
  }

  function animate(node, frames, duration, easing = "cubic-bezier(0.25, 0.7, 0.35, 1)") {
    const length = Math.max(16, ms(duration));
    const run = node.animate(frames, { duration: length, easing, fill: "both" });
    return new Promise((resolve) => {
      run.onfinish = resolve;
      setTimeout(resolve, length + 400);  // 어떤 경우에도 다음 단계로
    });
  }

  function barcode(seed, bars = 28) {  // 일련번호로 정해지는 막대(장식)
    const box = el("span", "barcode");
    let value = ((Number(seed) || 1) * 7919) % 233280;
    for (let i = 0; i < bars; i++) {
      value = (value * 9301 + 49297) % 233280;
      const bar = el("i");
      bar.style.width = `${1 + (value % 3)}px`;
      bar.style.marginRight = `${1 + (Math.floor(value / 7) % 3)}px`;
      box.appendChild(bar);
    }
    return box;
  }

  function percentEl(item, show) {
    return show ? el("small", "pct", `${item.percent}%`) : null;
  }

  function mark(body, eyes) {  // 작은 문양(복권 머리, 타로 뒷면)
    const svg = svgEl("svg", { viewBox: "30 4 60 82", class: "mark", "aria-hidden": "true" });
    svg.appendChild(emblemShapes(body, eyes));
    return svg;
  }

  // 희귀 공개: 들어 올려 흔든 뒤 천천히 열고 종이 조각(카드와 같은 순서)
  async function rareReveal(node, scene, openClass = "open") {
    node.classList.add("hint");
    await beat(650);
    node.classList.remove("hint");
    node.classList.add("slow", openClass);
    tone("rare");
    await beat(320);
    confetti(node);
    shake(scene);
    await beat(850);
  }

  // ================================================================ 캡슐 뽑기
  // 손잡이를 돌릴 때마다 캡슐이 굴러 나와 받침에 놓이고(캡슐 색이 등급 예고), 모두 나오면 열어 쪽지(상품)를 보여 준다
  const CAPSULE_DESIGNS = ["round", "box", "night", "mint", "lemon", "sky", "gold", "candy"];
  //: 모양(box: 네모 유리창, 아니면 둥근 돔)과 색
  const CAPSULE_LOOK = {
    round: { body: PINK, panel: PAPER, knob: PAPER, bar: PINK, cap: PINK, trim: null },
    box: { box: true, body: PAPER, panel: PINK_LIGHT, knob: PAPER, bar: PINK, cap: PINK, trim: PINK },
    night: { body: "#2b3238", panel: SLATE, knob: PINK, bar: PAPER, cap: PINK, trim: PINK },
    mint: { body: "#3fc1a5", panel: PAPER, knob: "#ffd84d", bar: "#ff8a5b", cap: "#ff8a5b", trim: null },
    lemon: { box: true, body: "#ffe066", panel: PAPER, knob: PAPER, bar: "#ff9f1c", cap: "#ff9f1c", trim: "#ff9f1c" },
    sky: { body: "#5aa9f0", panel: "#e8f4ff", knob: PAPER, bar: "#2f6fc4", cap: "#2f6fc4", trim: PAPER },
    gold: { body: "#d4a73a", panel: "#2b3238", knob: "#fff3c2", bar: "#8a6a1f", cap: "#8a6a1f", trim: "#fff3c2" },
    candy: { box: true, body: "#ff8fb8", panel: "#fff3f8", knob: "#7fd6c8", bar: "#b48cff", cap: "#b48cff", trim: "#7fd6c8" },
  };

  function miniCapsule(x, y, r, color, angle) {
    const group = svgEl("g", { transform: `translate(${x} ${y}) rotate(${angle})` });
    group.appendChild(svgEl("path", { d: `M${-r} 0 A${r} ${r} 0 0 1 ${r} 0 Z`, fill: color, stroke: INK, "stroke-width": 2.5 }));
    group.appendChild(svgEl("path", { d: `M${-r} 0 A${r} ${r} 0 0 0 ${r} 0 Z`, fill: PAPER, stroke: INK, "stroke-width": 2.5 }));
    return group;
  }

  function capsuleMachine(design) {
    const look = CAPSULE_LOOK[design];
    const box = Boolean(look.box);
    const svg = svgEl("svg", { viewBox: "0 0 200 336", class: "machine", "aria-hidden": "true" });
    const glass = box ? ["rect", { x: 26, y: 30, width: 148, height: 150, rx: 14 }] : ["circle", { cx: 100, cy: 106, r: 84 }];
    const defs = svgEl("defs");
    const clip = svgEl("clipPath", { id: `dk-glass-${design}` });
    clip.appendChild(svgEl(glass[0], glass[1]));
    defs.appendChild(clip);
    svg.appendChild(defs);
    svg.appendChild(svgEl("rect", { x: box ? 20 : 70, y: box ? 12 : 14, width: box ? 160 : 60, height: 22, rx: 6, fill: look.cap, stroke: INK, "stroke-width": 4 }));
    svg.appendChild(svgEl(glass[0], { ...glass[1], fill: "rgba(250, 247, 245, 0.3)" }));
    const balls = svgEl("g", { class: "balls" });
    const colors = [PINK, PINK_LIGHT, PAPER, SLATE, PINK_LIGHT, PINK, PAPER];
    const spots = box
      ? [[46, 162], [80, 164], [114, 162], [150, 160], [60, 132], [96, 134], [132, 130], [42, 104], [78, 106], [114, 102], [152, 100], [62, 76], [98, 74], [136, 70]]
      : [[52, 160], [86, 168], [120, 166], [152, 154], [36, 130], [70, 136], [104, 138], [138, 130], [166, 118], [56, 104], [90, 108], [124, 100], [154, 88], [76, 76]];
    spots.forEach(([x, y], index) => balls.appendChild(miniCapsule(x, y, 15, colors[index % colors.length], (index * 47) % 180)));
    const clipped = svgEl("g", { "clip-path": `url(#dk-glass-${design})` });
    clipped.appendChild(balls);
    svg.appendChild(clipped);
    svg.appendChild(svgEl(glass[0], { ...glass[1], fill: "none", stroke: INK, "stroke-width": 5 }));
    svg.appendChild(svgEl("path", { d: box ? "M44 52 L44 104" : "M46 80 A 62 62 0 0 1 84 38", fill: "none", stroke: "rgba(255, 255, 255, 0.85)",
      "stroke-width": 7, "stroke-linecap": "round" }));
    const lamp = svgEl("circle", { cx: 100, cy: box ? 12 : 14, r: 8, class: "lamp", stroke: INK, "stroke-width": 3 });
    svg.appendChild(lamp);
    svg.appendChild(svgEl("rect", { x: 50, y: 182, width: 100, height: 16, rx: 4, fill: INK }));
    svg.appendChild(svgEl("rect", { x: 22, y: 194, width: 156, height: 126, rx: 14, fill: look.body, stroke: INK, "stroke-width": 5 }));
    if (look.trim) svg.appendChild(svgEl("rect", { x: 30, y: 202, width: 140, height: 110, rx: 9, fill: "none", stroke: look.trim, "stroke-width": 3 }));
    svg.appendChild(svgEl("rect", { x: 40, y: 210, width: 120, height: 50, rx: 10, fill: look.panel, stroke: INK, "stroke-width": 3.5 }));
    svg.appendChild(svgEl("rect", { x: 136, y: 222, width: 8, height: 26, rx: 4, fill: INK }));
    svg.appendChild(svgEl("circle", { cx: 90, cy: 235, r: 21, fill: look.knob, stroke: INK, "stroke-width": 4 }));
    const crank = svgEl("g", { class: "crank" });
    crank.appendChild(svgEl("rect", { x: 69, y: 230, width: 42, height: 10, rx: 5, fill: look.bar, stroke: INK, "stroke-width": 3 }));
    crank.appendChild(svgEl("circle", { cx: 90, cy: 235, r: 4, fill: INK }));
    svg.appendChild(crank);
    svg.appendChild(svgEl("rect", { x: 64, y: 270, width: 72, height: 40, rx: 9, fill: INK }));
    const flap = svgEl("rect", { x: 69, y: 274, width: 62, height: 18, rx: 5, fill: "rgba(250, 247, 245, 0.55)" });
    svg.appendChild(flap);
    svg.appendChild(svgEl("rect", { x: 14, y: 318, width: 172, height: 14, rx: 4, fill: INK }));
    return { svg, crank, balls, flap };
  }

  function capsuleCell(item, slot, plan, showPercent, color) {
    const tier = tierOf(item);
    const cell = el("div", `dk-cap ${tier}`);
    if (tier === "normal") cell.style.setProperty("--cap", color);
    const shell = el("div", "shell");
    shell.append(el("i", "top"), el("i", "bottom"));
    const slip = el("div", "slip");
    slip.appendChild(el("span", "band", plan.big ? BAND[tier] : ""));
    const text = el("div", "text");
    text.appendChild(nameEl(item.name, plan.w - 18, plan.h * (plan.big ? 0.46 : 0.62), plan.big ? 40 : 24));
    slip.appendChild(text);
    const percent = percentEl(item, showPercent);
    if (percent) slip.appendChild(percent);
    cell.append(shell, slip);
    return { cell, shell, tier };
  }

  async function playCapsule(result, props, scene) {
    const design = chooseDesign(result.design, CAPSULE_DESIGNS);
    const total = result.draws.length;
    const plan = grid(total, [[1, 240, 164, 1, 124], [5, 150, 112, 5, 84], [12, 126, 90, 6, 66], [30, 104, 66, 10, 50]]);
    const names = result.prizes.map((prize) => prize.name);
    const stage = el("div", "dk-capsules");
    stage.dataset.design = design;
    const machine = capsuleMachine(design);
    const holder = el("div", "dk-machine");
    holder.appendChild(machine.svg);
    const shelf = tray(plan, "caps");
    const cells = revealOrder(result.draws).map((index, slot) => {
      const item = result.draws[index];
      return capsuleCell(item, slot, plan, result.show_percent, names.indexOf(item.name) % 2 ? PINK_LIGHT : PINK);
    });
    shelf.append(...cells.map((entry) => entry.cell));
    stage.append(holder, shelf);
    props.appendChild(stage);
    await beat(560);  // 시작: 머신 등장
    const step = total === 1 ? 950 : total <= 5 ? 640 : total <= 12 ? 340 : 190;
    const roll = total === 1 ? 860 : total <= 5 ? 700 : 520;
    for (const { cell, shell, tier } of cells) {
      if (tier === "rare") {  // 예고: 희귀 캡슐이 나오기 전 머신 등이 금색으로 켜지고 흔들림(실제 결과와 같음)
        holder.classList.add("hint");
        tone("crank");
        await beat(750);
      }
      animate(machine.crank, [{ transform: "rotate(0deg)" }, { transform: "rotate(360deg)" }], step * 0.9, "cubic-bezier(0.4, 0, 0.3, 1)");
      animate(machine.balls, [{ transform: "translate(0, 0)" }, { transform: "translate(3px, -5px) rotate(2deg)" }, { transform: "translate(-3px, -2px) rotate(-2deg)" },
        { transform: "translate(0, 0)" }], step * 0.9, "linear");
      tone("crank");
      await beat(step * 0.42);
      const [dx, dy] = offset(machine.flap, shell);
      cell.classList.add("out");
      animate(shell, [{ transform: `translate(${dx}px, ${dy}px) scale(0.35) rotate(0deg)` },
        { transform: `translate(${dx + 8}px, ${dy + 34}px) scale(0.85) rotate(110deg)`, offset: 0.24 },
        { transform: "translate(0px, 0px) scale(1) rotate(720deg)" }], roll, "cubic-bezier(0.3, 0.5, 0.35, 1)");
      setTimeout(() => tone("drop"), ms(roll * 0.8));
      await beat(tier === "rare" ? roll + 120 : step * 0.58);
      holder.classList.remove("hint");
    }
    await beat(roll * 0.6 + 280);
    for (const { cell, tier } of cells) {  // 공개: 일반, 꽝 캡슐을 먼저 빠르게 열고 희귀는 마지막에 천천히
      if (tier === "rare") continue;
      cell.classList.add("open");
      tone("pop");
      await beat(total > 12 ? 85 : total > 5 ? 150 : 280);
    }
    for (const { cell, tier } of cells) if (tier === "rare") await rareReveal(cell, scene);
    await beat(300);
  }

  // ================================================================ 즉석 복권
  // 복권 한 장에 추첨 횟수만큼 칸. 동전이 은박을 긁어 상품을 보여 준다. 일반, 꽝 칸은 한 줄씩 함께, 희귀 칸은 금색으로 빛난 뒤 마지막에 천천히
  const SCRATCH_DESIGNS = ["classic", "rough", "night", "pastel", "gold", "mint"];
  //: 긁는 막 색(금박 복권은 금색)
  const COATS = { gold: ["#b8902f", "#fff0b3", "#e2c066", "#9c7724"], silver: ["#a9b0b6", "#e8ebed", "#cdd3d7", "#959da4"] };

  function paintCoat(ctx, rect, coat = COATS.silver) {  // 은박: 금속 그러데이션, 가는 결, 잡음 점, 인쇄 글씨
    ctx.save();
    ctx.beginPath();
    ctx.rect(rect.x, rect.y, rect.w, rect.h);
    ctx.clip();
    const shine = ctx.createLinearGradient(rect.x, rect.y, rect.x + rect.w, rect.y + rect.h);
    shine.addColorStop(0, coat[0]);
    shine.addColorStop(0.42, coat[1]);
    shine.addColorStop(0.55, coat[2]);
    shine.addColorStop(1, coat[3]);
    ctx.fillStyle = shine;
    ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.32)";
    ctx.lineWidth = 1;
    for (let x = rect.x - rect.h; x < rect.x + rect.w; x += 6) {
      ctx.beginPath();
      ctx.moveTo(x, rect.y + rect.h);
      ctx.lineTo(x + rect.h, rect.y);
      ctx.stroke();
    }
    for (let i = 0; i < (rect.w * rect.h) / 45; i++) {
      ctx.fillStyle = Math.random() < 0.5 ? "rgba(30, 35, 39, 0.12)" : "rgba(255, 255, 255, 0.4)";
      ctx.fillRect(rect.x + Math.random() * rect.w, rect.y + Math.random() * rect.h, 1.6, 1.6);
    }
    if (rect.w >= 100 && rect.h >= 44) {
      ctx.fillStyle = "rgba(30, 35, 39, 0.3)";
      ctx.font = `${Math.round(Math.min(rect.h * 0.3, 30))}px "Black Han Sans", sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("긁는 곳", rect.x + rect.w / 2, rect.y + rect.h / 2 + 1);
    }
    ctx.restore();
  }

  // 칸 묶음을 지그재그로 긁는다. rough는 거친 붓질과 은박 부스러기, 끝나도 가장자리에 은박이 조금 남음
  function scratchArea(ctx, rects, coin, field, duration, rough) {
    const left = Math.min(...rects.map((rect) => rect.x));
    const right = Math.max(...rects.map((rect) => rect.x + rect.w));
    const top = Math.min(...rects.map((rect) => rect.y));
    const height = Math.max(...rects.map((rect) => rect.y + rect.h)) - top;
    const passes = Math.max(2, Math.min(5, Math.round(height / 24)));
    const radius = (height / passes) * 0.72 + 5;
    const points = [];
    for (let pass = 0; pass < passes; pass++) {
      const y = top + (height * (pass + 0.5)) / passes;
      const lane = (height / passes) * 0.3;
      const [from, to] = pass % 2 ? [right - 6, left + 6] : [left + 6, right - 6];
      points.push([from, y - lane], [to, y + lane]);
    }
    const lengths = [0];
    for (let i = 1; i < points.length; i++) lengths.push(lengths[i - 1] + Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]));
    const total = lengths[lengths.length - 1];
    const at = (distance) => {
      let i = 1;
      while (i < lengths.length - 1 && lengths[i] < distance) i++;
      const t = Math.min(1, Math.max(0, (distance - lengths[i - 1]) / Math.max(1, lengths[i] - lengths[i - 1])));
      return [points[i - 1][0] + (points[i][0] - points[i - 1][0]) * t, points[i - 1][1] + (points[i][1] - points[i - 1][1]) * t];
    };
    coin.style.setProperty("--size", `${Math.round(Math.max(30, Math.min(62, radius * 1.5)))}px`);
    coin.classList.add("on");
    const length = Math.max(120, ms(duration));
    tone("scratch", length / 1000);
    ctx.save();
    ctx.beginPath();
    for (const rect of rects) ctx.rect(rect.x, rect.y, rect.w, rect.h);
    ctx.clip();
    ctx.globalCompositeOperation = "destination-out";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    let done = 0;
    let flakes = 0;
    const erase = (distance) => {
      for (let d = done; d <= distance; d += rough ? 4 : 6) {
        const [x, y] = at(d);
        if (rough) {
          ctx.globalAlpha = 0.65 + Math.random() * 0.35;
          ctx.beginPath();
          ctx.arc(x + (Math.random() - 0.5) * radius * 0.7, y + (Math.random() - 0.5) * radius * 0.7, radius * (0.55 + Math.random() * 0.45), 0, Math.PI * 2);
          ctx.fill();
          if (Math.random() < 0.08 && flakes < 40) {
            flakes++;
            const flake = el("i", "flake");
            flake.style.left = `${x}px`;
            flake.style.top = `${y}px`;
            flake.style.setProperty("--fx", `${(Math.random() - 0.5) * 50}px`);
            field.appendChild(flake);
            setTimeout(() => flake.remove(), 900);
          }
        } else {
          ctx.beginPath();
          ctx.arc(x, y, radius, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      done = Math.max(done, distance);
    };
    return new Promise((resolve) => {
      const began = performance.now();
      let finished = false;
      const end = () => {
        if (finished) return;
        finished = true;
        erase(total);
        ctx.globalAlpha = 1;
        for (const rect of rects) {  // 깔끔하게: 칸 전체, 거칠게: 가운데만 확실히(가장자리에 은박이 조금 남음)
          if (rough) ctx.fillRect(rect.x + rect.w * 0.12, rect.y + rect.h * 0.16, rect.w * 0.76, rect.h * 0.68);
          else ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
        }
        ctx.restore();
        coin.classList.remove("on");
        resolve();
      };
      const frame = () => {
        if (finished) return;
        const t = Math.min(1, (performance.now() - began) / length);
        const distance = total * t;
        erase(distance);
        const [x, y] = at(distance);
        coin.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) rotate(${(-24 + Math.sin(t * 20) * 8).toFixed(1)}deg)`;
        if (t >= 1) return end();
        nextFrame(frame);
      };
      nextFrame(frame);
      setTimeout(end, length + 700);
    });
  }

  function coinEl() {
    const coin = el("div", "dk-coin");
    const svg = svgEl("svg", { viewBox: "-30 -30 60 60", "aria-hidden": "true" });
    svg.appendChild(svgEl("circle", { r: 27, fill: "#d5dade", stroke: INK, "stroke-width": 3.5 }));
    svg.appendChild(svgEl("circle", { r: 20, fill: "none", stroke: "#8f979e", "stroke-width": 2, "stroke-dasharray": "3 3" }));
    const face = emblemShapes("#8f979e", "#d5dade");
    face.setAttribute("transform", "scale(0.32) translate(-60,-46)");
    svg.appendChild(face);
    coin.appendChild(svg);
    return coin;
  }

  async function playScratch(result, props, scene) {
    const design = chooseDesign(result.design, SCRATCH_DESIGNS);
    const total = result.draws.length;
    const plan = grid(total, [[1, 420, 140, 1], [3, 210, 104, 3], [6, 184, 84, 3], [12, 156, 68, 4], [20, 134, 58, 5], [30, 118, 50, 6]]);
    const ticket = el("div", "dk-lotto");
    ticket.dataset.design = design;
    const head = el("div", "head");
    head.append(mark(PINK, design === "night" ? "#262d33" : INK), el("b", "", result.title || "후원 추첨"), el("span", "kind", "즉석 복권"),
      el("span", "serial", `No. ${String(result.seq || 1).padStart(6, "0")}`));
    const field = tray(plan, "field");
    const order = revealOrder(result.draws);
    const wins = order.map((index) => {
      const item = result.draws[index];
      const win = el("div", `win ${tierOf(item)}`);
      win.appendChild(nameEl(item.name, plan.w - 20, plan.h * 0.7, plan.big ? 54 : 28));
      const percent = percentEl(item, result.show_percent);
      if (percent) win.appendChild(percent);
      return win;
    });
    field.append(...wins);
    const canvas = el("canvas", "coat");
    const coin = coinEl();
    field.append(canvas, coin);
    const foot = el("div", "foot");
    foot.append(el("span", "", total > 1 ? `${total}칸을 모두 긁으면 결과 확인` : "칸을 긁으면 결과 확인"), barcode(result.seq));
    ticket.append(head, field, foot);
    props.appendChild(ticket);
    // 은박: 칸 위치에 맞춰 캔버스 하나에 칠한다(표시 크기만큼 선명하게)
    const density = Math.max(1, kit.scale()) * (window.devicePixelRatio || 1);
    const width = field.clientWidth;
    const height = field.clientHeight;
    canvas.width = Math.round(width * density);
    canvas.height = Math.round(height * density);
    const ctx = canvas.getContext("2d");
    ctx.scale(density, density);
    const rects = wins.map((win) => ({ x: win.offsetLeft, y: win.offsetTop, w: win.offsetWidth, h: win.offsetHeight }));
    rects.forEach((rect) => paintCoat(ctx, rect, design === "gold" ? COATS.gold : COATS.silver));
    await beat(600);  // 시작: 복권 등장
    const rare = wins.map((win, index) => index).filter((index) => wins[index].classList.contains("rare"));
    if (rare.length) {  // 예고: 희귀 칸 둘레만 금색 빛
      for (const index of rare) wins[index].classList.add("hint");
      await beat(900);
    } else {
      await beat(250);
    }
    const rows = new Map();
    wins.forEach((win, index) => {
      if (win.classList.contains("rare")) return;
      const row = Math.round(rects[index].y);
      rows.set(row, [...(rows.get(row) || []), index]);
    });
    for (const indexes of rows.values()) {  // 공개: 일반, 꽝 칸은 한 줄씩 함께
      await scratchArea(ctx, indexes.map((index) => rects[index]), coin, field, total === 1 ? 1500 : 420 + indexes.length * 90, design === "rough");
      for (const index of indexes) wins[index].classList.add("open");
      tone("flip");
      await beat(total > 12 ? 60 : 160);
    }
    for (const index of rare) {  // 희귀 칸은 하나씩 천천히
      await scratchArea(ctx, [rects[index]], coin, field, total === 1 ? 2000 : 1300, design === "rough");
      wins[index].classList.remove("hint");
      wins[index].classList.add("open", "won");
      tone("rare");
      confetti(wins[index]);
      shake(scene);
      await beat(900);
    }
    await beat(300);
  }

  // ================================================================ 티켓 출력
  // 출력기의 등이 등급 색으로 켜진 뒤(예고, 희귀는 금색으로 깜빡이며 흔들림) 티켓이 한 줄씩 인쇄되어 나온다(공개).
  // 여러 장이면 찢어서 옆에 차례로 놓는다
  const TICKET_DESIGNS = ["stub", "receipt", "coupon", "concert", "movie", "boarding", "gift", "shop"];
  //: 디자인마다 바탕 모양(입장권, 영수증, 교환권)과 교환권 위쪽 이름
  const TICKET_BASE = { stub: "stub", receipt: "receipt", coupon: "coupon", concert: "stub", movie: "stub", boarding: "coupon", gift: "coupon", shop: "receipt" };
  const COUPON_LABEL = { coupon: "교환권", boarding: "탑승권", gift: "상품권" };
  const TICKET_SIZE = {  // [인쇄 크기(1장), 인쇄 크기(여러 장), 옆에 놓는 칸 배치]
    stub: [[330, 156], [232, 110], [[5, 200, 94, 5], [12, 160, 76, 6], [30, 118, 58, 10]]],
    coupon: [[330, 156], [232, 110], [[5, 200, 94, 5], [12, 160, 76, 6], [30, 118, 58, 10]]],
    receipt: [[216, 268], [160, 200], [[5, 128, 160, 5], [12, 104, 130, 6], [30, 80, 100, 10]]],
  };

  function zigzag(width, height, tooth) {  // 영수증 위아래 톱니(px 다각형)
    const top = [];
    const bottom = [];
    const count = Math.max(4, Math.round(width / tooth));
    for (let i = 0; i <= count; i++) {
      const x = ((width * i) / count).toFixed(1);
      top.push(`${x}px ${i % 2 ? tooth * 0.55 : 0}px`);
      bottom.push(`${(width - (width * i) / count).toFixed(1)}px ${height - (i % 2 ? tooth * 0.55 : 0)}px`);
    }
    return `polygon(${[...top, ...bottom].join(", ")})`;
  }

  function ticketEl(item, slot, total, design, size, showPercent, title) {
    const [width, height] = size;
    const tier = tierOf(item);
    const base = TICKET_BASE[design] || "stub";
    const node = el("div", `dk-ticket ${base}${base === design ? "" : ` ${design}`} ${tier}${width < 150 ? " small" : ""}`);
    node.style.setProperty("--tw", `${width}px`);
    node.style.setProperty("--th", `${height}px`);
    const paper = el("div", "paper");
    const number = `${pad(slot + 1)}/${pad(total)}`;
    if (base === "stub") {
      const stub = el("div", "stub");
      stub.appendChild(el("span", "", `No.${pad(slot + 1)}`));
      const main = el("div", "main");
      main.append(el("span", "label", tier === "normal" ? title : BAND[tier]), nameEl(item.name, width * 0.66, height * 0.5, 44));
      const percent = percentEl(item, showPercent);
      if (percent) main.appendChild(percent);
      paper.append(stub, main);
    } else if (base === "receipt") {
      paper.style.clipPath = zigzag(width, height, Math.max(7, width / 18));
      const head = el("div", "row");
      head.append(el("span", "", title), el("span", "", number));
      const foot = el("div", "row");
      foot.append(el("span", "", BAND[tier]), el("span", "", showPercent ? `${item.percent}%` : ""));
      paper.append(head, el("i", "rule"), nameEl(item.name, width * 0.82, height * 0.4, 40, 3), el("i", "rule"), foot, barcode(item.percent * 100 + slot));
    } else {
      const head = el("div", "row");
      head.append(el("span", "label", COUPON_LABEL[design] || "교환권"), el("span", "", number));
      paper.append(head, nameEl(item.name, width * 0.8, height * 0.48, 44));
      const percent = percentEl(item, showPercent);
      if (percent) paper.appendChild(percent);
    }
    node.appendChild(paper);
    return node;
  }

  function printerEl(design, size) {
    const box = el("div", "dk-printer");
    box.dataset.design = design;
    box.style.setProperty("--pw", `${size[0]}px`);
    box.style.setProperty("--ph", `${size[1]}px`);
    const mouth = el("div", "mouth");
    const body = el("div", "body");
    body.append(el("i", "slot"), el("i", "lamp"), el("i", "vent"), el("span", "label", "출력"));
    box.append(mouth, body);
    return { box, mouth };
  }

  async function playTicket(result, props, scene) {
    const design = chooseDesign(result.design, TICKET_DESIGNS);
    const total = result.draws.length;
    const single = total === 1;
    const [big, print, table] = TICKET_SIZE[TICKET_BASE[design] || "stub"];
    const size = single ? big : print;
    const plan = single ? null : grid(total, table);
    const stage = el("div", "dk-tickets");
    const machine = printerEl(design, size);
    stage.appendChild(machine.box);
    const order = revealOrder(result.draws);
    let slots = [];
    if (plan) {
      const shelf = tray(plan, "tickets");
      slots = order.map((index, slot) => {
        const node = ticketEl(result.draws[index], slot, total, design, [plan.w, plan.h], result.show_percent, result.title || "후원 추첨");
        node.classList.add("waiting");
        return node;
      });
      shelf.append(...slots);
      stage.appendChild(shelf);
    }
    props.appendChild(stage);
    await beat(560);  // 시작: 출력기 등장
    const feed = single ? 1500 : total <= 5 ? 760 : total <= 12 ? 460 : 260;
    for (const [slot, index] of order.entries()) {
      const item = result.draws[index];
      const tier = tierOf(item);
      machine.box.dataset.lamp = tier;  // 예고: 등 색
      if (tier === "rare") {
        machine.box.classList.add("hint");
        tone("crank");
        await beat(850);
      } else {
        await beat(single ? 300 : 90);
      }
      const printed = ticketEl(item, slot, total, design, size, result.show_percent, result.title || "후원 추첨");
      machine.mouth.replaceChildren(printed);
      const length = feed * (tier === "rare" ? 1.5 : 1);
      tone("print", ms(length) / 1000);
      await animate(printed, [{ transform: "translateY(100%)" }, { transform: "translateY(0)" }], length, `steps(${single ? 16 : 9}, end)`);
      machine.box.classList.remove("hint");
      if (tier === "rare") {
        printed.classList.add("won");
        tone("rare");
        confetti(printed);
        shake(scene);
        await beat(700);
      }
      if (plan) {  // 찢어서 옆 자리로
        const target = slots[slot];
        const [dx, dy, ratio] = offset(printed, target);
        target.classList.remove("waiting");
        if (tier === "rare") target.classList.add("won");
        tone("tick");
        animate(target, [{ transform: `translate(${dx}px, ${dy}px) scale(${ratio}) rotate(-5deg)` }, { transform: "translate(0px, 0px) scale(1) rotate(0deg)" }],
          440, "cubic-bezier(0.3, 0.7, 0.3, 1.1)");
        machine.mouth.replaceChildren();
        await beat(Math.min(300, feed * 0.55));
      }
    }
    delete machine.box.dataset.lamp;
    await beat(plan ? 520 : 300);
  }

  // ================================================================ 추첨기
  // 손잡이를 돌리면 팔각 통이 돌고 공이 떨어진다. 공 색이 등급(희귀 금색, 일반 핑크, 꽝 슬레이트)이고, 이름표로 상품을 보여 준다.
  // 희귀 공이 나오면 종소리
  const DRUM_DESIGNS = ["classic", "wood", "night", "mint", "gold"];
  const DRUM_LOOK = {
    classic: { face: PINK, slat: PAPER, leg: PAPER, hub: PAPER, handle: PAPER, dish: PINK_LIGHT },
    mint: { face: "#3fc1a5", slat: PAPER, leg: "#2a8f79", hub: "#ffd84d", handle: "#ffd84d", dish: "#c9f1e7" },
    gold: { face: "#d4a73a", slat: "#fff3c2", leg: "#8a6a1f", hub: "#fff3c2", handle: "#fff3c2", dish: "#f3dc9c" },
    wood: { face: "#c98d5a", slat: "#e7c49a", leg: "#8a5a35", hub: PAPER, handle: PINK, dish: "#e7c49a" },
    night: { face: "#2b3238", slat: PINK, leg: SLATE, hub: PINK, handle: PINK, dish: SLATE },
  };
  const AXLE = [150, 128];
  const HOLE_Y = AXLE[1] + 92;  // 공이 나오는 구멍(통이 멈추면 아래쪽). CSS .dk-drum .hole 위치와 같음
  const DISH_Y = 246;  // 받침 접시 가운데

  function octagon(radius) {
    return Array.from({ length: 8 }, (_, k) => {
      const angle = ((22.5 + k * 45) * Math.PI) / 180;
      return `${(AXLE[0] + Math.cos(angle) * radius).toFixed(1)},${(AXLE[1] + Math.sin(angle) * radius).toFixed(1)}`;
    }).join(" ");
  }

  function drumMachine(design) {
    const look = DRUM_LOOK[design];
    const svg = svgEl("svg", { viewBox: "0 0 300 290", class: "drum-svg", "aria-hidden": "true" });
    const leg = (x2, y2) => [svgEl("line", { x1: AXLE[0], y1: AXLE[1], x2, y2, stroke: INK, "stroke-width": 15, "stroke-linecap": "round" }),
      svgEl("line", { x1: AXLE[0], y1: AXLE[1], x2, y2, stroke: look.leg, "stroke-width": 8, "stroke-linecap": "round" })];
    svg.append(...leg(62, 262), ...leg(238, 262));
    svg.appendChild(svgEl("rect", { x: 30, y: 258, width: 240, height: 18, rx: 5, fill: look.leg, stroke: INK, "stroke-width": 4 }));
    svg.appendChild(svgEl("path", { d: "M106 232 L194 232 L184 256 L116 256 Z", fill: look.dish, stroke: INK, "stroke-width": 4, "stroke-linejoin": "round" }));
    const drum = svgEl("g", { class: "drum" });
    drum.appendChild(svgEl("polygon", { points: octagon(104), fill: look.face, stroke: INK, "stroke-width": 6, "stroke-linejoin": "round" }));
    if (design === "wood") {  // 나뭇결
      for (const radius of [92, 82]) drum.appendChild(svgEl("polygon", { points: octagon(radius), fill: "none", stroke: "#a8693b", "stroke-width": 1.6 }));
    }
    drum.appendChild(svgEl("polygon", { points: octagon(68), fill: "none", stroke: INK, "stroke-width": 7, "stroke-linejoin": "round" }));
    drum.appendChild(svgEl("polygon", { points: octagon(68), fill: "none", stroke: look.slat, "stroke-width": 3, "stroke-linejoin": "round" }));
    for (let k = 0; k < 8; k++) {
      const angle = ((22.5 + k * 45) * Math.PI) / 180;
      const [cos, sin] = [Math.cos(angle), Math.sin(angle)];
      drum.appendChild(svgEl("line", { x1: AXLE[0] + cos * 68, y1: AXLE[1] + sin * 68, x2: AXLE[0] + cos * 104, y2: AXLE[1] + sin * 104, stroke: INK, "stroke-width": 3 }));
      drum.appendChild(svgEl("circle", { cx: AXLE[0] + cos * 96, cy: AXLE[1] + sin * 96, r: 3.6, fill: PAPER, stroke: INK, "stroke-width": 1.8 }));
    }
    drum.appendChild(svgEl("ellipse", { cx: AXLE[0], cy: HOLE_Y, rx: 10, ry: 6, fill: INK }));  // 공이 나오는 구멍(멈추면 아래)
    drum.appendChild(svgEl("line", { x1: AXLE[0], y1: AXLE[1], x2: AXLE[0] + 64, y2: AXLE[1] - 40, stroke: INK, "stroke-width": 11, "stroke-linecap": "round" }));
    drum.appendChild(svgEl("line", { x1: AXLE[0], y1: AXLE[1], x2: AXLE[0] + 64, y2: AXLE[1] - 40, stroke: look.slat, "stroke-width": 4.5, "stroke-linecap": "round" }));
    drum.appendChild(svgEl("circle", { cx: AXLE[0] + 64, cy: AXLE[1] - 40, r: 11, fill: look.handle, stroke: INK, "stroke-width": 4 }));
    drum.appendChild(svgEl("circle", { cx: AXLE[0], cy: AXLE[1], r: 20, fill: look.hub, stroke: INK, "stroke-width": 4 }));
    const face = emblemShapes(design === "night" ? INK : PINK, design === "night" ? PAPER : INK);
    face.setAttribute("transform", `translate(${AXLE[0]} ${AXLE[1]}) scale(0.27) translate(-60,-45)`);
    drum.appendChild(face);
    svg.appendChild(drum);
    return { svg, drum };
  }

  function ballCell(item, plan, showPercent, color) {
    const tier = tierOf(item);
    const cell = el("div", `dk-ball ${tier}`);
    if (tier === "normal") cell.style.setProperty("--ball", color);
    const ball = el("div", "ball");
    const tag = el("div", "tag");
    tag.appendChild(nameEl(item.name, plan.w - 18, plan.h - plan.d - 14, plan.big ? 36 : plan.w < 110 ? 17 : 22, plan.big || plan.w >= 110 ? 2 : 1));
    const percent = percentEl(item, showPercent);
    if (percent) tag.appendChild(percent);
    cell.append(ball, tag);
    return { cell, ball, tier };
  }

  async function playDrum(result, props, scene) {
    const design = chooseDesign(result.design, DRUM_DESIGNS);
    const total = result.draws.length;
    const plan = grid(total, [[1, 260, 150, 1, 78], [5, 160, 128, 5, 56], [12, 132, 104, 6, 46], [30, 104, 80, 10, 36]]);
    const names = result.prizes.map((prize) => prize.name);
    const stage = el("div", "dk-drums");
    stage.dataset.design = design;
    const machine = drumMachine(design);
    const holder = el("div", "dk-drum");
    const hole = el("i", "hole");
    holder.append(machine.svg, hole);
    const shelf = tray(plan, "balls");
    const cells = revealOrder(result.draws).map((index) => {
      const item = result.draws[index];
      return ballCell(item, plan, result.show_percent, names.indexOf(item.name) % 2 ? PINK_LIGHT : PINK);
    });
    shelf.append(...cells.map((entry) => entry.cell));
    stage.append(holder, shelf);
    props.appendChild(stage);
    await beat(560);  // 시작: 추첨기 등장
    const perTurn = total > 12 ? 2 : 1;  // 많으면 한 바퀴에 두 개
    const spin = total === 1 ? 1900 : total <= 5 ? 950 : total <= 12 ? 640 : 520;
    let angle = 0;
    for (const [slot, { cell, ball, tier }] of cells.entries()) {
      if (slot % perTurn === 0) {
        const turns = total === 1 ? 2 : 1;
        for (let i = 0; i < turns * 6; i++) setTimeout(() => tone("tick"), ms((spin * i) / (turns * 6)));
        await animate(machine.drum, [{ transform: `rotate(${angle}deg)` }, { transform: `rotate(${angle + 360 * turns}deg)` }], spin, "cubic-bezier(0.45, 0, 0.35, 1)");
        angle += 360 * turns;
      } else {
        await beat(120);
      }
      // 구멍에서 받침 접시로 떨어져 한 번 튄 뒤 자리로 굴러감
      const [hx, hy] = offset(hole, ball);
      const fall = ((DISH_Y - HOLE_Y) / 290) * (machine.svg.getBoundingClientRect().height / kit.scale());
      cell.classList.add("out");
      const travel = total === 1 ? 1000 : total <= 5 ? 800 : 560;
      animate(ball, [{ transform: `translate(${hx}px, ${hy}px) scale(0.55)` },
        { transform: `translate(${hx}px, ${hy + fall}px) scale(0.9)`, offset: 0.22 },
        { transform: `translate(${hx}px, ${hy + fall - 16}px) scale(0.9)`, offset: 0.32 },
        { transform: `translate(${hx}px, ${hy + fall}px) scale(0.9)`, offset: 0.4 },
        { transform: "translate(0px, 0px) scale(1) rotate(360deg)" }], travel, "cubic-bezier(0.35, 0.3, 0.4, 1)");
      setTimeout(() => tone("drop"), ms(travel * 0.22));
      if (tier === "rare") {  // 예고: 금색 공이 나오면 종소리. 이름표는 잠시 뒤 천천히
        await beat(travel);
        tone("bell");
        await rareReveal(cell, scene);
      } else {
        await beat(perTurn > 1 ? travel * 0.5 : travel * 0.8);
        cell.classList.add("open");
        tone("pop");
      }
    }
    await beat(500);
  }

  // ================================================================ 타로
  // 카드 더미를 두 번 섞고 추첨 횟수만큼 한 장씩 펼친다. 희귀 카드만 금색 빛(예고), 일반과 꽝을 먼저 뒤집고 희귀는 마지막에 천천히.
  // 앞면은 로마 숫자, 등급 그림(희귀 해, 일반 별, 꽝 달), 상품 이름. 오늘의 한마디는 서버가 고른 문장을 결과 판 아래에 표시(draw.js)
  const TAROT_DESIGNS = ["night", "sun", "pink"];
  const NUMERALS = [["X", 10], ["IX", 9], ["V", 5], ["IV", 4], ["I", 1]];
  const roman = (number) => NUMERALS.reduce((text, [mark_, value]) => {
    while (number >= value) {
      text += mark_;
      number -= value;
    }
    return text;
  }, "");
  const STAR = "M30 8 L36 24 L53 24 L39 34 L44 51 L30 41 L16 51 L21 34 L7 24 L24 24 Z";

  function tarotBack(design) {
    const svg = svgEl("svg", { viewBox: "0 0 100 172", preserveAspectRatio: "none", class: "art", "aria-hidden": "true" });
    const line = design === "night" ? PAPER : INK;
    svg.appendChild(svgEl("rect", { x: 7, y: 7, width: 86, height: 158, rx: 4, fill: "none", stroke: line, "stroke-width": 1.6 }));
    svg.appendChild(svgEl("rect", { x: 11.5, y: 11.5, width: 77, height: 149, rx: 2, fill: "none", stroke: line, "stroke-width": 0.8 }));
    if (design === "night") {  // 초승달과 별
      svg.appendChild(svgEl("path", { d: "M58 64 A 24 24 0 1 0 58 108 A 19 19 0 1 1 58 64 Z", fill: PAPER, stroke: INK, "stroke-width": 1.5 }));
      for (const [x, y, s] of [[66, 56, 5], [72, 90, 3.5], [30, 40, 3], [70, 130, 4], [28, 136, 3]]) {
        svg.appendChild(svgEl("path", { d: `M${x} ${y - s} Q${x + s * 0.2} ${y - s * 0.2} ${x + s} ${y} Q${x + s * 0.2} ${y + s * 0.2} ${x} ${y + s} Q${x - s * 0.2} ${y + s * 0.2} ${x - s} ${y} Q${x - s * 0.2} ${y - s * 0.2} ${x} ${y - s} Z`,
          fill: s > 4 ? PINK : PAPER }));
      }
    } else if (design === "sun") {  // 해
      for (let k = 0; k < 12; k++) {
        const angle = (k * 30 * Math.PI) / 180;
        const tip = [50 + Math.cos(angle) * 34, 86 + Math.sin(angle) * 34];
        const left = [50 + Math.cos(angle - 0.2) * 20, 86 + Math.sin(angle - 0.2) * 20];
        const right = [50 + Math.cos(angle + 0.2) * 20, 86 + Math.sin(angle + 0.2) * 20];
        svg.appendChild(svgEl("path", { d: `M${left.join(" ")} L${tip.join(" ")} L${right.join(" ")} Z`, fill: INK }));
      }
      svg.appendChild(svgEl("circle", { cx: 50, cy: 86, r: 18, fill: PINK, stroke: INK, "stroke-width": 2.5 }));
    } else {  // 핑크 문양: 가운데 타원 안 문양
      svg.appendChild(svgEl("ellipse", { cx: 50, cy: 86, rx: 27, ry: 36, fill: PAPER, stroke: INK, "stroke-width": 2.5 }));
      const face = emblemShapes(PINK, INK);
      face.setAttribute("transform", "translate(50 86) scale(0.5) translate(-60,-46)");
      svg.appendChild(face);
    }
    return svg;
  }

  function tarotSymbol(tier) {
    const svg = svgEl("svg", { viewBox: "0 0 60 60", class: "symbol", "aria-hidden": "true" });
    if (tier === "rare") {  // 해
      for (let k = 0; k < 8; k++) {
        const angle = (k * 45 * Math.PI) / 180;
        const point = (radius, turn) => `${(30 + Math.cos(angle + turn) * radius).toFixed(1)} ${(30 + Math.sin(angle + turn) * radius).toFixed(1)}`;
        svg.appendChild(svgEl("path", { d: `M${point(16, -0.32)} L${point(28, 0)} L${point(16, 0.32)} Z`, fill: GOLD, stroke: INK, "stroke-width": 2, "stroke-linejoin": "round" }));
      }
      svg.appendChild(svgEl("circle", { cx: 30, cy: 30, r: 14, fill: GOLD, stroke: INK, "stroke-width": 2.5 }));
    } else if (tier === "normal") {  // 별
      svg.appendChild(svgEl("path", { d: STAR, fill: PINK, stroke: INK, "stroke-width": 2.5, "stroke-linejoin": "round" }));
    } else {  // 달
      svg.appendChild(svgEl("path", { d: "M36 10 A 21 21 0 1 0 36 50 A 16 16 0 1 1 36 10 Z", fill: "#c9c3bd", stroke: INK, "stroke-width": 2.5 }));
    }
    return svg;
  }

  function tarotPlan(count) {
    const [w, h, rows] = count === 1 ? [150, 256, 1] : count <= 7 ? [118, 202, 1] : count <= 15 ? [92, 158, 2] : [72, 124, 3];
    const perRow = Math.ceil(count / rows);
    const spots = [];
    for (let i = 0; i < count; i++) {
      const row = Math.floor(i / perRow);
      const inRow = Math.min(perRow, count - row * perRow);
      const d = (i % perRow) - (inRow - 1) / 2;
      spots.push(rows === 1 ? { x: d * w * 1.1, y: d * d * 7, r: d * 3.5 } : { x: d * w * 1.08, y: row * h * 1.08, r: 0 });
    }
    const minX = Math.min(...spots.map((spot) => spot.x));
    const maxX = Math.max(...spots.map((spot) => spot.x));
    const maxY = Math.max(...spots.map((spot) => spot.y));
    for (const spot of spots) {
      spot.x += 24 - minX;
      spot.y += 12;
    }
    const width = maxX - minX + w + 48;
    const height = maxY + h + 34;
    return { w, h, spots, width, height, deckX: width / 2 - w / 2, deckY: Math.max(12, (height - h) / 2) };
  }

  function tarotCard(item, slot, plan, design, showPercent) {
    const tier = tierOf(item);
    const spot = plan.spots[slot];
    const node = el("div", `dk-card tarot ${tier}`);
    node.dataset.design = design;
    const vars = { "--w": `${plan.w}px`, "--h": `${plan.h}px`, "--x": `${spot.x}px`, "--y": `${spot.y}px`, "--r": `${spot.r}deg`, "--i": 0, "--z": slot + 1,
      "--deck-x": `${plan.deckX}px`, "--deck-y": `${plan.deckY}px` };
    for (const [name, value] of Object.entries(vars)) node.style.setProperty(name, value);
    const inner = el("div", "inner");
    const back = el("div", "face back");
    back.appendChild(tarotBack(design));
    const front = el("div", "face front");
    front.append(el("span", "numeral", roman(slot + 1)), tarotSymbol(tier));
    const banner = el("div", "banner");
    banner.appendChild(nameEl(item.name, plan.w * 0.76, plan.h * 0.24, Math.round(plan.h * 0.11)));
    front.appendChild(banner);
    const percent = percentEl(item, showPercent);
    if (percent) front.appendChild(percent);
    inner.append(back, front);
    node.appendChild(inner);
    return node;
  }

  async function playTarot(result, props, scene) {
    const design = chooseDesign(result.design, TAROT_DESIGNS);
    const total = result.draws.length;
    const plan = tarotPlan(total);
    const table = el("div", "dk-deck dk-spread");
    table.style.width = `${plan.width}px`;
    table.style.height = `${plan.height}px`;
    const pile = el("div", "dk-pile");
    pile.dataset.design = design;
    for (const [name, value] of [["--w", `${plan.w}px`], ["--h", `${plan.h}px`], ["--x", `${plan.deckX}px`], ["--y", `${plan.deckY}px`]]) pile.style.setProperty(name, value);
    const stack = Array.from({ length: 7 }, (_, i) => {
      const sheet = el("div", "face back");
      sheet.appendChild(tarotBack(design));
      sheet.style.transform = `translate(${-i * 1.6}px, ${-i * 1.6}px)`;
      return sheet;
    });
    pile.append(...stack);
    const cards = revealOrder(result.draws).map((index, slot) => tarotCard(result.draws[index], slot, plan, design, result.show_percent));
    table.append(pile, ...cards);
    props.appendChild(table);
    await beat(520);  // 시작: 더미 등장
    for (let round = 0; round < 2; round++) {  // 섞기: 두 무더기로 나눴다가 엇갈려 합침
      tone("shuffle");
      await Promise.all(stack.map((sheet, i) => {
        const base = `translate(${-i * 1.6}px, ${-i * 1.6}px)`;
        const side = i % 2 ? 1 : -1;
        return animate(sheet, [{ transform: base }, { transform: `translate(${side * plan.w * 0.62}px, ${-8 - i}px) rotate(${side * 9}deg)` }, { transform: base }],
          560, "cubic-bezier(0.45, 0, 0.35, 1)");
      }));
    }
    const step = total === 1 ? 420 : total <= 7 ? 300 : total <= 15 ? 150 : 95;
    for (const [n, node] of cards.entries()) {  // 펼치기: 한 장씩
      node.classList.add("dealt");
      tone("flip");
      if (n >= total - stack.length + 1 && stack.length > 1) stack.pop().remove();
      await beat(step);
    }
    pile.classList.add("gone");
    await beat(500);
    const rares = cards.filter((node) => node.classList.contains("rare"));
    if (rares.length) {  // 예고: 희귀 카드만 금색 빛
      for (const node of rares) node.classList.add("hint");
      await beat(1000);
    } else {
      await beat(250);
    }
    for (const node of cards) {  // 공개
      if (node.classList.contains("rare")) continue;
      node.classList.add("open");
      tone("flip");
      await beat(total > 12 ? 110 : 240);
    }
    for (const node of rares) {
      node.classList.remove("hint");
      node.classList.add("lift");
      await beat(500);
      node.classList.add("slow", "open");
      tone("rare");
      await beat(300);
      confetti(node);
      shake(scene);
      await beat(900);
      node.classList.remove("lift");
    }
    await beat(300);
  }

  return { capsule: playCapsule, scratch: playScratch, ticket: playTicket, drum: playDrum, tarot: playTarot };
};
