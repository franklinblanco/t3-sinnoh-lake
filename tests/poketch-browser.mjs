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
    ignoreDefaultArgs: ["--hide-scrollbars"],
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
      "scroll-state", "if(style(",
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
      beforeOpacity: before.opacity,
      afterOpacity: after.opacity,
      beforeBg: before.backgroundImage,
      afterBg: after.backgroundImage,
      beforeContent: before.content,
      afterContent: after.content,
      afterPos: after.backgroundPosition,
    };
  });

  const initial = await housingStyle();
  assert.equal(initial.beforePointer, "none");
  assert.equal(initial.afterPointer, "none");
  assert.match(initial.beforeBg, /data:image\/svg\+xml/);
  assert.match(initial.afterBg, /data:image\/svg\+xml/);
  assert.match(initial.afterContent, /Codex, Weekly, 0% remaining/);

  // Clicks over the LCD pass straight through to underlying UI.
  await page.evaluate(() => {
    window.__asideClicks = 0;
    document.querySelector("aside").addEventListener("click", () => { window.__asideClicks += 1; });
  });
  await page.mouse.click(1100 - 14 - 120, 780 - 90 - 60);
  assert.equal(await page.evaluate(() => window.__asideClicks), 1);

  // Tabbing onto <meta> scroll controls + replacing/clearing adoptedStyleSheets never crashes Chromium.
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
  });
  const tabSequence = [];
  for (let i = 0; i < 6; i += 1) {
    await page.keyboard.press("Tab");
    const active = await page.evaluate(() => document.activeElement?.tagName ?? null);
    tabSequence.push(active);
    if (active === "META") {
      await page.evaluate((text) => {
        const sheet = document.adoptedStyleSheets[0];
        sheet.replaceSync("");
        void document.activeElement;
        sheet.replaceSync(text);
        void document.activeElement;
      }, css);
    }
    if (active === "BUTTON") break;
  }
  assert.equal(crashed, false);
  assert.ok(tabSequence.includes("TEXTAREA") && tabSequence.includes("BUTTON"), `Unexpected Tab sequence: ${tabSequence}`);

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

  // Clickable UP/DOWN red rocker buttons step through all 6 faces without stealing focus.
  await page.setViewportSize({ width: 1100, height: 780 });
  await page.locator("#draft").focus();
  const expectedFaces = [
    { pos: "0px 0px", text: "Codex, Weekly, 0% remaining" },
    { pos: "-186px 0px", text: "Codex, Daily, 70% remaining" },
    { pos: "-372px 0px", text: "Second, No quota window" },
    { pos: "-558px 0px", text: "Third, Weekly, 0% remaining" },
    { pos: "-744px 0px", text: "Third, Daily, 70% remaining" },
    { pos: "-930px 0px", text: "Third, Expired, Quota remaining unknown, Awaiting reset update" },
  ];
  const rockerBox = await page.evaluate(() => {
    const r = document.querySelector('meta[name="viewport"]').getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height };
  });
  near(rockerBox.width, 29);
  near(rockerBox.height, 89);

  await page.waitForTimeout(100);
  for (let i = 1; i < expectedFaces.length; i += 1) {
    await page.mouse.click(rockerBox.x + rockerBox.width / 2, rockerBox.y + rockerBox.height * 0.75);
    await page.waitForFunction(
      (expectedTop) => document.querySelector('meta[name="viewport"]').scrollTop === expectedTop,
      i * 40,
      { timeout: 2_000 },
    );
    const current = await housingStyle();
    assert.equal(current.afterPos, expectedFaces[i].pos);
    assert.ok(current.afterContent.includes(expectedFaces[i].text), `Down #${i}: ${current.afterContent}`);
    assert.equal(await page.evaluate(() => document.activeElement?.id), "draft");
    await page.waitForTimeout(60);
  }

  // Step back UP two faces.
  for (const target of [4, 3]) {
    await page.mouse.click(rockerBox.x + rockerBox.width / 2, rockerBox.y + rockerBox.height * 0.25);
    await page.waitForFunction(
      (expectedTop) => document.querySelector('meta[name="viewport"]').scrollTop === expectedTop,
      target * 40,
      { timeout: 2_000 },
    );
    const current = await housingStyle();
    assert.equal(current.afterPos, expectedFaces[target].pos);
    assert.ok(current.afterContent.includes(expectedFaces[target].text), `Up -> ${target}: ${current.afterContent}`);
    assert.equal(await page.evaluate(() => document.activeElement?.id), "draft");
    await page.waitForTimeout(60);
  }

  // Clickable collapse ("-") and expand (mini Pokétch) toggle preserves selected face and focus.
  await page.waitForTimeout(150);
  const hideBox = await page.evaluate(() => {
    const r = document.querySelector("meta[charset]").getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height };
  });
  await page.mouse.click(hideBox.x + hideBox.width / 2, hideBox.y + hideBox.height / 2);
  await page.waitForFunction(
    () => document.querySelector("meta[charset]").scrollTop === 40,
    null,
    { timeout: 2_000 },
  );
  assert.equal((await housingStyle()).beforeOpacity, "0");
  const miniBox = await page.evaluate(() => {
    const r = document.querySelector("meta[charset]").getBoundingClientRect();
    return {
      x: r.x,
      y: r.y,
      width: r.width,
      height: r.height,
      rockerVis: getComputedStyle(document.querySelector('meta[name="viewport"]')).visibility,
      active: document.activeElement?.id,
    };
  });
  near(miniBox.width, 44);
  near(miniBox.height, 24);
  assert.equal(miniBox.rockerVis, "hidden");
  assert.equal(miniBox.active, "draft");

  // Live CSS refresh while collapsed keeps collapsed state + face, and clearing/restoring never crashes.
  const sheetLifecycle = await page.evaluate(({ singleCss, updatedCss, fullCss }) => {
    const sheet = document.adoptedStyleSheets[0];
    const log = [];
    sheet.replaceSync(updatedCss);
    const afterUpdate = {
      opacity: getComputedStyle(document.documentElement, "::before").opacity,
      pos: getComputedStyle(document.documentElement, "::after").backgroundPosition,
      active: document.activeElement?.id,
    };
    sheet.replaceSync("");
    log.push(document.activeElement?.id ?? null);
    sheet.replaceSync(singleCss);
    const singleRockerDisplay = getComputedStyle(document.querySelector('meta[name="viewport"]')).display;
    const singleContent = getComputedStyle(document.documentElement, "::after").content;
    log.push(document.activeElement?.id ?? null);
    sheet.replaceSync(fullCss);
    log.push(document.activeElement?.id ?? null);
    return { log, afterUpdate, singleRockerDisplay, singleContent };
  }, {
    singleCss,
    updatedCss: css.replaceAll("70% remaining", "69% remaining"),
    fullCss: css,
  });
  assert.equal(crashed, false);
  assert.equal(sheetLifecycle.afterUpdate.opacity, "0");
  assert.equal(sheetLifecycle.afterUpdate.pos, expectedFaces[3].pos);
  assert.equal(sheetLifecycle.afterUpdate.active, "draft");
  assert.deepEqual(sheetLifecycle.log, ["draft", "draft", "draft"]);
  assert.equal(sheetLifecycle.singleRockerDisplay, "none");
  assert.match(sheetLifecycle.singleContent, /Providers, No quota window, Quota remaining unknown/);

  // Expand back from the preserved collapsed state via mini Pokétch badge click.
  await page.waitForTimeout(150);
  await page.mouse.click(miniBox.x + miniBox.width / 2, miniBox.y + miniBox.height / 2);
  await page.waitForFunction(
    () => document.querySelector("meta[charset]").scrollTop === 0,
    null,
    { timeout: 2_000 },
  );
  const expanded = await housingStyle();
  assert.equal(expanded.beforeOpacity, "1");
  assert.equal(expanded.afterPos, expectedFaces[3].pos);
  assert.equal(await page.evaluate(() => document.activeElement?.id), "draft");

  // Legacy floating Browser suppression and independence from optional <head> tags.
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
  console.log("Renderer-wide panel: clickable rocker + collapse, LCD pass-through, Tab/focus safety, adoptedStyleSheets replaceSync stability, scale, inert and legacy scope");
}
