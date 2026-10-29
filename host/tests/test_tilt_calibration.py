"""Calibration de l'inclinomètre par retournement de 180°."""
import math
import random

import pytest

from host.airtable_host.client import AirtableClient
from host.airtable_host.sim import SimDevice
from host.airtable_host.tilt_calibration import flip_calibration, run_flip_procedure, series_stats


def series(rng, mean, sigma, n):
    return [(rng.gauss(mean[0], sigma), rng.gauss(mean[1], sigma)) for _ in range(n)]


def test_biais_et_pente_exacts_sans_bruit():
    a = [(155.0, -100.0)] * 5               # s = (120, -80), b = (35, -20)
    b = [(-85.0, 60.0)] * 5
    r = flip_calibration(a, b)
    assert r.bias_urad == pytest.approx((35.0, -20.0))
    assert r.slope_a_urad == pytest.approx((120.0, -80.0))
    assert r.command() == "CAL TILT BIAS 35 -20"


def test_statistique_avec_bruit():
    rng = random.Random(5)
    s, b = (120.0, -80.0), (35.0, -20.0)
    res = flip_calibration(series(rng, (s[0] + b[0], s[1] + b[1]), 20.0, 400),
                           series(rng, (-s[0] + b[0], -s[1] + b[1]), 20.0, 400))
    for i in (0, 1):
        assert abs(res.bias_urad[i] - b[i]) < 4 * res.bias_sigma_urad[i]
        assert abs(res.slope_a_urad[i] - s[i]) < 4 * res.slope_sigma_urad[i]
    # σ_biais = ½·√(2)·σ/√n = 0,707·20/20 = 0,71 µrad
    assert res.bias_sigma_urad[0] == pytest.approx(0.5 * math.sqrt(2) * 20 / 20, rel=0.2)
    assert res.reliable


def test_derive_detectee():
    rng = random.Random(1)
    a = series(rng, (155.0, -100.0), 5.0, 100)
    b = series(rng, (-85.0, 60.0), 5.0, 100)
    a2 = series(rng, (175.0, -100.0), 5.0, 100)          # +20 µrad de dérive sur X
    r = flip_calibration(a, b, a2)
    assert not r.reliable and any("dérive sur l'axe X" in w for w in r.warnings)
    assert r.drift_urad[0] == pytest.approx(20.0, abs=3.0)
    ok = flip_calibration(a, b, series(rng, (155.0, -100.0), 5.0, 100))
    assert ok.reliable


def test_garde_fous():
    with pytest.raises(ValueError):
        flip_calibration([(1.0, 1.0)], [(0.0, 0.0), (1.0, 1.0)])
    r = flip_calibration([(30000.0, 0.0), (30001.0, 0.0)], [(30000.0, 1.0), (30002.0, 0.0)])
    assert any("anormalement grand" in w for w in r.warnings)


def test_procedure_complete_avec_simulateur():
    dev = SimDevice(seed=11, true_slope=(120.0, -80.0), sensor_bias=(35.0, -20.0), tilt_noise_urad=8.0)
    client = AirtableClient(transport=dev, timeout=1.0)
    steps = []

    def prompt(msg):
        steps.append(msg[:10])
        if msg.startswith("Retournez") or msg.startswith("Remettez"):
            dev.rotate_sensor_180()

    res = run_flip_procedure(client, prompt, n_samples=200, hz=10, with_return=True, apply=True, save=True,
                             out=lambda *_: None)
    assert len(steps) == 3
    assert res.bias_urad[0] == pytest.approx(35.0, abs=3 * res.bias_sigma_urad[0] + 0.5)
    assert res.bias_urad[1] == pytest.approx(-20.0, abs=3 * res.bias_sigma_urad[1] + 0.5)
    assert res.slope_a_urad[0] == pytest.approx(120.0, abs=3 * res.slope_sigma_urad[0] + 0.5)
    # le biais a été envoyé au (simulateur de) firmware
    assert dev.cal_bias == pytest.approx([res.bias_urad[0], res.bias_urad[1]], abs=0.01)
    assert any(l.startswith("CAL TILT BIAS") for l in dev.log) and "SAVE" in dev.log


def test_procedure_refuse_resultat_non_fiable():
    dev = SimDevice(seed=2, tilt_noise_urad=2.0)
    client = AirtableClient(transport=dev, timeout=1.0)
    n = {"k": 0}

    def prompt(msg):
        n["k"] += 1
        if msg.startswith("Retournez"):
            dev.rotate_sensor_180()
        if msg.startswith("Remettez"):
            dev.rotate_sensor_180()
            dev.sensor_bias[0] += 60.0          # dérive du biais pendant la procédure

    with pytest.raises(RuntimeError, match="non fiable"):
        run_flip_procedure(client, prompt, n_samples=100, apply=True, out=lambda *_: None)
    assert not any(l.startswith("CAL TILT BIAS") for l in dev.log)
