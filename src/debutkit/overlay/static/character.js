// debutkit 캐릭터 화면: OBS 브라우저 소스용. PNGTuber, VRM, 일반 3D 모델(GLB, FBX)을 목소리 크기와 얼굴 추적 값(/live 연결 하나로 받음)에 맞춰 움직인다.
// GLB, FBX는 뼈와 표정 이름 표(/character/humanoid.json, 파이썬 humanoid.py와 같은 표)로 VRM 사람 모양 뼈와 표정을 만들어 VRM과 같은 방식으로 움직인다.
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


function show(text) {
  notice.textContent = text;
  notice.hidden = !text;
}

function listen() {
  // 브라우저의 같은 주소 동시 연결 수 제한(6개, OBS 브라우저 소스끼리 공유) 때문에 연결 하나로 받는다
  const source = new EventSource("/live");
  source.addEventListener("tracking", (message) => Object.assign(tracked, { found: false }, JSON.parse(message.data)));
  if (demo) {  // 말하기 시험: 0.6초 말하고 0.6초 쉼
    setInterval(() => {
      voice.talking = !voice.talking;
      voice.level = voice.talking ? 0.75 : 0;
    }, 600);
    return;
  }
  source.addEventListener("voice", (message) => Object.assign(voice, JSON.parse(message.data)));
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

// 이름 비교 규칙: 파이썬 humanoid.normalize, bone_key, morph_keys와 같아야 함
const normalize = (name) => name.replace(/[\s_\-.:\/\[\]\\|]+/g, "").toLowerCase();
const boneKey = (name) => normalize(name).replace(/^mixamorig\d*/, "");
const morphKeys = (name) => [...new Set([normalize(name), normalize(name.split(/[.|:]/).pop())])];

export function matchBones(names, table) {  // VRM 뼈 이름 -> 모델 뼈 이름(먼저 나온 뼈)
  const found = {};
  for (const name of names) {
    const bone = table.bones[boneKey(name)];
    if (bone && !found[bone]) found[bone] = name;
  }
  return found;
}

export function matchExpressions(names, table) {  // VRM 표정 이름 -> {형태 변형 이름: 가중치}. 없으면 ARKit 조합으로 대체
  const found = {};
  for (const name of names) {
    for (const key of morphKeys(name)) {
      const expression = table.expressions[key];
      if (expression && !found[expression]) {
        found[expression] = { [name]: 1 };
        break;
      }
    }
  }
  const arkit = {};
  for (const name of names) {
    arkit[normalize(name)] = name;
    for (const key of morphKeys(name)) arkit[key] = name;
  }
  for (const [expression, parts] of Object.entries(table.arkit)) {
    const keys = Object.keys(parts);
    if (found[expression] || !(normalize(keys[0]) in arkit)) continue;
    found[expression] = Object.fromEntries(keys.filter((part) => normalize(part) in arkit).map((part) => [arkit[normalize(part)], parts[part]]));
  }
  return found;
}

async function loadVrm(THREE, lib, info) {
  const { GLTFLoader } = await import("three/addons/loaders/GLTFLoader.js");
  const loader = new GLTFLoader();
  loader.register((parser) => new lib.VRMLoaderPlugin(parser));
  const gltf = await loader.loadAsync(info.files.model);
  const vrm = gltf.userData.vrm;
  if (!vrm) throw new Error("VRM 정보를 읽지 못함");
  lib.VRMUtils.removeUnnecessaryVertices(gltf.scene);
  if (lib.VRMUtils.combineSkeletons) lib.VRMUtils.combineSkeletons(gltf.scene);
  lib.VRMUtils.rotateVRM0(vrm);  // VRM 0.x는 반대 방향을 보므로 1.0과 같은 방향으로
  return vrm;
}

async function loadModel(THREE, lib, info) {
  const table = await (await fetch("/character/humanoid.json", { cache: "no-store" })).json();
  let root;
  if (/\.fbx$/i.test(info.files.model)) {
    const { FBXLoader } = await import("three/addons/loaders/FBXLoader.js");
    root = await new FBXLoader().loadAsync(info.files.model);
  } else {
    const { GLTFLoader } = await import("three/addons/loaders/GLTFLoader.js");
    root = (await new GLTFLoader().loadAsync(info.files.model)).scene;
  }
  const nodes = {};
  const meshes = [];
  root.traverse((node) => {
    if (node.isBone && !(node.name in nodes)) nodes[node.name] = node;
    if (node.isMesh) {
      node.frustumCulled = false;  // 움직인 뼈 때문에 화면 밖으로 잘못 판단되지 않도록
      if (node.morphTargetDictionary) meshes.push(node);
    }
  });
  const found = matchBones(Object.keys(nodes), table);
  const missing = table.required.filter((bone) => !found[bone]);
  if (missing.length) throw new Error(`사람 모양 뼈를 찾지 못함(${missing.join(", ")})`);

  // 미터 단위, 정면(+Z), 가운데로 맞춤. 사람 모양 뼈는 맞춘 뒤의 자세를 기준으로 만든다(VRM 1.0과 같은 회전 방향)
  const model = new THREE.Group();
  model.add(root);
  model.updateMatrixWorld(true);
  const at = (bone) => nodes[found[bone]].getWorldPosition(new THREE.Vector3());
  const footY = Math.min(at("leftFoot").y, at("rightFoot").y);
  const height = at("head").y - footY;
  const scale = height > 0.5 && height < 3 ? 1 : 1.45 / Math.max(height, 1e-6);  // 센티미터 단위 FBX 등
  model.scale.setScalar(scale);
  if (at("leftUpperArm").x < at("rightUpperArm").x) model.rotation.y = Math.PI;  // 뒤를 보는 모델
  model.updateMatrixWorld(true);
  const hips = at("hips");
  model.position.set(-hips.x, -Math.min(at("leftFoot").y, at("rightFoot").y), -hips.z);
  const scene = new THREE.Group();
  scene.add(model);
  scene.updateMatrixWorld(true);

  const humanBones = Object.fromEntries(Object.entries(found).map(([bone, name]) => [bone, { node: nodes[name] }]));
  const humanoid = new lib.VRMHumanoid(humanBones, { autoUpdateHumanBones: true });
  scene.add(humanoid.normalizedHumanBonesRoot);
  const expressionManager = new lib.VRMExpressionManager();
  const names = [...new Set(meshes.flatMap((mesh) => Object.keys(mesh.morphTargetDictionary)))];
  for (const [name, parts] of Object.entries(matchExpressions(names, table))) {
    const expression = new lib.VRMExpression(name);
    for (const [morph, weight] of Object.entries(parts)) {
      for (const mesh of meshes) {
        const index = mesh.morphTargetDictionary[morph];
        if (index !== undefined) expression.addBind(new lib.VRMExpressionMorphTargetBind({ primitives: [mesh], index, weight }));
      }
    }
    expressionManager.registerExpression(expression);
    scene.add(expression);
  }
  const meta = { metaVersion: "1", name: info.name, authors: [], licenseUrl: "" };
  return new lib.VRMCore({ scene, meta, humanoid, expressionManager });
}

async function start3d(info) {
  const THREE = await import("three");
  const lib = await import("/vendor/three-vrm/three-vrm.module.min.js");

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

  const vrm = info.kind === "vrm" ? await loadVrm(THREE, lib, info) : await loadModel(THREE, lib, info);
  scene.add(vrm.scene);
  window.debutkitCharacter = { vrm, THREE };  // 시험용

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

  // 팔 내리기: 기준 자세의 팔 각도(T자 0, A자 등은 이미 내려간 만큼)를 빼고 약 69도까지(VRM 0.x 정규화 뼈대는 x, z 회전 방향이 반대)
  const flip = vrm.meta?.metaVersion === "0" ? -1 : 1;
  const lowered = (side) => {
    const upper = bone(`${side}UpperArm`);
    const lower = bone(`${side}LowerArm`);
    if (!upper || !lower) return 0;
    const from = upper.getWorldPosition(new THREE.Vector3());
    const to = lower.getWorldPosition(new THREE.Vector3());
    return Math.max(0, 1.2 - Math.atan2(from.y - to.y, Math.abs(to.x - from.x)));
  };
  const leftArm = bone("leftUpperArm");
  const rightArm = bone("rightUpperArm");
  if (leftArm) leftArm.rotation.z = -lowered("left") * flip;
  if (rightArm) rightArm.rotation.z = lowered("right") * flip;
  const jaw = vrm.expressionManager?.getExpression("aa") ? null : bone("jaw");  // 입 모양 표정이 없으면 턱 뼈로

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
    if (jaw) jaw.rotation.x = Math.min(1, mouth) * 0.3 * flip;
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

function watchCharacter() {  // 설정 마법사나 명령줄에서 캐릭터를 바꾸면 다시 불러오기(표시에 실패한 경우도 포함)
  setInterval(async () => {
    try {
      const found = await info();
      if (currentId && found.id !== currentId) location.reload();
      if (!currentId) currentId = found.id;
    } catch (error) {
      // 오버레이를 다시 시작하는 중
    }
  }, 5000);
}

async function main() {
  listen();
  if (!explicit) watchCharacter();
  const found = await info();
  currentId = found.id;
  if (!found.renders) {
    const app = found.kind === "live2d" ? "VTube Studio" : "Inochi Session";
    show(`${found.name}: ${app}에서 표시하는 캐릭터입니다. OBS에서 ${app} 창 캡처를 사용하십시오.`);
  } else if (found.kind === "png") {
    startPng(found);
  } else {
    await start3d(found);
  }
}

main().catch((error) => show(`캐릭터를 표시하지 못함: ${error.message}`));
