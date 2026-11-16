# Backlog

## 2026-11-16 NoExperimentFolder (OpenRigs.Logging .16)

Done: `src\main.bonsai` and `src\deliver.bonsai` include lib-open-rigs' `NoExperimentFolder` (`SubjectId` `_valve-calibration_`) in their Settings group, in place of their own never-published `PathPrefix`; `src\Extensions\Spouts.bonsai` drops its own `SubjectId` (the same `_valve-calibration_`). Nothing written changes: no piece logs, the spouts still go to rig.yml's `lickSpoutDefaultPosition`, and the weights and pulses files are as before. `tests\test_workflow.py` holds both workflows to `no_experiment_folder_problems`.

## 2026-11-16 PulseClock gone: ClockFromBoard's Timestamp is the 1 kHz analog data time (OpenRigs.Devices .23)

Done: OpenRigs.Devices .23 (lib-open-rigs, unpushed) publishes `ClockFromBoard`'s `Timestamp` from the board's AnalogData events, as `PulseClock` did, so `PulseClock` is deleted and all six `FirePulses` (five in main, one in deliver) take `Timestamp`. Pulse spacing unchanged: each next pulse fires on the first 1 ms tick at least `pulseGapMs` (80) after the last one closes. `tests\test_workflow.py` holds every `FirePulses` to `Timestamp` and reads the installed package's `ClockFromBoard`. The Python tests need lib's lint (`uv pip install` the lib clone, `uv run --no-sync`) until `update-workflows` moves the open-rigs pin past 38aed51.

## 2026-11-16 Onto the lab's device pieces (lib-open-rigs 5ea5729)

Done: the calibration and the delivery use lib's pieces, never a device opened by hand (Pip, 16 Nov 2026): `ReadyGate`, `BehaviorBoard`, `ClockFromBoard`, `PulseOutputs`, and `LickSpoutStage` behind the rig's stage (was the old `BehaviorBoard` include with its own `RigDevice`, `PulseController`, `BehaviorBoard.Timestamps` and `HarpLickSpoutStage`). `PathPrefix` declared and never published, so no piece logs. Every pulse fires as before: the same ValveTrains, DripTrains, TestTrain and DeliverTrain into the same `FirePulses` (unchanged in lib from 38aed51 to 5ea5729), on the same clock (the board's analog data time, now `PulseClock`), into the same `PulseController` (unchanged). Changes, each an improvement:
- `-pulses.csv`: the setup rows before the first pulse show `PulseDO1` to `PulseDO3` at 1 ms (PulseOutputs' placeholder), not 10 ms. Every fired pulse still writes its own width first. Columns and file names unchanged.
- The pulse-enabled lines are rig.yml's `outputPulseEnable` without the ZapitTrigger line (was the RewardValve lines), the same lines on every rig, and a RewardValve line missing from `outputPulseEnable` stops it at Start, as it stops every task.
- The ZapitTrigger line is cleared however the workflow stops (BehaviorBoard's `ClearOutputsOnStop`); the board's clock is set to UTC, re-sent until it agrees, and a clock that stops for 3 s stops the workflow (ClockFromBoard).
- `tests\rigs\box.yml`: camera `triggerFrequency` dropped (the lab rig model refuses it) and `pixelFormat: Mono8` written out.

Suggestions for lib (lib frozen at 5ea5729 for this push):
- Done in Devices .23 (above): `ClockFromBoard`'s `Timestamp` was the heartbeat, once a second, so `FirePulses` on it (DeliverReward on a box-clocked rig) fired one pulse a second.
- `hardware_problems` knows only the pieces' Ready stages; this workflow announces its own (`CalibrationReady`, `DeliveryReady`: pulse setup out and spouts in), so `tests\test_workflow.py` expects that one problem. A `ReadyGate` property for a workflow's own stages, or lint reading local includes, would end the exception.
- A conditional piece (a stage only where rig.yml has one) is invisible to `required_devices` here, as it sits in `Extensions\Spouts.bonsai`.

## Audit round 3 of 3 (15 Nov 2026)

- `scripts\deploy.ps1` exits 1 naming `.bonsai\Setup.ps1` when it is missing (a missing script left the last exit code, 0).

## Audit round 3 of 3 (15 Nov 2026): items not changed

- `.bonsai\Setup.ps1` is the same 15 lines in five task repos (coen-dome-navigation, coen-dome-decision-making, coen-behaviour-box, coen-qc-calibrate-valve, coen-qc-preflight-rig): each repo needs its own bootstrap.

## 2026-11-14 Dome-task alignment audit

- **Done 15 Nov 2026: log through the lab's loggers.** `valve-weights.csv` (`pulseWidthMs`, `pulses`, `beforeG`, `afterG`, `channel`, `pulseGapMs`) and `valve-pulses.csv` (`harpTime`, `register`, `value`) are written by OpenRigs.Logging's `CsvWriter`. Was: written by Bonsai's own `CsvWriter` (dome-task alignment audit, 14 Nov 2026).

## Measure the in/out (Radial) motors' forward travel

Since 12 Nov 2026 the calibration moves both Radial motors (motors 2 and 3) to 15000 steps from home before Ready, a fixed number in `src\main.bonsai` (the Spouts include's SpoutsForwardSteps) (Pip: "Just go with 8000 for both", then "make it 15000"). Nothing records the real travel: the motor (8E12S0604AA4-050RS) is likely a 4 mm lead on a 50 mm screw, and there is no forward limit switch, only the home switch. If 15000 is past the end, the motor stalls against it, skipping steps and grinding until the move's time is up; the next run re-zeroes on the home switch, so positions recover, but the stall strains the screw and nut. To do: on each rig, step a Radial forward by hand until it stops, note the steps, and set the number below the smallest; if rigs differ, read it per rig instead.
