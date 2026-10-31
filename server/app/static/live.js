function live(role, handlers) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let ws;
  let delay = 500;
  const connect = () => {
    handlers.status?.("connecting");
    ws = new WebSocket(`${proto}://${location.host}/ws/${role}`);
    ws.onopen = () => { delay = 500; handlers.status?.("live"); };
    ws.onclose = () => {
      handlers.status?.("reconnecting");
      setTimeout(connect, delay);
      delay = Math.min(delay * 2, 8000);
    };
    ws.onmessage = (e) => {
      const { type, data } = JSON.parse(e.data);
      handlers[type]?.(data);
    };
  };
  connect();
  return {
    send(type, data) {
      if (ws?.readyState !== WebSocket.OPEN) return false;
      ws.send(JSON.stringify({ type, data }));
      return true;
    },
  };
}

function countdown() {
  return {
    deadline: 0,
    total: 0,
    now: Date.now(),
    start(seconds) {
      this.total = seconds * 1000;
      this.deadline = Date.now() + this.total;
    },
    remaining() { return Math.max(0, Math.ceil((this.deadline - this.now) / 1000)); },
    progress() { return this.total ? Math.max(0, (this.deadline - this.now) / this.total) * 100 : 0; },
    tick() { setInterval(() => (this.now = Date.now()), 250); },
  };
}
