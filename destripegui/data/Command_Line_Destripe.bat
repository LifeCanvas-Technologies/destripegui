@echo off
for /f "tokens=4 delims=[] " %%a in ('ver') do @set version=%%a

if %version:~5,2%==19 mode con: cols=120 lines=60
@echo on
@echo Loading Destriper...
@echo off

call activate command_line_destripe
command_line_destripe