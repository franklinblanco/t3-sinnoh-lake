# T3 Sinnoh Lake

Sinnoh Rift · Lake Life brings an animated pixel-art lake to the T3 Code conversation pane. The artwork includes submerged Magikarp, Buizel and Finneon. Starly, Staravia and Staraptor fly in formation while Wingull, Zubat and Drifloon follow their own paths. Turtwig, Chimchar and Piplup cruise past in a wooden boat. Pokétch is a green LCD quota monitor that floats over the conversation inside T3 Desktop.

## Install

Use Python 3.11–3.14 with `venv`, `pip` and Git. Run the installer as the signed-in desktop user with T3 Code open. On an existing setup, pass `--keep-theme` to preserve the selected theme.

| Desktop | Install command | Startup and migration |
| --- | --- | --- |
| Windows 10/11 | `py -3.12 install.py --keep-theme` | Task Scheduler runs the background worker in the current user’s interactive session. The installer verifies the owner and action of the existing **T3 Sinnoh Lake** task before restarting it with the new launcher. |
| Linux | `python3 install.py --keep-theme` | The existing XDG autostart entry is reused. The installer stops the previous process matching the installed launcher and starts the background worker. The same panel works on X11 and Wayland. |
| macOS | `python3 install.py --keep-theme` | A per-user LaunchAgent starts the background worker. Once it responds, the installer stops the old clock and floating overlay jobs and archives their plists under the install directory’s `legacy/`. The old bundle stays on disk for rollback. |

On a fresh install, omit `--keep-theme` to select **Sinnoh Rift · Lake Life** through `t3 theme set`. If the CLI is unavailable, select it in **Settings → Appearance**. The static **Sinnoh Rift** variant is also available. Existing theme definitions and custom CSS are kept.

The default T3 data directory is `~/.t3`. Set `T3CODE_HOME` or pass `--t3-home PATH` for a custom directory. The installer prints the panel URL. If the default port is occupied, pass `--port PORT` and use the printed URL.

## Open Pokétch

1. In a thread on your local T3 environment, open the **right panel**.
2. Choose **Browser**, or use **+ → Browser** if the right panel already has tabs.
3. Enter `http://127.0.0.1:47984/poketch/` in the Browser address bar.
4. Select **Float preview over chat** in the Browser toolbar. Select **Sinnoh Rift · Lake Life** to apply Pokétch’s placement and sizing.

Pokétch floats 14 px from the right edge and 90 px from the bottom of the T3 viewport. Its reference size is 240 × 126 px at T3’s default window size. The whole device scales down in compact windows and up in larger ones.

The floating Browser belongs to the thread. Open and float it in each thread where you want it, and reopen it if T3 clears the tab after a restart. Minimizing or closing the T3 window hides the monitor with it. The background worker continues to update the theme.

This uses T3’s stock floating Browser and a small set of theme rules for its placement and size. Tested in T3 Nightly `0.1.11-nightly.20261118.4890`. An interactive global widget would need a renderer extension point. The proposed plugin host was closed without merging. [T3 Browser documentation](https://github.com/pingdotgg/t3code/blob/8cf97b5f06f30a872ce30ab8a888f2ff012365a2/docs/user/remote-access.md#browser-on-a-remote-environment) · [Theme CSS documentation](https://github.com/pingdotgg/t3code/blob/8cf97b5f06f30a872ce30ab8a888f2ff012365a2/docs/user/appearance.md#custom-css) · [Plugin proposal](https://github.com/pingdotgg/t3code/pull/33606)

The worker binds to IPv4 loopback and serves only the panel and its read-only quota snapshot. It reads the provider instance configuration and cached quota fields on this machine. T3’s Browser can share tabs with paired T3 clients through its normal environment access.

## Quota, context and local time

- Press the upper or lower red rocker to cycle through every configured provider instance and any enabled built-ins present in T3’s cache.
- **LEFT** and the meter show remaining quota. The LCD starts on the tightest valid quota window for the selected provider. Click the LCD to cycle all reported windows. Reset times use the desktop’s locale and time zone.
- Expired quota values are hidden until T3 reports a new snapshot. Selecting an expired window shows **Awaiting reset update**. Unknown quota shows a dash. A valid exhausted window shows **0%** and an empty meter.
- Hover over the ring to the left of the composer’s model picker for the thread’s context percentage. Linked machines use the latest reading T3 Desktop received, including last-known data when a machine goes offline. The theme prioritizes recent and active threads within T3’s stylesheet size limit.
- The solar clock checks the local zone once a minute and selects one of 18 animated WebP loops based on solar altitude at the zone’s representative city. T3 reloads the image from its watched theme directory.

## Verify and rebuild

Run `python -m sinnoh.solar --status` with the installed environment to check the time zone and phase. Use `t3 theme show` to inspect the environment theme. Check `monitor.log` in the installed directory if the Browser cannot connect.

| Desktop | Install directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\T3 Sinnoh Lake` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/t3-sinnoh-lake` |
| macOS | `~/Library/Application Support/T3 Sinnoh Lake` |

To run the tests, install `requirements.txt` and `Pillow==13.0.0`, then run `python -m unittest discover -s tests -v` and `node --test tests/poketch.test.mjs`. For the optional Chromium layout test, install Playwright and its Chromium build, then run `node tests/poketch-browser.mjs`. The desktop installer does not require Node.

The shipped animations are ready to use. To rebuild a phase, install `artwork/requirements.txt` and run `python artwork/build.py day`. The other keys are `night`, `rise1` through `rise8`, and `set1` through `set8`. For attribution, see [CREDITS.md](CREDITS.md).
