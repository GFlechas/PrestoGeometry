@echo off
:: PrestoGeometry Launcher — main entry point
::
:: Opens the graphical launcher where you can select a photos folder and
:: start the Annotation or Assembly tools.
::
:: Usage:
::   launch.bat

call "C:\Users\gabri\miniconda3\Scripts\activate.bat" ai_agent
python "%~dp0tools\launcher.py" %*
