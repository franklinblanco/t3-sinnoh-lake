import { expired, remaining, selection, step } from "./model.mjs";

const ui = Object.fromEntries(
  ["previous", "next", "lcd", "name", "position", "percent", "meter", "old",
    "window", "pager", "reset", "announcement"].map((id) => [id, document.getElementById(id)]),
);
const providerKey = "sinnoh-poketch-provider";
let spec = {
  meterBars: 12,
  staleMinutes: 30,
  segments: [[2, 0, 12, 3], [13, 2, 3, 10], [13, 14, 3, 10], [2, 23, 12, 3],
    [0, 14, 3, 10], [0, 2, 3, 10], [2, 12, 12, 3]],
  digitMasks: [0x3f, 0x06, 0x5b, 0x4f, 0x66, 0x6d, 0x7d, 0x07, 0x7f, 0x6f],
};

let providers = [];
let providerId = localStorage.getItem(providerKey) ?? "codex";
let windowId;
let connected = true;

function digitElement(value) {
  const digit = document.createElement("span");
  digit.className = "digit";
  spec.segments.forEach(([x, y, width, height], index) => {
    if (spec.digitMasks[Number(value)] & (1 << index)) {
      const segment = document.createElement("i");
      Object.assign(segment.style, { left: `${x}px`, top: `${y}px`,
        width: `${width}px`, height: `${height}px` });
      digit.append(segment);
    }
  });
  return digit;
}

function drawRemaining(value) {
  if (value === null) {
    const dash = document.createElement("span");
    dash.className = "dash";
    ui.percent.replaceChildren(dash);
    ui.meter.hidden = true;
    return;
  }
  ui.percent.replaceChildren(...String(Math.round(value)).split("").map(digitElement), "%");
  const filled = Math.ceil(value * spec.meterBars / 100);
  ui.meter.replaceChildren(...Array.from({ length: spec.meterBars }, (_, index) => {
    const segment = document.createElement("i");
    segment.classList.toggle("filled", index < filled);
    return segment;
  }));
  ui.meter.hidden = false;
}

function resetText(window, provider, now) {
  if (!connected) return "Pokétch disconnected";
  if (!window) return provider?.status ?? "Awaiting T3 data";
  if (expired(window, now)) return "Awaiting reset update";
  if (window.reset === null) return "Reset not reported";
  const reset = new Date(window.reset);
  const format = { timeStyle: "short" };
  if (reset.toDateString() !== new Date(now).toDateString()) format.dateStyle = "short";
  return `Reset ${new Intl.DateTimeFormat(undefined, format).format(reset)}`;
}

function render(announce = false) {
  const now = Date.now();
  const { index, provider, order, window } = selection(providers, providerId, windowId, now);
  const value = connected ? remaining(window, now) : null;
  const old = value !== null && now - Date.parse(provider.checked) > spec.staleMinutes * 60 * 1000;
  const total = provider?.windows.length ?? 0;
  const name = provider?.name ?? "Providers";
  const label = window?.label ?? "No quota window";
  const reset = resetText(window, provider, now);
  const quota = value === null ? "Quota remaining unknown" : `${Math.round(value)}% remaining`;
  const description = [name, label, quota, reset, ...(old ? ["cached more than 30 minutes ago"] : [])]
    .join(", ");
  ui.name.textContent = name;
  ui.position.textContent = provider ? `${index + 1}/${providers.length}` : "";
  drawRemaining(value);
  ui.old.hidden = !old;
  ui.window.textContent = label;
  ui.pager.textContent = total > 1 ? `${order + 1}/${total} ›` : "";
  ui.reset.textContent = reset;
  ui.lcd.setAttribute("aria-label", description);
  ui.lcd.setAttribute("aria-disabled", String(total < 2));
  ui.lcd.title = total > 1 ? `${description}\nClick the LCD for the next quota window.` : description;
  for (const rocker of [ui.previous, ui.next]) {
    rocker.setAttribute("aria-disabled", String(providers.length < 2));
  }
  if (announce) ui.announcement.textContent = description;
}

function cycleProvider(direction) {
  if (providers.length < 2) return;
  const { index } = selection(providers, providerId, windowId, Date.now());
  providerId = providers[step(index, providers.length, direction)].id;
  windowId = undefined;
  localStorage.setItem(providerKey, providerId);
  render(true);
}

ui.previous.addEventListener("click", () => cycleProvider(-1));
ui.next.addEventListener("click", () => cycleProvider(1));
ui.lcd.addEventListener("click", () => {
  const { provider, order } = selection(providers, providerId, windowId, Date.now());
  if (!provider || provider.windows.length < 2) return;
  windowId = provider.windows[step(order, provider.windows.length, 1)].id;
  render(true);
});

async function loadSpec() {
  try {
    const response = await fetch("spec.json", { signal: AbortSignal.timeout(5000) });
    if (response.ok) spec = await response.json();
  } catch {
    // Keep inline defaults if spec.json is unavailable.
  }
}

async function refresh() {
  try {
    const response = await fetch("usage.json", {
      headers: { "X-Sinnoh-Panel": "1" },
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) throw new Error("Quota snapshot unavailable");
    providers = await response.json();
    if (providers.length && !providers.some((provider) => provider.id === providerId)) {
      providerId = providers[0].id;
      windowId = undefined;
    }
    connected = true;
  } catch {
    connected = false;
  }
  render();
  setTimeout(refresh, 10_000);
}

loadSpec().finally(refresh);
