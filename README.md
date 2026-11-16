# coen-qc-calibrate-valve

Calibrates the reward valves on a Coen Lab rig, one valve or all of them in one run. It fires known pulse widths on the behavior board's valve lines and weighs what each burst delivers. rig-control turns the weights into the curve (pulse width in ms against volume per pulse in µl) where the rig's experiment workflows read it. Every burst is fired by lib-open-rigs' `OpenRigs.Core` `FirePulses` on the rig's Harp clock, at the procedure's one `pulseGapMs`, the operator and gap a rig then fires its rewards with (lib-open-rigs `docs/articles/calibration.md`). Its C# (`src\Extensions`) reads rig.yml, orders the bursts over the valves and turns them into pulse trains; it measures nothing and fits nothing.

## Bonsai Measures, rig-control Computes

This workflow drives the board and writes each burst's weights, nothing more. The curve, its checks and its history are written by rig-control's Python (`calibrations.py`, `fit_run` and `rebuild`), with tests, once the run has completed. The lab's rule (Pip, 7 Nov 2026) is that fits and derived files are tested Python, never C# in a workflow. The copied steps (`RunCalibration`, with `PrimeAndWeighBaseline` and `FireAndWeighSample`) no longer follow upstream's `DispenseCalibration`.

Run it from rig-control's Calibrations page, the only place it is offered: it is not in the Setup page's Workflow list. It is an open-rigs project under `ExperimentControl`, which the page launches, watches and stops.

## What It Takes

- **Launch properties, from rig-control.**
  - `Channel`: the line to calibrate, 1 to 3. `Channels`, for **Calibrate All**: every valve line, `1, 2`; empty for one valve.
  - `FileName`: the line's calibration name, its own `artefact:` when rig.yml already calibrates it, else `valve-DO<n>`; for Calibrate All, `valve-all` (rig-control's calibrations.toml `all_file`).
- **rig.yml, read by the workflow** (`<ConfigRoot>\<MACHINE-NAME>\rig.yml`), into the lab rig model every lab workflow reads (lib-open-rigs' `OpenRigs.Devices:ReadLabRig.bonsai`, `LabRig`), so a dome's, a box's and an arena's rig.yml all serve, and a key the model lacks stops it at Start as it stops every workflow. It takes `behaviorBoard: main:` for its port, the board's `wiring` lines whose `device` is `RewardValve` (`OpenRigs.Devices` `WiredOutputs`, each on DO1 to DO3), the board's `pulseController.outputPulseEnable`, and `stepperDriver: a:` and `b:` when the rig has a stage, whose spouts go to rig.yml's `lickSpoutDefaultPosition` (a valve calibration is not a mouse's). It stops at Start when rig.yml has no board main or no RewardValve on DO1 to DO3, when a RewardValve line is not in `outputPulseEnable`, and when `Channel` or `Channels` names a line that is not a RewardValve. The lines pulse-enabled are `outputPulseEnable` without the ZapitTrigger line, as in a session. `tests\rigs` holds a box, an arena and a dome rig.yml the tests read, each one the lab rig model takes.
- **`config\valve-calibration.yml`**: the procedure (pulse widths, pulses, `pulseGapMs`, priming, how long each weighing waits). Committed, the same for every rig. Seven widths, closer together at the short end, written for a 20 ms minimum (20, 25, 30, 40, 50, 70 and 100 ms) and scaled at Go to the rig's `MinPulseWidthMs` (below), each measured twice in rounds of all seven, each round in a new random order every run (Pip, 11 Nov 2026), each burst weighed once: 14 weighings. Per burst 20 ms x 600, 25 ms x 480, 30 ms x 400, 40 ms x 300, 50 ms x 240, 70 ms x 171, 100 ms x 120 pulses, so every burst delivers about what 600 pulses at the smallest width do. `pulseGapMs` is the off-to-on time between pulses, 80 ms (63 until 11 Nov 2026), the same for every sample: the calibration file records one, so samples at different gaps stop the workflow at Start. Each pulse as the board fired it goes to `calibration\<FileName>-pulses.csv` (board seconds, register, value: `OutputSet` starts a pulse, `PulseDO1` to `PulseDO3` its width just before; the first `PulseDO` rows, before any pulse, are `PulseOutputs`' 1 ms setup), kept in `history\` with the weights.
- **Parameters and commands, from rig-control's Calibrations page.** `MinPulseWidthMs` (5 to 100 ms, 20 by default) is the rig's shortest calibrated width: at Go `ScaleWidths` (`src\Extensions\ValveInterleave.cs`) multiplies every written width by `MinPulseWidthMs` over the smallest written (20), rounded half away from zero, so the smallest is `MinPulseWidthMs` and the largest 5 times it; pulses, gaps and priming stay as written. `Drip`, while a weight is due, fires more pulses at the width being weighed on its valve until the balance moves, so a drop hanging on the spout falls before the reading: its text is the pulses, 1 to 100, and for the baseline the line too (`1 DO2`, at the largest width); a sample's drip pulses are added to its `pulses`, and ManualBalance never counts them as a burst. `Test`, before Go only, fires a few pulses so a valve can be seen opening: its text is the width in ms (1 to 500), the pulses (1 to 100) and the line, such as `20 10 DO1`; it is counted nowhere and ignored after Go. `Weight` and `Snapshot` are below.

## One Workflow per Rig Kind

Pip, 16 Nov 2026: the calibration and the delivery go per rig kind, as the preflight does (coen-qc-preflight-rig's `dome.bonsai` and `box.bonsai`). On a dome the timestamp generator drives the board's clock, so the dome's workflows take the generator's clock (`ClockFromTimestampGenerator`, `TimestampGeneratorGen3-Main`, as lib-open-rigs' `DomeHardware`); a behaviour box has no generator and takes the board's own (`ClockFromBoard`, as `BehaviorBoxHardware`).

| | Dome (`rig-av-dome`) | Behaviour box (`rig-behaviour-box`), arena (`rig-av-arena`) |
|---|---|---|
| Calibration | `src\dome.bonsai` | `src\box.bonsai` |
| Delivery | `src\deliver-dome.bonsai` | `src\deliver-box.bonsai` |

rig-control's calibrations.toml `[[valve.by_profile]]` picks the pair by the machine's profile; the arena has no timestamp generator, so it takes the box's. Any other profile (a desk) has none. Each pair is the same file but for the clock piece and the words that name it (`tests\test_workflow.py` holds them so).

## The Hardware: the Lab's Device Pieces

Pip, 16 Nov 2026: a QC workflow uses the same lib-open-rigs pieces as the tasks, never a device opened by hand, so each device's code exists once. Each workflow lists them (a rig list such as `DomeHardware` would open the dome's cameras, speakers and projector too): `ReadLabRig`, `ReadyGate`, `BehaviorBoard` (`BehaviorBoard-Main`, which clears any ZapitTrigger line however the workflow stops), the rig's clock and `PulseOutputs`; `src\Extensions\Spouts.bonsai` runs `LickSpoutStage` only on a rig whose rig.yml has a stage. A calibration has no experiment folder: lib-open-rigs' `NoExperimentFolder` declares `PathPrefix`, never published, so no piece logs, and `SubjectId` `_valve-calibration_`, no mouse's, so the spouts go to rig.yml's `lickSpoutDefaultPosition`. Every pulse is timed on the clock's `Timestamp`. Ready (`ReadyGate`) waits for the clock and the workflow's own stage (ReadyGate's `WorkflowStages`: `CalibrationReady`, `DeliveryReady`): 1 s after the board's first event, once `PulseOutputs` has put the lines in pulse mode, and the spouts in.

## Every Valve in One Run

Pip, 7 Nov 2026: "an option to calibrate all valves (interleave left and right for each burst, obviously double number of calibrations) or each individual valve". With `Channels` set, `InterleaveValves` (`src\Extensions\ValveInterleave.cs`) expands the procedure once, at load: each sample once per valve, in turn (DO1's 40 ms burst, weighed, DO2's 40 ms burst, weighed, then the next width), and the priming pulses once per valve. Every spout delivers into the one container on the one balance, and each burst is weighed by difference before the next fires, so each valve's gain is its own. `ManualBalance`, `RunCalibration` and the weights file all follow the expanded procedure, so the prompts count every valve's bursts (`sample 3 of 42`) and the page knows burst n is valve (n - 1) mod the number of valves. `ValveTrains` turns each burst into a pulse train on its sample's valve for `FirePulses`, and `ValveWeighingRow` writes its `channel`. One valve (`Channels` empty) gives the procedure as written.

`uv run pytest` builds the extension and checks the expansion against it (`tests\interleave.ps1`, run by `tests\test_extensions.py`). `uv run pytest` checks `config\valve-calibration.yml` against lib-open-rigs' `DispenseCalibration` (one `pulseGapMs`, widths 20 to 100 ms in equal rounds) and against the schema its first line names, the pinned open-rigs' `calibration.json`, closed to unknown keys as the shared build check reads it (no key the workflow would refuse), and that each `tests\rigs` file wires its reward valves on DO1 to DO3.

## The Balance, Read by Eye

The balance is read by eye: the workflow runs `OpenRigs.Devices:ManualBalance.bonsai`, and nothing is plugged into the computer. From Start it follows the procedure's bursts by the pulses fired. Once each burst has landed, it asks for a weight in the `weigh` metric: the baseline after priming, then each sample's. The Calibrations page shows that prompt in a band, which turns amber with its box highlighted while a weight is due: read the balance, type the number in grams and press Enter (the `Weight` command). The next weight given is that burst's reading. A weight given when none is due, or text that is not a number, is refused in `weigh`, and the run waits. Each weighing waits up to an hour. Leave the container on the balance throughout: each sample is the difference from the one before.

## The Balance, Read from the Camera

The calibration camera, a USB camera on the balance that is in no rig.yml (Pip, 10 Nov 2026: a different one on each rig), sees the balance's display, so rig-control's Calibrations page reads the weights itself. `OpenRigs.Video` `UsbCamera` opens the first camera that is not one of the rig's own; with none plugged in the workflow stops at Start, saying so. Each `Snapshot` command (its text a file name) saves the camera's latest frame, full size, as `calibration\images\<text>.jpg` beside rig.yml. The page asks for one once each weight is due, reads the display from it and sends the number with `Weight`, as a person would. The workflow does not know who read it. See rig-control's README for the reading, its checks and the review at the end.

## A Run

1. On the Calibrations page, press **Calibrate All Valves** or one valve's **Calibrate** on the Valves bar, and give your Lab PIN.
2. **Ready** once the board has answered, its clock is set and the spouts are in. Put a container on the balance under the spout (under every spout, for all of them).
3. Press **Start**. The procedure primes the line (5 pulses of 500 ms), asks for the baseline weight, fires each sample's pulses and asks for each weight.
4. **Finished** once every burst is weighed (`points` says how many). rig-control then builds the curve and the page lists the volume per pulse at each width and shows it, or says why nothing was written.

## Delivering Water at a Reward Size

The delivery (`src\deliver-dome.bonsai`, `src\deliver-box.bonsai`) checks a calibration by weighing what it gives. It writes nothing. On a valve's details, the Calibrations page reads the reward size's pulse width off the curve, then launches it with `Channel`, `PulseWidthMs`, `Pulses` (1 ml at that size), and `PulseGapMs` (the curve's `pulseGapMs`); the board and the stage come from rig.yml as for a calibration. On a rig with a lick spout stage, the spouts go to the in position before **Ready** and out after. Go fires the pulses with `FirePulses` on the Harp clock and reports each as the `delivered` metric. **Finished** comes once the last pulse has closed.

## What It Writes

The workflow writes `calibration\<FileName>-weights.csv` beside rig.yml, one row per burst as it is weighed, replaced each run, by OpenRigs.Logging's `CsvWriter` (the lab's logger): `pulseWidthMs` (pulse width, ms), `pulses`, `beforeG` and `afterG` (the balance in grams before and after the burst; the first row's `beforeG` is the baseline after priming), `channel` (the line it fired on, 1 to 3) and `pulseGapMs` (the off-to-on time between its pulses, ms). These raw rows, with the pulses file, are all it writes.

Once the run completes, rig-control's Python writes `calibration\<FileName>.json` (for all of them, each valve's own artefact, from its rows alone; if any valve's curve fails a check, none is written), the open-rigs `CalibrationCurve` of lib-open-rigs' `fixtures\calibration\valve-DO1.json`: it adds `calibratedAt`, `calibratedBy`, `machineName`, `notes`, the axis names and units, the `points` (each burst's gain over its pulses and the density, in µl per pulse), `payloadPath`, the one `pulseGapMs` and the `linearFit` (slope, intercept, `minX`, `maxX`). A dated copy goes in `calibration\history\`, with the run's weights under the same date. It refuses, writing no curve, a run that did not weigh every burst, bursts that are not the procedure's, samples at different gaps, a burst that delivered nothing, and a fit whose slope is not above 0. A run that is stopped is not fitted.

A line still set to `FixedPulse` keeps its fixed width until rig.yml points it at the artefact. The Calibrations page says so, and its Use Calibration button makes that change, once asked and with a Lab PIN, to that line alone (the rest of rig.yml, comments included, kept as it was, the old file in `_backups`):

```yaml
DO1: { discriminatorType: CalibratedPulse, artefact: calibration/valve-DO1.json }
```

`calibratedBy` is whoever launched the run, as rig-control knows them from the Lab PIN.

## Setup

`scripts\deploy.ps1` (or `.bonsai\Setup.ps1`) installs Bonsai and the packages. The lab's packages come from lib-open-rigs through app-rig-setup's `workflows\update-workflows.ps1`, which reads `profile-repos.json` and the rules file's `extraWorkflows`; never bump them here by hand.
