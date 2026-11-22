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
let lastSent = 0;
let frames = 0;
let fpsSince = performance.now();

function setStatus(text) {
  statusLine.textContent = text;
}

// 4x4 열 우선 행렬에서 머리 회전(라디안). MediaPipe 얼굴 좌표: x는 얼굴의 왼쪽, y 위, z 카메라 쪽(VRM과 같은 방향)
export function headRotation(m) {
  const r = (row, col) => m[col * 4 + row];
  return {
    yaw: Math.atan2(r(0, 2), r(2, 2)),
    pitch: Math.asin(Math.max(-1, Math.min(1, -r(1, 2)))),
    roll: Math.atan2(r(1, 0), r(0, 0)),
  };
}

// 인식 결과를 캐릭터 값으로. 거울처럼: 좌우 회전과 기울기를 반대로, 왼눈과 오른눈을 바꿈
export function toValues(result, mirror) {
  if (!result || !result.faceBlendshapes || !result.faceBlendshapes.length) return { found: false };
  const shapes = {};
  for (const category of result.faceBlendshapes[0].categories) shapes[category.categoryName] = category.score;
  const matrix = result.facialTransformationMatrixes && result.facialTransformationMatrixes[0];
  const head = matrix ? headRotation(matrix.data) : { yaw: 0, pitch: 0, roll: 0 };
  const side = mirror ? -1 : 1;
  return {
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

function loop() {
  if (!running) return;
  if (video.readyState >= 2) {
    const now = performance.now();
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
  video.requestVideoFrameCallback ? video.requestVideoFrameCallback(loop) : requestAnimationFrame(loop);
}

async function start() {
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
    running = true;
    $("start").textContent = "다시 시작";
    loop();
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
