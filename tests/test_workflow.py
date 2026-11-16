"""The calibration (src\\dome.bonsai, src\\box.bonsai) and the delivery (src\\deliver-dome.bonsai, src\\deliver-box.bonsai)
against the lab's rules for a workflow's hardware (open_rigs.rigs.workflow_lint): the lab's device pieces, as in a
session, never a device opened by hand (Pip, 16 Nov 2026). One workflow per rig kind, as the preflight (Pip, 16 Nov
2026): a dome's board follows its timestamp generator, so the dome's clock is ClockFromTimestampGenerator, as lib's
DomeHardware; a box's is ClockFromBoard. Each pair is otherwise the same file."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml
from open_rigs.rigs import workflow_lint as lint
from open_rigs.rigs.lab_rig import LabRig

ROOT = Path(__file__).parents[1]
RIGS = sorted((ROOT / "tests" / "rigs").glob("*.yml"))
W, XSI = lint.W, lint.XSI
BOARD_CLOCK = "OpenRigs.Devices:BehaviorBoard.ClockFromBoard.bonsai"
GENERATOR_CLOCK = "OpenRigs.Devices:ClockFromTimestampGenerator.bonsai"
# Each workflow: its job and its rig kind. The job's stage is the one it announces itself: the old Ready (1 s after the
# board's first event, once PulseOutputs' setup has gone out, and the spouts in), ReadyGate's WorkflowStages, which
# Ready waits for beside the clock.
WORKFLOWS = {"dome.bonsai": ("calibrate", "dome"), "box.bonsai": ("calibrate", "box"),
             "deliver-dome.bonsai": ("deliver", "dome"), "deliver-box.bonsai": ("deliver", "box")}
STAGES = {"calibrate": "CalibrationReady", "deliver": "DeliveryReady"}
CLOCKS = {"dome": GENERATOR_CLOCK, "box": BOARD_CLOCK}
# The box file's words that say its clock and its kind, and the dome file's in their place: the only text that differs.
WORDS = {
    "calibrate": [("Calibrates the reward valves on a behaviour box's behavior board,", "Calibrates the reward valves on a dome's behavior board,"),
                  ("its clock (ClockFromBoard: the board's clock set to UTC, HarpClockSet, and Timestamp, the board's own time from its analog data events, 1 kHz,",
                   "the rig's clock (ClockFromTimestampGenerator, TimestampGeneratorGen3-Main, which the board follows: the generator's clock set to UTC, HarpClockSet, and Timestamp, the generator's timer at rig.yml's timerFrequency,")],
    "deliver": [("Delivers water on one of a behaviour box's valves", "Delivers water on one of a dome's valves"),
                ("its clock (ClockFromBoard: Timestamp, the board's own time from its analog data events, 1 kHz,",
                 "the rig's clock (ClockFromTimestampGenerator, TimestampGeneratorGen3-Main, which the board follows: Timestamp, the generator's timer at rig.yml's timerFrequency,")],
}
PIECE_LIST = ("ReadyGate, BehaviorBoard, ClockFromBoard, PulseOutputs", "ReadyGate, BehaviorBoard, ClockFromTimestampGenerator, PulseOutputs")


@pytest.fixture(params=WORKFLOWS, scope="module")
def wf(request):
    return lint.Workflow(ROOT, request.param)


def test_every_top_level_workflow_is_listed():
    assert sorted(p.name for p in (ROOT / "src").glob("*.bonsai")) == sorted(WORKFLOWS)


def test_the_hardware_is_the_lab_pieces(wf):
    assert lint.hardware_problems(wf) == []
    assert dict(lint.hardware(wf))[lint.READY_GATE]["WorkflowStages"] == STAGES[WORKFLOWS[wf.file][0]]


def test_the_clock_is_the_rig_kind_s(wf):
    clocks = [n.get("Path") for n in wf.root.iter(W + "Expression") if n.get("Path") in (BOARD_CLOCK, GENERATOR_CLOCK)]
    assert clocks == [CLOCKS[WORKFLOWS[wf.file][1]]]


def _normalised(file: str, swaps: list[tuple[str, str]]) -> bytes:
    """The workflow with its clock piece blanked and its descriptions' box words put as the dome's."""
    root = ET.parse(ROOT / "src" / file).getroot()
    for node in root.iter(W + "Expression"):
        if node.get("Path") in (BOARD_CLOCK, GENERATOR_CLOCK):
            node.attrib, node[:] = {"Path": "clock"}, []
    for description in root.iter(W + "Description"):
        for box, dome in swaps:
            description.text = description.text.replace(box, dome)
    return ET.tostring(root)


@pytest.mark.parametrize("job", STAGES)
def test_the_dome_and_box_files_differ_only_in_the_clock(job):
    (dome,) = [f for f, (j, k) in WORKFLOWS.items() if j == job and k == "dome"]
    (box,) = [f for f, (j, k) in WORKFLOWS.items() if j == job and k == "box"]
    swaps = [PIECE_LIST, *WORDS[job]]
    box_text = (ROOT / "src" / box).read_text(encoding="utf-8-sig")
    assert [box_text.count(b) for b, _ in swaps] == [1] * len(swaps)
    assert _normalised(box, swaps) == _normalised(dome, [])


def test_the_devices_it_drives(wf):
    # The lick spout stage is in Extensions\Spouts.bonsai, driving the rig's two stepper drivers.
    clock = [("TimestampGeneratorGen3-Main", "timestampGeneratorGen3")] if WORKFLOWS[wf.file][1] == "dome" else []
    assert sorted(lint.required_devices(wf)) == sorted([
        *clock,
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


def test_every_pulse_is_timed_on_the_rig_s_clock(wf):
    firings = 0
    for nodes, edges in lint._scopes(wf.root):
        for i, node in enumerate(nodes):
            if lint.kind(node) == "core:FirePulses":
                firings += 1
                (clock,) = [nodes[a] for a, b, label in edges if b == i and label == "Source2"]
                assert (clock.get(XSI), lint._name(clock)) == ("SubscribeSubject", "Timestamp")
    assert firings == {"calibrate": 5, "deliver": 1}[WORKFLOWS[wf.file][0]]
    # Timestamp is the clock piece's alone (test_the_clock_is_the_rig_kind_s): lib-open-rigs tests that ClockFromBoard's
    # is the board's 1 kHz AnalogData time and ClockFromTimestampGenerator's the generator's timer.
    declared = [n for n in wf.root.iter(W + "Expression") if "Subject" in (n.get(XSI) or "") and lint._name(n) == "Timestamp"
                and n.get(XSI) != "SubscribeSubject"]
    assert declared == []


def test_launch_id(wf):
    # The launcher's run id, mapped down to ExperimentControl, so rig-control finds the run after a crash.
    assert lint.launch_id_problems(wf) == []


def test_no_device_opened_by_hand(wf):
    # The balance camera is in no rig.yml, so the calibration opens it itself (OpenRigs.Video UsbCamera); the delivery
    # opens nothing.
    allowed = ("UsbCamera",) if WORKFLOWS[wf.file][0] == "calibrate" else ()
    assert lint.hand_opened_devices(wf, allowed) == []


def test_no_experiment_folder(wf):
    # NoExperimentFolder's PathPrefix is never published, so no piece's log starts; its SubjectId is no mouse's, so the
    # spouts go to rig.yml's lickSpoutDefaultPosition (Spouts.bonsai declared it until 16 Nov 2026).
    assert lint.no_experiment_folder_problems(wf) == []
    (node,) = [n for n in wf.root.iter(W + "Expression") if n.get("Path") == lint.NO_EXPERIMENT_FOLDER]
    assert node.findtext(W + "SubjectId") == "_valve-calibration_"


def test_live_view_is_last_and_fed_by_nothing(wf):
    # Every workflow streams its devices, as every lab workflow does.
    assert lint.live_view_problems(wf) == []


@pytest.mark.parametrize("file", [f for f, (job, _) in WORKFLOWS.items() if job == "calibrate"])
def test_the_balance_camera_reads_the_launch_s_config_root(file):
    # Its ConfigRoot (where it reads the rig's own cameras, never to take one) is ReadLabRig's, so --property:ConfigRoot
    # moves it with rig.yml; it was typed in.
    wf = lint.Workflow(ROOT, file)
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
