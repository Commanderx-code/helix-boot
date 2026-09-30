<#
.SYNOPSIS
  Lazarus launcher: the start screen of Lazarus PE (Helix Boot).

.DESCRIPTION
  Lists every tool the PE can reach, in the categories of launcher.json:
    - Helix Apps on the stick (Apps\apps.txt),
    - PortableApps.com apps on the stick (PortableApps\*\App\AppInfo\appinfo.ini),
    - the PE's own Start menu, which PhoenixPE fills as the PE starts.
  The same tool from more than one place is listed once (stick first: it's kept current).
  Lives on the stick in Apps\Lazarus\ and is updated by a refresh, so it needs no PE rebuild.

.EXAMPLE
  powershell -STA -NoProfile -ExecutionPolicy Bypass -File LazarusLauncher.ps1
.EXAMPLE
  .\LazarusLauncher.ps1 -Root D:\fake-stick -StartMenu D:\menu -Screenshot shot.png -Category disk
#>
[CmdletBinding()]
param(
  [string]$Root,                  # the stick; default: two folders up from this script
  [string[]]$StartMenu,           # Start menu folders to list; default: this system's
  [string]$Screenshot,            # render to this .png and exit (testing)
  [int]$Width = 1920,
  [int]$Height = 1080,
  [string]$Category,              # with -Screenshot: which category is open
  [string]$SearchText,            # with -Screenshot: text in the search box
  [switch]$ShowInfo,              # with -Screenshot: the System Info panel open
  [string]$ListTo                 # write the tools found, with their categories, to this .json and exit
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase, System.Xaml, System.Drawing

$here = $PSScriptRoot
if (-not $Root) { $Root = Split-Path (Split-Path $here) }
$Root = $Root.TrimEnd('\')
$cfg = Get-Content -Raw -Encoding UTF8 (Join-Path $here 'launcher.json') | ConvertFrom-Json
$inPE = Test-Path 'HKLM:\SYSTEM\CurrentControlSet\Control\MiniNT'

function Get-Geometry([string]$name) {
  $prop = $cfg.icons.PSObject.Properties[$name]   # a misspelled icon shows nothing rather than failing
  if (-not $prop) { return $null }
  $d = $prop.Value
  $g = [Windows.Media.Geometry]::Parse($d)
  $g.Freeze()
  $g
}

# ── Reading tools ────────────────────────────────────────────────────────────
# appinfo.ini comes as UTF-8, UTF-16 or ANSI (Recuva® and friends), sometimes with junk
# before the first [section].
function Read-Text([string]$path) {
  $bytes = [IO.File]::ReadAllBytes($path)
  if ($bytes.Length -ge 2 -and (($bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) -or ($bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF))) {
    return [IO.File]::ReadAllText($path)   # UTF-16, by its BOM
  }
  try { (New-Object Text.UTF8Encoding $false, $true).GetString($bytes).TrimStart([char]0xFEFF) }
  catch { [Text.Encoding]::Default.GetString($bytes) }   # not UTF-8: the system's ANSI code page
}
function Read-Ini([string]$path) {
  $ini = @{}
  $section = ''
  foreach ($line in ((Read-Text $path) -split "`r?`n")) {
    if ($line -match '^\s*\[(.+?)\]') { $section = $Matches[1]; $ini[$section] = @{}; continue }
    if ($section -and $line -match '^\s*([^=;]+?)\s*=\s*(.*)$') { $ini[$section][$Matches[1]] = $Matches[2].Trim() }
  }
  $ini
}
function Get-IniValue($ini, [string]$section, [string]$key) {
  if ($ini.ContainsKey($section) -and $ini[$section].ContainsKey($key)) { return $ini[$section][$key] }
  ''
}

function Get-ImageFromFile([string]$path, [int]$width = 88) {
  try {   # from memory: loaded now, and no file left open on the stick
    $b = New-Object Windows.Media.Imaging.BitmapImage
    $b.BeginInit()
    $b.StreamSource = New-Object IO.MemoryStream (, [IO.File]::ReadAllBytes($path))
    if ($width) { $b.DecodePixelWidth = $width }
    $b.CacheOption = [Windows.Media.Imaging.BitmapCacheOption]::OnLoad
    $b.EndInit()
    $b.Freeze()
    $b
  } catch { $null }
}

function Get-ImageFromExe([string]$path) {
  if (-not $path -or -not (Test-Path -LiteralPath $path)) { return $null }
  try {
    $icon = [System.Drawing.Icon]::ExtractAssociatedIcon($path)
    if (-not $icon) { return $null }
    $src = [Windows.Interop.Imaging]::CreateBitmapSourceFromHIcon($icon.Handle, [Windows.Int32Rect]::Empty,
      [Windows.Media.Imaging.BitmapSizeOptions]::FromEmptyOptions())
    $src.Freeze()
    $icon.Dispose()
    $src
  } catch { $null }
}

function New-Tool([string]$title, [string]$id, [string]$description, [string]$where, [string]$run,
                  [string]$arguments, [string]$workdir, $image, [string]$paCategory, [string]$folder) {
  $rename = $cfg.PSObject.Properties['rename']
  if ($rename -and $rename.Value.PSObject.Properties[$id]) { $title = $rename.Value.$id }
  if ($description) { $description = $description.Substring(0, 1).ToUpper() + $description.Substring(1) }
  if ($image -is [psobject]) { $image = $image.PSObject.BaseObject }   # WPF shows the picture, not PowerShell's wrapper
  [pscustomobject]@{
    Title = $title; Id = $id; Description = $description; Where = $where
    Run = $run; Arguments = $arguments; WorkDir = $workdir
    Image = $image; Glyph = $null; PACategory = $paCategory; Folder = $folder; Category = ''
    Line1 = $(if ($description) { $description } else { $where }); Line2 = $(if ($description) { $where } else { '' })
  }
}

function Get-HelixApps {
  $apps = Join-Path $Root 'Apps'
  $list = Join-Path $apps 'apps.txt'
  if (-not (Test-Path -LiteralPath $list)) { return }
  foreach ($line in (Get-Content -LiteralPath $list -Encoding UTF8)) {
    $f = $line.Split('|')
    if ($f.Count -lt 2 -or -not $f[1]) { continue }
    $path = Join-Path $apps $f[1]
    if (-not (Test-Path -LiteralPath $path)) { continue }
    $id = $f[1].Split('\')[0]
    $desc = if ($f.Count -ge 3) { $f[2] } else { '' }
    if ($path -like '*.ps1') {
      New-Tool $f[0] $id $desc 'Helix Apps' 'powershell.exe' "-NoProfile -ExecutionPolicy Bypass -File `"$path`"" (Split-Path $path) $null '' ''
    } else {
      New-Tool $f[0] $id $desc 'Helix Apps' $path '' (Split-Path $path) (Get-ImageFromExe $path) '' ''
    }
  }
}

function Get-PortableApps {
  $base = Join-Path $Root 'PortableApps'
  if (-not (Test-Path -LiteralPath $base)) { return }
  foreach ($d in (Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue)) {
    $info = Join-Path $d.FullName 'App\AppInfo'
    $ini = $null
    if (Test-Path -LiteralPath (Join-Path $info 'appinfo.ini')) {
      try { $ini = Read-Ini (Join-Path $info 'appinfo.ini') } catch { $ini = $null }
    }
    if ($ini) {
      $start = Get-IniValue $ini 'Control' 'Start'
      if (-not $start) { $start = Get-IniValue $ini 'Control' 'Start1' }
      $exe = if ($start) { Join-Path $d.FullName $start } else { '' }
      if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { continue }
      $name = Get-IniValue $ini 'Details' 'Name'
      if (-not $name) { $name = $d.Name }
      $name = ($name -replace '\s+Portable\b', '').Trim()
      $version = Get-IniValue $ini 'Version' 'DisplayVersion'
      $where = 'PortableApps' + $(if ($version) { " · $version" } else { '' })
      $image = $null
      foreach ($png in 'appicon_128.png', 'appicon_75.png', 'appicon_32.png') {
        $p = Join-Path $info $png
        if (Test-Path -LiteralPath $p) { $image = Get-ImageFromFile $p; if ($image) { break } }
      }
      if (-not $image) { $image = Get-ImageFromExe $exe }
      New-Tool $name $d.Name (Get-IniValue $ini 'Details' 'Description') $where $exe '' $d.FullName $image (Get-IniValue $ini 'Details' 'Category') ''
    } else {
      # No appinfo.ini (added by hand): list it if there's exactly one program at the top
      $exes = @(Get-ChildItem -LiteralPath $d.FullName -Filter *.exe -File -ErrorAction SilentlyContinue)
      if ($exes.Count -ne 1) { continue }
      New-Tool $d.Name $d.Name '' 'PortableApps' $exes[0].FullName '' $d.FullName (Get-ImageFromExe $exes[0].FullName) '' ''
    }
  }
}

$shell = $null
try { $shell = New-Object -ComObject WScript.Shell } catch { }
function Get-StartMenuTools {
  $roots = if ($StartMenu) { $StartMenu } else {
    @([Environment]::GetFolderPath('CommonPrograms'), [Environment]::GetFolderPath('Programs')) | Where-Object { $_ }
  }
  foreach ($r in $roots) {
    if (-not (Test-Path -LiteralPath $r)) { continue }
    foreach ($lnk in (Get-ChildItem -LiteralPath $r -Recurse -Filter *.lnk -File -ErrorAction SilentlyContinue)) {
      $rel = $lnk.FullName.Substring($r.TrimEnd('\').Length).TrimStart('\')
      $parts = $rel.Split('\')
      $folder = if ($parts.Count -gt 1) { $parts[0] } else { '' }
      $desc = ''; $target = ''
      if ($shell) {
        try { $s = $shell.CreateShortcut($lnk.FullName); $desc = $s.Description; $target = $s.TargetPath } catch { }
      }
      $image = Get-ImageFromExe $(if ($target -and (Test-Path -LiteralPath $target)) { $target } else { $lnk.FullName })
      $where = 'Lazarus PE' + $(if ($folder) { " · $folder" } else { '' })
      New-Tool $lnk.BaseName $lnk.BaseName $desc $where $lnk.FullName '' '' $image '' $folder
    }
  }
}

function Test-Hidden($t) {
  foreach ($h in $cfg.hide) {
    foreach ($v in $t.Id, $t.Title, $t.Folder) { if ($v -and $v.ToLower() -match $h) { return $true } }
  }
  $false
}

function Get-CategoryId($t) {
  $text = ('{0} {1} {2}' -f $t.Title, $t.Id, $t.Description).ToLower()
  foreach ($r in $cfg.rules) { if ($text -match $r.match) { return $r.category } }
  if ($t.PACategory -and $cfg.portableapps_categories.PSObject.Properties[$t.PACategory]) {
    return $cfg.portableapps_categories.($t.PACategory)
  }
  if ($t.Folder -and $cfg.startmenu_folders.PSObject.Properties[$t.Folder]) { return $cfg.startmenu_folders.($t.Folder) }
  ($cfg.categories | Where-Object { $_.PSObject.Properties['default'] -and $_.default } | Select-Object -First 1).id
}

function Get-AllTools {
  $seen = @{}
  $all = New-Object Collections.Generic.List[object]
  foreach ($t in @(Get-HelixApps) + @(Get-PortableApps) + @(Get-StartMenuTools)) {
    if (-not $t -or (Test-Hidden $t)) { continue }
    $key = ($t.Title.ToLower() -replace 'portable', '' -replace '[^a-z0-9]', '')
    if (-not $key -or $seen.ContainsKey($key)) { continue }
    $seen[$key] = $true
    $t.Category = Get-CategoryId $t
    if (-not $t.Image) {
      $c = $cfg.categories | Where-Object { $_.id -eq $t.Category } | Select-Object -First 1
      if ($c) { $t.Glyph = Get-Geometry $c.icon }
    }
    $all.Add($t)
  }
  , @($all | Sort-Object Title)
}

if ($ListTo) {
  $all = Get-AllTools   # the list comes back whole (not item by item): unpack it by assignment
  $found = @($all | ForEach-Object { [pscustomobject]@{ Title = $_.Title; Category = $_.Category; Where = $_.Where
                                        Icon = $(if ($_.Image) { $_.Image.PixelWidth } else { 0 }); Description = $_.Description
                                        IconType = $(if ($_.Image) { $_.Image.GetType().Name } else { '' }) } })
  [IO.File]::WriteAllText($ListTo, (ConvertTo-Json -InputObject $found -Depth 3), (New-Object Text.UTF8Encoding $false))
  exit 0
}

# ── Window ───────────────────────────────────────────────────────────────────
$xaml = Get-Content -Raw -Encoding UTF8 (Join-Path $here 'LazarusLauncher.xaml')
$win = [Windows.Markup.XamlReader]::Parse($xaml)
function N([string]$name) { $win.FindName($name) }
# The design is 1600x900 units; the bottom bar gets its 48 of them at the design's scale.
function Set-BarHeight([double]$w, [double]$h) {
  if ($w -gt 0 -and $h -gt 0) { (N 'Bar').Height = 48 * [Math]::Min($w / 1600, $h / 900) }
}
(N 'Root').Add_SizeChanged({ param($s, $e) Set-BarHeight $e.NewSize.Width $e.NewSize.Height })

$bg = Join-Path $here 'background.jpg'
if (Test-Path -LiteralPath $bg) { (N 'Backdrop').Source = Get-ImageFromFile $bg 0 }

function Add-Spaced($panel, [string[]]$lines, [double]$size, [string]$color) {
  foreach ($l in $lines) {
    $tb = New-Object Windows.Controls.TextBlock
    $tb.Text = (($l.ToCharArray() | ForEach-Object { if ($_ -eq ' ') { '  ' } else { $_ } }) -join ' ')
    $tb.FontSize = $size
    $tb.FontWeight = 'SemiBold'
    $tb.Foreground = New-Object Windows.Media.SolidColorBrush ([Windows.Media.ColorConverter]::ConvertFromString($color))
    $tb.Margin = '0,0,0,6'
    [void]$panel.Children.Add($tb)
  }
}
Add-Spaced (N 'Tagline') $cfg.tagline 14 '#2DE0C8'
Add-Spaced (N 'SideNote') $cfg.side_note 12.5 '#2DE0C8'
foreach ($q in $cfg.quote) {
  $tb = New-Object Windows.Controls.TextBlock
  $tb.Text = $q; $tb.FontSize = 14; $tb.FontStyle = 'Italic'; $tb.Margin = '0,0,0,4'
  $tb.Foreground = New-Object Windows.Media.SolidColorBrush ([Windows.Media.ColorConverter]::ConvertFromString('#9DB5B3'))
  [void](N 'Quote').Children.Add($tb)
}
(N 'TitleMain').Text = $cfg.title
(N 'TitleAccent').Text = $cfg.title_accent
(N 'Subtitle').Text = (($cfg.subtitle.ToCharArray() | ForEach-Object { if ($_ -eq ' ') { '  ' } else { $_ } }) -join ' ')
(N 'BarTitle').Text = "$($cfg.title) $($cfg.title_accent)"
(N 'BarPowered').Text = 'Powered by PhoenixPE  ·  Helix Boot'
(N 'QuickHeader').Text = 'Q U I C K   A C T I O N S'
foreach ($p in @(@('MinIcon', 'window-minimize'), @('CloseIcon', 'close'), @('SearchIcon', 'magnify'), @('WinIcon', 'microsoft-windows'),
                 @('StickIcon', 'usb-flash-drive'), @('InfoIcon', 'information-outline'))) {
  (N $p[0]).Data = Get-Geometry $p[1]
}
$drive = Split-Path -Qualifier $Root -ErrorAction SilentlyContinue
(N 'BarStick').Text = if ($drive) { "Helix Boot stick  $drive" } else { 'Helix Boot' }

# Categories
$chevron = Get-Geometry 'chevron-right'
$cats = @($cfg.categories | ForEach-Object {
    [pscustomobject]@{ Id = $_.id; Title = $_.title; Subtitle = $_.subtitle; Header = $_.header; Tagline = $_.tagline
                       Icon = Get-Geometry $_.icon; Chevron = $chevron }
  })
(N 'Categories').ItemsSource = $cats

$script:tools = Get-AllTools
function Show-Tools {
  $q = (N 'Search').Text.Trim()
  (N 'SearchHint').Visibility = if ($q) { 'Collapsed' } else { 'Visible' }
  $cat = (N 'Categories').SelectedItem
  if ($q) {
    $words = $q.ToLower().Split(' ', [StringSplitOptions]::RemoveEmptyEntries)
    $shown = @($script:tools | Where-Object {
        $t = ('{0} {1} {2}' -f $_.Title, $_.Description, $_.Where).ToLower()
        -not ($words | Where-Object { -not $t.Contains($_) })
      })
    (N 'ListHeader').Text = 'S E A R C H   R E S U L T S'
    (N 'ListTagline').Text = '{0} tool{1} match {2}{3}{4}' -f $shown.Count, $(if ($shown.Count -ne 1) { 's' }), [char]0x201C, $q, [char]0x201D
  } elseif ($cat) {
    $shown = @($script:tools | Where-Object { $_.Category -eq $cat.Id })
    (N 'ListHeader').Text = (($cat.Header.ToUpper().ToCharArray() | ForEach-Object { if ($_ -eq ' ') { ' ' } else { $_ } }) -join ' ')
    (N 'ListTagline').Text = $cat.Tagline
  } else { $shown = @() }
  (N 'Tools').ItemsSource = $shown
  (N 'ToolScroll').ScrollToTop()
  (N 'Empty').Visibility = if ($shown.Count) { 'Collapsed' } else { 'Visible' }
  (N 'Empty').Text = if ($q) { 'Nothing matches. Try part of a name, like "disk" or "crystal".' } else {
    'Nothing in this category on this stick yet. Tools you add in PortableApps show up here.' }
  (N 'Status').Text = "$($script:tools.Count) tools on this stick and in Lazarus PE"
}

function Start-Tool($t) {
  try {
    $p = @{ FilePath = $t.Run }
    if ($t.Arguments) { $p.ArgumentList = $t.Arguments }
    if ($t.WorkDir -and (Test-Path -LiteralPath $t.WorkDir)) { $p.WorkingDirectory = $t.WorkDir }
    Start-Process @p
    (N 'Status').Text = "Starting $($t.Title)…"
  } catch {
    (N 'Status').Text = "Couldn't start $($t.Title): $($_.Exception.Message)"
  }
}

function Invoke-Quick($q) {
  if ($q.PSObject.Properties['action'] -and $q.action) {
    $what = if ($q.action -eq 'reboot') { 'Restart' } else { 'Shut down' }
    $ok = [Windows.MessageBox]::Show($win, "$what this computer now?", 'Lazarus PE', 'YesNo', 'Question')
    if ($ok -ne 'Yes') { return }
    $wpeutil = Join-Path $env:SystemRoot 'System32\wpeutil.exe'
    if ($inPE -and (Test-Path $wpeutil)) {
      Start-Process $wpeutil $(if ($q.action -eq 'reboot') { 'reboot' } else { 'shutdown' })
    } else {
      Start-Process shutdown.exe $(if ($q.action -eq 'reboot') { '/r /t 0' } else { '/s /t 0' })
    }
    return
  }
  $run = $q.run.Replace('{stick}', $Root)
  $qargs = if ($q.PSObject.Properties['args']) { $q.args } else { '' }
  Start-Tool ([pscustomobject]@{ Title = $q.title; Run = $run; Arguments = $qargs; WorkDir = '' })
}
(N 'Quick').ItemsSource = @($cfg.quick | ForEach-Object {
    [pscustomobject]@{ Title = $_.title; Icon = Get-Geometry $_.icon; Q = $_ }
  })

# Status bar: network and clock
function Update-Bar {
  $now = Get-Date
  (N 'ClockTime').Text = $now.ToString('h:mm tt')
  (N 'ClockDate').Text = $now.ToString('MMM d, yyyy')
  $ips = @()
  try {
    foreach ($nic in [Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
      if ($nic.OperationalStatus -ne 'Up' -or $nic.NetworkInterfaceType -eq 'Loopback') { continue }
      foreach ($a in $nic.GetIPProperties().UnicastAddresses) {
        $ip = $a.Address
        if ($ip.AddressFamily -eq 'InterNetwork' -and -not $ip.ToString().StartsWith('169.254.')) { $ips += $ip.ToString() }
      }
    }
  } catch { }
  (N 'NetIcon').Data = Get-Geometry $(if ($ips) { 'lan-connect' } else { 'lan-disconnect' })
  (N 'NetText').Text = if ($ips) { $ips[0] } else { 'No network' }
}

function Get-SystemInfo {
  $out = New-Object Text.StringBuilder
  function Line([string]$k, [string]$v) { [void]$out.AppendLine(('{0,-13}{1}' -f $k, $v)) }
  try {
    $cs = Get-CimInstance Win32_ComputerSystem
    Line 'Computer' "$($cs.Manufacturer) $($cs.Model)".Trim()
    Line 'Memory' ('{0:N1} GB' -f ($cs.TotalPhysicalMemory / 1GB))
  } catch { Line 'Computer' '(unavailable)' }
  try { Get-CimInstance Win32_Processor | ForEach-Object { Line 'Processor' ("$($_.Name.Trim())  ($($_.NumberOfCores) cores)") } } catch { }
  $fw = ''
  try { $fw = @{ 1 = 'Legacy BIOS'; 2 = 'UEFI' }[[int](Get-ItemPropertyValue 'HKLM:\SYSTEM\CurrentControlSet\Control' PEFirmwareType)] } catch { }
  if ($fw) { Line 'Firmware' $fw }
  [void]$out.AppendLine()
  try {
    Get-CimInstance Win32_DiskDrive | Sort-Object Index | ForEach-Object {
      Line "Disk $($_.Index)" ('{0}  {1:N0} GB  {2}' -f $_.Model, ($_.Size / 1GB), $_.InterfaceType)
    }
  } catch { }
  [void]$out.AppendLine()
  foreach ($d in [IO.DriveInfo]::GetDrives()) {
    if (-not $d.IsReady) { continue }
    $mark = if (Test-Path -LiteralPath (Join-Path $d.RootDirectory 'Windows\System32\config\SYSTEM')) { '  ← Windows' } else { '' }
    Line $d.Name.TrimEnd('\') ('{0,-14} {1,-6} {2:N1} of {3:N1} GB free{4}' -f $d.VolumeLabel, $d.DriveFormat,
      ($d.AvailableFreeSpace / 1GB), ($d.TotalSize / 1GB), $mark)
  }
  [void]$out.AppendLine()
  try {
    foreach ($nic in [Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
      if ($nic.NetworkInterfaceType -eq 'Loopback') { continue }
      $ips = @($nic.GetIPProperties().UnicastAddresses | Where-Object { $_.Address.AddressFamily -eq 'InterNetwork' } |
               ForEach-Object { $_.Address.ToString() })
      Line 'Network' ('{0}  {1}  {2}' -f $nic.Description, $nic.OperationalStatus, ($ips -join ', '))
    }
  } catch { }
  $out.ToString()
}

# ── Wiring ───────────────────────────────────────────────────────────────────
(N 'Categories').Add_SelectionChanged({ if ((N 'Search').Text) { (N 'Search').Text = '' } else { Show-Tools } })
(N 'Search').Add_TextChanged({ Show-Tools })
(N 'Search').Add_KeyDown({
    param($s, $e)
    if ($e.Key -eq 'Return') { $first = @((N 'Tools').ItemsSource) | Select-Object -First 1; if ($first) { Start-Tool $first } }
    if ($e.Key -eq 'Escape') { (N 'Search').Text = '' }
  })
(N 'Tools').AddHandler([Windows.Controls.Primitives.ButtonBase]::ClickEvent, [Windows.RoutedEventHandler]{
    param($s, $e)
    $t = $e.OriginalSource.Tag
    if ($t) { Start-Tool $t }
  })
(N 'Tools').Add_MouseDoubleClick({
    param($s, $e)
    $t = $e.OriginalSource.DataContext
    if ($t -and $t.PSObject.Properties['Run']) { Start-Tool $t }
  })
(N 'Quick').AddHandler([Windows.Controls.Primitives.ButtonBase]::ClickEvent, [Windows.RoutedEventHandler]{
    param($s, $e)
    $b = $e.OriginalSource
    if ($b.Tag) { Invoke-Quick $b.Tag.Q }
  })
(N 'InfoButton').Add_Click({ (N 'InfoText').Text = Get-SystemInfo; (N 'InfoPanel').Visibility = 'Visible' })
(N 'InfoClose').Add_Click({ (N 'InfoPanel').Visibility = 'Collapsed' })
(N 'MinButton').Add_Click({ $win.WindowState = 'Minimized' })
(N 'CloseButton').Add_Click({ $win.Close() })
# Typing anywhere searches
$win.Add_PreviewTextInput({
    param($s, $e)
    if (-not (N 'Search').IsKeyboardFocused -and $e.Text -match '\S') {
      (N 'Search').Focus() | Out-Null
      (N 'Search').Text += $e.Text
      (N 'Search').CaretIndex = (N 'Search').Text.Length
      $e.Handled = $true
    }
  })

$first = $cats | Where-Object { $_.Id -eq $Category } | Select-Object -First 1
(N 'Categories').SelectedItem = if ($first) { $first } else { $cats[0] }
if ($SearchText) { (N 'Search').Text = $SearchText }
Show-Tools
Update-Bar

# ── Screenshot mode (testing): render at a fixed size, save, exit ────────────
if ($Screenshot) {
  if ($ShowInfo) { (N 'InfoText').Text = Get-SystemInfo; (N 'InfoPanel').Visibility = 'Visible' }
  # No window: Windows won't make one bigger than the screen. The layout is taken out of it
  # (its fonts and colours are set on the layout itself), sized, bound, laid out and drawn.
  $content = $win.Content
  $win.Content = $null
  $size = New-Object Windows.Size $Width, $Height
  Set-BarHeight $Width $Height
  for ($i = 0; $i -lt 3; $i++) {   # data binding and item templates settle over a few passes
    $content.Measure($size)
    $content.Arrange((New-Object Windows.Rect $size))
    $content.UpdateLayout()
    $content.Dispatcher.Invoke([action]{ }, [Windows.Threading.DispatcherPriority]::Background)
  }
  $rtb = New-Object Windows.Media.Imaging.RenderTargetBitmap $Width, $Height, 96, 96, ([Windows.Media.PixelFormats]::Pbgra32)
  $rtb.Render($content)
  $enc = New-Object Windows.Media.Imaging.PngBitmapEncoder
  $enc.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($rtb))
  $fs = [IO.File]::Create($Screenshot)
  try { $enc.Save($fs) } finally { $fs.Close() }
  exit 0
}

# ── Normal start: the whole screen, over the taskbar ─────────────────────────
# A borderless maximized window covers the taskbar; it comes back as soon as you switch to
# another program (the launcher isn't kept on top, so what you start opens in front of it).
# "fullscreen": false in launcher.json keeps the launcher above the taskbar instead.
$win.WindowStartupLocation = 'Manual'
$fullscreen = -not ($cfg.PSObject.Properties['fullscreen'] -and $cfg.fullscreen -eq $false)
if ($fullscreen) {
  $win.Left = 0; $win.Top = 0
  $win.Width = [Windows.SystemParameters]::PrimaryScreenWidth
  $win.Height = [Windows.SystemParameters]::PrimaryScreenHeight
  $win.WindowState = 'Maximized'
} else {
  $area = [Windows.SystemParameters]::WorkArea
  $win.Left = $area.Left; $win.Top = $area.Top; $win.Width = $area.Width; $win.Height = $area.Height
}

$timer = New-Object Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromSeconds(15)
$timer.Add_Tick({ Update-Bar })
$timer.Start()
# PhoenixPE fills the Start menu as the PE starts, maybe after this opens: look again shortly.
$later = New-Object Windows.Threading.DispatcherTimer
$later.Interval = [TimeSpan]::FromSeconds(8)
$script:rescans = 0
$later.Add_Tick({
    $script:rescans++
    if ($script:rescans -ge 3) { $later.Stop() }
    $again = Get-AllTools
    if ($again.Count -ne $script:tools.Count) { $script:tools = $again; Show-Tools }
  })
$later.Start()
[void]$win.ShowDialog()
