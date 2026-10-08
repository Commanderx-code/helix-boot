<#
  pe\phoenixpe\Build-LazarusPE.ps1 against a stand-in PhoenixPE folder and a stand-in Windows
  disc: what it writes into PhoenixPE's Source Config, which edition it picks, what it refuses.
  Nothing is downloaded, mounted or built.
    powershell -ExecutionPolicy Bypass -File tests\lazarus\Test-BuildScript.ps1 -Work $env:TEMP\build-test
#>
param([Parameter(Mandatory)][string]$Work)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3
$build = Join-Path (Join-Path (Join-Path (Split-Path (Split-Path $PSScriptRoot)) 'pe') 'phoenixpe') 'Build-LazarusPE.ps1'
$fail = @()
function Expect([string]$what, $got, $want) { if ("$got" -cne "$want") { $script:fail += "${what}: wanted '$want', got '$got'" } }

# A WIM as far as its image list goes: the header, then the XML it points at.
function New-Wim([string]$Path, [string[]]$Names, [int]$Build = 22621, [string]$Fallback = '') {
  $xml = '<WIM>'
  for ($i = 0; $i -lt $Names.Count; $i++) {
    $fb = if ($Fallback) { "<FALLBACK>$Fallback</FALLBACK>" } else { '' }
    $xml += "<IMAGE INDEX=`"$($i + 1)`"><NAME>$($Names[$i])</NAME><WINDOWS><ARCH>9</ARCH><LANGUAGES><DEFAULT>en-US</DEFAULT>$fb</LANGUAGES>" +
      "<VERSION><MAJOR>10</MAJOR><MINOR>0</MINOR><BUILD>$Build</BUILD><SPBUILD>1</SPBUILD></VERSION></WINDOWS></IMAGE>"
  }
  $body = [byte[]](0xFF, 0xFE) + [Text.Encoding]::Unicode.GetBytes($xml + '</WIM>')
  $head = New-Object byte[] 208
  [Text.Encoding]::ASCII.GetBytes('MSWIM').CopyTo($head, 0)
  [BitConverter]::GetBytes([int64]$body.Length -bor ([int64]2 -shl 56)).CopyTo($head, 0x48)
  [BitConverter]::GetBytes([int64]208).CopyTo($head, 0x50)
  [IO.File]::WriteAllBytes($Path, [byte[]]($head + $body))
}
function New-Disc([string]$Name, [string[]]$Editions, [int]$Build = 22621, [string]$Fallback = '') {
  $dir = Join-Path $Work $Name
  New-Item -ItemType Directory -Force (Join-Path $dir 'Sources') | Out-Null
  New-Wim (Join-Path (Join-Path $dir 'Sources') 'Boot.wim') 'Microsoft Windows PE', 'Microsoft Windows Setup' $Build
  New-Wim (Join-Path (Join-Path $dir 'Sources') 'Install.wim') $Editions $Build $Fallback
  $dir
}
# PhoenixPE as far as this script reads it, with rows shaped like the real ones.
function New-PhoenixPE([string]$Name) {
  $dir = Join-Path $Work $Name
  $project = Join-Path (Join-Path $dir 'Projects') 'PhoenixPE'
  New-Item -ItemType Directory -Force $project, (Join-Path (Join-Path (Join-Path $dir 'Workbench') 'PhoenixPE') 'Cache') | Out-Null
  $vars = 'SourceDir', 'SourceBaseWimName', 'SourceBaseWim', 'SourceInstallWim', 'SourceBaseWimImage', 'SourceInstallWimImage', 'SourceArch', 'SourceLang', 'SourceFallbackLang', 'SourceVer'
  [IO.File]::WriteAllText((Join-Path $project 'script.project'),
    ((@('[Main]', 'Title=PhoenixPE', '', '[Variables]', '%Workbench%=%BaseDir%\Workbench') + ($vars | ForEach-Object { "%$_%=" }) + @('', '[Interface]', 'lbl_Welcome=Welcome!,1,1,5,5,200,25,16,Bold')) -join "`r`n"))
  [IO.File]::WriteAllText((Join-Path $project '100-ConfigSource.script'), (@(
    '[Main]', 'Title=Config Source', 'Selected=True', '', '[Interface]',
    'fb_SrcPath=,1,20,94,93,500,20,dir,"Title=Select the directory",_SaveSource_,False',
    'cmb_BaseWim=Boot.wim,0,4,130,185,100,21,Boot.wim,WinRE.wim,_SaveSource_,False',
    'cmb_SrcBaseImage="[Please select a valid source]",1,4,130,211,474,21,"[Please select a valid source]"',
    'cmb_SrcInstallImage="[Please select a valid source]",1,4,130,237,474,21,"[Please select a valid source]",_GetSourceWimImage_,True',
    'lbl_ImgInfo=,1,1,131,274,474,16,8,Bold',
    'cb_RunFromWim="Run all programs from RAM (Boot.wim)",1,3,15,342,215,18,True,"__Pack all programs into Boot.wim, whatever each script says."'
  ) -join "`r`n"))
  $dir
}
function Run([string]$Disc, [string]$PE, [hashtable]$More = @{}) {
  $out = $null
  try { $out = & $build $Disc -PhoenixPE $PE -NoBuild @More *>&1 | Out-String; @{ Ok = $true; Text = $out } }
  catch { @{ Ok = $false; Text = "$_" } }
}
function Row([string]$PE, [string]$File, [string]$Name) {
  $line = @(Get-Content -LiteralPath (Join-Path (Join-Path (Join-Path $PE 'Projects') 'PhoenixPE') $File) | Where-Object { $_.StartsWith("$Name=") })
  if ($line.Count -ne 1) { return "($($line.Count) rows)" }
  $line[0].Substring($Name.Length + 1)
}

Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Work | Out-Null
$disc = New-Disc 'win' 'Windows 11 Home', 'Windows 11 Home N', 'Windows 11 Education', 'Windows 11 Pro', 'Windows 11 Pro N'
$pe = New-PhoenixPE 'ppe'
$src = (Resolve-Path $disc).Path.TrimEnd('\', '/')

# Pro by default, among several editions
$r = Run $disc $pe
Expect 'the first run' $r.Ok $true
if (-not $r.Ok) { $fail += $r.Text }
Expect 'SourceDir' (Row $pe 'script.project' '%SourceDir%') $src
Expect 'SourceBaseWim' (Row $pe 'script.project' '%SourceBaseWim%') "$src\Sources\Boot.wim"
Expect 'SourceInstallWim' (Row $pe 'script.project' '%SourceInstallWim%') "$src\Sources\Install.wim"
Expect 'the base image (Windows Setup)' (Row $pe 'script.project' '%SourceBaseWimImage%') '2'
Expect 'the edition (Pro)' (Row $pe 'script.project' '%SourceInstallWimImage%') '4'
Expect 'SourceArch' (Row $pe 'script.project' '%SourceArch%') 'x64'
Expect 'SourceFallbackLang' (Row $pe 'script.project' '%SourceFallbackLang%') 'en-US'
Expect 'SourceVer' (Row $pe 'script.project' '%SourceVer%') '10.0.22621.1'
Expect 'a variable that isn''t the source''s' (Row $pe 'script.project' '%Workbench%') '%BaseDir%\Workbench'
Expect 'the base dropdown' (Row $pe '100-ConfigSource.script' 'cmb_SrcBaseImage') '"2 - Microsoft Windows Setup",1,4,130,211,474,21,"1 - Microsoft Windows PE","2 - Microsoft Windows Setup"'
Expect 'the edition dropdown keeps what a change runs' (Row $pe '100-ConfigSource.script' 'cmb_SrcInstallImage') '"4 - Windows 11 Pro",1,4,130,237,474,21,"1 - Windows 11 Home","2 - Windows 11 Home N","3 - Windows 11 Education","4 - Windows 11 Pro","5 - Windows 11 Pro N",_GetSourceWimImage_,True'
Expect 'run from RAM is off, tooltip kept' (Row $pe '100-ConfigSource.script' 'cb_RunFromWim') '"Run all programs from RAM (Boot.wim)",1,3,15,342,215,18,False,"__Pack all programs into Boot.wim, whatever each script says."'
Expect 'the base-wim dropdown is as it was' (Row $pe '100-ConfigSource.script' 'cmb_BaseWim') 'Boot.wim,0,4,130,185,100,21,Boot.wim,WinRE.wim,_SaveSource_,False'
Expect 'a new source clears the cache' (Test-Path (Join-Path $pe 'Workbench\PhoenixPE\Cache')) $false
$bytes = [IO.File]::ReadAllBytes((Join-Path $pe 'Projects\PhoenixPE\script.project'))
Expect 'line endings kept (CRLF)' ([Text.Encoding]::UTF8.GetString($bytes).Contains("`r`n")) $true
Expect 'no BOM added' ($bytes[0] -eq 0xEF) $false

# The same again changes nothing, and so leaves a cache alone
New-Item -ItemType Directory -Force (Join-Path $pe 'Workbench\PhoenixPE\Cache') | Out-Null
$r = Run $disc $pe
Expect 'a second run says so' ($r.Text -match 'already set') $true
Expect 'an unchanged source keeps the cache' (Test-Path (Join-Path $pe 'Workbench\PhoenixPE\Cache')) $true

# Another edition by name; one that isn't there is refused, and nothing is written
$r = Run $disc $pe @{ Edition = 'Home' }
Expect 'Home, asked for' (Row $pe 'script.project' '%SourceInstallWimImage%') '1'
Expect 'Home comes with a note' ($r.Text -match 'tested with Pro') $true
$r = Run $disc $pe @{ Edition = 'Ultimate' }
Expect 'an edition the disc lacks' $r.Ok $false
Expect 'refusing leaves the last choice' (Row $pe 'script.project' '%SourceInstallWimImage%') '1'

# -WhatIf writes nothing
$r = Run $disc $pe @{ Edition = 'Pro'; WhatIf = $true }
Expect '-WhatIf leaves the edition' (Row $pe 'script.project' '%SourceInstallWimImage%') '1'

# A disc with one edition uses it; a fallback language is carried; 24H2 is warned about
$one = New-Disc 'home' @('Windows 11 Home') 26100 'en-US,de-DE'
$r = Run $one $pe
Expect 'the only edition' (Row $pe 'script.project' '%SourceInstallWimImage%') '1'
Expect 'fallback languages' (Row $pe 'script.project' '%SourceFallbackLang%') 'en-US|en-US|de-DE'
Expect '24H2 is warned about' ($r.Text -match 'Start menu') $true

# Not a Windows disc; not a PhoenixPE; a PhoenixPE that has changed
New-Item -ItemType Directory -Force (Join-Path $Work 'empty') | Out-Null
Expect 'a folder that isn''t a Windows disc' (Run (Join-Path $Work 'empty') $pe).Ok $false
New-Item -ItemType Directory -Force (Join-Path $Work 'other') | Out-Null
Set-Content (Join-Path $Work 'other\mine.txt') 'x'
$r = Run $disc (Join-Path $Work 'other')
Expect 'a folder of something else is not unpacked into' $r.Ok $false
Expect 'and is left alone' (@(Get-ChildItem (Join-Path $Work 'other')).Count) 1
$odd = New-PhoenixPE 'odd'
$file = Join-Path $odd 'Projects\PhoenixPE\100-ConfigSource.script'
(Get-Content $file) -replace '^cmb_SrcInstallImage=', 'cmb_Renamed=' | Set-Content $file
$r = Run $disc $odd
Expect 'a PhoenixPE with a renamed option' $r.Ok $false
Expect 'nothing half-written into it' (Row $odd 'script.project' '%SourceDir%') ''

if ($fail) { $fail | ForEach-Object { Write-Host "FAIL $_" }; throw "$($fail.Count) check(s) failed" }
'build script ok'
