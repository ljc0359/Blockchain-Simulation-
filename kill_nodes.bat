@echo off
for %%p in (8888, 8889, 8890, 8891, 8892. 8893) do (
    for /f "tokens=5" %%i in ('netstat -aon ^| findstr :%%p ^| findstr LISTENING') do (
        echo Killing process on port %%p with PID %%i
        taskkill /PID %%i /F
    )
)
