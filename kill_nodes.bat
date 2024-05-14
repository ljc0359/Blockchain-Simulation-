@echo off
for %%p in (8000, 8001, 8002, 8003) do (
    for /f "tokens=5" %%i in ('netstat -aon ^| findstr :%%p ^| findstr LISTENING') do (
        echo Killing process on port %%p with PID %%i
        taskkill /PID %%i /F
    )
)
