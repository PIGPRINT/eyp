@echo off
rem Builds the shareable app:  release\Now Playing\Now Playing.exe  and  release\Now-Playing-Widget.zip
rem Needs:  pip install -r requirements.txt
rem (paths use %~dp0 = this folder, because PyInstaller reads relative paths from its temp build folder)
cd /d "%~dp0"
python app.py --test || exit /b 1

pyinstaller --noconfirm --windowed --name "Now Playing" --icon "%~dp0icon.ico" ^
  --add-data "%~dp0skins;skins" --add-data "%~dp0bubble.html;." --add-data "%~dp0icon.ico;." ^
  --collect-all webview --collect-all winrt --collect-all pyaudiowpatch --hidden-import pycaw.pycaw ^
  --distpath release --workpath "%TEMP%\now-playing-build" --specpath "%TEMP%\now-playing-build" app.py || exit /b 1

copy /y README.md "release\Now Playing\README.md" >nul
powershell -NoProfile -Command "Compress-Archive -Force -Path 'release\Now Playing' -DestinationPath 'release\Now-Playing-Widget.zip'"
echo.
echo Done: release\Now-Playing-Widget.zip
