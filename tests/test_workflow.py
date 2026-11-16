"""The calibration (src\\main.bonsai) and the delivery (src\\deliver.bonsai) against the lab's rules for a workflow's
hardware (open_rigs.rigs.workflow_lint): the lab's device pieces, as in a session, never a device opened by hand
(Pip, 16 Nov 2026). Each valve pulse is timed as before the pieces: FirePulses on the board's 1 kHz analog data time."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml
from open_rigs.rigs import workflow_lint as lint
from open_rigs.rigs.lab_rig import LabRig

ROOT = Path(__file__).parents[1]
RIGS = sorted((ROOT / "tests" / "rigs").glob("*.yml"))
W, XSI = lint.W, lint.XSI
# Each workflow and the stage it announces itself: the old Ready (1 s after the board's first event, once PulseOutputs'
# setup has gone out, and the spouts in), ReadyGate's WorkflowStages, which Ready waits for beside the clock.
WORKFLOWS = {"main.bonsai": "CalibrationReady", "deliver.bonsai": "DeliveryReady"}


@pytest.fixture(params=WORKFLOWS, scope="module")
def wf(request):
    return lint.Workflow(ROOT, request.param)


def test_the_hardware_is_the_lab_pieces(wf):
    assert lint.hardware_problems(wf) == []
    assert dict(lint.hardware(wf))[lint.READY_GATE]["WorkflowStages"] == WORKFLOWS[wf.file]


def test_the_devices_it_drives(wf):
    # The lick spout stage is in Extensions\Spouts.bonsai, behind the rig's stepperDriver entries.
    assert lint.required_devices(wf) == [("BehaviorBoard-Main", "behaviorBoard")]


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
    assert "SpoutStepSize" not in wf.text and lint.spout_step_size_problems(wf) == []


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
    assert enabled == {f"DO{line}" for line in rig.reward_valve_lines()}


def test_every_pulse_is_timed_on_the_board_analog_data_time(wf):
    firings = 0
    for nodes, edges in lint._scopes(wf.root):
        for i, node in enumerate(nodes):
            if lint.kind(node) == "core:FirePulses":
                firings += 1
                (clock,) = [nodes[a] for a, b, label in edges if b == i and label == "Source2"]
                assert (clock.get(XSI), lint._name(clock)) == ("SubscribeSubject", "Timestamp")
    assert firings == {"main.bonsai": 5, "deliver.bonsai": 1}[wf.file]
    # Timestamp is ClockFromBoard's alone (lib-open-rigs tests that it is the board's 1 kHz AnalogData time).
    declared = [n for n in wf.root.iter(W + "Expression") if "Subject" in (n.get(XSI) or "") and lint._name(n) == "Timestamp"
                and n.get(XSI) != "SubscribeSubject"]
    assert declared == [] and wf.text.count('Path="OpenRigs.Devices:BehaviorBoard.ClockFromBoard.bonsai"') == 1


def test_no_experiment_folder(wf):
    # NoExperimentFolder's PathPrefix is never published, so no piece's log starts; its SubjectId is no mouse's, so the
    # spouts go to rig.yml's lickSpoutDefaultPosition (Spouts.bonsai declared it until 16 Nov 2026).
    assert lint.no_experiment_folder_problems(wf) == []
    (node,) = [n for n in wf.root.iter(W + "Expression") if n.get("Path") == lint.NO_EXPERIMENT_FOLDER]
    assert node.findtext(W + "SubjectId") == "_valve-calibration_"


def test_live_view_is_last_and_fed_by_nothing(wf):
    # Both workflows stream their devices, as every lab workflow does. StreamDevices finds only subjects built before
    # it, so nothing feeds it and nothing follows it (an edge into it builds it before the pieces: it streams nothing).
    nodes, edges = lint.nodes_and_edges(wf.root.find(W + "Workflow"))
    (live,) = [i for i, n in enumerate(nodes) if n.get(XSI) == "lv:StreamDevices"]
    assert live == len(nodes) - 1 and not [e for e in edges if live in e[:2]]


def test_the_balance_camera_reads_the_launch_s_config_root():
    # Its ConfigRoot (where it reads the rig's own cameras, never to take one) is ReadLabRig's, so --property:ConfigRoot
    # moves it with rig.yml; it was typed in.
    wf = lint.Workflow(ROOT, "main.bonsai")
    group = next(e for e in wf.root.iter(W + "Expression") if e.findtext(W + "Name") == "Hardware")
    nodes, edges = lint.nodes_and_edges(group.find(W + "Workflow"))
    (camera,) = [i for i, n in enumerate(nodes) if n.find(W + "Combinator") is not None and n.find(W + "Combinator").get(XSI) == "vid:UsbCamera"]
    mappings = [a for a, b, _ in edges if b == camera and nodes[a].get(XSI) == "PropertyMapping"
                and [p.get("Name") for p in nodes[a].iter(W + "Property")] == ["ConfigRoot"]]
    assert [nodes[a].findtext(W + "Name") for m in mappings for a, b, _ in edges if b == m] == ["ConfigRoot"]

def test_read_lab_rig_and_no_experiment_folder_are_top_level(wf):
    # As in the preflights and the tasks: ConfigRoot's mapping feeds ReadLabRig, then NoExperimentFolder, first of all.
    nodes, edges = lint.nodes_and_edges(lint.child(wf.root, W + "Workflow"))
    assert [n.get("Path") for n in nodes[1:3]] == [lint.READ_LAB_RIG, lint.NO_EXPERIMENT_FOLDER]
    assert [p.get("Name") for p in nodes[0].iter(W + "Property")] == ["ConfigRoot"] and (0, 1) in [e[:2] for e in edges]
