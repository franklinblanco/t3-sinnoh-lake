# T3 Sinnoh Lake

Sinnoh Rift · Lake Life brings an animated pixel-art lake to the T3 Code conversation pane. The artwork includes submerged Magikarp, Buizel and Finneon. Pokétch is a separate green LCD that reads quota from the same desktop user's T3 Code provider caches.

## Install

Run the installer as the user running T3 Code. It installs a private Python environment, publishes the theme, and selects it through the bundled `t3 theme set` command. T3 Code can stay open. If an older build lacks that command, select **Sinnoh Rift · Lake Life** in **Settings → Appearance**. The static **Sinnoh Rift** variant is also available.

| Desktop | Command | Startup and window behavior |
| --- | --- | --- |
| Windows 10/11 | `py -3.12 install.py` | A limited, interactive Task Scheduler job starts Pokétch in the signed-in session and at logon. It follows the foreground T3 Code window. |
| Linux | `python3 install.py` | An XDG autostart entry starts it at graphical login. Install from the graphical session to start it immediately. On an EWMH-compatible X11 desktop, it follows the foreground T3 Code window. |
| macOS | `python3 install.py` | Two per-user LaunchAgents run the solar clock and native AppKit overlay. Installation uses `swiftc` from Xcode or Command Line Tools. |

Use Python 3.11–3.14 with `venv`, `pip` and Git available. On Linux, install the Qt runtime libraries for your display server if your distribution does not include them. On Debian or Ubuntu, the X11 Qt plugin needs packages including `libxcb-cursor0` and `libxkbcommon-x11-0`. Wayland opens a movable Pokétch window because Wayland clients lack access to the foreground window and its global coordinates. The compositor controls always-on-top placement. Use your desktop's keep-above or window-rule feature when available.

The default T3 data directory is `~/.t3`. Set `T3CODE_HOME` or pass `--t3-home PATH` for a custom directory. Pass `--keep-theme` to install without selecting it. The installed `launch.py` supports `--standalone` for a movable panel on Windows and Linux, and `--clock-only` for an ongoing solar clock without a display. Switch back to a built-in theme in Appearance if you want to stop using the background. To stop the helper at future logins, remove its user task, autostart entry, or LaunchAgents.

## Pokétch and solar time

- Press the upper or lower red button to move between provider instances. The monitor includes every configured instance and enabled built-in providers discovered in T3 Code's caches.
- **LEFT** and the meter show `100 − usedPercent`. The initial window is the tightest valid quota. Click the LCD to cycle through all reported windows. Reset times use the desktop's locale and time zone.
- Quota expires at its reported reset until T3 supplies a new snapshot. Unknown quota is a dash with no meter. A valid exhausted window shows **0%** and an empty meter. Disabled, signed-out, unsupported and failed checks have their own status.
- Hover over the ring to the left of the model picker to see the percentage of context used in that thread. The ring refreshes once a minute. For linked machines it reads the latest measurement T3 Desktop has received, so an offline machine can show its last known reading. The theme prioritizes recently viewed and active threads across machines within T3’s stylesheet size limit. A thread without an available reading shows “Context usage unavailable.”
- The solar clock checks the system time zone every minute. It uses the zone's representative IANA city, including mappings from Windows zone names. Fixed-offset zones use the corresponding equatorial meridian. It swaps among 18 complete 24-second WebP loops using solar altitude and whether the sun is rising or setting. T3 Code reloads the image from its watched theme directory.

## Verify and rebuild

Run `python -m sinnoh.solar --status` in the source tree or installed directory with the relevant Python dependencies on its import path. It prints the detected time zone, coordinates and phase. The `t3 theme show` command confirms the selected theme. On Windows, check the **T3 Sinnoh Lake** scheduled task and `monitor.log` under `%LOCALAPPDATA%\T3 Sinnoh Lake`. On Linux the log is under `$XDG_DATA_HOME/t3-sinnoh-lake` or `~/.local/share/t3-sinnoh-lake`.

Install `requirements.txt` plus `Pillow==13.0.0` to run `python -m unittest discover -s tests -v`. The Qt tests also require `PySide6-Essentials==6.10.2` when run on macOS, where the installed monitor is native Swift. Run with `QT_QPA_PLATFORM=offscreen` to exercise the LCD without a desktop. The X11 and Wayland tests use `SINNOH_TEST_X11=1` and `SINNOH_TEST_WAYLAND=1` in their respective display sessions. On macOS, build the Swift helper with `swiftc -O Poketch.swift -o /tmp/poketch` and run `/tmp/poketch --check` to check provider and window cycling against local T3 data.

The shipped animations are ready to use. To rebuild a phase, install `artwork/requirements.txt` and run `python artwork/build.py day`. The other keys are `night`, `rise1` through `rise8`, and `set1` through `set8`. For attribution, see [CREDITS.md](CREDITS.md).
