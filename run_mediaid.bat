@echo off
title MediAid
cd /d "%~dp0"
echo.
echo  ================= MediAid =================
echo.

rem ---- 1. Python installed? ----
where python >nul 2>nul
if errorlevel 1 goto nopython

rem ---- 2. .env with a real Groq key? ----
if not exist ".env" goto makeenv
findstr /c:"gsk_your_key_here" ".env" >nul
if not errorlevel 1 goto placeholder

rem ---- 3. Packages ----
echo  [1/3] Checking packages... first run takes a few minutes
python -m pip install -q -r requirements.txt
if errorlevel 1 goto pipfail

rem ---- 4. Groq key and model work? ----
echo  [2/3] Checking Groq key and model...
python check_groq.py
if errorlevel 1 goto groqfail

rem ---- 5. Stop any old MediAid still running on port 8000 ----
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
  echo  Stopping an old MediAid that was still running...
  taskkill /PID %%a /F >nul 2>nul
)

rem ---- 6. Start server and open browser ----
echo.
echo  [3/3] MediAid v10.2 is running at http://localhost:8000
echo        Keep this window open. Close it to stop MediAid.
echo.
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8000"
python -m uvicorn app.api:app --port 8000
pause
exit /b 0

:nopython
echo  Python was not found.
echo  Install it from https://www.python.org/downloads and tick "Add Python to PATH" during setup.
pause
exit /b 1

:makeenv
copy ".env.example" ".env" >nul
echo  Created the .env file. Notepad will open now:
echo  paste your Groq key after GROQ_API_KEY=, save, close Notepad, and run this file again.
notepad ".env"
pause
exit /b 1

:placeholder
echo  Your .env still has the example key. Notepad will open now:
echo  paste your real Groq key after GROQ_API_KEY=, save, and run this file again.
notepad ".env"
pause
exit /b 1

:pipfail
echo  Installing packages failed. Check your internet connection and read the error above.
pause
exit /b 1

:groqfail
echo.
echo  The Groq check failed. Read the error above:
echo   - "model_not_found": set GROQ_MODEL=openai/gpt-oss-120b in .env
echo   - "invalid_api_key" or 401: the key in .env is wrong
echo  Notepad will open .env now. Fix it, save, and run this file again.
notepad ".env"
pause
exit /b 1
