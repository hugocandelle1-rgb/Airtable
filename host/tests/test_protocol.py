"""Protocole : construction des commandes, miroir du parseur C++, aplatissement des trames."""
import pytest

from host.airtable_host import protocol as P

VALID = [
    ("PING", "Ping"), ("GET STATUS", "GetStatus"), ("get config", "GetConfig"), ("GET VERSION", "GetVersion"),
    ("SET P 120.0", "SetP"), ("  set   p   87.5  ", "SetP"), ("SET P 1e2", "SetP"), ("SET MASS 5.0", "SetMass"),
    ("SET DUTY 0.35", "SetDuty"), ("SET GAINS 0.8 1.0", "SetGains"), ("SET NOZZLE 0.97 20", "SetNozzle"),
    ("LEVEL AUTO ON", "LevelAuto"), ("level auto off", "LevelAuto"), ("LEVEL MOVE X -25.5", "LevelMove"),
    ("LEVEL MOVE y 100", "LevelMove"), ("LEVEL JOG B 50", "LevelJog"), ("LEVEL ZERO", "LevelZero"),
    ("LEVEL HOME", "LevelHome"), ("LEVEL TARGET 12 -3.5", "LevelTarget"), ("STREAM ON 10", "StreamOn"),
    ("STREAM ON", "StreamOn"), ("STREAM OFF", "StreamOff"), ("TABLE ADD 2.0 70.5", "TableAdd"),
    ("TABLE CLEAR", "TableClear"), ("CAL TILT BIAS 12.5 -8", "CalTiltBias"), ("CAL PZERO", "CalPZero"),
    ("FAN ON", "FanOn"), ("FAN OFF", "FanOff"), ("CLEAR", "Clear"), ("SAFE", "Safe"),
]
INVALID = [
    ("", "empty"), ("FOO", "unknown_command"), ("GET", "missing_argument"), ("SET P", "missing_argument"),
    ("SET P 100 200", "extra_argument"), ("SET P abc", "bad_number"), ("SET P 12x", "bad_number"),
    ("SET P nan", "bad_number"), ("SET P inf", "bad_number"), ("SET P -5", "out_of_range"),
    ("SET P 99999", "out_of_range"), ("SET P 0x10", "bad_number"), ("SET P 1_0", "bad_number"),
    ("LEVEL MOVE Z 10", "bad_axis"), ("LEVEL MOVE A 10", "bad_axis"), ("LEVEL AUTO MAYBE", "bad_flag"),
    ("STREAM ON 1000", "out_of_range"), ("PING PONG", "extra_argument"), ("A B C D E F G H", "extra_argument"),
    ("A" * 200, "line_too_long"),
]


@pytest.mark.parametrize("line,typ", VALID)
def test_parse_valid(line, typ):
    assert P.parse_command(line).type == typ


@pytest.mark.parametrize("line,code", INVALID)
def test_parse_invalid(line, code):
    with pytest.raises(P.ParseError) as e:
        P.parse_command(line)
    assert e.value.code == code


def test_builders_roundtrip_through_parser():
    """Toute commande construite par l'hôte doit être acceptée par le (miroir du) firmware."""
    lines = [P.cmd_set_pressure(123.456789), P.cmd_set_mass(7.5), P.cmd_set_duty(0.5),
             P.cmd_level_move("x", -12.3456), P.cmd_level_jog("a", 20), P.cmd_level_target(1.5, -2.5),
             P.cmd_cal_tilt_bias(12.345, -6.789), P.cmd_table_add(2.0, 50.41), P.cmd_stream_on(10)]
    for ln in lines:
        P.parse_command(ln)
    assert P.cmd_set_pressure(120.0) == "SET P 120"
    assert P.cmd_level_move("y", 3.5) == "LEVEL MOVE Y 3.5"
    with pytest.raises(ValueError):
        P.cmd_level_move("z", 1)
    with pytest.raises(ValueError):
        P.fmt(float("nan"))


def test_parse_line_and_kinds():
    assert P.is_reply(P.parse_line(b'{"ok":true}\n'))
    fr = P.parse_line('{"t":1200,"p":[1,2]}')
    assert P.is_telemetry(fr) and not P.is_reply(fr)
    for bad in ("pas du json", "[1,2]"):
        with pytest.raises(P.ProtocolError):
            P.parse_line(bad)


def test_flatten_trame():
    fr = {"t": 5000, "st": "run", "p": [100.1, None, 99.9, 100.0, 100.2], "rpm": [2400.0], "tilt": [1.5, -2.5],
          "traw": [11.0, 12.0], "T": [20.1, 20.2, None, 20.0], "stp": [10, -10], "set": True, "faults": ["stall"]}
    f = P.flatten(fr)
    assert f["t_ms"] == 5000 and f["p1"] is None and f["p2"] == 99.9
    assert f["rpm0"] == 2400.0 and f["rpm1"] is None
    assert (f["tilt_x"], f["tilt_y"]) == (1.5, -2.5) and (f["traw_x"], f["traw_y"]) == (11.0, 12.0)
    assert f["T_air"] is None and f["T_local"] == 20.0 and f["stp1"] == -10
    assert set(f) == set(P.CSV_FIELDS)
