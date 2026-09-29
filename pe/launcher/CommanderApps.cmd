@echo off
rem The launcher's name before the rename to Helix Boot. Lazarus PE builds from then
rem still start this one, so it hands over to HelixApps.cmd next to it.
"%~dp0HelixApps.cmd"
