# PowerShell script to run the full PDF to EPUB pipeline

# Load environment variables from .env file if present
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^([^#][^=]+)=(.*)$") {
            $name = $matches[1]
            $value = $matches[2]
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

# Set default values if not defined in .env
$OUTPUT_DIR = if ($env:OUTPUT_DIR) { $env:OUTPUT_DIR } else { "output" }
$TEMP_DIR = if ($env:TEMP_DIR) { $env:TEMP_DIR } else { "temp" }

# Set default Tesseract path for Windows if not defined
if (-not $env:TESSERACT_PATH) {
    if (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe") {
        $env:TESSERACT_PATH = "C:\Program Files\Tesseract-OCR\tesseract.exe"
    } elseif (Test-Path "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe") {
        $env:TESSERACT_PATH = "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
    }
}

# Ensure required directories exist
New-Item -ItemType Directory -Force -Path $OUTPUT_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $TEMP_DIR | Out-Null

# Check if input PDF is provided
if ($args.Count -eq 0) {
    Write-Host "Usage: .\run_pipeline.ps1 <input.pdf>" -ForegroundColor Red
    exit 1
}

$inputPdf = $args[0]

# Verify input file exists
if (-not (Test-Path $inputPdf)) {
    Write-Host "Error: Input file '$inputPdf' not found!" -ForegroundColor Red
    exit 1
}

# Step 1: Perform OCR on PDF
Write-Host "Step 1: Starting OCR process..." -ForegroundColor Green
python pdf_ocr.py $inputPdf "$TEMP_DIR/ocr_output.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: OCR process failed!" -ForegroundColor Red
    exit 1
}

# Step 2: Clean the OCR text
Write-Host "Step 2: Cleaning OCR text..." -ForegroundColor Green
python process_ocr.py "$TEMP_DIR/ocr_output.txt" "$TEMP_DIR/cleaned_text.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: OCR cleaning failed!" -ForegroundColor Red
    exit 1
}

# Step 3: AI-Based Text Refinement
Write-Host "Step 3: Refining text with AI..." -ForegroundColor Green
python openai_cleaner.py "$TEMP_DIR/cleaned_text.txt" "$TEMP_DIR/refined_text.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: AI refinement failed!" -ForegroundColor Red
    exit 1
}

# Step 4: Convert cleaned text to EPUB
Write-Host "Step 4: Converting to EPUB..." -ForegroundColor Green
$outputFile = "$OUTPUT_DIR/$(Split-Path $inputPdf -LeafBase).epub"
python convert_to_epub.py "$TEMP_DIR/refined_text.txt" $outputFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: EPUB conversion failed!" -ForegroundColor Red
    exit 1
}

# Completion message
Write-Host "PDF to EPUB conversion complete!" -ForegroundColor Green
Write-Host "Output file: $outputFile" -ForegroundColor Cyan

# Optional cleanup
$cleanup = Read-Host "Delete temporary files? (y/N)"
if ($cleanup -eq "y" -or $cleanup -eq "Y") {
    Remove-Item -Path "$TEMP_DIR/*" -Force
    Write-Host "Temporary files cleaned up." -ForegroundColor Yellow
}
