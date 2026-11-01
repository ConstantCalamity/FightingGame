# Build the Windows dev player (optionally rebuilding the scene first) and run a CPU-vs-CPU autotest.
# Usage: powershell -File Tools/run_autotest.ps1 [-Scene] [-P1 Corvin] [-P2 Isolde] [-Map 0]
param([switch]$Scene, [string]$P1 = "Corvin", [string]$P2 = "Isolde", [int]$Map = 0)
$root = Split-Path $PSScriptRoot -Parent
$unity = "C:\Program Files\Unity\Hub\Editor\6000.3.27f2\Editor\Unity.exe"

function Invoke-Unity($method, $log) {
    $p = Start-Process $unity -ArgumentList @('-batchmode', '-quit', '-projectPath', "`"$root`"", '-executeMethod', $method, '-logFile', "`"$log`"") -Wait -PassThru
    $errors = Select-String -Path $log -Pattern "error CS" | ForEach-Object Line
    if ($p.ExitCode -ne 0 -or $errors) { "FAILED $method (exit $($p.ExitCode))"; $errors | Select-Object -First 15; exit 1 }
}

if ($Scene) { Invoke-Unity 'FightingGame.EditorTools.SceneBuilder.Build' "$root\Logs\build-scene.log"; "scene rebuilt" }
Invoke-Unity 'FightingGame.EditorTools.DevBuild.BuildWindows' "$root\Logs\build-player.log"
"player built"

Remove-Item "$root\Logs\autotest_*.png" -ErrorAction SilentlyContinue
$log = "$root\Logs\autotest-player.log"
$g = Start-Process "$root\Builds\Windows\FightingGame.exe" -ArgumentList @('-autotest', '-p1', $P1, '-p2', $P2, '-map', $Map, '-shot', "$root\Logs\autotest.png",
    '-screen-fullscreen', '0', '-screen-width', '1600', '-screen-height', '900', '-logFile', $log) -PassThru
if (-not $g.WaitForExit(90000)) { $g.Kill(); "player killed after timeout" }
"exceptions: " + (Select-String -Path $log -Pattern "Exception" | Measure-Object).Count
Select-String -Path $log -Pattern "Exception" -Context 0, 2 | Select-Object -First 3 | ForEach-Object { $_.Line; $_.Context.PostContext }
Select-String -Path $log -Pattern "\[view\]" | ForEach-Object Line
Select-String -Path $log -Pattern "\[autotest\]" | Select-Object -Last 2 | ForEach-Object Line
