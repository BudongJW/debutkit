// debutkit 캐릭터 화면: OBS 브라우저 소스용. PNGTuber와 VRM을 목소리 크기(/voice)와 얼굴 추적 값(/tracking)에 맞춰 움직인다.
// ?id=캐릭터 로 지정하지 않으면 방송에 사용할 캐릭터를 표시하고, 바뀌면 다시 불러온다. ?demo 는 말하기 시험 표시.
// 얼굴 추적 값은 별도 브라우저 창의 추적 화면(/tracker)이 보낸다. 0.6초 넘게 오지 않으면 기본 움직임으로 돌아간다.

const params = new URLSearchParams(location.search);
const explicit = params.get("id") || "";
const demo = params.has("demo");
const stage = document.getElementById("stage");
const notice = document.getElementById("notice");
const voice = { talking: false, level: 0 };
const tracked = { found: false, time: 0 };
let currentId = "";

function tracking() {  // 최근 추적 값이 있으면 그 값, 없으면 null
  return tracked.found && Date.now() / 1000 - tracked.time < 0.6 ? tracked : null;
}

function listenTracking() {
  const source = new EventSource("/tracking");
  source.onmessage = (message) => Object.assign(tracked, { found: false }, JSON.parse(message.data));
}

function show(text) {
  notice.textContent = text;
  notice.hidden = !text;
}

function listenVoice() {
  if (demo) {  // 말하기 시험: 0.6초 말하고 0.6초 쉼
    setInterval(() => {
      voice.talking = !voice.talking;
      voice.level = voice.talking ? 0.75 : 0;
    }, 600);
    return;
  }
  const source = new EventSource("/voice");
  source.onmessage = (message) => Object.assign(voice, JSON.parse(message.data));
}

function scheduleBlink(blink) {
  setTimeout(() => {
    blink();
    scheduleBlink(blink);
  }, 2500 + Math.random() * 3500);
}

function startPng(info) {
  const box = document.createElement("div");
  box.className = "png";
  const images = {};
  for (const [state, url] of Object.entries(info.files)) {
    const image = new Image();
    image.src = url;
    image.alt = info.name;
    image.hidden = state !== "idle";
    box.appendChild(image);
    images[state] = image;
  }
  stage.appendChild(box);
  let blinking = false;
  scheduleBlink(() => {
    blinking = true;
    setTimeout(() => (blinking = false), 140);
  });
  let shown = "idle";
  const frame = () => {
    const face = tracking();
    const talking = voice.talking || Boolean(face && face.mouth > 0.35);
    const closed = face ? (face.blinkLeft + face.blinkRight) / 2 > 0.55 : blinking;
    let state = talking ? "talk" : "idle";
    if (closed && images[talking ? "talk_blink" : "blink"]) state = talking ? "talk_blink" : "blink";
    if (state !== shown) {
      images[shown].hidden = true;
      images[state].hidden = false;
      shown = state;
    }
    box.classList.toggle("talking", talking);
    requestAnimationFrame(frame);
  };
  frame();
}

async function startVrm(info) {
  const THREE = await import("three");
  const { GLTFLoader } = await import("three/addons/loaders/GLTFLoader.js");
  const { VRMLoaderPlugin, VRMUtils } = await import("/vendor/three-vrm/three-vrm.module.min.js");

  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  stage.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, window.innerWidth / window.innerHeight, 0.1, 20);
  const light = new THREE.DirectionalLight(0xffffff, Math.PI);
  light.position.set(1, 1, 1).normalize();
  scene.add(light, new THREE.AmbientLight(0xffffff, 0.4));

  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));
  const gltf = await loader.loadAsync(info.files.model);
  const vrm = gltf.userData.vrm;
  if (!vrm) throw new Error("VRM 정보를 읽지 못함");
  VRMUtils.removeUnnecessaryVertices(gltf.scene);
  if (VRMUtils.combineSkeletons) VRMUtils.combineSkeletons(gltf.scene);
  VRMUtils.rotateVRM0(vrm);  // VRM 0.x는 반대 방향을 보므로 1.0과 같은 방향으로
  scene.add(vrm.scene);

  // 상반신이 보이도록 머리 위치에 맞춰 카메라 배치
  vrm.scene.updateMatrixWorld(true);
  const bone = (name) => vrm.humanoid?.getNormalizedBoneNode(name);
  const headPosition = new THREE.Vector3();
  (bone("head") || vrm.scene).getWorldPosition(headPosition);
  const fit = () => {
    renderer.setSize(window.innerWidth, window.innerHeight);
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.position.set(0, headPosition.y - 0.1, 1.7);  // 머리 위 여유부터 허리까지(세로 약 0.9 m)
    camera.lookAt(0, headPosition.y - 0.15, 0);
    camera.updateProjectionMatrix();
  };
  fit();
  window.addEventListener("resize", fit);
  if (vrm.lookAt) vrm.lookAt.target = camera;

  // T자 자세에서 팔 내리기(VRM 0.x 정규화 뼈대는 x, z 회전 방향이 반대)
  const flip = vrm.meta?.metaVersion === "0" ? -1 : 1;
  const leftArm = bone("leftUpperArm");
  const rightArm = bone("rightUpperArm");
  if (leftArm) leftArm.rotation.z = -1.2 * flip;
  if (rightArm) rightArm.rotation.z = 1.2 * flip;

  const timer = new THREE.Timer();
  let blink = 0;
  let blinkStart = -1;
  scheduleBlink(() => (blinkStart = timer.getElapsed()));
  let mouth = 0;
  const spine = bone("spine");
  const neck = bone("neck");
  const head = bone("head");
  const pose = { yaw: 0, pitch: 0, roll: 0, blinkLeft: 0, blinkRight: 0, mouth: 0, smile: 0 };  // 추적 값(부드럽게 따라감)
  const animate = (timestamp) => {
    timer.update(timestamp);
    const delta = Math.min(timer.getDelta(), 0.1);
    const t = timer.getElapsed();
    const face = tracking();
    const follow = Math.min(1, delta * 14);
    for (const name of Object.keys(pose)) pose[name] += ((face ? face[name] || 0 : 0) - pose[name]) * follow;
    const target = voice.talking ? Math.min(1, 0.35 + voice.level * 0.8) : 0;
    mouth += (Math.max(target, pose.mouth * 1.1) - mouth) * Math.min(1, delta * 18);
    if (blinkStart >= 0) {
      const phase = (t - blinkStart) / 0.16;
      blink = phase < 1 ? Math.sin(phase * Math.PI) : 0;
      if (phase >= 1) blinkStart = -1;
    }
    const expressions = vrm.expressionManager;
    if (expressions) {
      expressions.setValue("aa", Math.min(1, mouth));
      if (face) {  // 추적 중: 양쪽 눈 따로, 웃음
        expressions.setValue("blink", 0);
        expressions.setValue("blinkLeft", pose.blinkLeft);
        expressions.setValue("blinkRight", pose.blinkRight);
        expressions.setValue("happy", Math.min(1, pose.smile * 0.8));
      } else {
        expressions.setValue("blink", Math.max(blink, (pose.blinkLeft + pose.blinkRight) / 2));
        expressions.setValue("blinkLeft", 0);
        expressions.setValue("blinkRight", 0);
        expressions.setValue("happy", pose.smile * 0.8);
      }
    }
    if (spine) spine.rotation.x = Math.sin(t * 1.6) * 0.015 * flip;  // 호흡
    const idle = face ? 0 : 1;  // 추적이 없을 때만 기본 흔들림
    if (neck) {  // 머리 회전은 목 40%, 머리 60%로 나눔(VRM 0.x는 x, z 방향 반대)
      neck.rotation.y = pose.yaw * 0.4 + Math.sin(t * 0.5) * 0.06 * idle;
      neck.rotation.x = pose.pitch * 0.4 * flip;
      neck.rotation.z = (pose.roll * 0.4 + Math.sin(t * 0.7) * 0.02 * idle) * flip + (voice.talking ? Math.sin(t * 9) * 0.01 * idle : 0);
    }
    if (head) {
      head.rotation.y = pose.yaw * 0.6;
      head.rotation.x = pose.pitch * 0.6 * flip;
      head.rotation.z = pose.roll * 0.6 * flip;
    }
    vrm.update(delta);
    renderer.render(scene, camera);
    requestAnimationFrame(animate);
  };
  requestAnimationFrame(animate);
}

async function info() {
  const response = await fetch("/character/info" + (explicit ? `?id=${encodeURIComponent(explicit)}` : ""), { cache: "no-store" });
  if (!response.ok) throw new Error("캐릭터 정보를 받지 못함");
  return response.json();
}

async function main() {
  listenVoice();
  listenTracking();
  const found = await info();
  currentId = found.id;
  if (!found.renders) {
    const app = found.kind === "live2d" ? "VTube Studio" : "Inochi Session";
    show(`${found.name}: ${app}에서 표시하는 캐릭터입니다. OBS에서 ${app} 창 캡처를 사용하십시오.`);
  } else if (found.kind === "png") {
    startPng(found);
  } else {
    await startVrm(found);
  }
  if (!explicit) {  // 설정 마법사나 명령줄에서 캐릭터를 바꾸면 다시 불러오기
    setInterval(async () => {
      try {
        if ((await info()).id !== currentId) location.reload();
      } catch (error) {
        // 오버레이를 다시 시작하는 중
      }
    }, 5000);
  }
}

main().catch((error) => show(`캐릭터를 표시하지 못함: ${error.message}`));
