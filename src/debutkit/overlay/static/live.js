// debutkit 실시간 항목 받기와 무대 차례
//
// debutkitLive.subscribe(["pick", "theme"], (feed, data, initial) => { ... })
//   공유 연결(live-worker.js, SharedWorker)로 모든 화면이 /live 연결 하나를 함께 쓴다. 브라우저는 같은 주소에 동시 연결을
//   6개까지만 열기 때문(OBS 브라우저 소스끼리도 공유). SharedWorker가 없거나 3초 안에 응답이 없으면 이 화면만 직접 연결한다.
//   initial: 연결(다시 연결 포함) 직후의 현재 상태 값. 지난 연출을 다시 재생하지 않도록 화면이 구분한다.
//   theme 항목은 debutkitTheme(theme.js)이 있으면 색을 바로 바꾼다. 주소 뒤 ?direct 는 공유 연결을 쓰지 않음(문제 확인용).
//
// const release = await debutkitLive.cue("draw")  ...연출...  release()
//   화면 가운데를 크게 쓰는 연출(후원 추첨, 참여 추첨 결과, 뽑기판 결과)이 겹치지 않도록 차례를 기다린다(같은 브라우저의 모든 화면,
//   OBS 브라우저 소스끼리 포함). 알림, 후원 벽 카드, 채팅처럼 작은 연출은 차례 없이 함께 나온다.
//   조작 화면 안의 미리보기는 방송 화면을 기다리게 하지 않도록 차례에 끼지 않는다. 20초 넘게 기다리면 그냥 진행.
"use strict";

(() => {
  const params = new URLSearchParams(location.search);
  const forceDirect = params.has("direct");
  let port = null;  // 이 화면의 공유 연결(한 화면에 하나)
  let answered = false;
  let failed = false;
  const handlers = [];  // [항목 Set, 처리 함수]
  const directs = [];  // 공유 연결이 안 될 때의 직접 연결 해제 함수
  const waiting = new Map();  // 차례 번호 -> 받으면 부를 함수
  let cueSeq = 0;

  function onAir() {
    if (window.top === window) return true;  // OBS 브라우저 소스, 송출 화면 창
    try {
      return /^\/(stage|program)$/.test(window.top.location.pathname);  // 방송 화면 미리보기, 송출 화면 안의 화면
    } catch (error) {
      return false;
    }
  }

  function direct(feeds, handler) {
    const source = new EventSource(`/live?feeds=${encodeURIComponent(feeds.join(","))}`);
    const fresh = new Set();
    source.addEventListener("open", () => { for (const feed of feeds) fresh.add(feed); });
    for (const feed of feeds) {
      source.addEventListener(feed, (event) => {
        let data;
        try { data = JSON.parse(event.data); } catch (error) { return; }
        handler(feed, data, fresh.delete(feed));
      });
    }
    return () => source.close();
  }

  function fallback() {  // 공유 연결을 포기하고 화면마다 직접 연결
    failed = true;
    if (port) port.close();
    port = null;
    for (const [feeds, handler] of handlers) directs.push(direct([...feeds], handler));
    for (const resolve of waiting.values()) resolve();
    waiting.clear();
  }

  function shared() {
    if (port || failed) return port;
    if (forceDirect || !("SharedWorker" in window)) {
      failed = true;
      return null;
    }
    try {
      port = new SharedWorker("/live-worker.js", { name: "debutkit-live" }).port;
    } catch (error) {
      failed = true;
      return null;
    }
    port.onmessage = (message) => {
      const value = message.data || {};
      if (value.state) answered = true;
      if (value.cue && waiting.has(value.cue)) {
        const resolve = waiting.get(value.cue);
        waiting.delete(value.cue);
        resolve();
      }
      if (value.feed) {
        for (const [feeds, handler] of handlers) if (feeds.has(value.feed)) handler(value.feed, value.data, value.initial);
      }
    };
    port.start();
    setTimeout(() => { if (!answered && !failed) fallback(); }, 3000);  // 공유 연결이 동작하지 않는 환경(일부 내장 브라우저)
    addEventListener("pagehide", () => { if (port) port.postMessage({ close: true }); });
    return port;
  }

  function subscribe(feeds, handler) {
    const wanted = new Set(feeds);
    const wrapped = (feed, data, initial) => {
      if (feed === "theme" && window.debutkitTheme) window.debutkitTheme.apply(data);
      try { handler(feed, data, Boolean(initial)); } catch (error) { console.warn("debutkit: 화면 처리 실패", error); }
    };
    handlers.push([wanted, wrapped]);
    const connection = shared();
    if (!connection) {
      const close = direct([...wanted], wrapped);
      directs.push(close);
      return close;
    }
    connection.postMessage({ subscribe: [...wanted] });
    return () => {
      const index = handlers.findIndex(([set]) => set === wanted);
      if (index >= 0) handlers.splice(index, 1);
    };
  }

  function cue(name) {
    const connection = shared();
    if (!connection || failed || !onAir()) return Promise.resolve(() => {});
    const id = `${name}-${Date.now()}-${++cueSeq}`;
    return new Promise((resolve) => {
      let done = false;
      const release = () => {
        if (done) return;
        done = true;
        if (port) port.postMessage({ release: id });
      };
      waiting.set(id, () => resolve(release));
      connection.postMessage({ cue: id, name });
      setTimeout(() => {  // 오래 기다리면 그냥 진행(앞 연출이 멈춘 경우)
        if (!waiting.has(id)) return;
        waiting.delete(id);
        connection.postMessage({ release: id });
        resolve(() => {});
      }, 20000);
    });
  }

  window.debutkitLive = { subscribe, cue };
})();
