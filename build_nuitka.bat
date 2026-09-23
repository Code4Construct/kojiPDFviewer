@echo off
setlocal
cd /d "%~dp0"
if not defined APP_VERSION set /p APP_VERSION=<VERSION
python -m nuitka --standalone --remove-output --assume-yes-for-downloads --jobs=2 --enable-plugin=pyside6 --include-module=win32timezone --windows-console-mode=disable --windows-icon-from-ico=assets\icons\MailPDFViewer.ico --windows-product-name=MailPDFViewer --windows-file-description="Mail PDF Viewer" --windows-file-version=%APP_VERSION%.0 --windows-product-version=%APP_VERSION%.0 --output-filename=MailPDFViewer.exe main.py
exit /b %errorlevel%
