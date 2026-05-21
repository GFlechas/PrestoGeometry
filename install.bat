@echo off
setlocal enabledelayedexpansion

:: ─────────────────────────────────────────────────────────────────────────────
::  PrestoGeometry  —  Installation Script
::
::  Three setup paths:
::    1. Conda  (Miniconda / Anaconda) — creates a new named environment
::    2. Python venv               — creates a .venv folder in this project
::    3. Existing environment      — point to any Python you already have
::
::  All paths write _env.bat, which records the full path to python.exe so
::  launch.bat / annotate.bat / assemble.bat work without hardcoded paths.
::  _env.bat is machine-specific and git-ignored; re-run this script if you
::  move the repo or switch environments.
:: ─────────────────────────────────────────────────────────────────────────────

set REPO_DIR=%~dp0
:: Strip trailing backslash
if "!REPO_DIR:~-1!"=="\" set REPO_DIR=!REPO_DIR:~0,-1!

title PrestoGeometry Installer

echo.
echo ============================================================
echo   PrestoGeometry  ^|  Installation Setup
echo ============================================================
echo.
echo   This installer sets up a Python environment and writes
echo   _env.bat so the launcher knows which Python to use.
echo.
echo   Prerequisites:
echo     - Internet connection (to download packages on first run)
echo     - Conda OR Python 3.10+ already installed on this machine
echo.

:: ─────────────────────────────────────────────────────────────────────────────
:ask_type
echo   Which setup option would you like?
echo.
echo     [1] Conda          — create a new Conda environment
echo                          (Miniconda or Anaconda must be installed)
echo.
echo     [2] Python venv    — create a project-local .venv folder
echo                          (uses your system Python 3.10+)
echo.
echo     [3] Use existing   — point to a Python / Conda env you already have
echo                          (skips environment creation; just registers it)
echo.
set /p INSTALL_TYPE="  Enter 1, 2, or 3: "
echo.

if "!INSTALL_TYPE!"=="1" goto :conda_path
if "!INSTALL_TYPE!"=="2" goto :venv_path
if "!INSTALL_TYPE!"=="3" goto :existing_path
echo   Invalid choice.  Please enter 1, 2, or 3.
echo.
goto :ask_type


:: =============================================================================
::  PATH 1 — CONDA (create new environment)
:: =============================================================================
:conda_path

echo ─────────────────────────────────────────────────────────────
echo   Conda  —  new environment
echo ─────────────────────────────────────────────────────────────
echo.

:: ── Locate conda installation ─────────────────────────────────────────────────
set CONDA_ROOT=

for %%D in (
    "%USERPROFILE%\miniconda3"
    "%USERPROFILE%\anaconda3"
    "%USERPROFILE%\Miniconda3"
    "%USERPROFILE%\Anaconda3"
    "%USERPROFILE%\mambaforge"
    "%USERPROFILE%\Mambaforge"
    "%USERPROFILE%\miniforge3"
    "%USERPROFILE%\Miniforge3"
    "%LOCALAPPDATA%\miniconda3"
    "%LOCALAPPDATA%\Miniconda3"
    "C:\miniconda3"
    "C:\Miniconda3"
    "C:\ProgramData\miniconda3"
    "C:\ProgramData\Miniconda3"
    "C:\ProgramData\anaconda3"
    "C:\ProgramData\Anaconda3"
) do (
    if not defined CONDA_ROOT (
        if exist "%%~D\Scripts\conda.exe" (
            set CONDA_ROOT=%%~D
        )
    )
)

:: Fall back to PATH resolution
if not defined CONDA_ROOT (
    for /f "delims=" %%F in ('where conda.exe 2^>nul') do (
        if not defined CONDA_ROOT (
            set _CPATH=%%~dpF
            if "!_CPATH:~-1!"=="\" set _CPATH=!_CPATH:~0,-1!
            for %%P in ("!_CPATH!") do set CONDA_ROOT=%%~dpP
            if "!CONDA_ROOT:~-1!"=="\" set CONDA_ROOT=!CONDA_ROOT:~0,-1!
        )
    )
)

if defined CONDA_ROOT (
    echo   Found Conda at: !CONDA_ROOT!
    set /p _CONFIRM="  Use this location? [Y/n]: "
    if /i "!_CONFIRM!"=="n" set CONDA_ROOT=
    echo.
)

if not defined CONDA_ROOT (
    echo   Conda was not found automatically.
    echo   Enter the path to your Miniconda, Anaconda, or Mambaforge folder.
    echo   Example:  C:\Users\YourName\miniconda3
    echo.
    set /p CONDA_ROOT="  Conda root path: "
    echo.
    if not exist "!CONDA_ROOT!\Scripts\conda.exe" (
        echo   ERROR: conda.exe not found at !CONDA_ROOT!\Scripts\conda.exe
        echo   Check the path and try again.
        echo.
        goto :conda_path
    )
)

set CONDA_EXE=!CONDA_ROOT!\Scripts\conda.exe

:: ── Environment name ──────────────────────────────────────────────────────────
set ENV_NAME=presto_geometry
set /p _ENVNAME="  New environment name [presto_geometry]: "
if not "!_ENVNAME!"=="" set ENV_NAME=!_ENVNAME!
echo.

:: ── Existing env check ────────────────────────────────────────────────────────
set ENV_EXISTS=0
if exist "!CONDA_ROOT!\envs\!ENV_NAME!\python.exe" set ENV_EXISTS=1

if "!ENV_EXISTS!"=="1" (
    echo   Environment '!ENV_NAME!' already exists.
    set /p _REUSE="  Re-use it and just update packages? [Y/n]: "
    echo.
    if /i "!_REUSE!"=="n" (
        echo   Removing existing environment...
        "!CONDA_EXE!" env remove -n "!ENV_NAME!" -y
        set ENV_EXISTS=0
    )
)

:: ── Create ────────────────────────────────────────────────────────────────────
if "!ENV_EXISTS!"=="0" (
    echo   Creating Conda environment '!ENV_NAME!' from environment.yml ...
    echo   (This downloads packages — may take a few minutes on first run.)
    echo.
    "!CONDA_EXE!" env create -f "!REPO_DIR!\environment.yml" -n "!ENV_NAME!" -y
    if errorlevel 1 (
        echo.
        echo   WARNING: conda env create reported an error.
        echo   Trying fallback: bare Python 3.11 env + pip install...
        echo.
        "!CONDA_EXE!" create -n "!ENV_NAME!" python=3.11 pip -y
        if errorlevel 1 (
            echo   ERROR: Could not create the Conda environment.
            pause
            exit /b 1
        )
        goto :conda_pip_install
    )
    goto :conda_find_python
)

:: ── Update existing ───────────────────────────────────────────────────────────
echo   Updating packages in '!ENV_NAME!' ...
"!CONDA_EXE!" env update -n "!ENV_NAME!" -f "!REPO_DIR!\environment.yml" --prune
if errorlevel 1 (
    echo   WARNING: conda env update reported an error.  Continuing anyway.
)

:conda_pip_install
echo.
echo   Installing PrestoGeometry (pip install -e .) ...
"!CONDA_EXE!" run -n "!ENV_NAME!" pip install -e "!REPO_DIR!" --quiet
if errorlevel 1 (
    echo   ERROR: pip install failed.
    pause
    exit /b 1
)

:conda_find_python
set PYTHON_EXE=!CONDA_ROOT!\envs\!ENV_NAME!\python.exe
if not exist "!PYTHON_EXE!" (
    echo.
    echo   WARNING: python.exe not found at the expected location:
    echo     !PYTHON_EXE!
    echo.
    set /p PYTHON_EXE="  Enter the full path to python.exe in '!ENV_NAME!': "
    if not exist "!PYTHON_EXE!" (
        echo   ERROR: File not found.  Aborting.
        pause
        exit /b 1
    )
)

set INSTALL_NOTE=Conda environment '!ENV_NAME!' at !CONDA_ROOT!
goto :write_env


:: =============================================================================
::  PATH 2 — PYTHON VENV (create project-local .venv)
:: =============================================================================
:venv_path

echo ─────────────────────────────────────────────────────────────
echo   Python venv  —  project-local .venv
echo ─────────────────────────────────────────────────────────────
echo.
echo   A '.venv' folder will be created inside this project directory.
echo   It will not affect your system Python or any other projects.
echo.

:: ── Find base Python ──────────────────────────────────────────────────────────
set BASE_PYTHON=

for %%P in (python.exe python3.exe) do (
    if not defined BASE_PYTHON (
        for /f "delims=" %%F in ('where %%P 2^>nul') do (
            if not defined BASE_PYTHON set BASE_PYTHON=%%F
        )
    )
)

if defined BASE_PYTHON (
    echo   Found Python at: !BASE_PYTHON!
    for /f "tokens=2 delims= " %%V in ('"!BASE_PYTHON!" --version 2^>^&1') do set PY_VER=%%V
    echo   Version: !PY_VER!
    set /p _CONFIRM="  Use this Python to create the venv? [Y/n]: "
    if /i "!_CONFIRM!"=="n" set BASE_PYTHON=
    echo.
)

if not defined BASE_PYTHON (
    echo   Python was not found automatically.
    echo   Enter the full path to python.exe (3.10 or newer required).
    echo   Example:  C:\Users\YourName\AppData\Local\Programs\Python\Python311\python.exe
    echo.
    set /p BASE_PYTHON="  Python path: "
    echo.
)

if not exist "!BASE_PYTHON!" (
    echo   ERROR: File not found: !BASE_PYTHON!
    pause
    exit /b 1
)

:: ── Version check ─────────────────────────────────────────────────────────────
for /f "tokens=2 delims= " %%V in ('"!BASE_PYTHON!" --version 2^>^&1') do set PY_VER=%%V
for /f "tokens=1,2 delims=." %%A in ("!PY_VER!") do (
    set PY_MAJOR=%%A
    set PY_MINOR=%%B
)
if !PY_MAJOR! LSS 3 (
    echo   ERROR: Python 3.10 or newer is required.  Found: !PY_VER!
    pause
    exit /b 1
)
if !PY_MAJOR!==3 if !PY_MINOR! LSS 10 (
    echo   ERROR: Python 3.10 or newer is required.  Found: !PY_VER!
    pause
    exit /b 1
)

:: ── Create .venv ──────────────────────────────────────────────────────────────
set VENV_DIR=!REPO_DIR!\.venv

if exist "!VENV_DIR!\Scripts\python.exe" (
    echo   A virtual environment already exists at: !VENV_DIR!
    set /p _REUSE="  Re-use it and just update packages? [Y/n]: "
    echo.
    if /i "!_REUSE!"=="n" (
        echo   Removing existing .venv...
        rmdir /s /q "!VENV_DIR!"
    )
)

if not exist "!VENV_DIR!\Scripts\python.exe" (
    echo   Creating virtual environment at: !VENV_DIR!
    "!BASE_PYTHON!" -m venv "!VENV_DIR!"
    if errorlevel 1 (
        echo   ERROR: Failed to create virtual environment.
        echo   Ensure the venv module is available: python -m ensurepip
        pause
        exit /b 1
    )
    echo   Virtual environment created.
    echo.
)

:: ── Install packages ──────────────────────────────────────────────────────────
echo   Upgrading pip...
"!VENV_DIR!\Scripts\python.exe" -m pip install --upgrade pip --quiet

echo   Installing PrestoGeometry and all dependencies...
echo   (This downloads packages — may take a few minutes on first run.)
echo.
"!VENV_DIR!\Scripts\pip.exe" install -e "!REPO_DIR!" --quiet
if errorlevel 1 (
    echo   ERROR: pip install failed.
    echo   Check your internet connection and review the error above.
    pause
    exit /b 1
)

set PYTHON_EXE=!VENV_DIR!\Scripts\python.exe
set INSTALL_NOTE=Python venv at !VENV_DIR!
goto :write_env


:: =============================================================================
::  PATH 3 — EXISTING ENVIRONMENT (just register it)
:: =============================================================================
:existing_path

echo ─────────────────────────────────────────────────────────────
echo   Existing environment  —  register Python path
echo ─────────────────────────────────────────────────────────────
echo.
echo   Enter the full path to the python.exe you want to use.
echo   This can be from a Conda environment, a venv, or any Python
echo   installation that already has the required packages.
echo.
echo   Conda env examples:
echo     C:\Users\YourName\miniconda3\envs\my_env\python.exe
echo     C:\ProgramData\miniconda3\envs\my_env\python.exe
echo.
echo   venv example:
echo     C:\Projects\MyProject\.venv\Scripts\python.exe
echo.
echo   System Python example:
echo     C:\Users\YourName\AppData\Local\Programs\Python\Python311\python.exe
echo.

:existing_prompt
set PYTHON_EXE=
set /p PYTHON_EXE="  Path to python.exe: "
echo.

if not defined PYTHON_EXE (
    echo   Please enter a path.
    goto :existing_prompt
)

if not exist "!PYTHON_EXE!" (
    echo   ERROR: File not found: !PYTHON_EXE!
    echo.
    set /p _RETRY="  Try a different path? [Y/n]: "
    if /i not "!_RETRY!"=="n" goto :existing_prompt
    pause
    exit /b 1
)

:: ── Version check ─────────────────────────────────────────────────────────────
echo   Checking Python version...
for /f "tokens=2 delims= " %%V in ('"!PYTHON_EXE!" --version 2^>^&1') do set PY_VER=%%V
echo   Found: Python !PY_VER!
echo.

for /f "tokens=1,2 delims=." %%A in ("!PY_VER!") do (
    set PY_MAJOR=%%A
    set PY_MINOR=%%B
)
if !PY_MAJOR! LSS 3 (
    echo   ERROR: Python 3.10 or newer is required.  Found: !PY_VER!
    pause
    exit /b 1
)
if !PY_MAJOR!==3 if !PY_MINOR! LSS 10 (
    echo   ERROR: Python 3.10 or newer is required.  Found: !PY_VER!
    pause
    exit /b 1
)

:: ── Optionally install packages ───────────────────────────────────────────────
echo   Do you want to install / update PrestoGeometry packages
echo   into this environment?
echo.
echo     [Y] Yes — run  pip install -e .  (safe to re-run on existing envs)
echo     [N] No  — skip install (use this if packages are already present)
echo.
set /p _INSTALL="  Install packages? [Y/n]: "
echo.

if /i not "!_INSTALL!"=="n" (
    echo   Installing PrestoGeometry and all dependencies...
    echo   (This downloads packages — may take a few minutes on first run.)
    echo.
    "!PYTHON_EXE!" -m pip install -e "!REPO_DIR!" --quiet
    if errorlevel 1 (
        echo   ERROR: pip install failed.
        echo   Check your internet connection, or re-run and choose N to skip.
        pause
        exit /b 1
    )
    echo   Packages installed.
    echo.
) else (
    echo   Skipping package installation.
    echo.
)

set INSTALL_NOTE=Existing environment at !PYTHON_EXE!
goto :write_env


:: =============================================================================
::  WRITE _env.bat
:: =============================================================================
:write_env

echo ─────────────────────────────────────────────────────────────
echo   Writing environment config...
echo ─────────────────────────────────────────────────────────────
echo.

(
    echo @echo off
    echo :: Auto-generated by install.bat
    echo :: Re-run install.bat if you move the repo or switch environments.
    echo ::
    echo :: !INSTALL_NOTE!
    echo set PRESTO_PYTHON=!PYTHON_EXE!
) > "!REPO_DIR!\_env.bat"

echo   Written : !REPO_DIR!\_env.bat
echo   Python  : !PYTHON_EXE!
echo.

goto :verify


:: =============================================================================
::  VERIFY
:: =============================================================================
:verify

echo ─────────────────────────────────────────────────────────────
echo   Verifying installation...
echo ─────────────────────────────────────────────────────────────
echo.

"!PYTHON_EXE!" -c "import numpy; print('  numpy        ', numpy.__version__)"
"!PYTHON_EXE!" -c "import scipy; print('  scipy        ', scipy.__version__)"
"!PYTHON_EXE!" -c "import matplotlib; print('  matplotlib   ', matplotlib.__version__)"
"!PYTHON_EXE!" -c "import cv2; print('  opencv       ', cv2.__version__)"
"!PYTHON_EXE!" -c "import jsonschema; print('  jsonschema   ', jsonschema.__version__)"

echo.

:: Functional test — build a minimal Floorspace.js document
"!PYTHON_EXE!" -c ^
"import sys; sys.path.insert(0,'!REPO_DIR!'); from presto_geometry.exporters.floorspace import building_to_floorspace_dict; from presto_geometry.models.building import Building,ThermalZone,SpaceType; b=Building(); b.thermal_zones.append(ThermalZone(id='tz1',name='Zone',color='#88aadd')); b.space_types.append(SpaceType(id='st1',name='Type',color='#dddddd')); building_to_floorspace_dict(b); print('  Floorspace.js exporter: OK')" 2>nul
if errorlevel 1 (
    echo   WARNING: Floorspace.js exporter test failed.
    echo   Run install.bat again or check that all packages installed correctly.
) else (
    echo   Floorspace.js exporter: OK
)

echo.
echo ============================================================
echo   Setup complete!
echo.
echo   !INSTALL_NOTE!
echo.
echo   HOW TO START:
echo     Double-click  launch.bat      opens the graphical launcher
echo     Double-click  annotate.bat    opens the annotation tool directly
echo     Double-click  assemble.bat    opens the assembly tool directly
echo.
echo   WORKFLOW:
echo     1. In the launcher: select a folder of building photos
echo     2. Click 'Annotate' to trace building face edges in photos
echo     3. Click 'Assemble' to build and solve the floor plan
echo     4. Click 'Save Geometry' to write the Floorspace.js file
echo ============================================================
echo.

pause
exit /b 0
