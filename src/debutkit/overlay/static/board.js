// debutkit 주사위 판(OBS 브라우저 소스 1920x1080). /live?feeds=board 로 판과 게임 상태를 받아 그리고, 새 굴리기(event)는
// 주사위가 굴러간 뒤 말이 칸마다 뛰어 지나가는 연출로 보여 준다. 결과는 서버가 정한 그대로. 글은 textContent로만 넣는다.
// 주소: ?sample=1 예시 판(조작 화면 그림 견본), ?mute 소리 끔
"use strict";

(() => {
  const params = new URLSearchParams(location.search);
  const root = document.getElementById("board-root");
  const muted = params.has("mute");
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const BOARD = 980;
  const PIPS = { 1: [4], 2: [0, 8], 3: [0, 4, 8], 4: [0, 2, 6, 8], 5: [0, 2, 4, 6, 8], 6: [0, 2, 3, 5, 6, 8] };

  function fit() {
    const scale = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
    root.style.transform = `scale(${scale})`;
  }
  window.addEventListener("resize", fit);
  fit();

  // ---------------------------------------------------------------- 소리(브라우저에서 합성, OBS 오디오 제어를 켠 경우 방송에 나감)
  let audio = null;
  function play(kind) {
    if (muted) return;
    try {
      audio = audio || new AudioContext();
      const now = audio.currentTime;
      const tone = (frequency, start, length, peak = 0.06, type = "triangle") => {
        const oscillator = audio.createOscillator();
        const gain = audio.createGain();
        oscillator.type = type;
        oscillator.frequency.value = frequency;
        gain.gain.setValueAtTime(0.0001, now + start);
        gain.gain.exponentialRampToValueAtTime(peak, now + start + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + start + length);
        oscillator.connect(gain).connect(audio.destination);
        oscillator.start(now + start);
        oscillator.stop(now + start + length + 0.02);
      };
      if (kind === "rattle") for (let k = 0; k < 6; k++) tone(900 + Math.random() * 900, k * 0.07, 0.04, 0.04, "square");
      else if (kind === "step") tone(520 + Math.random() * 80, 0, 0.07, 0.05);
      else if (kind === "land") { tone(784, 0, 0.18); tone(1046.5, 0.1, 0.3); }
      else if (kind === "lucky") [784, 988, 1175, 1568].forEach((frequency, index) => tone(frequency, index * 0.08, 0.25, 0.05, "sine"));
    } catch (error) {
      // 소리를 낼 수 없는 환경
    }
  }

  // ---------------------------------------------------------------- 판 그리기
  let state = null;
  let cellBoxes = [];
  const tokens = new Map();  // 참가자 번호 -> 말
  let dice = null;
  let card = null;

  // 칸 자리: 0번(출발)은 오른쪽 아래 모서리, 시계 반대 방향(아래 줄 오른쪽에서 왼쪽, 왼쪽 줄 아래에서 위, 위 줄, 오른쪽 줄)
  function boxes(size) {
    const n = size / 4 + 1;
    const side = n - 1;
    const cell = BOARD / n;
    const found = [];
    for (let i = 0; i < size; i++) {
      let col;
      let row;
      if (i < side) { col = side - i; row = side; }
      else if (i < side * 2) { col = 0; row = side - (i - side); }
      else if (i < side * 3) { col = i - side * 2; row = 0; }
      else { col = side; row = i - side * 3; }
      found.push({ x: col * cell, y: row * cell, size: cell });
    }
    return found;
  }

  function diceFace(node, value) {
    node.className = `bd-dice f${value}`;
    [...node.children].forEach((pip, index) => pip.classList.toggle("on", (PIPS[value] || []).includes(index)));
  }

  function tokenSpot(player, at) {
    const box = cellBoxes[at] || cellBoxes[0];
    const here = state.players.map((item, index) => [item, index]).filter(([item]) => item.pos === at).map(([, index]) => index);
    const slot = Math.max(0, here.indexOf(player));
    const per = Math.ceil(Math.sqrt(Math.max(1, here.length)));
    const gap = box.size / (per + 1);
    return { x: 70 + box.x + gap * ((slot % per) + 1), y: 50 + box.y + box.size * 0.18 + (box.size * 0.82 / (per + 1)) * (Math.floor(slot / per) + 1) };
  }

  function placeTokens(turn) {
    state.players.forEach((player, index) => {
      const token = tokens.get(index);
      if (!token) return;
      const spot = tokenSpot(index, player.pos);
      token.style.left = `${spot.x}px`;
      token.style.top = `${spot.y}px`;
      token.classList.toggle("turn", index === turn);
    });
  }

  function showCard(event) {
    card.hidden = !event;
    if (!event) return;
    const who = el("div", "who");
    const mark = el("b");
    mark.style.background = event.color;
    who.append(mark, document.createTextNode(event.dice ? `${event.name}: 주사위 ${event.dice}` : event.name));
    const parts = [who, el("div", "what", event.text)];
    if (event.card_text) parts.push(el("span", "extra", `행운 카드: ${event.card_text}`));
    else if (event.again) parts.push(el("span", "extra", "한 번 더!"));
    else if (event.kind === "rest") parts.push(el("span", "extra", "다음 차례 쉬기"));
    if (event.laps) parts.push(el("span", "extra", "한 바퀴 완주!"));
    card.replaceChildren(...parts);
    card.style.animation = "none";
    void card.offsetWidth;
    card.style.animation = "";
  }

  function render(next) {
    state = next;
    root.dataset.design = next.design || "pastel";
    root.replaceChildren();
    tokens.clear();
    cellBoxes = boxes(next.size);
    const board = el("div", "bd-board");
    const cellSize = cellBoxes[0].size;
    board.style.setProperty("--cell", `${cellSize}px`);
    next.cells.forEach((cell, index) => {
      const node = el("div", `bd-cell k-${cell.kind}`);
      const box = cellBoxes[index];
      Object.assign(node.style, { left: `${box.x}px`, top: `${box.y}px`, width: `${box.size}px`, height: `${box.size}px` });
      if (cell.kind === "mission") node.append(el("span", "band"), el("span", "no", String(index)));
      node.append(el("span", "", cell.text));
      board.appendChild(node);
    });
    const center = el("div", "bd-center");
    Object.assign(center.style, { left: `${cellSize + 18}px`, top: `${cellSize + 18}px`, width: `${BOARD - cellSize * 2 - 36}px`, height: `${BOARD - cellSize * 2 - 36}px` });
    dice = el("div", "bd-dice f1");
    for (let k = 0; k < 9; k++) dice.appendChild(el("i"));
    diceFace(dice, next.event && next.event.dice ? next.event.dice : 1);
    card = el("div", "bd-card");
    center.append(el("div", "bd-title", next.title), dice, card);
    if (!next.playing) center.appendChild(el("div", "bd-hint", "참가자를 정하고 시작하면 말이 출발합니다"));
    board.appendChild(center);
    root.appendChild(board);
    const tokenSize = Math.min(58, cellSize * 0.42);
    next.players.forEach((player, index) => {
      const token = el("div", "bd-token", player.name.slice(0, 1));
      token.style.setProperty("--color", player.color);
      token.style.setProperty("--token", `${tokenSize}px`);
      root.appendChild(token);
      tokens.set(index, token);
    });
    placeTokens(next.turn);
    root.appendChild(panel(next));
    showCard(next.event);
  }

  function panel(next) {
    const box = el("div", "bd-panel");
    box.appendChild(el("h2", "", next.playing ? "참가자" : "주사위 판"));
    const list = el("ol", "bd-players");
    next.players.forEach((player, index) => {
      const item = el("li", index === next.turn ? "turn" : "");
      const mark = el("b");
      mark.style.background = player.color;
      const cell = next.cells[player.pos];
      item.append(mark, el("span", "name", player.name), el("small", "", `${player.laps ? `${player.laps}바퀴, ` : ""}${player.rest ? "쉬는 중, " : ""}${cell ? cell.text : ""}`));
      list.appendChild(item);
    });
    box.appendChild(list);
    if (next.playing && next.command) box.appendChild(el("div", "bd-command", `차례인 참가자가 채팅에 ${next.command} 를 쓰면 주사위를 굴림`));
    return box;
  }

  // ---------------------------------------------------------------- 굴리기 연출: 주사위, 칸마다 뛰기, 뒤로, 행운 카드, 도착 칸 빛
  async function hop(player, path) {
    const token = tokens.get(player);
    for (const at of path) {
      const before = state.players[player].pos;
      state.players[player].pos = at;
      const spot = tokenSpot(player, at);
      state.players[player].pos = before;
      token.style.left = `${spot.x}px`;
      token.style.top = `${spot.y}px`;
      token.classList.remove("hop");
      void token.offsetWidth;
      token.classList.add("hop");
      play("step");
      await wait(270);
    }
  }

  async function animate(next) {
    const event = next.event;
    card.hidden = true;
    if (event.dice) {
      dice.classList.add("rolling");
      play("rattle");
      for (let k = 0; k < 7; k++) {
        diceFace(dice, 1 + Math.floor(Math.random() * 6));
        await wait(110);
      }
      dice.classList.remove("rolling");
      diceFace(dice, event.dice);
      await wait(350);
      await hop(event.player, event.path || []);
      if (event.back) await hop(event.player, event.back);
      if (event.more) { play("lucky"); await hop(event.player, event.more); }
      if (event.card) play("lucky");
    }
    render(next);  // 모두의 마지막 자리(모두 1칸, 자리 바꾸기 포함)
    const landed = root.querySelectorAll(".bd-cell")[event.at];
    if (landed) landed.classList.add("landed");
    play("land");
  }

  let chain = Promise.resolve();
  let lastSeq = 0;
  function accept(data, initial) {
    const fresh = data.event && data.event.seq === data.seq && data.event.seq > lastSeq && !initial && state && state.playing;
    lastSeq = Math.max(lastSeq, data.seq || 0);
    if (fresh) return animate(data);
    render(data);
    return Promise.resolve();
  }

  if (params.has("sample")) {  // 그림 견본: 예시 참가자 4명이 판을 도는 중
    fetch("/board/state").then((response) => response.json()).then((snapshot) => {
      const names = ["고양이집사", "별빛구름", "노래하는토끼", "초코우유"];
      const colors = ["#ff4f8b", "#3ba7f0", "#f2b705", "#1f9d67"];
      const players = names.map((name, index) => ({ name, color: colors[index], pos: [3, 7, 7, 12][index] % snapshot.size, rest: 0, laps: index === 0 ? 1 : 0 }));
      const event = { seq: 1, player: 1, name: names[1], color: colors[1], dice: 4, path: [], at: 7, kind: "mission", text: snapshot.cells[7].text };
      render({ ...snapshot, players, turn: 2, playing: true, event });
    }).catch((error) => console.warn("debutkit 주사위 판 그림 견본", error));
  } else {
    window.debutkitLive.subscribe(["board", "theme"], (feed, data, initial) => {
      if (feed === "theme" && !initial) return state && render(state);
      if (feed !== "board" || !data || !data.cells) return;
      chain = chain.then(() => accept(data, initial)).catch((error) => console.warn("debutkit 주사위 판", error));
    });
  }
  window.debutkitBoard = { boxes, get state() { return state; } };  // 시험용
})();
