// debutkit 얼굴 추적: 웹캠 영상에서 MediaPipe Face Landmarker로 머리 회전과 표정을 계산해 /tracking 으로 보낸다.
// 영상은 이 창 안에서만 처리하고 숫자 값만 이 PC의 debutkit 서버로 보낸다. 콘텐츠 보안 정책으로 외부 접속은 차단된다.

import { FaceLandmarker, FilesetResolver } from "/vendor/mediapipe/vision_bundle.mjs";

const $ = (id) => document.getElementById(id);
const video = $("video");
const statusLine = $("status");
const SEND_INTERVAL = 50;  // 초당 20회
let landmarker = null;
let stream = null;
let running = false;
let generation = 0;  // 다시 시작할 때마다 증가: 이전 반복을 멈춘다
let lastSent = 0;
let lastTime = 0;
let frames = 0;
let fpsSince = performance.now();

function setStatus(text) {
  statusLine.textContent = text;
}

// 4x4 열 우선 행렬에서 머리 회전(라디안). MediaPipe 얼굴 좌표: x는 얼굴의 왼쪽, y 위, z 카메라 쪽(VRM과 같은 방향)
// 회전 순서 Y(좌우), X(위아래), Z(기울기): R = Ry Rx Rz 에서 r02 = sin(yaw)cos(pitch), r12 = -sin(pitch), r10 = cos(pitch)sin(roll), r11 = cos(pitch)cos(roll)
export function headRotation(m) {
  const r = (row, col) => m[col * 4 + row];
  return {
    yaw: Math.atan2(r(0, 2), r(2, 2)),
    pitch: Math.asin(Math.max(-1, Math.min(1, -r(1, 2)))),
    roll: Math.atan2(r(1, 0), r(1, 1)),
  };
}

// 왼쪽과 오른쪽 표정 이름 바꾸기(거울처럼)
const swapSide = (name) => name.endsWith("Left") ? name.slice(0, -4) + "Right" : name.endsWith("Right") ? name.slice(0, -5) + "Left" : name;

// 인식 결과를 캐릭터 값으로. 거울처럼: 좌우 회전과 기울기를 반대로, 왼눈과 오른눈을 바꿈
// arkit: MediaPipe 표정 51개(ARKit 이름, tongueOut 없음). 같은 이름의 표정이 있는 모델(퍼펙트 싱크)은 얼굴 전체가 움직인다
export function toValues(result, mirror) {
  if (!result || !result.faceBlendshapes || !result.faceBlendshapes.length) return { found: false };
  const shapes = {};
  for (const category of result.faceBlendshapes[0].categories) shapes[category.categoryName] = category.score;
  const matrix = result.facialTransformationMatrixes && result.facialTransformationMatrixes[0];
  const head = matrix ? headRotation(matrix.data) : { yaw: 0, pitch: 0, roll: 0 };
  const side = mirror ? -1 : 1;
  const arkit = {};
  for (const [name, score] of Object.entries(shapes)) {
    if (!name.startsWith("_")) arkit[mirror ? swapSide(name) : name] = Math.round(score * 1000) / 1000;
  }
  return {
    arkit,
    found: true,
    yaw: head.yaw * side,
    pitch: head.pitch,
    roll: head.roll * side,
    blinkLeft: (mirror ? shapes.eyeBlinkRight : shapes.eyeBlinkLeft) || 0,
    blinkRight: (mirror ? shapes.eyeBlinkLeft : shapes.eyeBlinkRight) || 0,
    mouth: shapes.jawOpen || 0,
    smile: ((shapes.mouthSmileLeft || 0) + (shapes.mouthSmileRight || 0)) / 2,
  };
}

function show(values) {
  for (const name of ["yaw", "pitch", "roll", "blinkLeft", "blinkRight", "mouth", "smile"]) {
    const cell = $(`v-${name}`);
    if (cell) cell.textContent = values.found ? values[name].toFixed(2) : "-";
  }
}

async function send(values) {
  try {
    await fetch("/tracking", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) });
  } catch (error) {
    setStatus("debutkit 서버에 연결하지 못함: 오버레이 실행 여부 확인");
  }
}

export async function createLandmarker() {
  const fileset = await FilesetResolver.forVisionTasks("/vendor/mediapipe/wasm");
  const options = (delegate) => ({
    baseOptions: { modelAssetPath: "/vendor/mediapipe/face_landmarker.task", delegate },
    runningMode: "VIDEO",
    numFaces: 1,
    outputFaceBlendshapes: true,
    outputFacialTransformationMatrixes: true,
  });
  try {
    return await FaceLandmarker.createFromOptions(fileset, options("GPU"));
  } catch (error) {
    return FaceLandmarker.createFromOptions(fileset, options("CPU"));  // 그래픽 가속을 쓸 수 없는 환경
  }
}

async function listCameras() {
  const select = $("camera");
  const current = select.value;
  const devices = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === "videoinput");
  select.replaceChildren(new Option("기본 카메라", ""), ...devices.map((device, index) => new Option(device.label || `카메라 ${index + 1}`, device.deviceId)));
  select.value = current;
}

function loop(mine) {
  if (!running || mine !== generation) return;
  const now = performance.now();
  if (video.readyState >= 2 && now > lastTime) {  // MediaPipe는 같은 시각의 영상을 두 번 받지 않음
    lastTime = now;
    const values = toValues(landmarker.detectForVideo(video, now), $("mirror").checked);
    frames += 1;
    if (now - fpsSince >= 1000) {
      $("v-fps").textContent = String(frames);
      frames = 0;
      fpsSince = now;
    }
    show(values);
    setStatus(values.found ? "추적 중" : "얼굴을 찾지 못함: 카메라 정면을 보십시오");
    if (now - lastSent >= SEND_INTERVAL) {
      lastSent = now;
      send(values);
    }
  }
  const next = () => loop(mine);
  video.requestVideoFrameCallback ? video.requestVideoFrameCallback(next) : requestAnimationFrame(next);
}

async function start() {
  const mine = ++generation;
  running = false;
  $("start").disabled = true;
  try {
    if (!landmarker) {
      setStatus("얼굴 추적 모델 불러오는 중");
      landmarker = await createLandmarker();
    }
    if (stream) stream.getTracks().forEach((track) => track.stop());
    const deviceId = $("camera").value;
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, ...(deviceId ? { deviceId: { exact: deviceId } } : {}) }, audio: false });
    video.srcObject = stream;
    await video.play();
    await listCameras();
    if (mine !== generation) return;
    running = true;
    $("start").textContent = "다시 시작";
    loop(mine);
  } catch (error) {
    running = false;
    const denied = error && (error.name === "NotAllowedError" || error.name === "SecurityError");
    const missing = error && error.name === "NotFoundError";
    setStatus(denied ? "카메라 사용이 허용되지 않음: 주소 표시줄의 카메라 권한 확인" : missing ? "카메라를 찾지 못함" : `추적 시작 실패: ${error.message || error}`);
    send({ found: false });
  } finally {
    $("start").disabled = false;
  }
}

$("start").addEventListener("click", start);
$("camera").addEventListener("change", () => running && start());
$("mirror").addEventListener("change", () => video.classList.toggle("mirror", $("mirror").checked));
window.addEventListener("pagehide", () => navigator.sendBeacon && navigator.sendBeacon("/tracking", new Blob([JSON.stringify({ found: false })], { type: "application/json" })));
window.debutkitTracker = { toValues, headRotation, createLandmarker };  // 시험용
