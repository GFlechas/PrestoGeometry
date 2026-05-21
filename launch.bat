@echo off
:: PrestoGeometry Launcher — main entry point
::
:: Opens the step-by-step graphical launcher where you can select a photos
:: folder and start the Annotation or Assembly tools.
::
:: Run install.bat first if you have not set up the environment yet.
::
:: Usage:
::   launch.bat

if not exist "%~dp0_env.bat" (
    echo.
    echo  ERROR: _env.bat not found.
    echo  Please run install.bat first to set up the Python environment.
    echo.
    pause
    exit /b 1
)

call "%~dp0_env.bat"

if not defined PRESTO_PYTHON (
    echo.
    echo  ERROR: PRESTO_PYTHON is not set in _env.bat.
    echo  Please re-run install.bat to regenerate _env.bat.
    echo.
    pause
    exit /b 1
)

"%PRESTO_PYTHON%" "%~dp0tools\launcher.py" %*
