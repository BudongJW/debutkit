// debutkit 방송 이미지 만들기(/decor): 프사, 체키, 배너, 다시보기 썸네일, 시그니처 풍선 그림을 캔버스로 그려 저장(움짤 포함).
// 꾸미기(테두리, 파티클, 자막, 움직임, 프리셋, 손그림 펜)는 decor-fx.js. 움짤은 이 PC 서버(/decor/animate)에서 GIF로,
// 시그니처는 후원 벽(/wall/signature)에 바로 등록. 올린 그림, 움짤, 영상은 브라우저 안에서만 쓴다. 글은 textContent로만 넣는다.
"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const fx = window.debutkitDecorFx;
  const canvas = $("canvas");
  const ctx = canvas.getContext("2d");
  let formats = {};
  let format = "profile";
  let media = null;  // 그릴 그림: { kind: "image" | "frames" | "video", el, frames: [{ bitmap, ms }], total, box }
  let uploaded = "";  // 올린 파일의 주소(브라우저 안)
  let phase = null;  // 움짤 장면 위치(0에서 1, 한 바퀴). null이면 멈춘 그림
  const GIF_FRAMES = 24, GIF_DELAY = 80, GIF_MS = GIF_FRAMES * GIF_DELAY;
  const strokesByFormat = {};  // 손그림: 그림 종류별 획
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
    const width = image.videoWidth || image.width, height = image.videoHeight || image.height;
    const probe = document.createElement("canvas");
    const scale = Math.min(1, 512 / Math.max(width, height));
    probe.width = Math.max(1, Math.round(width * scale));
    probe.height = Math.max(1, Math.round(height * scale));
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
    if (right < 0) return { x: 0, y: 0, w: width, h: height };
    return { x: left / scale, y: top / scale, w: (right - left + 1) / scale, h: (bottom - top + 1) / scale };
  }

  // 지금 장면의 그림(움짤은 시간에 맞는 장, 영상은 맞춰 둔 위치)
  function current() {
    if (!media) return null;
    if (media.kind !== "frames") return media.el;
    let time = phase === null ? 0 : (phase * GIF_MS) % media.total;
    for (const frame of media.frames) {
      if (time < frame.ms) return frame.bitmap;
      time -= frame.ms;
    }
    return media.frames[media.frames.length - 1].bitmap;
  }

  const filling = () => media && $("place").value === "fill";

  function background(c, width, height, pattern) {
    if (filling()) {  // 올린 그림, 움짤, 영상으로 바탕을 꽉 채움(자유 편집)
      const image = current();
      const w = media.el.videoWidth || media.box.w, h = media.el.videoHeight || media.box.h;
      const scale = Math.max(width / w, height / h);
      ctx.drawImage(image, (width - w * scale) / 2, (height - h * scale) / 2, w * scale, h * scale);
      return;
    }
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

  // 캐릭터: 아래쪽에 붙여 높이 tall만큼, 가운데 x. 은은한 그림자와 움직임(움짤)
  function figure(cx, bottom, tall) {
    if (!media || filling()) return;
    const image = current();
    const box = media.box;
    const width = (box.w * tall) / box.h;
    const moved = fx.motion($("motion").value, phase, tall);
    ctx.save();
    ctx.translate(cx + moved.dx, bottom + moved.dy);
    ctx.rotate(moved.rotate);
    ctx.scale(moved.scale, moved.scale);
    ctx.shadowColor = "rgba(20, 10, 40, 0.35)";
    ctx.shadowBlur = tall * 0.04;
    ctx.shadowOffsetY = tall * 0.015;
    ctx.drawImage(image, box.x, box.y, box.w, box.h, -width / 2, -tall, width, tall);
    ctx.restore();
  }

  // 글꼴(공통 글꼴 목록, /theme 의 font_catalog): 제목(채널 이름, 금액)과 글(한 줄 소개, 시그니처 이름)
  let catalog = {};
  const loadedFonts = new Set();
  const face = (id, fallback) => catalog[$(id).value] || catalog[fallback] || { css: fallback === "pretendard" ? '"Pretendard", sans-serif' : '"Black Han Sans", sans-serif', weight: fallback === "pretendard" ? 700 : 400 };

  async function loadFont(item) {  // 그림에 쓰기 전에 파일을 불러 둠(canvas는 글꼴을 스스로 받지 않음)
    if (!item || !item.src || loadedFonts.has(item.src) || !window.FontFace) return;
    try {
      const font = new FontFace(item.family, `url("${item.src}")`, { weight: "100 900", display: "block" });
      document.fonts.add(await font.load());
      loadedFonts.add(item.src);
    } catch (error) {
      // 불러오지 못하면 다음 글꼴(맑은 고딕 등)로 그림
    }
  }

  async function fillFonts() {
    try {
      catalog = (await (await fetch("/theme")).json()).font_catalog || {};
    } catch (error) {
      catalog = {};
    }
    for (const [id, chosen] of [["title-font", "blackhan"], ["text-font", "pretendard"]]) {
      const groups = new Map();
      for (const [key, item] of Object.entries(catalog)) {
        if (!groups.has(item.group)) groups.set(item.group, Object.assign(document.createElement("optgroup"), { label: item.group }));
        groups.get(item.group).append(new Option(item.name, key));
      }
      $(id).replaceChildren(...groups.values());
      $(id).value = chosen;
    }
    await useFonts();
  }

  const useFonts = () => Promise.all([loadFont(catalog[$("title-font").value]), loadFont(catalog[$("text-font").value])]);

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

  // 글자 묶음: 채널 이름(큰 글씨, 흰색과 짙은 외곽), 한 줄 소개(자막 스타일)
  function texts(c, x, y, maxWidth, size, align) {
    const name = $("name").value.trim();
    const line = $("line").value.trim();
    ctx.textAlign = align;
    ctx.textBaseline = "alphabetic";
    if (name) {
      const title = face("title-font", "blackhan");
      const px = fitText(name, title.css, size, maxWidth, String(title.weight));
      ctx.lineJoin = "round";
      ctx.lineWidth = px * 0.14;
      ctx.strokeStyle = c.deep;
      ctx.strokeText(name, x, y);
      ctx.fillStyle = "#ffffff";
      ctx.fillText(name, x, y);
    }
    if (line) {
      const text = face("text-font", "pretendard");
      const px = fitText(line, text.css, size * 0.36, maxWidth * 0.9, String(text.weight));
      fx.caption(ctx, $("caption").value, line, x, y + size * 0.3, px, align, c, text, phase);
    }
  }

  function roundRect(x, y, w, h, r) {
    fx.outline(ctx, { type: "rect", x, y, w, h, r });
  }

  //: 시그니처 단위 -> 금액 뒤에 붙는 말
  const SUFFIX = { "별풍선": "개", "애드벌룬": "개", "원": "원", bits: " bits" };
  const sigAmount = () => Number(String($("sig-amount").value).replace(/[^0-9.]/g, ""));

  // 시그니처 풍선 그림: 둥근 카드(방송 색)에 빛살, 캐릭터, 이름 띠, 큰 금액. 카드 바깥은 투명
  function drawSignature(c, width, height, scale) {
    ctx.clearRect(0, 0, width, height);
    const pad = width * 0.04, radius = width * 0.14;
    const card = { type: "rect", x: pad, y: pad, w: width - pad * 2, h: height - pad * 2, r: radius };
    ctx.save();
    fx.outline(ctx, card);
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
    figure(width / 2, height * 0.74, height * 0.6 * scale);
    fx.particles(ctx, $("particles").value, width, height, c, phase);
    ctx.restore();
    fx.border(ctx, $("border").value, card, c, phase);
    const title = $("sig-title").value.trim();
    if (title) {  // 이름 띠
      const font = face("text-font", "pretendard");
      const px = fitText(title, font.css, height * 0.065, width * 0.66, String(font.weight));
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
      const font = face("title-font", "blackhan");
      const px = fitText(text, font.css, height * 0.19, width * 0.82, String(font.weight));
      ctx.textAlign = "center";
      ctx.lineJoin = "round";
      ctx.lineWidth = px * 0.16;
      ctx.strokeStyle = c.deep;
      ctx.strokeText(text, width / 2, height * 0.915);
      ctx.fillStyle = "#ffffff";
      ctx.fillText(text, width / 2, height * 0.915);
    }
  }

  // 체키(폴라로이드): 흰 종이에 사진 칸(고른 비율), 아래 넓은 여백에 손글씨 문구, 사진 오른쪽 아래 날짜 도장
  function chekiLayout() {
    const [a, b] = $("cheki-ratio").value.split(":").map(Number);
    const width = 1080, margin = width * 0.06, photoW = width - margin * 2, photoH = Math.round((photoW * b) / a);
    return { width, height: Math.round(margin + photoH + width * 0.24), photo: { x: margin, y: margin, w: photoW, h: photoH } };
  }

  function drawCheki(c, width, height, scale) {
    const { photo } = chekiLayout();
    ctx.fillStyle = "#fdfbf6";
    ctx.fillRect(0, 0, width, height);
    ctx.save();
    ctx.beginPath();
    ctx.rect(photo.x, photo.y, photo.w, photo.h);
    ctx.clip();
    ctx.translate(photo.x, photo.y);
    background(c, photo.w, photo.h, $("pattern").value);
    figure(photo.w / 2, photo.h, Math.min(photo.h * 0.92, photo.w * 1.1) * scale);
    fx.particles(ctx, $("particles").value, photo.w, photo.h, c, phase);
    fx.border(ctx, $("border").value, { type: "rect", x: 0, y: 0, w: photo.w, h: photo.h, r: 0 }, c, phase);
    if ($("cheki-date").checked) {  // 필름 날짜 도장
      const now = new Date();
      const stamp = `'${String(now.getFullYear()).slice(2)} ${String(now.getMonth() + 1).padStart(2, " ")} ${String(now.getDate()).padStart(2, " ")}`;
      ctx.font = `700 ${Math.round(photo.w * 0.045)}px "Galmuri11", Consolas, monospace`;
      ctx.textAlign = "right";
      ctx.fillStyle = "#ff8a2a";
      ctx.shadowColor = "#ff5a00";
      ctx.shadowBlur = photo.w * 0.01;
      ctx.fillText(stamp, photo.w * 0.95, photo.h * 0.95);
    }
    ctx.restore();
    const line = $("line").value.trim();
    if (line) {  // 손글씨 문구
      const font = face("text-font", "pretendard");
      const px = fitText(line, font.css, width * 0.075, photo.w * 0.92, String(font.weight));
      ctx.textAlign = "center";
      ctx.fillStyle = c.ink;
      ctx.fillText(line, width / 2, photo.y + photo.h + (height - photo.y - photo.h) / 2 + px * 0.35);
    }
  }

  // 그리기: guide가 참이면 안내선(프사 원, YouTube 안전 영역)도
  function draw(guide) {
    const spec = size();
    if (!spec) return;
    const { width, height } = spec;
    canvas.width = width;
    canvas.height = height;
    const c = colors();
    const scale = Number($("scale").value) / 100;
    if (format === "signature") drawSignature(c, width, height, scale);
    else if (format === "cheki") drawCheki(c, width, height, scale);
    else if (format === "profile") drawProfile(c, width, height, scale, guide);
    else drawBanner(c, width, height, scale, guide);
    fx.strokes(ctx, strokesByFormat[format] || [], width, height);
  }

  function drawProfile(c, width, height, scale, guide) {
    background(c, width, height, $("pattern").value);
    figure(width / 2, height * 0.98, height * 0.84 * scale);
    fx.particles(ctx, $("particles").value, width, height, c, phase);
    fx.border(ctx, $("border").value, { type: "circle", cx: width / 2, cy: height / 2, r: width / 2 }, c, phase);
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
  }

  // 배너, 썸네일: 안전 영역 안에 캐릭터와 글자
  function drawBanner(c, width, height, scale, guide) {
    background(c, width, height, $("pattern").value);
    const side = $("side").value;
    const safe = format === "youtube" ? { x: (width - 1546) / 2, y: (height - 423) / 2, w: 1546, h: 423 } : { x: 0, y: 0, w: width, h: height };
    const tall = Math.min(safe.h * 0.98 * scale, format === "youtube" ? safe.h * 1.4 : height * 1.2);
    const bottom = format === "youtube" ? safe.y + safe.h : height;
    const cx = side === "left" ? safe.x + safe.w * 0.2 : side === "center" ? safe.x + safe.w / 2 : safe.x + safe.w * 0.8;
    figure(cx, bottom, tall);
    fx.particles(ctx, $("particles").value, width, height, c, phase);
    const textAlign = side === "left" ? "right" : side === "right" ? "left" : "center";
    const textX = side === "left" ? safe.x + safe.w * 0.94 : side === "right" ? safe.x + safe.w * 0.06 : safe.x + safe.w / 2;
    const fontSize = safe.h * (format === "soop" ? 0.34 : 0.22);
    const textY = side === "center" ? safe.y + safe.h * 0.2 : safe.y + safe.h * (format === "soop" ? 0.5 : 0.52);
    texts(c, textX, textY, safe.w * (side === "center" ? 0.9 : 0.58), fontSize, textAlign);
    fx.border(ctx, $("border").value, { type: "rect", x: 0, y: 0, w: width, h: height, r: 0 }, c, phase);
    if (guide && format === "youtube") {
      ctx.save();
      ctx.setLineDash([24, 16]);
      ctx.lineWidth = 6;
      ctx.strokeStyle = "rgba(255, 255, 255, 0.85)";
      ctx.strokeRect(safe.x, safe.y, safe.w, safe.h);
      ctx.restore();
    }
  }

  const size = () => (format === "cheki" ? chekiLayout() : formats[format]);

  function redraw() {
    draw($("guide").checked);
  }

  // ---------------------------------------------------------------- 그림 고르기: 캐릭터, 올린 그림, 움짤(GIF, WebP), 영상(MP4, WebM)
  async function decodeFrames(file) {  // 움직이는 그림의 장들(브라우저의 ImageDecoder가 있을 때)
    if (!window.ImageDecoder || !["image/gif", "image/webp"].includes(file.type)) return null;
    try {
      const decoder = new ImageDecoder({ data: await file.arrayBuffer(), type: file.type });
      await decoder.tracks.ready;
      const track = decoder.tracks.selectedTrack;
      if (!track || track.frameCount < 2) return null;
      const frames = [];
      for (let index = 0; index < Math.min(track.frameCount, 90); index += 1) {
        const { image } = await decoder.decode({ frameIndex: index });
        frames.push({ bitmap: await createImageBitmap(image), ms: Math.max(20, (image.duration || 100000) / 1000) });
        image.close();
      }
      decoder.close();
      return frames;
    } catch (error) {
      return null;
    }
  }

  function loadVideo(src) {
    return new Promise((resolve, reject) => {
      const video = document.createElement("video");
      video.muted = true;
      video.playsInline = true;
      video.preload = "auto";
      video.onloadeddata = () => resolve(video);
      video.onerror = () => reject(new Error("영상을 불러오지 못함"));
      video.src = src;
    });
  }

  const seek = (video, seconds) => new Promise((resolve) => {
    if (Math.abs(video.currentTime - seconds) < 0.001) return resolve();
    video.onseeked = () => resolve();
    video.currentTime = seconds;
  });

  async function choose() {
    const option = $("character").selectedOptions[0];
    const file = uploaded ? $("upload").files[0] : null;
    media = null;
    try {
      if (file && file.type.startsWith("video/")) {
        const video = await loadVideo(uploaded);
        await seek(video, Math.min(0.5, (video.duration || 1) / 2));
        media = { kind: "video", el: video, box: { x: 0, y: 0, w: video.videoWidth, h: video.videoHeight } };
      } else if (file) {
        const frames = await decodeFrames(file);
        const first = await load(uploaded);
        media = frames ? { kind: "frames", el: first, frames, total: frames.reduce((sum, frame) => sum + frame.ms, 0) } : { kind: "image", el: first };
        media.box = trimmed(frames ? frames[0].bitmap : first);
      } else if (option && option.value) {
        const image = await load(option.value);
        media = { kind: "image", el: image, box: trimmed(image) };
      }
    } catch (error) {
      media = null;
      $("save-state").textContent = error.message;
    }
    $("place-row").hidden = !file;
    if (!file) $("place").value = "figure";
    $("media-note").textContent = !file ? "" : media && media.kind === "frames" ? `움짤 ${media.frames.length}장(움짤 저장에서 움직임)`
      : media && media.kind === "video" ? `영상 ${media.el.duration.toFixed(1)}초(움짤 저장은 앞 ${(GIF_MS / 1000).toFixed(1)}초)` : "";
    redraw();
  }

  function buildFormats() {
    $("formats").replaceChildren(...Object.entries(formats).map(([key, spec]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = key === "cheki" ? spec.name : `${spec.name} ${spec.width}x${spec.height}`;
      button.setAttribute("aria-pressed", String(key === format));
      button.addEventListener("click", () => {
        format = key;
        for (const other of $("formats").children) other.setAttribute("aria-pressed", String(other === button));
        $("format-note").textContent = spec.note;
        $("side").value = ["profile", "signature", "cheki"].includes(key) ? "center" : "right";
        fields();
        redraw();
      });
      return button;
    }));
    $("format-note").textContent = formats[format].note;
    fields();
  }

  // 그림 종류마다 쓰는 칸과 단추만: 시그니처는 단위, 금액, 이름과 후원 벽 등록, 체키는 비율과 날짜
  function fields() {
    const signature = format === "signature";
    const cheki = format === "cheki";
    $("sig-fields").hidden = !signature;
    $("cheki-fields").hidden = !cheki;
    $("to-wall").hidden = !signature;
    $("wall-gif-row").hidden = !signature;
    $("name").closest("label").hidden = signature || cheki;
    $("line").closest("label").hidden = signature;
    $("caption").closest("label").hidden = signature || cheki;
    $("side").closest("label").hidden = signature || cheki;
  }

  function download(href, name) {
    const link = document.createElement("a");
    link.href = href;
    link.download = name;
    link.click();
  }

  // 움짤: 24장(한 바퀴)을 긴 변 512px(프사, 시그니처) 또는 640px로 그려 이 PC 서버에서 GIF로(Pillow). 시그니처는 바깥 투명
  async function saveGif() {
    const spec = size();
    const longest = ["profile", "signature"].includes(format) ? 512 : 640;
    const ratio = Math.min(1, longest / Math.max(spec.width, spec.height));
    const small = document.createElement("canvas");
    small.width = Math.round(spec.width * ratio);
    small.height = Math.round(spec.height * ratio);
    const smallCtx = small.getContext("2d");
    smallCtx.imageSmoothingQuality = "high";
    $("save-gif").disabled = true;
    $("save-state").textContent = "움짤 장면 그리는 중";
    const frames = [];
    try {
      for (let index = 0; index < GIF_FRAMES; index += 1) {
        phase = index / GIF_FRAMES;
        if (media && media.kind === "video") await seek(media.el, ((phase * GIF_MS) / 1000) % Math.max(0.1, media.el.duration));
        draw(false);
        smallCtx.clearRect(0, 0, small.width, small.height);
        smallCtx.drawImage(canvas, 0, 0, small.width, small.height);
        frames.push(small.toDataURL("image/png"));
      }
      phase = null;
      redraw();
      $("save-state").textContent = "움짤 만드는 중";
      const transparent = format === "signature";
      const response = await fetch("/decor/animate", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ frames, delay: GIF_DELAY, transparent }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "움짤을 만들지 못함");
      const name = `debutkit-${format}-${small.width}x${small.height}.gif`;
      download(data.gif, name);
      lastGif = transparent ? data.gif : "";
      $("save-state").textContent = `저장함: ${name}(${Math.round(data.bytes / 1024)}KB)`;
    } catch (error) {
      $("save-state").textContent = error.message;
    } finally {
      phase = null;
      redraw();
      $("save-gif").disabled = false;
    }
  }

  // 후원 벽 시그니처로 등록: 같은 단위와 금액의 시그니처가 있으면 그림과 이름만 바꿈. 움직이는 시그니처를 만들었으면 그 GIF로
  let lastGif = "";
  async function toWall() {
    const unit = $("sig-unit").value;
    const amount = sigAmount();
    if (!(amount > 0)) { $("save-state").textContent = "시그니처 금액을 숫자로 입력"; return; }
    draw(false);
    const image = $("wall-gif").checked && lastGif ? lastGif : canvas.toDataURL("image/png");
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
      $("save-state").textContent = `후원 벽에 ${existing ? "바꿔" : "새로"} 등록함: ${body.title || "시그니처"}(${amount.toLocaleString("ko-KR")}${SUFFIX[unit] || ""})${image === lastGif ? ", 움직이는 그림" : ""}`;
    } catch (error) {
      $("save-state").textContent = error.message;
    } finally {
      $("to-wall").disabled = false;
    }
  }

  async function save() {
    const spec = size();
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

  // ---------------------------------------------------------------- 꾸미기 목록과 프리셋
  function fillSelect(id, table, chosen) {
    $(id).replaceChildren(...Object.entries(table).map(([key, name]) => new Option(typeof name === "string" ? name : name.name, key)));
    $(id).value = chosen;
  }

  async function applyPreset(key) {
    const preset = fx.PRESETS[key];
    if (!preset) return;
    for (const [id, name] of [["border", "border"], ["particles", "particles"], ["caption", "caption"], ["motion", "motion"], ["pattern", "pattern"]]) {
      $(id).value = preset[name];
    }
    if (catalog[preset.title]) $("title-font").value = preset.title;
    if (catalog[preset.text]) $("text-font").value = preset.text;
    await useFonts();
    redraw();
  }

  // ---------------------------------------------------------------- 손그림: 캔버스 위를 끌어 그림(펜 5종)
  let drawing = null;
  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)), Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height))];
  }
  canvas.addEventListener("pointerdown", (event) => {
    if (!$("pen-on").checked) return;
    event.preventDefault();
    canvas.setPointerCapture(event.pointerId);
    drawing = { pen: $("pen").value, color: $("pen-color").value, size: Number($("pen-size").value) / 1000, points: [point(event)] };
    (strokesByFormat[format] = strokesByFormat[format] || []).push(drawing);
    redraw();
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drawing) return;
    drawing.points.push(point(event));
    redraw();
  });
  for (const name of ["pointerup", "pointercancel"]) canvas.addEventListener(name, () => { drawing = null; });

  async function start() {
    fillSelect("border", fx.BORDERS, "ring");
    fillSelect("particles", fx.PARTICLES, "none");
    fillSelect("caption", fx.CAPTIONS, "band");
    fillSelect("motion", fx.MOTIONS, "float");
    fillSelect("pen", fx.PENS, "pen");
    $("preset").replaceChildren(new Option("직접 고르기", ""), ...Object.entries(fx.PRESETS).map(([key, item]) => new Option(item.name, key)));
    const data = await (await fetch("/decor/characters")).json();
    formats = data.formats;
    $("character").replaceChildren(...data.characters.map((item) => new Option(item.name + (item.active ? " (방송 중)" : ""), item.picture)));
    const active = data.characters.findIndex((item) => item.active);
    if (active >= 0) $("character").selectedIndex = active;
    buildFormats();
    $("side").value = "center";  // 처음 그림은 프사(가운데)
    if (document.fonts) await Promise.all(['40px "Black Han Sans"', '700 20px "Pretendard"', '700 20px "Galmuri11"'].map((font) => document.fonts.load(font))).catch(() => null);
    await fillFonts();
    await choose();
  }

  $("character").addEventListener("change", () => { if (uploaded) URL.revokeObjectURL(uploaded); uploaded = ""; $("upload").value = ""; choose(); });
  $("upload").addEventListener("change", () => {
    const file = $("upload").files[0];
    if (!file) return;
    if (uploaded) URL.revokeObjectURL(uploaded);
    uploaded = URL.createObjectURL(file);
    choose();
  });
  for (const id of ["name", "line", "sig-amount", "sig-title"]) $(id).addEventListener("input", redraw);
  for (const id of ["pattern", "scale", "side", "guide", "sig-unit", "border", "particles", "caption", "motion", "place", "cheki-ratio", "cheki-date"]) {
    $(id).addEventListener("input", () => { $("preset").value = ""; redraw(); });
  }
  for (const id of ["title-font", "text-font"]) $(id).addEventListener("change", async () => { await loadFont(catalog[$(id).value]); redraw(); });
  $("preset").addEventListener("change", () => applyPreset($("preset").value));
  $("pen-undo").addEventListener("click", () => { (strokesByFormat[format] || []).pop(); redraw(); });
  $("pen-clear").addEventListener("click", () => { strokesByFormat[format] = []; redraw(); });
  $("pen-on").addEventListener("change", () => canvas.classList.toggle("drawing", $("pen-on").checked));
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
    preset: applyPreset,
  };
  start();
})();
