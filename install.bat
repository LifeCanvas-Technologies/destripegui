call conda env create -f environment.yml

call conda activate destripegui_gpu

call pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

call pip install destripegui_gpu


@echo off

set SCRIPT="%TEMP%\%RANDOM%-%RANDOM%-%RANDOM%-%RANDOM%.vbs"

echo Set WshShell = CreateObject("Wscript.shell") >> %SCRIPT%
echo Set oLink = WshShell.CreateShortcut("%USERPROFILE%\Desktop\Destripe_GUI.lnk") >> %SCRIPT%
echo oLink.TargetPath = "%WINDIR%\System32\wscript.exe" >> %SCRIPT%  
echo oLink.IconLocation = "%~dp0destripegui\data\lct.ico" >> %SCRIPT%
echo oLink.Arguments = "%~dp0destripegui\data\invisible.vbs %~dp0destripegui\data\Destripe_GUI.bat" >> %SCRIPT%
echo oLink.Save >> %SCRIPT%

cscript %SCRIPT%
del %SCRIPT%