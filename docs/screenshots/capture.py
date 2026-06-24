"""Render swedish-circle screenshots for bob documentation.

Drives the MainWindow programmatically (offscreen Qt) through a realistic
session and captures each window via QWidget.grab(). All screenshots use
deterministic geometries and explicit view fits so they are reproducible.
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
from swedish_circle.material import Material, STIFF_CLAY
from swedish_circle.search import search_critical_circle


WINDOW_W, WINDOW_H = 1600, 900  # 16:9 for slides


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
             margin: float = 1.0, fill: float = 0.99) -> None:
    """Frame the canvas to a specific world-space bounding box.

    ``fill`` controls how aggressively the bounding box stretches to the
    edges of the canvas (1.0 = touch the edges; default 0.99 leaves a
    1% safety margin so axes labels aren't cut by the dock border).
    """
    xmin -= margin; xmax += margin
    ymin -= margin; ymax += margin
    w = canvas.width(); h = canvas.height()
    world_w = xmax - xmin
    world_h = ymax - ymin
    if world_w <= 0 or world_h <= 0:
        return
    scale = min(w / world_w, h / world_h) * fill
    cx = (xmin + xmax) / 2
    cy = (ymin + ymax) / 2
    t = QTransform()
    t.translate(w / 2, h / 2)
    t.scale(scale, -scale)
    t.translate(-cx, -cy)
    canvas._transform = t
    canvas.update()


def abramson_slope() -> SlopeProfile:
    """Abramson textbook example: 2H:1V slope, 10 m height, dry."""
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


def multi_bench_slope() -> SlopeProfile:
    """Multi-bench cut slope with phreatic surface and stiff-clay material.

    Two benches with intermediate berm, steeper lower segment, gentler
    upper segment. Water table runs through the lower bench.
    """
    ground = [
        (0.0, 0.0),    # toe
        (10.0, 6.0),   # lower-slope crest
        (15.0, 6.0),   # bench 1
        (22.0, 11.0),  # mid-slope crest
        (27.0, 11.0),  # bench 2
        (38.0, 16.0),  # main crest
        (55.0, 16.0),  # upper plateau
    ]
    water = [
        (0.0, 0.0),
        (15.0, 5.0),
        (28.0, 9.0),
        (55.0, 12.0),
    ]
    return SlopeProfile(
        ground_surface=ground,
        water_table=water,
        material=STIFF_CLAY,
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
    w.property_panel.update_from_window(w)
    grab(w, out_dir / "01_empty_window.png")

    # --- 02: Slope geometry loaded, framed cleanly ---
    print("02_slope_geometry: Abramson slope loaded")
    slope = abramson_slope()
    w.slope_profile = slope
    w.material = slope.material
    w.canvas.set_slope(slope)
    fit_view(w.canvas, 0.0, 35.0, 0.0, 11.0, margin=1.0)
    w.property_panel.update_from_window(w)
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
    fit_view(w.canvas, 0.0, 35.0, -1.0, 11.0, margin=1.0)
    w.canvas.update()
    w.property_panel.update_from_window(w)
    grab(w, out_dir / "03_critical_circle.png")

    # --- 04: Full analysis with FoS contour, view fitted to include grid ---
    print("04_fos_contour: Full analysis with smooth FoS heatmap")
    overlay._render_fos_contour = AnalysisOverlay._render_fos_contour.__get__(
        overlay, AnalysisOverlay,
    )
    # The heatmap is now clipped to the slope's x-domain and to the
    # bottom half of the FoS range, so we can frame to slope + a bit
    # of headroom above to capture the critical-center neighborhood.
    fit_view(w.canvas, 0.0, 35.0, -1.0, 24.0, margin=1.0)
    w.canvas.update()
    grab(w, out_dir / "04_fos_contour.png")

    # --- 05: Multi-bench slope with water table and stiff clay ---
    print("05_multi_bench: Multi-bench slope with water table (stiff clay)")
    slope3 = multi_bench_slope()
    # Reset the canvas's paint hook before re-binding a new overlay, so
    # we don't stack contour renderers across captures.
    w.slope_profile = slope3
    w.material = slope3.material
    w.canvas.set_slope(slope3)
    overlay._search_result = None
    w.canvas.update()
    result3 = search_critical_circle(
        slope3, method="bishop",
        x_grid=35, y_grid=35, r_grid=18, n_slices=60,
    )
    print(f"     critical FoS = {result3.critical_fos:.3f}  "
          f"center=({result3.critical_center[0]:.1f},{result3.critical_center[1]:.1f})  "
          f"r={result3.critical_radius:.1f}")
    overlay._search_result = result3
    overlay._render_fos_contour = AnalysisOverlay._render_fos_contour.__get__(
        overlay, AnalysisOverlay,
    )
    w.last_search_result = result3
    # Frame to slope footprint plus enough vertical room to show the
    # heatmap above the upper plateau.
    fit_view(w.canvas, 0.0, 55.0, -1.0, 38.0, margin=1.0)
    w.canvas.update()
    w.property_panel.update_from_window(w)
    grab(w, out_dir / "05_multi_bench.png")

    # --- 06: Steeper slope, comparison geometry ---
    print("06_steeper_slope: 1.5H:1V cohesive-frictional slope")
    slope2 = steeper_slope()
    w.slope_profile = slope2
    w.material = slope2.material
    w.canvas.set_slope(slope2)
    overlay._search_result = None
    w.canvas.update()
    result2 = search_critical_circle(
        slope2, method="bishop",
        x_grid=25, y_grid=25, r_grid=15, n_slices=50,
    )
    print(f"     critical FoS = {result2.critical_fos:.3f}  "
          f"center=({result2.critical_center[0]:.1f},{result2.critical_center[1]:.1f})  "
          f"r={result2.critical_radius:.1f}")
    overlay._search_result = result2
    overlay._render_fos_contour = lambda painter: None
    w.last_search_result = result2
    fit_view(w.canvas, 0.0, 25.0, -1.0, 9.0, margin=1.0)
    w.canvas.update()
    w.property_panel.update_from_window(w)
    grab(w, out_dir / "06_steeper_slope.png")

    # --- 07: Material editor showing soil parameters ---
    print("07_material_dialog: Material editor")
    dlg = MaterialDialog(parent=w, material=slope.material)
    dlg.resize(440, 340)
    dlg.show()
    grab(dlg, out_dir / "07_material_dialog.png")
    dlg.close()

    w.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
