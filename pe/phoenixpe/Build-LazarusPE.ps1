<#
.SYNOPSIS
  Build Lazarus PE in one go: fetch PhoenixPE, set it up, open the builder.

.DESCRIPTION
  1. Downloads the latest PhoenixPE release, checks it against the checksum GitHub
     records for it, and unpacks it (skipped when the folder is a PhoenixPE already).
  2. Applies the Helix preset (Apply-HelixPreset.ps1): the add-on, the ticked scripts,
     the Lazarus PE look.
  3. Fills in Source Config from your Windows ISO, as its "Rescan Source" button would:
     the source, the Windows Setup base image, the edition, not run from RAM.
  4. Opens PEBakery. You press Build: PEBakery has no way to start one from outside.
  5. Waits for the ISO and copies it out as LazarusPE.iso.

  Windows Security quarantines some of PhoenixPE's tools, which breaks the build:
  do step 3 of pe\README.md ("Exclude the build from Defender") before the first run.

.PARAMETER Windows
  The Windows ISO to build from (Windows 11 22H2 or 23H2, see pe\README.md), or a
  drive or folder that holds one unpacked. An ISO is mounted, and stays mounted.

.PARAMETER PhoenixPE
  The PhoenixPE folder to make or reuse.

.PARAMETER Archive
  A PhoenixPE-*.7z you already have, to unpack without downloading. One on the
  build VM's transfer disk is found by itself.

.PARAMETER Edition
  Which edition of install.wim to take system files from: Pro, Home, Education ...
  All of an ISO's editions make the same PE; Pro is what PhoenixPE is tested with.

.PARAMETER Out
  The folder LazarusPE.iso is copied to. Without it: the transfer disk's out folder,
  or this repo's pe\out.

.PARAMETER NoBuild
  Set everything up, but don't open PEBakery.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\Build-LazarusPE.ps1 C:\Users\me\Downloads\Win11_23H2.iso

.EXAMPLE
  .\Build-LazarusPE.ps1 E:\ -PhoenixPE D:\PhoenixPE -Edition Home -WhatIf     # show what would change
#>
[CmdletBinding(SupportsShouldProcess)]
param(
  [Parameter(Mandatory, Position = 0)]
  [string]$Windows,
  [string]$PhoenixPE = 'C:\PhoenixPE',
  [string]$Archive,
  [string]$Edition = 'Pro',
  [string]$Out,
  [switch]$NoBuild
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is many times slower drawing its bar

$here = $PSScriptRoot
$onWindows = $env:OS -eq 'Windows_NT'
if ($onWindows) {
  $me = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
  if (-not $me.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this from an administrator PowerShell: PEBakery builds as administrator, and so must what sets it up.'
  }
}

function Test-PhoenixPE([string]$Dir) {
  Test-Path -LiteralPath (Join-Path (Join-Path (Join-Path $Dir 'Projects') 'PhoenixPE') 'script.project')
}

# ── 1. PhoenixPE ────────────────────────────────────────────────────────────
# 7-Zip from where its installer recorded it, else Windows' own tar: never a program found by name.
function Find-Unpacker {
  foreach ($key in 'HKLM:\SOFTWARE\7-Zip', 'HKLM:\SOFTWARE\WOW6432Node\7-Zip') {
    $dir = (Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue | ForEach-Object { $_.PSObject.Properties['Path'] } | ForEach-Object { $_.Value })
    if ($dir) {
      $exe = Join-Path $dir '7z.exe'
      if (Test-Path -LiteralPath $exe) { return @{ Exe = $exe; Args = { param($a, $to) @('x', '-y', "-o$to", $a) } } }
    }
  }
  $tar = Join-Path ([Environment]::GetFolderPath('System')) 'tar.exe'
  if (Test-Path -LiteralPath $tar) { return @{ Exe = $tar; Args = { param($a, $to) @('-xf', $a, '-C', $to) } } }
  throw 'Nothing here can unpack a .7z: install 7-Zip (7-zip.org), or unpack PhoenixPE yourself and run this again.'
}

function Get-PhoenixPERelease([string]$To) {
  [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
  $release = Invoke-RestMethod -UseBasicParsing 'https://api.github.com/repos/PhoenixPE/PhoenixPE/releases/latest'
  $asset = @($release.assets | Where-Object { $_.name -like 'PhoenixPE-*-x64.7z' })
  if ($asset.Count -ne 1) { throw "PhoenixPE's release $($release.tag_name) has no single PhoenixPE-*-x64.7z: download it yourself and pass -Archive." }
  $asset = $asset[0]
  $digest = if ($asset.PSObject.Properties['digest']) { [string]$asset.digest } else { '' }
  if ($digest -notmatch '^sha256:([0-9a-f]{64})$') { throw "GitHub records no checksum for $($asset.name): download it yourself, check it, and pass -Archive." }
  $want = $Matches[1]
  $file = Join-Path $To ($asset.name -replace '[^A-Za-z0-9._-]', '_')
  Write-Host "Downloading $($asset.name) ($([math]::Round($asset.size / 1MB)) MB) ..."
  Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $file
  $got = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($got -ne $want) {
    Remove-Item -LiteralPath $file -Force
    throw "$($asset.name) isn't what GitHub recorded (sha256 $got, expected $want): not unpacked."
  }
  Write-Host "+ $($asset.name) matches GitHub's checksum"
  $file
}

if (Test-PhoenixPE $PhoenixPE) {
  Write-Host "PhoenixPE: $PhoenixPE (already there, kept)"
} elseif ((Test-Path -LiteralPath $PhoenixPE) -and @(Get-ChildItem -LiteralPath $PhoenixPE -Force).Count) {
  throw "$PhoenixPE exists, has files in it and isn't a PhoenixPE folder: name another with -PhoenixPE."
} elseif ($PSCmdlet.ShouldProcess($PhoenixPE, 'Download and unpack PhoenixPE')) {
  $unpack = Find-Unpacker
  if (-not $Archive) {   # the build VM's transfer disk carries the release that Linux put there
    $disk = Split-Path (Split-Path $here)
    $carried = @(if (Test-Path -LiteralPath (Join-Path $disk 'README.txt')) { Get-ChildItem -LiteralPath $disk -Filter 'PhoenixPE-*.7z' -File | Sort-Object Name })
    if ($carried) { $Archive = $carried[-1].FullName; Write-Host "PhoenixPE: $Archive (from the transfer disk)" }
  }
  New-Item -ItemType Directory -Force $PhoenixPE | Out-Null
  $file = if ($Archive) { (Resolve-Path -LiteralPath $Archive).Path } else { Get-PhoenixPERelease $PhoenixPE }
  Write-Host "Unpacking into $PhoenixPE ..."
  & $unpack.Exe @(& $unpack.Args $file $PhoenixPE) | Out-Null
  if ($LASTEXITCODE -ne 0 -or -not (Test-PhoenixPE $PhoenixPE)) { throw "Couldn't unpack $file into $PhoenixPE ($($unpack.Exe) said $LASTEXITCODE)." }
  if (-not $Archive) { Remove-Item -LiteralPath $file -Force }
  Write-Host "+ PhoenixPE unpacked"
} else {
  Write-Host "`nNothing else can be shown until PhoenixPE is unpacked."
  return
}

# ── 2. The preset ───────────────────────────────────────────────────────────
Write-Host "`nThe Helix preset:"
& (Join-Path $here 'Apply-HelixPreset.ps1') -PhoenixPE $PhoenixPE -WhatIf:$WhatIfPreference 6>&1 |
  Where-Object { "$_" -notmatch '^\s*$|Open PEBakeryLauncher\.exe' } | ForEach-Object { Write-Host $_ }

# ── 3. Source Config ────────────────────────────────────────────────────────
# A WIM (or ESD) lists its images in an XML block that its header points at: no DISM needed.
function Get-WimImages([string]$Path) {
  $stream = [IO.File]::Open($Path, 'Open', 'Read', 'ReadWrite')
  try {
    $head = New-Object byte[] 96
    if ($stream.Read($head, 0, 96) -ne 96 -or [Text.Encoding]::ASCII.GetString($head, 0, 5) -ne 'MSWIM') { throw "$Path isn't a Windows image file." }
    $size = [BitConverter]::ToInt64($head, 0x48) -band 0x00FFFFFFFFFFFFFF   # the top byte is flags
    $offset = [BitConverter]::ToInt64($head, 0x50)
    if ($size -lt 2 -or $size -gt 64MB -or $offset -le 0 -or $offset + $size -gt $stream.Length) { throw "$Path has a damaged image list." }
    $size = [int]$size
    $bytes = New-Object byte[] $size
    [void]$stream.Seek($offset, 'Begin')
    $read = 0
    while ($read -lt $size) {
      $n = $stream.Read($bytes, $read, $size - $read)
      if ($n -le 0) { throw "$Path ends inside its image list." }
      $read += $n
    }
  } finally { $stream.Dispose() }
  $text = [Text.Encoding]::Unicode.GetString($bytes).TrimStart([char]0xFEFF)
  $settings = New-Object Xml.XmlReaderSettings
  $settings.DtdProcessing = 'Prohibit'
  $settings.XmlResolver = $null
  $xml = New-Object Xml.XmlDocument
  $xml.XmlResolver = $null
  $reader = [Xml.XmlReader]::Create((New-Object IO.StringReader $text), $settings)
  try { $xml.Load($reader) } finally { $reader.Dispose() }
  foreach ($image in $xml.SelectNodes('/WIM/IMAGE')) {
    $get = { param($q) $n = $image.SelectSingleNode($q); if ($n) { $n.InnerText.Trim() } else { '' } }
    $name = & $get 'DISPLAYNAME'
    if (-not $name) { $name = & $get 'NAME' }
    $lang = & $get 'WINDOWS/LANGUAGES/DEFAULT'
    $fallback = (& $get 'WINDOWS/LANGUAGES/FALLBACK') -replace ',', '|'
    [pscustomobject]@{
      Index    = [int]$image.GetAttribute('INDEX')
      Name     = $name
      Arch     = if ((& $get 'WINDOWS/ARCH') -eq '0') { 'x86' } else { 'x64' }
      Lang     = $lang
      Fallback = "$lang|$fallback".Trim('|')
      Version  = '{0}.{1}.{2}.{3}' -f (& $get 'WINDOWS/VERSION/MAJOR'), (& $get 'WINDOWS/VERSION/MINOR'), (& $get 'WINDOWS/VERSION/BUILD'), (& $get 'WINDOWS/VERSION/SPBUILD')
      Build    = [int]('0' + (& $get 'WINDOWS/VERSION/BUILD'))
    }
  }
}

# PhoenixPE's files are read and written keeping their encoding, BOM and line endings.
function Read-Script([string]$Path) {
  $bytes = [IO.File]::ReadAllBytes($Path)
  $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
  $enc = New-Object Text.UTF8Encoding($bom)
  $text = $enc.GetString($bytes)
  if ($bom) { $text = $text.Substring(1) }
  $nl = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
  @{ Enc = $enc; Nl = $nl; Lines = $text -split "\r?\n"; Was = $text }
}
function Write-Script([string]$Path, $s) {
  if (($s.Lines -join $s.Nl) -ceq $s.Was) { return $false }
  [IO.File]::WriteAllBytes($Path, [byte[]]($s.Enc.GetPreamble() + $s.Enc.GetBytes($s.Lines -join $s.Nl)))
  $true
}
function Find-Row($s, [string]$Section, [string]$Name) {
  $in = ''
  for ($i = 0; $i -lt $s.Lines.Count; $i++) {
    if ($s.Lines[$i] -match '^\s*\[(.+)\]\s*$') { $in = $Matches[1]; continue }
    if ($in -eq $Section -and $s.Lines[$i].StartsWith("$Name=")) { return $i }
  }
  throw "this PhoenixPE has no $Name in [$Section]: it has changed since this script was written. Set Source Config by hand in PEBakery (pe\README.md)."
}
function Split-Fields([string]$s) {
  [regex]::Matches($s, '(?<=^|,)("[^"]*"|[^,]*)') | ForEach-Object { $_.Value }
}
function Quote([string]$s) { if ($s -match '[\s,]') { '"' + $s + '"' } else { $s } }
# A value PEBakery reads back: it writes these few characters as escapes.
function Escape([string]$s) { $s.Replace('#', '#$s').Replace('%', '#$p').Replace('"', '#$q') }

# One row of a script's [Interface]: its value, and for a dropdown its choices as well.
function Set-Row($s, [string]$Name, [string]$Type, [string]$Value, [string[]]$Choices) {
  $at = Find-Row $s 'Interface' $Name
  $fields = @(Split-Fields $s.Lines[$at].Substring($Name.Length + 1))
  if ($fields.Count -lt 7 -or $fields[2] -ne $Type) { throw "$Name isn't the kind of option it was (type $($fields[2]), expected $Type): set Source Config by hand in PEBakery." }
  if ($Type -eq '4') {
    # after the choices: the section a change runs (_Name_,True|False) and a tooltip (__text)
    $tail = @()
    for ($i = 7; $i -lt $fields.Count; $i++) {
      if ($fields[$i] -match '^_[^_].*_$|^"?__') { $tail = $fields[$i..($fields.Count - 1)]; break }
    }
    $fields = @(Quote (Escape $Value)) + $fields[1..6] + @($Choices | ForEach-Object { Quote (Escape $_) }) + $tail
  } elseif ($Type -eq '3') {
    $fields[7] = $Value
  } else {
    $fields[0] = Quote (Escape $Value)
  }
  $s.Lines[$at] = "$Name=" + ($fields -join ',')
}

Write-Host "`nSource Config:"
$mounted = $false
$source = if ($Windows -match '^[A-Za-z]:$') { "$Windows\" } else { $Windows }   # E: means the disc, not a folder on it
if ((Test-Path -LiteralPath $Windows -PathType Leaf) -and $Windows -match '\.iso$') {
  $iso = (Resolve-Path -LiteralPath $Windows).Path
  $image = Get-DiskImage -ImagePath $iso
  if (-not $image.Attached) { $image = Mount-DiskImage -ImagePath $iso -PassThru; $mounted = $true }
  $letter = ($image | Get-Volume).DriveLetter
  if (-not $letter) { throw "$iso is mounted but has no drive letter: give it one in Disk Management, or unpack it and pass the folder." }
  $source = "${letter}:\"
  Write-Host "  $iso is drive ${letter}: (leave it mounted until the build is done)"
}
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "$Windows is neither an .iso nor a folder." }
$source = (Resolve-Path -LiteralPath $source).Path
$sources = Join-Path $source 'Sources'
$bootWim = Join-Path $sources 'Boot.wim'
$installWim = @('Install.wim', 'Install.esd' | ForEach-Object { Join-Path $sources $_ } | Where-Object { Test-Path -LiteralPath $_ })
if (-not (Test-Path -LiteralPath $bootWim) -or -not $installWim) { throw "$source isn't a Windows disc: it has no Sources\Boot.wim and Sources\Install.wim." }
$installWim = $installWim[0]

$base = @(Get-WimImages $bootWim | Sort-Object Index)
$editions = @(Get-WimImages $installWim | Sort-Object Index)
if (-not $base -or -not $editions) { throw "$source's image files list no images." }
$baseImage = $base[-1]   # the last one is Windows Setup, which is what PhoenixPE takes
$picked = @($editions | Where-Object { $_.Name -match "^Windows 1[01] $([regex]::Escape($Edition))$" })
if (-not $picked) { $picked = @($editions | Where-Object { $_.Name -eq $Edition }) }
if (-not $picked -and $editions.Count -eq 1) {
  $picked = $editions
  Write-Host "  this disc has one edition, $($picked[0].Name): using it"
}
if ($picked.Count -ne 1) {
  Write-Host "  this disc's editions:"
  $editions | ForEach-Object { Write-Host "    $($_.Name)" }
  throw "No single '$Edition' edition on this disc: pick one of the above with -Edition (the part after 'Windows 11', or the whole name)."
}
$chosen = $picked[0]
if ($chosen.Index -gt 9 -or $baseImage.Index -gt 9) { throw "PhoenixPE reads an image's number as one digit; $($chosen.Name) is number $($chosen.Index). Use a disc with fewer editions." }
if ($chosen.Arch -ne 'x64') { throw "$($chosen.Name) is $($chosen.Arch): Lazarus PE is built from 64-bit Windows." }
if ($chosen.Name -match '\bS\b|S mode') { Write-Warning "$($chosen.Name): PhoenixPE doesn't support Windows S." }
if ($chosen.Name -notmatch ' Pro$') { Write-Warning "$($chosen.Name): PhoenixPE is tested with Pro. Other editions of the same disc should make the same PE; if the build fails, try -Edition Pro." }
if ($chosen.Build -ge 26100) {
  Write-Warning "This is Windows build $($chosen.Build) (24H2 or later): the PE builds, but its Start menu doesn't open. Build from Windows 11 22H2 or 23H2 (pe\README.md, 'Which Windows to build from')."
} elseif ($chosen.Build -notin 19041, 22621, 22631) {
  Write-Warning "Windows build $($chosen.Build) isn't one PhoenixPE recommends (Windows 10 2004, Windows 11 22H2 or 23H2)."
}

# What PhoenixPE's own "Rescan Source" works out and saves, worked out here.
$sourceDir = $source.TrimEnd('\', '/')
$vars = [ordered]@{
  SourceDir             = $sourceDir
  SourceBaseWimName     = 'Boot.wim'
  SourceBaseWim         = "$sourceDir\Sources\Boot.wim"
  SourceInstallWim      = "$sourceDir\Sources\$(Split-Path $installWim -Leaf)"
  SourceBaseWimImage    = [string]$baseImage.Index
  SourceInstallWimImage = [string]$chosen.Index
  SourceArch            = $chosen.Arch
  SourceLang            = $chosen.Lang
  SourceFallbackLang    = $chosen.Fallback
  SourceVer             = $chosen.Version
}
$project = Join-Path (Join-Path $PhoenixPE 'Projects') 'PhoenixPE'
$projectFile = Join-Path $project 'script.project'
$configFile = Join-Path $project '100-ConfigSource.script'
if (-not (Test-Path -LiteralPath $configFile)) { throw "this PhoenixPE has no 100-ConfigSource.script: it has changed since this script was written. Set Source Config by hand in PEBakery (pe\README.md)." }

$p = Read-Script $projectFile
foreach ($name in $vars.Keys) {
  $p.Lines[(Find-Row $p 'Variables' "%$name%")] = "%$name%=" + $vars[$name]
}
$c = Read-Script $configFile
$label = { param($i) "$($i.Index) - $($i.Name)" }
Set-Row $c 'fb_SrcPath' '20' $source
Set-Row $c 'cmb_BaseWim' '4' 'Boot.wim' @('Boot.wim', 'WinRE.wim')
Set-Row $c 'cmb_SrcBaseImage' '4' (& $label $baseImage) @($base | ForEach-Object { & $label $_ })
Set-Row $c 'cmb_SrcInstallImage' '4' (& $label $chosen) @($editions | ForEach-Object { & $label $_ })
Set-Row $c 'lbl_ImgInfo' '1' "Language:  $($chosen.Lang)          Architecture:  $($chosen.Arch)          Version:  $($chosen.Version)"
Set-Row $c 'cb_RunFromWim' '3' 'False'   # apps load from the stick: a small image that boots in legacy BIOS mode too

$changed = $false
if ($PSCmdlet.ShouldProcess($projectFile, "Source: $sourceDir, $($chosen.Name)")) {
  $changed = (Write-Script $projectFile $p) -or $changed
  $changed = (Write-Script $configFile $c) -or $changed
  # A different source makes what PhoenixPE cached from the last one wrong, as its own rescan knows
  $cache = Join-Path (Join-Path (Join-Path $PhoenixPE 'Workbench') 'PhoenixPE') 'Cache'
  if ($changed -and (Test-Path -LiteralPath $cache)) {
    Remove-Item -LiteralPath $cache -Recurse -Force
    Write-Host "  the source changed: PhoenixPE's cache of the last one is cleared"
  }
}
Write-Host "  source   $sourceDir"
Write-Host "  base     $(& $label $baseImage)"
Write-Host "  edition  $(& $label $chosen)   ($($chosen.Lang), $($chosen.Arch), $($chosen.Version))"
Write-Host "  programs load from the stick, not from RAM"
if (-not $changed -and -not $WhatIfPreference) { Write-Host "  (already set)" }

if ($WhatIfPreference -or $NoBuild) {
  Write-Host "`nReady. Run PEBakeryLauncher.exe in $PhoenixPE as administrator and press Build."
  return
}

# ── 4. Build ────────────────────────────────────────────────────────────────
$launcher = Join-Path $PhoenixPE 'PEBakeryLauncher.exe'
if (-not (Test-Path -LiteralPath $launcher)) { throw "$PhoenixPE has no PEBakeryLauncher.exe." }
$isoDir = Join-Path $PhoenixPE 'Output'
$started = Get-Date
Start-Process -FilePath $launcher -WorkingDirectory $PhoenixPE
Write-Host "`nPEBakery is opening. Press Build (top left) and leave this window open."
Write-Host "The first build takes a while: it caches the Windows files. Waiting for the ISO ..."

# ── 5. The ISO ──────────────────────────────────────────────────────────────
$built = $null; $lastSize = -1; $seen = $false
while (-not $built) {
  Start-Sleep -Seconds 5
  $running = @(Get-Process -Name 'PEBakery*' -ErrorAction SilentlyContinue).Count -gt 0
  $seen = $seen -or $running
  $new = @(Get-ChildItem -LiteralPath $isoDir -Filter '*.iso' -File -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -gt $started } | Sort-Object LastWriteTime)
  if ($new) {
    $size = $new[-1].Length
    if ($size -gt 0 -and $size -eq $lastSize) {
      try { [IO.File]::Open($new[-1].FullName, 'Open', 'Read', 'None').Dispose(); $built = $new[-1] } catch { }   # still being written
    }
    $lastSize = $size
  } elseif ($seen -and -not $running) {
    Write-Warning "PEBakery was closed before an ISO was built. Run this again, or PEBakeryLauncher.exe, when you're ready."
    return
  }
}
Write-Host "+ built: $($built.FullName) ($([math]::Round($built.Length / 1MB)) MB)"

if (-not $Out) {
  $transfer = Split-Path (Split-Path $here)      # <transfer disk>\helix\phoenixpe
  $repoOut = Join-Path (Split-Path $here) 'out'  # <repo>\pe\phoenixpe
  if ((Test-Path -LiteralPath (Join-Path $transfer 'out')) -and (Test-Path -LiteralPath (Join-Path $transfer 'README.txt'))) {
    $Out = Join-Path $transfer 'out'
  } elseif (Test-Path -LiteralPath $repoOut) {
    $Out = $repoOut
  }
}
$final = $built.FullName
if ($Out) {
  New-Item -ItemType Directory -Force $Out | Out-Null
  $final = Join-Path $Out 'LazarusPE.iso'
  Copy-Item -LiteralPath $built.FullName -Destination $final -Force
  Write-Host "+ copied to $final"
}
if ($mounted) { Write-Host "  (the Windows ISO is still mounted: right-click its drive, Eject, when you're done building)" }
Write-Host @"

Lazarus PE is built. Next:
  - Built from Windows 11 22H2 or 23H2? Give it a newer boot manager, or it hangs on
    newer PCs: on Linux, pe/fix-bootmgr.sh <a current Windows 11 .iso>  (pe\README.md)
  - On the stick it goes in ISO\6-Live-Operating-Systems\LazarusPE.iso.
    From a clone on Linux: pe/out/LazarusPE.iso, then ./helix fetch lazarus-pe and ./refresh.sh
"@
