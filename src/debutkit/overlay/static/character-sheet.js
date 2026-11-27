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
//: 부위별 자세(부위마다 골라 조합): 사람 모양 뼈(정규화) 회전 [x, y, z] 라디안, VRM 1.0 방향 기준(0.x는 x, z 부호를 바꿔 적용).
// x: 앞뒤로 숙임(+ 앞), y: 돌기, z: 옆으로. 왼팔은 캐릭터의 왼쪽(정면 그림에서는 화면 오른쪽), 오른팔은 왼팔을 좌우 반전
const LEFT_ARM = {
  down: { name: "내림", bones: { leftUpperArm: [0, 0, -1.22], leftLowerArm: [0, 0, -0.12] } },
  relaxed: { name: "편하게", bones: { leftUpperArm: [0, -0.25, -1.3], leftLowerArm: [0, -0.7, 0], leftHand: [0, 0, -0.2] } },
  hip: { name: "허리에 손", bones: { leftUpperArm: [0, 0.25, -0.75], leftLowerArm: [0, -0.3, -1.75], leftHand: [0, 0, 0.45] } },  // 팔꿈치는 밖으로, 손은 허리로
  wave: { name: "손 흔들기", bones: { leftUpperArm: [0, -0.35, -0.6], leftLowerArm: [0, 0, 2.05], leftHand: [0, 0, 0.2] } },
  up: { name: "만세", bones: { leftUpperArm: [0, 0, 1.1], leftLowerArm: [0, 0, 0.15] } },
  front: { name: "앞으로 모음", bones: { leftUpperArm: [0, -0.55, -1.15], leftLowerArm: [0, -1.25, 0], leftHand: [0, 0, -0.1] } },
};
const mirrorArm = (options) => Object.fromEntries(Object.entries(options).map(([key, item]) => [key, { name: item.name,
  bones: Object.fromEntries(Object.entries(item.bones).map(([bone, [x, y, z]]) => [bone.replace("left", "right"), [x, -y, -z]])) }]));
const PARTS = {
  body: { name: "몸", options: {
    straight: { name: "바로", bones: {} },
    turn: { name: "살짝 돌기", bones: { hips: [0, 0.2, 0.02], spine: [0.03, -0.07, -0.03], chest: [0, -0.06, -0.02] } },
    lean: { name: "기울이기", bones: { hips: [0, 0.1, -0.04], spine: [0, 0, 0.07], chest: [0, 0, 0.05] } },
    bow: { name: "살짝 숙이기", bones: { spine: [0.12, 0, 0], chest: [0.08, 0, 0] } },
  } },
  head: { name: "머리", options: {
    front: { name: "정면", bones: {} },
    tilt: { name: "갸웃", bones: { neck: [0, -0.04, 0.04], head: [0.06, -0.1, 0.1] } },
    tiltOther: { name: "반대로 갸웃", bones: { neck: [0, 0.04, -0.04], head: [0.05, 0.08, -0.1] } },
    down: { name: "내려다보기", bones: { neck: [0.08, 0, 0], head: [0.15, 0, 0] } },
    up: { name: "올려다보기", bones: { neck: [-0.06, 0, 0], head: [-0.14, 0, 0] } },
  } },
  leftArm: { name: "왼팔", options: LEFT_ARM },
  rightArm: { name: "오른팔", options: mirrorArm(LEFT_ARM) },
  legs: { name: "다리", options: {
    stand: { name: "차렷", bones: {} },
    contra: { name: "짝다리", bones: { leftUpperLeg: [0, 0, 0.04], rightUpperLeg: [-0.14, 0, -0.06], rightLowerLeg: [0.26, 0, 0], rightFoot: [-0.1, 0, 0] } },
    wide: { name: "벌리기", bones: { leftUpperLeg: [0, 0, 0.12], rightUpperLeg: [0, 0, -0.12], leftFoot: [0, 0, -0.1], rightFoot: [0, 0, 0.1] } },
    step: { name: "한 발 앞으로", bones: { leftUpperLeg: [-0.3, 0, 0.02], leftLowerLeg: [0.18, 0, 0], leftFoot: [0.1, 0, 0], rightUpperLeg: [0.12, 0, 0] } },
  } },
};
//: 추천 자세: 부위별 고른 값. 고른 뒤 부위를 바꾸면 직접 조합
const PRESETS = {
  relaxed: { name: "편하게 서기", parts: { body: "turn", head: "tilt", leftArm: "relaxed", rightArm: "relaxed", legs: "contra" } },
  wave: { name: "손 인사", parts: { body: "turn", head: "tiltOther", leftArm: "relaxed", rightArm: "wave", legs: "contra" } },
  hip: { name: "허리에 손", parts: { body: "lean", head: "tilt", leftArm: "hip", rightArm: "relaxed", legs: "contra" } },
  cheer: { name: "만세", parts: { body: "straight", head: "up", leftArm: "up", rightArm: "up", legs: "wide" } },
  a: { name: "A 자세(정면 확인용)", parts: { body: "straight", head: "front", leftArm: "down", rightArm: "down", legs: "stand" } },
};
const poseState = { ...PRESETS.relaxed.parts };

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
  applyPose();
  express({});
  return info;
}

//: 관절 직접 돌리기: 뼈 -> [x, y, z] 라디안(VRM 1.0 방향). 고른 자세 위에 더함
const tweaks = {};
//: 자세 파일(VRMA, VPD)에서 받은 자세: 뼈 -> [x, y, z, w](VRM 1.0 방향 정규화 뼈 회전). 있으면 부위별 자세 대신
let filePose = null;

// 자세 적용: 자세 파일이 있으면 그 자세, 없으면 부위별로 고른 뼈 회전. 그 위에 관절 직접 돌리기(T 자세 그대로면 시트가 넓어지고 어색함)
function applyPose() {
  const { vrm, flip } = current;
  if (!vrm.humanoid) return;
  vrm.humanoid.resetNormalizedPose();
  const node = (bone) => vrm.humanoid.getNormalizedBoneNode(bone);
  if (filePose) {
    for (const [bone, [x, y, z, w]] of Object.entries(filePose)) {
      const target = node(bone);
      if (target) target.quaternion.set(x * flip, y, z * flip, w);
    }
  } else {
    const bones = {};
    for (const [part, key] of Object.entries(poseState)) Object.assign(bones, (PARTS[part].options[key] || {}).bones);
    for (const [bone, [x, y, z]] of Object.entries(bones)) {
      const target = node(bone);
      if (target) target.rotation.set(x * flip, y, z * flip);
    }
  }
  const turn = new THREE.Quaternion();
  const euler = new THREE.Euler();
  for (const [bone, [x, y, z]] of Object.entries(tweaks)) {
    const target = node(bone);
    const side = bone.startsWith("right") ? -1 : 1;  // 오른쪽은 거울로(같은 값이면 양쪽이 같은 동작)
    if (target && (x || y || z)) target.quaternion.multiply(turn.setFromEuler(euler.set(x * flip, y * side, z * flip * side)));
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
    drawPose();
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
// ---------------------------------------------------------------- 포즈 그림: 부위별로 고르기, 잠금, 랜덤, 표정, 각도, PNG 저장
const FACES = [...EXPRESSIONS.filter(([name]) => name !== "aa" && name !== "blink"), ["surprised", "놀람"]];
const ANGLES = [["정면", 0], ["살짝 옆", 0.3], ["3/4", 0.62]];
const locks = {};

// 포즈 그림 한 장: 온몸, 고른 표정과 각도. background가 거짓이면 투명
function renderPose(width, height, background, face = $("pose-face").value) {
  express({ [face]: face === "neutral" ? 0 : 1 });
  const body = bodyBox();
  frame(body.center, body.height * 1.1, Number($("pose-angle").value), width, height);
  const out = document.createElement("canvas");
  out.width = width;
  out.height = height;
  const ctx = out.getContext("2d");
  if (background) {
    stage(ctx, 0, 0, width, height, 0.42, 18);
    floorGlow(ctx, width / 2, height * (0.5 + 0.5 / 1.1), width * 0.36);
  }
  ctx.drawImage(shot(width, height), 0, 0);
  express({});
  return out;
}

function drawPose() {
  if (!current) return;
  const canvas = $("pose-shot");
  const picture = renderPose(canvas.width, canvas.height, $("pose-bg").checked);
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(picture, 0, 0);
  $("save-pose").disabled = false;
}

let redrawTimer = 0;
function redraw(all = true) {  // 부위를 바꾸면 시트, 4상태, 포즈 그림을 다시(연속으로 바꿀 때는 마지막만)
  if (!current) return;
  clearTimeout(redrawTimer);
  redrawTimer = setTimeout(() => {
    applyPose();
    if (all) {
      drawSheet(current.name);
      drawStates();
    }
    drawPose();
    if (vmcOn) vmcSend();
  }, 120);
}

function syncParts() {
  for (const part of Object.keys(PARTS)) $(`part-${part}`).value = poseState[part];
  const preset = Object.entries(PRESETS).find(([, item]) => Object.entries(item.parts).every(([part, key]) => poseState[part] === key));
  $("pose").value = preset ? preset[0] : "custom";
}

function buildPoseControls() {
  $("pose").replaceChildren(...Object.entries(PRESETS).map(([key, item]) => new Option(item.name, key)), new Option("직접 조합", "custom"));
  $("parts").replaceChildren(...Object.entries(PARTS).map(([part, item]) => {
    const row = document.createElement("div");
    row.className = "part";
    const name = document.createElement("span");
    name.textContent = item.name;
    const select = document.createElement("select");
    select.id = `part-${part}`;
    select.setAttribute("aria-label", `${item.name} 자세`);
    select.append(...Object.entries(item.options).map(([key, option]) => new Option(option.name, key)));
    select.addEventListener("change", () => {
      dropFilePose();
      poseState[part] = select.value;
      syncParts();
      redraw();
    });
    const lock = document.createElement("label");
    lock.className = "check";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.addEventListener("change", () => (locks[part] = box.checked));
    lock.append(box, document.createTextNode(" 잠금"));
    row.append(name, select, lock);
    return row;
  }));
  $("pose-face").replaceChildren(...FACES.map(([key, title]) => new Option(title, key)));
  $("pose-angle").replaceChildren(...ANGLES.map(([title, yaw]) => new Option(title, String(yaw))));
  syncParts();
}

buildPoseControls();

// ---------------------------------------------------------------- 관절 직접 돌리기
//: 돌릴 수 있는 관절: [VRM 뼈 이름, 이름표]. 왼쪽, 오른쪽은 캐릭터 기준
const JOINTS = [["hips", "엉덩이"], ["spine", "허리"], ["chest", "가슴"], ["neck", "목"], ["head", "머리"],
  ...["left", "right"].flatMap((side) => {
    const word = side === "left" ? "왼쪽" : "오른쪽";
    return [[`${side}Shoulder`, `${word} 어깨`], [`${side}UpperArm`, `${word} 위팔`], [`${side}LowerArm`, `${word} 아래팔`], [`${side}Hand`, `${word} 손목`],
      [`${side}UpperLeg`, `${word} 허벅지`], [`${side}LowerLeg`, `${word} 종아리`], [`${side}Foot`, `${word} 발목`]];
  })];
const AXES = ["x", "y", "z"];
const degrees = (radian) => Math.round((radian * 180) / Math.PI);

//: 축 이름표. 팔 뼈는 옆으로 뻗은 자세가 기준이라 x가 비틀기, z가 위아래
const AXIS_NAMES = { body: ["앞뒤", "돌기", "옆으로"], arm: ["비틀기", "앞뒤", "위아래"] };

function showJoint() {
  const bone = $("joint-bone").value;
  const values = tweaks[bone] || [0, 0, 0];
  const names = AXIS_NAMES[/Shoulder|Arm|Hand/.test(bone) ? "arm" : "body"];
  AXES.forEach((axis, index) => {
    $(`joint-${axis}-name`).textContent = names[index];
    $(`joint-${axis}`).value = String(degrees(values[index]));
    $(`joint-${axis}-out`).textContent = `${degrees(values[index])}°`;
  });
}

$("joint-bone").replaceChildren(...JOINTS.map(([bone, name]) => new Option(name, bone)));
$("joint-bone").addEventListener("change", showJoint);
showJoint();
for (const axis of AXES) {
  $(`joint-${axis}`).addEventListener("input", () => {
    tweaks[$("joint-bone").value] = AXES.map((name) => (Number($(`joint-${name}`).value) * Math.PI) / 180);
    showJoint();
    redraw();
  });
}
$("joint-reset").addEventListener("click", () => { delete tweaks[$("joint-bone").value]; showJoint(); redraw(); });
$("joint-reset-all").addEventListener("click", () => { for (const bone of Object.keys(tweaks)) delete tweaks[bone]; showJoint(); redraw(); });

// ---------------------------------------------------------------- 자세 파일(VRMA, VPD)
//: VRM 사람 모양 뼈 전부(손가락 포함). VRMA에서 자세를 읽을 때
const ALL_BONES = ["hips", "spine", "chest", "upperChest", "neck", "head", ...["left", "right"].flatMap((side) => [
  `${side}Shoulder`, `${side}UpperArm`, `${side}LowerArm`, `${side}Hand`, `${side}UpperLeg`, `${side}LowerLeg`, `${side}Foot`, `${side}Toes`,
  ...["Thumb", "Index", "Middle", "Ring", "Little"].flatMap((finger) => (finger === "Thumb" ? ["Metacarpal", "Proximal", "Distal"] : ["Proximal", "Intermediate", "Distal"])
    .map((joint) => `${side}${finger}${joint}`))])];
let vrma = null;  // { source, duration }
let vpd = null;  // MMD 뼈 이름 -> THREE.Quaternion(오른손 좌표로 바꾼 것)

// VRMA의 t초 자세를 읽어 filePose로(모델에 동작을 잠깐 재생해 정규화 뼈 회전을 받음)
async function sampleVrma(seconds) {
  const { vrm, flip } = current;
  const animation = await import("/vendor/three-vrm-animation/three-vrm-animation.module.min.js");
  vrm.humanoid.resetNormalizedPose();
  const target = { humanoid: vrm.humanoid, meta: vrm.meta, expressionManager: vrm.expressionManager, scene: vrm.scene, lookAt: null };
  const mixer = new THREE.AnimationMixer(vrm.scene);
  const action = mixer.clipAction(animation.createVRMAnimationClip(vrma.source, target));
  action.setLoop(THREE.LoopOnce, 1);  // 끝 시점이 처음(0초)으로 돌아가지 않게
  action.clampWhenFinished = true;
  action.play();
  mixer.setTime(seconds);
  filePose = {};
  for (const bone of ALL_BONES) {
    const node = vrm.humanoid.getNormalizedBoneNode(bone);
    if (node) filePose[bone] = [node.quaternion.x * flip, node.quaternion.y, node.quaternion.z * flip, node.quaternion.w];
  }
  mixer.stopAllAction();
  mixer.uncacheRoot(vrm.scene);
  express({});
}

//: MMD 표준 뼈 이름 -> VRM 뼈(왼쪽만 적고 오른쪽은 右로 바꿔 씀). 손가락 숫자는 반각으로 바꿔 찾음
const MMD_SIDE = { "肩": "Shoulder", "腕": "UpperArm", "ひじ": "LowerArm", "手首": "Hand", "足": "UpperLeg", "ひざ": "LowerLeg", "足首": "Foot", "つま先": "Toes",
  "足D": "UpperLeg", "ひざD": "LowerLeg", "足首D": "Foot", "親指0": "ThumbMetacarpal", "親指1": "ThumbProximal", "親指2": "ThumbDistal",
  "人指1": "IndexProximal", "人指2": "IndexIntermediate", "人指3": "IndexDistal", "中指1": "MiddleProximal", "中指2": "MiddleIntermediate",
  "中指3": "MiddleDistal", "薬指1": "RingProximal", "薬指2": "RingIntermediate", "薬指3": "RingDistal", "小指1": "LittleProximal",
  "小指2": "LittleIntermediate", "小指3": "LittleDistal" };
const MMD_BODY = { "上半身2": "chest", "上半身3": "upperChest", "首": "neck", "頭": "head" };

// VPD 글(Shift_JIS를 푼 것) -> 뼈 이름별 회전. MMD는 왼손 좌표라 x, y 부호를 바꿔 three.js(오른손) 회전으로
function parseVpd(text) {
  const found = {};
  const pattern = /Bone\d+\s*\{\s*([^\r\n]+?)\s*[\r\n]+\s*[-\d.eE+]+\s*,\s*[-\d.eE+]+\s*,\s*[-\d.eE+]+\s*;[^\r\n]*[\r\n]+\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*;/g;
  for (const match of text.matchAll(pattern)) {
    const name = match[1].replace(/[０-９]/g, (digit) => String.fromCharCode(digit.charCodeAt(0) - 0xFEE0)).replace(/Ｄ/g, "D").trim();
    const [x, y, z, w] = match.slice(2, 6).map(Number);
    if ([x, y, z, w].every(Number.isFinite)) found[name] = new THREE.Quaternion(-x, -y, z, w).normalize();
  }
  return found;
}

// MMD 자세 -> VRM 자세. MMD 모델은 팔을 내린 자세가 기준이라 위팔은 그만큼 더 돌리고, 아래팔, 손, 손가락은 그 기준으로 바꿔 계산
function vpdPose(bones, armDegrees) {
  const pose = {};
  const get = (name) => bones[name] ? bones[name].clone() : new THREE.Quaternion();
  const set = (bone, quaternion) => { pose[bone] = [quaternion.x, quaternion.y, quaternion.z, quaternion.w]; };
  const lower = get("下半身");
  const hips = get("センター").multiply(get("グルーブ")).multiply(get("腰")).multiply(lower);
  set("hips", hips);
  set("spine", lower.clone().invert().multiply(get("上半身")));
  for (const [name, bone] of Object.entries(MMD_BODY)) if (bones[name]) set(bone, get(name));
  for (const [mark, side] of [["左", "left"], ["右", "right"]]) {
    const rest = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), ((side === "left" ? -1 : 1) * armDegrees * Math.PI) / 180);
    const back = rest.clone().invert();
    for (const [name, suffix] of Object.entries(MMD_SIDE)) {
      if (!bones[mark + name] || (name.endsWith("D") && bones[mark + name.slice(0, -1)])) continue;
      let rotation = get(mark + name);
      if (name === "腕") rotation.multiply(get(`${mark}腕捩`));
      if (name === "ひじ") rotation.multiply(get(`${mark}手捩`));
      const arm = ["UpperArm", "LowerArm", "Hand"].includes(suffix) || /^(Thumb|Index|Middle|Ring|Little)/.test(suffix);
      if (suffix === "UpperArm") rotation = rotation.multiply(rest);
      else if (arm) rotation = back.clone().multiply(rotation).multiply(rest);
      set(`${side}${suffix}`, rotation);
    }
  }
  return pose;
}

function fileState(text, error = false) {
  $("pose-file-state").textContent = text;
  $("pose-file-state").classList.toggle("error", error);
}

$("pose-file").addEventListener("change", async () => {
  const file = $("pose-file").files[0];
  if (!file || !current) return;
  vrma = null;
  vpd = null;
  try {
    if (/\.vpd$/i.test(file.name)) {
      const buffer = await file.arrayBuffer();
      let text;  // MMD가 저장한 VPD는 Shift_JIS, 다른 도구는 UTF-8도 있음
      try { text = new TextDecoder("utf-8", { fatal: true }).decode(buffer); } catch { text = new TextDecoder("shift_jis").decode(buffer); }
      if (!/Vocaloid Pose Data/.test(text)) throw new Error("VPD 파일이 아님");
      vpd = parseVpd(text);
      if (!Object.keys(vpd).length) throw new Error("VPD에서 뼈 회전을 찾지 못함");
      filePose = vpdPose(vpd, Number($("vpd-arm").value));
      fileState(`VPD 뼈 ${Object.keys(vpd).length}개를 적용함`);
    } else {
      const animation = await import("/vendor/three-vrm-animation/three-vrm-animation.module.min.js");
      const loader = new loaderClass();
      loader.register((parser) => new animation.VRMAnimationLoaderPlugin(parser));
      const url = URL.createObjectURL(file);
      try {
        const source = (await loader.loadAsync(url)).userData.vrmAnimations?.[0];
        if (!source) throw new Error("VRMA 동작을 읽지 못함");
        vrma = { source, duration: source.duration || 0 };
      } finally {
        URL.revokeObjectURL(url);
      }
      $("vrma-time").value = "0";
      await sampleVrma(0);
      fileState(`VRMA 동작(${vrma.duration.toFixed(1)}초)의 0초 자세를 적용함`);
    }
    $("vrma-time-row").hidden = !vrma;
    $("vpd-arm-row").hidden = !vpd;
    $("pose-file-off").disabled = false;
    $("pose").value = "custom";
    redraw();
  } catch (error) {
    fileState(`불러오지 못함: ${error.message}`, true);
  }
});
$("vrma-time").addEventListener("input", async () => {
  if (!vrma) return;
  const seconds = (Number($("vrma-time").value) / 1000) * vrma.duration;
  $("vrma-time-out").textContent = `${seconds.toFixed(1)}초`;
  await sampleVrma(seconds);
  fileState(`VRMA 동작(${vrma.duration.toFixed(1)}초)의 ${seconds.toFixed(1)}초 자세를 적용함`);
  redraw();
});
$("vpd-arm").addEventListener("input", () => {
  $("vpd-arm-out").textContent = `${$("vpd-arm").value}°`;
  if (!vpd) return;
  filePose = vpdPose(vpd, Number($("vpd-arm").value));
  redraw();
});
// 자세 파일 끄기(부위별 자세나 추천 자세를 고를 때도)
function dropFilePose() {
  if (!filePose) return;
  filePose = null;
  vrma = null;
  vpd = null;
  $("pose-file").value = "";
  $("vrma-time-row").hidden = true;
  $("vpd-arm-row").hidden = true;
  $("pose-file-off").disabled = true;
  fileState("부위별 자세로 돌아감");
}
$("pose-file-off").addEventListener("click", () => { dropFilePose(); syncParts(); redraw(); });

// ---------------------------------------------------------------- 내 자세 저장(이 PC 서버에 이름으로)
function poseNote(text, error = false) {
  $("my-pose-state").textContent = text;
  $("my-pose-state").classList.toggle("error", error);
}

async function loadMyPoses(select = "") {
  const data = await (await fetch("/character/poses")).json();
  $("my-poses").replaceChildren(...(data.poses || []).map((item) => new Option(item.name, item.name)));
  if (select) $("my-poses").value = select;
  return data.poses || [];
}

$("my-pose-save").addEventListener("click", async () => {
  const name = $("my-pose-name").value.trim();
  if (!name) return poseNote("자세 이름을 입력", true);
  const round = (values) => values.map((value) => Math.round(value * 1e5) / 1e5);
  const file = filePose && Object.fromEntries(Object.entries(filePose).map(([bone, values]) => [bone, round(values)]));
  const body = { name, parts: { ...poseState }, tweaks: { ...tweaks }, file };
  const response = await fetch("/character/poses", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) return poseNote(data.error || "저장하지 못함", true);
  await loadMyPoses(name);
  poseNote(`저장함: ${name}`);
});
$("my-pose-load").addEventListener("click", async () => {
  const poses = await loadMyPoses($("my-poses").value);
  const found = poses.find((item) => item.name === $("my-poses").value);
  if (!found) return poseNote("저장한 자세를 고름", true);
  Object.assign(poseState, found.parts || {});
  for (const bone of Object.keys(tweaks)) delete tweaks[bone];
  Object.assign(tweaks, found.tweaks || {});
  dropFilePose();
  filePose = found.file || null;
  $("pose-file-off").disabled = !filePose;
  syncParts();
  if (filePose) {
    $("pose").value = "custom";
    fileState(`저장한 자세 ${found.name}의 파일 자세를 적용함`);
  }
  showJoint();
  redraw();
  poseNote(`불러옴: ${found.name}`);
});
$("my-pose-remove").addEventListener("click", async () => {
  const name = $("my-poses").value;
  if (!name) return;
  const response = await fetch("/character/poses/remove", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
  if (!response.ok) return poseNote("지우지 못함", true);
  await loadMyPoses();
  poseNote(`지움: ${name}`);
});
loadMyPoses().catch(() => {});

// ---------------------------------------------------------------- VMC로 자세 보내기(서버가 Unity 좌표로 바꿔 초당 30번 보냄)
let vmcOn = false;
let vmcKeep = 0;

function vmcNote(text, error = false) {
  $("vmc-state").textContent = text;
  $("vmc-state").classList.toggle("error", error);
}

// 지금 자세의 정규화 뼈: [회전 x, y, z, w, 위치 x, y, z](VRM 1.0 방향, VRM 0.x는 x, z 부호를 바꿈)
function vmcBones() {
  applyPose();
  const { vrm, flip } = current;
  const bones = {};
  for (const bone of ALL_BONES) {
    const node = vrm.humanoid.getNormalizedBoneNode(bone);
    if (!node) continue;
    const { quaternion: q, position: p } = node;
    bones[bone] = [q.x * flip, q.y, q.z * flip, q.w, p.x * flip, p.y, p.z * flip].map((value) => Math.round(value * 1e5) / 1e5);
  }
  return bones;
}

function vmcStop(note = "멈춤") {
  vmcOn = false;
  clearInterval(vmcKeep);
  $("vmc-send").textContent = "보내기 시작";
  vmcNote(note);
}

async function vmcSend() {
  if (!vmcOn || !current) return;
  const body = { host: $("vmc-host").value.trim(), port: Number($("vmc-port").value), bones: vmcBones(),
    expression: $("vmc-face").checked ? $("pose-face").value : null };
  try {
    const response = await fetch("/vmc/pose", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "보내지 못함");
    if (!vmcOn) return;  // 기다리는 사이 멈춤을 누름
    vmcNote(`보내는 중: ${data.host}:${data.port}, 뼈 ${data.bones}개${data.face ? "(머리와 표정은 얼굴 추적 VMC 송신 값)" : ""}${data.error ? `, ${data.error}` : ""}`);
  } catch (error) {
    vmcStop(error.message);
    $("vmc-state").classList.add("error");
  }
}

$("vmc-send").addEventListener("click", () => {
  if (vmcOn) {
    vmcStop();
    fetch("/vmc/pose/stop", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
    return;
  }
  if (!current) return vmcNote("먼저 캐릭터를 그림", true);
  vmcOn = true;
  $("vmc-send").textContent = "보내기 멈춤";
  vmcKeep = setInterval(vmcSend, 5000);  // 자세가 그대로여도 계속 보내라고 알림(화면을 닫으면 20초 안에 서버가 멈춤)
  vmcSend();
});
$("vmc-face").addEventListener("change", vmcSend);
window.addEventListener("pagehide", () => {
  if (vmcOn) fetch("/vmc/pose/stop", { method: "POST", keepalive: true, headers: { "Content-Type": "application/json" }, body: "{}" });
});
fetch("/vmc/status").then((response) => response.json()).then((data) => {  // 얼굴 추적 송신에 저장한 받는 곳을 기본값으로
  const pose = data.pose || {};
  if (pose.host) $("vmc-host").value = pose.host;
  if (pose.port) $("vmc-port").value = String(pose.port);
}).catch(() => {});

// 문서 그림용(packaging/build_screens.py, build_promo.py가 헤드리스 브라우저로 부름): 추천 자세, 각도(0, 0.3, 0.62),
// 표정(VRM 표정 이름, 눈 감음 blink 포함)을 정해 그림을 PNG 주소로
window.debutkitSheet = {
  ready: () => Boolean(current) && $("state").textContent === "그림 완료",
  pose(preset, angle = 0, face = "neutral", width = 600, height = 900, background = false) {
    dropFilePose();
    Object.assign(poseState, PRESETS[preset].parts);
    syncParts();
    $("pose-angle").value = String(angle);
    applyPose();
    return renderPose(width, height, background, face).toDataURL("image/png");
  },
  sheet(preset) {
    dropFilePose();
    Object.assign(poseState, PRESETS[preset].parts);
    syncParts();
    applyPose();
    drawSheet(current.name);
    return $("sheet").toDataURL("image/png");
  },
};
$("pose").addEventListener("change", () => {
  const preset = PRESETS[$("pose").value];
  if (!preset) return;
  dropFilePose();
  Object.assign(poseState, preset.parts);
  syncParts();
  redraw();
});
$("random").addEventListener("click", () => {  // 잠그지 않은 부위만 무작위로
  dropFilePose();
  for (const [part, item] of Object.entries(PARTS)) {
    if (locks[part]) continue;
    const keys = Object.keys(item.options);
    poseState[part] = keys[Math.floor(Math.random() * keys.length)];
  }
  syncParts();
  redraw();
});
for (const id of ["pose-face", "pose-angle", "pose-bg"]) $(id).addEventListener("change", () => redraw(false));
$("save-pose").addEventListener("click", () => {  // 1024x1536 PNG(무대 배경을 끄면 투명)
  const link = document.createElement("a");
  link.href = renderPose(1024, 1536, $("pose-bg").checked).toDataURL("image/png");
  link.download = "pose.png";
  link.click();
  drawPose();
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
