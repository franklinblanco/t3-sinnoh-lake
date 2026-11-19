import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";

const { chromium } = createRequire(import.meta.url)("playwright-core");
const assets = new URL("../assets/poketch/", import.meta.url);
const mimeTypes = { ".html": "text/html", ".css": "text/css", ".mjs": "text/javascript", ".json": "application/json" };
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
    if (!["index.html", "panel.css", "panel.mjs", "model.mjs", "spec.json"].includes(name)) {
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
  const generateCss = (providersJson) => execFileSync(process.env.SINNOH_PYTHON || "python3", ["-c", `
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
    input: JSON.stringify(providersJson),
    encoding: "utf8",
  });

  const multiProviders = [...quotas, {
    ...quotas[0],
    id: "third",
    name: "Third",
    windows: [...quotas[0].windows, { id: "expired", label: "Expired", used: 15, reset: "2000-01-01T00:00:00Z" }],
  }];
  const css = generateCss(multiProviders);
  const singleCss = generateCss([]);

  for (const stylesheet of [css, singleCss]) {
    for (const forbidden of [
      "scroll-marker", "scroll-marker-group", "scroll-button",
      "scroll-timeline", "timeline-scope", "scroll-state",
      "if(style(", "> head", "head >", "head::",
    ]) {
      assert.equal(stylesheet.includes(forbidden), false, `Forbidden token found: ${forbidden}`);
    }
  }

  let crashed = false;
  page.on("crash", () => { crashed = true; });

  await page.goto("about:blank");
  await page.setViewportSize({ width: 1100, height: 780 });
  await page.setContent(`<!doctype html>
    <html>
      <head>
        <meta charset="utf-8"><meta name="viewport" content="width=device-width">
        <meta name="theme-color" content="#000000"><link rel="icon" href="data:,">
        <link rel="apple-touch-icon" href="data:,"><title>T3 Code</title>
      </head>
      <body>
        <main data-slot="sidebar-inset" style="position:relative;z-index:0;min-height:100vh">
          <div data-chat-canvas data-route="local">
            <textarea id="draft"></textarea>
            <button id="send" type="button">Send</button>
          </div>
        </main>
        <aside aria-label="Other floating preview"
          style="position:fixed;right:0;bottom:0;width:320px;height:230px;z-index:48"></aside>
      </body>
    </html>`);

  await page.evaluate((css) => {
    const theme = new CSSStyleSheet();
    theme.replaceSync(css);
    document.adoptedStyleSheets = [theme];
  }, css);

  const readout = () => page.evaluate(() => getComputedStyle(document.documentElement, "::after").content);
  const housingStyle = () => page.evaluate(() => {
    const before = getComputedStyle(document.documentElement, "::before");
    const after = getComputedStyle(document.documentElement, "::after");
    return {
      beforePointer: before.pointerEvents,
      afterPointer: after.pointerEvents,
      beforeBg: before.backgroundImage,
      afterBg: after.backgroundImage,
      beforeContent: before.content,
      afterContent: after.content,
    };
  });

  const initial = await housingStyle();
  assert.equal(initial.beforePointer, "none");
  assert.equal(initial.afterPointer, "none");
  assert.match(initial.beforeBg, /data:image\/svg\+xml/);
  assert.match(initial.afterBg, /data:image\/svg\+xml/);
  assert.match(initial.afterContent, /Codex, Weekly, 0% remaining/);

  // Clicks over the Pokétch pass straight through to underlying UI.
  await page.evaluate(() => {
    window.__asideClicks = 0;
    document.querySelector("aside").addEventListener("click", () => { window.__asideClicks += 1; });
  });
  await page.mouse.click(1100 - 14 - 120, 780 - 90 - 60);
  assert.equal(await page.evaluate(() => window.__asideClicks), 1);

  // Pressing Tab never focuses <head> or its metadata children.
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
  });
  const tabSequence = [];
  for (let i = 0; i < 4; i += 1) {
    await page.keyboard.press("Tab");
    const active = await page.evaluate(() => document.activeElement?.tagName ?? null);
    assert.ok(!["HEAD", "META", "TITLE", "LINK"].includes(active), `Unexpected head focus: ${active}`);
    tabSequence.push(active);
    if (active === "BUTTON") break;
  }
  assert.deepEqual(tabSequence.filter((tag) => tag !== "BODY"), ["TEXTAREA", "BUTTON"]);

  await page.locator("#draft").fill("Unsent draft");

  // Renders across chat routes and hides when sidebar-inset is inert.
  for (const route of ["remote", "draft", "local"]) {
    const result = await page.evaluate((route) => {
      const region = document.querySelector("[data-slot=sidebar-inset]");
      const canvas = document.createElement("div");
      canvas.dataset.chatCanvas = "";
      canvas.dataset.route = route;
      canvas.innerHTML = '<textarea id="draft"></textarea><button id="send" type="button">Send</button>';
      region.replaceChildren(canvas);
      return getComputedStyle(document.documentElement, "::after").content;
    }, route);
    assert.match(result, /Codex, Weekly, 0% remaining/);
  }
  await page.locator("main").evaluate((element) => { element.inert = true; });
  assert.equal(await readout(), "none");
  assert.equal((await housingStyle()).beforeContent, "none");
  await page.locator("main").evaluate((element) => { element.inert = false; });
  assert.match(await readout(), /Codex, Weekly, 0% remaining/);

  // Responsive scaling across compact, regular, and enlarged viewports.
  for (const [width, height, deviceWidth] of [[940, 640, 205.09], [1100, 780, 240], [1920, 1200, 320]]) {
    await page.setViewportSize({ width, height });
    const box = await page.evaluate(() => {
      const { width, height, right, bottom } = getComputedStyle(document.documentElement, "::before");
      return [width, height, right, bottom].map(parseFloat);
    });
    [deviceWidth, deviceWidth * 126 / 240, 14, 90].forEach((expected, index) => near(box[index], expected));
  }

  // Auto-cycling across all 6 faces via @keyframes steps(1, end).
  await page.setViewportSize({ width: 1100, height: 780 });
  const expectedFaces = [
    { pos: "0px 0px", text: "Codex, Weekly, 0% remaining" },
    { pos: "-186px 0px", text: "Codex, Daily, 70% remaining" },
    { pos: "-372px 0px", text: "Second, No quota window" },
    { pos: "-558px 0px", text: "Third, Weekly, 0% remaining" },
    { pos: "-744px 0px", text: "Third, Daily, 70% remaining" },
    { pos: "-930px 0px", text: "Third, Expired, Quota remaining unknown, Awaiting reset update" },
  ];
  const cycleFrames = await page.evaluate((count) => {
    const anim = document.getAnimations().find((a) => a.animationName === "sinnoh-cycle");
    if (!anim) return null;
    const timing = anim.effect.getTiming();
    const timingFn = getComputedStyle(document.documentElement, "::after").animationTimingFunction;
    anim.pause();
    const samples = [];
    for (let i = 0; i < count; i += 1) {
      anim.currentTime = (i + 0.5) * 5000;
      const cs = getComputedStyle(document.documentElement, "::after");
      samples.push({ pos: cs.backgroundPosition, content: cs.content });
    }
    return { duration: timing.duration, timingFn, samples };
  }, expectedFaces.length);
  assert.ok(cycleFrames, "Expected sinnoh-cycle animation");
  assert.equal(cycleFrames.duration, expectedFaces.length * 5000);
  assert.match(cycleFrames.timingFn, /^steps\(1(, end)?\)$/);
  expectedFaces.forEach((expected, index) => {
    assert.equal(cycleFrames.samples[index].pos, expected.pos);
    assert.ok(cycleFrames.samples[index].content.includes(expected.text),
      `Face ${index}: ${cycleFrames.samples[index].content}`);
  });

  // Verify real-time playback advances from face 0 to face 1 automatically.
  await page.evaluate(() => {
    const anim = document.getAnimations().find((a) => a.animationName === "sinnoh-cycle");
    anim.currentTime = 0;
    anim.playbackRate = 25;
    anim.play();
  });
  await page.waitForFunction(
    () => getComputedStyle(document.documentElement, "::after").content.includes("Codex, Daily, 70% remaining"),
    null,
    { timeout: 4_000 },
  );

  // Clearing and replacing adoptedStyleSheets + reading document.activeElement never crashes.
  await page.locator("#draft").focus();
  const sheetLifecycle = await page.evaluate(({ singleCss, updatedCss, fullCss }) => {
    const sheet = document.adoptedStyleSheets[0];
    const log = [];
    sheet.replaceSync("");
    log.push(document.activeElement?.tagName ?? null);
    sheet.replaceSync(singleCss);
    const singleAnim = getComputedStyle(document.documentElement, "::after").animationName;
    const singleContent = getComputedStyle(document.documentElement, "::after").content;
    log.push(document.activeElement?.tagName ?? null);
    sheet.replaceSync(updatedCss);
    const updatedContent = getComputedStyle(document.documentElement, "::after").content;
    log.push(document.activeElement?.tagName ?? null);
    sheet.replaceSync("");
    log.push(document.activeElement?.tagName ?? null);
    sheet.replaceSync(fullCss);
    log.push(document.activeElement?.tagName ?? null);
    return { log, singleAnim, singleContent, updatedContent };
  }, {
    singleCss,
    updatedCss: css.replaceAll("70% remaining", "69% remaining"),
    fullCss: css,
  });
  assert.equal(crashed, false);
  assert.deepEqual(sheetLifecycle.log, ["TEXTAREA", "TEXTAREA", "TEXTAREA", "TEXTAREA", "TEXTAREA"]);
  assert.equal(sheetLifecycle.singleAnim, "none");
  assert.match(sheetLifecycle.singleContent, /Providers, No quota window, Quota remaining unknown/);
  assert.match(sheetLifecycle.updatedContent, /Codex, Weekly, 0% remaining/);

  // Legacy floating Browser suppression and independence from <head> metadata tags.
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
    floating.firstChild.setAttribute("src", url);
    document.head.querySelector('link[rel="apple-touch-icon"]').remove();
    const stillActive = [getComputedStyle(document.documentElement, "::after").content !== "none",
      getComputedStyle(floating).opacity];
    return { hidden, unrelated, stillActive };
  });
  assert.deepEqual(migration, {
    hidden: ["hidden", "0"],
    unrelated: ["visible", "1", "1"],
    stillActive: [true, "0"],
  });
  assert.equal(crashed, false);
  console.log("Renderer-wide panel: auto-cycling faces, pass-through clicks, Tab safety, adoptedStyleSheets replaceSync stability, scale, inert and legacy scope");
}
