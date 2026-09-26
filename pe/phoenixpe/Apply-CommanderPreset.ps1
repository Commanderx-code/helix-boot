<#
.SYNOPSIS
  Set up a PhoenixPE folder for the Commander PE build.

.DESCRIPTION
  1. Copies the Commander Rescue add-on (CommanderRescue.script + the app
     launcher) into PhoenixPE's Projects\MyApps\Commander Rescue\.
  2. Ticks / unticks the scripts listed in preset.txt, exactly as if you had
     clicked their checkboxes in PEBakery.

  Only the "Selected=" line of each listed script changes. Run it again after
  updating PhoenixPE, or unpack a fresh PhoenixPE to undo it.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\Apply-CommanderPreset.ps1 -PhoenixPE C:\PhoenixPE

.EXAMPLE
  .\Apply-CommanderPreset.ps1 C:\PhoenixPE -WhatIf     # show what would change
#>
[CmdletBinding(SupportsShouldProcess)]
param(
  [Parameter(Mandatory, Position = 0)]
  [string]$PhoenixPE
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3

$here = $PSScriptRoot
$projects = Join-Path $PhoenixPE 'Projects'
if (-not (Test-Path (Join-Path (Join-Path $projects 'PhoenixPE') 'script.project'))) {
  throw "$PhoenixPE doesn't look like a PhoenixPE folder (no Projects\PhoenixPE\script.project)."
}

# ── 1. Add-on ───────────────────────────────────────────────────────────────
$launcher = Join-Path (Join-Path (Split-Path $here) 'launcher') 'CommanderApps.cmd'
$addonDir = Join-Path (Join-Path $projects 'MyApps') 'Commander Rescue'
if ($PSCmdlet.ShouldProcess($addonDir, 'Install Commander Rescue add-on')) {
  New-Item -ItemType Directory -Force $addonDir | Out-Null
  Copy-Item (Join-Path $here 'CommanderRescue.script') $addonDir -Force
  Copy-Item $launcher $addonDir -Force
  Write-Host "+ add-on installed in $addonDir"
}

# ── 2. Preset ───────────────────────────────────────────────────────────────
# Rewrite "Selected=" inside [Main], keeping the file's encoding, BOM and line endings.
function Set-ScriptSelected([string]$Path, [bool]$On) {
  $bytes = [IO.File]::ReadAllBytes($Path)
  $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
  $enc = New-Object Text.UTF8Encoding($bom)
  $text = $enc.GetString($bytes)
  if ($bom) { $text = $text.Substring(1) }
  $nl = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }

  $lines = $text -split "\r?\n"
  $inMain = $false; $hit = $false; $want = if ($On) { 'True' } else { 'False' }
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s*\[(.+)\]\s*$') { $inMain = $Matches[1] -eq 'Main'; continue }
    if ($inMain -and $lines[$i] -match '^\s*Selected\s*=\s*(.*)$') {
      $hit = $true
      $cur = $Matches[1].Trim()
      if ($cur -eq 'None') { return 'fixed' }   # not a selectable script
      if ($cur -eq $want) { return 'same' }
      $lines[$i] = "Selected=$want"
      break
    }
  }
  if (-not $hit) { return 'noline' }
  if ($PSCmdlet.ShouldProcess($Path, "Selected=$want")) {
    [IO.File]::WriteAllBytes($Path, [byte[]]($enc.GetPreamble() + $enc.GetBytes($lines -join $nl)))
  }
  return 'changed'
}

$problems = 0
foreach ($raw in Get-Content (Join-Path $here 'preset.txt')) {
  $line = ($raw -replace '#.*$', '').Trim()
  if (-not $line) { continue }
  if ($line -notmatch '^(on|off)\s+(.+)$') { Write-Warning "preset.txt: can't read '$raw'"; $problems++; continue }
  $on = $Matches[1] -eq 'on'
  $rel = $Matches[2].Trim()
  $path = Join-Path $projects ($rel -replace '\\', [IO.Path]::DirectorySeparatorChar)
  $mark = if ($on) { 'on ' } else { 'off' }
  if (-not (Test-Path -LiteralPath $path)) {
    if ($WhatIfPreference -and $path.StartsWith($addonDir)) { Write-Host "  $mark  $rel (after the add-on is installed)"; continue }
    Write-Warning "$rel not found in this PhoenixPE release. Pick its replacement by hand in PEBakery."
    $problems++
    continue
  }
  switch (Set-ScriptSelected $path $on) {
    'changed' { Write-Host "  $mark  $rel" }
    'same'    { Write-Host "  $mark  $rel (already)" }
    'fixed'   { Write-Warning "$rel can't be ticked or unticked; skipped."; $problems++ }
    'noline'  { Write-Warning "$rel has no Selected= line; skipped."; $problems++ }
  }
}

if ($problems) { Write-Warning "$problems preset line(s) need a look (above)." }
Write-Host "`nDone. Open PEBakeryLauncher.exe, check Source (your Windows ISO) and press Build."
