#!/usr/bin/env python3
"""
convert_to_epub.py - Convert cleaned and refined text to EPUB format
Uses EbookLib to generate an EPUB file from text
"""

import argparse
from pathlib import Path
from ebooklib import epub
import html


def parse_chapters(file_path):
    """
    Parse the cleaned text file into chapters based on standard markers.

    Args:
        file_path (Path): Path to the text file

    Returns:
        List of tuples: Chapter title and content
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()

    import re
    
    # Split on chapter/part markers
    # This regex looks for lines starting with Chapter/Part followed by number/roman numerals
    chapter_pattern = re.compile(r'^(Chapter|Part|CHAPTER|PART)\s+([IVXLCDM]+|\d+)', re.MULTILINE)
    
    # Find all chapter positions
    chapter_matches = list(chapter_pattern.finditer(text))
    
    if not chapter_matches:
        # No chapters found, treat entire text as one chapter
        return [("Introduction", text)]
    
    chapters = []
    
    # If there's content before the first chapter, add it as an introduction
    if chapter_matches[0].start() > 0:
        intro_text = text[:chapter_matches[0].start()].strip()
        if intro_text:
            chapters.append(("Introduction", intro_text))
    
    # Extract each chapter
    for i, match in enumerate(chapter_matches):
        # Chapter title is the matched line
        title_start = match.start()
        title_end = text.find('\n', title_start)
        if title_end == -1:
            title_end = len(text)
        title = text[title_start:title_end].strip()
        
        # Chapter content is from after the title to the next chapter (or end)
        content_start = title_end + 1
        if i < len(chapter_matches) - 1:
            content_end = chapter_matches[i + 1].start()
        else:
            content_end = len(text)
        
        content = text[content_start:content_end].strip()
        
        if title and content:
            chapters.append((title, content))
    
    return chapters


def create_epub(book_id, title, author, chapters, output_path):
    """
    Create an EPUB book from the provided chapters.

    Args:
        book_id (str): Identifier for the book
        title (str): Book title
        author (str): Author name
        chapters (List[Tuple[str, str]]): List of chapter (title, content) tuples
        output_path (Path): Path where EPUB will be written
    """
    book = epub.EpubBook()

    book.set_identifier(book_id)
    book.set_title(title)
    book.add_author(author)

    epub_items = []

    for i, (chapter_title, chapter_content) in enumerate(chapters):
        chapter_file_name = f'chap_{i+1}.xhtml'
        # Convert content to proper HTML with paragraphs
        paragraphs = chapter_content.split('\n\n')
        html_paragraphs = []
        for para in paragraphs:
            para = para.strip()
            if para:
                # Escape HTML and preserve line breaks within paragraphs
                escaped_para = html.escape(para.replace('\n', '<br>'))
                html_paragraphs.append(f'<p>{escaped_para}</p>')
        
        chapter_html = f'<h1>{html.escape(chapter_title)}</h1>\n' + '\n'.join(html_paragraphs)
        chapter = epub.EpubHtml(
            title=chapter_title,
            file_name=chapter_file_name,
            content=chapter_html,
        )
        epub_items.append(chapter)
        book.add_item(chapter)

    # Define Table Of Contents
    book.toc = (
        (epub.Link(item.file_name, item.title, item.file_name) for item in epub_items),
    )

    # Add default NCX and Nav files
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Define CSS style
    style = '''
    @namespace epub "http://www.idpf.org/2007/ops";
    body {
        font-family: Times, Times New Roman, serif;
    }
    h1 {
        text-align: left;
        text-transform: uppercase;
        font-weight: 200;
    }
    ol {
        list-style-type: none;
    }
    ol > li:first-child {
        margin-top: 0.3em;
    }
    nav[epub|type~="toc"] > ol > li > ol  {
        list-style-type: none;
    }
    '''

    nav_css = epub.EpubItem(
        uid="style_nav",
        file_name="style/nav.css",
        media_type="text/css",
        content=style
    )
    book.add_item(nav_css)

    # Basic spine
    book.spine = ['nav'] + epub_items

    # Write to the file
    epub.write_epub(output_path, book)


def main():
    """Main entry point with CLI argument parsing"""
    parser = argparse.ArgumentParser(
        description='Convert text to EPUB format'
    )
    parser.add_argument(
        '--in',
        dest='input',
        type=str,
        default='output/innerspace_final.txt',
        help='Input file path (default: output/innerspace_final.txt)'
    )
    parser.add_argument(
        '--out',
        dest='output',
        type=str,
        default='output/innerspace.epub',
        help='Output file path (default: output/innerspace.epub)'
    )

    args = parser.parse_args()

    input_file = Path(args.input)
    output_file = Path(args.output)

    if not input_file.exists():
        print(f"Error: Input file '{input_file}' not found.")
        exit(1)

    print(f"Converting text to EPUB")
    print(f"Input: {input_file}")
    print(f"Output: {output_file}")

    chapters = parse_chapters(input_file)
    print(f"Parsed {len(chapters)} chapters")

    create_epub(
        book_id="innerspace",
        title="Innerspace",
        author="Rabbi Aryeh Kaplan",
        chapters=chapters,
        output_path=output_file
    )
    print("EPUB conversion completed!")


if __name__ == "__main__":
    main()
