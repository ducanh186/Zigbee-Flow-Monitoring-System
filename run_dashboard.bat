@echo off
REM Script to run Zigbee Flow Monitoring Dashboard
echo Starting Zigbee Flow Monitoring Dashboard...
echo.
echo Closing any existing Streamlit/Python processes that may be using COM7...
echo.

REM Kill existing streamlit processes
taskkill /F /IM streamlit.exe >nul 2>&1
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *streamlit*" >nul 2>&1

REM Kill any python process with dashboard or gateway in command line
for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| findstr /I "PID"') do (
    wmic process where "ProcessId=%%i and CommandLine like '%%dashboard%%' or CommandLine like '%%gateway%%'" delete >nul 2>&1
)

echo Waiting for ports to be released...
timeout /t 2 /nobreak >nul
echo.
echo Starting dashboard...
echo.

cd /d "%~dp0"
streamlit run dashboard.py

pause
