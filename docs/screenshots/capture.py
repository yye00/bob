"""Render swedish-circle screenshots for bob3 documentation.

Drives the MainWindow programmatically (offscreen Qt) through a realistic
session and captures each window via QWidget.grab(). All screenshots use
fixed seeds, deterministic geometries, and explicit view fits so they are
reproducible.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QApplication

from swedish_circle.geometry import SlopeProfile
from swedish_circle.gui.analysis_overlay import AnalysisOverlay
from swedish_circle.gui.main_window import MainWindow
from swedish_circle.gui.material_dialog import MaterialDialog
from swedish_circle.material import Material
from swedish_circle.search import search_critical_circle


WINDOW_W, WINDOW_H = 1280, 800


def process_events(times: int = 6) -> None:
    app = QApplication.instance()
    for _ in range(times):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)


def grab(widget, out: Path) -> None:
    process_events()
    pixmap = widget.grab()
    pixmap.save(str(out), "PNG")
    print(f"  wrote {out.name} ({pixmap.width()}x{pixmap.height()})")


def fit_view(canvas, xmin: float, xmax: float, ymin: float, ymax: float,
             margin: float = 1.0) -> None:
    """Frame the canvas to a specific world-space bounding box."""
    xmin -= margin; xmax += margin
    ymin -= margin; ymax += margin
    w = canvas.width(); h = canvas.height()
    world_w = xmax - xmin
    world_h = ymax - ymin
    if world_w <= 0 or world_h <= 0:
        return
    scale = min(w / world_w, h / world_h) * 0.92
    cx = (xmin + xmax) / 2
    cy = (ymin + ymax) / 2
    t = QTransform()
    t.translate(w / 2, h / 2)
    t.scale(scale, -scale)
    t.translate(-cx, -cy)
    canvas._transform = t
    canvas.update()


def abramson_slope() -> SlopeProfile:
    """Abramson textbook example: 2H:1V slope, 10 m height."""
    ground = [(0.0, 0.0), (20.0, 10.0), (35.0, 10.0)]
    material = Material(
        cohesion=20.0, friction_deg=20.0,
        unit_weight=18.0, sat_unit_weight=18.0,
    )
    return SlopeProfile(
        ground_surface=ground, water_table=None, material=material,
    )


def steeper_slope() -> SlopeProfile:
    """Cohesive 1.5H:1V slope, 8 m height — steeper, lower FoS."""
    ground = [(0.0, 0.0), (12.0, 8.0), (25.0, 8.0)]
    material = Material(
        cohesion=15.0, friction_deg=18.0,
        unit_weight=19.0, sat_unit_weight=19.0,
    )
    return SlopeProfile(
        ground_surface=ground, water_table=None, material=material,
    )


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv)

    # --- 01: Empty MainWindow on first launch ---
    print("01_empty_window: empty MainWindow on first launch")
    w = MainWindow()
    w.resize(WINDOW_W, WINDOW_H)
    w.show()
    grab(w, out_dir / "01_empty_window.png")

    # --- 02: Slope geometry loaded, framed cleanly ---
    print("02_slope_geometry: Abramson slope loaded")
    slope = abramson_slope()
    w.slope_profile = slope
    w.material = slope.material
    w.canvas.set_slope(slope)
    fit_view(w.canvas, 0.0, 35.0, 0.0, 12.0, margin=2.0)
    grab(w, out_dir / "02_slope_geometry.png")

    # --- 03: Critical circle + slices, no FoS contour (clean engineering view) ---
    print("03_critical_circle: Bishop critical circle + slice boundaries")
    result = search_critical_circle(
        slope, method="bishop",
        x_grid=30, y_grid=30, r_grid=20, n_slices=50,
    )
    print(f"     critical FoS = {result.critical_fos:.3f}  "
          f"center=({result.critical_center[0]:.1f},{result.critical_center[1]:.1f})  "
          f"r={result.critical_radius:.1f}")
    overlay = AnalysisOverlay(w.canvas)
    overlay._search_result = result
    w.last_search_result = result
    # Suppress the FoS contour for this engineering-clean view.
    overlay._render_fos_contour = lambda painter: None
    fit_view(w.canvas, 0.0, 35.0, -2.0, 12.0, margin=1.5)
    w.canvas.update()
    grab(w, out_dir / "03_critical_circle.png")

    # --- 04: Steeper slope, comparison geometry ---
    print("04_steeper_slope: 1.5H:1V cohesive-frictional slope")
    slope2 = steeper_slope()
    w.slope_profile = slope2
    w.material = slope2.material
    w.canvas.set_slope(slope2)
    result2 = search_critical_circle(
        slope2, method="bishop",
        x_grid=25, y_grid=25, r_grid=15, n_slices=50,
    )
    print(f"     critical FoS = {result2.critical_fos:.3f}  "
          f"center=({result2.critical_center[0]:.1f},{result2.critical_center[1]:.1f})  "
          f"r={result2.critical_radius:.1f}")
    # Reuse the existing overlay so we don't stack canvas-paint wrappers.
    overlay._search_result = result2
    overlay._render_fos_contour = lambda painter: None
    w.last_search_result = result2
    fit_view(w.canvas, 0.0, 25.0, -2.0, 10.0, margin=1.5)
    w.canvas.update()
    grab(w, out_dir / "04_steeper_slope.png")

    # --- 05: Material editor showing soil parameters ---
    print("05_material_dialog: Material editor")
    dlg = MaterialDialog(parent=w, material=slope.material)
    dlg.resize(440, 340)
    dlg.show()
    grab(dlg, out_dir / "05_material_dialog.png")
    dlg.close()

    w.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
