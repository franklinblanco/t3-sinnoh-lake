import assert from "node:assert/strict";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";

const { chromium } = createRequire(import.meta.url)("playwright-core");
const assets = new URL("../assets/poketch/", import.meta.url);
const mimeTypes = { ".html": "text/html", ".css": "text/css", ".mjs": "text/javascript" };
const quotas = [
  { id: "codex", name: "Codex", windows: [
    { id: "week", label: "Weekly", used: 100, reset: null },
    { id: "day", label: "Daily", used: 30, reset: null },
  ] },
  { id: "second", name: "Second", status: "Quota not reported", windows: [] },
];
const file = async (name) => readFile(new URL(name, assets), "utf8");
const layout = await file("floating.css");
let origin;
const server = createServer(async (request, response) => {
  if (request.url === "/") {
    const page = layout.replaceAll("__POKETCH_URL__", `${origin}/poketch/`);
    response.setHeader("Content-Type", "text/html");
    response.end(`<!doctype html>
      <style>
        webview { display: block; position: absolute }
        webview > iframe { display: block; width: 100%; height: 100%; border: 0 }
        ${page}
      </style>
      <main data-chat-canvas><section data-preview-mini-player="browser:sample"
        style="position:absolute;left:70px;top:30px;width:320px;height:170px">
        <div></div><div data-browser-surface-slot></div>
      </section></main>
      <div data-preview-viewport style="position:fixed;left:70px;top:30px;width:320px;height:170px;z-index: 48;">
        <div><div><webview src="${origin}/poketch/"><iframe src="/poketch/"></iframe></webview></div></div>
      </div>`);
  } else if (request.url === "/poketch/usage.json") {
    response.setHeader("Content-Type", "application/json");
    response.end(JSON.stringify(quotas));
  } else {
    const name = request.url.slice("/poketch/".length) || "index.html";
    const extension = name.slice(name.lastIndexOf("."));
    if (!["index.html", "panel.css", "panel.mjs", "model.mjs"].includes(name)) {
      response.writeHead(404).end();
      return;
    }
    response.setHeader("Content-Type", mimeTypes[extension]);
    response.end(await file(name));
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
origin = `http://127.0.0.1:${server.address().port}`;

const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1, `${actual} ≠ ${expected}`);
let browser;
try {
  browser = await chromium.launch({
    executablePath: process.env.SINNOH_CHROMIUM || undefined,
  });
  const page = await browser.newPage();
  for (const [label, width, height, deviceWidth] of [
    ["compact", 940, 640, 205.09],
    ["regular", 1100, 780, 240],
    ["enlarged", 1920, 1200, 320],
  ]) {
    await page.setViewportSize({ width, height });
    await page.goto(origin);
    const guest = page.frameLocator("iframe");
    const face = guest.getByRole("button", { name: /Weekly, 0% remaining/ });
    await face.waitFor();
    for (const locator of [page.locator("[data-preview-viewport]"), guest.locator(".housing")]) {
      const box = await locator.boundingBox();
      near(box.width, deviceWidth);
      near(box.height, deviceWidth * 126 / 240);
      near(width - box.x - box.width, 14);
      near(height - box.y - box.height, 90);
    }
    const previous = guest.getByRole("button", { name: "Previous provider" });
    const next = guest.getByRole("button", { name: "Next provider" });
    assert.ok((await previous.boundingBox()).width >= 24);
    await face.click();
    await guest.getByRole("button", { name: /Daily, 70% remaining/ }).waitFor();
    await next.click();
    await guest.getByRole("button", { name: /^Second, No quota window/ }).waitFor();
    await previous.click();
    await face.waitFor();
    console.log(`${label} ${width}×${height}: ${JSON.stringify(await guest.locator(".housing").boundingBox())}`);
    // Another site in the same native floating host must keep its original bounds.
    await page.locator("webview").evaluate((element) => element.setAttribute("src", "about:blank"));
    const other = await page.locator("[data-preview-viewport]").boundingBox();
    assert.deepEqual(other, { x: 70, y: 30, width: 320, height: 170 });
  }
} finally {
  await browser?.close();
  server.close();
}
