r"""src\Extensions checked without the rig (tests\interleave.ps1): built as Bonsai builds it (C# 5) with its packages, then
loaded by Windows PowerShell, as Bonsai loads it."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.skipif(shutil.which("dotnet") is None or shutil.which("powershell") is None, reason="needs dotnet and Windows PowerShell")
def test_the_valves_trains_and_spouts(tmp_path):
    build = subprocess.run(["dotnet", "build", str(ROOT / "src" / "Extensions.csproj"), "-p:LangVersion=5", "-o", str(tmp_path),
                            "--source", "https://api.nuget.org/v3/index.json", "--source", str(ROOT / "local_packages")],
                           capture_output=True, text=True)
    assert build.returncode == 0, build.stdout[-3000:]
    run = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tests" / "interleave.ps1"), "-Bin", str(tmp_path)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-2000:]
