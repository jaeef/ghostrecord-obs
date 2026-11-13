# Changelog

All notable changes to GhostRec OBS. Dates are release dates (YYYY-MM-DD).

## [Unreleased]

### Changed
- Windows 11 look instead of macOS: native title bar (recolored to match),
  Segoe Fluent icons, soft orange accent, Windows button order in dialogs.
- OBS-style cues: the app logo (title bar, taskbar, tray), timer and REC
  badge are red while recording (covered is normal) and yellow only when the
  recording is at risk: minimized, may freeze, or output restarting.
- Record page cards fill the row (as many columns as fit), titles wrap to two
  readable lines, and app logos come from the window itself (Store apps too).
- GhostRec shows its own logo in the taskbar instead of Python's.

### Removed
- Traffic-light window controls and the `ui.native_frame` setting.

## [1.2.0] - 2026-11-13

### Fixed
- OBS capture sources use the "window title must match" priority, so OBS can
  no longer fall back to another window of the same app (a privacy leak).
- A renamed target window is re-aimed within ~0.25 s instead of up to
  `poll_seconds`; identical twin windows trigger a warning.
- Recording no longer restarts (creating an extra file segment) right after
  start, before OBS reports the output as active.
- A failing log sink can no longer break moving the finished file.
- Library actions enable as soon as a recording is selected.

### Added
- OBS is switched back to your previous scene after each recording.
- "Make Recording-Safe": restarts Chrome, Edge, Brave, Opera, Vivaldi,
  Electron apps and new Teams (WebView2) so they keep drawing while covered.
- macOS-style interface: traffic-light window controls, sidebar, unified
  toolbar, light/dark appearance, macOS-style alerts.
- Record page with live window thumbnails and a pre-flight checklist; Live page
  with a scrolling inspector and a filterable activity log.
- Recordings are moved to the Recycle Bin instead of being deleted.
- `pyproject.toml` with `ghostrec` and `ghostrec-cli` commands;
  `python -m ghostrec` opens the app; tests and CI.

### Changed
- CLI moved to `ghostrec/cli.py`; `record.py` and `app.py` remain as entry
  points.

### Removed
- `start_recorder.bat`, `open_class_browser.bat` and the interactive
  `setup.py` helper — `start_gui.bat` and the Settings page cover setup.
- Unused logo variants (`icon.svg`, `icon-light.svg`, `mark-mono.svg`).

## [1.1.0] - 2026-11-03
- Desktop app (PyQt6) with picker, live status, library and settings.
- Covered-window capture with Windows Graphics Capture, audio monitoring,
  system tray, single-instance guard and safety checks.

## [1.0.0] - 2026-09-08
- First release: CLI window recorder that pins one window by HWND in OBS.
