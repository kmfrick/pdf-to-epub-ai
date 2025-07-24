#!/usr/bin/env python3
"""
process_ocr.py - Local regex/heuristic clean-up for OCR text
Reads OCR output text and applies various cleaning operations to improve readability
"""

import argparse
import re
from pathlib import Path


def clean_ocr_text(text):
    """
    Apply various cleaning operations to OCR text.
    
    Args:
        text (str): Raw OCR text
        
    Returns:
        str: Cleaned text
    """
    # 1. Strip form-feeds
    text = text.replace('\f', '')
    
    # 2. Remove standalone page numbers (lines with only digits)
    text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
    
    # 3. Merge hyphen-broken words
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
    
    # 4. Re-flow paragraphs: join lines that don't end with sentence punctuation
    # This regex matches lines that don't end with .!?:"'" (including quotes)
    lines = text.split('\n')
    merged_lines = []
    i = 0
    
    while i < len(lines):
        current_line = lines[i].rstrip()
        
        if i < len(lines) - 1:
            next_line = lines[i + 1].strip()
            
            # Check if current line ends with sentence punctuation
            if (current_line and 
                next_line and 
                not re.search(r'[.!?:"\'"]$', current_line) and
                not re.match(r'^(Chapter|Part|CHAPTER|PART)\s+', next_line)):
                # Merge with next line
                merged_lines.append(current_line + ' ' + next_line)
                i += 2  # Skip next line as it's been merged
                continue
        
        merged_lines.append(current_line)
        i += 1
    
    text = '\n'.join(merged_lines)
    
    # 5. Normalize multiple blank lines to maximum 1
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    
    # 6. Translate curly quotes and smart apostrophes to straight ASCII
    replacements = {
        '"': '"',  # Left double quotation mark
        '"': '"',  # Right double quotation mark
        ''': "'",  # Left single quotation mark
        ''': "'",  # Right single quotation mark
        '–': '-',  # En dash
        '—': '--', # Em dash
        '…': '...' # Ellipsis
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Collapse multiple spaces
    text = re.sub(r' +', ' ', text)
    
    # 7. Optional: Common OCR artifacts dictionary
    ocr_corrections = {
        # Common OCR misreadings
        r'\brn\b': 'm',  # "rn" often misread as "m"
        r'\bI\b(?=[a-z])': 'l',  # Capital I before lowercase often should be l
        r'(?<=[a-z])\bI\b': 'l',  # Capital I after lowercase often should be l
        r'\btl1e\b': 'the',  # Common "the" misreading
        r'\btl1at\b': 'that',  # Common "that" misreading
        r'\bwl1ich\b': 'which',  # Common "which" misreading
        r'\b0f\b': 'of',  # Zero instead of 'o' in "of"
        r'\bt0\b': 'to',  # Zero instead of 'o' in "to"
    }
    
    for pattern, replacement in ocr_corrections.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    # Clean up any remaining issues
    # Remove trailing spaces from lines
    text = '\n'.join(line.rstrip() for line in text.split('\n'))
    
    # Ensure text ends with a newline
    if text and not text.endswith('\n'):
        text += '\n'
    
    return text


def process_file(input_path, output_path):
    """
    Process an OCR text file and save the cleaned version.
    
    Args:
        input_path (Path): Path to input file
        output_path (Path): Path to output file
    """
    try:
        # Read input file
        with open(input_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        print(f"Read {len(text):,} characters from {input_path}")
        
        # Clean the text
        cleaned_text = clean_ocr_text(text)
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write cleaned text
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_text)
        
        print(f"Wrote {len(cleaned_text):,} characters to {output_path}")
        print(f"Reduction: {len(text) - len(cleaned_text):,} characters")
        
    except FileNotFoundError:
        print(f"Error: Input file '{input_path}' not found.")
        return False
    except Exception as e:
        print(f"Error processing file: {e}")
        return False
    
    return True


def main():
    """Main entry point with CLI argument handling."""
    parser = argparse.ArgumentParser(
        description='Clean OCR text using regex and heuristics'
    )
    parser.add_argument(
        '--in', 
        dest='input',
        type=str,
        default='innerspace.txt',
        help='Input file path (default: innerspace.txt)'
    )
    parser.add_argument(
        '--out',
        dest='output',
        type=str,
        default='output/innerspace_clean.txt',
        help='Output file path (default: output/innerspace_clean.txt)'
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    print(f"Processing OCR cleanup...")
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    
    if process_file(input_path, output_path):
        print("OCR cleanup completed successfully!")
    else:
        print("OCR cleanup failed.")
        exit(1)


if __name__ == "__main__":
    main()
