<#
  Builds a stand-in Helix Boot stick and Start menu from fixture.json, for the Lazarus
  launcher's CI screenshots: Apps\apps.txt, PortableApps with appinfo.ini (UTF-8, UTF-16 and
  junk-prefixed, like real ones) and generated icons, and a Start menu of .lnk shortcuts.
  Programs are copies of small Windows programs, so every tool has a real icon to extract.
#>
param(
  [Parameter(Mandatory)] [string]$Stick,
  [Parameter(Mandatory)] [string]$Menu
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$fx = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'fixture.json') | ConvertFrom-Json
$pool = @('notepad.exe', 'regedit.exe', 'taskmgr.exe', 'cmd.exe', 'mmc.exe', 'charmap.exe', 'write.exe',
          'mspaint.exe', 'dxdiag.exe', 'perfmon.exe', 'resmon.exe', 'eventvwr.exe', 'msinfo32.exe', 'calc.exe') |
  ForEach-Object { Join-Path $env:SystemRoot "System32\$_" } | Where-Object { Test-Path $_ }
if (-not $pool) { $pool = @(Join-Path $env:SystemRoot 'notepad.exe') }
$n = 0
function Copy-Program([string]$dest) {
  New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
  Copy-Item $pool[$script:n % $pool.Count] $dest -Force
  $script:n++
}

# A 128px app icon: a rounded tile with the app's initials
$palette = @('#1F8A7E', '#2B6CB0', '#8E44AD', '#C0392B', '#D35400', '#16A085', '#2C3E50', '#B7950B')
function New-Icon([string]$name, [string]$path) {
  $bmp = New-Object Drawing.Bitmap 128, 128
  $g = [Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode = 'AntiAlias'; $g.TextRenderingHint = 'AntiAliasGridFit'
  $col = [Drawing.ColorTranslator]::FromHtml($palette[[Math]::Abs($name.GetHashCode()) % $palette.Count])
  $gp = New-Object Drawing.Drawing2D.GraphicsPath
  $r = 26
  $gp.AddArc(8, 8, $r, $r, 180, 90); $gp.AddArc(120 - $r, 8, $r, $r, 270, 90)
  $gp.AddArc(120 - $r, 120 - $r, $r, $r, 0, 90); $gp.AddArc(8, 120 - $r, $r, $r, 90, 90); $gp.CloseFigure()
  $g.FillPath((New-Object Drawing.SolidBrush $col), $gp)
  $letters = (($name -split '[^A-Za-z0-9]+' | Where-Object { $_ } | Select-Object -First 2 | ForEach-Object { $_[0] }) -join '').ToUpper()
  $font = New-Object Drawing.Font 'Segoe UI', 40, ([Drawing.FontStyle]::Bold), ([Drawing.GraphicsUnit]::Pixel)
  $fmt = New-Object Drawing.StringFormat; $fmt.Alignment = 'Center'; $fmt.LineAlignment = 'Center'
  $g.DrawString($letters, $font, [Drawing.Brushes]::White, (New-Object Drawing.RectangleF 0, 0, 128, 128), $fmt)
  $g.Dispose()
  $bmp.Save($path, [Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
}

# Helix Apps
$apps = Join-Path $Stick 'Apps'
New-Item -ItemType Directory -Force $apps | Out-Null
$lines = foreach ($a in $fx.helix) {
  $path = Join-Path $apps $a.path
  if ($path -like '*.ps1') { New-Item -ItemType Directory -Force (Split-Path $path) | Out-Null; Set-Content $path '# fake' }
  else { Copy-Program $path }
  "$($a.title)|$($a.path)|$($a.description)"
}
[IO.File]::WriteAllText((Join-Path $apps 'apps.txt'), (($lines -join "`r`n") + "`r`n"), (New-Object Text.UTF8Encoding $false))

# PortableApps
foreach ($a in $fx.portableapps) {
  $dir = Join-Path $Stick "PortableApps\$($a.folder)"
  $info = Join-Path $dir 'App\AppInfo'
  New-Item -ItemType Directory -Force $info | Out-Null
  $ini = "[Format]`r`nType=PortableApps.comFormat`r`n[Details]`r`nName=$($a.name)`r`nCategory=$($a.category)`r`n" +
         "Description=$($a.description)`r`n[Version]`r`nDisplayVersion=$($a.version)`r`n[Control]`r`nIcons=1`r`nStart=$($a.start)`r`n"
  if ($a.PSObject.Properties['junk']) { $ini = $a.junk + $ini }
  $kind = if ($a.PSObject.Properties['encoding']) { $a.encoding } else { 'utf-8' }
  $enc = switch ($kind) {
    'utf-16' { New-Object Text.UnicodeEncoding $false, $true }
    'ansi'   { [Text.Encoding]::GetEncoding(1252) }
    default  { New-Object Text.UTF8Encoding $false }
  }
  [IO.File]::WriteAllText((Join-Path $info 'appinfo.ini'), $ini, $enc)
  if ($a.start) { Copy-Program (Join-Path $dir $a.start) }
  New-Icon $a.name (Join-Path $info 'appicon_128.png')
}
# The Platform's own folder and a folder added by hand
New-Item -ItemType Directory -Force (Join-Path $Stick 'PortableApps\CommonFiles') | Out-Null
Copy-Program (Join-Path $Stick 'PortableApps\Brave\brave.exe')
Copy-Program (Join-Path $Stick 'Start.exe')

# Start menu (what PhoenixPE makes as Lazarus PE starts)
$shell = New-Object -ComObject WScript.Shell
foreach ($e in $fx.startmenu) {
  $folder = if ($e[0]) { Join-Path $Menu $e[0] } else { $Menu }
  New-Item -ItemType Directory -Force $folder | Out-Null
  $target = Join-Path $env:TEMP ("fake-pe-" + ($e[1] -replace '[^A-Za-z0-9]', '') + '.exe')
  Copy-Program $target
  $s = $shell.CreateShortcut((Join-Path $folder "$($e[1]).lnk"))
  $s.TargetPath = $target
  $s.Description = "$($e[1]) (in Lazarus PE)"
  $s.Save()
}
Write-Host "fake stick: $Stick  ($(@($fx.helix).Count) Helix Apps, $(@($fx.portableapps).Count) PortableApps, $(@($fx.startmenu).Count) shortcuts)"
