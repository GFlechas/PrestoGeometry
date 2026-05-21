@echo off
:: PrestoGeometry — Annotation Tool
::
:: Launches the interactive building face annotation tool directly.
:: For the guided workflow, use launch.bat instead.
::
:: Run install.bat first if you have not set up the environment yet.
::
:: Usage:
::   annotate.bat [building_name] [--photos-dir PATH] [--faces N]
::
:: Examples:
::   annotate.bat
::   annotate.bat MyBuilding --photos-dir "C:\Photos\MyBuilding"
::   annotate.bat MyBuilding --faces 5

if not exist "%~dp0_env.bat" (
    echo.
    echo  ERROR: _env.bat not found.
    echo  Please run install.bat first to set up the Python environment.
    echo.
    pause
    exit /b 1
)

call "%~dp0_env.bat"
"%PRESTO_PYTHON%" "%~dp0tools\annotate_building.py" %*
