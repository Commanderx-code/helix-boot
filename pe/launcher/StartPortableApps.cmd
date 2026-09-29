@echo off
rem Helix Boot - start the PortableApps.com Platform from the USB, if it's there.
rem Lazarus PE runs this at startup; it also works from plain Windows. If the stick
rem has Apps\LazarusStartup.cmd, that runs instead.
setlocal EnableDelayedExpansion
rem The USB can take a few seconds to get a drive letter after the desktop loads.
for /l %%T in (1,1,15) do (
  for %%D in (C D E F G H I J K L M N O P Q R S T U V W Y Z) do (
    set "TAG="
    if exist "%%D:\helix-boot.tag" set "TAG=1"
    if exist "%%D:\commander-rescue.tag" set "TAG=1"
    rem The stick's own startup script wins: it changes with refresh.sh, no PE rebuild
    if defined TAG if exist "%%D:\Apps\LazarusStartup.cmd" (
      call "%%D:\Apps\LazarusStartup.cmd" %%D:
      exit /b 0
    )
    if defined TAG if exist "%%D:\Start.exe" (
      start "" /d "%%D:\" "%%D:\Start.exe"
      exit /b 0
    )
  )
  ping -n 3 127.0.0.1 >nul
)
exit /b 1
