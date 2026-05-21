@echo off
:: Assembles 3-D building geometry from face annotations and saves a PNG.
::
:: Usage:
::   assemble.bat [building_name] [--floors N] [--floor-height F] [--widths F0=W,...]
::
:: Examples:
::   assemble.bat
::   assemble.bat UnivStThomas_1loop
::   assemble.bat UnivStThomas_1loop --floors 5 --floor-height 3.4
::   assemble.bat UnivStThomas_1loop --widths F0=13,F1=47,F2=15,F3=40,F4=10

call "C:\Users\gabri\miniconda3\Scripts\activate.bat" ai_agent
python "%~dp0tools\assemble_geometry.py" %*
