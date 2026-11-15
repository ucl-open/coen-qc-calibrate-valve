"""The committed settings and test rigs, checked without the rig or Bonsai."""

import json
import re
from collections import Counter
from importlib.resources import files
from pathlib import Path

import jsonschema
import pytest
import yaml
from open_rigs.core.dispense import DispenseCalibration
from open_rigs.rigs.lab_rig import LabRig

ROOT = Path(__file__).parents[1]
RIGS = sorted((ROOT / "tests" / "rigs").glob("*.yml"))
SETTINGS = ROOT / "config" / "valve-calibration.yml"


def closed(node):
    """The schema with every object that lists its properties closed to others, as lib-open-rigs'
    check-config-schemas.py and the generated DeserializeFromYaml are."""
    if isinstance(node, dict):
        node = {key: closed(value) for key, value in node.items()}
        if isinstance(node.get("properties"), dict) and "additionalProperties" not in node:
            node["additionalProperties"] = False
    elif isinstance(node, list):
        node = [closed(value) for value in node]
    return node


def schema_errors(data):
    """What the schema the file's yaml-language-server line names refuses in data, as the shared checks read it."""
    named = re.match(r"# yaml-language-server: \$schema=(\S+)#/\$defs/(\w+)\n", SETTINGS.read_text(encoding="utf-8"))
    assert named, "config\\valve-calibration.yml names no schema, so the shared checks skip it"
    path = (SETTINGS.parent / named.group(1)).resolve()
    assert path == Path(str(files("open_rigs") / "schemas" / "calibration.json")).resolve()
    schema = closed(json.loads(path.read_text(encoding="utf-8")))
    schema = {"$schema": schema.get("$schema"), "$defs": schema["$defs"], "$ref": f"#/$defs/{named.group(2)}"}
    return [error.message for error in jsonschema.Draft202012Validator(schema).iter_errors(data)]


def test_the_settings_fit_the_calibration_schema():
    assert schema_errors(yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))) == []


def test_the_schema_refuses_an_unknown_key():
    # Audit, 15 Nov 2026: DispenseCalibration keeps only the keys it knows, so a misspelt one (primingSize for
    # primingPulseWidthMs) passed the model; the closed schema refuses it.
    data = yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))
    data["procedure"]["primingSize"] = 500
    assert schema_errors(data) == ["Additional properties are not allowed ('primingSize' was unexpected)"]


def unknown_keys(given, kept, path=""):
    """Keys of the file that the model did not keep: the generated C# refuses them at Start."""
    if isinstance(given, dict) and isinstance(kept, dict):
        for key, value in given.items():
            if key not in kept:
                yield f"{path}{key}"
            else:
                yield from unknown_keys(value, kept[key], f"{path}{key}.")
    elif isinstance(given, list) and isinstance(kept, list):
        for index, (value, kept_value) in enumerate(zip(given, kept)):
            yield from unknown_keys(value, kept_value, f"{path}{index}.")


@pytest.fixture(scope="module")
def settings():
    data = yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))
    model = DispenseCalibration.model_validate(data)
    assert not list(unknown_keys(data, model.model_dump(by_alias=True, exclude_unset=True)))
    return model


def test_one_gap_for_every_sample(settings):
    # The calibration file records one pulseGapMs and the workflow refuses samples at different gaps.
    assert {sample.pulse_gap_ms for sample in settings.procedure.samples} == {80}


def test_widths_from_20_ms_to_5_times_that(settings):
    # Written for a 20 ms minimum; at Go they are scaled so the smallest is the rig's MinPulseWidthMs.
    widths = [sample.pulse_width_ms for sample in settings.procedure.samples]
    assert min(widths) == 20
    assert max(widths) == 5 * min(widths)


def test_rounds_measure_every_width_alike(settings):
    counts = Counter(sample.pulse_width_ms for sample in settings.procedure.samples)
    assert len(set(counts.values())) == 1


def test_every_burst_opens_the_valve_about_as_long(settings):
    opening = [sample.pulse_width_ms * sample.repeats for sample in settings.procedure.samples]
    assert max(opening) / min(opening) < 1.01


@pytest.mark.parametrize("path", RIGS, ids=lambda path: path.name)
def test_a_test_rig_wires_reward_valves_on_pulse_lines(path):
    # A rig.yml every lab workflow takes (the lab rig model, OpenRigs.Devices ReadLabRig), with what the
    # calibration reads: behaviorBoard main's port and its RewardValve lines on DO1 to DO3 (WiredOutputs).
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    LabRig.model_validate(data)
    board = data["behaviorBoard"]["main"]
    valves = [line for line, wired in board["wiring"].items() if wired["device"] == "RewardValve"]
    assert board["portName"]
    assert valves and set(valves) <= {"DO1", "DO2", "DO3"}


def test_the_three_test_rigs_are_there():
    assert [path.name for path in RIGS] == ["arena.yml", "box.yml", "dome.yml"]
