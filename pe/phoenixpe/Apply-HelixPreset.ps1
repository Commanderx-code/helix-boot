<#
.SYNOPSIS
  Set up a PhoenixPE folder for the Lazarus PE build.

.DESCRIPTION
  1. Copies the Helix Boot add-on (HelixBoot.script + the app launcher) into
     PhoenixPE's Projects\MyApps\Helix Boot\, replacing the Commander Rescue one.
  2. Ticks / unticks the scripts listed in preset.txt and sets the options it
     lists (wallpaper, theme), exactly as if you had clicked them in PEBakery.

  Only the "Selected=" line and the listed options of each script change; all
  your other choices stay. Run it again after updating PhoenixPE, or unpack a
  fresh PhoenixPE to undo it.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\Apply-HelixPreset.ps1 -PhoenixPE C:\PhoenixPE

.EXAMPLE
  .\Apply-HelixPreset.ps1 C:\PhoenixPE -WhatIf     # show what would change
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
$launcher = Join-Path (Join-Path (Split-Path $here) 'launcher') 'HelixApps.cmd'
$addonDir = Join-Path (Join-Path $projects 'MyApps') 'Helix Boot'
# Its name before the rename to Helix Boot: remove it, or the PE would get both launchers
$oldAddon = Join-Path (Join-Path $projects 'MyApps') 'Commander Rescue'
if ((Test-Path $oldAddon) -and $PSCmdlet.ShouldProcess($oldAddon, 'Remove the old Commander Rescue add-on')) {
  Remove-Item $oldAddon -Recurse -Force
  Write-Host "- old Commander Rescue add-on removed"
}
if ($PSCmdlet.ShouldProcess($addonDir, 'Install Helix Boot add-on')) {
  New-Item -ItemType Directory -Force $addonDir | Out-Null
  Copy-Item (Join-Path $here 'HelixBoot.script') $addonDir -Force
  Copy-Item $launcher $addonDir -Force
  Copy-Item (Join-Path (Split-Path $launcher) 'StartPortableApps.cmd') $addonDir -Force
  Copy-Item (Join-Path $here 'wallpaper.jpg') $addonDir -Force
  Copy-Item (Join-Path $here 'profile.png') $addonDir -Force
  Copy-Item (Join-Path $here 'AccountPictures') $addonDir -Recurse -Force
  Write-Host "+ add-on installed in $addonDir"
}

# ── 2. Preset ───────────────────────────────────────────────────────────────
# Scripts are read and written keeping their encoding, BOM and line endings.
function Read-Script([string]$Path) {
  $bytes = [IO.File]::ReadAllBytes($Path)
  $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
  $enc = New-Object Text.UTF8Encoding($bom)
  $text = $enc.GetString($bytes)
  if ($bom) { $text = $text.Substring(1) }
  $nl = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
  @{ Enc = $enc; Nl = $nl; Lines = $text -split "\r?\n" }
}
function Write-Script([string]$Path, $s) {
  [IO.File]::WriteAllBytes($Path, [byte[]]($s.Enc.GetPreamble() + $s.Enc.GetBytes($s.Lines -join $s.Nl)))
}

# Rewrite "Selected=" inside [Main].
function Set-ScriptSelected([string]$Path, [bool]$On) {
  $s = Read-Script $Path
  $lines = $s.Lines
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
  if ($PSCmdlet.ShouldProcess($Path, "Selected=$want")) { Write-Script $Path $s }
  return 'changed'
}

# PEBakery interface lines: Name=field0,visible,type,left,top,width,height,... with
# "quoted" fields where needed. Where the value sits depends on the control type.
function Split-Fields([string]$s) {
  [regex]::Matches($s, '(?<=^|,)("[^"]*"|[^,]*)') | ForEach-Object { $_.Value }
}
function Unquote([string]$s) { if ($s -match '^"(.*)"$') { $Matches[1] } else { $s } }
function Quote([string]$s) { if ($s -match '[\s,]') { '"' + $s + '"' } else { $s } }
$valueAt = @{ '0' = 7; '2' = 7; '3' = 7; '4' = 0; '11' = 7; '13' = 0 }   # text, number, check, dropdown, radio, file

# Set one option, as if picked in PEBakery. Returns what happened, or a problem to report.
function Set-ScriptOption([string]$Path, [string]$Name, [string]$Value) {
  $s = Read-Script $Path
  $lines = $s.Lines
  $iface = 'Interface'   # [Main] can name another interface section
  $inMain = $false
  foreach ($l in $lines) {
    if ($l -match '^\s*\[(.+)\]\s*$') { $inMain = $Matches[1] -eq 'Main'; continue }
    if ($inMain -and $l -match '^\s*Interface\s*=\s*(.+?)\s*$') { $iface = $Matches[1] }
  }
  $section = ''; $rows = @{}
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s*\[(.+)\]\s*$') { $section = $Matches[1]; continue }
    if ($section -eq $iface -and $lines[$i] -match '^([^=]+)=(.*)$') { $rows[$Matches[1].Trim()] = $i }
  }
  if (-not $rows.ContainsKey($Name)) { return "has no option $Name" }

  $fields = @(Split-Fields ($lines[$rows[$Name]] -replace '^[^=]+=', ''))
  $type = $fields[2]
  if (-not $valueAt.ContainsKey($type)) { return "can't set $Name (control type $type)" }
  $at = $valueAt[$type]
  if ($type -eq '4') {   # dropdown: only its own choices, before any _Section_ to run
    $choices = @($fields[7..($fields.Count - 1)] | ForEach-Object { Unquote $_ } |
      Where-Object { $_ -notmatch '^_.*_$' -and $_ -notin 'True', 'False' -and $_ -notmatch '^__' })
    if ($Value -notin $choices) { return "has no choice '$Value' for $Name" }
  }
  if ($type -in '3', '11' -and $Value -notin 'True', 'False') { return "$Name takes True or False" }
  if ((Unquote $fields[$at]) -eq $Value) { return 'same' }

  $fields[$at] = Quote $Value
  $lines[$rows[$Name]] = "$Name=" + ($fields -join ',')
  if ($type -eq '11' -and $Value -eq 'True') {   # radio buttons: picking one clears the others
    foreach ($other in $rows.Keys) {
      $f = @(Split-Fields ($lines[$rows[$other]] -replace '^[^=]+=', ''))
      if ($other -ne $Name -and $f.Count -gt 7 -and $f[2] -eq '11' -and $f[7] -eq 'True') {
        $f[7] = 'False'
        $lines[$rows[$other]] = "$other=" + ($f -join ',')
      }
    }
  }
  if ($PSCmdlet.ShouldProcess($Path, "$Name=$Value")) { Write-Script $Path $s }
  return 'changed'
}

$problems = 0
foreach ($raw in Get-Content (Join-Path $here 'preset.txt')) {
  $line = ($raw -replace '#.*$', '').Trim()
  if (-not $line) { continue }
  if ($line -match '^set\s+([^|]+)\|([^|]+)\|(.*)$') {
    $rel = $Matches[1].Trim(); $name = $Matches[2].Trim()
    $value = $Matches[3].Trim().Replace('{addon}', $addonDir)
    $path = Join-Path $projects ($rel -replace '\\', [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $path)) {
      Write-Warning "$rel not found in this PhoenixPE release. Set $name by hand in PEBakery."
      $problems++
      continue
    }
    switch (Set-ScriptOption $path $name $value) {
      'changed' { Write-Host "  set  $rel : $name = $value" }
      'same'    { Write-Host "  set  $rel : $name = $value (already)" }
      default   { Write-Warning "$rel $_. Set it by hand in PEBakery."; $problems++ }
    }
    continue
  }
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
