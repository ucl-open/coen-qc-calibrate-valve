# Checks src\Extensions\ValveInterleave.cs without the rig: the valves parsed from Channels, and
# the procedure expanded over them (each sample once per valve, in turn; priming once per valve).
# Run after lib-open-rigs' check-workflow-builds.ps1 has compiled the extension, which leaves
# Extensions.dll and OpenRigs.Core.dll in %TEMP%\check-workflow-builds-coen-qc-calibrate-valve.
# Exit 0 when every check passes.
$ErrorActionPreference = 'Stop'
$bin = Join-Path ([IO.Path]::GetTempPath()) 'check-workflow-builds-coen-qc-calibrate-valve'
foreach ($dll in 'System.Reactive.Interfaces', 'System.Reactive.Core', 'System.Reactive.Linq', 'Bonsai.Core', 'OpenRigs.Core', 'Extensions') {
    $path = Join-Path $bin "$dll.dll"
    if (Test-Path $path) { $null = [Reflection.Assembly]::LoadFrom($path) }
}
$failed = 0
function Check($name, $ok) {
    if ($ok) { "  ok    $name" } else { "  FAIL  $name"; $script:failed++ }
}

function New-Settings {
    $settings = New-Object OpenRigs.Core.Calibration.DispenseCalibration
    $procedure = New-Object OpenRigs.Core.Calibration.DispenseProcedure
    $samples = New-Object 'System.Collections.Generic.List[OpenRigs.Core.Calibration.DispenseSample]'
    foreach ($s in @(@(40, 250), @(20, 500))) {
        $sample = New-Object OpenRigs.Core.Calibration.DispenseSample
        $sample.Size = $s[0]; $sample.Repeats = $s[1]; $sample.InterPulseIntervalMs = 63
        $samples.Add($sample)
    }
    $procedure.Samples = $samples
    $procedure.PrimingPulses = 5
    $settings.Procedure = $procedure
    $settings
}

$parse = [CoenQcCalibrateValve.Valves]
Check 'empty Channels is the one Channel' ((@($parse::Parse('', 2)) -join ',') -eq '2')
Check 'Channels as numbers' ((@($parse::Parse('1, 2', 1)) -join ',') -eq '1,2')
Check 'Channels as line names' ((@($parse::Parse('DO2,DO1', 1)) -join ',') -eq '2,1')
foreach ($bad in 'DO4', '1, 1', 'left') {
    $threw = $false
    try { $null = $parse::Parse($bad, 1) } catch { $threw = $true }
    Check "Channels '$bad' refused" $threw
}

$all = [CoenQcCalibrateValve.InterleaveValves]::Expand((New-Settings), [int[]]@(1, 2)).Procedure
$order = @($all.Samples | ForEach-Object { "$($_.Size)@$($_.Channel)" }) -join ' '
Check "two valves: each burst on each in turn ($order)" ($order -eq '40@1 40@2 20@1 20@2')
Check 'two valves: repeats kept' ((@($all.Samples | ForEach-Object { $_.Repeats }) -join ',') -eq '250,250,500,500')
Check 'two valves: priming once per valve, counted together' ($all.PrimingPulses -eq 10)
Check 'two valves: the valves read back in firing order' ((@([CoenQcCalibrateValve.Valves]::Of($all)) -join ',') -eq '1,2')

$one = [CoenQcCalibrateValve.InterleaveValves]::Expand((New-Settings), [int[]]@(2)).Procedure
$order = @($one.Samples | ForEach-Object { "$($_.Size)@$($_.Channel)" }) -join ' '
Check "one valve: the procedure as written ($order)" ($order -eq '40@2 20@2')
Check 'one valve: priming as written' ($one.PrimingPulses -eq 5)

# Drips (Pip, 8 Nov 2026): a Drip command's pulses at the sample's width on its valve; for the
# baseline, at the largest width on the line named.
$rx = [System.Reactive.Linq.Observable]
function Obs($type, $value) { ($rx.GetMethods() | Where-Object { $_.Name -eq 'Return' -and $_.GetParameters().Count -eq 1 })[0].MakeGenericMethod($type).Invoke($null, @($value)) }
function Items($type, $source) { @(($rx.GetMethods() | Where-Object { $_.Name -eq 'ToEnumerable' })[0].MakeGenericMethod($type).Invoke($null, @($source))) }
$drip = [CoenQcCalibrateValve.DripBurst]
Check "Drip '5' is 5 pulses, no line" (($drip::Parse('5').Item1 -eq 5) -and ($drip::Parse('5').Item2 -eq 0))
Check "Drip '1 DO2' is 1 pulse on line 2" (($drip::Parse('1 DO2').Item1 -eq 1) -and ($drip::Parse('1 DO2').Item2 -eq 2))
foreach ($bad in '', '0', 'five', '1 DO4', '101') {
    $threw = $false
    try { $null = $drip::Parse($bad) } catch { $threw = $true }
    Check "Drip '$bad' refused" $threw
}
$sample = $all.Samples[3]  # 20 ms on valve 2
$pulses = Items ([Tuple[int, int]]) ((New-Object CoenQcCalibrateValve.DripBurst).Process((Obs ([string]) '3'), (Obs ([OpenRigs.Core.Calibration.DispenseSample]) $sample)))
Check "a sample's drip: its width on its valve ($($pulses -join ' '))" ((@($pulses | ForEach-Object { "$($_.Item2)@$($_.Item1)" }) -join ' ') -eq '20@2 20@2 20@2')
$pulses = Items ([Tuple[int, int]]) ((New-Object CoenQcCalibrateValve.DripBurst).Process((Obs ([string]) '1 DO2'), (Obs ([OpenRigs.Core.Calibration.DispenseProcedure]) $all)))
Check "the baseline's drip: the largest width on the line named ($($pulses -join ' '))" ((@($pulses | ForEach-Object { "$($_.Item2)@$($_.Item1)" }) -join ' ') -eq '40@2')

if ($failed) { "test-interleave: $failed failed."; exit 1 }
'test-interleave: all passed.'
