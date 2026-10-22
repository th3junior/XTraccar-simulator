@echo off
cd /d "%~dp0"
echo Parando instancias antigas na porta 8081...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8081 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
timeout /t 2 /nobreak >nul
echo Iniciando XTraccar Simulator em http://127.0.0.1:8081
".venv\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port 8081
pause
