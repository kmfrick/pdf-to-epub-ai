@echo off
REM Windows batch script to run the full PDF to EPUB pipeline

REM Check if input file is provided
if "%~1"=="" (
    echo Usage: run_pipeline.bat ^<input.pdf^>
    echo Example: run_pipeline.bat document.pdf
    exit /b 1
)

set INPUT_PDF=%~1

REM Check if input file exists
if not exist "%INPUT_PDF%" (
    echo Error: Input file '%INPUT_PDF%' not found!
    exit /b 1
)

REM Get filename without extension for output naming
for %%F in ("%INPUT_PDF%") do set "BASENAME=%%~nF"

REM Load environment variables from .env file if it exists
if exist .env (
    echo Loading configuration from .env file...
    for /f "usebackq tokens=1,2 delims==" %%A in (.env) do (
        if not "%%A"=="" if not "%%B"=="" (
            set "%%A=%%B"
        )
    )
)

REM Set default values if not defined in .env
if not defined OUTPUT_DIR set OUTPUT_DIR=output
if not defined TEMP_DIR set TEMP_DIR=temp

REM Set default Tesseract path for Windows
if not defined TESSERACT_PATH (
    if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
        set TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe
    ) else if exist "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe" (
        set TESSERACT_PATH=C:\Program Files (x86)\Tesseract-OCR\tesseract.exe
    )
)

REM Create directories if they don't exist
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%"

echo ========================================
echo PDF to EPUB Conversion Pipeline
echo ========================================
echo Input PDF: %INPUT_PDF%
echo Output directory: %OUTPUT_DIR%
echo Temporary directory: %TEMP_DIR%
echo ========================================

REM Step 1: Extract text from PDF using OCR
echo.
echo [STEP 1/4] Extracting text from PDF...
python pdf_ocr.py --in "%INPUT_PDF%" --out "%TEMP_DIR%\%BASENAME%_ocr.txt"
if errorlevel 1 (
    echo ERROR: PDF text extraction failed!
    exit /b 1
)

REM Step 2: Clean the OCR text
echo.
echo [STEP 2/4] Cleaning OCR text...
python process_ocr.py --in "%TEMP_DIR%\%BASENAME%_ocr.txt" --out "%TEMP_DIR%\%BASENAME%_clean.txt"
if errorlevel 1 (
    echo ERROR: OCR text cleaning failed!
    exit /b 1
)

REM Step 3: AI-Based Text Refinement
echo.
echo [STEP 3/4] Refining text with AI...
python openai_cleaner.py --in "%TEMP_DIR%\%BASENAME%_clean.txt" --out "%TEMP_DIR%\%BASENAME%_refined.txt"
if errorlevel 1 (
    echo ERROR: AI text refinement failed!
    exit /b 1
)

REM Step 4: Convert to EPUB
echo.
echo [STEP 4/4] Converting to EPUB...
python convert_to_epub.py --in "%TEMP_DIR%\%BASENAME%_refined.txt" --out "%OUTPUT_DIR%\%BASENAME%.epub"
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

REM Ask if user wants to clean up temporary files
set /p CLEANUP="Delete temporary files? (y/N): "
if /i "%CLEANUP%"=="y" (
    echo Cleaning up temporary files...
    del "%TEMP_DIR%\%BASENAME%_*.txt" 2>nul
    echo Temporary files cleaned up.
) else (
    echo Temporary files kept in %TEMP_DIR%
)

echo.
echo Done!
pause
