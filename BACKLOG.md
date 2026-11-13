# Backlog

## Measure the in/out (Radial) motors' forward travel

Since 12 Nov 2026 the calibration moves both Radial motors (motors 2 and 3) to 15000 steps from home before Ready, a fixed number in `src\main.bonsai` (the Spouts include's SpoutsForwardSteps) (Pip: "Just go with 8000 for both", then "make it 15000"). Nothing records the real travel: the motor (8E12S0604AA4-050RS) is likely a 4 mm lead on a 50 mm screw, and there is no forward limit switch, only the home switch. If 15000 is past the end, the motor stalls against it, skipping steps and grinding until the move's time is up; the next run re-zeroes on the home switch, so positions recover, but the stall strains the screw and nut. To do: on each rig, step a Radial forward by hand until it stops, note the steps, and set the number below the smallest; if rigs differ, read it per rig instead.
