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

## Pokétch in chat

Select **Sinnoh Rift · Lake Life** in **Settings → Appearance**. Pokétch appears as soon as T3 renders any existing chat or new draft, including chats on linked environments. It hides on non-chat screens and when the T3 window is minimized or closed. Clicks over the LCD pass straight through to the chat beneath it (`pointer-events: none`), and clicking the red buttons or collapse toggle never steals focus from the chat composer.

Pokétch floats 14 px from the right edge and 90 px from the bottom of the T3 viewport. Its reference size is 240 × 126 px at T3’s default window size. The whole device scales down in compact windows and up in larger ones.

The update hides the old floating Pokétch when its tab is on the installed loopback URL. The tab remains available in the right panel and you can close it there. Docked tabs and other Browser pages retain their layout.

The in-chat controls use CSS `scroll-timeline` driven by non-focusable `::-webkit-scrollbar-button` steppers (avoiding Chromium’s `::scroll-marker` / `::scroll-button()` crash) and were tested in T3 Nightly `0.1.11-nightly.20261118.4890`. The standalone panel also remains available at the installer’s loopback URL in the docked **Browser** panel or a regular browser tab. [T3 theme CSS documentation](https://github.com/pingdotgg/t3code/blob/8cf97b5f06f30a872ce30ab8a888f2ff012365a2/docs/user/appearance.md#custom-css)

The worker reads the provider instance configuration and cached quota fields on the machine where it runs. It updates the displayed quota through the published theme, so a theme export or a client following that environment theme receives the display values. The standalone panel and its read-only quota endpoint bind to IPv4 loopback.

## Quota, context and local time

- Click the Pokétch’s red **UP** and **DOWN** buttons (or scroll with the mouse wheel / trackpad over them) to step through every configured provider instance and reported quota window. Click the small **−** pill above the top-right edge to collapse Pokétch into a compact badge, and click the badge to expand it again.
- **LEFT** and the meter show remaining quota. Each provider begins on its tightest valid quota window before advancing through its remaining windows. The theme uses the worker’s local time zone for reset times.
- Expired quota values are hidden until T3 reports a new snapshot, showing **Awaiting reset update**. Unknown quota shows a dash. A valid exhausted window shows **0%** and an empty meter.
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
