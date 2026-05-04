@echo off
CHCP 65001 >NUL
setlocal

echo ================================
echo   START NEWS RECOMMEND SYSTEM
echo ================================

cd /d "%~dp0"

echo.
echo [1] Starting Docker services...
docker-compose up -d
timeout /t 8 >NUL

echo.
echo [2] Starting Python services...

set "CONDA_BAT=C:\Users\kiman\miniconda3\condabin\conda.bat"
set "ENV_NAME=news_realtime"
set "ROOT_DIR=%~dp0"

start "Topic Consumer" cmd /k ""%CONDA_BAT%" activate %ENV_NAME% && cd /d "%ROOT_DIR%" && python -m consumer.topic_consumer"

timeout /t 4 >NUL

start "Click Tracking Backend" cmd /k ""%CONDA_BAT%" activate %ENV_NAME% && cd /d "%ROOT_DIR%" && python -m uvicorn dashboard.backend_click:app --reload --host 127.0.0.1 --port 8000"

timeout /t 3 >NUL

start "Dashboard" cmd /k ""%CONDA_BAT%" activate %ENV_NAME% && cd /d "%ROOT_DIR%" && python -m streamlit run dashboard/app.py"

timeout /t 3 >NUL

start "Crawler" cmd /k ""%CONDA_BAT%" activate %ENV_NAME% && cd /d "%ROOT_DIR%crawl_data" && python run_all_spiders.py"



===== Optional: Evaluation =====

start "Evaluation" cmd /k ""%CONDA_BAT%" activate %ENV_NAME% && cd /d "%ROOT_DIR%" && python -m evaluation.evaluate_recommender"
echo.
echo All services started.
pause