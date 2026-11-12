"""Record page: visual window gallery + "Ready to record" panel.

Left: search, filter segments and a grid of window cards with live
thumbnails. Right: the selected window large, a pre-flight checklist (OBS,
restored, keeps drawing when covered), the file name and the record button.
"""

import os
import threading

from PyQt6.QtCore import (QFileInfo, QSettings, QSize, Qt, QTimer,
                          pyqtSignal)
from PyQt6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QFileIconProvider,
                             QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QListView, QListWidget, QListWidgetItem,
                             QPushButton, QScrollArea, QSizePolicy,
                             QVBoxLayout, QWidget)

from ghostrec.core.library import unique_recording_name
from ghostrec.core.recorder import sanitize_recording_name
from ghostrec.core.safe_apps import app_kind, app_name, is_recording_safe
from ghostrec.core.thumbs import capture as capture_thumb
from ghostrec.core.windows import list_windows
from ghostrec.ui import theme
from ghostrec.ui.widgets import ElidedLabel

CARD_W, CARD_H = 228, 214
THUMB_W, THUMB_H = 204, 124


def _to_image(raw, w, h):
    """BGRA bytes -> QImage scaled for the panel (safe off the GUI thread)."""
    img = QImage(raw, w, h, w * 4, QImage.Format.Format_RGB32)
    return img.scaled(560, 350, Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation).copy()


def _cover(pixmap, w, h):
    """Scale + center-crop a pixmap to exactly w x h (like CSS cover)."""
    if pixmap is None or pixmap.isNull():
        return None
    scaled = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
    x = max(0, (scaled.width() - w) // 2)
    y = max(0, (scaled.height() - h) // 2)
    return scaled.copy(x, y, w, h)


class WindowTile(QWidget):
    """Gallery card: thumbnail, app icon, title, one status badge."""

    def __init__(self, win, icon=None, parent=None):
        super().__init__(parent)
        self.win = win
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(0)
        self.thumb = QLabel()
        self.thumb.setObjectName("tileThumb")
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.thumb)
        lay.addSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.icon = QLabel()
        self.icon.setFixedSize(18, 18)
        self._icon = icon
        if icon is not None and not icon.isNull():
            self.icon.setPixmap(icon.pixmap(18, 18))
        row.addWidget(self.icon)
        self.title = ElidedLabel(win.get("title", "Untitled"))
        self.title.setObjectName("tileTitle")
        row.addWidget(self.title, 1)
        lay.addLayout(row)
        lay.addSpacing(4)

        meta = QHBoxLayout()
        meta.setSpacing(6)
        exe = QLabel(app_name(win.get("exe")) if win.get("safe_kind")
                     else (win.get("exe") or "").replace(".exe", ""))
        exe.setObjectName("tileMeta")
        meta.addWidget(exe)
        meta.addStretch(1)
        badge = None
        if win.get("minimized"):
            badge = ("Minimized", "tileBadgeWarn")
        elif win.get("safe_kind") and not win.get("record_friendly"):
            badge = ("May freeze", "tileBadgeWarn")
        elif win.get("safe_kind"):
            badge = ("Recording-safe", "tileBadgeOk")
        if badge:
            b = QLabel(badge[0])
            b.setObjectName(badge[1])
            meta.addWidget(b)
        lay.addLayout(meta)
        lay.addStretch(1)
        self.set_thumbnail(None)

    def set_thumbnail(self, pixmap):
        pm = _cover(pixmap, THUMB_W, THUMB_H)
        if pm is not None:
            self.thumb.setPixmap(pm)
            self.thumb.setText("")
        else:
            self.thumb.setPixmap(QPixmap())
            if self._icon is not None and not self._icon.isNull():
                self.thumb.setPixmap(self._icon.pixmap(40, 40))
            else:
                self.thumb.setText("No preview")


class CheckRow(QWidget):
    """Checklist line: status glyph + text + optional action button."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 5, 0, 5)
        lay.setSpacing(10)
        self.glyph = QLabel("•")
        self.glyph.setFixedWidth(18)
        self.glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text = QLabel(text)
        self.text.setObjectName("rowLabel")
        self.text.setWordWrap(True)
        self.action = QPushButton("")
        self.action.setObjectName("linkButton")
        self.action.hide()
        lay.addWidget(self.glyph)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.action)

    def set(self, state, text, action=None):
        """state: ok | warn | err | idle."""
        glyph, color = {"ok": ("✓", theme.OK), "warn": ("!", theme.WARN),
                        "err": ("✕", theme.ERR)}.get(state, ("•", theme.DIMMED))
        self.glyph.setText(glyph)
        self.glyph.setStyleSheet(
            f"color: white; background: {color}; border-radius: 9px; "
            "font-size: 11px; font-weight: 800; min-height: 18px; "
            "max-height: 18px;" if state != "idle" else
            f"color: {color}; font-size: 14px;")
        self.text.setText(text)
        self.action.setVisible(bool(action))
        if action:
            self.action.setText(action)


class PickerPage(QWidget):
    """Emits record_requested(window_dict, name)."""

    record_requested = pyqtSignal(dict, str)
    chrome_requested = pyqtSignal()
    make_safe_requested = pyqtSignal(dict)
    connect_requested = pyqtSignal()
    _windows_ready = pyqtSignal(int, object, object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wins = []
        self._busy = False
        self._output_dir = ""
        self._refreshing = False
        self._refresh_generation = 0
        self._filter_text = ""
        self._segment = "all"
        self._obs_connected = False
        self._icon_provider = QFileIconProvider()
        self._icons = {}      # exe_path -> QIcon
        self._thumbs = {}     # hwnd -> QPixmap (last good thumbnail)
        self._tiles = {}      # hwnd -> WindowTile
        self._last_sig = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        # ================= left: gallery =================================== #
        left = QVBoxLayout()
        left.setSpacing(12)
        root.addLayout(left, 1)

        hero = QVBoxLayout()
        hero.setSpacing(2)
        h1 = QLabel("What do you want to record?")
        h1.setObjectName("heroTitle")
        h2 = QLabel("Pick a window. Only that window is captured — keep "
                    "working anywhere else.")
        h2.setObjectName("pageSubtitle")
        hero.addWidget(h1)
        hero.addWidget(h2)
        left.addLayout(hero)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchField")
        self.search_edit.setPlaceholderText("Search windows")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(220)
        bar.addWidget(self.search_edit)

        seg = QWidget()
        seg.setObjectName("segmented")
        seg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(2, 2, 2, 2)
        seg_lay.setSpacing(2)
        self._seg_group = QButtonGroup(self)
        for key, label in (("all", "All"), ("browser", "Browsers"),
                           ("apps", "Apps")):
            b = QPushButton(label)
            b.setObjectName("segment")
            b.setCheckable(True)
            b.setProperty("segKey", key)
            if key == "all":
                b.setChecked(True)
            self._seg_group.addButton(b)
            seg_lay.addWidget(b)
        self._seg_group.buttonClicked.connect(self._on_segment)
        bar.addWidget(seg)
        bar.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("dimmed")
        bar.addWidget(self.count_label)
        self.auto_refresh = QCheckBox("Live")
        self.auto_refresh.setToolTip("Refresh the window list and thumbnails "
                                     "every few seconds")
        self.auto_refresh.setChecked(True)
        bar.addWidget(self.auto_refresh)
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setObjectName("iconButton")
        self.refresh_btn.setToolTip("Refresh now")
        self.refresh_btn.setFixedSize(30, 28)
        bar.addWidget(self.refresh_btn)
        left.addLayout(bar)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("windowGrid")
        self.list_widget.setViewMode(QListView.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_widget.setMovement(QListView.Movement.Static)
        self.list_widget.setFlow(QListView.Flow.LeftToRight)
        self.list_widget.setWrapping(True)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setGridSize(QSize(CARD_W + 14, CARD_H + 14))
        self.list_widget.setSpacing(0)
        self.list_widget.setSelectionMode(
            QListWidget.SelectionMode.SingleSelection)
        self.list_widget.setVerticalScrollMode(
            QListWidget.ScrollMode.ScrollPerPixel)
        self.list_widget.verticalScrollBar().setSingleStep(24)
        left.addWidget(self.list_widget, 1)

        self.empty_label = QLabel("No windows match your search.")
        self.empty_label.setObjectName("muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.hide()
        left.addWidget(self.empty_label, 1)

        # ================= right: ready panel =============================== #
        panel = QWidget()
        panel.setObjectName("inspector")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setFixedWidth(312)
        panel_outer = QVBoxLayout(panel)
        panel_outer.setContentsMargins(0, 0, 0, 0)
        panel_outer.setSpacing(0)
        root.addWidget(panel)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("inspectorBody")
        p = QVBoxLayout(body)
        p.setContentsMargins(18, 18, 18, 10)
        p.setSpacing(10)
        scroll.setWidget(body)
        panel_outer.addWidget(scroll, 1)

        head = QLabel("Ready to record")
        head.setObjectName("sectionHeader")
        p.addWidget(head)

        self.big_thumb = QLabel("Select a window")
        self.big_thumb.setObjectName("bigThumb")
        self.big_thumb.setFixedSize(276, 160)
        self.big_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p.addWidget(self.big_thumb)

        self.sel_title = ElidedLabel("No window selected")
        self.sel_title.setObjectName("cardTitle")
        p.addWidget(self.sel_title)
        self.sel_meta = QLabel("")
        self.sel_meta.setObjectName("mono")
        p.addWidget(self.sel_meta)

        p.addSpacing(4)
        p.addWidget(self._section("Checklist"))
        checks = QWidget()
        checks.setObjectName("groupCard")
        checks.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cl = QVBoxLayout(checks)
        cl.setContentsMargins(12, 4, 12, 4)
        cl.setSpacing(0)
        self.check_obs = CheckRow("OBS connected")
        self.check_restored = CheckRow("Window is restored")
        self.check_safe = CheckRow("Keeps drawing when covered")
        for i, row in enumerate((self.check_obs, self.check_restored,
                                 self.check_safe)):
            if i:
                line = QFrame()
                line.setObjectName("hairline")
                line.setFixedHeight(1)
                cl.addWidget(line)
            cl.addWidget(row)
        p.addWidget(checks)
        self.check_obs.action.clicked.connect(self.connect_requested.emit)
        self.check_safe.action.clicked.connect(self._emit_make_safe)

        p.addSpacing(4)
        p.addWidget(self._section("Save as"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("recording")
        self.name_edit.setText(QSettings().value("last_name", "") or "")
        p.addWidget(self.name_edit)
        self.save_hint = QLabel("")
        self.save_hint.setObjectName("dimmed")
        self.save_hint.setWordWrap(True)
        p.addWidget(self.save_hint)
        p.addStretch(1)

        footer = QWidget()
        footer.setObjectName("inspectorFooter")
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        f = QVBoxLayout(footer)
        f.setContentsMargins(18, 14, 18, 14)
        f.setSpacing(8)
        self.start_btn = QPushButton("●  Start Recording")
        self.start_btn.setObjectName("recordButton")
        self.start_btn.setSizePolicy(QSizePolicy.Policy.Expanding,
                                     QSizePolicy.Policy.Fixed)
        f.addWidget(self.start_btn)
        foot_note = QLabel("Stops and saves when the window closes.")
        foot_note.setObjectName("dimmed")
        foot_note.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f.addWidget(foot_note)
        self.chrome_btn = QPushButton("Open Safe Browser")
        self.chrome_btn.setObjectName("ghost")
        self.chrome_btn.setToolTip(
            "Opens a separate Chrome that keeps drawing while covered — "
            "handy for web meetings and online classes.")
        f.addWidget(self.chrome_btn)
        panel_outer.addWidget(footer)

        # Signals
        self.name_edit.textChanged.connect(self._update_hint)
        self.search_edit.textChanged.connect(self._set_filter)
        self.refresh_btn.clicked.connect(self.refresh)
        self.chrome_btn.clicked.connect(self.chrome_requested.emit)
        self.start_btn.clicked.connect(self._start)
        self.list_widget.itemDoubleClicked.connect(lambda *_: self._start())
        self.list_widget.currentItemChanged.connect(self._update_panel)
        self._windows_ready.connect(self._apply_windows)
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            QShortcut(QKeySequence(key), self.list_widget,
                      context=Qt.ShortcutContext.WidgetWithChildrenShortcut
                      ).activated.connect(self._start)

        self._timer = QTimer(self)
        self._timer.setInterval(4000)
        self._timer.timeout.connect(self._auto_tick)
        self._timer.start()

        self._update_panel()
        self.refresh()

    # -- small builders ------------------------------------------------------ #

    @staticmethod
    def _section(text):
        lbl = QLabel(text.upper())
        lbl.setObjectName("sectionLabel")
        return lbl

    # -- API used by the main window ------------------------------------------ #

    def set_output_dir(self, folder):
        self._output_dir = folder or ""
        self._update_hint()

    def set_obs_connected(self, connected):
        self._obs_connected = bool(connected)
        self._update_panel()

    def set_busy(self, busy):
        self._busy = busy
        self._update_panel()
        self.start_btn.setText("●  Start Recording" if not busy
                               else "Recording in Progress…")

    def restyle(self):
        self._last_sig = None
        self._apply_windows(self._refresh_generation, self._wins, None, "")
        self._update_hint()
        self._update_panel()

    def refresh(self):
        if self._refreshing:
            return
        self._refreshing = True
        self._refresh_generation += 1
        token = self._refresh_generation
        if not self._wins:
            self.count_label.setText("Scanning…")

        def work():
            thumbs = {}
            try:
                own_pid = os.getpid()
                # never offer GhostRec's own windows as a target
                windows = [w for w in list_windows()
                           if w.get("pid") != own_pid]
                for win in windows:
                    exe = (win.get("exe") or "").lower()
                    win["minimized"] = False
                    kind = app_kind(exe)
                    if kind:
                        win["safe_kind"] = kind
                        win["record_friendly"] = is_recording_safe(
                            win.get("pid"), exe)
                    try:
                        shot = capture_thumb(win["hwnd"])
                    except Exception:
                        shot = None
                    if shot:
                        thumbs[win["hwnd"]] = _to_image(shot[2], shot[0],
                                                        shot[1])
                    else:
                        import win32gui
                        win["minimized"] = bool(win32gui.IsIconic(win["hwnd"]))
                error = ""
            except Exception as e:
                windows = []
                error = str(e)
            self._windows_ready.emit(token, windows, thumbs, error)

        threading.Thread(target=work, name="ghostrec-window-scan",
                         daemon=True).start()

    # -- internals ----------------------------------------------------------- #

    def _resolved_name(self):
        base = sanitize_recording_name(self.name_edit.text())
        return base, unique_recording_name(self._output_dir, base)

    def _update_hint(self, *_):
        base, final = self._resolved_name()
        if final != base:
            self.save_hint.setText(f"Saves as “{final}” (name already used)")
        else:
            self.save_hint.setText(f"Saves as “{final}_<date>”")

    def _visible(self):
        needle = self._filter_text.strip().lower()
        out = []
        for w in self._wins:
            if needle and needle not in (f"{w.get('title', '')}\n"
                                         f"{w.get('exe', '')}").lower():
                continue
            if self._segment == "browser" and w.get("safe_kind") != "browser":
                continue
            if self._segment == "apps" and w.get("safe_kind") == "browser":
                continue
            out.append(w)
        return out

    def _apply_windows(self, token, windows, thumbs, error):
        if token != self._refresh_generation:
            return
        self._refreshing = False
        for hwnd, img in (thumbs or {}).items():
            self._thumbs[hwnd] = QPixmap.fromImage(img)
        live = {w["hwnd"] for w in windows}
        for hwnd in list(self._thumbs):
            if hwnd not in live:
                self._thumbs.pop(hwnd, None)

        sig = (self._filter_text, self._segment, error,
               tuple((w.get("hwnd"), w.get("title"), w.get("record_friendly"),
                      w.get("minimized")) for w in windows))
        self._wins = windows
        if sig == self._last_sig:
            # same windows: only refresh thumbnails, keep scroll + selection
            for hwnd, tile in self._tiles.items():
                tile.set_thumbnail(self._thumbs.get(hwnd))
            self._update_panel()
            return
        self._last_sig = sig

        prev = self._selected_window()
        prev_hwnd = prev.get("hwnd") if prev else None
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self._tiles = {}
        visible = self._visible()
        for w in visible:
            item = QListWidgetItem()
            item.setSizeHint(QSize(CARD_W, CARD_H))
            item.setData(Qt.ItemDataRole.UserRole, w)
            self.list_widget.addItem(item)
            tile = WindowTile(w, icon=self._icon_for(w.get("exe_path", "")))
            tile.set_thumbnail(self._thumbs.get(w["hwnd"]))
            self.list_widget.setItemWidget(item, tile)
            self._tiles[w["hwnd"]] = tile
            if w["hwnd"] == prev_hwnd:
                self.list_widget.setCurrentItem(item)
        if self.list_widget.currentItem() is None and visible:
            self.list_widget.setCurrentRow(0)
        self.list_widget.blockSignals(False)
        self.count_label.setText(
            f"⚠ {error}" if error else
            f"{len(visible)} window{'s' if len(visible) != 1 else ''}")
        empty = not visible and bool(self._wins)
        self.empty_label.setVisible(empty)
        self.list_widget.setVisible(not empty)
        self._update_panel()

    def _selected_window(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _update_panel(self, *_):
        win = self._selected_window()
        if self._obs_connected:
            self.check_obs.set("ok", "OBS connected")
        else:
            self.check_obs.set("err", "OBS is not connected", "Connect")
        if not win:
            self.big_thumb.setPixmap(QPixmap())
            self.big_thumb.setText("Select a window")
            self.sel_title.setText("No window selected")
            self.sel_meta.setText("")
            self.check_restored.set("idle", "Window is restored")
            self.check_safe.set("idle", "Keeps drawing when covered")
            self.start_btn.setEnabled(False)
            return
        pm = _cover(self._thumbs.get(win["hwnd"]), 276, 160)
        if pm is not None:
            self.big_thumb.setPixmap(pm)
            self.big_thumb.setText("")
        else:
            self.big_thumb.setPixmap(QPixmap())
            self.big_thumb.setText("Preview unavailable")
        self.sel_title.setText(win.get("title", ""))
        self.sel_meta.setText(f"{win.get('exe', '')}  •  "
                              f"0x{win.get('hwnd', 0):08X}")
        if win.get("minimized"):
            self.check_restored.set("warn", "Minimized — restore it first")
        else:
            self.check_restored.set("ok", "Window is restored")
        if not win.get("safe_kind"):
            self.check_safe.set("ok", "Keeps drawing when covered")
        elif win.get("record_friendly"):
            self.check_safe.set("ok", "Recording-safe — cover it freely")
        else:
            self.check_safe.set(
                "warn", f"{app_name(win.get('exe'))} may freeze when covered",
                "Fix")
        self.start_btn.setEnabled(not self._busy)

    def _emit_make_safe(self):
        win = self._selected_window()
        if win:
            self.make_safe_requested.emit(dict(win))

    def _on_segment(self, button):
        self._segment = button.property("segKey") or "all"
        self._last_sig = None
        self._apply_windows(self._refresh_generation, self._wins, None, "")

    def _set_filter(self, text):
        self._filter_text = text
        self._last_sig = None
        self._apply_windows(self._refresh_generation, self._wins, None, "")

    def _icon_for(self, exe_path):
        if not exe_path:
            return None
        if exe_path not in self._icons:
            self._icons[exe_path] = self._icon_provider.icon(QFileInfo(exe_path))
        return self._icons[exe_path]

    def _auto_tick(self):
        if self._busy or not self.auto_refresh.isChecked():
            return
        if not self.isVisible():
            return
        self.refresh()

    def _start(self):
        if self._busy:
            return
        win = self._selected_window()
        if not win:
            return
        base, name = self._resolved_name()
        QSettings().setValue("last_name", base)
        self.record_requested.emit(win, name)
