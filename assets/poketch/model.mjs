export function selection(providers, providerId, windowId, now) {
  const found = providers.findIndex((provider) => provider.id === providerId);
  const index = Math.max(0, found);
  const provider = providers[index];
  const windows = provider?.windows ?? [];
  let order = found < 0 ? -1 : windows.findIndex((window) => window.id === windowId);
  if (order < 0) {
    let tightest = -1;
    order = 0;
    windows.forEach((window, candidate) => {
      if (window.used !== null && !expired(window, now) && window.used > tightest) {
        tightest = window.used;
        order = candidate;
      }
    });
  }
  return { index, provider, order, window: windows[order] };
}

export function expired(window, now) {
  return window.reset !== null && Date.parse(window.reset) <= now;
}

export function remaining(window, now) {
  return window && window.used !== null && !expired(window, now) ? 100 - window.used : null;
}

export function step(index, count, direction) {
  return (index + direction + count) % count;
}
