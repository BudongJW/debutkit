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
const motionRequests = { handler: null };  // 3D 캐릭터를 불러온 뒤 동작 실행 요청을 처리
let currentId = "";

function tracking() {  // 최근 추적 값이 있으면 그 값, 없으면 null
  return tracked.found && Date.now() / 1000 - tracked.time < 0.6 ? tracked : null;
}


function show(text) {
  notice.textContent = text;
  notice.hidden = !text;
}

function listen() {
  // 브라우저의 같은 주소 동시 연결 수 제한(6개, OBS 브라우저 소스끼리 공유) 때문에 다른 방송 화면과 공유 연결(live.js) 하나로 받는다
  window.debutkitLive.subscribe(demo ? ["tracking", "motion"] : ["voice", "tracking", "motion"], (feed, data) => {
    if (feed === "tracking") Object.assign(tracked, { found: false }, data);
    else if (feed === "motion") motionRequests.handler?.(data);
    else if (feed === "voice") Object.assign(voice, data);
  });
  if (demo) {  // 말하기 시험: 0.6초 말하고 0.6초 쉼
    setInterval(() => {
      voice.talking = !voice.talking;
      voice.level = voice.talking ? 0.75 : 0;
    }, 600);
  }
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

// 퍼펙트 싱크: ARKit 표정 52개(파이썬 tracking.ARKIT_NAMES와 같아야 함). 같은 이름의 표정이 있는 모델은 추적 값으로 얼굴 전체를 움직인다
export const ARKIT = [
  "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight", "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
  "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight",
  "eyeLookUpLeft", "eyeLookUpRight", "eyeSquintLeft", "eyeSquintRight", "eyeWideLeft", "eyeWideRight", "jawForward", "jawLeft", "jawOpen",
  "jawRight", "mouthClose", "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft", "mouthFrownRight", "mouthFunnel", "mouthLeft",
  "mouthLowerDownLeft", "mouthLowerDownRight", "mouthPressLeft", "mouthPressRight", "mouthPucker", "mouthRight", "mouthRollLower",
  "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper", "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft", "mouthStretchRight",
  "mouthUpperUpLeft", "mouthUpperUpRight", "noseSneerLeft", "noseSneerRight", "tongueOut",
];
const PERFECT_SYNC_MIN = 12;  // ARKit 이름 표정이 이만큼 있으면 퍼펙트 싱크 모델로 판단
const ARKIT_KEYS = new Map();
for (const name of ARKIT) {
  ARKIT_KEYS.set(normalize(name), name);
  const side = name.match(/(Left|Right)$/);
  if (side && !/^(jaw|mouth)(Left|Right)$/.test(name)) ARKIT_KEYS.set(normalize(name.slice(0, -side[1].length) + side[1][0]), name);  // eyeBlink_L
}

export function arkitName(name) {  // 표정이나 형태 변형 이름 -> ARKit 이름(대소문자, _L, _R, 앞 붙은 이름 무시). 없으면 null
  for (const key of morphKeys(name)) {
    const found = ARKIT_KEYS.get(key);
    if (found) return found;
  }
  return null;
}

export function perfectSyncMap(names) {  // 표정 이름 목록 -> Map(ARKit 이름 -> 표정 이름). 먼저 나온 이름 사용
  const found = new Map();
  for (const name of names) {
    const key = arkitName(name);
    if (key && !found.has(key)) found.set(key, name);
  }
  return found;
}

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
  const table = await nameTable();
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
  for (const [canonical, morph] of perfectSyncMap(names)) {  // ARKit 이름 형태 변형(퍼펙트 싱크)은 그 이름의 표정으로
    if (expressionManager.getExpression(canonical)) continue;
    const expression = new lib.VRMExpression(canonical);
    for (const mesh of meshes) {
      const index = mesh.morphTargetDictionary[morph];
      if (index !== undefined) expression.addBind(new lib.VRMExpressionMorphTargetBind({ primitives: [mesh], index, weight: 1 }));
    }
    expressionManager.registerExpression(expression);
    scene.add(expression);
  }
  const meta = { metaVersion: "1", name: info.name, authors: [], licenseUrl: "" };
  return new lib.VRMCore({ scene, meta, humanoid, expressionManager });
}

// ------------------------------------------------------------------ 동작(VRMA, FBX, GLB)
// 동작은 정규화 뼈대(VRM 1.0 방향, 기준 자세에서 회전 0)의 회전으로 바꿔 AnimationMixer로 재생한다.
// 매 프레임 기본 움직임(팔 내림, 호흡, 흔들림)을 먼저 정하고, 동작이 있으면 그 위에 섞은 뒤 얼굴 추적 회전을 더한다.

const FADE = 0.4;  // 동작 사이 전환 시간(초)
const DRIVEN = new Set(["aa", "ih", "ou", "ee", "oh", "blink", "blinkLeft", "blinkRight", "happy"]);  // 목소리, 눈 깜빡임, 추적이 정하는 표정
let humanoidTable = null;

async function nameTable() {  // 뼈와 표정 이름 표(/character/humanoid.json)
  humanoidTable ??= fetch("/character/humanoid.json", { cache: "no-store" }).then((response) => response.json());
  return humanoidTable;
}

function trackNode(track) {
  return track.name.slice(0, track.name.lastIndexOf("."));
}

// 동작 파일의 뼈 회전을 정규화 뼈대 기준으로: 부모의 기준 자세 월드 회전 * 동작 회전 * 기준 자세 월드 회전의 역(three-vrm 공식 예제 방식)
export function retarget(THREE, root, source, vrm, bones) {
  root.updateMatrixWorld(true);
  const nodes = {};
  const order = [];
  root.traverse((node) => {
    if (node.name && !(node.name in nodes)) {
      nodes[node.name] = node;
      order.push(node);
    }
  });
  const found = matchBones([...order.filter((node) => node.isBone), ...order.filter((node) => !node.isBone)].map((node) => node.name), bones);
  const boneOf = Object.fromEntries(Object.entries(found).map(([bone, name]) => [name, bone]));
  const vrm0 = vrm.meta?.metaVersion === "0";
  const rig = (vector) => (vrm0 ? vector.set(-vector.x, vector.y, -vector.z) : vector);  // VRM 0.x 정규화 뼈대는 반대 방향
  const at = (bone) => nodes[found[bone]].getWorldPosition(new THREE.Vector3());
  const rest = vrm.humanoid.normalizedRestPose;
  const legs = ["leftUpperLeg", "leftLowerLeg", "leftFoot"].reduce((sum, bone) => sum + (rest[bone]?.position?.[1] || 0), 0);
  const sourceHeight = found.leftFoot ? at("hips").y - at("leftFoot").y : at("hips").y;
  const scale = sourceHeight > 1e-6 && legs < 0 ? -legs / sourceHeight : 1;  // 엉덩이에서 발목까지 높이 비율
  const hipsRest = at("hips");
  const tracks = [];
  const quaternion = new THREE.Quaternion();
  const point = new THREE.Vector3();
  for (const track of source.tracks) {
    const name = trackNode(track);
    const bone = boneOf[name];
    const target = bone && vrm.humanoid.getNormalizedBoneNode(bone);
    if (!target) continue;
    const node = nodes[name];
    if (track instanceof THREE.QuaternionKeyframeTrack) {
      const inverse = node.getWorldQuaternion(new THREE.Quaternion()).invert();
      const parent = node.parent ? node.parent.getWorldQuaternion(new THREE.Quaternion()) : new THREE.Quaternion();
      const values = new Float32Array(track.values.length);
      for (let i = 0; i < values.length; i += 4) {
        quaternion.fromArray(track.values, i).premultiply(parent).multiply(inverse);
        if (vrm0) quaternion.set(-quaternion.x, quaternion.y, -quaternion.z, quaternion.w);
        quaternion.toArray(values, i);
      }
      tracks.push(new THREE.QuaternionKeyframeTrack(`${target.name}.quaternion`, track.times, values));
    } else if (bone === "hips" && track.name.endsWith(".position")) {  // 엉덩이 이동: 기준 자세에서 움직인 거리를 캐릭터 크기에 맞춤
      const parentMatrix = node.parent ? node.parent.matrixWorld : new THREE.Matrix4();
      const origin = new THREE.Vector3().fromArray(rest.hips.position);
      const values = new Float32Array(track.values.length);
      for (let i = 0; i < values.length; i += 3) {
        rig(point.fromArray(track.values, i).applyMatrix4(parentMatrix).sub(hipsRest).multiplyScalar(scale)).add(origin).toArray(values, i);
      }
      tracks.push(new THREE.VectorKeyframeTrack(`${target.name}.position`, track.times, values));
    }
  }
  if (!tracks.length) throw new Error("사람 모양 뼈를 움직이는 동작이 없음");
  const arm = (side) => (found[`${side}UpperArm`] && found[`${side}LowerArm`] ? rig(at(`${side}LowerArm`).sub(at(`${side}UpperArm`))) : null);
  return { clip: new THREE.AnimationClip(source.name, source.duration, tracks), arms: { left: arm("left"), right: arm("right") } };
}

// 기준 자세 차이 보정: 동작의 기준 팔 방향(VRMA는 T자)과 캐릭터의 기준 팔 방향(A자 모델 등)이 다르면 위팔, 아래팔, 손 회전을 맞춘다
export function fitArms(THREE, clip, vrm, arms) {
  const rest = vrm.humanoid.normalizedRestPose;
  const name = (bone) => vrm.humanoid.getNormalizedBoneNode(bone)?.name;
  const quaternion = new THREE.Quaternion();
  for (const side of ["left", "right"]) {
    const offset = rest[`${side}LowerArm`]?.position;
    if (!offset || !arms[side]) continue;
    const fix = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3().fromArray(offset).normalize(), arms[side].clone().normalize());
    if (fix.angleTo(new THREE.Quaternion()) < 0.02) continue;
    const back = fix.clone().invert();
    const upper = name(`${side}UpperArm`);
    if (!clip.tracks.some((track) => trackNode(track) === upper)) continue;
    const children = new Set([name(`${side}LowerArm`), name(`${side}Hand`)]);
    for (const track of clip.tracks) {
      const node = trackNode(track);
      if (!(track instanceof THREE.QuaternionKeyframeTrack) || (node !== upper && !children.has(node))) continue;
      for (let i = 0; i < track.values.length; i += 4) {
        quaternion.fromArray(track.values, i);
        if (node === upper) quaternion.multiply(fix);
        else quaternion.premultiply(back).multiply(fix);
        quaternion.toArray(track.values, i);
      }
    }
  }
}

async function loadClip(THREE, vrm, item) {
  const { GLTFLoader } = await import("three/addons/loaders/GLTFLoader.js");
  const vrm0 = vrm.meta?.metaVersion === "0";
  let made;
  if (item.kind === "vrma") {
    const animation = await import("/vendor/three-vrm-animation/three-vrm-animation.module.min.js");
    const loader = new GLTFLoader();
    loader.register((parser) => new animation.VRMAnimationLoaderPlugin(parser));
    const source = (await loader.loadAsync(item.url)).userData.vrmAnimations?.[0];
    if (!source) throw new Error("VRMA 동작을 읽지 못함");
    // 시선은 카메라를 보도록 두고 동작의 시선은 쓰지 않음(lookAt 제외)
    const target = { humanoid: vrm.humanoid, meta: vrm.meta, expressionManager: vrm.expressionManager, scene: vrm.scene, lookAt: null };
    const sign = vrm0 ? -1 : 1;
    made = { clip: animation.createVRMAnimationClip(source, target), arms: { left: new THREE.Vector3(sign, 0, 0), right: new THREE.Vector3(-sign, 0, 0) } };
  } else {
    let root;
    let clips;
    if (item.kind === "fbx") {
      const { FBXLoader } = await import("three/addons/loaders/FBXLoader.js");
      root = await new FBXLoader().loadAsync(item.url);
      clips = root.animations;
    } else {
      const gltf = await new GLTFLoader().loadAsync(item.url);
      root = gltf.scene;
      clips = gltf.animations;
    }
    const source = (item.clip && clips.find((clip) => clip.name === item.clip)) || clips[0];
    if (!source) throw new Error("동작이 없는 파일");
    made = retarget(THREE, root, source, vrm, await nameTable());
  }
  const expression = (track) => trackNode(track).startsWith("VRMExpression_") && DRIVEN.has(trackNode(track).slice("VRMExpression_".length));
  made.clip.tracks = made.clip.tracks.filter((track) => !expression(track));
  fitArms(THREE, made.clip, vrm, made.arms);
  return made.clip;
}

function motionPlayer(THREE, vrm) {
  const mixer = new THREE.AnimationMixer(vrm.scene);
  const clips = new Map();
  const entries = [];  // { id, action, weight, target, idle }
  const bones = Object.keys(vrm.humanoid.rawHumanBones).filter((bone) => !bone.endsWith("Eye"))  // 눈은 시선(lookAt)이 정함
    .map((bone) => vrm.humanoid.getNormalizedBoneNode(bone)).filter(Boolean);
  const hips = vrm.humanoid.getNormalizedBoneNode("hips");
  const hipsRest = new THREE.Vector3().fromArray(vrm.humanoid.normalizedRestPose.hips?.position || [0, 0, 0]);
  const saved = bones.map(() => new THREE.Quaternion());
  const savedHips = new THREE.Vector3();
  const blended = new THREE.Quaternion();
  let idleId = "";

  const clipOf = (item) => {
    if (!clips.has(item.id)) clips.set(item.id, loadClip(THREE, vrm, item).catch((error) => {
      clips.delete(item.id);
      throw error;
    }));
    return clips.get(item.id);
  };
  const failed = (item, error) => {
    console.warn("debutkit 동작", item.name, error);
    show(`동작을 불러오지 못함(${item.name}): ${error.message}`);
    setTimeout(() => show(""), 6000);
  };
  const once = () => entries.some((entry) => !entry.idle && entry.target === 1);

  return {
    entries,
    reset() {  // 매 프레임 기준 자세에서 시작(기본 움직임이 정하지 않는 뼈는 기준 자세)
      for (const bone of bones) bone.quaternion.identity();
      if (hips) hips.position.copy(hipsRest);
    },
    async play(item, idle = false) {
      try {
        const clip = await clipOf(item);
        if (idle && item.id !== idleId) return;  // 불러오는 사이 기본 동작이 바뀜
        const action = mixer.clipAction(clip);
        let entry = entries.find((found) => found.action === action);
        if (entry?.idle) return;  // 기본 동작으로 재생 중인 동작은 그대로
        if (entry && idle) {  // 실행 중인 동작을 기본 동작으로 지정
          entry.idle = true;
          action.paused = false;
          action.setLoop(THREE.LoopRepeat, Infinity);
          return;
        }
        if (!entry) {
          entry = { id: item.id, action, weight: 0, target: 1, idle };
          entries.push(entry);
        }
        entry.target = 1;
        action.reset();
        action.setLoop(idle ? THREE.LoopRepeat : THREE.LoopOnce, Infinity);
        action.clampWhenFinished = true;
        action.play();
        if (!idle) for (const other of entries) if (other !== entry && !other.idle) other.target = 0;
      } catch (error) {
        failed(item, error);
      }
    },
    idle(item) {  // 기본 동작 지정(null이면 해제)
      idleId = item ? item.id : "";
      if (item && !entries.some((entry) => entry.idle && entry.id === item.id)) this.play(item, true);
    },
    stop() {
      for (const entry of entries) if (!entry.idle) entry.target = 0;
    },
    update(delta) {
      for (const entry of entries) {
        if (!entry.idle && entry.target === 1 && entry.action.time >= entry.action.getClip().duration - FADE) entry.target = 0;  // 끝나기 전에 되돌아감
      }
      const busy = once();
      for (const entry of entries) {
        if (entry.idle) entry.target = !busy && entry.id === idleId ? 1 : 0;
        const step = Math.min(Math.abs(entry.target - entry.weight), delta / FADE);
        entry.weight += Math.sign(entry.target - entry.weight) * step;
      }
      for (let i = entries.length - 1; i >= 0; i--) {
        const entry = entries[i];
        if (entry.weight <= 0 && entry.target === 0 && !(entry.idle && entry.id === idleId)) {
          entry.action.stop();
          entries.splice(i, 1);
        }
      }
      const total = entries.reduce((sum, entry) => sum + entry.weight, 0);
      if (total <= 0) return;
      bones.forEach((bone, i) => saved[i].copy(bone.quaternion));
      if (hips) savedHips.copy(hips.position);
      for (const entry of entries) entry.action.setEffectiveWeight(entry.weight / total);  // 동작끼리는 합이 1(기준 자세와 섞이지 않게)
      mixer.update(delta);
      const weight = Math.min(1, total);  // 기본 움직임과 동작 사이
      if (weight < 1) {
        bones.forEach((bone, i) => {
          blended.copy(bone.quaternion);
          bone.quaternion.copy(saved[i]).slerp(blended, weight);
        });
        if (hips) hips.position.lerp(savedHips, 1 - weight);
      }
    },
  };
}

async function motionList() {
  const response = await fetch("/motion/list", { cache: "no-store" });
  if (!response.ok) throw new Error("동작 목록을 받지 못함");
  return response.json();
}

function startMotions(player) {
  // 동작 실행 요청(/live의 motion). 연결할 때 받는 지난 요청은 재생하지 않는다
  let seen = -1;
  motionRequests.handler = async (data) => {
    const fresh = data.seq !== seen && Date.now() / 1000 - data.time < 5;
    seen = data.seq;
    if (!fresh) return;
    if (data.stop) return player.stop();
    const item = (await motionList()).motions.find((found) => found.id === data.play);
    if (item) player.play(item);
  };
  let idleId = null;
  const watch = async () => {
    try {
      const list = await motionList();
      if (list.idle !== idleId) {
        idleId = list.idle;
        player.idle(list.motions.find((found) => found.id === list.idle) || null);
      }
    } catch (error) {
      // 오버레이를 다시 시작하는 중
    }
  };
  watch();
  setInterval(watch, 5000);
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
  const player = motionPlayer(THREE, vrm);
  window.debutkitCharacter = { vrm, THREE, player };  // 시험용

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
  const leftLowered = -lowered("left") * flip;
  const rightLowered = lowered("right") * flip;
  const jaw = vrm.expressionManager?.getExpression("aa") ? null : bone("jaw");  // 입 모양 표정이 없으면 턱 뼈로
  startMotions(player);
  const euler = new THREE.Euler();
  const turn = new THREE.Quaternion();

  const timer = new THREE.Timer();
  let blink = 0;
  let blinkStart = -1;
  scheduleBlink(() => (blinkStart = timer.getElapsed()));
  let mouth = 0;
  const spine = bone("spine");
  const neck = bone("neck");
  const head = bone("head");
  const pose = { yaw: 0, pitch: 0, roll: 0, blinkLeft: 0, blinkRight: 0, mouth: 0, smile: 0 };  // 추적 값(부드럽게 따라감)
  // 퍼펙트 싱크: 모델에 ARKit 이름 표정이 충분하면 추적 값(arkit)으로 얼굴 전체를 움직이고 입, 눈, 웃음 기본 표정은 쓰지 않는다
  const perfect = vrm.expressionManager ? perfectSyncMap(vrm.expressionManager.expressions.map((item) => item.expressionName)) : new Map();
  const perfectSync = perfect.size >= PERFECT_SYNC_MIN;
  const shapes = Object.fromEntries([...perfect.keys()].map((name) => [name, 0]));
  window.debutkitCharacter.perfectSync = perfectSync ? Object.fromEntries(perfect) : null;  // 시험용
  const animate = (timestamp) => {
    timer.update(timestamp);
    const delta = Math.min(timer.getDelta(), 0.1);
    const t = timer.getElapsed();
    const face = tracking();
    const follow = Math.min(1, delta * 14);
    for (const name of Object.keys(pose)) pose[name] += ((face ? face[name] || 0 : 0) - pose[name]) * follow;
    const synced = perfectSync && Boolean(face && face.arkit && Object.keys(face.arkit).length);  // 이번 프레임에 퍼펙트 싱크로 움직임
    if (perfectSync) {
      const quick = Math.min(1, delta * 20);
      for (const name of Object.keys(shapes)) shapes[name] += ((synced ? face.arkit[name] || 0 : 0) - shapes[name]) * quick;
    }
    const target = voice.talking ? Math.min(1, 0.35 + voice.level * 0.8) : 0;
    mouth += (Math.max(target, pose.mouth * 1.1) - mouth) * Math.min(1, delta * 18);
    if (blinkStart >= 0) {
      const phase = (t - blinkStart) / 0.16;
      blink = phase < 1 ? Math.sin(phase * Math.PI) : 0;
      if (phase >= 1) blinkStart = -1;
    }
    player.reset();
    if (leftArm) leftArm.rotation.z = leftLowered;
    if (rightArm) rightArm.rotation.z = rightLowered;
    if (jaw) jaw.rotation.x = (synced ? shapes.jawOpen || 0 : Math.min(1, mouth)) * 0.3 * flip;
    const expressions = vrm.expressionManager;
    if (perfectSync) for (const [name, expression] of perfect) expressions.setValue(expression, shapes[name]);
    if (expressions && synced) {  // 퍼펙트 싱크 중: 기본 표정은 0(같은 형태 변형을 두 번 움직이지 않도록)
      for (const name of ["aa", "blink", "blinkLeft", "blinkRight", "happy"]) expressions.setValue(name, 0);
    } else if (expressions) {
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
    if (neck) neck.rotation.set(0, Math.sin(t * 0.5) * 0.06 * idle, Math.sin(t * 0.7) * 0.02 * idle * flip + (voice.talking ? Math.sin(t * 9) * 0.01 * idle : 0));
    player.update(delta);  // 동작(있으면 기본 움직임 위에 섞음)
    // 얼굴 추적 머리 회전은 동작 위에 더함: 목 40%, 머리 60%(VRM 0.x는 x, z 방향 반대)
    if (neck) neck.quaternion.multiply(turn.setFromEuler(euler.set(pose.pitch * 0.4 * flip, pose.yaw * 0.4, pose.roll * 0.4 * flip)));
    if (head) head.quaternion.multiply(turn.setFromEuler(euler.set(pose.pitch * 0.6 * flip, pose.yaw * 0.6, pose.roll * 0.6 * flip)));
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
