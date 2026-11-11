# coen-qc-calibrate-valve

Calibrates the reward valves on a Coen Lab rig, one valve or all of them in one run. It fires known pulse widths on the behavior board's valve lines and weighs what each burst delivers. rig-control turns the weights into the curve (pulse width in ms against volume per pulse in µl) where the rig's experiment workflows read it. Its bursts and weighings are the open-rigs dispense calibration's (`OpenRigs.Core:DispenseCalibration.bonsai`, see open-rigs' `docs/articles/calibration.md`), copied here without its fit; it uses the lab's open-rigs packages. Its one piece of C#, `src\Extensions\ValveInterleave.cs`, orders the bursts over the valves (below); it measures nothing and fits nothing.

## Bonsai Measures, rig-control Computes

This workflow drives the board and writes each burst's weights, nothing more. The curve, its checks and its history are written by rig-control's Python (`calibrations.py`, `fit_run` and `rebuild`), with tests, once the run has completed. The lab's rule (Pip, 7 Nov 2026) is that fits and derived files are tested Python, never C# in a workflow. The copied steps (`RunCalibration`, with `PrimeAndWeighBaseline` and `FireAndWeighSample`) no longer follow upstream's `DispenseCalibration`.

Run it from rig-control's Calibrations page, the only place it is offered: it is not in the Setup page's Workflow list. It is an open-rigs project under `ExperimentControl`, which the page launches, watches and stops.

## What It Takes

- **Launch properties, from rig-control.** The Calibrations page reads the rig's own rig.yml (`<ConfigRoot>\<MACHINE-NAME>\rig.yml`, the file av-dome reads) and launches with:
  - `PortName`: `behaviorBoard: main: portName`.
  - `OutputPulseEnable`: its `pulseController: outputPulseEnable`, written with commas (`DO1, DO2`).
  - `Channel`: the line's number.
  - `Channels`, for **Calibrate All**: every valve line's number, `1, 2`. Empty for one valve.
  - `FileName`: the line's calibration name. That is its own `artefact:` when rig.yml already calibrates it, else `valve-DO<n>`. For Calibrate All, `valve-all` (rig-control's calibrations.toml `all_file`).
  - `CameraSerialNumber`, `CameraExposureTime`: `camera: body:`'s, and `CameraFrequency`: `cameraTriggerController: trigger0Frequency`. The body camera runs on camera trigger 0 (DO0) and is streamed by `OpenRigs.LiveView` (5558) for the Calibrations page to show live; nothing is recorded. Trigger 1 stays off, so DO1 stays a valve line.
  
  The page refuses a line that `outputPulseEnable` does not list, and does not show one rig.yml gives another job (the domes' DO3, the Zapit TTL).
- **`config\valve-calibration.yml`**: the procedure (pulse widths, repeats, priming, fit, and how long each weighing waits). Committed, the same for every rig. Seven widths, closer together at the short end (20, 25, 30, 40, 50, 70 and 100 ms), each measured twice in rounds of all seven in a shuffled order (fixed in the file), each burst weighed once: 14 weighings (three rounds, 21, until 9 Nov 2026). Per burst 20 ms x 600, 25 ms x 480, 30 ms x 400, 40 ms x 300, 50 ms x 240, 70 ms x 171, 100 ms x 120 pulses, so every burst delivers about what 600 pulses at 20 ms do (volume taken as proportional to width). Pulses are 63 ms apart, 1.25 times the 50 ms av-dome leaves between a reward's pulses (rig.yml `interPulseInterval`).

## Every Valve in One Run

Pip, 7 Nov 2026: "an option to calibrate all valves (interleave left and right for each burst, obviously double number of calibrations) or each individual valve". With `Channels` set, `InterleaveValves` (`src\Extensions\ValveInterleave.cs`) expands the procedure once, at load: each sample once per valve, in turn (DO1's 40 ms burst, weighed, DO2's 40 ms burst, weighed, then the next width), and the priming pulses once per valve. Every spout delivers into the one container on the one balance, and each burst is weighed by difference before the next fires, so each valve's gain is its own. `ManualBalance`, `RunCalibration` and the weights file all follow the expanded procedure, so the prompts count every valve's bursts (`sample 3 of 42`) and the page knows burst n is valve (n - 1) mod the number of valves. `ValvePulseBurst` fires each burst on its sample's valve, and `ValveWeighingRow` writes its `channel`. One valve (`Channels` empty) gives the procedure as written.

`scripts\test-interleave.ps1` checks the expansion against the compiled extension, after lib-open-rigs' `check-workflow-builds.ps1` has built it.

## The Balance, Read by Eye

The balance is read by eye: the workflow runs `OpenRigs.Devices:ManualBalance.bonsai`, and nothing is plugged into the computer. From Start it follows the procedure's bursts by the pulses fired. Once each burst has landed, it asks for a weight in the `weigh` metric: the baseline after priming, then each sample's. The Calibrations page shows that prompt in a band, which turns amber with its box highlighted while a weight is due: read the balance, type the number in grams and press Enter (the `Weight` command). The next weight given is that burst's reading. A weight given when none is due, or text that is not a number, is refused in `weigh`, and the run waits. Each weighing waits up to an hour. Leave the container on the balance throughout: each sample is the difference from the one before.

## The Balance, Read from the Camera

The body camera can see the balance's display, so rig-control's Calibrations page reads the weights itself. Each `Snapshot` command (its text a file name) saves the camera's latest frame, full size, as `calibration\images\<text>.jpg` beside rig.yml. The page asks for one once each weight is due, reads the display from it and sends the number with `Weight`, as a person would. The workflow does not know who read it. See rig-control's README for the reading, its checks and the review at the end.

## A Run

1. On the Calibrations page, press **Calibrate All Valves** or one valve's **Calibrate** on the Valves bar, and give your Lab PIN.
2. **Ready** once the board has answered. Put a container on the balance under the spout (under every spout, for all of them).
3. Press **Start**. The procedure primes the line (5 pulses of 500 ms), asks for the baseline weight, fires each sample's pulses and asks for each weight.
4. **Finished** once every burst is weighed (`points` says how many). rig-control then builds the curve and the page lists the volume per pulse at each width and shows it, or says why nothing was written.

## Delivering Water at a Reward Size

`src\deliver.bonsai` checks a calibration by weighing what it gives. It writes nothing. On a valve's details, the Calibrations page reads the reward size's pulse width off the curve, then launches it with `Channel`, `SizeMs` and `Pulses` (1 ml at that size), and with the board and the stage as for a calibration. On a rig with a lick spout stage, the spouts go forward before **Ready** and back after (main.bonsai's Spouts group, copied). Go fires the pulses on `TriggerCalibratedPulse`, 63 ms apart (`InterPulseIntervalMs`), and reports each pulse as the `delivered` metric. **Finished** comes once the last pulse has landed.

## What It Writes

The workflow writes `calibration\<FileName>-weights.csv` beside rig.yml, one row per burst as it is weighed, replaced each run: `size` (pulse width, ms), `repeats` (pulses), `before` and `after` (the balance in grams before and after the burst; the first row's `before` is the baseline after priming), and `channel` (the line it fired on, 1 to 3).

Once the run completes, rig-control writes `calibration\<FileName>.json` (for all of them, each valve's own artefact, from its rows alone; if any valve's curve fails a check, none is written), the open-rigs `CalibrationCurve` that experiments' `CalibratedPulse` reads: each sample's volume per pulse is its gain over its pulses and the density, in µl, as `DispenseCalibration` built it. A dated copy goes in `calibration\history\`, with the run's weights under the same date (kept whether or not they could be fitted). It refuses, writing no curve, a run that did not weigh every burst, bursts that are not the procedure's (the file changed since), a burst that delivered nothing, and a curve that is not monotone. A run that is stopped is not fitted.

A line still set to `FixedPulse` keeps its fixed width until rig.yml points it at the artefact. The Calibrations page says so, and its Use Calibration button makes that change, once asked and with a Lab PIN, to that line alone (the rest of rig.yml, comments included, kept as it was, the old file in `_backups`):

```yaml
DO1: { discriminatorType: CalibratedPulse, artefact: calibration/valve-DO1.json }
```

`calibratedBy` is whoever launched the run, as rig-control knows them from the Lab PIN.

## Setup

`scripts\deploy.ps1` (or `.bonsai\Setup.ps1`) installs Bonsai and the packages. The lab's packages come from lib-open-rigs (`workflows.txt` there); never bump them here by hand.
