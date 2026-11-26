// debutkit 캐릭터 그림 만들기(/character/sheet?id=): 등록한 VRM을 three-vrm으로 그려 정면, 3/4, 얼굴, 표정 7종 시트와 PNGTuber 4상태를 만든다.
// 모델 파일은 이 PC 서버(/character/files/)에서만 읽고, 등록할 때 그림(PNG)만 서버로 보낸다. 글은 textContent로만 넣는다.
import * as THREE from "three";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
//: 시트의 표정: [VRM 1.0 표정 이름, 이름표]. VRM 0.x(joy, sorrow, fun, a)는 three-vrm이 1.0 이름으로 바꿔 준다
const EXPRESSIONS = [["neutral", "기본"], ["happy", "기쁨"], ["angry", "화남"], ["sad", "슬픔"], ["relaxed", "편안"], ["aa", "아"], ["blink", "눈 감음"]];
//: PNGTuber 상태와 표정
const STATES = [["idle", "입 다묾", {}], ["talk", "입 벌림", { aa: 1 }], ["blink", "눈 감음", { blink: 1 }], ["talk_blink", "입 벌리고 눈 감음", { aa: 1, blink: 1 }]];
const PNG_SIZE = 1024;
//: 그릴 때 이 배수로 크게 그린 뒤 줄임(가장자리, 머리카락 끝이 매끄럽게)
const SUPER = 2;
//: 자세: 사람 모양 뼈(정규화) 회전 [x, y, z] 라디안, VRM 1.0 방향 기준(0.x는 x, z 부호를 바꿔 적용).
// 편하게 서기: 몸을 살짝 돌리고 한쪽 무릎을 굽힌 짝다리, 팔꿈치를 굽혀 손을 앞으로, 고개를 기울임
const RELAXED = {
  hips: [0, 0.2, 0.02], spine: [0.03, -0.07, -0.03], chest: [0, -0.06, -0.02], neck: [0, -0.04, 0.04], head: [0.06, -0.1, 0.1],
  leftUpperArm: [0, -0.25, -1.3], leftLowerArm: [0, -0.7, 0], leftHand: [0, 0, -0.2],
  rightUpperArm: [0, 0.2, 1.33], rightLowerArm: [0, 0.5, 0], rightHand: [0, 0, 0.2],
  leftUpperLeg: [0, 0, 0.04], rightUpperLeg: [-0.14, 0, -0.06], rightLowerLeg: [0.26, 0, 0], rightFoot: [-0.1, 0, 0],
};
const POSES = {
  relaxed: { name: "편하게 서기", bones: RELAXED },
  // 손 인사: 팔꿈치는 어깨 아래, 손은 얼굴 옆
  wave: { name: "손 인사", bones: { ...RELAXED, head: [0.05, -0.08, -0.1], rightUpperArm: [0, 0.35, 0.6], rightLowerArm: [0, 0, -2.05], rightHand: [0, 0, -0.2] } },
  a: { name: "A 자세(정면 확인용)", bones: { leftUpperArm: [0, 0, -1.2], rightUpperArm: [0, 0, 1.2], leftLowerArm: [0, 0, -0.12], rightLowerArm: [0, 0, 0.12] } },
};

let lib = null;
let loaderClass = null;
let current = null;  // { vrm, id }
const images = {};

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setPixelRatio(1);
renderer.setClearColor(0x000000, 0);
const scene = new THREE.Scene();
scene.add(new THREE.AmbientLight(0xffffff, 1.4));
const light = new THREE.DirectionalLight(0xffffff, 1.6);
light.position.set(0.6, 1.6, 2.2);
scene.add(light);
const camera = new THREE.PerspectiveCamera(18, 1, 0.05, 50);

function note(text, error = false) {
  $("state").textContent = text;
  $("state").classList.toggle("error", error);
}

async function libraries() {
  if (!lib) {
    lib = await import("/vendor/three-vrm/three-vrm.module.min.js");
    ({ GLTFLoader: loaderClass } = await import("three/addons/loaders/GLTFLoader.js"));
  }
}

async function load(id) {
  await libraries();
  const info = await (await fetch(`/character/info?id=${encodeURIComponent(id)}`)).json();
  if (!info.files || !info.files.model) throw new Error(info.error || "모델 파일을 찾지 못함");
  const loader = new loaderClass();
  loader.register((parser) => new lib.VRMLoaderPlugin(parser));
  const gltf = await loader.loadAsync(info.files.model);
  const vrm = gltf.userData.vrm;
  if (!vrm) throw new Error("VRM 정보를 읽지 못함");
  lib.VRMUtils.removeUnnecessaryVertices(gltf.scene);
  if (lib.VRMUtils.combineSkeletons) lib.VRMUtils.combineSkeletons(gltf.scene);
  lib.VRMUtils.rotateVRM0(vrm);
  if (current) scene.remove(current.vrm.scene);
  scene.add(vrm.scene);
  if (vrm.lookAt) vrm.lookAt.target = camera;
  // VRM 0.x는 모델 방향이 반대라 x, z 회전 부호도 반대(캐릭터 화면과 같음)
  current = { vrm, id, name: info.name, flip: vrm.meta && vrm.meta.metaVersion === "0" ? -1 : 1 };
  pose($("pose").value);
  express({});
  return info;
}

// 자세 적용(T 자세 그대로면 시트가 넓어지고 어색함)
function pose(key) {
  const { vrm, flip } = current;
  if (!vrm.humanoid) return;
  vrm.humanoid.resetNormalizedPose();
  for (const [bone, [x, y, z]] of Object.entries((POSES[key] || POSES.relaxed).bones)) {
    const node = vrm.humanoid.getNormalizedBoneNode(bone);
    if (node) node.rotation.set(x * flip, y, z * flip);
  }
  vrm.update(0);
}

function express(values) {
  const { vrm } = current;
  const manager = vrm.expressionManager;
  if (manager) {
    for (const expression of manager.expressions) manager.setValue(expression.expressionName, 0);
    for (const [name, value] of Object.entries(values)) {
      if (manager.getExpression(name)) manager.setValue(name, value);
      else if (name === "blink" && manager.getExpression("blinkLeft")) {  // 두 눈 표정 없이 좌우 따로만 있는 모델
        manager.setValue("blinkLeft", value);
        manager.setValue("blinkRight", value);
      }
    }
  }
  vrm.update(0);
}

function bone(name) {
  const node = current.vrm.humanoid && current.vrm.humanoid.getNormalizedBoneNode(name);
  const point = new THREE.Vector3();
  if (node) node.getWorldPosition(point);
  return node ? point : null;
}

// 틀 맞추기: 가운데 점(center)과 보일 높이(height)로 카메라 거리, 각도(yaw, 라디안. 0은 정면)
function frame(center, height, yaw, width, heightPx) {
  camera.aspect = width / heightPx;
  camera.updateProjectionMatrix();
  const fov = THREE.MathUtils.degToRad(camera.fov);
  const distance = (height / 2) / Math.tan(fov / 2);
  camera.position.set(center.x + Math.sin(yaw) * distance, center.y, center.z + Math.cos(yaw) * distance);
  camera.lookAt(center);
  current.vrm.update(0);  // 시선(lookAt)을 카메라 쪽으로
}

// 그림 한 장: SUPER배로 그린 뒤 줄인 투명 캔버스(다음 shot 전에 쓸 것)
const shotCanvas = document.createElement("canvas");
function shot(width, height) {
  renderer.setSize(width * SUPER, height * SUPER, false);
  renderer.render(scene, camera);
  shotCanvas.width = width;
  shotCanvas.height = height;
  const ctx = shotCanvas.getContext("2d");
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(renderer.domElement, 0, 0, width, height);
  return shotCanvas;
}

// 무대 배경: 위가 밝은 남보라 그라데이션, 캐릭터 뒤 라벤더 빛(glowY: 빛 높이 비율), 작은 별
function stage(ctx, x, y, width, height, glowY, stars = 0) {
  const sky = ctx.createLinearGradient(0, y, 0, y + height);
  sky.addColorStop(0, "#2b2249");
  sky.addColorStop(1, "#110e1d");
  ctx.fillStyle = sky;
  ctx.fillRect(x, y, width, height);
  const cx = x + width / 2;
  const cy = y + height * glowY;
  const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(width, height) * 0.55);
  glow.addColorStop(0, "rgba(169, 139, 247, 0.42)");
  glow.addColorStop(1, "rgba(169, 139, 247, 0)");
  ctx.fillStyle = glow;
  ctx.fillRect(x, y, width, height);
  let seed = 7;
  const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let index = 0; index < stars; index += 1) {
    ctx.fillStyle = `rgba(255, 255, 255, ${0.25 + random() * 0.5})`;
    ctx.beginPath();
    ctx.arc(x + random() * width, y + random() * height * 0.7, 0.6 + random() * 1.2, 0, Math.PI * 2);
    ctx.fill();
  }
}

// 바닥 빛(민트 타원): 발 아래
function floorGlow(ctx, cx, cy, radius) {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(1, 0.2);
  const glow = ctx.createRadialGradient(0, 0, 0, 0, 0, radius);
  glow.addColorStop(0, "rgba(69, 214, 184, 0.6)");
  glow.addColorStop(1, "rgba(69, 214, 184, 0)");
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(0, 0, radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function bodyBox() {
  const box = new THREE.Box3().setFromObject(current.vrm.scene);
  return { center: box.getCenter(new THREE.Vector3()), height: box.max.y - box.min.y };
}

// 머리 크기(머리 뼈에서 머리끝까지). 등신이 달라도(치비 2.5등신에서 애니풍 7등신까지) 얼굴, 표정, PNGTuber 틀이 머리에 맞도록
// 애니풍 VRM(VRoid)은 약 0.23m, 큰 머리 로우폴리(100Avatars)는 약 0.45m. 머리 위 장식이 너무 높으면 엉덩이에서 머리까지의 1.2배로 제한
function headSize() {
  const head = bone("head");
  const box = new THREE.Box3().setFromObject(current.vrm.scene);
  if (!head) return { head: box.getCenter(new THREE.Vector3()), size: (box.max.y - box.min.y) * 0.14 };
  const hips = bone("hips");
  const limit = hips ? Math.max(0.12, (head.y - hips.y) * 1.2) : 1;
  return { head, size: Math.min(limit, Math.max(0.12, box.max.y - head.y)) };
}

// 머리끝 위 여백(margin)을 두고 위에서부터 span만큼 보이는 틀(둘 다 머리 크기의 배수): { center, height }
function headFrame(span, margin) {
  const { head, size } = headSize();
  const top = head.y + size * (1 + margin);
  return { center: new THREE.Vector3(head.x, top - (span * size) / 2, head.z), height: span * size };
}

function label(ctx, text, x, y) {
  ctx.font = "600 15px Pretendard, 'Malgun Gothic', sans-serif";
  const width = ctx.measureText(text).width + 14;
  ctx.fillStyle = "rgba(255, 255, 255, 0.1)";
  ctx.fillRect(x, y, width, 24);
  ctx.fillStyle = "#d8dde3";
  ctx.fillText(text, x + 7, y + 17);
}

function drawSheet(name) {
  const canvas = $("sheet");
  const ctx = canvas.getContext("2d");
  stage(ctx, 0, 0, 1040, canvas.height, 0.42, 26);
  express({});
  const body = bodyBox();
  for (const [index, [title, yaw]] of [["정면", 0], ["3/4", 0.62]].entries()) {
    frame(body.center, body.height * 1.08, yaw, 520, 880);
    floorGlow(ctx, index * 520 + 260, 20 + 880 * (0.5 + 0.5 / 1.08), 200);
    ctx.drawImage(shot(520, 880), index * 520, 20, 520, 880);
    label(ctx, title, index * 520 + 10, 44);
  }
  const face = headFrame(1.6, 0.08);
  frame(face.center, face.height, 0, 560, 420);
  stage(ctx, 1040, 0, 560, 420, 0.45, 10);
  ctx.drawImage(shot(560, 420), 1040, 0);
  label(ctx, "얼굴", 1050, 10);
  EXPRESSIONS.forEach(([expression, title], index) => {
    express({ [expression]: 1 });
    const x = 1040 + (index % 4) * 140;
    const y = 420 + Math.floor(index / 4) * 240;
    const cell = headFrame(2.2, 0.15);
    frame(cell.center, cell.height, 0, 140, 240);
    stage(ctx, x, y, 140, 240, 0.35);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
    ctx.strokeRect(x + 0.5, y + 0.5, 139, 239);
    ctx.drawImage(shot(140, 240), x, y);
    label(ctx, title, x + 6, y + 8);
  });
  stage(ctx, 1460, 660, 140, 240, 0.35);  // 표정 7칸 뒤 빈칸도 같은 배경
  express({});
  ctx.font = "700 18px Pretendard, 'Malgun Gothic', sans-serif";
  ctx.fillStyle = "#ffffff";
  ctx.fillText(name, 14, 22);
  $("save-sheet").disabled = false;
}

function drawStates() {
  const box = $("states");
  box.replaceChildren();
  for (const [state, title, values] of STATES) {
    express(values);
    const bust = headFrame(3.16, 0.1);  // 가슴 위, 머리 위 여백
    frame(bust.center, bust.height, 0, PNG_SIZE, PNG_SIZE);
    images[state] = shot(PNG_SIZE, PNG_SIZE).toDataURL("image/png");
    const figure = document.createElement("figure");
    const img = document.createElement("img");
    img.src = images[state];
    img.alt = `${title} 그림`;
    const caption = document.createElement("figcaption");
    caption.textContent = title;
    figure.append(img, caption);
    box.appendChild(figure);
  }
  express({});
  $("register").disabled = false;
}

async function draw() {
  const id = $("pick").value;
  if (!id) return note("등록한 VRM이 없음: 설정 마법사의 캐릭터 단계에서 VRM 추가", true);
  $("draw").disabled = true;
  $("register").disabled = true;
  note("불러오는 중");
  try {
    const info = await load(id);
    drawSheet(info.name);
    drawStates();
    note("그림 완료");
  } catch (error) {
    note(`그리지 못함: ${error.message}`, true);
  } finally {
    $("draw").disabled = false;
  }
}

// 모델 점검: 표정(캐릭터 화면이 쓰는 입 모양, 눈 깜빡임, 웃음)과 텍스처 무게. 무거우면 가벼운 사본 단추
const EMOTION_NAMES = { happy: "기쁨", angry: "화남", sad: "슬픔", relaxed: "편안", surprised: "놀람" };
const megabytes = (bytes) => `${(bytes / 1048576).toFixed(1)}MB`;

async function checkModel() {
  const id = $("pick").value;
  $("check-box").hidden = !id;
  $("lighten").disabled = true;
  $("light-state").textContent = "";
  if (!id) return;
  const response = await fetch(`/character/sheet/check?id=${encodeURIComponent(id)}`);
  const data = await response.json();
  if (!response.ok) {
    $("check").replaceChildren(Object.assign(document.createElement("li"), { textContent: data.error || "점검하지 못함", className: "warn" }));
    return;
  }
  const texture = data.textures;
  const emotions = data.emotions.map((name) => EMOTION_NAMES[name]).join(", ");
  const lines = [
    [`감정 표정 ${data.emotions.length}/5${emotions ? `(${emotions})` : ""}: 표정 시트와 얼굴 추적의 웃음`, !data.emotions.includes("happy")],
    [`입 모양 ${data.vowels.length}/5${data.vowels.includes("aa") ? "" : data.jaw ? ", 말할 때 턱 뼈로 움직임" : ""}`, !data.vowels.includes("aa") && !data.jaw],
    [`눈 깜빡임: ${{ both: "두 눈 함께", sides: "좌우 따로" }[data.blink] || "없음"}`, !data.blink],
    [data.perfect_sync ? `퍼펙트 싱크: ARKit 표정 ${data.perfect_sync}개(얼굴 추적으로 얼굴 전체가 움직임)` : "퍼펙트 싱크 없음: 얼굴 추적은 입, 눈, 웃음만", false],
    [`텍스처 ${texture.count}장, 가장 큰 그림 ${texture.largest}px, 그래픽 메모리 약 ${texture.gpu_mb}MB, 파일 ${megabytes(data.size)}`, false],
    ...data.warnings.map((text) => [text, true]),
  ];
  $("check").replaceChildren(...lines.map(([text, warn]) => Object.assign(document.createElement("li"), { textContent: text, className: warn ? "warn" : "" })));
  const shrinkable = texture.largest > data.light;
  $("lighten").disabled = !shrinkable || !data.modification;
  $("light-state").textContent = !data.modification ? "모델 제작자가 수정을 허용하지 않음" : shrinkable ? "" : `이미 가벼움(텍스처 ${data.light}px 이하)`;
}

$("pick").addEventListener("change", checkModel);
$("pose").replaceChildren(...Object.entries(POSES).map(([key, item]) => new Option(item.name, key)));
$("pose").addEventListener("change", () => {
  if (!current) return;
  pose($("pose").value);
  drawSheet(current.name);
  drawStates();
});
$("lighten").addEventListener("click", async () => {
  $("lighten").disabled = true;
  $("light-state").classList.remove("error");
  $("light-state").textContent = "만드는 중(몇 초)";
  try {
    const response = await fetch("/character/lighten", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: $("pick").value }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "만들지 못함");
    $("pick").append(new Option(data.name, data.id));
    $("light-state").textContent = `${data.name} 등록: ${megabytes(data.before)}에서 ${megabytes(data.after)}(텍스처 ${data.images}장 줄임)`;
    if (window.debutkitUi) window.debutkitUi.toast(`${data.name} 등록`);
  } catch (error) {
    $("light-state").textContent = error.message;
    $("light-state").classList.add("error");
    $("lighten").disabled = false;
  }
});
$("draw").addEventListener("click", draw);
$("save-sheet").addEventListener("click", () => {
  const link = document.createElement("a");
  link.href = $("sheet").toDataURL("image/png");
  link.download = "character-sheet.png";
  link.click();
});
$("register").addEventListener("click", async () => {
  $("register").disabled = true;
  try {
    const response = await fetch("/character/pngtuber", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: current.id, name: $("name").value.trim(), images }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "등록하지 못함");
    note(`등록함: ${data.name}(캐릭터 목록에서 방송에 사용)`);
    if (window.debutkitUi) window.debutkitUi.toast(`${data.name} 등록`);
  } catch (error) {
    note(error.message, true);
    $("register").disabled = false;
  }
});

fetch("/character/sheet/list").then((response) => response.json()).then((data) => {
  const list = data.characters || [];
  $("pick").replaceChildren(...list.map((item) => new Option(item.name + (item.active ? " (방송 중)" : ""), item.id)));
  const wanted = params.get("id");
  if (wanted && list.some((item) => item.id === wanted)) $("pick").value = wanted;
  checkModel();
  if (!list.length) {
    note("등록한 VRM이 없음", true);
    if (window.debutkitUi) $("empty").replaceChildren(window.debutkitUi.mascot("dessaengi", "아직 VRM 캐릭터가 없음. 설정 마법사의 캐릭터 단계에서 VRM을 추가하거나 VRoid Studio로 만들기"));
  }
  else if (wanted) draw();
});
