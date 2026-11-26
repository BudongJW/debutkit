// debutkit 커뮤니티 미리보기: node preview.mjs [포트] [데이터 파일]
// Cloudflare에 올리기 전에 이 PC에서 화면을 확인한다(127.0.0.1만). debutkit API 토큰은 DEBUTKIT_COMMUNITY_TOKEN 또는 dev-token.
import { createServer } from "node:http";
import worker from "./worker.js";
import { fakeEnv } from "./local.mjs";

const port = Number(process.argv[2] || 8794);
const env = await fakeEnv({ adminToken: process.env.DEBUTKIT_COMMUNITY_TOKEN || "dev-token", path: process.argv[3] || ":memory:" });

createServer(async (req, res) => {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const body = chunks.length ? Buffer.concat(chunks) : undefined;
  const headers = new Headers();
  for (const [key, value] of Object.entries(req.headers)) if (typeof value === "string") headers.set(key, value);
  const request = new Request(`http://localhost:${port}${req.url}`, { method: req.method, headers, body: ["GET", "HEAD"].includes(req.method) ? undefined : body });
  const response = await worker.fetch(request, env);
  const out = {};
  response.headers.forEach((value, key) => { if (key !== "set-cookie") out[key] = value; });
  const setCookie = response.headers.getSetCookie();
  if (setCookie.length) out["set-cookie"] = setCookie;
  res.writeHead(response.status, out);
  res.end(Buffer.from(await response.arrayBuffer()));
}).listen(port, "127.0.0.1", () => console.log(`debutkit 커뮤니티 미리보기: http://localhost:${port}`));
