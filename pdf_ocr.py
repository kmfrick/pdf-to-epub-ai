#!/usr/bin/env python3
"""
pdf_ocr.py - Extract text from PDF files using OCR
Supports both text-based PDFs and image-based PDFs requiring OCR
"""

import argparse
import os
from pathlib import Path
import tempfile
import subprocess
import sys
from dotenv import load_dotenv

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("Warning: PyMuPDF not available, will try alternative methods")

try:
    from PIL import Image
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    print("Warning: Tesseract OCR not available, text extraction only")

try:
    import pdf2image
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    print("Warning: pdf2image not available, will use alternative conversion")


def check_dependencies():
    """Check if required dependencies are available."""
    missing = []
    
    if not PYMUPDF_AVAILABLE:
        missing.append("PyMuPDF (pip install PyMuPDF)")
    
    if not TESSERACT_AVAILABLE:
        missing.append("pytesseract and PIL (pip install pytesseract pillow)")
    
    if not PDF2IMAGE_AVAILABLE:
        missing.append("pdf2image (pip install pdf2image)")
    
    if missing:
        print("Missing dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        print("\nFor full functionality, install all dependencies.")
        return False
    
    return True


def extract_text_pymupdf(pdf_path):
    """
    Extract text from PDF using PyMuPDF (fastest method).
    
    Args:
        pdf_path (Path): Path to PDF file
        
    Returns:
        str: Extracted text
    """
    if not PYMUPDF_AVAILABLE:
        return None
    
    try:
        doc = fitz.open(pdf_path)
        text = ""
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            page_text = page.get_text()
            
            # Add page separator
            if page_text.strip():
                text += f"\n--- Page {page_num + 1} ---\n"
                text += page_text
                text += "\n"
        
        doc.close()
        return text
    
    except Exception as e:
        print(f"Error extracting text with PyMuPDF: {e}")
        return None


def convert_pdf_to_images(pdf_path, output_dir):
    """
    Convert PDF pages to images for OCR processing.
    
    Args:
        pdf_path (Path): Path to PDF file
        output_dir (Path): Directory to save images
        
    Returns:
        List[Path]: List of image file paths
    """
    image_paths = []
    
    if PDF2IMAGE_AVAILABLE:
        try:
            # Use pdf2image (requires poppler)
            from pdf2image import convert_from_path
            
            images = convert_from_path(pdf_path, dpi=300)
            
            for i, image in enumerate(images):
                image_path = output_dir / f"page_{i+1:03d}.png"
                image.save(image_path, "PNG")
                image_paths.append(image_path)
                
            return image_paths
            
        except Exception as e:
            print(f"Error with pdf2image: {e}")
    
    # Fallback: try using PyMuPDF for image conversion
    if PYMUPDF_AVAILABLE:
        try:
            doc = fitz.open(pdf_path)
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                
                # Render page as image at high resolution
                mat = fitz.Matrix(2.0, 2.0)  # 2x zoom = 144 DPI
                pix = page.get_pixmap(matrix=mat)
                
                image_path = output_dir / f"page_{page_num+1:03d}.png"
                pix.save(image_path)
                image_paths.append(image_path)
            
            doc.close()
            return image_paths
            
        except Exception as e:
            print(f"Error converting PDF to images: {e}")
    
    return []


def ocr_image(image_path, language='eng'):
    """
    Perform OCR on a single image.
    
    Args:
        image_path (Path): Path to image file
        language (str): Tesseract language code
        
    Returns:
        str: Extracted text
    """
    if not TESSERACT_AVAILABLE:
        return ""
    
    try:
        # Configure Tesseract for better results
        custom_config = r'--oem 3 --psm 6 -c preserve_interword_spaces=1'
        
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image, lang=language, config=custom_config)
        
        return text
    
    except Exception as e:
        print(f"Error performing OCR on {image_path}: {e}")
        return ""


def process_pdf_with_ocr(pdf_path, output_path, language='eng', force_ocr=False):
    """
    Process PDF file with OCR if needed.
    
    Args:
        pdf_path (Path): Path to input PDF
        output_path (Path): Path to output text file
        language (str): Tesseract language code
        force_ocr (bool): Force OCR even if text extraction works
    """
    print(f"Processing: {pdf_path}")
    
    # First, try direct text extraction (much faster)
    extracted_text = None
    if not force_ocr:
        print("Attempting direct text extraction...")
        extracted_text = extract_text_pymupdf(pdf_path)
        
        if extracted_text and len(extracted_text.strip()) > 100:
            print(f"Successfully extracted {len(extracted_text)} characters directly")
            
            # Write extracted text
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(extracted_text)
            
            print(f"Text saved to: {output_path}")
            return True
        else:
            print("Direct text extraction yielded minimal text, falling back to OCR...")
    
    # If direct extraction failed or was forced, use OCR
    if not TESSERACT_AVAILABLE:
        print("Error: OCR required but Tesseract not available")
        return False
    
    print("Starting OCR process...")
    
    # Create temporary directory for images
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Convert PDF to images
        print("Converting PDF to images...")
        image_paths = convert_pdf_to_images(pdf_path, temp_path)
        
        if not image_paths:
            print("Error: Could not convert PDF to images")
            return False
        
        print(f"Converted {len(image_paths)} pages to images")
        
        # Perform OCR on each image
        all_text = ""
        for i, image_path in enumerate(image_paths):
            print(f"Processing page {i+1}/{len(image_paths)}...")
            
            page_text = ocr_image(image_path, language)
            
            if page_text.strip():
                all_text += f"\n--- Page {i+1} ---\n"
                all_text += page_text
                all_text += "\n"
        
        # Write OCR results
        if all_text.strip():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(all_text)
            
            print(f"OCR completed! Extracted {len(all_text)} characters")
            print(f"Text saved to: {output_path}")
            return True
        else:
            print("Error: OCR produced no readable text")
            return False


def detect_tesseract_languages():
    """Detect available Tesseract languages."""
    if not TESSERACT_AVAILABLE:
        return []
    
    try:
        langs = pytesseract.get_languages()
        return langs
    except Exception:
        return ['eng']  # Default fallback


def main():
    """Main entry point with CLI argument handling."""
    load_dotenv()
    
    # Get defaults from environment
    default_temp_dir = os.getenv('TEMP_DIR', 'temp')
    default_tesseract_lang = os.getenv('TESSERACT_LANG', 'eng')
    tesseract_path = os.getenv('TESSERACT_PATH')
    
    # Set tesseract path if provided
    if tesseract_path and TESSERACT_AVAILABLE:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
    
    parser = argparse.ArgumentParser(
        description='Extract text from PDF files using OCR when necessary'
    )
    parser.add_argument(
        '--in',
        dest='input',
        type=str,
        required=True,
        help='Input PDF file path'
    )
    parser.add_argument(
        '--out',
        dest='output',
        type=str,
        help='Output text file path (default: same name as input with .txt extension)'
    )
    parser.add_argument(
        '--language',
        type=str,
        default=default_tesseract_lang,
        help=f'Tesseract language code (default: {default_tesseract_lang}). Use --list-languages to see available languages'
    )
    parser.add_argument(
        '--force-ocr',
        action='store_true',
        help='Force OCR even if direct text extraction works'
    )
    parser.add_argument(
        '--list-languages',
        action='store_true',
        help='List available Tesseract languages and exit'
    )
    parser.add_argument(
        '--check-deps',
        action='store_true',
        help='Check dependencies and exit'
    )
    
    args = parser.parse_args()
    
    # Handle special flags
    if args.check_deps:
        check_dependencies()
        return
    
    if args.list_languages:
        langs = detect_tesseract_languages()
        print("Available Tesseract languages:")
        for lang in sorted(langs):
            print(f"  {lang}")
        return
    
    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found")
        sys.exit(1)
    
    if input_path.suffix.lower() != '.pdf':
        print(f"Warning: Input file doesn't have .pdf extension")
    
    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_suffix('.txt')
    
    print("PDF OCR Text Extraction")
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(f"Language: {args.language}")
    print(f"Force OCR: {args.force_ocr}")
    print()
    
    # Check basic dependencies
    if not PYMUPDF_AVAILABLE and not TESSERACT_AVAILABLE:
        print("Error: No text extraction method available")
        print("Please install either PyMuPDF or Tesseract dependencies")
        sys.exit(1)
    
    # Process the PDF
    success = process_pdf_with_ocr(
        input_path, 
        output_path, 
        language=args.language,
        force_ocr=args.force_ocr
    )
    
    if success:
        print("\nPDF processing completed successfully!")
        print(f"Next step: python process_ocr.py --in {output_path}")
    else:
        print("\nPDF processing failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
