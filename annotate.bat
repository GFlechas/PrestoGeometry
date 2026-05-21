@echo off
:: Launches the interactive building face annotation tool.
::
:: Usage:
::   annotate.bat [building_name]
::
:: Examples:
::   annotate.bat
::   annotate.bat UnivStThomas_1loop
::   annotate.bat UnivStThomas_1loop --faces 5
::   annotate.bat LoringPark

call "C:\Users\gabri\miniconda3\Scripts\activate.bat" ai_agent
python "%~dp0tools\annotate_building.py" %*
