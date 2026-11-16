"""The calibration (src\\main.bonsai) and the delivery (src\\deliver.bonsai) against the lab's rules for a workflow's
hardware (open_rigs.rigs.workflow_lint): the lab's device pieces, as in a session, never a device opened by hand
(Pip, 16 Nov 2026). Each valve pulse is timed as before the pieces: FirePulses on the board's 1 kHz analog data time."""

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
import yaml
from open_rigs.rigs import workflow_lint as lint
from open_rigs.rigs.lab_rig import LabRig

ROOT = Path(__file__).parents[1]
RIGS = sorted((ROOT / "tests" / "rigs").glob("*.yml"))
W, XSI = lint.W, lint.XSI
# Each workflow and the stage it announces itself: the old Ready (1 s after the board's first event, once PulseOutputs'
# setup has gone out, and the spouts in), which the lab's ReadyGate waits for beside the clock.
WORKFLOWS = {"main.bonsai": "CalibrationReady", "deliver.bonsai": "DeliveryReady"}


@pytest.fixture(params=WORKFLOWS, scope="module")
def wf(request):
    return lint.Workflow(ROOT, request.param)


def test_the_hardware_is_the_lab_pieces(wf):
    # The one problem is the workflow's own stage: hardware_problems knows only the pieces' stages, and the
    # calibration's Ready also waits for the pulse setup and the spouts (Spouts.bonsai, which it does not read).
    stage = WORKFLOWS[wf.file]
    assert lint.hardware_problems(wf) == [f"ReadyGate's ReadyWaitsFor is HarpClockSet, {stage}, not HarpClockSet"]


def test_the_devices_it_drives(wf):
    # The lick spout stage is in Extensions\Spouts.bonsai, behind the rig's stepperDriver entries.
    assert lint.required_devices(wf) == [("BehaviorBoard-Main", "behaviorBoard")]


def test_every_announcer_never_completes(wf):
    assert lint.ready_announcer_problems(wf.root) == []
    assert lint.ready_announcer_problems(ET.parse(ROOT / "src" / "Extensions" / "Spouts.bonsai").getroot()) == []


def test_no_shared_mapping(wf):
    assert lint.shared_mapping_problems(wf.root) == []


def test_every_command_is_declared(wf):
    assert lint.undeclared_commands(wf) == []


def test_spout_step_size_is_declared(wf):
    # LickSpoutStage (in Spouts.bonsai) shows SpoutStepSize's default at Start; undeclared, that stops the workflow.
    assert re.search(r"<Parameter>\s*<Name>SpoutStepSize</Name>", wf.text)
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
    # Timestamp is ClockFromBoard's alone, and the installed OpenRigs.Devices (.23 on) publishes it from AnalogData.
    declared = [n for n in wf.root.iter(W + "Expression") if "Subject" in (n.get(XSI) or "") and lint._name(n) == "Timestamp"
                and n.get(XSI) != "SubscribeSubject"]
    assert declared == [] and wf.text.count('Path="OpenRigs.Devices:BehaviorBoard.ClockFromBoard.bonsai"') == 1
    config = (ROOT / ".bonsai" / "Bonsai.config").read_text(encoding="utf-8-sig")
    version = re.search(r'<Package id="OpenRigs.Devices" version="([^"]+)"', config).group(1)
    with zipfile.ZipFile(ROOT / "local_packages" / f"OpenRigs.Devices.{version}.nupkg") as z:
        dll = z.read("lib/net472/OpenRigs.Devices.dll").decode("latin-1")
    at = dll.index("<Description>The rig's clock from a Behavior board")
    piece = ET.fromstring(dll[dll.rindex("<WorkflowBuilder", 0, at):dll.index("</WorkflowBuilder>", at) + 18].encode("latin-1"))
    nodes = list(piece.find(f"{W}Workflow/{W}Nodes"))
    feeds = {int(e.get("To")): int(e.get("From")) for e in piece.iter(W + "Edge")}
    chain = [next(i for i, n in enumerate(nodes) if n.get(XSI) == "rx:BehaviorSubject" and lint._name(n) == "Timestamp")]
    while chain[-1] in feeds:
        chain.append(feeds[chain[-1]])
    described = [nodes[i].findtext(W + "Selector") or next(iter(nodes[i])).get(XSI) or nodes[i].get(XSI) for i in reversed(chain)]
    assert described[-4:] == ["harp:FilterMessageType", "beh:TimestampedAnalogData", "Seconds", "rx:BehaviorSubject"]


def test_no_experiment_folder(wf):
    # PathPrefix is declared and never published, so no piece's log starts.
    declared = [n for n in wf.root.iter(W + "Expression") if lint._name(n) == "PathPrefix"]
    assert [(n.get(XSI), n.get("TypeArguments")) for n in declared] == [("rx:BehaviorSubject", "sys:String")]
    assert not [n for n in wf.root.iter(W + "Expression") if n.get(XSI) == "MulticastSubject" and lint._name(n) == "PathPrefix"]
