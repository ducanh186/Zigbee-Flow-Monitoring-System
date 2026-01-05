@echo off
setlocal enabledelayedexpansion
REM Script to run Zigbee Flow Monitoring Dashboard
echo Starting Zigbee Flow Monitoring Dashboard...
echo.
echo Closing any existing Streamlit/Python processes that may be using COM x ..
echo.

REM Kill streamlit.exe if running
taskkill /F /IM streamlit.exe >nul 2>&1

REM Kill python processes running dashboard, gateway, or streamlit
wmic process where "name='python.exe' and (CommandLine like '%%dashboard%%' or CommandLine like '%%streamlit%%' or CommandLine like '%%gateway%%' or CommandLine like '%%pc_gateway%%')" delete /nointeractive >nul 2>&1

REM Alternative: Kill all python.exe processes (uncomment if above doesn't work)
REM for /f "tokens=1" %%p in ('wmic process where name="python.exe" get processid /format:list ^| findstr "ProcessId"') do (
REM     set "pid=%%p"
REM     taskkill /pid !pid:*=! /f >nul 2>&1
REM )

echo Waiting for COM7 to be released...
timeout /t 3 /nobreak >nul
echo.
echo Starting dashboard...
echo.

cd /d "%~dp0Dashboard_Coordinator"
streamlit run dashboard.py --server.address 0.0.0.0 --server.port 8502

pause
