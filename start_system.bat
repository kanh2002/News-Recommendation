@echo off
CHCP 65001 >NUL
echo ===================================================
echo     KHỞI ĐỘNG HỆ THỐNG REALTIME NEWS TREND
echo ===================================================
echo.
echo Đang mở các tiến trình chạy song song...
echo (Vui lòng đảm bảo Docker cho Kafka và MongoDB đang chạy)
echo.


cd /d "%~dp0"



:: 1. Khởi động News Consumer
echo Bật News Consumer...
start "News Consumer" cmd /k "python consumer\news_consumer.py"

:: 2. Khởi động Topic Consumer
echo Bật Topic Consumer...
start "Topic Consumer" cmd /k "python consumer\topic_consumer.py"

:: Đợi 3 giây để Consumer kịp khởi động và kết nối Kafka
timeout /t 3 /nobreak >NUL

:: 3. Khởi động Dashboard 
echo Bật Dashboard Streamlit...
start "Streamlit Dashboard" cmd /k "streamlit run dashboard\app.py"

:: 4. crawl data (Realtime)

echo Kích hoạt Web Spiders để cào dữ liệu thời gian thực...

@REM :: 
@REM start "Push Old Data" cmd /k "python consumer\push_old_data.py"

start "Crawl Spiders" cmd /k "cd crawl_data && python run_all_spiders.py"

pause
