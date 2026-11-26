// debutkit 후원 추첨 연출(OBS 브라우저 소스, 권장 1920x1080). /live?feeds=draw 로 추첨 결과를 받아 차례로 연출한다.
// 콘셉트 "방송 소품": 마스코트 마이(리본 마이크) 문양을 찍은 실물 카드와 무대용 상품 룰렛. 소품과 하단 띠만 화면 아래쪽에 놓는다.
// 연출 순서: 시작(띠, 소품 등장), 예고(희귀 카드만 금색 빛, 실제 결과와 같음), 공개(일반 카드 빠르게, 희귀 카드 마지막 천천히), 정리(결과 판), 퇴장.
// 뽑기는 서버가 하고 이 화면은 받은 결과를 보여 주기만 한다(모든 화면이 같은 결과). 글은 textContent로만 넣는다.
// 시청자 참여 추첨(/live의 raffle): 모집 중에는 하단 모집 띠와 참가자 이름, 결과는 당첨 카드나 순서표로 같은 차례 안에서 연출.
// 연출: 카드, 룰렛(이 파일), 캡슐 뽑기, 즉석 복권, 티켓 출력, 추첨기, 타로(draw-props.js). 결과 판이 나올 때 고른 효과(EFFECTS),
// 상품 이름과 안내 글 글꼴, 크기는 결과에 담겨 온 설정을 따른다. 타로의 오늘의 한마디는 서버가 고른 문장만 표시
// 빠른 모드: 지금 연출을 포함해 FAST_QUEUE개 이상 기다리면 연출 시간을 FAST_RATE배로, 결과 표시를 FAST_HOLD초 이내로 줄인다
// 주소: ?style=card 처럼 연출 고정. ?sample=capsule&count=11&result=rare(miss, normal)&design=box&effect=stars&bg=light 미리보기
// (이 화면에서만, 실시간 연결 없음). ?sound 효과음 강제
"use strict";

(() => {
  const root = document.getElementById("draw");
  const raffleRoot = document.getElementById("raffle");
  const params = new URLSearchParams(location.search);
  const forced = params.get("style");
  const PLATFORMS = (window.debutkit && window.debutkit.PLATFORMS) || {};
  const NS = "http://www.w3.org/2000/svg";
  const INK = "#1e2327";
  const PAPER = "#faf7f5";
  // 방송 색(/theme.css): 화면을 불러올 때의 색. 색을 바꾸면 연출이 없을 때 화면을 새로 불러온다
  const themed = (name, fallback) => (window.debutkitTheme && window.debutkitTheme.color(name)) || fallback;
  const GOLD = themed("highlight", "#ffd84d");
  const PINK = themed("primary", "#ff4f8b");
  const PINK_LIGHT = themed("primary-light", "#ffb3cb");
  const FAST_QUEUE = 3;  // 빠른 모드: 기다리는 추첨(지금 연출 포함) 수
  const FAST_RATE = 0.5;  // 빠른 모드의 연출 시간 배율
  const FAST_HOLD = 4;  // 빠른 모드의 결과 표시 최대 시간(초)
  const queue = [];
  let busy = false;
  let pace = 1;  // 연출 시간 배율(빠른 모드 0.5)
  let sceneScale = 1;

  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const beat = (ms) => wait(ms * pace);  // 연출 단계 사이 시간(빠른 모드에서 짧아짐)
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

  // 마스코트 마이(리본 마이크) 문양: 꼭대기 불, 둥근 몸, 위쪽 망 두 줄, 눈과 웃는 입, 아래 띠. 몸 색과 무늬 색 두 가지로
  // (assets/brand의 마이를 줄인 모양, pick.js와 같은 도형). 그룹으로 만들어 카드 뒷면, 룰렛 가운데, 소품에 사용. 가운데는 (60, 45)
  function emblemShapes(body, ink) {
    const group = svgEl("g");
    group.appendChild(svgEl("circle", { cx: 60, cy: 9, r: 4, fill: body }));
    group.appendChild(svgEl("rect", { x: 36, y: 14, width: 48, height: 68, rx: 24, fill: body }));
    group.appendChild(svgEl("rect", { x: 43, y: 23, width: 34, height: 3.6, rx: 1.8, fill: ink }));
    group.appendChild(svgEl("rect", { x: 39.5, y: 30.5, width: 41, height: 3.6, rx: 1.8, fill: ink }));
    group.appendChild(svgEl("circle", { cx: 50.5, cy: 46, r: 4, fill: ink }));
    group.appendChild(svgEl("circle", { cx: 69.5, cy: 46, r: 4, fill: ink }));
    group.appendChild(svgEl("path", { d: "M54.5 53 Q60 59.5 65.5 53", fill: "none", stroke: ink, "stroke-width": 3.4, "stroke-linecap": "round" }));
    group.appendChild(svgEl("rect", { x: 40, y: 66, width: 40, height: 3.6, rx: 1.8, fill: ink }));
    return group;
  }

  function emblem(body, eyes) {
    const svg = svgEl("svg", { viewBox: "30 4 60 82", class: "emblem", "aria-hidden": "true" });
    svg.appendChild(emblemShapes(body, eyes));
    return svg;
  }

  // ---------------------------------------------------------------- 효과음(브라우저에서 합성. 음원 파일 없음)
  let audio = null;
  let noise = null;
  let soundOn = false;
  function tone(kind, seconds = 0.4) {
    if (!soundOn) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const now = audio.currentTime;
      const note = (type, frequency, start, length, peak, to) => {
        const oscillator = audio.createOscillator();
        const gain = audio.createGain();
        oscillator.type = type;
        oscillator.frequency.setValueAtTime(frequency, now + start);
        if (to) oscillator.frequency.exponentialRampToValueAtTime(to, now + start + length);
        gain.gain.setValueAtTime(0.0001, now + start);
        gain.gain.exponentialRampToValueAtTime(peak, now + start + 0.006);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + start + length);
        oscillator.connect(gain).connect(audio.destination);
        oscillator.start(now + start);
        oscillator.stop(now + start + length + 0.03);
      };
      // 잡음(긁기, 섞기, 불꽃): 1초짜리 무작위 소리를 한 번 만들어 거름망을 거쳐 사용
      const hiss = (start, length, peak, frequency, kindOf = "bandpass") => {
        if (!noise) {
          noise = audio.createBuffer(1, audio.sampleRate, audio.sampleRate);
          const data = noise.getChannelData(0);
          for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
        }
        const source = audio.createBufferSource();
        const filter = audio.createBiquadFilter();
        const gain = audio.createGain();
        source.buffer = noise;
        source.loop = true;
        filter.type = kindOf;
        filter.frequency.value = frequency;
        gain.gain.setValueAtTime(0.0001, now + start);
        gain.gain.exponentialRampToValueAtTime(peak, now + start + 0.01);
        gain.gain.setValueAtTime(peak, now + start + Math.max(0.01, length - 0.05));
        gain.gain.exponentialRampToValueAtTime(0.0001, now + start + length);
        source.connect(filter).connect(gain).connect(audio.destination);
        source.start(now + start);
        source.stop(now + start + length + 0.03);
      };
      if (kind === "tick") note("square", 2300, 0, 0.025, 0.04);
      else if (kind === "start") note("triangle", 520, 0, 0.12, 0.07);
      else if (kind === "flip") { note("triangle", 880, 0, 0.07, 0.06); note("triangle", 1320, 0.035, 0.06, 0.04); }
      else if (kind === "rare") [1318.5, 1975.5, 2637].forEach((frequency, index) => note("sine", frequency, index * 0.09, 1.5, 0.1));
      else if (kind === "done") { note("sine", 784, 0, 0.25, 0.07); note("sine", 1046.5, 0.12, 0.4, 0.07); }
      else if (kind === "crank") [0, 0.06, 0.12].forEach((start) => note("square", 1500, start, 0.018, 0.035));
      else if (kind === "drop") { note("triangle", 240, 0, 0.12, 0.09, 120); note("square", 1900, 0, 0.015, 0.03); }
      else if (kind === "pop") note("sine", 420, 0, 0.12, 0.08, 980);
      else if (kind === "print") { note("sawtooth", 130, 0, seconds, 0.025); hiss(0, seconds, 0.02, 2400); }
      else if (kind === "scratch") hiss(0, seconds, 0.05, 3600);
      else if (kind === "shuffle") for (let i = 0; i < 14; i++) hiss(i * 0.028, 0.02, 0.06, 2800);
      else if (kind === "bell") [0, 0.32].forEach((start) => [1568, 2349, 3951].forEach((frequency) => note("sine", frequency, start, 0.9, 0.05)));
      else if (kind === "boom") { hiss(0, 0.3, 0.09, 900, "lowpass"); note("sine", 90, 0, 0.25, 0.08, 45); }
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

  function confetti(target, count = 30, colors = [GOLD, PINK, PAPER, GOLD], power = 1) {  // 희귀 공개: 금, 핑크, 크림 종이 조각
    const box = target.getBoundingClientRect();
    const layer = el("div", "dk-confetti");
    layer.style.setProperty("--cx", `${box.left + box.width / 2}px`);
    layer.style.setProperty("--cy", `${box.top + box.height / 3}px`);
    for (let i = 0; i < count; i++) {
      const bit = el("i");
      const angle = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 0.95;
      const speed = (150 + Math.random() * 200) * power;
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

  // 공개 순서: 희귀가 아닌 것 먼저, 희귀 마지막(결과는 그대로, 보여 주는 순서만 바꿈)
  const revealOrder = (draws) => [...draws.keys()].sort((a, b) => Number(draws[a].rare) - Number(draws[b].rare) || a - b);

  // ---------------------------------------------------------------- 글꼴, 크기(설정의 상품 이름, 안내 글). 함께 배포한 글꼴과 운영체제 기본 글꼴만
  const FONTS = {
    display: ['"Black Han Sans", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif', 400],
    text: ['"Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif', 700],
    gothic: ['"Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo", sans-serif', 700],
    serif: ['"Batang", "바탕", "AppleMyungjo", serif', 700],
    gungsuh: ['"Gungsuh", "궁서", "GungSeo", "AppleMyungjo", serif', 700],
  };
  const SIZES = { small: 0.85, medium: 1, large: 1.18 };

  function applyLook(scene, result) {
    for (const part of ["name", "caption"]) {
      const [family, weight] = FONTS[result[`${part}_font`]] || FONTS.display;
      scene.style.setProperty(`--${part}-font`, family);
      scene.style.setProperty(`--${part}-weight`, String(weight));
      scene.style.setProperty(`--${part}-scale`, String(SIZES[result[`${part}_size`]] || 1));
    }
    // 작은 상품 이름: 굵은 제목 글꼴은 획이 뭉치므로 본문 글꼴, 다른 글꼴은 그대로
    const small = FONTS[result.name_font] && result.name_font !== "display" ? FONTS[result.name_font] : FONTS.text;
    scene.style.setProperty("--name-small-font", small[0]);
    scene.style.setProperty("--name-small-weight", String(small[1]));
  }

  function adviceLine(text) {  // 타로 오늘의 한마디(서버가 고른 문장)
    const box = el("div", "dk-advice");
    const ribbon = el("div", "ribbon");
    ribbon.append(el("span", "label", "오늘의 한마디"), el("span", "line", text));
    box.appendChild(ribbon);
    return box;
  }

  // ---------------------------------------------------------------- 결과 뒤 효과: 결과 판이 나올 때 한 번(모두 꽝이면 생략). 금색은 희귀 결과가 있을 때만
  const rand = (min, max) => min + Math.random() * (max - min);

  function fxLayer(name, life) {  // 화면 전체에 고정한 효과 층. 크기는 표시 크기를 따름
    const node = el("div", `dk-fx ${name}`);
    node.style.setProperty("--s", String(sceneScale));
    document.body.appendChild(node);
    setTimeout(() => node.remove(), life);
    return node;
  }

  function place(node, values) {
    for (const [name, value] of Object.entries(values)) node.style.setProperty(`--${name}`, value);
    return node;
  }

  const RIBBON = "M10 2 C 18 18, 2 30, 10 46 S 18 76, 10 92 S 2 122, 10 138";
  const HEART = "M12 21 C 4 14 1 10 1 6.5 C 1 3.4 3.4 1 6.5 1 C 8.6 1 10.6 2.2 12 4 C 13.4 2.2 15.4 1 17.5 1 C 20.6 1 23 3.4 23 6.5 C 23 10 20 14 12 21 Z";
  const SPARK = "M12 0 Q 13.6 10.4 24 12 Q 13.6 13.6 12 24 Q 10.4 13.6 0 12 Q 10.4 10.4 12 0 Z";

  function shape(viewBox, path, fill, outline) {
    const svg = svgEl("svg", { viewBox, "aria-hidden": "true" });
    svg.appendChild(svgEl("path", { d: path, fill, stroke: INK, "stroke-width": outline, "stroke-linejoin": "round" }));
    return svg;
  }

  const EFFECTS = {
    confetti(box, colors, rare) {  // 종이 조각: 소품 양쪽에서 두 번
      const bit = { getBoundingClientRect: () => box };
      confetti(bit, rare ? 46 : 36, colors, 1.3);
      setTimeout(() => confetti(bit, rare ? 40 : 30, colors, 1.1), 260);
    },
    streamers(box, colors) {  // 색 테이프: 아래 양쪽 모서리에서 터지는 곱슬 리본
      const fx = fxLayer("streamers", 2900);
      for (let i = 0; i < 18; i++) {
        const side = i % 2 ? 1 : -1;
        const ribbon = el("i");
        const svg = svgEl("svg", { viewBox: "0 0 20 140", "aria-hidden": "true" });
        svg.append(svgEl("path", { d: RIBBON, fill: "none", stroke: INK, "stroke-width": 8, "stroke-linecap": "round" }),
          svgEl("path", { d: RIBBON, fill: "none", stroke: colors[i % colors.length], "stroke-width": 4.6, "stroke-linecap": "round" }));
        ribbon.appendChild(svg);
        fx.appendChild(place(ribbon, { x: `${side < 0 ? box.left - 10 : box.right + 10}px`, y: `${box.bottom - 20}px`,
          dx: `${-side * rand(120, 420) * sceneScale}px`, dy: `${-rand(240, 520) * sceneScale}px`, r0: `${side * 40}deg`,
          r: `${rand(-260, 260).toFixed(0)}deg`, d: `${Math.floor(i / 2) * 55}ms` }));
      }
    },
    fireworks(box, colors) {  // 불꽃놀이: 소품 위 세 곳에서 차례로
      const fx = fxLayer("fireworks", 2900);
      [[0.18, 0.05], [0.82, 0.12], [0.5, -0.22]].forEach(([fx_, fy], n) => {
        const burst = place(el("b"), { x: `${box.left + box.width * fx_}px`, y: `${Math.max(90, box.top + box.height * fy)}px`, d: `${n * 280}ms` });
        burst.appendChild(place(el("u"), { c: colors[n % colors.length] }));
        for (let k = 0; k < 16; k++) {
          burst.appendChild(place(el("i"), { a: `${(k * 360) / 16 + n * 7}deg`, len: `${rand(90, 140) * sceneScale}px`, c: colors[(k + n) % colors.length] }));
        }
        fx.appendChild(burst);
        setTimeout(() => tone("boom"), n * 280);
      });
    },
    spotlight(box) {  // 무대 조명: 위쪽 양옆 조명이 소품을 비춤(소품 뒤에 그림)
      const fx = fxLayer("spotlight", 3700);
      const cx = box.left + box.width / 2;
      const ty = box.top + box.height * 0.55;
      for (const side of [-1, 1]) {
        const sx = Math.min(innerWidth - 40, Math.max(40, cx + side * Math.max(380, box.width * 0.75)));
        const dx = cx - sx;
        const dy = ty + 30;
        const angle = (-Math.atan2(dx, dy) * 180) / Math.PI;
        const values = { x: `${sx}px`, y: "-30px", a: `${angle.toFixed(1)}deg`, from: `${(angle - side * 26).toFixed(1)}deg` };
        fx.appendChild(place(el("i", "beam"), { ...values, h: `${Math.hypot(dx, dy) * 1.12}px`, w: `${Math.max(260, box.width * 0.62)}px` }));
        fx.appendChild(place(el("b", "lamp"), values));
      }
      fx.appendChild(place(el("u", "pool"), { x: `${cx}px`, y: `${box.bottom - 6}px`, w: `${box.width * 1.15}px` }));
    },
    hearts(box, colors) {  // 하트: 결과 판 쪽에서 흔들리며 올라감
      const fx = fxLayer("hearts", 3500);
      for (let i = 0; i < 20; i++) {
        const heart = place(el("i"), { x: `${rand(box.left, box.right)}px`, y: `${box.bottom - rand(0, box.height * 0.3)}px`,
          rise: `${-rand(240, 460) * sceneScale}px`, sway: `${rand(18, 52) * sceneScale}px`, size: `${rand(24, 40) * sceneScale}px`, d: `${i * 75}ms` });
        heart.appendChild(shape("-1 -1 26 24", HEART, colors[i % colors.length], 1.8));
        fx.appendChild(heart);
      }
    },
    stars(box, colors) {  // 반짝이는 별: 소품 둘레 여기저기
      const fx = fxLayer("stars", 3000);
      const pad = 60 * sceneScale;
      for (let i = 0; i < 26; i++) {
        const star = place(el("i"), { x: `${rand(box.left - pad, box.right + pad)}px`, y: `${rand(box.top - pad, box.bottom)}px`,
          size: `${rand(16, 44) * sceneScale}px`, d: `${rand(0, 1500).toFixed(0)}ms` });
        star.appendChild(shape("-2 -2 28 28", SPARK, colors[i % colors.length], 1.6));
        fx.appendChild(star);
      }
    },
  };

  function effect(kind, scene, rare) {
    const run = EFFECTS[kind];
    const props = scene.querySelector(".dk-props");
    if (!run || !props) return;
    const box = props.getBoundingClientRect();
    run(box, rare ? [GOLD, PINK, PAPER, GOLD, PINK_LIGHT] : [PINK, PAPER, PINK_LIGHT, PINK], rare);
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
    back.appendChild(emblem(PINK, INK));
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
    const cards = revealOrder(result.draws).map((index, slot) => card(result.draws[index], slot, total, plan, result.show_percent));
    deck.append(...cards);
    props.appendChild(deck);
    await wait(60);
    for (const node of cards) node.classList.add("dealt");  // 시작: 더미에서 펼쳐짐
    await beat(560 + total * 45);
    const rares = cards.filter((node) => node.classList.contains("rare"));
    if (rares.length) {  // 예고: 희귀 카드만 금색 빛
      for (const node of rares) node.classList.add("hint");
      await beat(1000);
    } else {
      await beat(250);
    }
    for (const node of cards) {  // 공개: 일반, 꽝은 빠르게
      if (node.classList.contains("rare")) break;
      node.classList.add("open");
      tone("flip");
      await beat(total > 12 ? 110 : 220);
    }
    for (const node of rares) {  // 희귀는 하나씩 들어 올려 흔든 뒤 천천히
      node.classList.remove("hint");
      node.classList.add("lift");
      await beat(500);
      node.classList.add("slow", "open");
      tone("rare");
      await beat(280);
      confetti(node);
      shake(scene);
      await beat(900);
      node.classList.remove("lift");
    }
    await beat(300);
  }

  // ---------------------------------------------------------------- 룰렛
  const FILLS = [PINK, PAPER, PINK_LIGHT];

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
      let fill = prize.rare ? GOLD : prize.miss ? "url(#dk-stripes)" : FILLS[normal++ % FILLS.length];
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
    const cap = emblemShapes(PINK, INK);
    cap.setAttribute("transform", "scale(0.3) translate(-60,-45)");
    spin.appendChild(cap);
    svg.appendChild(spin);
    return { svg, spin, bulbs, segments, legend };
  }

  function flapper() {
    const svg = svgEl("svg", { viewBox: "0 0 34 62", class: "flapper", "aria-hidden": "true" });
    svg.appendChild(svgEl("path", { d: "M17 3 C28 3 31 13 27 23 L19 57 Q17 61 15 57 L7 23 C3 13 6 3 17 3 Z", fill: PINK, stroke: INK, "stroke-width": 3,
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
    await beat(450);
    const duration = pace * (result.count === 1 ? 5200 : Math.round(Math.max(1500, Math.min(3200, 9500 / result.count))));
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
      await beat(item.rare ? 700 : 250);
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

  // ---------------------------------------------------------------- 연출 목록: 카드, 룰렛(이 파일)과 소품 연출(draw-props.js, 이 파일보다 먼저 불러옴)
  const kit = { el, svgEl, wait, beat, tone, emblem, emblemShapes, confetti, shake, nextFrame, revealOrder, nameSize, INK, PAPER, GOLD, PINK, PINK_LIGHT,
                scale: () => sceneScale, pace: () => pace };
  const PLAYERS = { card: playCards, wheel: playWheel, ...(typeof window.debutkitDrawProps === "function" ? window.debutkitDrawProps(kit) : {}) };
  const STYLES = Object.keys(PLAYERS);

  // ---------------------------------------------------------------- 차례로 연출
  async function play(entry) {
    document.body.classList.add("playing");
    pace = queue.length + 1 >= FAST_QUEUE ? FAST_RATE : 1;  // 빠른 모드(지금 연출 포함 대기 수)
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
    const style = STYLES.includes(forced) ? forced : STYLES.includes(result.style) ? result.style : "card";
    const scene = el("div", "dk-scene");
    sceneScale = Math.max(0.6, Math.min(1.4, (Number(result.scale) || 100) / 100));
    scene.style.setProperty("--scale", String(sceneScale));
    scene.style.setProperty("--pace", String(pace));
    scene.dataset.style = style;
    applyLook(scene, result);
    const props = el("div", "dk-props");
    const band = strip(result);
    scene.append(props, band);
    root.replaceChildren(scene);
    tone("start");
    await beat(320);
    await PLAYERS[style](result, props, scene);
    scene.insertBefore(plate(result), band);  // 정리: 결과 판
    if (result.advice) scene.insertBefore(adviceLine(result.advice), band);
    root.setAttribute("aria-label", summary(result) + (result.advice ? `. 오늘의 한마디 ${result.advice}` : ""));
    if (!result.draws.every((item) => item.miss)) effect(result.effect, scene, result.draws.some((item) => item.rare));
    if (!result.draws.some((item) => item.rare)) tone("done");
    let hold = Math.max(2, Number(result.seconds) || 8) * 1000;
    if (queue.length + 1 >= FAST_QUEUE) hold = Math.min(hold, FAST_HOLD * 1000);  // 연출 중에 대기가 늘어난 경우 포함
    await wait(hold);
    scene.classList.add("leave");  // 퇴장
    await wait(560);
    root.replaceChildren();
  }

  async function drain() {
    if (busy) return;
    busy = true;
    while (queue.length) {  // 동시에 여러 후원이 와도 하나씩. 뽑기판 결과 등 가운데 연출과는 무대 차례(live.js의 cue)로 번갈아
      const release = window.debutkitLive && !sample ? await window.debutkitLive.cue("draw") : () => {};
      try {
        await play(queue.shift());
      } catch (error) {
        console.warn("debutkit 추첨 연출", error);
        root.replaceChildren();
      } finally {
        release();
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
  // 미리보기(?sample)는 실시간 연결을 열지 않는다(조작 화면의 미리보기가 OBS 소스와 같은 주소의 동시 연결 수를 나눠 쓰지 않게)
  const sample = params.get("sample");
  // 공유 연결(live.js): 연결(다시 연결 포함) 직후의 값(initial)은 지난 결과나 현재 상태라 연출하지 않는다
  if (!sample) {
    window.debutkitLive.subscribe(["draw", "raffle", "theme"], (feed, data, initial) => {
      if (feed === "theme") {
        if (!initial && !busy) location.reload();  // 소품의 색은 불러올 때 정해서 새로 불러옴
      } else if (feed === "draw") {
        if (!initial) accept(data);
      } else if (feed === "raffle") {
        if (data.type === "status") {
          if (data.open && !raffleBar) refreshDisplay().then(() => raffleStatus(data, initial));
          else raffleStatus(data, initial);
        } else if (!initial) {
          acceptRaffle(data);
        }
      }
    });
  }

  // 미리보기(?sample=card, wheel, capsule 등): 저장한 상품표로 예시 추첨을 이 화면에서만 표시. OBS와 다른 화면에는 나가지 않음
  // 표시 설정은 주소로 바꿔 볼 수 있음(조작 화면의 미리보기가 저장 전 값을 보여 줌): design, effect, name_font, name_size, caption_font,
  // caption_size, title, position, scale, percent(1, 0), advice(1, 0), advice_text. result=rare(miss, normal)는 결과 종류, 기본은 섞어서
  if (STYLES.includes(sample)) {
    document.body.classList.add("sample");
    if (params.get("bg") === "light") document.body.classList.add("light");
    fetch("/draw/config").then((response) => response.json()).then((config) => {
      const prizes = config.prizes;
      const rare = prizes.find((prize) => prize.rare) || prizes[prizes.length - 1];
      const others = prizes.filter((prize) => prize !== rare);
      const kind = params.get("result");
      const pool = kind === "rare" ? [rare] : kind === "miss" ? prizes.filter((prize) => prize.miss)
        : kind === "normal" ? prizes.filter((prize) => !prize.rare && !prize.miss) : null;
      const count = Math.max(1, Math.min(30, Number(params.get("count")) || (sample === "wheel" ? 1 : 3)));
      const draws = pool && pool.length ? Array.from({ length: count }, (_, index) => pool[index % pool.length])
        : count === 1 ? [rare] : Array.from({ length: count }, (_, index) => (index === 1 ? rare : others[index % others.length] || rare));
      const pick = (name, choices) => (choices && params.get(name) in choices ? params.get(name) : config[name]);
      const percent = params.get("percent");
      const advice = params.has("advice") ? params.get("advice") === "1" : config.advice;
      const title = (params.get("title") || "").trim().slice(0, 20);
      const scale = Number(params.get("scale"));
      accept({ seq: 1, time: Date.now() / 1000, test: false, name: "고양이집사", platform: "chzzk", kind: "donation", amount: count === 1 ? 1000 : 5000,
               unit: "원", count, draws, prizes, style: sample, seconds: 600, title: title || config.title,
               position: pick("position", config.positions), scale: scale >= 60 && scale <= 140 ? scale : config.scale,
               sound: params.has("mute") ? false : config.sound,  // 그림 견본(mute)은 소리 없이
               show_percent: percent === null ? config.show_percent : percent === "1", design: pick("design", (config.designs || {})[sample]),
               effect: pick("effect", config.effects), name_font: pick("name_font", config.fonts), name_size: pick("name_size", config.sizes),
               caption_font: pick("caption_font", config.fonts), caption_size: pick("caption_size", config.sizes),
               advice: sample === "tarot" && advice ? (params.get("advice_text") || config.advice_example).slice(0, 40) : "" });
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
  window.debutkitDraw = { accept, acceptRaffle, queue, summary, layout, styles: STYLES, pace: () => pace };  // 시험용
})();
