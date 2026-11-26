// debutkit 게임 패키지 미리보기(/games/preview?game=valorant): 그 게임 느낌의 배경 그림 위에 실제 방송 화면(캐릭터 프레임, 채팅창, 후원 알림)을
// 패키지 배치대로 겹쳐 그린다. 고른 게임의 방송 스타일과 색은 이 화면에서만 쓰고 저장하지 않는다. 그림 단추(그림 견본 이미지)를 만들 때도 쓴다.
// 주소: ?game=키 &hud=0(게임 HUD 흉내 숨기기)
"use strict";

(() => {
  const params = new URLSearchParams(location.search);
  const stage = document.getElementById("stage");
  const fit = () => { stage.style.transform = `scale(${Math.min(innerWidth / 1920, innerHeight / 1080)})`; };
  addEventListener("resize", fit);
  fit();

  const el = (tag, className) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    return node;
  };
  const place = (node, [x, y, w, h]) => Object.assign(node.style, { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px` });
  // HUD 이름으로 흉내 모양 고르기(미니맵, 체력 막대만. 나머지는 배경 그림이 대신)
  const hudKind = (label) => (/미니맵|레이더/.test(label) ? "map" : /체력|스킬|단축|상태 막대/.test(label) ? "bar" : "");

  fetch("/games").then((response) => response.json()).then((info) => {
    const key = params.get("game");
    const game = (info.games || {})[key];
    if (!game) return;
    const colors = { primary: game.primary.slice(1), highlight: game.highlight.slice(1) };
    const scene = el("img", "scene");
    scene.src = `/games/scene/${key}.svg`;
    scene.alt = "";
    stage.appendChild(scene);
    if (params.get("hud") !== "0") {
      for (const hud of game.hud) {
        const kind = hudKind(hud.label);
        if (!kind || /전장|판|손패/.test(hud.label)) continue;  // 화면 가운데를 차지하는 게임 판은 배경 그림이 대신
        const box = el("div", `hud ${kind}`);
        place(box, hud.rect);
        stage.appendChild(box);
      }
    }
    // 캐릭터 자리: 예시 캐릭터 그림 + 캐릭터 프레임(이름표)
    const cam = el("div", "cam");
    place(cam, game.character);
    const avatar = el("img");
    avatar.src = "/games/avatar.svg";
    avatar.alt = "";
    const frame = el("iframe", "layer");
    frame.src = `/frame?${new URLSearchParams({ kind: "cam", look: game.look, name: "치즈냥", tag: "LIVE", ...colors })}`;
    cam.append(avatar, frame);
    stage.appendChild(cam);
    // 채팅창(방송 스타일 카드, 예시 채팅)
    const chat = el("iframe", "layer");
    chat.src = `/chat?${new URLSearchParams({ theme: "style", look: game.look, sample: "1", font: "21", max: "6", ...colors })}`;
    place(chat, game.chat);
    stage.appendChild(chat);
    // 후원 알림(멈춘 그림)
    const alert = el("iframe", "layer");
    alert.src = `/alerts?${new URLSearchParams({ still: "1", style: game.look, position: game.alert, layout: "card", scale: "100", ...colors })}`;
    place(alert, [0, 0, 1920, 1080]);
    stage.appendChild(alert);
  });
})();
