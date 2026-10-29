"""Calibration par palets : ajustement, amortissement, carte, correction, conventions de signe."""
import math

import numpy as np
import pytest

from host.airtable_host import drift_calibration as dc

G = 9.81
URAD_TO_MM_S2 = G * 1000.0 * 1e-6          # 1 µrad ↔ 0,00981 mm/s²


def theta_field(x, y):
    """Pente de dérive vraie [µrad] (descendante vers +x/+y), irrotationnelle : dérive d'un potentiel."""
    c = 0.02
    return 60.0 + 0.08 * x + c * y, -40.0 + c * x + 0.05 * y


def make_traj(rng, i, x0, y0, th, T=2.5, fps=30.0, sigma=0.05, v0=(0.0, 0.0), tau=math.inf, outliers=0):
    t = np.arange(0.0, T, 1.0 / fps)
    a = np.array(th) * URAD_TO_MM_S2        # mm/s²
    k = 0.0 if math.isinf(tau) else 1.0 / tau
    p1, p2 = dc._phi(t, k)
    x = x0 + v0[0] * p1 + a[0] * p2 + rng.normal(0, sigma, t.size)
    y = y0 + v0[1] * p1 + a[1] * p2 + rng.normal(0, sigma, t.size)
    for j in rng.choice(t.size, outliers, replace=False) if outliers else []:
        x[j] += 3.0
    return dc.Trajectory(f"d{i}", t + 100.0, x, y)      # t0 ≠ 0 : le code doit recaler


def synth(n=60, seed=0, **kw):
    rng = np.random.default_rng(seed)
    trajs = []
    for i in range(n):
        x0, y0 = rng.uniform(-135, 135, 2)
        trajs.append(make_traj(rng, i, x0, y0, theta_field(x0, y0), **kw))
    return trajs


def test_ajustement_parabole_sans_amortissement():
    rng = np.random.default_rng(1)
    tr = make_traj(rng, 0, 10.0, -5.0, (50.0, -30.0), T=3.0, sigma=0.03, v0=(0.2, 0.1))
    f = dc.fit_trajectory(tr)
    assert f.ok and f.k == 0.0
    # 50 µrad = 0,4905 mm/s²
    assert f.theta_x_urad == pytest.approx(50.0, abs=4 * f.sigma_theta_x_urad)
    assert f.theta_y_urad == pytest.approx(-30.0, abs=4 * f.sigma_theta_y_urad)
    assert f.x.x0 == pytest.approx(10.0, abs=4 * f.x.sigma_x0)
    assert f.x.v0 == pytest.approx(0.2, abs=4 * f.x.sigma_v0)
    assert f.sigma_theta_x_urad == pytest.approx(dc.expected_sigma_theta_urad(3.0, 90, 0.03), rel=0.3)
    assert f.x.rms == pytest.approx(0.03, rel=0.25)


def test_lacher_sans_vitesse_ameliore_la_precision():
    rng = np.random.default_rng(2)
    tr = make_traj(rng, 0, 0.0, 0.0, (80.0, 20.0), T=2.5, sigma=0.05)
    free = dc.fit_trajectory(tr)
    fixed = dc.fit_trajectory(tr, fix_v0=0.0)
    assert fixed.sigma_theta_x_urad < free.sigma_theta_x_urad / 2
    assert fixed.theta_x_urad == pytest.approx(80.0, abs=4 * fixed.sigma_theta_x_urad)
    assert fixed.x.v0 == 0.0


def test_amortissement_biais_si_ignore_et_recupere_si_estime():
    rng = np.random.default_rng(3)
    tau = 12.0
    tr = make_traj(rng, 0, 0.0, 0.0, (200.0, -150.0), T=6.0, fps=40.0, sigma=0.01, tau=tau)
    none = dc.fit_trajectory(tr, damping="none", fix_v0=0.0)
    fit = dc.fit_trajectory(tr, damping="fit", fix_v0=0.0)
    forced = dc.fit_trajectory(tr, damping=tau, fix_v0=0.0)
    assert abs(none.theta_x_urad - 200.0) > 15.0                      # ignorer l'amortissement biaise a
    assert fit.k_fitted and fit.tau_s == pytest.approx(tau, rel=0.3)
    assert fit.theta_x_urad == pytest.approx(200.0, abs=max(4 * fit.sigma_theta_x_urad, 1.0))
    assert fit.sigma_theta_x_urad >= forced.sigma_theta_x_urad       # incertitude sur τ répercutée
    assert forced.theta_x_urad == pytest.approx(200.0, abs=4 * forced.sigma_theta_x_urad)
    assert forced.theta_y_urad == pytest.approx(-150.0, abs=4 * forced.sigma_theta_y_urad)


def test_pas_damortissement_retenu_sans_evidence():
    rng = np.random.default_rng(4)
    tr = make_traj(rng, 0, 0.0, 0.0, (60.0, 10.0), T=3.0, sigma=0.05)
    f = dc.fit_trajectory(tr, damping="fit", fix_v0=0.0)
    assert not f.k_fitted and f.k == 0.0 and math.isinf(f.tau_s)


def test_valeurs_aberrantes_rejetees():
    rng = np.random.default_rng(5)
    tr = make_traj(rng, 0, 0.0, 0.0, (70.0, 0.0), T=3.0, sigma=0.03, outliers=4)
    robust = dc.fit_trajectory(tr, fix_v0=0.0)
    plain = dc.fit_trajectory(tr, fix_v0=0.0, robust=False)
    assert robust.n_used < robust.n_total
    assert abs(robust.theta_x_urad - 70.0) < abs(plain.theta_x_urad - 70.0)
    assert robust.theta_x_urad == pytest.approx(70.0, abs=4 * robust.sigma_theta_x_urad)


def test_trajectoire_trop_courte():
    tr = dc.Trajectory("c", [0, 1, 2], [0, 1, 2], [0, 0, 0])
    f = dc.fit_trajectory(tr)
    assert not f.ok and "trop peu" in f.reason


def test_fenetre_temporelle():
    rng = np.random.default_rng(6)
    tr = make_traj(rng, 0, 0.0, 0.0, (100.0, 0.0), T=4.0, sigma=0.02)
    f = dc.fit_trajectory(tr, t_min=1.0, t_max=3.0)
    assert 55 <= f.n_total <= 62 and f.duration_s == pytest.approx(2.0, abs=0.1)
    assert f.theta_x_urad == pytest.approx(100.0, abs=4 * f.sigma_theta_x_urad)


def test_signe_theta_et_correction():
    """Palet qui dérive vers +x : θx > 0, la plaque descend vers +x ; correction = +θ (relever +x)."""
    rng = np.random.default_rng(7)
    trajs = [make_traj(rng, i, *rng.uniform(-100, 100, 2), (45.0, -25.0), sigma=0.03) for i in range(20)]
    an = dc.analyze(trajs, damping="none", fix_v0=0.0, poly_order=1)
    c = an.correction
    assert all(f.x.a > 0 for f in an.fits)                                  # dérive vers +x
    assert c.d_slope_urad[0] == pytest.approx(45.0, abs=1.0)
    assert c.d_slope_urad[1] == pytest.approx(-25.0, abs=1.0)
    assert c.level_move_commands() == [f"LEVEL MOVE X {c.d_slope_urad[0]:.2f}",
                                       f"LEVEL MOVE Y {c.d_slope_urad[1]:.2f}"]
    assert c.level_target_command((2.0, 1.0)) == \
        f"LEVEL TARGET {2.0 + c.d_slope_urad[0]:.2f} {1.0 + c.d_slope_urad[1]:.2f}"
    assert c.residual_peak_urad < 2.0                                       # plan pur : rien de non plan
    # champ de hauteur : le gradient de surface est l'opposé de θ
    gx, gy = an.height_field.surface_gradient_urad([0.0], [0.0])
    assert gx[0] == pytest.approx(-45.0, abs=1.0) and gy[0] == pytest.approx(25.0, abs=1.0)


def test_analyse_complete_champ_non_plan():
    trajs = synth(n=80, seed=10, sigma=0.04)
    an = dc.analyze(trajs, damping="none", fix_v0=0.0, grid=(5, 5), poly_order=2)
    c = an.correction
    # moyenne du champ sur le carré 300×300 centré : (60, −40)
    assert c.method == "field"
    assert c.d_slope_urad[0] == pytest.approx(60.0, abs=3 * c.sigma_urad[0] + 0.3)
    assert c.d_slope_urad[1] == pytest.approx(-40.0, abs=3 * c.sigma_urad[1] + 0.3)
    assert c.sigma_urad[0] < 1.0
    # pente non plane : θ − θ_moyen = (0,08x + 0,02y ; 0,02x + 0,05y) sur |x|,|y| ≤ 150 → crête ≈ √(14,4²+9²)
    assert c.residual_peak_urad == pytest.approx(math.hypot(0.08 * 150 + 0.02 * 150, 0.02 * 150 + 0.05 * 150), rel=0.1)
    assert c.residual_rms_urad < c.residual_peak_urad
    # la méthode par échantillons (moyenne pondérée) donne la même correction à l'incertitude près
    c2 = dc.plan_correction(an.samples, None, method="samples")
    assert c2.d_slope_urad[0] == pytest.approx(60.0, abs=3 * c2.sigma_urad[0] + 2.0)
    # carte : cellule centrale ≈ pente en (0,0) = (60, −40)
    m = an.slope_map
    assert m.count.sum() == len(an.samples) and m.theta_x.shape == (5, 5)
    assert m.theta_x[2, 2] == pytest.approx(60.0, abs=4.0)
    assert m.theta_y[2, 2] == pytest.approx(-40.0, abs=4.0)
    # les coins reflètent le gradient : en (+120,+120) θx ≈ 60 + 0,08·120 + 0,02·120 = 72
    assert m.theta_x[4, 4] == pytest.approx(72.0, abs=5.0)
    txt = dc.format_report(an)
    assert "LEVEL MOVE X" in txt and "LEVEL TARGET" in txt and "cible crête" in txt


def test_champ_hauteur_reconstruit_la_forme():
    trajs = synth(n=80, seed=11, sigma=0.03)
    an = dc.analyze(trajs, damping="none", fix_v0=0.0, poly_order=2)
    hf = an.height_field
    # le gradient ajusté colle au champ vrai (surface = −θ) en quelques points
    for (x, y) in [(-100, -100), (0, 0), (100, -50), (120, 120)]:
        gx, gy = hf.surface_gradient_urad([x], [y])
        tx, ty = theta_field(x, y)
        assert gx[0] == pytest.approx(-tx, abs=1.5) and gy[0] == pytest.approx(-ty, abs=1.5)
    # hauteur : z(x,y) = −(60x −40y + 0,04x² + 0,02xy + 0,025y²)·1e-3 mm → en µm : relative à (0,0)
    h = hf.height_um([100.0], [0.0]) - hf.height_um([0.0], [0.0])
    assert h[0] == pytest.approx(-(60 * 100 + 0.04 * 100 ** 2) * 1e-6 * 1e3, rel=0.03)   # µrad·mm = nm → µm


def test_critere_crete_reduit_la_pente_maximale():
    trajs = synth(n=80, seed=12, sigma=0.04)
    an_m = dc.analyze(trajs, damping="none", fix_v0=0.0, poly_order=2, criterion="mean")
    an_p = dc.analyze(trajs, damping="none", fix_v0=0.0, poly_order=2, criterion="peak")
    assert an_p.correction.residual_peak_urad <= an_m.correction.residual_peak_urad + 1e-6
    assert an_p.correction.residual_rms_urad >= an_m.correction.residual_rms_urad - 1e-6


def test_repere_camera_rotation_et_miroir():
    # Caméra tournée de 90° : x_plaque = −y_cam ... on fabrique les trajectoires dans le repère plaque
    # puis on les exprime en repère caméra ; analyze(frame) doit retrouver la correction plaque.
    rng = np.random.default_rng(13)
    plate = [make_traj(rng, i, *rng.uniform(-100, 100, 2), (45.0, -25.0), sigma=0.03) for i in range(15)]
    frame = dc.CameraFrame(rot_deg=90.0, flip_y=True, origin_mm=(3.0, -2.0))
    M = frame.matrix()
    cam = []
    for tr in plate:
        p_plate = np.stack([tr.x, tr.y], axis=1)
        p_cam = p_plate @ np.linalg.inv(M).T + np.asarray(frame.origin_mm)
        cam.append(dc.Trajectory(tr.id, tr.t, p_cam[:, 0], p_cam[:, 1]))
    wrong = dc.analyze(cam, damping="none", fix_v0=0.0, poly_order=1)
    right = dc.analyze(cam, damping="none", fix_v0=0.0, poly_order=1, frame=frame)
    assert right.correction.d_slope_urad[0] == pytest.approx(45.0, abs=1.5)
    assert right.correction.d_slope_urad[1] == pytest.approx(-25.0, abs=1.5)
    assert abs(wrong.correction.d_slope_urad[0] - 45.0) > 10.0      # sans le bon repère, le résultat est faux


def test_csv_aller_retour_et_formats(tmp_path):
    trajs = synth(n=3, seed=20)
    f = tmp_path / "t.csv"
    dc.write_trajectories_csv(f, trajs)
    back = dc.load_trajectories_csv(f)
    assert [t.id for t in back] == [t.id for t in trajs]
    assert np.allclose(back[1].x, trajs[1].x, atol=1e-5)
    # variantes : séparateur « ; », temps en ms, colonne sans id, NaN ignorés
    g = tmp_path / "u.csv"
    g.write_text("t_ms;x_mm;y_mm\n0;1;2\n100;1.5;2\n200;nan;2\n300;2.5;2.1\n")
    one = dc.load_trajectories_csv(g)
    assert len(one) == 1 and len(one[0]) == 3 and one[0].t[-1] == pytest.approx(0.3)
    h = tmp_path / "v.csv"
    h.write_text("frame,x,y\n0,10,10\n1,11,10\n")
    with pytest.raises(ValueError, match="fps"):
        dc.load_trajectories_csv(h)
    px = dc.load_trajectories_csv(h, fps=50.0, scale=0.2)
    assert px[0].t[1] == pytest.approx(0.02) and px[0].x[1] == pytest.approx(2.2)
    bad = tmp_path / "w.csv"
    bad.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError, match="colonnes"):
        dc.load_trajectories_csv(bad)


def test_precision_theorique_decroit_avec_la_duree():
    s1 = dc.expected_sigma_theta_urad(1.0, 30, 0.05, fix_v0=0.0)
    s3 = dc.expected_sigma_theta_urad(3.0, 90, 0.05, fix_v0=0.0)
    assert s3 < s1 / 10
    assert dc.expected_sigma_theta_urad(3.0, 90, 0.05) > s3          # v0 libre : moins précis


def test_aucune_trajectoire_exploitable():
    tr = dc.Trajectory("c", [0, 1, 2], [0, 1, 2], [0, 0, 0])
    with pytest.raises(ValueError, match="exploitable"):
        dc.analyze([tr])


def test_video_optionnelle(tmp_path):
    cv2 = pytest.importorskip("cv2")
    # Vidéo synthétique : un disque clair qui accélère vers +x sur fond sombre (0,2 mm/px, 30 i/s)
    W, H, fps, s = 320, 240, 30.0, 0.2
    path = tmp_path / "d.avi"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (W, H))
    a_mm = 150.0 * URAD_TO_MM_S2 * 40            # accélération exagérée pour être visible en pixels
    for i in range(60):
        t = i / fps
        x_px = W / 2 - 30 + 0.5 * a_mm * t ** 2 / s
        img = np.zeros((H, W, 3), np.uint8)
        cv2.circle(img, (int(round(x_px)), H // 2), 12, (255, 255, 255), -1, lineType=cv2.LINE_AA)
        vw.write(img)
    vw.release()
    trajs = dc.track_pucks_video(path, mm_per_px=s)
    assert len(trajs) == 1 and len(trajs[0]) >= 55
    f = dc.fit_trajectory(trajs[0], fix_v0=0.0)
    assert f.x.a == pytest.approx(a_mm, rel=0.15)           # int() au pixel près : tolérance large
