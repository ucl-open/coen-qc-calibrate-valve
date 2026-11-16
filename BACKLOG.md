# Backlog

History is in `git log`.

## Open

- Measure the in/out (Radial) motors' forward travel. Since 12 Nov 2026 the calibration moves both Radial motors (2 and 3) to 15000 steps from home before Ready (`Spouts.bonsai`'s `SpoutsForwardSteps`; Pip: "make it 15000"). There is no forward limit switch: past the end the motor stalls and grinds until the move's time is up. On each rig, step a Radial forward by hand until it stops, note the steps, and set the number below the smallest; if rigs differ, read it per rig.
- The balance camera's names: `Camera-Temporary` is lib LiveView's rule for a device a workflow brings itself, and `CameraExposureUs` is the parameter app-rig-control's Calibrations page sets. `Camera-Balance` and `BalanceCameraExposureUs` need lib LiveView to stream a named instance rig.yml lacks and app-rig-control's page renamed in the same sitting.

## Decided

- The calibration and the delivery use lib's pieces, never a device opened by hand (Pip, 16 Nov 2026); no experiment folder (`NoExperimentFolder`).
- Every pulse is fired by `FirePulses` on `ClockFromBoard`'s `Timestamp`, the board's 1 kHz analog data time.
- `valve-weights.csv` and `valve-pulses.csv` go through OpenRigs.Logging's `CsvWriter`.
- Fits are app-rig-control's tested Python, never C# here (Bonsai measures, Python computes).
