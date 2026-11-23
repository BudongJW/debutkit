// debutkit 후원 추첨 연출(OBS 브라우저 소스, 권장 1920x1080). /live?feeds=draw 로 추첨 결과를 받아 차례로 연출한다.
// 콘셉트 "방송 소품": 고양이 귀 마이크 문양을 찍은 실물 카드와 무대용 상품 룰렛. 소품과 하단 띠만 화면 아래쪽에 놓는다.
// 연출 순서: 시작(띠, 소품 등장), 예고(희귀 카드만 금색 빛, 실제 결과와 같음), 공개(일반 카드 빠르게, 희귀 카드 마지막 천천히), 정리(결과 판), 퇴장.
// 뽑기는 서버가 하고 이 화면은 받은 결과를 보여 주기만 한다(모든 화면이 같은 결과). 글은 textContent로만 넣는다.
// 시청자 참여 추첨(/live의 raffle): 모집 중에는 하단 모집 띠와 참가자 이름, 결과는 당첨 카드나 순서표로 같은 차례 안에서 연출.
// 주소: ?style=card, ?style=wheel 연출 고정. ?sample=card(또는 wheel)&count=11&bg=light 미리보기(이 화면에서만). ?sound 효과음 강제
"use strict";

(() => {
  const root = document.getElementById("draw");
  const raffleRoot = document.getElementById("raffle");
  const params = new URLSearchParams(location.search);
  const forced = params.get("style");
  const STYLES = ["card", "wheel"];
  const PLATFORMS = (window.debutkit && window.debutkit.PLATFORMS) || {};
  const NS = "http://www.w3.org/2000/svg";
  const INK = "#1e2327";
  const PAPER = "#faf7f5";
  const queue = [];
  let busy = false;

  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
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
  // 글꼴을 다 불러온 뒤 연출(공개 도중 글꼴이 바뀌어 보이지 않게)
  const fontsReady = document.fonts
    ? Promise.all(['40px "Black Han Sans"', '600 20px "Pretendard"', '700 20px "Pretendard"'].map((font) => document.fonts.load(font))).catch(() => null)
    : Promise.resolve();

  // 고양이 귀 마이크 문양(assets/brand의 기호와 같은 도형). 그룹으로 만들어 카드 뒷면과 룰렛 가운데에 사용
  function emblemShapes(body, eyes) {
    const group = svgEl("g");
    group.appendChild(svgEl("path", { d: "M38 32 L42 9 L56 21 Z M82 32 L78 9 L64 21 Z", fill: body, stroke: body, "stroke-width": 6, "stroke-linejoin": "round" }));
    group.appendChild(svgEl("rect", { x: 36, y: 18, width: 48, height: 64, rx: 24, fill: body }));
    group.appendChild(svgEl("rect", { x: 45.5, y: 40, width: 8, height: 13, rx: 4, fill: eyes }));
    group.appendChild(svgEl("rect", { x: 66.5, y: 40, width: 8, height: 13, rx: 4, fill: eyes }));
    return group;
  }

  function emblem(body, eyes) {
    const svg = svgEl("svg", { viewBox: "30 4 60 82", class: "emblem", "aria-hidden": "true" });
    svg.appendChild(emblemShapes(body, eyes));
    return svg;
  }

  // ---------------------------------------------------------------- 효과음(브라우저에서 합성. 음원 파일 없음)
  let audio = null;
  let soundOn = false;
  function tone(kind) {
    if (!soundOn) return;
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
      if (kind === "tick") note("square", 2300, 0, 0.025, 0.04);
      else if (kind === "start") note("triangle", 520, 0, 0.12, 0.07);
      else if (kind === "flip") { note("triangle", 880, 0, 0.07, 0.06); note("triangle", 1320, 0.035, 0.06, 0.04); }
      else if (kind === "rare") [1318.5, 1975.5, 2637].forEach((frequency, index) => note("sine", frequency, index * 0.09, 1.5, 0.1));
      else if (kind === "done") { note("sine", 784, 0, 0.25, 0.07); note("sine", 1046.5, 0.12, 0.4, 0.07); }
    } catch (error) {
      // 소리를 낼 수 없는 환경
    }
  }

  // ---------------------------------------------------------------- 공통: 하단 띠, 결과 판, 종이 조각
  function amountText(result) {
    if (result.kind === "member") return "구독";
    const count = Number(result.amount).toLocaleString("ko-KR");
    if (result.unit === "원") return `${count}원`;
    if (result.unit === "별풍선" || result.unit === "애드벌룬") return `${result.unit} ${count}개`;
    return `${count} ${result.unit}`.trim();
  }

  function strip(result) {
    const box = el("div", "dk-strip");
    box.appendChild(el("span", "tag", result.title || "후원 추첨"));
    const who = el("span", "who", result.name);
    who.appendChild(el("small", "", "님"));
    box.appendChild(who);
    const meta = el("span", "meta");
    const platform = PLATFORMS[result.platform];
    if (platform && result.platform !== "demo") {
      const label = el("span", "dk-platform", platform.label);
      label.style.setProperty("--platform", platform.color);
      meta.appendChild(label);
    }
    meta.appendChild(el("span", "", amountText(result)));
    meta.appendChild(el("span", "", `추첨 ${result.count}회`));
    if (result.test) meta.appendChild(el("span", "test", "시험"));
    box.appendChild(meta);
    return box;
  }

  function grouped(draws) {  // 같은 상품은 횟수로 묶고 희귀, 일반, 꽝 순서로
    const found = new Map();
    for (const item of draws) {
      const entry = found.get(item.name) || { ...item, count: 0 };
      entry.count += 1;
      found.set(item.name, entry);
    }
    const rank = (item) => (item.rare ? 0 : item.miss ? 2 : 1);
    return [...found.values()].sort((a, b) => rank(a) - rank(b));
  }

  function summary(result) {
    return "결과 " + grouped(result.draws).map((item) => (item.count > 1 ? `${item.name} ${item.count}회` : item.name)).join(", ");
  }

  function plate(result, label = "결과") {
    const items = grouped(result.draws);
    // 판 전체 금색은 결과가 모두 희귀일 때만(룰렛 1회 희귀 등). 여러 결과에서는 희귀 상품만 금색 표시
    const box = el("div", `dk-plate${items.every((item) => item.rare) ? " rare" : ""}`);
    box.appendChild(el("span", "label", label));
    const list = el("span", "items");
    for (const item of items) {
      const span = el("span", item.rare ? "rare" : item.miss ? "miss" : "", item.name);
      if (item.count > 1) span.appendChild(el("small", "", `${item.count}회`));
      list.appendChild(span);
    }
    box.appendChild(list);
    return box;
  }

  function confetti(target) {  // 희귀 공개: 금, 핑크, 크림 종이 조각
    const box = target.getBoundingClientRect();
    const layer = el("div", "dk-confetti");
    layer.style.setProperty("--cx", `${box.left + box.width / 2}px`);
    layer.style.setProperty("--cy", `${box.top + box.height / 3}px`);
    const colors = ["#ffd84d", "#ff4f8b", PAPER, "#ffd84d"];
    for (let i = 0; i < 30; i++) {
      const bit = el("i");
      const angle = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 0.95;
      const speed = 150 + Math.random() * 200;
      bit.style.setProperty("--x", `${Math.cos(angle) * speed}px`);
      bit.style.setProperty("--peak", `${Math.sin(angle) * speed}px`);
      bit.style.setProperty("--fall", `${260 + Math.random() * 180}px`);
      bit.style.setProperty("--r", `${Math.round((Math.random() - 0.5) * 1080)}deg`);
      bit.style.setProperty("--d", `${Math.round(Math.random() * 120)}ms`);
      bit.style.setProperty("--c", colors[i % colors.length]);
      layer.appendChild(bit);
    }
    document.body.appendChild(layer);
    setTimeout(() => layer.remove(), 1900);
  }

  function shake(scene) {
    scene.classList.remove("shake");
    void scene.offsetWidth;  // 같은 애니메이션 다시 시작
    scene.classList.add("shake");
  }

  // ---------------------------------------------------------------- 카드
  const CARD = { l: [172, 240], m: [136, 190], s: [96, 134] };  // 실물 트레이딩 카드 비율 63:88

  function layout(count, spread = 0.86) {  // 1에서 5장은 부채꼴(spread: 카드 간격, 1보다 크면 겹치지 않음), 6에서 12장은 두 줄 겹침, 그 이상은 한 줄 10장
    const size = count <= 5 ? "l" : count <= 12 ? "m" : "s";
    const [w, h] = CARD[size];
    const spots = [];
    if (count <= 5) {
      const step = w * spread;
      for (let i = 0; i < count; i++) {
        const d = i - (count - 1) / 2;
        spots.push({ x: d * step, y: d * d * 8, r: d * 5 });
      }
    } else {
      const perRow = count <= 12 ? Math.ceil(count / 2) : 10;
      const stepX = w * (count <= 12 ? 0.9 : 1.04);
      const stepY = h * (count <= 12 ? 0.66 : 0.78);
      for (let i = 0; i < count; i++) {
        const row = Math.floor(i / perRow);
        const inRow = Math.min(perRow, count - row * perRow);
        spots.push({ x: ((i % perRow) - (inRow - 1) / 2) * stepX, y: row * stepY, r: (((i * 37) % 7) - 3) * 0.7 });
      }
    }
    const minX = Math.min(...spots.map((spot) => spot.x));
    const maxX = Math.max(...spots.map((spot) => spot.x));
    const maxY = Math.max(...spots.map((spot) => spot.y));
    for (const spot of spots) {
      spot.x += 24 - minX;
      spot.y += 12;
    }
    return { size, w, h, spots, width: maxX - minX + w + 48, height: maxY + h + 34 };
  }

  function nameSize(name, h) {
    const length = [...name].length;
    return `${Math.round(h * (length <= 4 ? 0.13 : length <= 7 ? 0.105 : length <= 11 ? 0.085 : 0.07))}px`;
  }

  function card(item, slot, total, plan, showPercent) {
    const spot = plan.spots[slot];
    const node = el("div", `dk-card${item.rare ? " rare" : ""}${item.miss ? " miss" : ""}`);
    const vars = { "--w": `${plan.w}px`, "--h": `${plan.h}px`, "--x": `${spot.x}px`, "--y": `${spot.y}px`, "--r": `${spot.r}deg`, "--i": slot,
      "--z": slot + 1, "--deck-x": `${plan.width / 2 - plan.w / 2}px` };
    for (const [name, value] of Object.entries(vars)) node.style.setProperty(name, value);
    const inner = el("div", "inner");
    const back = el("div", "face back");
    back.appendChild(emblem("#ff4f8b", INK));
    const front = el("div", "face front");
    front.appendChild(el("div", "band", item.band || (item.rare ? "희귀" : item.miss ? "꽝" : "일반")));
    const name = el("div", "dk-name", item.name);
    name.style.setProperty("--name-size", nameSize(item.name, plan.h));
    front.appendChild(name);
    const foot = el("div", "foot");
    const pad = (number) => String(number).padStart(2, "0");
    foot.appendChild(el("span", "", `${pad(slot + 1)}/${pad(total)}`));
    foot.appendChild(el("span", "", item.note !== undefined ? item.note : showPercent ? `${item.percent}%` : ""));
    front.appendChild(foot);
    inner.append(back, front);
    node.appendChild(inner);
    return node;
  }

  async function playCards(result, props, scene) {
    const total = result.draws.length;
    const plan = layout(total);
    const deck = el("div", "dk-deck");
    deck.style.width = `${plan.width}px`;
    deck.style.height = `${plan.height}px`;
    // 공개 순서: 희귀가 아닌 카드 먼저, 희귀 카드 마지막(결과는 그대로, 보여 주는 순서만 바꿈)
    const order = [...result.draws.keys()].sort((a, b) => Number(result.draws[a].rare) - Number(result.draws[b].rare) || a - b);
    const cards = order.map((index, slot) => card(result.draws[index], slot, total, plan, result.show_percent));
    deck.append(...cards);
    props.appendChild(deck);
    await wait(60);
    for (const node of cards) node.classList.add("dealt");  // 시작: 더미에서 펼쳐짐
    await wait(560 + total * 45);
    const rares = cards.filter((node) => node.classList.contains("rare"));
    if (rares.length) {  // 예고: 희귀 카드만 금색 빛
      for (const node of rares) node.classList.add("hint");
      await wait(1000);
    } else {
      await wait(250);
    }
    for (const node of cards) {  // 공개: 일반, 꽝은 빠르게
      if (node.classList.contains("rare")) break;
      node.classList.add("open");
      tone("flip");
      await wait(total > 12 ? 110 : 220);
    }
    for (const node of rares) {  // 희귀는 하나씩 들어 올려 흔든 뒤 천천히
      node.classList.remove("hint");
      node.classList.add("lift");
      await wait(500);
      node.classList.add("slow", "open");
      tone("rare");
      await wait(280);
      confetti(node);
      shake(scene);
      await wait(900);
      node.classList.remove("lift");
    }
    await wait(300);
  }

  // ---------------------------------------------------------------- 룰렛
  const FILLS = ["#ff4f8b", PAPER, "#ffb3cb"];

  function wheelParts(prizes, showPercent) {
    const svg = svgEl("svg", { viewBox: "-120 -120 240 240", class: "wheel-svg", "aria-hidden": "true" });
    const defs = svgEl("defs");
    const stripes = svgEl("pattern", { id: "dk-stripes", width: 10, height: 10, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
    stripes.append(svgEl("rect", { width: 10, height: 10, fill: "#3a4249" }), svgEl("rect", { width: 5, height: 10, fill: INK }));
    defs.appendChild(stripes);
    svg.append(defs, svgEl("circle", { r: 116, fill: INK }));
    const bulbs = [];
    for (let i = 0; i < 24; i++) {  // 테두리 전구(고정)
      const angle = (i / 24) * Math.PI * 2;
      const bulb = svgEl("circle", { cx: (Math.sin(angle) * 108.5).toFixed(2), cy: (-Math.cos(angle) * 108.5).toFixed(2), r: 3.6, class: "bulb" });
      bulbs.push(bulb);
      svg.appendChild(bulb);
    }
    const spin = svgEl("g");
    spin.appendChild(svgEl("circle", { r: 101, fill: INK }));
    const total = prizes.reduce((sum, prize) => sum + prize.percent, 0) || 1;
    const point = (degrees, radius) => [Math.sin((degrees * Math.PI) / 180) * radius, -Math.cos((degrees * Math.PI) / 180) * radius];
    const segments = [];
    const legend = [];
    let start = 0;
    let previous = null;
    let normal = 0;
    prizes.forEach((prize, index) => {
      const sweep = (prize.percent / total) * 360;
      let fill = prize.rare ? "#ffd84d" : prize.miss ? "url(#dk-stripes)" : FILLS[normal++ % FILLS.length];
      if (!prize.rare && !prize.miss) {  // 이웃 칸, 마지막과 첫 칸이 같은 색이 되지 않게
        const first = segments.length ? segments[0].fill : null;
        if (fill === previous || (index === prizes.length - 1 && fill === first)) fill = FILLS.find((color) => color !== previous && color !== first) || fill;
      }
      const [x1, y1] = point(start, 100);
      const [x2, y2] = point(start + sweep, 100);
      spin.appendChild(svgEl("path", {
        d: sweep >= 359.99 ? "M0,-100 A100,100 0 1,1 -0.01,-100 Z"
          : `M0,0 L${x1.toFixed(3)},${y1.toFixed(3)} A100,100 0 ${sweep > 180 ? 1 : 0},1 ${x2.toFixed(3)},${y2.toFixed(3)} Z`,
        fill, stroke: INK, "stroke-width": 1.4,
      }));
      const mid = start + sweep / 2;
      // 이름은 원 둘레 방향: 당첨 칸이 위에 왔을 때 바로 읽힘. 칸이 좁으면 번호와 범례
      const arc = (2 * Math.PI * 72 * Math.min(sweep, 150)) / 360;
      const label = [...prize.name].length > 10 ? `${[...prize.name].slice(0, 9).join("")}..` : prize.name;
      let size = Math.min(15, arc / ([...label].length * 1.02));
      let text = label;
      if (size < 7) {
        text = String(index + 1);
        size = Math.min(13, arc * 0.75);
        legend.push({ number: index + 1, name: prize.name, percent: prize.percent });
      }
      const dark = fill === "url(#dk-stripes)";
      const group = svgEl("g", { transform: `rotate(${mid.toFixed(2)}) translate(0,-72)` });
      const write = (content, y, fontSize) => {
        const node = svgEl("text", { y, "text-anchor": "middle", "dominant-baseline": "central", "font-size": fontSize.toFixed(1), fill: dark ? PAPER : INK });
        if (dark) Object.entries({ stroke: INK, "stroke-width": 2.4, "paint-order": "stroke" }).forEach(([name, value]) => node.setAttribute(name, value));
        node.textContent = content;
        group.appendChild(node);
      };
      if (size >= 4) write(text, showPercent && size >= 9 ? -5 : 0, size);
      if (showPercent && size >= 9 && text === label) write(`${prize.percent}%`, 9, 7.5);
      spin.appendChild(group);
      segments.push({ name: prize.name, mid, sweep, start, fill });
      previous = fill;
      start += sweep;
    });
    for (const segment of segments) {  // 칸 경계 못
      const [x, y] = point(segment.start, 95);
      spin.appendChild(svgEl("circle", { cx: x.toFixed(2), cy: y.toFixed(2), r: 2.6, fill: PAPER, stroke: INK, "stroke-width": 1.2 }));
    }
    spin.appendChild(svgEl("circle", { r: 100, fill: "none", stroke: INK, "stroke-width": 3 }));
    spin.appendChild(svgEl("circle", { r: 21, fill: PAPER, stroke: INK, "stroke-width": 3 }));
    const cap = emblemShapes("#ff4f8b", INK);
    cap.setAttribute("transform", "scale(0.3) translate(-60,-45)");
    spin.appendChild(cap);
    svg.appendChild(spin);
    return { svg, spin, bulbs, segments, legend };
  }

  function flapper() {
    const svg = svgEl("svg", { viewBox: "0 0 34 62", class: "flapper", "aria-hidden": "true" });
    svg.appendChild(svgEl("path", { d: "M17 3 C28 3 31 13 27 23 L19 57 Q17 61 15 57 L7 23 C3 13 6 3 17 3 Z", fill: "#ff4f8b", stroke: INK, "stroke-width": 3,
      "stroke-linejoin": "round" }));
    svg.appendChild(svgEl("circle", { cx: 17, cy: 11, r: 4, fill: PAPER, stroke: INK, "stroke-width": 2 }));
    return svg;
  }

  // 다음 장면: 화면 갱신(requestAnimationFrame)과 40ms 타이머 중 먼저 오는 쪽. 갱신이 멈추는 환경(가려진 창, 일부 촬영 방식)에서도 회전이 이어짐
  function nextFrame(callback) {
    let called = false;
    const run = () => {
      if (!called) {
        called = true;
        callback();
      }
    };
    requestAnimationFrame(run);
    setTimeout(run, 40);
  }

  function spinTo(state, target, duration) {
    return new Promise((resolve) => {
      const from = state.angle;
      const began = performance.now();
      let finished = false;
      const draw = (angle, now) => {
        state.angle = angle;
        state.spin.setAttribute("transform", `rotate(${angle.toFixed(3)})`);
        const under = (((-angle) % 360) + 360) % 360;  // 위쪽 플래퍼 아래에 있는 원판 각도
        let nearest = 180;
        let zone = 0;
        state.segments.forEach((segment, index) => {
          const distance = Math.abs((((under - segment.start) % 360) + 540) % 360 - 180);
          nearest = Math.min(nearest, distance);
          if (under >= segment.start && under < segment.start + segment.sweep) zone = index;
        });
        const push = nearest < 7 ? 1 - nearest / 7 : 0;  // 못이 지나갈 때 플래퍼가 밀림(원판은 시계 방향)
        state.flapper.style.transform = `rotate(${(-push * 26).toFixed(2)}deg)`;
        if (zone !== state.zone) {
          state.zone = zone;
          tone("tick");
        }
        const step = Math.floor(now / 70);
        state.bulbs.forEach((bulb, index) => bulb.classList.toggle("on", (index + step) % 3 === 0));
      };
      const end = () => {
        if (finished) return;
        finished = true;
        draw(target, performance.now());
        state.flapper.style.transform = "";
        resolve();
      };
      const frame = () => {
        if (finished) return;
        const now = performance.now();
        const t = Math.min(1, (now - began) / duration);
        if (t >= 1) return end();
        draw(from + (target - from) * (1 - Math.pow(1 - t, 4)), now);
        nextFrame(frame);
      };
      nextFrame(frame);
      setTimeout(end, duration + 600);  // 어떤 경우에도 결과로 진행
    });
  }

  async function blink(bulbs, times) {
    for (let i = 0; i < times * 2; i++) {
      bulbs.forEach((bulb) => bulb.classList.toggle("on", i % 2 === 0));
      await wait(110);
    }
    bulbs.forEach((bulb) => bulb.classList.add("on"));
  }

  async function playWheel(result, props, scene) {
    const parts = wheelParts(result.prizes, result.show_percent);
    const box = el("div", "dk-wheel");
    const pointer = flapper();
    box.append(parts.svg, pointer);
    const row = el("div", "dk-wheel-row");
    row.appendChild(box);
    if (parts.legend.length) {
      const legend = el("div", `dk-legend${parts.legend.length > 8 ? " many" : ""}`);
      for (const entry of parts.legend) {
        const line = el("div");
        line.append(el("b", "", String(entry.number)), document.createTextNode(result.show_percent ? `${entry.name} ${entry.percent}%` : entry.name));
        legend.appendChild(line);
      }
      row.appendChild(legend);
    }
    const chips = el("div", "dk-chips");
    props.append(row, chips);
    const state = { angle: 0, spin: parts.spin, flapper: pointer, bulbs: parts.bulbs, segments: parts.segments, zone: -1 };
    await wait(450);
    const duration = result.count === 1 ? 5200 : Math.round(Math.max(1500, Math.min(3200, 9500 / result.count)));
    for (const item of result.draws) {
      const segment = parts.segments.find((found) => found.name === item.name) || parts.segments[0];
      const target = -(segment.mid + (Math.random() - 0.5) * segment.sweep * 0.6);  // 칸 가운데 근처(경계는 피함)
      const turn = (((target - state.angle) % 360) + 360) % 360;
      await spinTo(state, state.angle + (result.count === 1 ? 5 : 3) * 360 + turn, duration);
      box.dataset.rotation = state.angle.toFixed(2);
      if (item.rare) {
        tone("rare");
        confetti(box);
        shake(scene);
      }
      await blink(parts.bulbs, item.rare ? 4 : 2);
      if (result.count > 1) chips.appendChild(el("span", item.rare ? "rare" : item.miss ? "miss" : "", item.name));
      await wait(item.rare ? 700 : 250);
    }
  }

  // ---------------------------------------------------------------- 시청자 참여 추첨
  const platformName = (platform) => (platform === "manual" ? "직접 추가" : (PLATFORMS[platform] || {}).label || platform);

  function raffleStrip(result) {
    const box = el("div", "dk-strip");
    box.appendChild(el("span", "tag", result.title || "시청자 추첨"));
    box.appendChild(el("span", "who", result.mode === "order" ? "순서 정하기" : "당첨자 발표"));
    const meta = el("span", "meta");
    meta.appendChild(el("span", "", `참가 ${Number(result.total).toLocaleString("ko-KR")}명`));
    if (result.mode !== "order") meta.appendChild(el("span", "", `당첨 ${result.winners.length}명`));
    box.appendChild(meta);
    return box;
  }

  async function playRaffle(result, props, scene) {
    const winners = result.winners;
    if (result.mode === "order") {  // 순서표: 번호와 이름이 차례로 나타남
      const board = el("div", "dk-order");
      board.style.setProperty("--cols", winners.length > 20 ? 3 : winners.length > 8 ? 2 : 1);
      winners.forEach((winner, index) => {
        const row = el("div", "row");
        row.style.setProperty("--i", index);
        row.append(el("b", "", String(index + 1)), el("span", "", winner.name), el("small", "", platformName(winner.platform)));
        board.appendChild(row);
      });
      if (result.more) board.appendChild(el("div", "more", `외 ${result.more}명`));
      props.appendChild(board);
      await wait(500 + winners.length * 110);
      tone("done");
      return;
    }
    const plan = layout(winners.length, 1.08);  // 당첨 카드: 모두 금색 띠, 아래에 플랫폼(이름이 가려지지 않게 겹치지 않음)
    const deck = el("div", "dk-deck");
    deck.style.width = `${plan.width}px`;
    deck.style.height = `${plan.height}px`;
    const cards = winners.map((winner, slot) => card({ name: winner.name, rare: true, band: "당첨", note: platformName(winner.platform) }, slot, winners.length, plan, false));
    for (const node of cards) node.classList.add("winner");
    deck.append(...cards);
    props.appendChild(deck);
    await wait(60);
    for (const node of cards) node.classList.add("dealt");
    await wait(560 + winners.length * 45);
    for (const node of cards) node.classList.add("hint");
    await wait(900);
    for (const node of cards) {
      node.classList.remove("hint");
      node.classList.add("slow", "open");
      tone("flip");
      await wait(winners.length > 12 ? 160 : 420);
    }
    tone("rare");
    confetti(deck);
    shake(scene);
    await wait(900);
  }

  // 모집 띠: 모집 중에만 표시. 참가하면 이름이 잠깐 위에 나타남. 추첨 연출 중에는 잠시 숨김
  let display = { position: "center", scale: 100 };
  const refreshDisplay = () => fetch("/draw/config").then((response) => response.json()).then((config) => (display = config)).catch(() => null);
  refreshDisplay();
  let raffleBar = null;

  function raffleStatus(status, quiet) {
    if (!status.open) {
      raffleRoot.replaceChildren();
      raffleBar = null;
      return;
    }
    if (!raffleBar) {
      raffleRoot.dataset.position = ["left", "right"].includes(display.position) ? display.position : "center";
      const wrap = el("div", "dk-raffle");
      wrap.style.setProperty("--scale", String(Math.max(0.6, Math.min(1.4, (Number(display.scale) || 100) / 100))));
      const joined = el("div", "dk-joined");
      const band = el("div", "dk-strip");
      const tag = el("span", "tag");
      const who = el("span", "who", "참가자 모집");
      const meta = el("span", "meta");
      band.append(tag, who, meta);
      wrap.append(joined, band);
      raffleRoot.replaceChildren(wrap);
      raffleBar = { wrap, joined, tag, meta };
    }
    raffleBar.tag.textContent = status.title || "시청자 추첨";
    const parts = [`채팅에 ${status.keyword}`];
    if (status.donation_min !== null && status.donation_min !== undefined) parts.push(`${Number(status.donation_min).toLocaleString("ko-KR")}원 이상 후원`);
    raffleBar.meta.replaceChildren(...parts.map((text) => el("span", "", text)), el("span", "count", `${Number(status.count).toLocaleString("ko-KR")}명`));
    if (status.joined && !quiet) {
      const chip = el("span", "", "");
      chip.append(el("b", "", status.joined.name), document.createTextNode(status.joined.source === "donation" ? " 후원 참가" : " 참가"));
      raffleBar.joined.appendChild(chip);
      while (raffleBar.joined.children.length > 4) raffleBar.joined.firstElementChild.remove();
      setTimeout(() => chip.remove(), 3200);
    }
  }

  // ---------------------------------------------------------------- 차례로 연출
  async function play(entry) {
    document.body.classList.add("playing");
    try {
      if (entry.kind === "raffle") await playRaffleScene(entry.data);
      else await playDraw(entry.data);
    } finally {
      document.body.classList.remove("playing");
    }
  }

  async function playRaffleScene(result) {
    await fontsReady;
    await refreshDisplay();
    soundOn = Boolean(display.sound) || params.has("sound");
    root.dataset.position = ["left", "right"].includes(display.position) ? display.position : "center";
    const scene = el("div", "dk-scene");
    scene.style.setProperty("--scale", String(Math.max(0.6, Math.min(1.4, (Number(display.scale) || 100) / 100))));
    const props = el("div", "dk-props");
    const band = raffleStrip(result);
    scene.append(props, band);
    root.replaceChildren(scene);
    tone("start");
    await wait(320);
    await playRaffle(result, props, scene);
    if (result.mode !== "order") scene.insertBefore(plate({ draws: result.winners.map((winner) => ({ name: winner.name, rare: true })) }, "당첨"), band);
    await wait(Math.max(4, Number(display.seconds) || 8) * 1000 + (result.mode === "order" ? 4000 : 0));
    scene.classList.add("leave");
    await wait(560);
    root.replaceChildren();
  }

  async function playDraw(result) {
    await fontsReady;
    soundOn = Boolean(result.sound) || params.has("sound");
    root.dataset.position = ["left", "right"].includes(result.position) ? result.position : "center";
    const scene = el("div", "dk-scene");
    scene.style.setProperty("--scale", String(Math.max(0.6, Math.min(1.4, (Number(result.scale) || 100) / 100))));
    const props = el("div", "dk-props");
    const band = strip(result);
    scene.append(props, band);
    root.replaceChildren(scene);
    tone("start");
    await wait(320);
    const style = STYLES.includes(forced) ? forced : result.style;
    if (style === "wheel") await playWheel(result, props, scene);
    else await playCards(result, props, scene);
    scene.insertBefore(plate(result), band);  // 정리: 결과 판
    root.setAttribute("aria-label", summary(result));
    if (!result.draws.some((item) => item.rare)) tone("done");
    await wait(Math.max(2, Number(result.seconds) || 8) * 1000);
    scene.classList.add("leave");  // 퇴장
    await wait(560);
    root.replaceChildren();
  }

  async function drain() {
    if (busy) return;
    busy = true;
    while (queue.length) {  // 동시에 여러 후원이 와도 하나씩
      try {
        await play(queue.shift());
      } catch (error) {
        console.warn("debutkit 추첨 연출", error);
        root.replaceChildren();
      }
    }
    busy = false;
  }

  function accept(result) {
    if (!result || !result.seq || !Array.isArray(result.draws) || !result.draws.length) return;
    queue.push({ kind: "draw", data: result });
    drain();
  }

  function acceptRaffle(result) {
    if (!result || result.type !== "result" || !Array.isArray(result.winners) || !result.winners.length) return;
    queue.push({ kind: "raffle", data: result });
    drain();
  }

  // 연결할 때(다시 연결 포함) 받는 첫 값: 추첨은 지난 결과라 재생하지 않고, 참여 추첨은 현재 모집 상태라 그대로 표시(참가 알림만 생략)
  let first = true;
  let raffleFirst = true;
  const source = new EventSource("/live?feeds=draw,raffle");
  source.addEventListener("open", () => {
    first = true;
    raffleFirst = true;
  });
  source.addEventListener("draw", (message) => {
    const result = JSON.parse(message.data);
    if (first) {
      first = false;
      return;
    }
    accept(result);
  });
  source.addEventListener("raffle", (message) => {
    const data = JSON.parse(message.data);
    if (data.type === "status") {
      if (data.open && !raffleBar) refreshDisplay().then(() => raffleStatus(data, raffleFirst));
      else raffleStatus(data, raffleFirst);
    } else if (!raffleFirst) {
      acceptRaffle(data);
    }
    raffleFirst = false;
  });

  // 미리보기(?sample=card 또는 ?sample=wheel): 저장한 설정으로 예시 추첨을 이 화면에서만 표시. OBS와 다른 화면에는 나가지 않음
  const sample = params.get("sample");
  if (STYLES.includes(sample)) {
    document.body.classList.add("sample");
    if (params.get("bg") === "light") document.body.classList.add("light");
    fetch("/draw/config").then((response) => response.json()).then((config) => {
      const prizes = config.prizes;
      const rare = prizes.find((prize) => prize.rare) || prizes[prizes.length - 1];
      const others = prizes.filter((prize) => prize !== rare);
      const count = Math.max(1, Math.min(30, Number(params.get("count")) || (sample === "wheel" ? 1 : 3)));
      const draws = count === 1 ? [rare] : Array.from({ length: count }, (_, index) => (index === 1 ? rare : others[index % others.length] || rare));
      accept({ seq: 1, time: Date.now() / 1000, test: false, name: "고양이집사", platform: "chzzk", kind: "donation", amount: count === 1 ? 1000 : 5000,
               unit: "원", count, draws, prizes, style: sample, seconds: 600, title: config.title, position: config.position, scale: config.scale,
               sound: config.sound, show_percent: config.show_percent });
    });
  }
  // 참여 추첨 미리보기(?sample=raffle 당첨 카드, order 순서표, recruit 모집 띠): 예시 이름으로 이 화면에서만 표시
  const VIEWERS = ["고양이집사", "새벽감성", "별빛구름", "debut_streamer", "노래하는토끼", "밤하늘산책", "초코우유", "푸른고래", "라면한그릇", "햇살가득",
                   "모닝커피", "달빛소나타"];
  const platforms = ["chzzk", "soop", "youtube", "twitch"];
  if (["raffle", "order", "recruit"].includes(sample)) {
    document.body.classList.add("sample");
    if (params.get("bg") === "light") document.body.classList.add("light");
    const count = Math.max(1, Math.min(30, Number(params.get("count")) || (sample === "order" ? 12 : 3)));
    const winners = Array.from({ length: count }, (_, index) => ({ name: VIEWERS[index % VIEWERS.length] + (index >= VIEWERS.length ? String(index) : ""),
                                                                 platform: platforms[index % platforms.length], source: "chat" }));
    if (sample === "recruit") {
      refreshDisplay().then(() => {
        raffleStatus({ open: true, keyword: "!참가", title: "시청자 추첨", donation_min: 1000, count: 23 }, true);
        winners.slice(0, 3).forEach((winner, index) => setTimeout(() => raffleStatus({ open: true, keyword: "!참가", title: "시청자 추첨", donation_min: 1000,
                                                                                         count: 24 + index, joined: { ...winner } }, false), 400 + index * 500));
      });
    } else {
      acceptRaffle({ type: "result", seq: 1, mode: sample === "order" ? "order" : "pick", title: "시청자 추첨", total: 37, winners, more: 0 });
    }
  }
  window.debutkitDraw = { accept, acceptRaffle, queue, summary, layout };  // 시험용
})();
