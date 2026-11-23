// debutkit 휴대폰 카메라 수신 화면(OBS 브라우저 소스): debutkit 휴대폰 앱이 보내는 카메라 영상을 WebRTC로 직접 받는다.
// 연결 정보(SDP)만 이 PC의 debutkit 서버를 거치고(camcall.py), 영상은 같은 Wi-Fi의 휴대폰과 직접 주고받는다(외부 서버 없음).
// 주소 뒤 ?fit=cover 꽉 채우기, ?mirror 좌우 반전, ?debug 연결 상태 글자(일반 브라우저에서 확인할 때).

const params = new URLSearchParams(location.search);
const video = document.getElementById("video");
const state = document.getElementById("state");
const debug = params.has("debug");
if (params.get("fit") === "cover") video.classList.add("cover");
if (params.has("mirror")) video.classList.add("mirror");
let pc = null;
let current = "";

function show(text) {
  if (!debug) return;
  state.textContent = text;
  state.hidden = !text;
}

function close() {
  if (pc) pc.close();
  pc = null;
  video.srcObject = null;
}

function gathered(peer, ms) {  // 후보(내 주소) 모으기가 끝날 때까지(외부 서버가 없으므로 금방 끝남)
  if (peer.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    peer.addEventListener("icegatheringstatechange", () => {
      if (peer.iceGatheringState === "complete") {
        clearTimeout(timer);
        resolve();
      }
    });
  });
}

async function accept(call) {
  close();
  current = call.id;
  const peer = new RTCPeerConnection({ iceServers: [] });
  pc = peer;
  peer.ontrack = (event) => {
    video.srcObject = event.streams[0] || new MediaStream([event.track]);
    video.play().catch(() => {});
  };
  peer.onconnectionstatechange = () => {
    const labels = { connecting: "연결 중", connected: `${call.name} 연결됨`, disconnected: "연결 끊김", failed: "연결 실패: 같은 Wi-Fi인지, 방화벽 확인" };
    show(labels[peer.connectionState] || "");
    if (peer.connectionState === "disconnected" || peer.connectionState === "failed") {
      setTimeout(() => {  // 5초 넘게 끊겨 있으면 통화 끝으로 알림(앱이 꺼진 경우 등. 앱은 살아 있으면 다시 연결 제안)
        if (pc === peer && peer.connectionState !== "connected") {
          fetch("/camera/ended", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: call.id }) }).catch(() => {});
        }
      }, 5000);
    }
  };
  await peer.setRemoteDescription({ type: "offer", sdp: call.sdp });
  await peer.setLocalDescription(await peer.createAnswer());
  await gathered(peer, 3000);
  if (pc !== peer) return;
  const response = await fetch("/camera/answer", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: call.id, sdp: peer.localDescription.sdp }),
  });
  if (!response.ok && pc === peer) {  // 다른 수신 화면이 먼저 응답함
    close();
    show("다른 화면이 연결함");
  }
}

const live = new EventSource("/live?feeds=camera");
live.addEventListener("camera", (message) => {
  const call = JSON.parse(message.data);
  if (call.type === "offer" && call.id !== current) {
    accept(call).catch((error) => show(`연결 실패: ${error.message}`));
  } else if ((call.type === "stop" || call.type === "idle") && (!call.id || call.id === current)) {
    close();
    current = "";
    show("휴대폰 대기");
  }
});
show("휴대폰 대기");
window.debutkitCamera = { get pc() { return pc; }, video };  // 시험용
