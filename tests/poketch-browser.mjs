import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
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
  await verifyGlobal(page);
} finally {
  await browser?.close();
  server.close();
}

async function verifyGlobal(page) {
  const css = execFileSync(process.env.SINNOH_PYTHON || "python3", ["-c", `
import json
import sys
from pathlib import Path
from unittest.mock import patch

from sinnoh.poketch_theme import styles
from sinnoh.usage import Provider, Window, iso_date

providers = [
    Provider(p["id"], p["name"],
             tuple(Window(w["id"], w["label"], w["used"], iso_date(w["reset"])) for w in p["windows"]),
             p.get("status", ""), None)
    for p in json.load(sys.stdin)
]
with patch("sinnoh.poketch_theme.read_providers", return_value=providers):
    print(styles(Path("."), 47984))
`], {
    cwd: new URL("../", import.meta.url),
    input: JSON.stringify([...quotas, {
      ...quotas[0],
      id: "third",
      name: "Third",
      windows: [...quotas[0].windows, { id: "expired", label: "Expired", used: 15, reset: "2000-01-01T00:00:00Z" }],
    }]),
    encoding: "utf8",
  });
  await page.goto("about:blank");
  await page.setViewportSize({ width: 1100, height: 780 });
  await page.setContent(`<!doctype html>
    <html>
      <head>
        <meta charset="utf-8"><meta name="viewport" content="width=device-width">
        <meta name="theme-color" content="#000000"><link rel="apple-touch-icon" href="data:,">
        <title>T3 Code</title>
      </head>
      <body>
        <main data-slot="sidebar-inset">
          <div data-chat-canvas data-route="local"><textarea></textarea></div>
        </main>
      </body>
    </html>`);
  await page.evaluate((css) => {
    const theme = new CSSStyleSheet();
    theme.replaceSync(css);
    document.adoptedStyleSheets = [theme];
  }, css);
  const readout = () => page.evaluate(() => getComputedStyle(document.documentElement, "::after").content);
  const waitForReadout = (text) => page.waitForFunction(
    (text) => getComputedStyle(document.documentElement, "::after").content.includes(text),
    text, { timeout: 4_000 },
  );
  const click = async (control, expected) => {
    // Click native generated buttons or the marker at the same point on wrap.
    const { width, height } = page.viewportSize();
    const size = await page.evaluate(
      () => parseFloat(getComputedStyle(document.documentElement, "::before").width),
    );
    const scale = size / 240;
    const [x, y] = { previous: [222, 40], next: [222, 85], lcd: [106, 63] }[control];
    await page.mouse.click(width - 14 - (240 - x) * scale, height - 90 - (126 - y) * scale);
    await waitForReadout(expected);
  };
  assert.match(await readout(), /Codex, Weekly, 0% remaining/);
  await page.locator("textarea").fill("Unsent draft");
  await click("lcd", "Codex, Daily, 70% remaining");
  await click("lcd", "Codex, Weekly, 0% remaining");
  await click("previous", "Third, Weekly, 0% remaining");
  await click("lcd", "Third, Daily, 70% remaining");
  await click("lcd", "Third, Expired, Quota remaining unknown, Awaiting reset update");
  await click("lcd", "Third, Weekly, 0% remaining");
  await click("lcd", "Third, Daily, 70% remaining");
  await click("next", "Codex, Weekly, 0% remaining");
  await click("next", "Second, No quota window");
  await click("next", "Third, Weekly, 0% remaining");
  assert.equal(await page.locator("textarea").inputValue(), "Unsent draft");

  for (const route of ["remote", "draft", "local"]) {
    const result = await page.evaluate((route) => {
      const region = document.querySelector("[data-slot=sidebar-inset]");
      const canvas = document.createElement("div");
      canvas.dataset.chatCanvas = "";
      canvas.dataset.route = route;
      region.replaceChildren(canvas);
      return getComputedStyle(document.documentElement, "::after").content;
    }, route);
    assert.match(result, /Third, Weekly, 0% remaining/);
  }
  await page.locator("main").evaluate((element) => { element.inert = true; });
  assert.equal(await readout(), "none");
  await page.locator("main").evaluate((element) => { element.inert = false; });
  assert.match(await readout(), /Third, Weekly, 0% remaining/);

  for (const [width, height, deviceWidth] of [[940, 640, 205.09], [1100, 780, 240], [1920, 1200, 320]]) {
    await page.setViewportSize({ width, height });
    const box = await page.evaluate(() => {
      const { width, height, right, bottom } = getComputedStyle(document.documentElement, "::before");
      return [width, height, right, bottom].map(parseFloat);
    });
    [deviceWidth, deviceWidth * 126 / 240, 14, 90].forEach((expected, index) => near(box[index], expected));
    assert.match(await readout(), /Third, Weekly, 0% remaining/);
  }
  await click("lcd", "Third, Daily, 70% remaining");
  await page.evaluate((css) => {
    document.adoptedStyleSheets[0].replaceSync(css.replaceAll("70% remaining", "69% remaining"));
  }, css);
  await waitForReadout("Third, Daily, 69% remaining");

  const migration = await page.evaluate(() => {
    const canvas = document.querySelector("[data-chat-canvas]");
    canvas.innerHTML = '<section data-preview-mini-player="browser:legacy">Old panel</section>';
    const shell = canvas.firstChild;
    const surface = (id, url, layer) => {
      const viewport = document.createElement("div");
      viewport.dataset.previewViewport = id;
      viewport.style.zIndex = layer;
      viewport.innerHTML = `<webview src="${url}"></webview>`;
      document.body.append(viewport);
      return viewport;
    };
    const url = "http://127.0.0.1:47984/poketch/";
    const floating = surface("legacy", url, 48);
    const docked = surface("docked", url, 30);
    const hidden = [getComputedStyle(shell).visibility, getComputedStyle(floating).opacity];
    floating.firstChild.setAttribute("src", "about:blank");
    const unrelated = [getComputedStyle(shell).visibility, getComputedStyle(floating).opacity,
      getComputedStyle(docked).opacity];
    return { hidden, unrelated };
  });
  assert.deepEqual(migration, { hidden: ["hidden", "0"], unrelated: ["visible", "1", "1"] });
  console.log("Renderer-wide panel: instant routes, native wrapping, scale, draft and legacy scope");
}
