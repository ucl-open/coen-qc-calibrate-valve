# Installs Bonsai and the workflow's packages into .bonsai\. This project has no rig schema of its
# own: the workflow reads the rig's existing <ConfigRoot>\<MACHINE-NAME>\rig.yml (the one every rig shares)
# and writes its artefacts into calibration\ beside it.
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
& (Join-Path $repo '.bonsai\Setup.ps1')
exit $LASTEXITCODE
