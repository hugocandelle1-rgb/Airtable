"""Export de la carte de pente / efforts parasites : JSON, CSV, conventions de signe, relecture par le consommateur."""
import csv
import json
import math

import numpy as np
import pytest

from host.airtable_host import drift_calibration as dc
from host.airtable_host import slope_export as se
from host.airtable_host.cli import main as cli_main
from host.tests.test_drift_calibration import G, synth, theta_field

URAD_TO_MM_S2 = G * 1000.0 * 1e-6


@pytest.fixture(scope="module")
def analysis():
    return dc.analyze(synth(n=80, seed=4, T=3.0, sigma=0.03), damping="none", fix_v0=0.0, poly_order=2,
                      extent_mm=(-150, 150, -150, 150), g=G)


def test_grille_champ_reproduit_la_pente_vraie(analysis):
    grid = se.build_slope_grid(analysis, 7, 5, (-120, 120, -100, 100), source="field", g=G)
    assert grid.theta_x_urad.shape == (5, 7) and grid.valid.all()
    X, Y = np.meshgrid(grid.x_mm, grid.y_mm)
    tx, ty = theta_field(X, Y)
    assert np.max(np.abs(grid.theta_x_urad - tx)) < 4.0
    assert np.max(np.abs(grid.theta_y_urad - ty)) < 4.0
    # accélération de perturbation : a = g·θ en mm/s² (θ > 0 : dérive vers +x)
    assert grid.a_x_mm_s2[2, 3] == pytest.approx(grid.theta_x_urad[2, 3] * URAD_TO_MM_S2, rel=1e-9)
    assert grid.a_x_mm_s2[2, 3] > 0                       # θ(0,0) = +60 µrad
    assert np.all(np.isfinite(grid.sigma_x_urad)) and grid.sigma_x_urad.max() < 5.0


def test_plan_corrige_retranche_la_correction(analysis):
    raw = se.build_slope_grid(analysis, 5, 5, source="field", plane="raw", g=G)
    cor = se.build_slope_grid(analysis, 5, 5, source="field", plane="corrected", g=G)
    d = analysis.correction.d_slope_urad
    assert cor.correction_applied_urad == pytest.approx(d)
    assert np.allclose(raw.theta_x_urad - cor.theta_x_urad, d[0]) and np.allclose(raw.theta_y_urad - cor.theta_y_urad, d[1])
    # la pente moyenne de la grille corrigée est ≈ 0 (correction « plan moyen »)
    assert abs(cor.stats()["theta_mean_urad"][0]) < 3.0 and abs(cor.stats()["theta_mean_urad"][1]) < 3.0
    assert raw.stats()["theta_rms_urad"] > cor.stats()["theta_rms_urad"]


def test_source_carte_cellules_vides_invalides():
    rng = np.random.default_rng(1)
    from host.tests.test_drift_calibration import make_traj
    trajs = []
    for i, (x0, y0) in enumerate([(-100, -100), (100, -100), (-100, 100), (100, 100), (0, 100), (100, 0)]):
        trajs.append(make_traj(rng, i, x0, y0, theta_field(x0, y0)))
    an = dc.analyze(trajs, damping="none", fix_v0=0.0, grid=(3, 3), poly_order=1, extent_mm=(-150, 150, -150, 150), g=G)
    grid = se.build_slope_grid(an, 9, 9, (-150, 150, -150, 150), source="map", g=G)
    assert grid.source == "map" and grid.valid.any() and not grid.valid.all()
    assert np.all(np.isnan(grid.theta_x_urad[~grid.valid]))


def test_extrapolation_signalee(analysis):
    far = se.build_slope_grid(analysis, 5, 5, (-600, 600, -600, 600), source="field", g=G)
    assert not far.valid.all() and any("extrapolation" in w for w in far.warnings)


def test_json_format_et_nan(analysis, tmp_path):
    grid = se.build_slope_grid(analysis, 4, 3, source="field", g=G)
    grid.theta_x_urad[0, 0] = np.nan                       # valeur manquante → null, JSON strict
    grid.valid[0, 0] = False
    path = tmp_path / "carte.json"
    se.export(grid, path, "json")
    data = json.loads(path.read_text(encoding="utf-8"))   # json strict (pas de NaN)
    assert data["format"] == "airtable-slope-map" and data["format_version"] == 1
    assert data["units"]["accel"] == "mm/s^2" and data["frame"] == "plate" and data["g_m_s2"] == G
    assert data["grid"]["nx"] == 4 and data["grid"]["ny"] == 3 and len(data["grid"]["x_mm"]) == 4
    f = data["fields"]
    assert set(f) == {"theta_x_urad", "theta_y_urad", "sigma_x_urad", "sigma_y_urad", "a_x_mm_s2", "a_y_mm_s2", "valid"}
    assert len(f["theta_x_urad"]) == 3 and len(f["theta_x_urad"][0]) == 4
    assert f["theta_x_urad"][0][0] is None and f["valid"][0][0] is False
    assert "F = m*a" in data["conventions"] and "-m*a" in data["conventions"]
    assert data["stats"]["n_valid"] == 11


def test_csv_format(analysis, tmp_path):
    grid = se.build_slope_grid(analysis, 4, 3, source="field", g=G)
    path = tmp_path / "carte.csv"
    se.export(grid, path, "csv")
    text = path.read_text(encoding="utf-8").splitlines()
    assert text[0].startswith("# format: airtable-slope-map 1")
    body = [l for l in text if not l.startswith("#")]
    rows = list(csv.DictReader(body))
    assert list(rows[0]) == se.CSV_COLUMNS and len(rows) == 12
    # ordre : y croissant en boucle externe, x croissant en boucle interne
    assert [float(r["x_mm"]) for r in rows[:4]] == pytest.approx(list(grid.x_mm), abs=1e-3)
    assert float(rows[4]["y_mm"]) == pytest.approx(grid.y_mm[1], abs=1e-3)
    r = rows[5]
    assert float(r["a_x_mm_s2"]) == pytest.approx(float(r["theta_x_urad"]) * URAD_TO_MM_S2, rel=2e-3)
    both = se.export(grid, tmp_path / "x.dat", "both")
    assert [p.suffix for p in both] == [".json", ".csv"]
    with pytest.raises(ValueError):
        se.export(grid, tmp_path / "y", "xml")


def test_relecture_et_anticipation(analysis, tmp_path):
    grid = se.build_slope_grid(analysis, 31, 31, source="field", g=G)
    path = tmp_path / "carte.json"
    se.write_json(grid, path)
    m = se.SlopeMapField.load(path)
    tx, ty = m.theta_urad(20.0, -35.0)
    ex, ey = theta_field(20.0, -35.0)
    assert tx == pytest.approx(ex, abs=4.0) and ty == pytest.approx(ey, abs=4.0)
    ax, ay = m.disturbance_accel_mm_s2(20.0, -35.0)
    assert ax == pytest.approx(tx * URAD_TO_MM_S2, rel=1e-9)
    # palet de 0,5 kg : F_ff = −m·a (N), de signe opposé à la dérive
    fx, fy = m.feedforward_force_N(0.5, 20.0, -35.0)
    assert fx == pytest.approx(-0.5 * ax * 1e-3, rel=1e-9) and fx < 0 < ax
    assert math.isnan(m.theta_urad(0.0, 0.0)[0]) is False
    with pytest.raises(ValueError):
        se.SlopeMapField({"format": "autre"})
    with pytest.raises(ValueError):
        se.build_slope_grid(analysis, 3, 3, source="nimporte")
    with pytest.raises(ValueError):
        se.build_slope_grid(analysis, 3, 3, plane="nimporte")


def test_cli_slope_export(tmp_path, capsys):
    trajs = synth(n=50, seed=9, T=3.0, sigma=0.03)
    src = tmp_path / "lachers.csv"
    dc.write_trajectories_csv(src, trajs)
    out = tmp_path / "carte.json"
    rc = cli_main(["slope-export", str(src), "-o", str(out), "--grid-out", "9x9", "--damping", "none", "--fix-v0", "0",
                   "--poly-order", "2", "--plane", "corrected", "--format", "both"])
    assert rc == 0
    assert out.exists() and out.with_suffix(".csv").exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["plane"] == "corrected" and data["grid"]["nx"] == 9
    assert "accélération crête" in capsys.readouterr().out
