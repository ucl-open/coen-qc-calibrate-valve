# Backlog

History is in `git log`.

## Open

- Measure the radial motors' travel in (towards the mouse). The calibration moves Radial-Left and Radial-Right to 15000 steps from home before Ready (`Spouts.bonsai`'s `RadialInSteps`; Pip: "make it 15000"). There is no limit switch at that end: past it the motor stalls and grinds until the move's time is up. On each rig, step a radial in by hand until it stops, note the steps, and set the number below the smallest; if rigs differ, read it per rig.
- Run `main.bonsai` and `deliver.bonsai` once on a dome on the lib-open-rigs it pins (`.bonsai\Bonsai.config`) before relying on them: neither has run with `SetClock` false. Ready comes once the board's time is read, Calibrate All weighs every burst and the curve is written, and a delivery fires its pulses at the curve's gap.

## Decided

- The one setting, the shortest pulse width, is the task file's (`config\task-valve.yml`, `taskParameters.minPulseWidthMs`, read at Go into `TaskConfig`), never a controller parameter (Pip, 27 Nov 2026: app-rig-control's Parameters tab goes).
- The calibration and the delivery use lib's pieces, never a device opened by hand (Pip, 16 Nov 2026); no experiment folder (`NoExperimentFolder`).
- The clock (Pip, 16 Nov 2026): one calibration (`main.bonsai`) and one delivery (`deliver.bonsai`) for every rig with valves, setting no clock. `ClockFromBoard` with `SetClock` false reads the board's time (on a dome it follows the generator); Ready waits for `HarpClockRead`.
- Every pulse is fired by `FirePulses` on `ClockFromBoard`'s `Timestamp`.
- `<FileName>-weights.csv` and `<FileName>-pulses.csv` go through OpenRigs.Logging's `CsvWriter`.
- Fits are app-rig-control's tested Python, never C# here (Bonsai measures, Python computes).
- Valves by piece name (`Valve`, `Valves`, the weights file's `valve` column) through lib's `WiredRewardValve`; one board opened (`BehaviorBoard-Main`) until a rig has two. A rig with a second board (the arena) brings it in through its rig list, and the calibration then gets one firing branch per board, routed on the valve's board.

## Not recommended

- ManualPulses allowed on a RewardValve line (lib's lint, `workflow_lint.py:587-611`): flushing a valve is its job, and a calibrated pulse writes its own width.
- No shared hardware include for the valve: one `main.bonsai` and `deliver.bonsai` for every rig, setting no clock, was chosen 16 Nov 2026 (see Decided).
- Calibrate and deliver not merged: they differ in inputs, the camera and the fit guard.
- One `FirePulses` for every train not built: it restructures a hardware-tested workflow, and the `TakeUntil` fix covers the bug.

## Audit 2026-11-22 (/audit-rigs, pipeline)

Changed (b878575): CI runs `scripts\check-workflow.ps1` in place of the C# 5 and parse steps, and the header no longer calls the check private (P6S-L1).

Deferred: a manual Checks run of the new step.

Not changed, do not raise again without new information:

- None in this repo this round.
