' run_orchestrator_hidden.vbs
' Launches the AI Employee Orchestrator without showing a terminal window.
' Used by Windows auto-start (HKCU\Run) for 24/7 background operation.

Dim WshShell, fso, baseDir, python, logFile, cmd

Set WshShell = CreateObject("WScript.Shell")
Set fso      = CreateObject("Scripting.FileSystemObject")

' ── Paths ────────────────────────────────────────────────────────────────────
baseDir = "D:\AI-Employee"
python  = "C:\Users\hp\AppData\Local\Programs\Python\Python312\python.exe"
logFile = baseDir & "\AI_Employee_Vault\Logs\orchestrator_stdout.log"

' ── Run silently ─────────────────────────────────────────────────────────────
' WindowStyle 0 = hidden, bWaitOnReturn False = don't block

' Start orchestrator (all watchers)
cmd = "cmd /c cd /d """ & baseDir & """ && """ & python & """ orchestrator.py >> """ & logFile & """ 2>&1"
WshShell.Run cmd, 0, False

' Start dashboard (Flask on port 5000)
Dim dashLog
dashLog = baseDir & "\AI_Employee_Vault\Logs\dashboard_stdout.log"
Dim dashCmd
dashCmd = "cmd /c cd /d """ & baseDir & """ && """ & python & """ dashboard\app.py >> """ & dashLog & """ 2>&1"
WshShell.Run dashCmd, 0, False

Set WshShell = Nothing
Set fso      = Nothing
