<#
  Helix Boot - print the stick's drive (e.g. "E:"), or nothing if it isn't there.

  A tag file alone proves nothing: the PC being repaired can have C:\helix-boot.tag planted
  on its own disks, and whatever this picks, Lazarus PE runs as SYSTEM. So a drive counts
  only if its tag is a file (not a folder), it holds no installed Windows, and its disk is on a USB, SD or MMC bus (a USB SSD enclosure included).

  Used by StartPortableApps.cmd and HelixApps.cmd. -Letters and -BusOf are for testing.
#>
param(
  [string[]]$Letters,
  [hashtable]$BusOf
)
$ErrorActionPreference = 'SilentlyContinue'
$tags = 'helix-boot.tag', 'commander-rescue.tag'
if (-not $Letters) { $Letters = @([IO.DriveInfo]::GetDrives() | ForEach-Object { $_.Name.Substring(0, 1) }) }

function Test-Candidate([string]$letter) {
  $root = "${letter}:\"
  $tagged = @($tags | Where-Object { Test-Path -LiteralPath (Join-Path $root $_) -PathType Leaf }).Count -gt 0
  $tagged -and -not (Test-Path -LiteralPath (Join-Path $root 'Windows\System32\config\SYSTEM'))
}

# Drive letter -> bus type, from the Storage cmdlets or else WMI; empty when neither answers.
function Get-BusMap {
  $map = @{}
  try {
    foreach ($p in @(Get-Partition -ErrorAction Stop | Where-Object { $_.DriveLetter })) {
      $map["$($p.DriveLetter)"] = "$((Get-Disk -Number $p.DiskNumber -ErrorAction Stop).BusType)"
    }
  } catch { $map = @{} }
  if ($map.Count) { return $map }
  try {
    foreach ($d in @(Get-CimInstance Win32_DiskDrive -ErrorAction Stop)) {
      foreach ($p in @(Get-CimAssociatedInstance -InputObject $d -ResultClassName Win32_DiskPartition)) {
        foreach ($v in @(Get-CimAssociatedInstance -InputObject $p -ResultClassName Win32_LogicalDisk)) {
          $map[$v.DeviceID.Substring(0, 1)] = "$($d.InterfaceType)"
        }
      }
    }
  } catch { }
  $map
}

$found = @($Letters | Where-Object { Test-Candidate $_ })
$bus = if ($PSBoundParameters.ContainsKey('BusOf')) { $BusOf } else { Get-BusMap }
$found = @($found | Where-Object { $bus["$_"] -in 'USB', 'SD', 'MMC' })
if ($found.Count) { "$($found[0]):" }
