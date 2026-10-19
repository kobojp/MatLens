param([switch]$NoLaunch)
$ErrorActionPreference = "Stop"
$source = Join-Path $PSScriptRoot 'MatLens'
$programsRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'MatLens'))
$target = [IO.Path]::GetFullPath((Join-Path $programsRoot 'app'))
if (-not (Test-Path -LiteralPath (Join-Path $source 'MatLens.exe'))) {
    throw 'Extract the complete ZIP before installing MatLens.'
}
if (-not $target.StartsWith($programsRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Invalid application installation path.'
}
if (Get-Process MatLens -ErrorAction SilentlyContinue) {
    throw 'Close MatLens before installing or updating.'
}
New-Item -ItemType Directory -Path $target -Force | Out-Null
foreach ($name in @('MatLens.exe', 'MatLensUpdater.exe', '_internal')) {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination $target -Recurse -Force
}
$shell = New-Object -ComObject WScript.Shell
foreach ($shortcutDirectory in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    $shortcut = $shell.CreateShortcut((Join-Path $shortcutDirectory 'MatLens.lnk'))
    $shortcut.TargetPath = Join-Path $target 'MatLens.exe'
    $shortcut.WorkingDirectory = $target
    $shortcut.Description = 'MatLens photo management'
    $shortcut.Save()
}
Write-Host "Installed MatLens: $target"
Write-Host 'Your case database and photos are stored separately and preserved.'
if (-not $NoLaunch) { Start-Process -FilePath (Join-Path $target 'MatLens.exe') }
