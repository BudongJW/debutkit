// debutkit 휴대폰 조작 화면의 요청 서명: SHA-256, HMAC-SHA256(파이썬 overlay/remote.py의 canonical, sign과 같아야 함).
// 휴대폰 브라우저는 http://내부주소 페이지에서 Web Crypto(crypto.subtle)를 제공하지 않으므로 직접 계산한다(FIPS 180-4).

const K = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];
const ror = (x, n) => (x >>> n) | (x << (32 - n));

export function sha256(bytes) {  // Uint8Array -> Uint8Array(32)
  const length = bytes.length;
  const padded = Math.ceil((length + 9) / 64) * 64;
  const data = new Uint8Array(padded);
  data.set(bytes);
  data[length] = 0x80;
  const view = new DataView(data.buffer);
  view.setUint32(padded - 8, Math.floor(length / 0x20000000));  // 비트 길이 상위 32비트
  view.setUint32(padded - 4, (length * 8) >>> 0);
  const h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
  const w = new Array(64);
  for (let offset = 0; offset < padded; offset += 64) {
    for (let t = 0; t < 16; t++) w[t] = view.getUint32(offset + t * 4);
    for (let t = 16; t < 64; t++) {
      const s0 = ror(w[t - 15], 7) ^ ror(w[t - 15], 18) ^ (w[t - 15] >>> 3);
      const s1 = ror(w[t - 2], 17) ^ ror(w[t - 2], 19) ^ (w[t - 2] >>> 10);
      w[t] = (w[t - 16] + s0 + w[t - 7] + s1) | 0;
    }
    let [a, b, c, d, e, f, g, k] = h;
    for (let t = 0; t < 64; t++) {
      const t1 = (k + (ror(e, 6) ^ ror(e, 11) ^ ror(e, 25)) + ((e & f) ^ (~e & g)) + K[t] + w[t]) | 0;
      const t2 = ((ror(a, 2) ^ ror(a, 13) ^ ror(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
      k = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    [a, b, c, d, e, f, g, k].forEach((value, index) => { h[index] = (h[index] + value) | 0; });
  }
  const out = new Uint8Array(32);
  const outView = new DataView(out.buffer);
  h.forEach((value, index) => outView.setUint32(index * 4, value >>> 0));
  return out;
}

const encoder = new TextEncoder();
export const hex = (bytes) => Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");

export function hmacSha256(key, message) {  // 문자열 또는 Uint8Array -> Uint8Array(32)
  let keyBytes = typeof key === "string" ? encoder.encode(key) : key;
  const messageBytes = typeof message === "string" ? encoder.encode(message) : message;
  if (keyBytes.length > 64) keyBytes = sha256(keyBytes);
  const inner = new Uint8Array(64 + messageBytes.length);
  const outer = new Uint8Array(64 + 32);
  for (let i = 0; i < 64; i++) {
    const byte = keyBytes[i] || 0;
    inner[i] = byte ^ 0x36;
    outer[i] = byte ^ 0x5c;
  }
  inner.set(messageBytes, 64);
  outer.set(sha256(inner), 64);
  return sha256(outer);
}

export function canonical(method, path, stamp, nonce, body) {
  return `${method.toUpperCase()}\n${path}\n${stamp}\n${nonce}\n${hex(sha256(encoder.encode(body || "")))}`;
}

export function sign(secret, method, path, stamp, nonce, body) {
  return hex(hmacSha256(secret, canonical(method, path, stamp, nonce, body)));
}

export function confirmCode(secret) {  // 파이썬 remote.confirm_code와 같음
  const digest = hex(hmacSha256(secret, "debutkit-confirm"));
  return String(parseInt(digest.slice(0, 8), 16) % 10000).padStart(4, "0");
}

export function nonce() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);  // 보안 컨텍스트가 아니어도 제공
  return hex(bytes);
}
