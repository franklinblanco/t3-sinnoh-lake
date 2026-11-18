import assert from "node:assert/strict";
import test from "node:test";
import { expired, remaining, selection, step } from "../assets/poketch/model.mjs";

const now = Date.parse("2026-11-18T12:00:00Z");
const past = "2026-11-18T11:00:00+00:00";
const future = "2026-11-18T13:00:00+00:00";
const providers = [
  { id: "codex", windows: [
    { id: "expired", used: 100, reset: past },
    { id: "day", used: 50, reset: future },
    { id: "week", used: 100, reset: future },
    { id: "unknown", used: null, reset: null },
  ] },
  { id: "second", windows: [] },
  { id: "third", windows: [{ id: "day", used: 30, reset: null }] },
];

test("initial LCD selection is the tightest current quota, including zero remaining", () => {
  const { window } = selection(providers, "codex", undefined, now);
  assert.equal(window.id, "week");
  assert.equal(remaining(window, now), 0);
  assert.equal(remaining(window, Date.parse(future)), null);
  assert.equal(expired(window, Date.parse(future)), true);
});

test("LCD clicks wrap through all windows including unknown and expired quota", () => {
  let id;
  const readings = {};
  for (let index = 0; index < 4; index += 1) {
    const { provider, order, window } = selection(providers, "codex", id, now);
    readings[window.id] = remaining(window, now);
    id = provider.windows[step(order, provider.windows.length, 1)].id;
  }
  assert.deepEqual(readings, { week: 0, unknown: null, expired: null, day: 50 });
  assert.equal(id, "week");
});

test("rockers wrap both ways and the model tolerates a removed provider or window", () => {
  const expected = ["codex", "second", "third", "codex"];
  let index = 0;
  for (const id of expected) {
    assert.equal(providers[index].id, id);
    index = step(index, providers.length, 1);
  }
  assert.equal(providers[step(0, providers.length, -1)].id, "third");
  assert.equal(selection(providers, "removed", "unknown", now).window.id, "week");
  assert.equal(selection(providers, "second", undefined, now).window, undefined);
  assert.equal(selection([], "codex", undefined, now).provider, undefined);
});
