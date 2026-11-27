"""The calibration (src\\main.bonsai) and the delivery (src\\deliver.bonsai) against the lab's rules for a workflow's
hardware (open_rigs.rigs.workflow_lint): the lab's device pieces, as in a session, never a device opened by hand (Pip,
16 Nov 2026). One of each for every rig with valves, setting no clock (Pip, 16 Nov 2026): ClockFromBoard with SetClock
false reads the board's time, which on a dome follows the timestamp generator."""

import re
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
    # Pip, 16 Nov 2026: calibration/RewardValve-<Name>.json, the valve's piece name, never its line.
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
    # The launcher's run id, mapped down to ExperimentControl, so app-rig-control finds the run after a crash.
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
    # The piece Camera-Balance (OpenRigs.Devices UsbCamera) declares Camera-Balance.ExposureUs, the name
    # app-rig-control's Calibrations page sets; it starts at 15625 (1/64 s).
    wf = lint.Workflow(ROOT, "main.bonsai")
    (node,) = [n for n in wf.root.iter(W + "Expression") if n.get("Path") == "OpenRigs.Devices:UsbCamera.bonsai"]
    assert node.findtext(W + "ExposureUs") == "15625"
    assert "vid:UsbCamera" not in wf.text and "CameraExposureUs" not in wf.text
    assert "<Name>Camera-Balance.Data</Name>" in wf.text and "Camera-Temporary" not in wf.text


def test_valves_are_launched_by_name(wf):
    # A valve is its piece name, RewardValve-Left, found on its board and line by lib's WiredRewardValve; a board pin
    # is a line, never a launch property.
    top = lint.nodes_and_edges(lint.child(wf.root, W + "Workflow"))[0]
    names = {p.get("Name") for n in top if n.get(XSI) == "ExternalizedMapping" for p in n.iter(W + "Property")}
    assert names >= ({"Valve", "Valves"} if wf.file == "main.bonsai" else {"Valve"})
    assert "Channel" not in wf.text and "RewardValveLines" not in wf.text


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


def test_the_minimum_width_is_the_task_file_s_and_no_controller_parameter():
    # Pip, 27 Nov 2026: app-rig-control's Parameters tab goes, so no workflow keeps a controller parameter. The one the
    # calibration had, MinPulseWidthMs, is config\task-valve.yml's taskParameters.minPulseWidthMs, read at Go into TaskConfig.
    wf = lint.Workflow(ROOT, "main.bonsai")
    assert "orcl:ParameterValue" not in wf.text and "<Parameters>" not in wf.text
    # The workflow declares none (a piece's own, such as LickSpoutStage's SpoutStepSize, is lib-open-rigs').
    assert [d for d in lint.control_declarations(wf) if d[1] == "parameter" and d[0] == "ExperimentControl"] == []
    outside_descriptions = re.sub(r"<Description>.*?</Description>", "", wf.text, flags=re.S).replace("TaskParameters.MinPulseWidthMs", "")
    assert "MinPulseWidthMs" not in outside_descriptions
    # Both readers (the calibration's widths and ManualBalance's) take it from TaskConfig, published once.
    assert wf.text.count("<Selector>TaskParameters.MinPulseWidthMs</Selector>") == 2
    assert wf.text.count("<Name>TaskConfig</Name>") == 3


def test_the_task_file_is_read_at_go_into_task_config():
    # ExperimentGo zipped with TaskPath (known from Start, read at Go), deserialized as the generated model.
    wf = lint.Workflow(ROOT, "main.bonsai")
    assert any(e.findtext(W + "Name") == "TaskFile" for e in wf.root.iter(W + "Expression"))
    text = wf.text
    for part in ("<Name>ExperimentGo</Name>", "<Name>TaskPath</Name>", "orc:ReadTextFile", "CoenQcCalibrateValveTaskLogic", "<Name>TaskConfig</Name>"):
        assert part in text
    # No LaunchSettings (NoExperimentFolder declares SubjectId): the workflow publishes TaskPath itself and exposes it.
    assert 'Path="OpenRigs.Control:LaunchSettings.bonsai"' not in wf.text
    assert '<Property Name="TaskPath"' in wf.text and chr(92).join(("..", "config", "task-valve.yml")) in wf.text


def _graph(group):
    """A group's nodes (its Workflow's Nodes, in order) and its edges as (from, to, label)."""
    flow = group.find(W + "Workflow")
    nodes = list(flow.find(W + "Nodes"))
    edges = [(int(e.get("From")), int(e.get("To")), e.get("Label")) for e in flow.find(W + "Edges")]
    return nodes, edges


def _kind(node) -> str:
    """A node as its type and what names it: its xsi:type (a Combinator's own), and its Name, Selector, Format or Value."""
    inner = node.find(W + "Combinator")
    typed = (inner if inner is not None else node).get(XSI) or ""
    named = next((c.text for c in node.iter() if c.tag.split("}")[-1] in ("Name", "Selector", "Format", "Value", "Count")
                  and c.text and c is not node), "")
    return f"{typed.split(':')[-1]} {named}".strip()


def test_the_task_path_and_task_file_are_wired_as_go_needs_them():
    # Audit r1, finding 4 (27 Nov 2026): Bonsai may not be run tonight, so the wiring is checked here edge by edge, and
    # scripts\check-workflow.ps1 builds it with Bonsai's own builders (every type, selector, subject and mapping), and
    # tests\interleave.ps1 reads the task file with the generated reader. Initialization: the launch's TaskPath (the
    # outer mapping) into the StringProperty, its first value kept in the TaskPath subject from Start.
    wf = lint.Workflow(ROOT, "main.bonsai")
    top = wf.root.find(W + "Workflow").find(W + "Nodes")
    assert any(p.get("Name") == "TaskPath" for n in top if n.get(XSI) == "ExternalizedMapping" for p in n)
    init = next(n for n in top if n.findtext(W + "Name") == "Initialization")
    nodes, edges = _graph(init)
    path = next(i for i, n in enumerate(nodes) if n.get(XSI) == "ExternalizedMapping"
                and any(p.get("Name") == "Value" and p.get("DisplayName") == "TaskPath" for p in n))
    chain = [path]
    while (nxt := [t for f, t, _ in edges if f == chain[-1]]):
        assert len(nxt) == 1
        chain.append(nxt[0])
    assert [_kind(nodes[i]) for i in chain[1:]] == [r"StringProperty ..\config\task-valve.yml", "Take 1", "AsyncSubject TaskPath"]
    # TaskFile: Go's first value zipped with TaskPath, the path read and deserialized as the generated model into the
    # TaskConfig AsyncSubject, which emits once the file is read (Take(1) ends the Zip, so the subject completes).
    group = next(n for n in nodes if n.findtext(W + "Name") == "TaskFile")
    nodes, edges = _graph(group)
    assert [_kind(n) for n in nodes] == ["SubscribeSubject ExperimentGo", "Take 1", "SubscribeSubject TaskPath", "Zip",
                                         "MemberSelector Item2", "ReadTextFile", "DeserializeFromYaml", "AsyncSubject TaskConfig"]
    assert sorted(edges) == [(0, 1, "Source1"), (1, 3, "Source1"), (2, 3, "Source2"), (3, 4, "Source1"), (4, 5, "Source1"),
                             (5, 6, "Source1"), (6, 7, "Source1")]
    assert nodes[6].find(f"{{clr-namespace:CoenQcCalibrateValveTask;assembly=Extensions}}Type").get("TypeArguments") == \
        "task:CoenQcCalibrateValveTaskLogic"


def test_each_reader_of_the_minimum_takes_it_from_task_config_as_scale_widths_text():
    # Both readers (the calibration's widths and ManualBalance's): TaskConfig, its MinPulseWidthMs, as text ({0}) into the
    # Zip ScaleWidths takes (Source1), the procedure its Source2, as the parameter's ParameterValue gave it before.
    wf = lint.Workflow(ROOT, "main.bonsai")
    found = 0
    for group in wf.root.iter(W + "Expression"):
        flow = group.find(W + "Workflow")
        if flow is None or flow.find(W + "Nodes") is None:
            continue
        nodes, edges = _graph(group)
        for i, node in enumerate(nodes):
            if _kind(node) != "MemberSelector TaskParameters.MinPulseWidthMs":
                continue
            found += 1
            into = [(f, t, label) for f, t, label in edges if t == i]
            assert len(into) == 1 and _kind(nodes[into[0][0]]) == "SubscribeSubject TaskConfig"
            out = [t for f, t, _ in edges if f == i]
            assert len(out) == 1 and _kind(nodes[out[0]]) == "Format {0}"
            zip_ = [(t, label) for f, t, label in edges if f == out[0]]
            assert len(zip_) == 1 and zip_[0][1] == "Source1"
            other = [_kind(nodes[f]) for f, t, label in edges if t == zip_[0][0] and label == "Source2"]
            assert other == ["SubscribeSubject Procedure"], other
    assert found == 2
