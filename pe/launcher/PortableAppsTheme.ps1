# Commander Rescue - switch the PortableApps.com menu theme.
# The Platform lists only its built-in themes and has one slot for a custom one
# (PortableApps.com\Data\Theme, used when its settings say Theme=Custom). This
# puts a theme from Data\ThemeLibrary (made with theme/make-pa-theme.py) into
# that slot, or goes back to the built-in theme, and restarts the menu.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent              # the stick: this script lives in <stick>\Apps
$pa = Join-Path $root 'PortableApps\PortableApps.com'
$ini = Join-Path $pa 'Data\PortableAppsMenu.ini'
$slot = Join-Path $pa 'Data\Theme'
$library = Join-Path $pa 'Data\ThemeLibrary'

if (-not (Test-Path (Join-Path $pa 'PortableAppsPlatform.exe'))) {
  Write-Host "`n  The PortableApps.com Platform isn't on this stick." ; Read-Host '  Enter to close' | Out-Null ; exit 1
}
$themes = @(if (Test-Path $library) { Get-ChildItem $library -Directory | Sort-Object Name })

Clear-Host
Write-Host "`n  PortableApps.com menu theme`n  ----------------------------"
Write-Host '    0)  PortableApps.com built-in (pick it in Options > Themes)'
for ($i = 0; $i -lt $themes.Count; $i++) { Write-Host ('    {0})  {1}' -f ($i + 1), $themes[$i].Name) }
if (-not $themes.Count) { Write-Host "`n  No custom themes in $library" }
$pick = Read-Host "`n  Choose (Enter to cancel)"
if ($pick -notmatch '^\d+$' -or [int]$pick -gt $themes.Count) { exit 0 }

# The Platform writes its settings back when it exits, so close it first
$running = Get-Process PortableAppsPlatform -ErrorAction SilentlyContinue
if ($running) {
  $running | ForEach-Object { $_.CloseMainWindow() | Out-Null }
  $running | Wait-Process -Timeout 10 -ErrorAction SilentlyContinue
  Get-Process PortableAppsPlatform -ErrorAction SilentlyContinue | Stop-Process -Force
}

if ([int]$pick -gt 0) {
  $theme = $themes[[int]$pick - 1]
  if (Test-Path $slot) { Remove-Item $slot -Recurse -Force }
  Copy-Item $theme.FullName $slot -Recurse
  $value = 'Custom'
} else {
  $theme = $null
  $value = 'Default'
}

# PortableAppsMenu.ini is UTF-16; set Theme= under [DisplayOptions]
if (Test-Path $ini) { $text = [IO.File]::ReadAllText($ini, [Text.Encoding]::Unicode) } else { $text = "[DisplayOptions]`r`n" }
if ($text -match '(?m)^Theme=') {                  # [^\r\n]* keeps the line's CRLF ending intact
  $text = $text -replace '(?m)^Theme=[^\r\n]*', "Theme=$value"
} elseif ($text -match '(?m)^\[DisplayOptions\]') {
  $text = $text -replace '(?m)^\[DisplayOptions\][^\r\n]*', "[DisplayOptions]`r`nTheme=$value"
} else {
  $text = "[DisplayOptions]`r`nTheme=$value`r`n" + $text
}
[IO.File]::WriteAllText($ini, $text, [Text.Encoding]::Unicode)

Write-Host ("`n  Theme set to {0}." -f $(if ($theme) { $theme.Name } else { 'the PortableApps.com built-in' }))
$start = Join-Path $root 'Start.exe'
if (Test-Path $start) { Start-Process -FilePath $start -WorkingDirectory $root }
Start-Sleep -Seconds 2
