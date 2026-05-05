"""Render swedish-circle screenshots for bob3 documentation.

Drives the MainWindow programmatically (offscreen Qt) through a realistic
session — empty state, with slope loaded, after analysis — and captures
each window via QWidget.grab(), plus a separate snapshot of the
MaterialDialog. Output goes to ``OUT_DIR``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from swedish_circle.geometry import SlopeProfile
from swedish_circle.gui.analysis_overlay import AnalysisOverlay
from swedish_circle.gui.main_window import MainWindow
from swedish_circle.gui.material_dialog import MaterialDialog
from swedish_circle.material import Material
from swedish_circle.search import search_critical_circle


OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def process_events(times: int = 5) -> None:
    """Spin the Qt event loop a few times so layouts/paints settle."""
    app = QApplication.instance()
    for _ in range(times):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)


def grab_window(window, name: str, width: int = 1280, height: int = 800) -> Path:
    window.resize(width, height)
    window.show()
    process_events()
    pixmap = window.grab()
    out = OUT_DIR / name
    pixmap.save(str(out), "PNG")
    print(f"  wrote {out} ({pixmap.width()}x{pixmap.height()})")
    return out


def abramson_slope() -> SlopeProfile:
    # 2H:1V slope, 10m height, with bench beyond crest. Matches the canonical
    # Abramson textbook example used by the V&V tests.
    ground = [(0.0, 0.0), (20.0, 10.0), (35.0, 10.0)]
    material = Material(
        cohesion=20.0, friction_deg=20.0,
        unit_weight=18.0, sat_unit_weight=18.0,
    )
    return SlopeProfile(
        ground_surface=ground, water_table=None, material=material,
    )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    # --- 1. Empty MainWindow on first launch ---
    print("Capturing empty main window...")
    w = MainWindow()
    grab_window(w, "01_empty_window.png")

    # --- 2. With Abramson slope loaded ---
    print("Capturing with slope loaded...")
    slope = abramson_slope()
    w.slope_profile = slope
    w.material = slope.material
    w.canvas.set_slope(slope)
    w.canvas.fit_to_view()
    process_events()
    grab_window(w, "02_with_slope.png")

    # --- 3. Run analysis and overlay critical circle ---
    print("Running search_critical_circle (this takes a moment)...")
    result = search_critical_circle(
        slope, method="bishop",
        x_grid=25, y_grid=25, r_grid=15, n_slices=50,
    )
    print(f"  critical FoS = {result.critical_fos:.3f} "
          f"center=({result.critical_center[0]:.1f},{result.critical_center[1]:.1f}) "
          f"r={result.critical_radius:.1f}")

    overlay = AnalysisOverlay(w.canvas)
    overlay._search_result = result
    w.last_search_result = result
    w.canvas.update()
    process_events()
    grab_window(w, "03_with_analysis.png")

    # --- 4. Material dialog showing soil parameters ---
    print("Capturing material dialog...")
    dlg = MaterialDialog(parent=w, material=slope.material)
    grab_window(dlg, "04_material_dialog.png", width=420, height=320)
    dlg.close()

    w.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
