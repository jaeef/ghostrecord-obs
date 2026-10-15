"""Recordings library: scan the output folder, open/delete files.

Files are matched against the naming scheme produced by
``recorder.file_recording``: ``<name>_YYYY-MM-DD_HH-MM-SS.<ext>``.
Unparsable files are still listed (name = file stem, no timestamp).
"""

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime

_FILENAME_RE = re.compile(
    r"^(?P<name>.+)_(?P<ts>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})(?P<ext>\.\w+)$")


@dataclass
class Recording:
    path: str
    name: str
    timestamp: datetime | None
    ext: str
    size_bytes: int
    mtime: float

    @property
    def display_date(self):
        dt = self.timestamp or datetime.fromtimestamp(self.mtime)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def scan_recordings(output_folder):
    """Return recordings newest-first. Empty/missing folder -> []."""
    if not output_folder or not os.path.isdir(output_folder):
        return []
    out = []
    for fname in os.listdir(output_folder):
        path = os.path.join(output_folder, fname)
        if not os.path.isfile(path):
            continue
        try:
            st = os.stat(path)
        except OSError:
            continue
        stem, ext = os.path.splitext(fname)
        m = _FILENAME_RE.match(fname)
        if m:
            name = m.group("name")
            ext = m.group("ext")
            try:
                ts = datetime.strptime(m.group("ts"), "%Y-%m-%d_%H-%M-%S")
            except ValueError:
                ts = None
        else:
            name, ts = stem, None
        out.append(Recording(path=path, name=name, timestamp=ts, ext=ext,
                             size_bytes=st.st_size, mtime=st.st_mtime))
    out.sort(key=lambda r: r.timestamp or datetime.fromtimestamp(r.mtime),
             reverse=True)
    return out


def human_size(n):
    """'93.9 MB' style size string."""
    step = 1024.0
    val = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if val < step:
            if unit == "B":
                return f"{int(val)} B"
            return f"{val:.1f} {unit}"
        val /= step
    return f"{val:.1f} PB"


def open_file(path):
    os.startfile(path)


def show_in_explorer(path):
    subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])


def delete_recording(path):
    os.remove(path)
