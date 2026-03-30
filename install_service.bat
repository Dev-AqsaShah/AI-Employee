@echo off
:: install_service.bat
:: Registers the AI Employee Orchestrator to auto-start at Windows login.
:: Uses HKCU registry key — no Administrator required.
::
:: Run this ONCE to enable 24/7 auto-start.

setlocal
set TASK_NAME=AIEmployee-Orchestrator
set BASE_DIR=D:\AI-Employee
set VBS=%BASE_DIR%\run_orchestrator_hidden.vbs
set REG_PATH=HKCU\Software\Microsoft\Windows\CurrentVersion\Run

echo.
echo ============================================================
echo   AI Employee — Installing Auto-Start
echo ============================================================
echo.

:: Register in HKCU Run key (runs at login, no admin needed)
reg add "%REG_PATH%" /v "%TASK_NAME%" /t REG_SZ /d "wscript.exe \"%VBS%\"" /f

if %errorlevel% == 0 (
    echo.
    echo  [OK] Auto-start registered.
    echo  [OK] Orchestrator will launch silently every time you log in.
    echo  [OK] No terminal window will appear.
    echo.
    echo  To start RIGHT NOW:
    echo    wscript.exe "%VBS%"
    echo.
    echo  To stop auto-start: run uninstall_service.bat
    echo.
) else (
    echo.
    echo  [ERROR] Failed to register. Try again.
    echo.
)

pause
endlocal
