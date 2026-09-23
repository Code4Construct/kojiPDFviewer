@echo off
setlocal
cd /d "%~dp0"
if not defined APP_VERSION set /p APP_VERSION=<VERSION
python -m nuitka --standalone --remove-output --assume-yes-for-downloads --jobs=2 --lto=no --noinclude-custom-mode=pymupdf.mupdf:bytecode --enable-plugin=pyside6 --include-module=win32timezone --windows-console-mode=disable --windows-icon-from-ico=assets\icons\kojiPDFviewer.ico --windows-product-name=kojiPDFviewer --windows-file-description="kojiPDFviewer" --windows-file-version=%APP_VERSION%.0 --windows-product-version=%APP_VERSION%.0 --output-filename=kojiPDFviewer.exe main.py
exit /b %errorlevel%
