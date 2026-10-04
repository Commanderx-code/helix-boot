@echo off
rem Helix Boot - what Lazarus PE runs when its desktop loads: find the stick, then run its
rem Apps\LazarusStartup.cmd (the Lazarus launcher), or else its PortableApps.com menu.
rem Also works from plain Windows.
rem
rem Whatever this picks runs as SYSTEM, and the PC being repaired can plant a tag file on
rem its own disks, so the stick is found by FindStick.ps1 (a USB/SD disk whose tag is a
rem file and that holds no Windows). Discovery requires bus information.
setlocal EnableDelayedExpansion
set "FIND=%~dp0FindStick.ps1"
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "USEPS="
if exist "%FIND%" if exist "%PS%" set "USEPS=1"
if not defined USEPS (
  echo Cannot verify the USB bus. Open the trusted stick manually to launch its apps.
  exit /b 1
)
rem The USB can take a few seconds to get a drive letter after the desktop loads.
for /l %%T in (1,1,15) do (
  set "CR="
  if defined USEPS (
    for /f "delims=" %%S in ('%PS% -NoProfile -ExecutionPolicy Bypass -File "%FIND%"') do set "CR=%%S"
  )
  if defined CR (
    rem The stick's own startup script wins: it changes with refresh.sh, no PE rebuild
    if exist "!CR!\Apps\LazarusStartup.cmd" (
      call "!CR!\Apps\LazarusStartup.cmd" !CR!
      exit /b 0
    )
    if exist "!CR!\Start.exe" (
      start "" /d "!CR!\" "!CR!\Start.exe"
      exit /b 0
    )
  )
  ping -n 3 127.0.0.1 >nul
)
exit /b 1
