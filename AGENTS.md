# AGENTS.md

Guidance for agents working in `t3-sinnoh-lake`.

## Overview

`t3-sinnoh-lake` provides the **Sinnoh Rift · Lake Life** animated T3 Code theme, a local solar-phase switcher, a composer context-usage meter (including linked T3 environments), and the in-chat + loopback **Pokétch** quota monitor across macOS, Linux, and Windows.

### Repository layout

- `install.py` — Cross-platform installer (Python 3.11–3.14). Creates `<app_dir>/.venv`, installs `requirements.txt`, syncs `sinnoh/`, `assets/phases/`, `assets/poketch/`, and `launch.py` via `copy_tree()` (pruning stale files and `._*` AppleDouble artifacts), installs/upgrades theme JSONs under `<t3_home>/userdata/themes/` without clobbering user CSS, runs `sinnoh.solar`, and registers/restarts the background worker.
- `launch.py` — Installed background worker entrypoint; logs to `<app_dir>/monitor.log` and calls `sinnoh.panel.serve()`.
- `sinnoh/` — Runtime Python package:
  - `panel.py` — Loopback HTTP server (`127.0.0.1:47984/poketch/`) and 10 s polling `clock` thread that updates theme CSS on change and runs `solar.sync()` at least every 60 s.
  - `poketch_theme.py` — Renders provider quota snapshots into a 1D SVG sprite and substitutes `assets/poketch/global.css`.
  - `usage.py` — Read-only parser for `<t3_home>/userdata/settings.json` and `<t3_home>/caches/*.json` (ignores `acp-auth-*.json` probes).
  - `context_meter.py` & `remote_context.py` — Generates composer context-usage CSS from local `statev2.sqlite` (read-only URI) and T3 Desktop's Chromium IndexedDB LevelDB cache for linked machines.
  - `solar.py` — Maps local timezone (`tzlocal` + `tzdata`) solar elevation (`astral`) to 18 phases (`day`, `night`, `rise1`–`rise8`, `set1`–`set8`) and atomically publishes `sinnoh-lake-life.webp`.
  - `startup.py` — Per-user service registration and safe ownership verification:
    - **macOS:** LaunchAgent (`local.t3code.sinnoh-lake-panel`), archiving legacy overlay/clock plists to `legacy/`.
    - **Linux:** `systemd --user` service (`t3-sinnoh-lake.service`, `Restart=on-failure`) so the worker runs outside the caller's shell/agent cgroup, archiving owned legacy XDG autostart `.desktop` entries; falls back to XDG autostart when `systemd --user` is unavailable.
    - **Windows:** Per-user Scheduled Task (`\T3 Sinnoh Lake`) running `pythonw.exe`, verified by user SID and action before replacing.
  - `paths.py` — `ASSETS`, `THEME_ID` (`sinnoh-lake-life`), `t3_home()`, and `atomic_write()`.
- `assets/` — Theme definitions (`sinnoh-lake-life.json`, `sinnoh-rift.json`), static background (`sinnoh-rift.png`), 18 prebuilt animated WebP loops (`phases/*.webp`), and Pokétch assets (`poketch/`).
- `artwork/` — Offline phase generator (`build.py`, `cruise.py`, `sprites/`, `requirements.txt`). Not installed or required at runtime.
- `tests/` — Python `unittest` suite (`test_sinnoh.py`, `test_panel.py`, `test_remote_context.py`), Node model tests (`poketch.test.mjs`), and Playwright Chromium layout/interaction checks (`poketch-browser.mjs`).

## Key invariants and pitfalls

### T3 theme CSS constraints
- **100 KB hard limit:** T3 caps theme CSS at `100_000` bytes (`LIMIT` in `sinnoh/context_meter.py`). Keep `METER_BUDGET` (`24_000` bytes) and `MAX_THREADS` (`40`) bounded so Pokétch CSS fits comfortably and `:root:has()` selector counts stay fast.
- **No backslashes in theme CSS:** T3 rejects `\` in theme CSS values. Avoid backslashes in `assets/sinnoh-*.json`, `assets/poketch/global.css`, and generated strings in `sinnoh/poketch_theme.py` (use typographic characters or percent-encoded data URIs).
- **Avoid crashing Chromium CSS pseudo-elements:** Never introduce `::scroll-marker`, `::scroll-marker-group`, `::scroll-button()`, `scroll-state`, or `if(style(...))` into `global.css` — they crash Electron/Chromium renderers. Keep in-chat controls on non-focusable `::-webkit-scrollbar-button` steppers + `scroll-timeline`, and keep `::-webkit-scrollbar*` rules free of `:has()`.
- **Preserve user CSS:** Managed blocks are strictly delimited by `/* Sinnoh floating Pokétch */ ... /* End Sinnoh floating Pokétch */` and `/* Sinnoh context meter */ ... /* End Sinnoh context meter */`. Base theme upgrades in `install.py` (`upgrade_theme_css`) must be narrow and idempotent.
- **Keep empty/draft screens transparent:** T3 renders `[data-timeline-loading]` with an opaque background inside `[data-workspace-area="conversation"]` on new/draft threads and loading states. Keep both `.messages-timeline-scroll` and `[data-workspace-area="conversation"] [data-timeline-loading]` set to `background-color: transparent !important`.
- **Single source of truth for Pokétch geometry:** Share dimensions, bar counts, stale threshold, and 7-segment masks through `assets/poketch/spec.json` between `sinnoh/poketch_theme.py` and `assets/poketch/panel.mjs`.

### Read-only T3 integration, atomicity, and security
- **Never mutate T3 state:** Only read `<t3_home>/userdata/settings.json`, `<t3_home>/caches/*.json`, `statev2.sqlite` (`?mode=ro`), and Chromium's IndexedDB store. Only write theme files under `<t3_home>/userdata/themes/` and our own index cache under `<t3_home>/caches/sinnoh-lake/`.
- **Atomic writes:** Use `sinnoh.paths.atomic_write()` for files watched by T3 so the file watcher sees complete inodes.
- **Loopback panel hardening:** Keep `PanelServer` bound to `127.0.0.1` with strict `Host` validation, `Sec-Fetch-Site: same-origin` + `X-Sinnoh-Panel: 1` on `/poketch/usage.json`, no CORS headers, `frame-ancestors 'none'` CSP, and explicit field projection in `quota_snapshot()`. Never expose or log raw provider auth/cache records.
- **Ownership checks in `startup.py`:** Never stop, delete, or overwrite a LaunchAgent, systemd unit, XDG autostart file, Windows Scheduled Task, or running process unless its definition/command matches the installed launcher owned by the current user.
- **Minimal runtime dependencies:** The desktop installer must not require Node or Pillow. If you add new runtime asset subdirectories, copy them explicitly in `install.py`.

## Testing and verification

CI (`.github/workflows/checks.yml`) runs on Ubuntu, Windows, and macOS (Python 3.12, Node 22):

```bash
# Python suite (needs requirements.txt + Pillow==13.0.0)
python -m unittest discover -s tests -v

# Standalone Pokétch model tests
node --test tests/poketch.test.mjs

# Chromium layout/interaction test (run whenever changing Pokétch CSS/UI)
node tests/poketch-browser.mjs
```

### Local install & smoke check
After code or theme changes, reinstall without switching the user's active theme:

```bash
# macOS / Linux
python3 install.py --keep-theme

# Windows
py -3.12 install.py --keep-theme
```

Verify the worker is running and updating:
- **Linux:** `systemctl --user status t3-sinnoh-lake.service` (or check `<app_dir>/monitor.log` if falling back to XDG autostart).
- **macOS:** `launchctl print "gui/$(id -u)/local.t3code.sinnoh-lake-panel"` and check `~/Library/Application Support/T3 Sinnoh Lake/monitor.log`.
- **All platforms:** `http://127.0.0.1:47984/poketch/` responds with `200` and header `X-Sinnoh-Lake: poketch`, and `<t3_home>/userdata/themes/sinnoh-lake-life.json` reflects current provider cache values.

### Rebuilding artwork
Install `artwork/requirements.txt` and run `python artwork/build.py <phase>`. All 18 phases in `assets/phases/` must pass `SolarTest` in `tests/test_sinnoh.py` (`1672×941`, `< 16 MB`, 240 frames, `loop == 0`, autumn palette checks, and motion/static region bounds).

## Git and cross-machine updates

- Leave unrelated untracked local workspace files (for example `t3.json` or `assets/icon.png` if present locally) unstaged unless explicitly asked.
- Commit and push changes to `origin/main` before updating other machines so each machine stays on a clean checkout (`git pull --ff-only` followed by `python3 install.py --keep-theme`).
