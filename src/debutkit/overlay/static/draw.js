// debutkit 후원 추첨 연출(OBS 브라우저 소스, 권장 1920x1080). /live?feeds=draw 로 추첨 결과를 받아 차례로 연출한다.
// 평소에는 투명하고, 결과가 오면 나타나 연출한 뒤 표시 시간이 지나면 사라진다. 연출: card(카드 뒤집기), wheel(룰렛).
// 뽑기는 서버가 하고 이 화면은 받은 결과를 보여 주기만 한다(모든 화면이 같은 결과). 글은 textContent로만 넣는다.
// 주소의 ?style=card, ?style=wheel 로 연출을 고정할 수 있다.
"use strict";

(() => {
  const root = document.getElementById("draw");
  const forced = new URLSearchParams(location.search).get("style");
  const STYLES = ["card", "wheel"];
  const COLORS = ["#ff4f8b", "#faf7f5", "#ffb3cb", "#8fd3ff", "#ff8fb1", "#e3dfdb"];  // 브랜드 Pink, Cream 계열. 희귀 Gold, 꽝 회색
  const DARK_TEXT = ["#faf7f5", "#ffb3cb", "#8fd3ff", "#ff8fb1", "#e3dfdb", "#ffd84d", "#aab2b8"];
  const queue = [];
  let busy = false;

  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  function amountText(result) {
    if (result.kind === "member") return "구독";
    const count = Number(result.amount).toLocaleString("ko-KR");
    if (result.unit === "원") return `${count}원 후원`;
    if (result.unit === "별풍선" || result.unit === "애드벌룬") return `${result.unit} ${count}개`;
    return `${count} ${result.unit}`.trim();
  }

  function summary(result) {  // 같은 상품은 횟수로 묶음
    const counts = new Map();
    for (const item of result.draws) counts.set(item.name, (counts.get(item.name) || 0) + 1);
    return "결과 " + [...counts].map(([name, count]) => (count > 1 ? `${name} ${count}회` : name)).join(", ");
  }

  function header(result) {
    const box = el("div", "draw-head");
    if (window.debutkit && window.debutkit.badge) box.appendChild(window.debutkit.badge(result));
    box.appendChild(el("div", "draw-name", `${result.name} 님`));
    box.appendChild(el("div", "draw-sub", `${amountText(result)}, 추첨 ${result.count}회${result.test ? " (시험)" : ""}`));
    return box;
  }

  function burst(target) {  // 희귀 상품 반짝임
    const layer = el("div", "burst");
    for (let i = 0; i < 36; i++) {
      const spark = el("span", "spark");
      const angle = Math.random() * Math.PI * 2;
      const distance = 90 + Math.random() * 170;
      spark.style.setProperty("--x", `${Math.cos(angle) * distance}px`);
      spark.style.setProperty("--y", `${Math.sin(angle) * distance}px`);
      spark.style.setProperty("--delay", `${Math.round(Math.random() * 140)}ms`);
      spark.style.setProperty("--hue", [45, 330, 190][i % 3]);
      layer.appendChild(spark);
    }
    target.appendChild(layer);
    setTimeout(() => layer.remove(), 1800);
  }

  // ---------------------------------------------------------------- 카드 뒤집기
  async function playCards(result, stage) {
    const size = result.count > 6 ? "many" : result.count > 3 ? "some" : "few";
    const grid = el("div", `draw-cards ${size}`);
    grid.style.setProperty("--columns", Math.min(result.count, 6));
    const cards = result.draws.map((item, index) => {
      const card = el("div", `draw-card${item.rare ? " rare" : ""}${item.miss ? " miss" : ""}`);
      card.style.setProperty("--i", index);
      const inner = el("div", "inner");
      inner.appendChild(el("div", "face back"));
      const front = el("div", "face front");
      front.appendChild(el("div", "prize", item.name));
      front.appendChild(el("div", "percent", `${item.percent}%`));
      if (item.rare) front.appendChild(el("div", "tag", "희귀"));
      inner.appendChild(front);
      card.appendChild(inner);
      grid.appendChild(card);
      return card;
    });
    stage.appendChild(grid);
    await wait(500 + result.count * 70);  // 카드가 모두 놓인 뒤 뒤집기
    const step = result.count > 6 ? 280 : 560;
    for (const card of cards) {
      card.classList.add("open");
      if (card.classList.contains("rare")) burst(card);
      await wait(step);
    }
  }

  // ---------------------------------------------------------------- 룰렛
  function wheel(prizes) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "-110 -110 220 220");
    svg.setAttribute("class", "wheel");
    const total = prizes.reduce((sum, prize) => sum + prize.percent, 0) || 1;
    const point = (degrees) => [Math.sin((degrees * Math.PI) / 180) * 100, -Math.cos((degrees * Math.PI) / 180) * 100];
    const segments = [];
    let start = 0;
    prizes.forEach((prize, index) => {
      const sweep = (prize.percent / total) * 360;
      const [x1, y1] = point(start);
      const [x2, y2] = point(start + sweep);
      const path = document.createElementNS(ns, "path");
      path.setAttribute("d", sweep >= 359.99 ? "M0,-100 A100,100 0 1,1 -0.01,-100 Z"
        : `M0,0 L${x1.toFixed(3)},${y1.toFixed(3)} A100,100 0 ${sweep > 180 ? 1 : 0},1 ${x2.toFixed(3)},${y2.toFixed(3)} Z`);
      // 마지막 칸이 첫 칸과 같은 색이 되지 않게
      let fill = prize.rare ? "#ffd84d" : prize.miss ? "#aab2b8" : COLORS[index % COLORS.length];
      if (index === prizes.length - 1 && index % COLORS.length === 0 && index > 0 && !prize.rare && !prize.miss) fill = COLORS[2];
      path.setAttribute("fill", fill);
      path.setAttribute("stroke", "#1e2327");
      path.setAttribute("stroke-width", "0.8");
      svg.appendChild(path);
      const mid = start + sweep / 2;
      if (sweep >= 6) {  // 좁은 칸은 이름 생략(결과 목록에 표시). 이름은 반지름 방향으로 써서 좁은 칸에도 들어가게
        const label = document.createElementNS(ns, "text");
        label.textContent = prize.name.length > 8 ? `${prize.name.slice(0, 7)}..` : prize.name;
        label.setAttribute("transform", `rotate(${(mid - 90).toFixed(2)}) translate(60,0)`);
        label.setAttribute("text-anchor", "middle");
        label.setAttribute("dominant-baseline", "central");
        label.setAttribute("font-size", String(Math.max(6, Math.min(11, sweep * 0.4)).toFixed(1)));
        label.setAttribute("fill", DARK_TEXT.includes(fill) ? "#1e2327" : "#faf7f5");
        svg.appendChild(label);
      }
      segments.push({ name: prize.name, mid, sweep });
      start += sweep;
    });
    const rim = document.createElementNS(ns, "circle");  // 어두운 배경에서 바퀴 경계가 보이도록
    rim.setAttribute("r", "101");
    rim.setAttribute("fill", "none");
    rim.setAttribute("stroke", "#faf7f5");
    rim.setAttribute("stroke-width", "3");
    svg.appendChild(rim);
    const hub = document.createElementNS(ns, "circle");
    hub.setAttribute("r", "13");
    hub.setAttribute("fill", "#faf7f5");
    hub.setAttribute("stroke", "#1e2327");
    hub.setAttribute("stroke-width", "2");
    svg.appendChild(hub);
    return { svg, segments };
  }

  async function playWheel(result, stage) {
    const box = el("div", "wheel-box");
    const { svg, segments } = wheel(result.prizes);
    box.appendChild(svg);
    box.appendChild(el("div", "pointer"));
    const chips = el("div", "wheel-results");
    stage.append(box, chips);
    const duration = result.count === 1 ? 4500 : Math.round(Math.max(1200, Math.min(3000, 9000 / result.count)));
    let rotation = 0;
    await wait(300);
    for (const item of result.draws) {
      const segment = segments.find((found) => found.name === item.name) || segments[0];
      const target = -(segment.mid + (Math.random() - 0.5) * segment.sweep * 0.6);  // 칸 가운데 근처(칸 경계는 피함)
      const turn = (((target - rotation) % 360) + 360) % 360;
      rotation += (result.count === 1 ? 5 : 3) * 360 + turn;
      svg.style.transition = `transform ${duration}ms cubic-bezier(0.12, 0.8, 0.2, 1)`;
      svg.style.transform = `rotate(${rotation.toFixed(2)}deg)`;
      box.dataset.rotation = rotation.toFixed(2);
      await wait(duration + 250);
      chips.appendChild(el("span", `chip${item.rare ? " rare" : ""}${item.miss ? " miss" : ""}`, item.name));
      if (item.rare) burst(box);
    }
  }

  // ---------------------------------------------------------------- 차례로 연출
  async function play(result) {
    const panel = el("div", "draw-panel");
    panel.appendChild(header(result));
    const stage = el("div", "draw-stage");
    panel.appendChild(stage);
    root.replaceChildren(panel);
    root.classList.add("show");
    const style = STYLES.includes(forced) ? forced : result.style;
    if (style === "wheel") await playWheel(result, stage);
    else await playCards(result, stage);
    panel.appendChild(el("div", "draw-summary", summary(result)));
    await wait(Math.max(2, Number(result.seconds) || 8) * 1000);
    root.classList.remove("show");
    await wait(500);
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
      }
    }
    busy = false;
  }

  function accept(result) {
    if (!result || !result.seq || !Array.isArray(result.draws) || !result.draws.length) return;
    queue.push(result);
    drain();
  }

  // 연결할 때(다시 연결 포함) 받는 첫 값은 지난 결과이므로 재생하지 않는다
  let first = true;
  const source = new EventSource("/live?feeds=draw");
  source.addEventListener("open", () => (first = true));
  source.addEventListener("draw", (message) => {
    const result = JSON.parse(message.data);
    if (first) {
      first = false;
      return;
    }
    accept(result);
  });
  // 미리보기(?sample=card 또는 ?sample=wheel): 저장한 상품표로 예시 추첨을 이 화면에서만 표시. OBS와 다른 화면에는 나가지 않음
  const sample = new URLSearchParams(location.search).get("sample");
  if (STYLES.includes(sample)) {
    document.body.classList.add("sample");
    fetch("/draw/config").then((response) => response.json()).then((config) => {
      const prizes = config.prizes;
      const rare = prizes.find((prize) => prize.rare) || prizes[prizes.length - 1];
      const draws = sample === "wheel" ? [rare] : [prizes[1] || prizes[0], rare, prizes[0]];
      accept({ seq: 1, time: Date.now() / 1000, test: false, name: "고양이집사", platform: "chzzk", kind: "donation", amount: sample === "wheel" ? 1000 : 5000,
               unit: "원", count: draws.length, draws, prizes, style: sample, seconds: 600 });
    });
  }
  window.debutkitDraw = { accept, queue, summary };  // 시험용
})();
