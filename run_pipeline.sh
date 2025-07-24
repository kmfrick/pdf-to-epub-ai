#!/bin/bash
# This script runs the full PDF to EPUB pipeline

# Load environment variables from .env file if present
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# Ensure required directories exist
mkdir -p "$OUTPUT_DIR"
mkdir -p "$TEMP_DIR"

# Step 1: Perform OCR on PDF
echo "Starting OCR process..."
python pdf_ocr.py input.pdf "$TEMP_DIR/ocr_output.txt"

# Step 2: Clean the OCR text
echo "Cleaning OCR text..."
python process_ocr.py "$TEMP_DIR/ocr_output.txt" "$TEMP_DIR/cleaned_text.txt"

# Step 3: AI-Based Text Refinement
echo "Refining text with AI..."
python openai_cleaner.py "$TEMP_DIR/cleaned_text.txt" "$TEMP_DIR/refined_text.txt"

# Step 4: Convert cleaned text to EPUB
echo "Converting to EPUB..."
python convert_to_epub.py "$TEMP_DIR/refined_text.txt" "$OUTPUT_DIR/final_output.epub"

# Completion message
echo "PDF to EPUB conversion complete! Find your file at: $OUTPUT_DIR/final_output.epub"
