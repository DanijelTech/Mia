@echo off
rem Mia GPU STT server (Windows). Copy to run-stt.bat, fill in the token.
rem Auto-start at logon: create MiaSTT.vbs in shell:startup containing:
rem   CreateObject("Wscript.Shell").Run "C:\path\to\run-stt.bat", 0, False
set MIA_STT_TOKEN=YOUR_MIA_HUD_TOKEN
set MIA_STT_MODEL=large-v3-turbo
set MIA_STT_LANGUAGE=sl
cd /d %~dp0
.venv\Scripts\python.exe stt_server.py >> stt_server.log 2>&1
