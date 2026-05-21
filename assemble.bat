@echo off
:: PrestoGeometry — Assembly Tool
::
:: Launches the interactive geometry assembly and editor directly.
:: For the guided workflow, use launch.bat instead.
::
:: Run install.bat first if you have not set up the environment yet.
::
:: Usage:
::   assemble.bat [building_name] [--widths F0=13,F1=47,...]
::
:: Examples:
::   assemble.bat
::   assemble.bat MyBuilding
::   assemble.bat MyBuilding --widths F0=13,F1=47,F2=15,F3=40,F4=10

if not exist "%~dp0_env.bat" (
    echo.
    echo  ERROR: _env.bat not found.
    echo  Please run install.bat first to set up the Python environment.
    echo.
    pause
    exit /b 1
)

call "%~dp0_env.bat"
"%PRESTO_PYTHON%" "%~dp0tools\assemble_geometry.py" %*
