"""The committed settings and test rigs, checked without the rig or Bonsai."""

from collections import Counter
from pathlib import Path

import pytest
import yaml
from open_rigs.core.dispense import DispenseCalibration

ROOT = Path(__file__).parents[1]
RIGS = sorted((ROOT / "tests" / "rigs").glob("*.yml"))


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
    data = yaml.safe_load((ROOT / "config" / "valve-calibration.yml").read_text(encoding="utf-8"))
    model = DispenseCalibration.model_validate(data)
    assert not list(unknown_keys(data, model.model_dump(by_alias=True, exclude_unset=True)))
    return model


def test_one_gap_for_every_sample(settings):
    # The calibration file records one pulseGapMs and the workflow refuses samples at different gaps.
    assert {sample.pulse_gap_ms for sample in settings.procedure.samples} == {80}


def test_widths_from_20_ms_to_5_times_that(settings):
    # Written for a 20 ms minimum; at Go they are scaled so the smallest is the rig's MinPulseMs.
    sizes = [sample.size for sample in settings.procedure.samples]
    assert min(sizes) == 20
    assert max(sizes) == 5 * min(sizes)


def test_rounds_measure_every_width_alike(settings):
    counts = Counter(sample.size for sample in settings.procedure.samples)
    assert len(set(counts.values())) == 1


def test_every_burst_opens_the_valve_about_as_long(settings):
    opening = [sample.size * sample.repeats for sample in settings.procedure.samples]
    assert max(opening) / min(opening) < 1.01


@pytest.mark.parametrize("path", RIGS, ids=lambda path: path.name)
def test_a_test_rig_wires_reward_valves_on_pulse_lines(path):
    # What ValveRig takes from a rig.yml: behaviorBoard main's port and its RewardValve lines on DO1 to DO3.
    board = yaml.safe_load(path.read_text(encoding="utf-8"))["behaviorBoard"]["main"]
    valves = [line for line, wired in board["wiring"].items() if wired["device"] == "RewardValve"]
    assert board["portName"]
    assert valves and set(valves) <= {"DO1", "DO2", "DO3"}


def test_the_three_test_rigs_are_there():
    assert [path.name for path in RIGS] == ["arena.yml", "box.yml", "dome.yml"]
