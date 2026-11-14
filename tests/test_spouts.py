"""Spouts.bonsai's stage on a dome: its drivers' entries are ready before HarpLickSpoutStage opens them.

Made inside the Stage SelectMany, the StepperDriver-A and -B subjects got their entry only after the
nested graph had subscribed, so HarpLickSpoutStage opened both drivers on no port and the calibration
and the delivery stopped at Start on every dome (BLUE-OPTO-2, 14 Nov 2026)."""

import xml.etree.ElementTree as ET
from pathlib import Path

W = "{https://bonsai-rx.org/2018/workflow}"
XSI = "{http://www.w3.org/2001/XMLSchema-instance}type"
SPOUTS = ET.parse(Path(__file__).parents[1] / "src" / "Extensions" / "Spouts.bonsai").getroot()
TOP = SPOUTS.find(f"{W}Workflow")


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


def test_the_driver_subjects_are_made_outside_stage():
    top = [(n.get(XSI), _name(n)) for n in _nodes(TOP)]
    assert ("rx:AsyncSubject", "StepperDriver-A") in top
    assert ("rx:AsyncSubject", "StepperDriver-B") in top
    inner = _nodes(_nodes(TOP)[_stage()].find(f"{W}Workflow"))
    assert not [n for n in inner if n.get(XSI) == "rx:AsyncSubject"]


def test_stage_starts_from_a_zip_of_both_driver_subjects():
    nodes, edges = _nodes(TOP), _edges(TOP)
    into_stage = [f for f, t, label in edges if t == _stage() and label == "Source1"]
    assert len(into_stage) == 1
    zip_node = into_stage[0]
    assert nodes[zip_node].find(f"{W}Combinator").get(XSI) == "rx:Zip"
    sources = sorted(_name(nodes[f]) for f, t, _ in edges if t == zip_node)
    assert sources == ["StepperDriver-A", "StepperDriver-B"]
    assert all(nodes[f].get(XSI) == "SubscribeSubject" for f, t, _ in edges if t == zip_node)
