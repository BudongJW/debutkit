// debutkit 실시간 항목 받기: debutkitLive.subscribe(["pick", "theme"], (feed, data, initial) => { ... })
// 공유 연결(live-worker.js, SharedWorker)로 모든 화면이 /live 연결 하나를 함께 쓴다. 브라우저는 같은 주소에 동시 연결을
// 6개까지만 열기 때문(OBS 브라우저 소스끼리도 공유). SharedWorker가 없거나 3초 안에 응답이 없으면 이 화면만 직접 연결한다.
// initial: 연결(다시 연결 포함) 직후의 현재 상태 값. 지난 연출을 다시 재생하지 않도록 화면이 구분한다.
// theme 항목은 debutkitTheme(theme.js)이 있으면 색을 바로 바꾼다. 주소 뒤 ?direct 는 공유 연결을 쓰지 않음(문제 확인용).
"use strict";

(() => {
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

  function subscribe(feeds, handler) {
    const wanted = [...new Set(feeds)];
    const wrapped = (feed, data, initial) => {
      if (feed === "theme" && window.debutkitTheme) window.debutkitTheme.apply(data);
      try { handler(feed, data, Boolean(initial)); } catch (error) { console.warn("debutkit: 화면 처리 실패", error); }
    };
    if (!("SharedWorker" in window) || new URLSearchParams(location.search).has("direct")) return direct(wanted, wrapped);
    let worker;
    try {
      worker = new SharedWorker("/live-worker.js", { name: "debutkit-live" });
    } catch (error) {
      return direct(wanted, wrapped);
    }
    let fallback = null;
    let answered = false;
    const port = worker.port;
    port.onmessage = (message) => {
      const value = message.data || {};
      if (value.state) answered = true;
      if (value.feed && wanted.includes(value.feed)) wrapped(value.feed, value.data, value.initial);
    };
    port.start();
    port.postMessage({ subscribe: wanted });
    const watchdog = setTimeout(() => {  // 공유 연결이 동작하지 않는 환경(일부 내장 브라우저)
      if (answered) return;
      port.close();
      fallback = direct(wanted, wrapped);
    }, 3000);
    const close = () => {
      clearTimeout(watchdog);
      if (fallback) fallback();
      else port.postMessage({ close: true });
    };
    addEventListener("pagehide", close);
    return close;
  }

  window.debutkitLive = { subscribe };
})();
