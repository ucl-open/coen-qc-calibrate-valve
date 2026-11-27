"""The task file, its pydantic model, the committed JSON schema and the generated C# agree."""

import json
import re
from pathlib import Path

import jsonschema
import pydantic
import pytest
import yaml
from pydantic import ValidationError

from coen_qc_calibrate_valve.task import CoenQcCalibrateValveTaskLogic

ROOT = Path(__file__).parent.parent
TASK = ROOT / "config" / "task-valve.yml"
SCHEMA = ROOT / "src" / "DataSchemas" / "coen_qc_calibrate_valve_task.json"
GENERATED = ROOT / "src" / "Extensions" / "CoenQcCalibrateValveTask.Generated.cs"


def task() -> dict:
    return yaml.safe_load(TASK.read_text(encoding="utf-8"))


def _closed(node):
    # app-rig-control checks a task file against the schema with every object closed.
    if isinstance(node, dict):
        out = {k: _closed(v) for k, v in node.items()}
        if "properties" in out:
            out["additionalProperties"] = False
        return out
    return [_closed(v) for v in node] if isinstance(node, list) else node


def test_the_task_file_validates_and_keeps_the_20_ms_minimum():
    model = CoenQcCalibrateValveTaskLogic.model_validate(task())
    assert model.task_parameters.min_pulse_width_ms == 20
    assert task() == {"taskParameters": {"minPulseWidthMs": 20}}


@pytest.mark.parametrize("ms", [0, 4, 101, -1, 12.5, "20 ms", None])
def test_a_width_that_is_not_a_whole_number_from_5_to_100_is_refused(ms):
    with pytest.raises(ValidationError):
        CoenQcCalibrateValveTaskLogic.model_validate({"taskParameters": {"minPulseWidthMs": ms}})
    errors = list(jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).iter_errors({"taskParameters": {"minPulseWidthMs": ms}}))
    assert errors


@pytest.mark.parametrize("key", ["minPulseWidth", "rngSeed", "MinPulseWidthMs"])
def test_the_schema_refuses_a_key_the_task_does_not_have(key):
    errors = list(jsonschema.Draft202012Validator(_closed(json.loads(SCHEMA.read_text(encoding="utf-8")))).iter_errors({"taskParameters": {key: 20}}))
    assert errors


def test_the_committed_task_schema_is_the_model_s():
    model = pydantic.RootModel[CoenQcCalibrateValveTaskLogic].model_json_schema(
        by_alias=True, mode="serialization", union_format="primitive_type_array"
    )
    assert json.loads(SCHEMA.read_text(encoding="utf-8")) == json.loads(json.dumps(model))


def _property_names(node) -> set[str]:
    if isinstance(node, dict):
        return set(node.get("properties", {})) | {n for v in node.values() for n in _property_names(v)}
    return {n for v in node for n in _property_names(v)} if isinstance(node, list) else set()


def test_the_generated_csharp_has_every_schema_field():
    # A field added to the model and schema but not regenerated into C# stops the workflow at Go: run regenerate-schemas.
    names = set(re.findall(r'JsonPropertyAttribute\("([^"]+)"', GENERATED.read_text(encoding="utf-8")))
    assert names == _property_names(json.loads(SCHEMA.read_text(encoding="utf-8")))
    assert "minPulseWidthMs" in names


def test_the_minimum_is_required_with_no_default():
    # Audit r1, finding 5 (27 Nov 2026): a task file without minPulseWidthMs ran at 20 ms whatever the rig's minimum was.
    # Now the model and the schema refuse it (app-rig-control refuses the launch), and the generated C# has no default:
    # it reads 0, which ScaleWidths refuses at Go (tests\interleave.ps1).
    for doc in ({"taskParameters": {}}, {}):
        with pytest.raises(ValidationError):
            CoenQcCalibrateValveTaskLogic.model_validate(doc)
        assert list(jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).iter_errors(doc))
    generated = GENERATED.read_text(encoding="utf-8")
    assert '"minPulseWidthMs", Required=Newtonsoft.Json.Required.Always' in generated
    assert "_minPulseWidthMs = " not in generated.split("public CoenQcCalibrateValveTaskParameters()", 1)[1].split("}", 1)[0]
