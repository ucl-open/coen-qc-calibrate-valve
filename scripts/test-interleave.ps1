# Checks src\Extensions without the rig: the rig model (tests\rigs: a box, an arena and a dome
# rig.yml, and the refusals), the valves parsed from Channels, the procedure expanded over them
# (each sample once per valve, in turn; priming once per valve; one pulseGapMs), each burst's
# PulseTrain for FirePulses, and the spouts' targets.
# Run after lib-open-rigs' check-workflow-builds.ps1 has compiled the extension, which leaves
# Extensions.dll and its packages in %TEMP%\check-workflow-builds-<this repo's folder name>.
# Exit 0 when every check passes.
param([string]$Bin = (Join-Path ([IO.Path]::GetTempPath()) ('check-workflow-builds-' + (Split-Path (Split-Path $PSScriptRoot) -Leaf))))
$ErrorActionPreference = 'Stop'
foreach ($dll in 'System.Reactive.Interfaces', 'System.Reactive.Core', 'System.Reactive.Linq', 'Bonsai.Core', 'YamlDotNet', 'Harp.Behavior', 'OpenRigs.Core', 'OpenRigs.Devices', 'Extensions') {
    $null = [Reflection.Assembly]::LoadFrom((Join-Path $Bin "$dll.dll"))
}
$rigs = Join-Path (Split-Path $PSScriptRoot) 'tests\rigs'
$failed = 0
function Check($name, $ok) {
    if ($ok) { "  ok    $name" } else { "  FAIL  $name"; $script:failed++ }
}
function Refused($block) { try { $null = & $block; $false } catch { $true } }
function Train($t) { "$($t.Count)x$($t.WidthMs)@DO$($t.Line)/$($t.PulseGapMs)" }

# The rig model: a box, an arena and a dome all read; only the valve lines and the stage are taken.
$box = [CoenQcCalibrateValve.ValveRig]::Read((Join-Path $rigs 'box.yml'))
Check 'box: port, one valve, no stage' (($box.PortName -eq 'COM3') -and ((@($box.Valves) -join ',') -eq '1') -and -not $box.HasStage)
Check 'box: only the valve line pulsed' ("$($box.OutputPulseEnable)" -eq 'DO1')
$arena = [CoenQcCalibrateValve.ValveRig]::Read((Join-Path $rigs 'arena.yml'))
Check 'arena: two valves, no stage' (((@($arena.Valves) -join ',') -eq '1,2') -and -not $arena.HasStage -and ("$($arena.OutputPulseEnable)" -eq 'DO1, DO2'))
$dome = [CoenQcCalibrateValve.ValveRig]::Read((Join-Path $rigs 'dome.yml'))
Check 'dome: two valves, not the Zapit line' (((@($dome.Valves) -join ',') -eq '1,2') -and ("$($dome.OutputPulseEnable)" -eq 'DO1, DO2'))
Check 'dome: the stage on StepperDriver-A and -B' ($dome.HasStage -and $dome.StepperDriverA.Name -eq 'StepperDriver-A' -and $dome.StepperDriverA.Settings.PortName -eq 'COM5' -and $dome.StepperDriverB.Settings.PortName -eq 'COM6')
Check 'a valve wiring does not give is refused' (Refused { $arena.Check([int[]]@(3)) })
Check 'a wired valve passes' (-not (Refused { $dome.Check([int[]]@(2, 1)) }))

$tmp = Join-Path ([IO.Path]::GetTempPath()) "test-interleave-$PID"
New-Item -ItemType Directory -Force $tmp | Out-Null
$refusals = [ordered]@{
    'no RewardValve (a box today)' = "behaviorBoard:`n  main:`n    portName: COM3`n    pulseController: null`n"
    'a RewardValve off DO1 to DO3' = "behaviorBoard:`n  main:`n    portName: COM3`n    wiring:`n      DOPort0: { device: RewardValve }`n"
    'no port' = "behaviorBoard:`n  main:`n    portName: null`n    wiring:`n      DO1: { device: RewardValve }`n"
    'no board main' = "behaviorBoard:`n  left:`n    portName: COM3`n"
    'a stage with one driver' = "behaviorBoard:`n  main:`n    portName: COM3`n    wiring:`n      DO1: { device: RewardValve }`nstepperDriver:`n  a: { portName: COM5 }`n"
}
foreach ($case in $refusals.Keys) {
    $file = Join-Path $tmp 'rig.yml'
    [IO.File]::WriteAllText($file, $refusals[$case])
    $message = ''
    try { $null = [CoenQcCalibrateValve.ValveRig]::Read($file) } catch { $message = $_.Exception.InnerException.Message; if (-not $message) { $message = $_.Exception.Message } }
    Check "refused, naming the rule's home: $case" ($message -like '*valve calibration rig model*')
}
Check 'no rig.yml refused' (Refused { [CoenQcCalibrateValve.ValveRig]::Read((Join-Path $tmp 'none.yml')) })
Remove-Item $tmp -Recurse -Force

function New-Sample($size, $repeats, $gap) {
    $sample = New-Object OpenRigs.Core.Calibration.DispenseSample
    $sample.Size = $size; $sample.Repeats = $repeats; $sample.PulseGapMs = $gap
    $sample
}
function New-Settings($sizes = @(@(40, 250), @(20, 500)), $gap = 80) {
    $settings = New-Object OpenRigs.Core.Calibration.DispenseCalibration
    $procedure = New-Object OpenRigs.Core.Calibration.DispenseProcedure
    $samples = New-Object 'System.Collections.Generic.List[OpenRigs.Core.Calibration.DispenseSample]'
    foreach ($s in $sizes) { $samples.Add((New-Sample $s[0] $s[1] $gap)) }
    $procedure.Samples = $samples
    $procedure.PrimingPulses = 5
    $settings.Procedure = $procedure
    $settings
}

$parse = [CoenQcCalibrateValve.Valves]
Check 'empty Channels is the one Channel' ((@($parse::Parse('', 2)) -join ',') -eq '2')
Check 'Channels as numbers' ((@($parse::Parse('1, 2', 1)) -join ',') -eq '1,2')
Check 'Channels as line names' ((@($parse::Parse('DO2,DO1', 1)) -join ',') -eq '2,1')
foreach ($bad in 'DO4', '1, 1', 'left') { Check "Channels '$bad' refused" (Refused { $parse::Parse($bad, 1) }) }

# One pulseGapMs (plan v11): the calibration file records it and a rig fires its rewards at it.
Check 'the gap is the samples'' one' ($parse::Gap((New-Settings).Procedure) -eq 80)
$mixed = New-Settings
$mixed.Procedure.Samples[1].PulseGapMs = 63
Check 'samples at different gaps refused' (Refused { $parse::Gap($mixed.Procedure) })
Check 'expanding samples at different gaps refused' (Refused { [CoenQcCalibrateValve.InterleaveValves]::Expand($mixed, [int[]]@(1), $null) })

$all = [CoenQcCalibrateValve.InterleaveValves]::Expand((New-Settings), [int[]]@(1, 2), $null).Procedure
$order = @($all.Samples | ForEach-Object { "$($_.Size)@$($_.Channel)" }) -join ' '
Check "two valves: each burst on each in turn ($order)" ($order -eq '40@1 40@2 20@1 20@2')
Check 'two valves: repeats and gap kept' ((@($all.Samples | ForEach-Object { "$($_.Repeats)/$($_.PulseGapMs)" }) -join ',') -eq '250/80,250/80,500/80,500/80')
Check 'two valves: priming once per valve, counted together' ($all.PrimingPulses -eq 10)
Check 'two valves: the valves read back in firing order' ((@([CoenQcCalibrateValve.Valves]::Of($all)) -join ',') -eq '1,2')

$one = [CoenQcCalibrateValve.InterleaveValves]::Expand((New-Settings), [int[]]@(2), $null).Procedure
$order = @($one.Samples | ForEach-Object { "$($_.Size)@$($_.Channel)" }) -join ' '
Check "one valve: the procedure as written ($order)" ($order -eq '40@2 20@2')
Check 'one valve: priming as written' ($one.PrimingPulses -eq 5)

# Shuffled rounds (Pip, 11 Nov 2026): round k is each width's k-th sample, in a random order; rounds in turn.
$orders = @{}
foreach ($seed in 1..40) {
    $settings = New-Settings @(@(40, 250), @(20, 500), @(20, 500), @(70, 100), @(40, 250), @(70, 100), @(20, 500))
    $s = [CoenQcCalibrateValve.InterleaveValves]::Expand($settings, [int[]]@(1, 2), (New-Object Random $seed)).Procedure.Samples
    $sizes = @($s | ForEach-Object { $_.Size })
    $ok = ((@($sizes[0..5] | Sort-Object) -join ',') -eq '20,20,40,40,70,70') -and ((@($sizes[6..11] | Sort-Object) -join ',') -eq '20,20,40,40,70,70') -and ((@($sizes[12..13]) -join ',') -eq '20,20')
    $ok = $ok -and ((@($s | ForEach-Object { $_.Channel }) -join '') -eq '12121212121212')
    $ok = $ok -and (@(0..6 | Where-Object { $sizes[2 * $_] -ne $sizes[2 * $_ + 1] }).Count -eq 0)
    $ok = $ok -and (@($s | Where-Object { $_.Repeats -ne @{20 = 500; 40 = 250; 70 = 100}[$_.Size] }).Count -eq 0)
    if (-not $ok) { break }
    $orders[($sizes -join ' ')] = 1
}
Check 'shuffled: every round has its widths, both valves in turn, repeats kept' $ok
Check "shuffled: the order changes from run to run ($($orders.Count) orders in 40)" ($orders.Count -gt 4)

# The bursts as FirePulses trains.
$rx = [System.Reactive.Linq.Observable]
function Obs($type, $value) { ($rx.GetMethods() | Where-Object { $_.Name -eq 'Return' -and $_.GetParameters().Count -eq 1 })[0].MakeGenericMethod($type).Invoke($null, @($value)) }
function Items($type, $source) { @(($rx.GetMethods() | Where-Object { $_.Name -eq 'ToEnumerable' })[0].MakeGenericMethod($type).Invoke($null, @($source))) }
$train = [CoenQcCalibrateValve.PulseTrain]
$trains = Items $train ((New-Object CoenQcCalibrateValve.ValveTrains).Process((Obs ([OpenRigs.Core.Calibration.DispenseSample]) $all.Samples[3])))
Check "a sample's burst: its pulses at its width on its valve at its gap ($(Train $trains[0]))" ((Train $trains[0]) -eq '500x20@DO2/80')
$all.PrimingSize = 500
$trains = @([CoenQcCalibrateValve.ValveTrains]::Priming($all, 1) | ForEach-Object { Train $_ })
Check "priming: an equal share on each valve in turn ($($trains -join ' '))" (($trains -join ' ') -eq '5x500@DO1/80 5x500@DO2/80')

# Drips (Pip, 8 Nov 2026): a Drip command's pulses at the sample's width on its valve; for the
# baseline, at the largest width on the line named.
$drip = [CoenQcCalibrateValve.DripTrains]
Check "Drip '5' is 5 pulses, no line" (($drip::Parse('5').Item1 -eq 5) -and ($drip::Parse('5').Item2 -eq 0))
Check "Drip '1 DO2' is 1 pulse on line 2" (($drip::Parse('1 DO2').Item1 -eq 1) -and ($drip::Parse('1 DO2').Item2 -eq 2))
foreach ($bad in '', '0', 'five', '1 DO4', '101') { Check "Drip '$bad' refused" (Refused { $drip::Parse($bad) }) }
$trains = Items $train ((New-Object CoenQcCalibrateValve.DripTrains).Process((Obs ([string]) '3'), (Obs ([OpenRigs.Core.Calibration.DispenseSample]) $all.Samples[3])))
Check "a sample's drip: its width on its valve ($(Train $trains[0]))" ((Train $trains[0]) -eq '3x20@DO2/80')
$trains = Items $train ((New-Object CoenQcCalibrateValve.DripTrains).Process((Obs ([string]) '1 DO2'), (Obs ([OpenRigs.Core.Calibration.DispenseProcedure]) $all)))
Check "the baseline's drip: the largest width on the line named ($(Train $trains[0]))" ((Train $trains[0]) -eq '1x40@DO2/80')

# A minimum per rig (Pip, 12 Nov 2026): the widths scaled so the smallest is MinPulseMs, pulses as written.
$ladder = { New-Settings @(@(40, 300), @(20, 600), @(25, 480), @(100, 120), @(30, 400), @(70, 171), @(50, 240)) }
$scale = [CoenQcCalibrateValve.ScaleWidths]
$scaled = $scale::Scale((& $ladder), 30).Procedure.Samples
Check "min 30: widths 30 to 150 ($(@($scaled | ForEach-Object { $_.Size }) -join ','))" ((@($scaled | ForEach-Object { $_.Size }) -join ',') -eq '60,30,38,150,45,105,75')
Check 'min 30: pulses as written' ((@($scaled | ForEach-Object { $_.Repeats }) -join ',') -eq '300,600,480,120,400,171,240')
$twice = $scale::Scale($scale::Scale((& $ladder), 15), 15).Procedure.Samples
Check "min 15: scaling twice is scaling once ($(@($twice | ForEach-Object { $_.Size }) -join ','))" ((@($twice | ForEach-Object { $_.Size }) -join ',') -eq '30,15,19,75,23,53,38')
Check 'min 20: the procedure as written' ((@($scale::Scale((& $ladder), 20).Procedure.Samples | ForEach-Object { $_.Size }) -join ',') -eq '40,20,25,100,30,70,50')
foreach ($bad in '', '4', '101', '12.5', 'twenty') { Check "MinPulseMs '$bad' refused" (Refused { $scale::ParseMin($bad) }) }

# Test (Pip, 12 Nov 2026): a width tested before Start, on the line named, at the procedure's gap.
$test = [CoenQcCalibrateValve.TestTrain]::Parse('25 10 DO2')
Check "Test '25 10 DO2' is 10 pulses of 25 ms on line 2" (($test.Item1 -eq 25) -and ($test.Item2 -eq 10) -and ($test.Item3 -eq 2))
foreach ($bad in '', '25 10', '0 10 DO1', '25 0 DO1', '25 101 DO1', '501 10 DO1', '25 10 DO4') { Check "Test '$bad' refused" (Refused { [CoenQcCalibrateValve.TestTrain]::Parse($bad) }) }
$testInput = [Tuple]::Create([string]'25 3 DO1', (New-Settings))
$trains = Items $train ((New-Object CoenQcCalibrateValve.TestTrain).Process((Obs $testInput.GetType() $testInput)))
Check "a test: its width on its line at the procedure's gap ($(Train $trains[0]))" ((Train $trains[0]) -eq '3x25@DO1/80')

# The weights file's row carries the gap its burst was fired at.
$inner = New-Object 'Tuple[Tuple[double,double],OpenRigs.Core.Calibration.DispenseSample]' ([Tuple]::Create([double]20.5, [double]20.1)), $all.Samples[1]
$weighed = [Tuple]::Create($inner, [int]2)
$row = (Items ([CoenQcCalibrateValve.ValveWeighing]) ((New-Object CoenQcCalibrateValve.ValveWeighingRow).Process((Obs $weighed.GetType() $weighed))))[0]
Check 'a weights row: its drips in its repeats, its valve and its gap' (($row.repeats -eq 252) -and ($row.channel -eq 2) -and ($row.pulseGapMs -eq 80) -and ($row.before -eq 20.1))

# Delivering water (deliver.bonsai) at the calibration file's gap, on a wired valve only.
function Deliver($channel, $gap) {
    $d = New-Object CoenQcCalibrateValve.DeliverTrain
    $d.Channel = $channel; $d.SizeMs = 30; $d.Pulses = 10; $d.PulseGapMs = $gap
    $go = [Tuple]::Create([int]0, $arena)
    (Items $train ($d.Process((Obs $go.GetType() $go))))[0]
}
Check "deliver: its pulses on its valve at its gap ($(Train (Deliver 2 80)))" ((Train (Deliver 2 80)) -eq '10x30@DO2/80')
Check 'deliver: a line not wired as a RewardValve refused' (Refused { Deliver 3 80 })
Check 'deliver: no gap given refused' (Refused { Deliver 1 0 })

# The spouts (Pip, 12 Nov 2026): both radial axes fully forward for the calibration, the rest kept.
$in = [OpenRigs.Devices.SpoutPositions]::FromArray([int[]]@(1000, 2000, 2100, 3000, 3100))
Check 'spouts forward: radials at 15000, the rest kept' ((@([CoenQcCalibrateValve.SpoutsForward]::Forward($in, 15000).ToArray()) -join ',') -eq '1000,15000,15000,3000,3100')
Check 'spouts forward 0: the target unchanged' ((@([CoenQcCalibrateValve.SpoutsForward]::Forward($in, 0).ToArray()) -join ',') -eq '1000,2000,2100,3000,3100')
Check 'the move time: 0.5 s plus 280 us a step on the farthest axis' ([CoenQcCalibrateValve.WaitForMove]::MoveTime($in).TotalSeconds -eq (0.5 + 0.00028 * 3100))

if ($failed) { "test-interleave: $failed failed."; exit 1 }
'test-interleave: all passed.'
