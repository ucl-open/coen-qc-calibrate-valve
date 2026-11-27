"""The task file's schema: config/task-valve.yml, which app-rig-control writes at launch and again at Go with the form's
edits; the calibration (src\\main.bonsai) reads the copy (TaskPath) at Go. Its one setting is the shortest pulse width."""

from typing import Literal

from open_rigs.core.task import Task
from pydantic import Field
from swc.aeon.schema import BaseSchema

from coen_qc_calibrate_valve import __semver__


class CoenQcCalibrateValveTaskParameters(BaseSchema):
    """Task params."""

    # Required, no default (audit r1, finding 5): a task file without it is refused by app-rig-control at connect, and
    # the generated C# then reads 0, which ScaleWidths refuses at Go, never a silent 20 ms on a rig whose minimum is not.
    min_pulse_width_ms: int = Field(
        ...,
        ge=5,
        le=100,
        description="Shortest calibrated pulse width, in ms (5 to 100). At Go every width in config\\valve-calibration.yml is scaled so the smallest is this and the largest 5 times it",
    )


class CoenQcCalibrateValveTaskLogic(Task):
    """Top-level task logic schema."""

    version: Literal[__semver__] = __semver__
    name: Literal["CoenQcCalibrateValve"] = Field(default="CoenQcCalibrateValve", description="Name of the task", frozen=True)
    task_parameters: CoenQcCalibrateValveTaskParameters
