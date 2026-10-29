"""Client + simulateur du firmware + journal CSV."""
import csv
import json

import pytest

from host.airtable_host import protocol as P
from host.airtable_host.client import AirtableClient, interpolate_setpoint, read_setpoints
from host.airtable_host.logger import CsvLogger, HEADER
from host.airtable_host.sim import SimDevice

SETPOINTS = {"h_target_um": 120.0, "points": [{"mass_g": 2.0, "p_Pa": 50.0}, {"mass_g": 10.0, "p_Pa": 300.0},
                                              {"mass_g": 5.0, "p_Pa": 130.0}]}


@pytest.fixture
def client():
    with AirtableClient(transport=SimDevice(seed=3), timeout=1.0) as c:
        yield c


def test_ping_version_status(client):
    assert client.ping()["ok"]
    assert client.version()["proto"] == 1
    st = client.status()
    assert st["ok"] and "t" in st and len(st["p"]) == 5


def test_device_error_raised(client):
    with pytest.raises(P.DeviceError) as e:
        client.set_pressure(5.0)          # hors plage 30..400
    assert e.value.err == "out_of_range"
    with pytest.raises(P.DeviceError) as e:
        client.set_mass(5.0)              # pas de table
    assert e.value.err == "no_table"
    r = client.command("FOO", raise_on_error=False)
    assert r == {"ok": False, "err": "unknown_command"}


def test_table_load_and_set_mass(client, tmp_path):
    f = tmp_path / "sp.json"
    f.write_text(json.dumps(SETPOINTS))
    assert client.load_setpoints(f) == 3
    r = client.set_mass(3.5)               # entre 2 g (50) et 5 g (130) : 50 + 0,5·80 = 90
    assert r["p"] == pytest.approx(90.0)
    assert client.status()["st"] == "run"
    tab = client.command("GET TABLE")
    assert tab["h_um"] == 120.0 and tab["points"][0] == [2.0, 50.0]


def test_interpolation_miroir_firmware(tmp_path):
    f = tmp_path / "sp.json"
    f.write_text(json.dumps(SETPOINTS))
    h, pts = read_setpoints(f)
    assert h == 120.0 and [m for m, _ in pts] == [2.0, 5.0, 10.0]     # trié
    assert interpolate_setpoint(pts, 3.5) == pytest.approx(90.0)
    assert interpolate_setpoint(pts, 1.0) == 50.0                       # saturation basse
    assert interpolate_setpoint(pts, 50.0) == 300.0                     # saturation haute
    assert interpolate_setpoint(pts, 7.5) == pytest.approx(215.0)


def test_setpoints_invalides(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"points": [{"mass_g": 2, "p_Pa": 1}, {"mass_g": 2, "p_Pa": 2}]}))
    with pytest.raises(ValueError):
        read_setpoints(f)
    f.write_text(json.dumps({"points": []}))
    with pytest.raises(ValueError):
        read_setpoints(f)


def test_stream_et_arret(client):
    frames = list(client.stream(hz=20, count=10))
    assert len(frames) == 10
    ts = [fr["t"] for fr in frames]
    assert all(b > a for a, b in zip(ts, ts[1:]))
    assert client.status()["ok"]          # le flux est bien arrêté (la réponse n'est pas noyée)


def test_stream_duree_horloge_firmware(client):
    frames = list(client.stream(hz=10, duration_s=2.0))
    assert 20 <= len(frames) <= 22


def test_telemetrie_recue_pendant_une_commande(client):
    client._t.write(b"STREAM ON 10\n")
    client._t.readline()                    # ok
    r = client.command("PING")              # des trames de flux s'intercalent avant la réponse
    assert r["ok"] and client.bad_lines == 0


def test_collect_tilt_raw(client):
    s = client.collect_tilt_raw(50, hz=10)
    assert len(s) == 50
    mx = sum(a for a, _ in s) / len(s)
    assert mx == pytest.approx(120.0 + 35.0, abs=3.0)     # pente vraie + biais du simulateur


def test_level_requires_home(client):
    with pytest.raises(P.DeviceError) as e:
        client.level_move("X", 10)
    assert e.value.err == "not_homed"
    client.level_home()
    assert client.level_move("X", 10)["ok"]
    client.level_auto(True)
    assert client.status()["auto"] is True


def test_logger_csv(tmp_path, client):
    path = tmp_path / "log.csv"
    with CsvLogger(path, flush_every=1) as log:
        n = log.write_all(client.stream(hz=10, count=5))
    assert n == 5
    rows = list(csv.DictReader(open(path)))
    assert len(rows) == 5 and list(rows[0].keys()) == HEADER
    assert rows[0]["time_utc"].endswith("Z") and rows[0]["time_utc"][4] == "-"
    assert float(rows[1]["t_ms"]) > float(rows[0]["t_ms"])
    assert rows[0]["p0"] != "" and rows[0]["disp0"] == ""        # champ absent → cellule vide
