#!/usr/bin/env python3
"""
process_ocr.py - Local regex/heuristic clean-up for OCR text
Reads OCR output text and applies various cleaning operations to improve readability
"""

import argparse
import os
import re
from pathlib import Path
from dotenv import load_dotenv


def detect_paragraph_boundaries(text):
    """
    Smart paragraph boundary detection using multiple heuristics.
    
    Args:
        text (str): Text to analyze
        
    Returns:
        str: Text with proper paragraph breaks
    """
    lines = text.split('\n')
    processed_lines = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            processed_lines.append('')
            continue
            
        # Check if this should start a new paragraph
        should_break = False
        
        # Previous line ended with sentence punctuation
        if i > 0 and processed_lines and processed_lines[-1]:
            prev_line = processed_lines[-1].strip()
            if re.search(r'[.!?]\s*["\']?$', prev_line):
                # Current line starts with capital letter or number
                if re.match(r'^[A-Z0-9]', line):
                    should_break = True
        
        # Headers and titles
        if re.match(r'^(Chapter|Part|Section|Foreword|Introduction|Conclusion|Appendix|Index|Bibliography|Table of Contents)\b', line, re.IGNORECASE):
            should_break = True
        
        # Add paragraph break if needed
        if should_break and processed_lines and processed_lines[-1].strip():
            processed_lines.append('')
            
        processed_lines.append(line)
    
    return '\n'.join(processed_lines)

def smart_sentence_flow(text):
    """
    Improve sentence flow by intelligently merging broken sentences.
    
    Args:
        text (str): Text to process
        
    Returns:
        str: Text with improved sentence flow
    """
    lines = text.split('\n')
    merged_lines = []
    i = 0
    
    while i < len(lines):
        current_line = lines[i].rstrip()
        
        # Skip empty lines
        if not current_line:
            merged_lines.append('')
            i += 1
            continue
        
        # Look ahead for continuation
        if i < len(lines) - 1:
            next_line = lines[i + 1].strip()
            
            # Merge conditions:
            # 1. Current line doesn't end with sentence punctuation
            # 2. Next line doesn't start with capital letter (unless it's a proper noun)
            # 3. Not a header or title
            should_merge = (
                current_line and next_line and
                not re.search(r'[.!?:;"\']\s*$', current_line) and
                not re.match(r'^[A-Z][a-z]*\s+(Chapter|Part|Section)', next_line) and
                not re.match(r'^(Chapter|Part|Section|Foreword|Introduction)', next_line, re.IGNORECASE) and
                not re.match(r'^[A-Z]{2,}', next_line) and  # Avoid all-caps headers
                len(current_line) > 10  # Avoid merging very short lines
            )
            
            if should_merge:
                # Add space if current line doesn't end with space or hyphen
                separator = '' if current_line.endswith(('-', ' ')) else ' '
                merged_lines.append(current_line + separator + next_line)
                i += 2
                continue
        
        merged_lines.append(current_line)
        i += 1
    
    return '\n'.join(merged_lines)

def enhance_punctuation_and_capitalization(text):
    """
    Fix common punctuation and capitalization issues.
    
    Args:
        text (str): Text to fix
        
    Returns:
        str: Text with improved punctuation and capitalization
    """
    # Fix sentences that should start with capital letters
    text = re.sub(r'([.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text)
    
    # Fix beginning of paragraphs
    text = re.sub(r'(^|\n\n)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text, flags=re.MULTILINE)
    
    # Fix spacing around punctuation
    text = re.sub(r'\s+([.!?,:;])', r'\1', text)  # Remove space before punctuation
    text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)  # Add space after sentence punctuation
    
    # Fix common spacing issues (commented out as it's too aggressive)
    # text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)  # Add space between lowercase and uppercase
    
    return text

def advanced_ocr_corrections(text):
    """
    Advanced OCR error corrections with context awareness.
    
    Args:
        text (str): Text to correct
        
    Returns:
        str: Corrected text
    """
    # Enhanced OCR corrections dictionary
    ocr_corrections = {
        # Character substitutions
        r'\brn\b': 'm',
        r'\bm(?=[aeiou])': 'rn',  # 'm' before vowels might be 'rn'
        r'\b0(?=[a-z])': 'o',    # Zero before lowercase letters
        r'\b1(?=[a-z])': 'l',    # One before lowercase letters
        r'(?<=[a-z])1(?=[a-z])': 'l',  # One between lowercase letters
        r'(?<=[a-z])0(?=[a-z])': 'o',  # Zero between lowercase letters
        
        # Common word corrections
        r'\btl1e\b': 'the',
        r'\btl1at\b': 'that',
        r'\bwl1ich\b': 'which',
        r'\bwitl1\b': 'with',
        r'\btl1is\b': 'this',
        r'\btl1ey\b': 'they',
        r'\btl1ere\b': 'there',
        r'\bwl1en\b': 'when',
        r'\bwl1ere\b': 'where',
        r'\bwl1at\b': 'what',
        r'\bwl1o\b': 'who',
        r'\bwl1y\b': 'why',
        
        # Word-level corrections
        r'\b0f\b': 'of',
        r'\bt0\b': 'to',
        r'\bfor\b(?=\s+[a-z])': 'for',  # Ensure 'for' is correct
        r'\bin\b(?=\s+[a-z])': 'in',    # Ensure 'in' is correct
        
        # Fix common OCR spacing issues (commented out as it's too aggressive)
        # r'(?<=[a-z])(?=[A-Z][a-z])': ' ',  # Add space between camelCase
        
        # Hebrew/religious text corrections
        r'\bK abbalah\b': 'Kabbalah',
        r'\bT orah\b': 'Torah',
        r'\bJ oshua\b': 'Joshua',
        r'\bM oses\b': 'Moses',
        r'\bR abbi\b': 'Rabbi',
        
        # Fix broken words with spaces
        r'\bo f\b': 'of',
        r'\bt o\b': 'to',
        r'\bi n\b': 'in',
        r'\ba nd\b': 'and',
        r'\bt he\b': 'the',
        r'\bi s\b': 'is',
        r'\ba re\b': 'are',
        r'\bw as\b': 'was',
        r'\bw ere\b': 'were',
    }
    
    for pattern, replacement in ocr_corrections.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    return text

def split_oversized_paragraphs(text, max_sentences=8):
    """
    Split very long paragraphs into smaller, more readable ones.
    
    Args:
        text (str): Text to process
        max_sentences (int): Maximum sentences per paragraph
        
    Returns:
        str: Text with appropriately sized paragraphs
    """
    paragraphs = text.split('\n\n')
    processed_paragraphs = []
    
    for paragraph in paragraphs:
        if not paragraph.strip():
            processed_paragraphs.append('')
            continue
            
        # Count sentences in paragraph
        sentences = re.split(r'[.!?]+\s+', paragraph)
        
        if len(sentences) <= max_sentences:
            processed_paragraphs.append(paragraph)
        else:
            # Split into smaller paragraphs
            for i in range(0, len(sentences), max_sentences):
                chunk = sentences[i:i + max_sentences]
                if chunk:
                    processed_paragraphs.append('. '.join(chunk).rstrip('.') + '.')
    
    return '\n\n'.join(processed_paragraphs)

def clean_ocr_text(text):
    """
    Apply comprehensive OCR cleaning with smart paragraph processing.
    
    Args:
        text (str): Raw OCR text
        
    Returns:
        str: Cleaned and intelligently processed text
    """
    print("Starting comprehensive OCR cleaning...")
    
    # 1. Strip form-feeds and basic cleanup
    text = text.replace('\f', '')
    text = re.sub(r'\r\n', '\n', text)  # Normalize line endings
    text = re.sub(r'\r', '\n', text)
    
    # 2. Remove standalone page numbers and headers/footers
    text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[ivxlcdm]+\s*$', '', text, flags=re.MULTILINE)  # Roman numerals
    
    # 3. Advanced OCR corrections first
    print("Applying OCR corrections...")
    text = advanced_ocr_corrections(text)
    
    # 4. Merge hyphen-broken words
    text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)
    text = re.sub(r'(\w)-\s+(\w)', r'\1\2', text)  # Also fix same-line hyphen breaks
    
    # 5. Smart sentence flow improvement
    print("Improving sentence flow...")
    text = smart_sentence_flow(text)
    
    # 6. Detect and improve paragraph boundaries
    print("Detecting paragraph boundaries...")
    text = detect_paragraph_boundaries(text)
    
    # 7. Enhance punctuation and capitalization
    print("Fixing punctuation and capitalization...")
    text = enhance_punctuation_and_capitalization(text)
    
    # 8. Normalize whitespace
    text = re.sub(r' +', ' ', text)  # Collapse multiple spaces
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Normalize paragraph breaks
    
    # 9. Unicode normalization and smart quotes
    replacements = {
        '“': '"',  # Left double quotation mark
        '”': '"',  # Right double quotation mark
        '‘': "'",  # Left single quotation mark
        '’': "'",  # Right single quotation mark
        '–': '-',  # En dash
        '—': '--', # Em dash
        '…': '...' # Ellipsis
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # 10. Split oversized paragraphs for better readability
    print("Optimizing paragraph sizes...")
    text = split_oversized_paragraphs(text)
    
    # 11. Final cleanup
    lines = [line.rstrip() for line in text.split('\n')]
    text = '\n'.join(lines)
    
    # Ensure text ends with a newline
    if text and not text.endswith('\n'):
        text += '\n'
    
    print("OCR cleaning completed.")
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
    load_dotenv()
    
    # Get defaults from environment
    default_output_dir = os.getenv('OUTPUT_DIR', 'output')
    
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
        default=f'{default_output_dir}/innerspace_clean.txt',
        help=f'Output file path (default: {default_output_dir}/innerspace_clean.txt)'
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
