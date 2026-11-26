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
  // A 자세: 팔을 내림(T 자세 그대로면 시트가 넓어지고 어색함)
  const bend = (name, z) => {
    const node = vrm.humanoid && vrm.humanoid.getNormalizedBoneNode(name);
    if (node) node.rotation.z = z;
  };
  bend("leftUpperArm", -1.2);
  bend("rightUpperArm", 1.2);
  bend("leftLowerArm", -0.12);
  bend("rightLowerArm", 0.12);
  if (vrm.lookAt) vrm.lookAt.target = camera;
  current = { vrm, id };
  express({});
  return info;
}

function express(values) {
  const { vrm } = current;
  const manager = vrm.expressionManager;
  if (manager) {
    for (const expression of manager.expressions) manager.setValue(expression.expressionName, 0);
    for (const [name, value] of Object.entries(values)) if (manager.getExpression(name)) manager.setValue(name, value);
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

function shot(width, height) {
  renderer.setSize(width, height, false);
  renderer.render(scene, camera);
  return renderer.domElement;
}

function bodyBox() {
  const box = new THREE.Box3().setFromObject(current.vrm.scene);
  return { center: box.getCenter(new THREE.Vector3()), height: box.max.y - box.min.y };
}

function headFrame(span) {
  const head = bone("head") || bodyBox().center;
  return new THREE.Vector3(head.x, head.y + span * 0.12, head.z);
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
  ctx.fillStyle = "#1d1f23";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  express({});
  const body = bodyBox();
  for (const [index, [title, yaw]] of [["정면", 0], ["3/4", 0.62]].entries()) {
    frame(body.center, body.height * 1.08, yaw, 520, 880);
    ctx.drawImage(shot(520, 880), index * 520, 20, 520, 880);
    label(ctx, title, index * 520 + 10, 44);
  }
  frame(headFrame(0.36), 0.36, 0, 560, 420);
  ctx.fillStyle = "#24272c";
  ctx.fillRect(1040, 0, 560, 420);
  ctx.drawImage(shot(560, 420), 1040, 0);
  label(ctx, "얼굴", 1050, 10);
  EXPRESSIONS.forEach(([expression, title], index) => {
    express({ [expression]: 1 });
    const x = 1040 + (index % 4) * 140;
    const y = 420 + Math.floor(index / 4) * 240;
    frame(headFrame(0.5), 0.5, 0, 140, 240);
    ctx.fillStyle = index % 2 ? "#26292e" : "#2a2d33";
    ctx.fillRect(x, y, 140, 240);
    ctx.drawImage(shot(140, 240), x, y);
    label(ctx, title, x + 6, y + 8);
  });
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
    frame(headFrame(0.72).add(new THREE.Vector3(0, -0.2, 0)), 0.72, 0, PNG_SIZE, PNG_SIZE);  // 가슴 위, 머리 위 여백
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
  if (!list.length) {
    note("등록한 VRM이 없음", true);
    if (window.debutkitUi) $("empty").replaceChildren(window.debutkitUi.mascot("dessaengi", "아직 VRM 캐릭터가 없음. 설정 마법사의 캐릭터 단계에서 VRM을 추가하거나 VRoid Studio로 만들기"));
  }
  else if (wanted) draw();
});
