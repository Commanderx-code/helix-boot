@echo off
rem Commander Rescue - what Lazarus PE does once its desktop is up.
rem Lives on the stick (Apps\) and is kept current by refresh.sh: the PE's built-in
rem startup helper hands over to it, so changing this needs no PE rebuild.
rem %1 is the stick's drive, e.g. E:
setlocal
set "CR=%~1"
if not defined CR set "CR=%~d0"

rem The PortableApps.com Platform menu
if exist "%CR%\Start.exe" start "" /d "%CR%\" "%CR%\Start.exe"
exit /b 0
