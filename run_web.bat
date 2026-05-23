@echo off
echo ========================================
echo Quality Inspection Dashboard (Web)
echo ========================================
echo.
call e:\99IS\B1F2\.venv\Scripts\activate.bat
echo Starting web server at http://localhost:8080
flet run --web --host localhost --port 8080 main.py
