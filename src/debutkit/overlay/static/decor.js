// debutkit 방송 이미지 만들기(/decor): 프사(움짤 포함), 배너, 다시보기 썸네일, 시그니처 풍선 그림을 캔버스로 그려 저장.
// 움짤은 이 PC 서버(/decor/animate)에서 GIF로, 시그니처는 후원 벽(/wall/signature)에 바로 등록. 글은 textContent로만 넣는다.
"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const canvas = $("canvas");
  const ctx = canvas.getContext("2d");
  let formats = {};
  let format = "profile";
  let picture = null;  // 그릴 캐릭터 그림(Image)
  let uploaded = "";  // 올린 그림의 주소(브라우저 안)
  let phase = null;  // 움짤 장면 위치(0에서 1, 한 바퀴). null이면 멈춘 그림
  const wave = (offset = 0) => (phase === null ? 0 : Math.sin((phase + offset) * Math.PI * 2));

  const css = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  const colors = () => ({
    primary: css("--dk-primary", "#a98bf7"), deep: css("--dk-primary-deep", "#5b3fc4"), light: css("--dk-primary-light", "#c2adff"),
    highlight: css("--dk-highlight", "#45d6b8"), onHighlight: css("--dk-on-highlight", "#231b3d"), ink: css("--dk-ink", "#231b3d"),
  });

  function load(src) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("그림을 불러오지 못함"));
      image.src = src;
    });
  }

  // 그림의 투명하지 않은 영역(캐릭터만 꼭 맞게 놓으려고). 투명 테두리가 넓은 그림도 같은 크기로 보이게
  function trimmed(image) {
    const probe = document.createElement("canvas");
    const scale = Math.min(1, 512 / Math.max(image.width, image.height));
    probe.width = Math.max(1, Math.round(image.width * scale));
    probe.height = Math.max(1, Math.round(image.height * scale));
    const p = probe.getContext("2d");
    p.drawImage(image, 0, 0, probe.width, probe.height);
    const data = p.getImageData(0, 0, probe.width, probe.height).data;
    let left = probe.width, top = probe.height, right = -1, bottom = -1;
    for (let y = 0; y < probe.height; y += 1) {
      for (let x = 0; x < probe.width; x += 1) {
        if (data[(y * probe.width + x) * 4 + 3] > 12) {
          left = Math.min(left, x); right = Math.max(right, x); top = Math.min(top, y); bottom = Math.max(bottom, y);
        }
      }
    }
    if (right < 0) return { x: 0, y: 0, w: image.width, h: image.height };
    return { x: left / scale, y: top / scale, w: (right - left + 1) / scale, h: (bottom - top + 1) / scale };
  }

  function background(c, width, height, pattern) {
    const g = ctx.createLinearGradient(0, 0, width, height);
    g.addColorStop(0, c.light);
    g.addColorStop(0.45, c.primary);
    g.addColorStop(1, c.deep);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, width, height);
    ctx.save();
    ctx.globalAlpha = 0.16;
    ctx.fillStyle = "#ffffff";
    ctx.strokeStyle = "#ffffff";
    const unit = Math.max(10, Math.min(width, height) / 14);
    if (pattern === "dots") {
      for (let y = unit / 2; y < height; y += unit) for (let x = (y / unit) % 2 ? unit : unit / 2; x < width; x += unit) {
        ctx.beginPath(); ctx.arc(x, y, unit * 0.12, 0, Math.PI * 2); ctx.fill();
      }
    } else if (pattern === "stripes") {
      ctx.lineWidth = unit * 0.28;
      for (let x = -height; x < width; x += unit) { ctx.beginPath(); ctx.moveTo(x, height); ctx.lineTo(x + height, 0); ctx.stroke(); }
    } else if (pattern === "stars") {
      let seed = 11;
      const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
      for (let k = 0; k < Math.round((width * height) / (unit * unit * 3)); k += 1) {
        const x = random() * width, y = random() * height, r = unit * (0.08 + random() * 0.16), offset = random();
        ctx.globalAlpha = 0.5 + 0.4 * wave(offset);  // 움짤에서는 별마다 다른 때에 반짝임
        star(x, y, r * (1 + 0.25 * wave(offset)));
      }
    }
    ctx.restore();
  }

  function star(x, y, r) {
    ctx.beginPath();
    for (let k = 0; k < 8; k += 1) {
      const angle = (k * Math.PI) / 4 - Math.PI / 2;
      const radius = k % 2 ? r * 0.38 : r;
      ctx[k ? "lineTo" : "moveTo"](x + Math.cos(angle) * radius, y + Math.sin(angle) * radius);
    }
    ctx.closePath();
    ctx.fill();
  }

  // 캐릭터: 아래쪽에 붙여 높이 tall만큼, 가운데 x. 은은한 그림자
  function figure(image, cx, bottom, tall) {
    if (!image) return;
    const box = image.dkBox || (image.dkBox = trimmed(image));
    const width = (box.w * tall) / box.h;
    const bob = tall * 0.012 * wave();  // 움짤에서 살짝 위아래로
    ctx.save();
    ctx.shadowColor = "rgba(20, 10, 40, 0.35)";
    ctx.shadowBlur = tall * 0.04;
    ctx.shadowOffsetY = tall * 0.015;
    ctx.drawImage(image, box.x, box.y, box.w, box.h, cx - width / 2, bottom - tall + bob, width, tall);
    ctx.restore();
  }

  // 넓이에 맞게 글자 크기 줄이기(ctx.font를 그 크기로 둠)
  function fitText(text, family, size, maxWidth, weight = "") {
    let px = Math.round(size);
    ctx.font = `${weight} ${px}px ${family}`;
    while (px > 8 && ctx.measureText(text).width > maxWidth) {
      px -= 1;
      ctx.font = `${weight} ${px}px ${family}`;
    }
    return px;
  }

  // 글자 묶음: 채널 이름(큰 글씨, 흰색과 짙은 외곽), 한 줄 소개(강조 색 띠)
  function texts(c, x, y, maxWidth, size, align) {
    const name = $("name").value.trim();
    const line = $("line").value.trim();
    ctx.textAlign = align;
    ctx.textBaseline = "alphabetic";
    if (name) {
      const px = fitText(name, '"Black Han Sans", sans-serif', size, maxWidth);
      ctx.lineJoin = "round";
      ctx.lineWidth = px * 0.14;
      ctx.strokeStyle = c.deep;
      ctx.strokeText(name, x, y);
      ctx.fillStyle = "#ffffff";
      ctx.fillText(name, x, y);
    }
    if (line) {
      const px = fitText(line, '"Pretendard", sans-serif', size * 0.36, maxWidth * 0.9, "700");
      const width = ctx.measureText(line).width + px * 1.2;
      const top = y + size * 0.3;
      const left = align === "center" ? x - width / 2 : align === "right" ? x - width : x;
      ctx.fillStyle = c.highlight;
      roundRect(left, top, width, px * 1.6, px * 0.8);
      ctx.fill();
      ctx.fillStyle = c.onHighlight;
      ctx.textAlign = "left";
      ctx.fillText(line, left + px * 0.6, top + px * 1.15);
    }
  }

  function roundRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  //: 시그니처 단위 -> 금액 뒤에 붙는 말
  const SUFFIX = { "별풍선": "개", "애드벌룬": "개", "원": "원", bits: " bits" };
  const sigAmount = () => Number(String($("sig-amount").value).replace(/[^0-9.]/g, ""));

  // 시그니처 풍선 그림: 둥근 카드(방송 색)에 빛살, 캐릭터, 이름 띠, 큰 금액. 카드 바깥은 투명
  function drawSignature(c, width, height, scale) {
    ctx.clearRect(0, 0, width, height);
    const pad = width * 0.04, radius = width * 0.14;
    ctx.save();
    roundRect(pad, pad, width - pad * 2, height - pad * 2, radius);
    ctx.clip();
    background(c, width, height, $("pattern").value);
    ctx.fillStyle = "#ffffff";
    for (let k = 0; k < 12; k += 1) {  // 캐릭터 뒤 빛살(움짤에서는 천천히 돎)
      const angle = (k / 12) * Math.PI * 2 + (phase || 0) * (Math.PI / 6);
      ctx.globalAlpha = 0.16;
      ctx.beginPath();
      ctx.moveTo(width / 2, height * 0.42);
      ctx.arc(width / 2, height * 0.42, width, angle, angle + Math.PI / 24);
      ctx.closePath();
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    figure(picture, width / 2, height * 0.74, height * 0.6 * scale);
    ctx.restore();
    ctx.lineWidth = width * 0.03;
    ctx.strokeStyle = c.highlight;
    roundRect(pad, pad, width - pad * 2, height - pad * 2, radius);
    ctx.stroke();
    const title = $("sig-title").value.trim();
    if (title) {  // 이름 띠
      const px = fitText(title, '"Pretendard", sans-serif', height * 0.065, width * 0.66, "700");
      const w = ctx.measureText(title).width + px * 1.4;
      ctx.fillStyle = c.highlight;
      roundRect(width / 2 - w / 2, height * 0.665, w, px * 1.7, px * 0.85);
      ctx.fill();
      ctx.fillStyle = c.onHighlight;
      ctx.textAlign = "center";
      ctx.fillText(title, width / 2, height * 0.665 + px * 1.22);
    }
    const amount = sigAmount();
    if (amount > 0) {  // 큰 금액
      const text = amount.toLocaleString("ko-KR") + (SUFFIX[$("sig-unit").value] || "");
      const px = fitText(text, '"Black Han Sans", sans-serif', height * 0.19, width * 0.82);
      ctx.textAlign = "center";
      ctx.lineJoin = "round";
      ctx.lineWidth = px * 0.16;
      ctx.strokeStyle = c.deep;
      ctx.strokeText(text, width / 2, height * 0.915);
      ctx.fillStyle = "#ffffff";
      ctx.fillText(text, width / 2, height * 0.915);
    }
  }

  // 그리기: guide가 참이면 안내선(프사 원, YouTube 안전 영역)도
  function draw(guide) {
    const spec = formats[format];
    if (!spec) return;
    const { width, height } = spec;
    canvas.width = width;
    canvas.height = height;
    const c = colors();
    const scale = Number($("scale").value) / 100;
    if (format === "signature") return drawSignature(c, width, height, scale);
    background(c, width, height, $("pattern").value);
    const side = $("side").value;
    if (format === "profile") {
      figure(picture, width / 2, height * 0.98, height * 0.84 * scale);
      ctx.save();
      ctx.lineWidth = width * 0.035;
      ctx.strokeStyle = c.highlight;
      ctx.shadowColor = c.highlight;
      ctx.shadowBlur = phase === null ? 0 : width * (0.02 + 0.02 * wave());  // 움짤: 테두리 빛이 숨쉬듯
      ctx.beginPath();
      ctx.arc(width / 2, height / 2, width / 2 - ctx.lineWidth / 2, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
      if ($("name").value.trim()) texts(c, width / 2, height * 0.86, width * 0.62, height * 0.1, "center");
      if (guide) {  // 원형으로 잘리는 바깥을 어둡게
        ctx.save();
        ctx.fillStyle = "rgba(0, 0, 0, 0.35)";
        ctx.beginPath();
        ctx.rect(0, 0, width, height);
        ctx.arc(width / 2, height / 2, width / 2, 0, Math.PI * 2, true);
        ctx.fill("evenodd");
        ctx.restore();
      }
      return;
    }
    // 배너, 썸네일: 안전 영역 안에 캐릭터와 글자
    const safe = format === "youtube" ? { x: (width - 1546) / 2, y: (height - 423) / 2, w: 1546, h: 423 } : { x: 0, y: 0, w: width, h: height };
    const tall = Math.min(safe.h * 0.98 * scale, format === "youtube" ? safe.h * 1.4 : height * 1.2);
    const bottom = format === "youtube" ? safe.y + safe.h : height;
    const cx = side === "left" ? safe.x + safe.w * 0.2 : side === "center" ? safe.x + safe.w / 2 : safe.x + safe.w * 0.8;
    figure(picture, cx, bottom, tall);
    const textAlign = side === "left" ? "right" : side === "right" ? "left" : "center";
    const textX = side === "left" ? safe.x + safe.w * 0.94 : side === "right" ? safe.x + safe.w * 0.06 : safe.x + safe.w / 2;
    const size = safe.h * (format === "soop" ? 0.34 : 0.22);
    const textY = side === "center" ? safe.y + safe.h * 0.2 : safe.y + safe.h * (format === "soop" ? 0.5 : 0.52);
    texts(c, textX, textY, safe.w * (side === "center" ? 0.9 : 0.58), size, textAlign);
    if (guide && format === "youtube") {
      ctx.save();
      ctx.setLineDash([24, 16]);
      ctx.lineWidth = 6;
      ctx.strokeStyle = "rgba(255, 255, 255, 0.85)";
      ctx.strokeRect(safe.x, safe.y, safe.w, safe.h);
      ctx.restore();
    }
  }

  function redraw() {
    draw($("guide").checked);
  }

  async function choose() {
    const option = $("character").selectedOptions[0];
    const src = uploaded || (option && option.value);
    picture = null;
    if (src) {
      try { picture = await load(src); } catch { picture = null; }
    }
    redraw();
  }

  function buildFormats() {
    $("formats").replaceChildren(...Object.entries(formats).map(([key, spec]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${spec.name} ${spec.width}x${spec.height}`;
      button.setAttribute("aria-pressed", String(key === format));
      button.addEventListener("click", () => {
        format = key;
        for (const other of $("formats").children) other.setAttribute("aria-pressed", String(other === button));
        $("format-note").textContent = spec.note;
        $("side").value = key === "profile" || key === "signature" ? "center" : "right";
        fields();
        redraw();
      });
      return button;
    }));
    $("format-note").textContent = formats[format].note;
    fields();
  }

  // 그림 종류마다 쓰는 칸과 단추만: 시그니처는 단위, 금액, 이름과 후원 벽 등록, 프사는 움짤
  function fields() {
    const signature = format === "signature";
    $("sig-fields").hidden = !signature;
    $("to-wall").hidden = !signature;
    $("save-gif").hidden = format !== "profile";
    for (const id of ["name", "line"]) $(id).closest("label").hidden = signature;
    $("side").closest("label").hidden = signature;
  }

  function download(href, name) {
    const link = document.createElement("a");
    link.href = href;
    link.download = name;
    link.click();
  }

  // 움짤 프사: 24장(한 바퀴)을 512px로 그려 이 PC 서버에서 GIF로(Pillow)
  async function saveGif() {
    const frames = [];
    const small = document.createElement("canvas");
    small.width = small.height = 512;
    const smallCtx = small.getContext("2d");
    smallCtx.imageSmoothingQuality = "high";
    for (let index = 0; index < 24; index += 1) {
      phase = index / 24;
      draw(false);
      smallCtx.clearRect(0, 0, 512, 512);
      smallCtx.drawImage(canvas, 0, 0, 512, 512);
      frames.push(small.toDataURL("image/png"));
    }
    phase = null;
    redraw();
    $("save-gif").disabled = true;
    $("save-state").textContent = "움짤 만드는 중";
    try {
      const response = await fetch("/decor/animate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ frames, delay: 80 }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "움짤을 만들지 못함");
      download(data.gif, "debutkit-profile-512.gif");
      $("save-state").textContent = `저장함: debutkit-profile-512.gif(${Math.round(data.bytes / 1024)}KB)`;
    } catch (error) {
      $("save-state").textContent = error.message;
    } finally {
      $("save-gif").disabled = false;
    }
  }

  // 후원 벽 시그니처로 등록: 같은 단위와 금액의 시그니처가 있으면 그림과 이름만 바꿈
  async function toWall() {
    const unit = $("sig-unit").value;
    const amount = sigAmount();
    if (!(amount > 0)) { $("save-state").textContent = "시그니처 금액을 숫자로 입력"; return; }
    draw(false);
    const image = canvas.toDataURL("image/png");
    redraw();
    $("to-wall").disabled = true;
    try {
      const state = await (await fetch("/wall/state")).json();
      const existing = ((state.config || {}).signatures || []).find((item) => item.unit === unit && Math.abs(item.amount - amount) < 0.005);
      const body = { unit, amount, title: $("sig-title").value.trim(), hide_number: existing ? existing.hide_number : false, image };
      if (existing) body.id = existing.id;
      const response = await fetch("/wall/signature", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "등록하지 못함");
      $("save-state").textContent = `후원 벽에 ${existing ? "바꿔" : "새로"} 등록함: ${body.title || "시그니처"}(${amount.toLocaleString("ko-KR")}${SUFFIX[unit] || ""})`;
    } catch (error) {
      $("save-state").textContent = error.message;
    } finally {
      $("to-wall").disabled = false;
    }
  }

  async function save() {
    const spec = formats[format];
    draw(false);
    const blob = (type, quality) => new Promise((resolve) => canvas.toBlob(resolve, type, quality));
    let data = await blob("image/png");
    let suffix = "png";
    if (format === "soop") {  // SOOP 방송국 배너: JPEG 200KB 이하
      for (let quality = 0.92; quality >= 0.5; quality -= 0.06) {
        data = await blob("image/jpeg", quality);
        if (data.size <= 200 * 1024) break;
      }
      suffix = "jpg";
    }
    const link = document.createElement("a");
    link.href = URL.createObjectURL(data);
    link.download = `debutkit-${format}-${spec.width}x${spec.height}.${suffix}`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 5000);
    $("save-state").textContent = `저장함: ${link.download}(${Math.round(data.size / 1024)}KB)`;
    redraw();
  }

  async function start() {
    const data = await (await fetch("/decor/characters")).json();
    formats = data.formats;
    $("character").replaceChildren(...data.characters.map((item) => new Option(item.name + (item.active ? " (방송 중)" : ""), item.picture)));
    const active = data.characters.findIndex((item) => item.active);
    if (active >= 0) $("character").selectedIndex = active;
    buildFormats();
    $("side").value = "center";  // 처음 그림은 프사(가운데)
    if (document.fonts) await Promise.all(['40px "Black Han Sans"', '700 20px "Pretendard"'].map((font) => document.fonts.load(font))).catch(() => null);
    await choose();
  }

  $("character").addEventListener("change", () => { uploaded = ""; $("upload").value = ""; choose(); });
  $("upload").addEventListener("change", () => {
    const file = $("upload").files[0];
    if (!file) return;
    if (uploaded) URL.revokeObjectURL(uploaded);
    uploaded = URL.createObjectURL(file);
    choose();
  });
  for (const id of ["name", "line", "sig-amount", "sig-title"]) $(id).addEventListener("input", redraw);
  for (const id of ["pattern", "scale", "side", "guide", "sig-unit"]) $(id).addEventListener("input", redraw);
  $("save").addEventListener("click", save);
  $("save-gif").addEventListener("click", saveGif);
  $("to-wall").addEventListener("click", toWall);
  // 문서 그림, 시험용: 그림 종류(key)를 그려 PNG 주소로. at은 움짤 장면 위치(0에서 1)
  window.debutkitDecor = {
    draw: (key, at = null) => {
      format = key;
      phase = at;
      draw(false);
      phase = null;
      return canvas.toDataURL("image/png");
    },
  };
  start();
})();
