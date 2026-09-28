@echo off
rem Commander Rescue - portable app launcher for WinPE.
rem Finds the USB (by commander-rescue.tag), reads Apps\apps.txt and offers a menu.
rem Works in Lazarus PE, Hiren's, or plain Windows.
setlocal EnableDelayedExpansion
title Commander Rescue - Apps

set "CR="
for %%D in (C D E F G H I J K L M N O P Q R S T U V W Y Z) do (
  if not defined CR if exist "%%D:\commander-rescue.tag" set "CR=%%D:"
)
if not defined CR (
  echo.
  echo  Commander Rescue USB not found. Plug it in, wait a few seconds, and try again.
  echo.
  pause
  exit /b 1
)
set "APPS=%CR%\Apps"
if not exist "%APPS%\apps.txt" (
  echo  %APPS%\apps.txt is missing - run refresh.sh on your Linux box.
  pause
  exit /b 1
)

:menu
cls
echo.
echo   Commander Rescue - portable apps       USB: %CR%
echo   ---------------------------------------------------
set n=0
for /f "usebackq tokens=1,2 delims=|" %%A in ("%APPS%\apps.txt") do (
  set /a n+=1
  set "exe!n!=%%B"
  if !n! lss 10 (echo     !n!^)  %%A) else (echo    !n!^)  %%A)
)
echo.
echo     o^)  Open the Apps folder
echo     q^)  Quit
echo.
set "pick="
set /p "pick=  Choose: "
if not defined pick goto menu
if /i "%pick%"=="q" exit /b 0
if /i "%pick%"=="o" (
  start "" explorer.exe "%APPS%"
  goto menu
)
echo %pick%| findstr /r "^[0-9][0-9]*$" >nul || goto menu
if not defined exe%pick% goto menu
set "target=%APPS%\!exe%pick%!"
if not exist "!target!" (
  echo   Not found: !target!
  pause
  goto menu
)
rem A .ps1 would open in Notepad, so scripts go to PowerShell
for %%F in ("!target!") do (
  if /i "%%~xF"==".ps1" (
    start "" /d "%%~dpF" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%%~fF"
  ) else (
    start "" /d "%%~dpF" "%%~fF"
  )
)
goto menu
