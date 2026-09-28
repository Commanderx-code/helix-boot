@echo off
rem Commander Rescue - start the PortableApps.com Platform from the USB, if it's there.
rem Lazarus PE runs this at startup; it also works from plain Windows.
setlocal EnableDelayedExpansion
rem The USB can take a few seconds to get a drive letter after the desktop loads.
for /l %%T in (1,1,15) do (
  for %%D in (C D E F G H I J K L M N O P Q R S T U V W Y Z) do (
    if exist "%%D:\commander-rescue.tag" if exist "%%D:\Start.exe" (
      start "" /d "%%D:\" "%%D:\Start.exe"
      exit /b 0
    )
  )
  ping -n 3 127.0.0.1 >nul
)
exit /b 1
