"""The calibration (src\\main.bonsai) and the delivery (src\\deliver.bonsai) against the lab's rules for a workflow's
hardware (open_rigs.rigs.workflow_lint): the lab's device pieces, as in a session, never a device opened by hand (Pip,
16 Nov 2026). One of each for every rig with valves, setting no clock (Pip, 16 Nov 2026): ClockFromBoard with SetClock
false reads the board's time, which on a dome follows the timestamp generator."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml
from open_rigs.rigs import workflow_lint as lint
from open_rigs.rigs.lab_rig import LabRig

ROOT = Path(__file__).parents[1]
RIGS = sorted((ROOT / "tests" / "rigs").glob("*.yml"))
W, XSI = lint.W, lint.XSI
# Each workflow's own stage: the spouts in, ReadyGate's WorkflowStages, which Ready waits for beside the clock and
# PulseOutputs' PulsesEnabled (PieceStages).
WORKFLOWS = {"main.bonsai": "CalibrationReady", "deliver.bonsai": "DeliveryReady"}


@pytest.fixture(params=WORKFLOWS, scope="module")
def wf(request):
    return lint.Workflow(ROOT, request.param)


def test_every_top_level_workflow_is_listed():
    assert sorted(p.name for p in (ROOT / "src").glob("*.bonsai")) == sorted(WORKFLOWS)


def test_the_hardware_is_the_lab_pieces(wf):
    assert lint.hardware_problems(wf) == []
    assert dict(lint.hardware(wf))[lint.READY_GATE]["WorkflowStages"] == WORKFLOWS[wf.file]


def test_the_board_s_time_is_read_and_never_set(wf):
    # One workflow for every rig with valves (Pip, 16 Nov 2026): it records nothing and times pulses only against
    # each other, so it reads the board's time as it runs and Ready waits for HarpClockRead and for PulseOutputs'
    # PulsesEnabled, no fixed timer.
    pieces = lint.hardware(wf)
    assert [(path, props.get("SetClock")) for path, props in pieces if path in lint.CLOCKS] == [
        (lint.CLOCK_FROM_BOARD, "false")]
    assert dict(pieces)[lint.READY_GATE]["PieceStages"] == f"{lint.CLOCK_READ}, PulsesEnabled"


def test_a_stop_ends_headless_bonsai(wf):
    # A stop held up in a device's teardown would keep headless Bonsai running until the agent's kill: OpenRigs.Control's
    # EndAfterStop ends it 2 s after the stop.
    assert wf.text.count("orcl:EndAfterStop") == 1


def test_the_devices_it_drives(wf):
    # The lick spout stage is in Extensions\Spouts.bonsai, driving the rig's two stepper drivers.
    assert sorted(lint.required_devices(wf)) == sorted([
        ("BehaviorBoard-Main", "behaviorBoard"),
        ("StepperDriver-A", "stepperDriver"),
        ("StepperDriver-B", "stepperDriver"),
    ])


def test_every_announcer_never_completes(wf):
    assert lint.ready_announcer_problems(wf.root) == []
    assert lint.ready_announcer_problems(ET.parse(ROOT / "src" / "Extensions" / "Spouts.bonsai").getroot()) == []


def test_no_shared_mapping(wf):
    assert lint.shared_mapping_problems(wf.root) == []


def test_every_command_is_declared_once(wf):
    assert lint.undeclared_commands(wf) == [] and lint.declared_twice(wf) == []


def test_spout_step_size_is_the_lick_spout_stage_s(wf):
    # LickSpoutStage (in Spouts.bonsai, on a rig with a stage) declares SpoutStepSize itself (16 Nov 2026): a copy here
    # would stop ControlServer at Start, and on a rig without a stage nothing declares it.
    assert lint.spout_step_size_problems(wf) == []


@pytest.mark.parametrize("path", RIGS, ids=lambda path: path.name)
def test_no_fixed_width_pulse_on_a_valve(wf, path):
    rig = LabRig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    assert lint.fixed_width_pulses_on_reward_valves(wf, rig.reward_valve_lines()) == []


@pytest.mark.parametrize("path", RIGS, ids=lambda path: path.name)
def test_the_pulsed_lines_are_the_valves(path):
    # PulseOutputs pulse-enables outputPulseEnable without the ZapitTrigger line; the calibration pulse-enabled the
    # RewardValve lines. On every test rig they are the same lines.
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rig = LabRig.model_validate(data)
    board = data["behaviorBoard"]["main"]
    zapit = {line for line, wired in board["wiring"].items() if wired["device"] == "ZapitTrigger"}
    enabled = set(board["pulseController"]["outputPulseEnable"].replace(",", " ").split()) - zapit
    assert enabled == set(rig.reward_valve_lines())


@pytest.mark.parametrize("path", RIGS, ids=lambda path: path.name)
def test_each_valve_s_calibration_is_named_by_the_valve(path):
    # Pip, 16 Nov 2026: calibration/RewardValve-<Name>.json, the valve's piece name, never its line (valve-DO1).
    rig = LabRig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    outputs = yaml.safe_load(path.read_text(encoding="utf-8"))["behaviorBoard"]["main"]["pulseController"]["outputs"]
    assert {piece: outputs[line]["artefact"] for piece, (_, line) in rig.reward_valves().items()} ==         {piece: f"calibration/{piece}.json" for piece in rig.reward_valves()}


def test_the_file_name_by_default_is_a_valve_s():
    assert "<Value>RewardValve-Left</Value>" in (ROOT / "src" / "main.bonsai").read_text(encoding="utf-8")


def test_every_pulse_is_timed_on_the_rig_s_clock(wf):
    firings = 0
    for nodes, edges in lint._scopes(wf.root):
        for i, node in enumerate(nodes):
            if lint.kind(node) == "core:FirePulses":
                firings += 1
                (clock,) = [nodes[a] for a, b, label in edges if b == i and label == "Source2"]
                assert (clock.get(XSI), lint._name(clock)) == ("SubscribeSubject", "Timestamp")
    assert firings == {"main.bonsai": 5, "deliver.bonsai": 1}[wf.file]
    # Timestamp is the clock piece's alone (test_the_board_s_time_is_read_and_never_set): lib-open-rigs tests that
    # ClockFromBoard's is the board's 1 kHz AnalogData time.
    declared = [n for n in wf.root.iter(W + "Expression") if "Subject" in (n.get(XSI) or "") and lint._name(n) == "Timestamp"
                and n.get(XSI) != "SubscribeSubject"]
    assert declared == []


def test_launch_id(wf):
    # The launcher's run id, mapped down to ExperimentControl, so rig-control finds the run after a crash.
    assert lint.launch_id_problems(wf) == []


def test_no_device_opened_by_hand(wf):
    # The balance camera, in no rig.yml, opens through lib's piece (OpenRigs.Devices UsbCamera); the delivery opens nothing.
    assert lint.hand_opened_devices(wf) == []


def test_no_experiment_folder(wf):
    # NoExperimentFolder's PathPrefix is never published, so no piece's log starts; its SubjectId is the include's default
    # (_no-experiment_), no mouse's, so the spouts go to rig.yml's lickSpoutDefaultPosition.
    assert lint.no_experiment_folder_problems(wf) == []
    (node,) = [n for n in wf.root.iter(W + "Expression") if n.get("Path") == lint.NO_EXPERIMENT_FOLDER]
    assert node.find(W + "SubjectId") is None


def test_live_view_is_last_and_fed_by_nothing(wf):
    # Every workflow streams its devices, as every lab workflow does.
    assert lint.live_view_problems(wf) == []


def test_read_lab_rig_and_no_experiment_folder_are_top_level(wf):
    # As in the preflights and the tasks: ConfigRoot's mapping feeds ReadLabRig, then NoExperimentFolder, first of all.
    nodes, edges = lint.nodes_and_edges(lint.child(wf.root, W + "Workflow"))
    assert [n.get("Path") for n in nodes[1:3]] == [lint.READ_LAB_RIG, lint.NO_EXPERIMENT_FOLDER]
    assert [p.get("Name") for p in nodes[0].iter(W + "Property")] == ["ConfigRoot"] and (0, 1) in [e[:2] for e in edges]


def test_the_balance_camera_is_lib_s_piece():
    # The piece Camera-Temporary (OpenRigs.Devices UsbCamera) declares Camera-Temporary.ExposureUs, the name
    # app-rig-control's Calibrations page sets; it starts at 15625 (1/64 s), as the camera opened by hand did.
    wf = lint.Workflow(ROOT, "main.bonsai")
    (node,) = [n for n in wf.root.iter(W + "Expression") if n.get("Path") == "OpenRigs.Devices:UsbCamera.bonsai"]
    assert node.findtext(W + "ExposureUs") == "15625"
    assert "vid:UsbCamera" not in wf.text and "CameraExposureUs" not in wf.text


def test_test_pulses_stop_at_go():
    # A Test train still firing at Go stops there, not alongside the priming: FirePulses
    # finishes a train whose input has completed, so the cut is after it, on its pulses to BehaviorBoard-Main.TriggerCalibratedPulse.
    group = next(e for e in lint.Workflow(ROOT, "main.bonsai").root.iter(W + "Expression") if e.findtext(W + "Name") == "Hardware")
    nodes, edges = lint.nodes_and_edges(group.find(W + "Workflow"))
    (train,) = [i for i, n in enumerate(nodes) if lint.kind(n) == "vc:TestTrain"]
    (fire,) = [b for a, b, _ in edges if a == train + 1 and lint.kind(nodes[b]) == "core:FirePulses"]
    (cut,) = [b for a, b, _ in edges if a == fire]
    assert lint.kind(nodes[cut]) == "rx:TakeUntil"
    (go,) = [a for a, b, label in edges if b == cut and label == "Source2"]
    assert lint._name(nodes[go]) == "ExperimentGo"
    assert [lint._name(nodes[b]) for a, b, _ in edges if a == cut] == ["BehaviorBoard-Main.TriggerCalibratedPulse"]


def test_experiment_control_is_written_as_in_every_lab_workflow(wf):
    # SubjectId, SessionId, LaunchId, ControlEndpoint, Parameters and Commands, as the preflight and the projector write it.
    (node,) = [n for n in wf.root.iter(W + "Expression") if n.get("Path") == "OpenRigs.Control:ExperimentControl.bonsai"]
    assert [c.tag.replace(W, "") for c in node] == ["SubjectId", "SessionId", "LaunchId", "ControlEndpoint", "Parameters", "Commands"]


def test_no_debug_dump_in_the_repo():
    assert not (ROOT / "blocks.txt").exists()