import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import Module from "node:module";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {test} from "node:test";
import ts from "typescript";
import {NextRequest} from "next/server.js";

// Exercise the actual TypeScript proxy with Next's request/response objects.
const filename = fileURLToPath(new URL("../proxy.ts", import.meta.url));
const compiled = ts.transpileModule(readFileSync(filename, "utf8"), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText;
const loaded = new Module(filename);
loaded.filename = filename;
loaded.paths = [resolve(dirname(filename), "node_modules")];
loaded._compile(compiled, filename);
const {proxy} = loaded.exports;

test("hosted proxy authenticates only the Vercel client address", () => {
  process.env.VERCEL = "1";
  process.env.PROXY_SHARED_SECRET = "s".repeat(32);
  process.env.API_INTERNAL_URL = "https://api.example.com";
  const response = proxy(new NextRequest("https://web.example.com/api/jobs?limit=3", {
    headers: {
      "x-vercel-forwarded-for": "203.0.113.7",
      "x-jobradar-client-ip": "198.51.100.99",
      "x-jobradar-proxy-secret": "attacker",
      "cookie": "access_token=test",
    },
  }));
  assert.equal(response.headers.get("x-middleware-rewrite"), "https://api.example.com/api/jobs?limit=3");
  assert.equal(response.headers.get("x-middleware-request-x-jobradar-client-ip"), "203.0.113.7");
  assert.equal(response.headers.get("x-middleware-request-x-jobradar-proxy-secret"), "s".repeat(32));
  assert.equal(response.headers.get("x-middleware-request-cookie"), "access_token=test");
  assert.equal(response.headers.get("x-jobradar-proxy-secret"), null);
});

test("hosted proxy fails closed without platform identity or HTTPS", () => {
  process.env.PROXY_SHARED_SECRET = "s".repeat(32);
  process.env.VERCEL = "1";
  process.env.API_INTERNAL_URL = "https://api.example.com";
  assert.equal(proxy(new NextRequest("https://web.example.com/api/jobs")).status, 503);
  const request = new NextRequest("https://web.example.com/api/jobs", {
    headers: {"x-vercel-forwarded-for": "203.0.113.7"},
  });
  process.env.API_INTERNAL_URL = "http://api.example.com";
  assert.equal(proxy(request).status, 503);
  process.env.API_INTERNAL_URL = "https://api.example.com";
  delete process.env.VERCEL;
  assert.equal(proxy(request).status, 503);
});

test("local deployments keep the existing rewrite path", () => {
  delete process.env.PROXY_SHARED_SECRET;
  const response = proxy(new NextRequest("http://localhost:3000/api/jobs"));
  assert.equal(response.headers.get("x-middleware-next"), "1");
});
