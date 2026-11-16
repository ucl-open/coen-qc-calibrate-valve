"""Spouts.bonsai's stage: the lab's LickSpoutStage piece, behind the condition that the rig has a stage.

A QC workflow runs on domes (with a stage) and boxes (without), and a workflow's graph is fixed, so the piece runs
only in Stage, the SelectMany a rig with stepperDriver entries starts. The piece declares StepperDriver-A and -B
itself (until 16 Nov 2026 this file made them, for the old HarpLickSpoutStage) and builds its positions file from
SubjectId, which here is never a mouse's (headless check, 16 Nov 2026: inside Stage the piece opened driver A on
rig.yml's port, and without a stage the workflow ran on)."""

import xml.etree.ElementTree as ET
from pathlib import Path

W = "{https://bonsai-rx.org/2018/workflow}"
XSI = "{http://www.w3.org/2001/XMLSchema-instance}type"
SPOUTS = ET.parse(Path(__file__).parents[1] / "src" / "Extensions" / "Spouts.bonsai").getroot()
TOP = SPOUTS.find(f"{W}Workflow")
STAGE_PIECE = "OpenRigs.Devices:LickSpoutStage.bonsai"


def _nodes(workflow):
    return list(workflow.find(f"{W}Nodes"))


def _edges(workflow):
    return [(int(e.get("From")), int(e.get("To")), e.get("Label")) for e in workflow.find(f"{W}Edges")]


def _name(node):
    name = node.find(f"{W}Name")
    if name is None:
        name = node.find("{clr-namespace:Bonsai.Reactive;assembly=Bonsai.Core}Name")
    return None if name is None else name.text


def _stage():
    return next(i for i, n in enumerate(_nodes(TOP)) if n.get(XSI) == "rx:SelectMany" and _name(n) == "Stage")


def _stage_nodes():
    return _nodes(_nodes(TOP)[_stage()].find(f"{W}Workflow"))


def test_the_stage_is_the_lab_piece_inside_stage_only():
    assert [n.get("Path") for n in _stage_nodes() if n.get("Path")] == [STAGE_PIECE]
    assert not [n for n in _nodes(TOP) if n.get("Path")]
    assert "HarpLickSpoutStage" not in ET.tostring(SPOUTS, encoding="unicode")


def test_stage_starts_only_on_a_rig_with_a_stage():
    nodes, edges = _nodes(TOP), _edges(TOP)
    into_stage = [nodes[f] for f, t, label in edges if t == _stage() and label == "Source1"]
    assert [(n.get(XSI), _name(n)) for n in into_stage] == [("rx:Condition", "Stage?")]


def test_the_drivers_are_the_pieces_own():
    named = {_name(n) for n in SPOUTS.iter(f"{W}Expression")}
    assert not {n for n in named if n and n.startswith("StepperDriver")}


def test_a_calibration_is_no_mouse_so_the_spouts_go_to_the_default_position():
    nodes = _stage_nodes()
    subject = next(i for i, n in enumerate(nodes) if n.get(XSI) == "rx:BehaviorSubject" and _name(n) == "SubjectId")
    edges = _edges(_nodes(TOP)[_stage()].find(f"{W}Workflow"))
    (source,) = [nodes[f] for f, t, _ in edges if t == subject]
    assert source.find(f"{W}Combinator").findtext(f"{W}Value") == "_valve-calibration_"
