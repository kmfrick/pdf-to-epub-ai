@echo off
REM Test batch script for text-only pipeline (skipping PDF OCR)

set INPUT_TEXT=sample_ocr_text.txt

REM Check if input file exists
if not exist "%INPUT_TEXT%" (
    echo Error: Input file '%INPUT_TEXT%' not found!
    exit /b 1
)

REM Get filename without extension for output naming
for %%F in ("%INPUT_TEXT%") do set "BASENAME=%%~nF"

REM Set directories
set OUTPUT_DIR=output
set TEMP_DIR=temp

REM Create directories if they don't exist
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%"

echo ========================================
echo Text to EPUB Conversion Pipeline (Test)
echo ========================================
echo Input text: %INPUT_TEXT%
echo Output directory: %OUTPUT_DIR%
echo ========================================

REM Step 1: Clean the text
echo.
echo [STEP 1/2] Cleaning text...
python process_ocr.py --in "%INPUT_TEXT%" --out "%TEMP_DIR%\%BASENAME%_clean.txt"
if errorlevel 1 (
    echo ERROR: Text cleaning failed!
    exit /b 1
)

REM Step 2: Convert to EPUB (skip AI refinement for demo)
echo.
echo [STEP 2/2] Converting to EPUB...
python convert_to_epub.py --in "%TEMP_DIR%\%BASENAME%_clean.txt" --out "%OUTPUT_DIR%\%BASENAME%.epub"
if errorlevel 1 (
    echo ERROR: EPUB conversion failed!
    exit /b 1
)

echo.
echo ========================================
echo CONVERSION COMPLETED SUCCESSFULLY!
echo ========================================
echo Output EPUB: %OUTPUT_DIR%\%BASENAME%.epub
echo.

echo Done!
pause
