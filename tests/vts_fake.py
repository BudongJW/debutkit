"""시험용 VTube Studio: 이 PC에서 WebSocket 서버를 열고 공개 API 일부를 흉내 낸다(실제 프로토콜, 가짜 동작)."""

import base64
import hashlib
import json
import socket
import struct
import threading

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _read_frame(conn):
    head = conn.recv(2)
    if len(head) < 2:
        return None
    opcode, length = head[0] & 0x0F, head[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", conn.recv(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", conn.recv(8))[0]
    mask = conn.recv(4) if head[1] & 0x80 else b""
    data = b""
    while len(data) < length:
        chunk = conn.recv(length - len(data))
        if not chunk:
            return None
        data += chunk
    if mask:
        data = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
    return None if opcode == 8 else data.decode("utf-8")


def _send_frame(conn, text):
    data = text.encode("utf-8")
    head = bytes([0x81])
    if len(data) < 126:
        head += bytes([len(data)])
    elif len(data) < 65536:
        head += bytes([126]) + struct.pack(">H", len(data))
    else:
        head += bytes([127]) + struct.pack(">Q", len(data))
    conn.sendall(head + data)


class FakeVts:
    def __init__(self, *, deny=False, valid=("good-token",)):
        self.deny, self.valid = deny, set(valid)
        self.models = [{"modelID": "m1", "modelName": "Hiyori", "modelLoaded": True}, {"modelID": "m2", "modelName": "Neko Mio", "modelLoaded": False}]
        self.hotkeys = [{"hotkeyID": "h1", "name": "Heart", "type": "ToggleExpression"}, {"hotkeyID": "h2", "name": "Clap", "type": "TriggerAnimation"}]
        self.loaded, self.triggered, self.icons = [], [], []
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen()
        self.url = f"ws://127.0.0.1:{self.server.getsockname()[1]}"
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        request = b""
        while b"\r\n\r\n" not in request:
            request += conn.recv(1024)
        key = [line.split(":", 1)[1].strip() for line in request.decode().split("\r\n") if line.lower().startswith("sec-websocket-key")][0]
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        conn.sendall(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n".encode())
        while True:
            text = _read_frame(conn)
            if text is None:
                conn.close()
                return
            message = json.loads(text)
            _send_frame(conn, json.dumps(self.answer(message)))

    def answer(self, message):
        kind, data = message["messageType"], message.get("data") or {}

        def reply(name, body):
            return {"apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0", "requestID": message["requestID"], "messageType": name, "data": body}

        if kind == "AuthenticationTokenRequest":
            self.icons.append(data.get("pluginIcon", ""))
            if self.deny:
                return reply("APIError", {"errorID": 50, "message": "User has denied API access for your plugin."})
            self.valid.add("new-token")
            return reply("AuthenticationTokenResponse", {"authenticationToken": "new-token"})
        if kind == "AuthenticationRequest":
            ok = data.get("authenticationToken") in self.valid and data.get("pluginName") == "debutkit"
            return reply("AuthenticationResponse", {"authenticated": ok, "reason": "ok" if ok else "invalid token"})
        if kind == "AvailableModelsRequest":
            return reply("AvailableModelsResponse", {"numberOfModels": len(self.models), "availableModels": self.models})
        if kind == "ModelLoadRequest":
            self.loaded.append(data["modelID"])
            return reply("ModelLoadResponse", {"modelID": data["modelID"]})
        if kind == "HotkeysInCurrentModelRequest":
            return reply("HotkeysInCurrentModelResponse", {"availableHotkeys": self.hotkeys})
        if kind == "HotkeyTriggerRequest":
            known = {hotkey["hotkeyID"] for hotkey in self.hotkeys} | {hotkey["name"] for hotkey in self.hotkeys}
            if data["hotkeyID"] not in known:
                return reply("APIError", {"errorID": 202, "message": "Hotkey not found"})
            self.triggered.append(data["hotkeyID"])
            return reply("HotkeyTriggerResponse", {"hotkeyID": data["hotkeyID"]})
        return reply("APIError", {"errorID": 1, "message": "unknown"})

    def close(self):
        self.server.close()
