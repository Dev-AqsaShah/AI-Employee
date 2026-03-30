@echo off
:: uninstall_service.bat — Removes the AI Employee auto-start and stops all processes
setlocal
set TASK_NAME=AIEmployee-Orchestrator
set REG_PATH=HKCU\Software\Microsoft\Windows\CurrentVersion\Run

echo Stopping orchestrator and all watcher processes...
taskkill /f /im python.exe >nul 2>&1

echo Removing auto-start registry entry...
reg delete "%REG_PATH%" /v "%TASK_NAME%" /f >nul 2>&1

echo.
echo [OK] AI Employee auto-start removed.
echo     All processes stopped.
echo.
pause
endlocal
