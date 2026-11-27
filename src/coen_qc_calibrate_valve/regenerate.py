import json
import subprocess
from pathlib import Path

import pydantic

import coen_qc_calibrate_valve.task

SCHEMA_ROOT = Path("./src/DataSchemas/")
EXTENSIONS_ROOT = Path("./src/Extensions/")


def regenerate(model_type: type, schema_file: Path) -> None:
    """Write the JSON schema for one root model and run Bonsai.Sgen on it."""
    model = pydantic.RootModel[model_type]
    schema = model.model_json_schema(by_alias=True, mode="serialization", union_format="primitive_type_array")
    schema_file.write_text(json.dumps(schema, indent=2))
    subprocess.run(
        [
            "dotnet",
            "bonsai.sgen",
            str(schema_file),
            "--output",
            str(EXTENSIONS_ROOT),
            "--serializer",
            "json",
            "--serializer",
            "yaml",
        ],
        check=True,
    )


def main():
    """Regenerate the task's JSON schema and Bonsai.Sgen C# classes from its pydantic model (the rig's are lib-open-rigs' OpenRigs.Devices.Rigs)."""
    SCHEMA_ROOT.mkdir(parents=True, exist_ok=True)
    EXTENSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    regenerate(coen_qc_calibrate_valve.task.CoenQcCalibrateValveTaskLogic, SCHEMA_ROOT / "coen_qc_calibrate_valve_task.json")


if __name__ == "__main__":
    main()
