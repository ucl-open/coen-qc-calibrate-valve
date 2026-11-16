# Checks src\Extensions without the rig: the lab rig model's valves (tests\rigs: a board-only and a
# dome rig.yml, and the refusals), the valves parsed from Channels, the procedure expanded over them
# (each sample once per valve, in turn; priming once per valve; one pulseGapMs), each burst's
# PulseTrain for FirePulses, and the spouts' targets.
# Run by tests\test_extensions.py (pytest), which builds the extension into -Bin with its packages.
# Exit 0 when every check passes.
param([Parameter(Mandatory = $true)][string]$Bin)
$ErrorActionPreference = 'Stop'
foreach ($dll in 'System.Reactive.Interfaces', 'System.Reactive.Core', 'System.Reactive.Linq', 'Bonsai.Core', 'YamlDotNet', 'Harp.Behavior', 'Harp.TimestampGeneratorGen3', 'Newtonsoft.Json', 'OpenRigs.Core', 'OpenRigs.Devices', 'Extensions') {
    $null = [Reflection.Assembly]::LoadFrom((Join-Path $Bin "$dll.dll"))
}
$rigs = Join-Path (Split-Path $PSScriptRoot) 'tests\rigs'
$failed = 0
function Check($name, $ok) {
    if ($ok) { "  ok    $name" } else { "  FAIL  $name"; $script:failed++ }
}
function Refused($block) { try { $null = & $block; $false } catch { $true } }
function Train($t) { "$($t.Pulses)x$($t.PulseWidthMs)@$($t.Line)/$($t.PulseGapMs)" }

# The rig model: lib-open-rigs' LabRig (OpenRigs.Devices ReadLabRig) reads a board-only and a dome
# rig.yml; the valves are the lines its wiring gives a RewardValve (OpenRigs.Devices WiredOutputs).
$rx = [System.Reactive.Linq.Observable]
function Obs($type, $value) { ($rx.GetMethods() | Where-Object { $_.Name -eq 'Return' -and $_.GetParameters().Count -eq 1 })[0].MakeGenericMethod($type).Invoke($null, @($value)) }
function Items($type, $source) { @(($rx.GetMethods() | Where-Object { $_.Name -eq 'ToEnumerable' })[0].MakeGenericMethod($type).Invoke($null, @($source))) }
$deserialize = [OpenRigs.Devices.Rigs.DeserializeFromYaml].GetMethod('Process', [Reflection.BindingFlags]'NonPublic, Static').MakeGenericMethod([OpenRigs.Devices.Rigs.LabRig])
function Rig($text) { (Items ([OpenRigs.Devices.Rigs.LabRig]) ($deserialize.Invoke($null, @((Obs ([string]) $text)))))[0] }
function RigFile($name) { Rig ([IO.File]::ReadAllText((Join-Path $rigs $name))) }
function Lines($rig) { [OpenRigs.Devices.WiredOutputs]::Find($rig, 'BehaviorBoard-Main', 'RewardValve') }
$boardRig = RigFile 'board.yml'
$board = Lines $boardRig
Check 'board only: two valves, not the photodiode line, no stage' (("$board" -eq 'DO1, DO2') -and $null -eq $boardRig.StepperDriver)
$dome = RigFile 'dome.yml'
Check 'dome: two valves, not the Zapit line' ("$(Lines $dome)" -eq 'DO1, DO2')
Check 'dome: the stage on stepperDriver a and b' ($dome.StepperDriver.Count -eq 2 -and $dome.StepperDriver['a'].PortName -eq 'COM5' -and $dome.StepperDriver['b'].PortName -eq 'COM6')
Check 'dome: its timestamp generator read (Harp.TimestampGeneratorGen3 0.1.1)' ("$($dome.TimestampGeneratorGen3['main'].TimerFrequency)" -eq 'Timer1000Hz')
Check 'a valve wiring does not give is refused' (Refused { [CoenQcCalibrateValve.Valves]::Check($board, [string[]]@('DO3')) })
Check 'a wired valve passes' (-not (Refused { [CoenQcCalibrateValve.Valves]::Check((Lines $dome), [string[]]@('DO2', 'DO1')) }))
$refusals = [ordered]@{
    'no RewardValve (a box today)' = "behaviorBoard:`n  main:`n    portName: COM3`n    pulseController: null`n"
    'no board main' = "behaviorBoard:`n  left:`n    portName: COM3`n"
    'a key the lab rig model lacks' = "behaviorBoard:`n  main:`n    portName: COM3`nrewardValves: { left: DO1 }`n"
}
foreach ($case in $refusals.Keys) { Check "refused: $case" (Refused { Lines (Rig $refusals[$case]) }) }
Check 'a RewardValve on a port line (DOPort0) allowed' (-not (Refused { Lines (Rig "behaviorBoard:`n  main:`n    portName: COM3`n    wiring:`n      DOPort0: { device: RewardValve, name: left }`n") }))

function New-Sample($width, $pulses, $gap) {
    $sample = New-Object OpenRigs.Core.Calibration.DispenseSample
    $sample.PulseWidthMs = $width; $sample.Pulses = $pulses; $sample.PulseGapMs = $gap
    $sample
}
function New-Settings($widths = @(@(40, 250), @(20, 500)), $gap = 80) {
    $settings = New-Object OpenRigs.Core.Calibration.DispenseCalibration
    $procedure = New-Object OpenRigs.Core.Calibration.DispenseProcedure
    $samples = New-Object 'System.Collections.Generic.List[OpenRigs.Core.Calibration.DispenseSample]'
    foreach ($s in $widths) { $samples.Add((New-Sample $s[0] $s[1] $gap)) }
    $procedure.Samples = $samples
    $procedure.PrimingPulses = 5
    $settings.Procedure = $procedure
    $settings
}

$parse = [CoenQcCalibrateValve.Valves]
Check 'empty Channels is the one Channel' ((@($parse::Parse('', '2')) -join ',') -eq 'DO2')
Check 'Channels as numbers' ((@($parse::Parse('1, 2', 'DO1')) -join ',') -eq 'DO1,DO2')
Check 'Channels as line names' ((@($parse::Parse('do2,DO1', 'DO1')) -join ',') -eq 'DO2,DO1')
foreach ($bad in 'DO4', '1, 1', 'left') { Check "Channels '$bad' refused" (Refused { $parse::Parse($bad, 'DO1') }) }

# One pulseGapMs (plan v11): the calibration file records it and a rig fires its rewards at it.
Check 'the gap is the samples'' one' ($parse::Gap((New-Settings).Procedure) -eq 80)
$mixed = New-Settings
$mixed.Procedure.Samples[1].PulseGapMs = 63
Check 'samples at different gaps refused' (Refused { $parse::Gap($mixed.Procedure) })
Check 'expanding samples at different gaps refused' (Refused { [CoenQcCalibrateValve.InterleaveValves]::Expand($mixed, [string[]]@('DO1'), $null) })

$all = [CoenQcCalibrateValve.InterleaveValves]::Expand((New-Settings), [string[]]@('DO1', 'DO2'), $null).Procedure
$order = @($all.Samples | ForEach-Object { "$($_.PulseWidthMs)@$($_.Channel)" }) -join ' '
Check "two valves: each burst on each in turn ($order)" ($order -eq '40@DO1 40@DO2 20@DO1 20@DO2')
Check 'two valves: pulses and gap kept' ((@($all.Samples | ForEach-Object { "$($_.Pulses)/$($_.PulseGapMs)" }) -join ',') -eq '250/80,250/80,500/80,500/80')
Check 'two valves: priming once per valve, counted together' ($all.PrimingPulses -eq 10)
Check 'two valves: the valves read back in firing order' ((@([CoenQcCalibrateValve.Valves]::Of($all)) -join ',') -eq 'DO1,DO2')

$one = [CoenQcCalibrateValve.InterleaveValves]::Expand((New-Settings), [string[]]@('DO2'), $null).Procedure
$order = @($one.Samples | ForEach-Object { "$($_.PulseWidthMs)@$($_.Channel)" }) -join ' '
Check "one valve: the procedure as written ($order)" ($order -eq '40@DO2 20@DO2')
Check 'one valve: priming as written' ($one.PrimingPulses -eq 5)

# Shuffled rounds (Pip, 11 Nov 2026): round k is each width's k-th sample, in a random order; rounds in turn.
$orders = @{}
foreach ($seed in 1..40) {
    $settings = New-Settings @(@(40, 250), @(20, 500), @(20, 500), @(70, 100), @(40, 250), @(70, 100), @(20, 500))
    $s = [CoenQcCalibrateValve.InterleaveValves]::Expand($settings, [string[]]@('DO1', 'DO2'), (New-Object Random $seed)).Procedure.Samples
    $widths = @($s | ForEach-Object { $_.PulseWidthMs })
    $ok = ((@($widths[0..5] | Sort-Object) -join ',') -eq '20,20,40,40,70,70') -and ((@($widths[6..11] | Sort-Object) -join ',') -eq '20,20,40,40,70,70') -and ((@($widths[12..13]) -join ',') -eq '20,20')
    $ok = $ok -and ((@($s | ForEach-Object { $_.Channel }) -join '') -eq ('DO1DO2' * 7))
    $ok = $ok -and (@(0..6 | Where-Object { $widths[2 * $_] -ne $widths[2 * $_ + 1] }).Count -eq 0)
    $ok = $ok -and (@($s | Where-Object { $_.Pulses -ne @{20 = 500; 40 = 250; 70 = 100}[$_.PulseWidthMs] }).Count -eq 0)
    if (-not $ok) { break }
    $orders[($widths -join ' ')] = 1
}
Check 'shuffled: every round has its widths, both valves in turn, pulses kept' $ok
Check "shuffled: the order changes from run to run ($($orders.Count) orders in 40)" ($orders.Count -gt 4)

# The bursts as FirePulses trains.
$train = [CoenQcCalibrateValve.PulseTrain]
$trains = Items $train ((New-Object CoenQcCalibrateValve.ValveTrains).Process((Obs ([OpenRigs.Core.Calibration.DispenseSample]) $all.Samples[3])))
Check "a sample's burst: its pulses at its width on its valve at its gap ($(Train $trains[0]))" ((Train $trains[0]) -eq '500x20@DO2/80')
$all.PrimingPulseWidthMs = 500
$trains = @([CoenQcCalibrateValve.ValveTrains]::Priming($all, 'DO1') | ForEach-Object { Train $_ })
Check "priming: an equal share on each valve in turn ($($trains -join ' '))" (($trains -join ' ') -eq '5x500@DO1/80 5x500@DO2/80')

# Drips (Pip, 8 Nov 2026): a Drip command's pulses at the sample's width on its valve; for the
# baseline, at the largest width on the line named.
$drip = [CoenQcCalibrateValve.DripTrains]
Check "Drip '5' is 5 pulses, no line" (($drip::Parse('5').Item1 -eq 5) -and ($null -eq $drip::Parse('5').Item2))
Check "Drip '1 DO2' is 1 pulse on DO2" (($drip::Parse('1 DO2').Item1 -eq 1) -and ($drip::Parse('1 DO2').Item2 -eq 'DO2'))
foreach ($bad in '', '0', 'five', '1 DO4', '101') { Check "Drip '$bad' refused" (Refused { $drip::Parse($bad) }) }
$trains = Items $train ((New-Object CoenQcCalibrateValve.DripTrains).Process((Obs ([string]) '3'), (Obs ([OpenRigs.Core.Calibration.DispenseSample]) $all.Samples[3]), (Obs $board.GetType() $board)))
Check "a sample's drip: its width on its valve ($(Train $trains[0]))" ((Train $trains[0]) -eq '3x20@DO2/80')
$trains = Items $train ((New-Object CoenQcCalibrateValve.DripTrains).Process((Obs ([string]) '1 DO2'), (Obs ([OpenRigs.Core.Calibration.DispenseProcedure]) $all), (Obs $board.GetType() $board)))
Check "the baseline's drip: the largest width on the line named ($(Train $trains[0]))" ((Train $trains[0]) -eq '1x40@DO2/80')
Check 'the baseline''s drip on a line not wired as a RewardValve refused' (Refused { Items $train ((New-Object CoenQcCalibrateValve.DripTrains).Process((Obs ([string]) '1 DO3'), (Obs ([OpenRigs.Core.Calibration.DispenseProcedure]) $all), (Obs $board.GetType() $board))) })
$strayed = New-Object CoenQcCalibrateValve.DripTrains
$strayed.Channel = 'DO3'
Check 'a sample''s drip on a line not wired as a RewardValve refused' (Refused { Items $train ($strayed.Process((Obs ([string]) '3'), (Obs ([OpenRigs.Core.Calibration.DispenseSample]) ([OpenRigs.Core.Calibration.DispenseSample](New-Sample 20 10 80))), (Obs $board.GetType() $board))) })

# A minimum per rig (Pip, 12 Nov 2026): the widths scaled so the smallest is MinPulseWidthMs, pulses as written.
$ladder = { New-Settings @(@(40, 300), @(20, 600), @(25, 480), @(100, 120), @(30, 400), @(70, 171), @(50, 240)) }
$scale = [CoenQcCalibrateValve.ScaleWidths]
$scaled = $scale::Scale((& $ladder), 30).Procedure.Samples
Check "min 30: widths 30 to 150 ($(@($scaled | ForEach-Object { $_.PulseWidthMs }) -join ','))" ((@($scaled | ForEach-Object { $_.PulseWidthMs }) -join ',') -eq '60,30,38,150,45,105,75')
Check 'min 30: pulses as written' ((@($scaled | ForEach-Object { $_.Pulses }) -join ',') -eq '300,600,480,120,400,171,240')
$twice = $scale::Scale($scale::Scale((& $ladder), 15), 15).Procedure.Samples
Check "min 15: scaling twice is scaling once ($(@($twice | ForEach-Object { $_.PulseWidthMs }) -join ','))" ((@($twice | ForEach-Object { $_.PulseWidthMs }) -join ',') -eq '30,15,19,75,23,53,38')
Check 'min 20: the procedure as written' ((@($scale::Scale((& $ladder), 20).Procedure.Samples | ForEach-Object { $_.PulseWidthMs }) -join ',') -eq '40,20,25,100,30,70,50')
foreach ($bad in '', '4', '101', '12.5', 'twenty') { Check "MinPulseWidthMs '$bad' refused" (Refused { $scale::ParseMin($bad) }) }

# Test (Pip, 12 Nov 2026): a width tested before Start, on the line named, at the procedure's gap.
$test = [CoenQcCalibrateValve.TestTrain]::Parse('25 10 DO2')
Check "Test '25 10 DO2' is 10 pulses of 25 ms on DO2" (($test.Item1 -eq 25) -and ($test.Item2 -eq 10) -and ($test.Item3 -eq 'DO2'))
foreach ($bad in '', '25 10', '0 10 DO1', '25 0 DO1', '25 101 DO1', '501 10 DO1', '25 10 DO4') { Check "Test '$bad' refused" (Refused { [CoenQcCalibrateValve.TestTrain]::Parse($bad) }) }
function TestOn($text) {
    $settings = [Tuple]::Create([string]$text, (New-Settings))
    $testInput = [Tuple]::Create($settings, $board)
    Items $train ((New-Object CoenQcCalibrateValve.TestTrain).Process((Obs $testInput.GetType() $testInput)))
}
$trains = TestOn '25 3 DO1'
Check "a test: its width on its line at the procedure's gap ($(Train $trains[0]))" ((Train $trains[0]) -eq '3x25@DO1/80')
Check 'a test on a line not wired as a RewardValve refused' (Refused { TestOn '25 3 DO3' })

# The weights file's row carries the gap its burst was fired at.
$inner = New-Object 'Tuple[Tuple[double,double],OpenRigs.Core.Calibration.DispenseSample]' ([Tuple]::Create([double]20.5, [double]20.1)), $all.Samples[1]
$weighed = [Tuple]::Create($inner, [int]2)
$row = (Items ([CoenQcCalibrateValve.ValveWeighing]) ((New-Object CoenQcCalibrateValve.ValveWeighingRow).Process((Obs $weighed.GetType() $weighed))))[0]
Check 'a weights row: its drips in its pulses, its valve and its gap' (($row.pulses -eq 252) -and ($row.channel -eq 2) -and ($row.pulseGapMs -eq 80) -and ($row.beforeG -eq 20.1))

# Delivering water (deliver.bonsai) at the calibration file's gap, on a wired valve only.
function Deliver($channel, $gap) {
    $d = New-Object CoenQcCalibrateValve.DeliverTrain
    $d.Channel = $channel; $d.PulseWidthMs = 30; $d.Pulses = 10; $d.PulseGapMs = $gap
    $go = [Tuple]::Create([int]0, $board)
    (Items $train ($d.Process((Obs $go.GetType() $go))))[0]
}
Check "deliver: its pulses on its valve at its gap ($(Train (Deliver 'DO2' 80)))" ((Train (Deliver 2 80)) -eq '10x30@DO2/80')
Check 'deliver: a line not wired as a RewardValve refused' (Refused { Deliver 'DO3' 80 })
Check 'deliver: no gap given refused' (Refused { Deliver 'DO1' 0 })

# The spouts (Pip, 12 Nov 2026): both radial axes fully forward for the calibration, the rest kept.
$in = [OpenRigs.Devices.SpoutPositions]::FromArray([int[]]@(1000, 2000, 2100, 3000, 3100))
Check 'spouts forward: radials at 15000, the rest kept' ((@([CoenQcCalibrateValve.SpoutsForward]::Forward($in, 15000).ToArray()) -join ',') -eq '1000,15000,15000,3000,3100')
Check 'spouts forward 0: the target unchanged' ((@([CoenQcCalibrateValve.SpoutsForward]::Forward($in, 0).ToArray()) -join ',') -eq '1000,2000,2100,3000,3100')
Check 'the move time: 0.5 s plus 280 us a step on the farthest axis' ([CoenQcCalibrateValve.WaitForMove]::MoveTime($in).TotalSeconds -eq (0.5 + 0.00028 * 3100))

if ($failed) { "test-interleave: $failed failed."; exit 1 }
'test-interleave: all passed.'
