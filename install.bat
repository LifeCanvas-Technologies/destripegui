call conda env remove -n command_line_destripe

call conda env create -f environment.yml

call conda activate command_line_destripe

call pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

call pip install -e .


@echo off

set SCRIPT="%TEMP%\%RANDOM%-%RANDOM%-%RANDOM%-%RANDOM%.vbs"

echo Set WshShell = CreateObject("Wscript.shell") >> %SCRIPT%
echo Set oLink = WshShell.CreateShortcut("%USERPROFILE%\Desktop\Command_Line_Destripe.lnk") >> %SCRIPT%
echo oLink.TargetPath = "%~dp0destripegui\data\Command_Line_Destripe.bat" >> %SCRIPT%
echo oLink.IconLocation = "%~dp0destripegui\data\lct.ico" >> %SCRIPT%
echo oLink.Save >> %SCRIPT%

cscript %SCRIPT%
del %SCRIPT%