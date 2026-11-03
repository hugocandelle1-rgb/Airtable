"""Réseau de N accéléromètres : retournement simultané, champ de pente, retournement motorisé,
apprentissage thermique, planification (simulateur du firmware, protocole v2)."""
import csv
import math

import pytest

from host.airtable_host import protocol as P
from host.airtable_host.client import AirtableClient
from host.airtable_host.sim import SimDevice
from host.airtable_host.tilt_calibration import (ArrayResult, DEFAULT_POSITIONS_MM, fit_bias_vs_temperature,
                                                 fit_slope_field, run_array_flip_procedure, run_motorized_flip,
                                                 schedule_flips)

CURV = (24.0, 6.0, -10.0)      # z_xx, z_xy, z_yy [µrad/m]


def make(n=4, **kw):
    dev = SimDevice(seed=kw.pop("seed", 5), n_sensors=n, tilt_noise_urad=kw.pop("noise", 6.0),
                    curvature=kw.pop("curvature", CURV), **kw)
    return dev, AirtableClient(transport=dev, timeout=1.0)


# ---- champ de pente (miroir des cas de test C++) --------------------------------------------------------

def test_champ_cuvette_et_selle_comme_le_firmware():
    pos = [DEFAULT_POSITIONS_MM[i] for i in range(4)]
    bowl = [(100 + 20 * x * 1e-3, -40 + 20 * y * 1e-3) for x, y in pos]
    f = fit_slope_field(pos, bowl)
    assert (f.zxx, f.zyy, f.zxy, f.curl) == pytest.approx((20.0, 20.0, 0.0, 0.0), abs=1e-6)
    assert f.mean_slope_urad == pytest.approx((100.0, -40.0))
    saddle = [(30 * y * 1e-3, 30 * x * 1e-3) for x, y in pos]
    f = fit_slope_field(pos, saddle)
    assert f.zxy == pytest.approx(30.0) and f.zxx == pytest.approx(0.0, abs=1e-9) and f.curl == pytest.approx(0.0, abs=1e-9)
    assert f.spread_urad[0] == pytest.approx(12.0)
    with pytest.raises(ValueError, match="alignés"):
        fit_slope_field([(0, 0), (100, 0), (200, 0)], [(1, 1), (2, 2), (3, 3)])
    with pytest.raises(ValueError):
        fit_slope_field(pos[:2], bowl[:2])


# ---- retournement manuel simultané ---------------------------------------------------------------------------

def test_retournement_simultane_de_quatre_capteurs():
    dev, client = make()
    cmds = []

    def prompt(msg):
        if msg.startswith("Retournez") or msg.startswith("Remettez"):
            for i in range(4):
                dev.rotate_sensor_180(i)

    res = run_array_flip_procedure(client, prompt, n_samples=200, hz=10, apply=True, save=True, out=lambda *_: None)
    assert isinstance(res, ArrayResult) and res.reliable and set(res.results) == {0, 1, 2, 3}
    for i, r in res.results.items():
        for a in (0, 1):
            assert r.bias_urad[a] == pytest.approx(dev.biases[i][a], abs=3 * r.bias_sigma_urad[a] + 0.5)
    # pente vraie au site = pente moyenne + courbure·position (la compensation du plan se fait ailleurs)
    f = res.slope_field
    assert f is not None
    assert f.zxx == pytest.approx(CURV[0], abs=2.0) and f.zyy == pytest.approx(CURV[2], abs=2.0)
    assert f.zxy == pytest.approx(CURV[1], abs=2.0)
    assert abs(f.curl) < 2.0                          # surface réelle : rotationnel nul
    assert f.mean_slope_urad == pytest.approx((120.0, -80.0), abs=2.0)
    # un biais par capteur a été envoyé avec son indice, puis SAVE
    sent = [l for l in dev.log if l.startswith("CAL TILT BIAS")]
    assert len(sent) == 4 and [l.split()[-1] for l in sent] == ["0", "1", "2", "3"]
    assert "SAVE" in dev.log
    for i in range(4):
        assert dev.cal[i]["bias"] == pytest.approx(list(res.results[i].bias_urad), abs=0.01)
    assert len(res.commands()) == 4


def test_retournement_simultane_refuse_si_derive():
    dev, client = make(noise=2.0)

    def prompt(msg):
        if msg.startswith("Retournez"):
            for i in range(4):
                dev.rotate_sensor_180(i)
        if msg.startswith("Remettez"):
            for i in range(4):
                dev.rotate_sensor_180(i)
            dev.biases[2][0] += 50.0                  # dérive d'un seul capteur

    with pytest.raises(RuntimeError, match="non fiable"):
        run_array_flip_procedure(client, prompt, n_samples=100, apply=True, out=lambda *_: None)
    assert not any(l.startswith("CAL TILT BIAS") for l in dev.log)


def test_collect_tilt_array_et_exclusion_de_capteur():
    dev, client = make()
    d = client.collect_tilt_array(20, sensors=(0, 2))
    assert set(d) == {0, 2} and all(len(v) == 20 for v in d.values())
    dev.biases[3] = [800.0, -600.0]                   # capteur aberrant
    fr = client.status()
    tilt_all = fr["tilt"]
    assert abs(tilt_all[0] - 120.0) < 40              # le rejet écarte l'aberrant (≥ 3 capteurs)
    client.tilt_use(1, False)
    assert client.status()["tu"] == 0b1101
    with pytest.raises(P.DeviceError) as e:
        client.command("CAL TILT USE 7 ON")           # indice > 3 : refusé par l'analyseur (même code que le firmware)
    assert e.value.err == "out_of_range"


def test_indice_de_capteur_inexistant_avec_un_seul_capteur():
    dev, client = make(n=1, curvature=(0, 0, 0))
    with pytest.raises(P.DeviceError) as e:
        client.cal_tilt_bias(1.0, 2.0, 2)
    assert e.value.err == "no_such_sensor"
    with pytest.raises(P.DeviceError) as e:
        client.tilt_use(3, True)
    assert e.value.err == "no_such_sensor"
    client.cal_tilt_bias(1.0, 2.0)                    # sans indice : tous (ici 1) les capteurs
    assert dev.cal[0]["bias"] == [1.0, 2.0]


# ---- retournement motorisé ---------------------------------------------------------------------------------

def test_retournement_motorise_applique_le_biais():
    dev, client = make(n=4, noise=4.0)
    res = run_motorized_flip(client, avg_s=20, apply=True, save=True, poll_s=0, out=lambda *_: None, sleep=lambda s: None)
    assert res.sensor == 0 and res.reliable
    assert res.bias_urad[0] == pytest.approx(35.0, abs=2.0) and res.bias_urad[1] == pytest.approx(-20.0, abs=2.0)
    # pente au site du capteur 0 : plan moyen + courbure à (−200, −200)
    sx = 120.0 + (CURV[0] * -200 + CURV[1] * -200) * 1e-3
    assert res.slope_a_urad[0] == pytest.approx(sx, abs=2.0)
    assert "FLIP RUN 20" in dev.log and "FLIP APPLY" in dev.log and "SAVE" in dev.log
    assert dev.cal[0]["bias"] == pytest.approx(list(res.bias_urad), abs=0.01)


def test_retournement_motorise_echec_et_absence_de_materiel():
    dev, client = make()
    dev.flip_fail = "actuator_timeout"
    with pytest.raises(RuntimeError, match="actuator_timeout"):
        run_motorized_flip(client, poll_s=0, out=lambda *_: None, sleep=lambda s: None)
    assert not any(l == "FLIP APPLY" for l in dev.log)
    dev2, client2 = make(has_flip=False)
    with pytest.raises(P.DeviceError) as e:
        run_motorized_flip(client2, poll_s=0, out=lambda *_: None, sleep=lambda s: None)
    assert e.value.err == "no_flip_hardware"


def test_planification_des_retournements(tmp_path):
    dev, client = make(n=4, temp_rate_k_s=0.0)
    clock = {"t": 1000.0}
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        clock["t"] += s

    log = tmp_path / "flips.csv"
    rows = schedule_flips(client, every_s=1800.0, count=3, avg_s=10, log_path=str(log), out=lambda *_: None,
                          sleep=sleep, now=lambda: clock["t"], poll_s=0)
    assert len(rows) == 3 and all(r["ok"] for r in rows)
    assert sum(1 for s in sleeps if s > 1000) == 2            # attente entre les retournements (début à début)
    with open(log, newline="", encoding="utf-8") as f:
        lines = list(csv.DictReader(f))
    assert len(lines) == 3 and float(lines[0]["bias_x"]) == pytest.approx(35.0, abs=3.0)
    # un échec n'interrompt pas la planification
    dev.flip_fail = "sensor_invalid"
    rows = schedule_flips(client, every_s=60.0, count=2, avg_s=10, out=lambda *_: None, sleep=sleep,
                          now=lambda: clock["t"], poll_s=0)
    assert [r["ok"] for r in rows] == [False, True]


# ---- thermique -------------------------------------------------------------------------------------------------

def test_apprentissage_thermique_et_compensation():
    k1 = [(60.0, -30.0), (45.0, 20.0), (-35.0, 10.0), (50.0, 50.0)]
    dev, client = make(n=4, noise=3.0, thermal_k1=k1, temp_rate_k_s=0.01)
    client.therm_start()
    for _ in client.stream(10.0, duration_s=400.0):         # 4 K d'excursion, 4 000 trames
        pass
    rep = client.therm_fit(1)
    assert len(rep["fit"]) == 4
    for row in rep["fit"]:
        i = int(row[0])
        assert row[1] == pytest.approx(k1[i][0], abs=2.5) and row[2] == pytest.approx(k1[i][1], abs=2.5)
        assert row[7] >= 3.5
    # après compensation, la sortie reste stable alors que la température continue de monter
    before = client.status()["tr"]
    for _ in client.stream(10.0, duration_s=300.0):
        pass
    after = client.status()["tr"]
    assert dev.T[0] > 26.0
    for a, b in zip(before, after):
        assert abs(a - b) < 6 * 3.0 / 1.0 + 3.0                # bruit seul (≪ 3 K × 60 µrad/K = 180 µrad sans compensation)
    cfg = client.config()
    assert cfg["th_ord"] == [1, 1, 1, 1] and cfg["th_c1"][0] == pytest.approx(k1[0][0], abs=2.5)


def test_apprentissage_thermique_refus_et_effacement():
    dev, client = make(n=2, curvature=(0, 0, 0))
    with pytest.raises(P.DeviceError) as e:
        client.therm_fit(1)
    assert e.value.err == "not_learning"
    client.therm_start()
    for _ in client.stream(10.0, duration_s=10.0):           # 100 trames, température constante
        pass
    with pytest.raises(P.DeviceError) as e:
        client.therm_fit(2)
    assert e.value.err == "span_too_small"
    client.therm_clear()
    assert client.config()["th_ord"] == [0, 0]


def test_biais_en_fonction_de_la_temperature_par_retournements():
    # sans compensation, le biais mesuré par retournement suit la dérive du capteur : c1 = 40 µrad/K
    dev, client = make(n=1, curvature=(0, 0, 0), thermal_k1=[(40.0, -25.0)], noise=2.0)
    pts = []
    for T in (21.0, 23.0, 25.0, 27.0, 24.0):
        dev.T[0] = T
        r = run_motorized_flip(client, avg_s=30, poll_s=0, out=lambda *_: None, sleep=lambda s: None)
        pts.append((r.t_mean_c, *r.bias_urad))
    fit = fit_bias_vs_temperature(pts, order=1)
    assert fit["c1_x"] == pytest.approx(40.0, abs=0.7) and fit["c1_y"] == pytest.approx(-25.0, abs=0.7)
    with pytest.raises(ValueError):
        fit_bias_vs_temperature(pts[:2], order=1)
    with pytest.raises(ValueError):
        fit_bias_vs_temperature([(20.0, 1, 1)] * 5, order=1)


# ---- télémétrie / CSV -------------------------------------------------------------------------------------------

def test_aplatissement_des_champs_du_reseau():
    dev, client = make()
    fr = P.flatten(client.status())
    assert set(fr) == set(P.CSV_FIELDS)
    assert fr["tn"] == 4 and fr["flip"] == "idle"
    assert fr["tc2_x"] is not None and fr["tr3_y"] is not None and fr["Tb1"] == pytest.approx(22.0)
    assert fr["crv_xx"] == CURV[0] and fr["dsp_x"] is not None
    assert math.isfinite(fr["tilt_x"])
