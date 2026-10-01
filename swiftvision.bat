@echo off
cd /d F:\SwiftVision\Tools\swiftvision

echo [1/4] Regenerating README with logo...
python make_readme.py
if errorlevel 1 goto error

echo [2/4] Cleaning old build...
rmdir /s /q dist 2>nul
rmdir /s /q build 2>nul
rmdir /s /q swiftvision.egg-info 2>nul

echo [3/4] Building package...
python -m build
if errorlevel 1 goto error

echo [4/4] Uploading to PyPI...
python -m twine upload dist/*
if errorlevel 1 goto error

echo.
echo ========================================
echo   SUCCESS! Package is live on PyPI
echo ========================================
pause
exit /b 0

:error
echo.
echo FAILED. Check output above.
pause
exit /b 1