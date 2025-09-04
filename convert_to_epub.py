#!/usr/bin/env python3
"""
convert_to_epub.py - Convert cleaned/refined text to EPUB format.

Improvements vs. original:
1) Handles page artifacts commonly found in OCR/exports:
   - Removes lines like: "--- Page 17 ---", "— Page 20 —", "-----"
   - Removes running headers/footers like: "xviii  |  Acknowledgments" or "Acknowledgments  |  xix"
   - (Optional) --preserve-pages inserts real page breaks where page markers existed.

2) Prompts for Title and Author (if not provided via CLI) and generates a stable book_id
   based on a slug of "{title}-{author}". You can override with --bookid.

3) Prompts for an optional cover image (or use --cover). Defaults to none.

Dependencies:
- ebooklib
- python-dotenv (optional; only if you want OUTPUT_DIR env default)

"""

import argparse
import os
from pathlib import Path
from ebooklib import epub
import html
import re
import unicodedata
from dotenv import load_dotenv

PAGE_BREAK_TOKEN = "<<<PAGE_BREAK>>>"

# ---------------------------
# Text preprocessing helpers
# ---------------------------

def slugify(s: str) -> str:
    """ASCII-ish, URL-safe-ish slug."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s or "book"

def preprocess_text(raw_text: str, preserve_pages: bool = False) -> str:
    """
    Remove page artifacts and normalize spacing.
    If preserve_pages=True, replace page markers with PAGE_BREAK_TOKEN (later rendered as an <hr> with page-break).
    """

    text = raw_text

    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 1) Replace or remove obvious page markers like:
    #    "--- Page 17 ---", "— Page 17 —", "Page 17"
    def _page_marker_sub(match):
        return f"\n{PAGE_BREAK_TOKEN}\n" if preserve_pages else "\n"

    page_marker_re = re.compile(
        r"^[ \t]*[-–—]*\s*Page\s+\d+\s*[-–—]*.*$",
        re.IGNORECASE | re.MULTILINE
    )
    text = page_marker_re.sub(_page_marker_sub, text)

    # Sometimes the source uses a bare "-----" between pages
    hrule_re = re.compile(r"^[ \t]*-{2,}[ \t]*$", re.MULTILINE)
    text = hrule_re.sub(_page_marker_sub if preserve_pages else "", text)

    # 2) Remove running headers/footers like:
    #    "xviii  |  Acknowledgments" or "Acknowledgments  |  xix"
    run_hdr_1 = re.compile(r"^[ \t]*[ivxlcdm]+\s*\|\s*.+$", re.IGNORECASE | re.MULTILINE)
    run_hdr_2 = re.compile(r"^[ \t]*.+\s*\|\s*[ivxlcdm]+[ \t]*$", re.IGNORECASE | re.MULTILINE)
    text = run_hdr_1.sub("", text)
    text = run_hdr_2.sub("", text)

    # 3) De-hyphenate line-break splits: "educa-\n tion" -> "education"
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)

    # 4) Collapse lines that are obviously wrapped within a paragraph
    #    Keep double newlines (paragraph breaks), but compress 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip stray spaces on each line
    text = "\n".join(line.rstrip() for line in text.split("\n"))

    return text.strip()

def detect_chapter_boundaries(clean_text: str):
    """
    Find chapter-like headings. Supports:
      - 'Chapter 1', 'CHAPTER V', 'Part II', etc.
      - Standalone ALL-CAPS headings like 'PREFACE', 'ACKNOWLEDGMENTS'
    Returns list of (match_start_index, title_text).
    """
    # Pattern A: Chapter/Part + number (arabic or roman)
    pat_a = r"^(?:Chapter|CHAPTER|Part|PART)\s+(?:\d+|[IVXLCDM]+)\b.*$"

    # Pattern B: Standalone ALL-CAPS lines (letters, digits, spaces and limited punctuation),
    # typically short to medium length.
    pat_b = r"^(?:[A-Z][A-Z0-9 ,\'’:&\-\u2014]{2,})$"

    chapter_pattern = re.compile(f"(?:{pat_a})|(?:{pat_b})", re.MULTILINE)

    matches = []
    for m in chapter_pattern.finditer(clean_text):
        title = m.group(0).strip()
        # Heuristic: avoid treating PAGE_BREAK_TOKEN as a "chapter"
        if PAGE_BREAK_TOKEN in title:
            continue
        # Heuristic: ignore all-caps lines that end with obvious mid-sentence punctuation
        if re.search(r"[.!?]$", title):
            continue
        matches.append((m.start(), title))
    return matches

def split_into_chapters(clean_text: str):
    """
    Use detected chapter boundaries. If none found, return one 'Introduction' chapter.
    If there is content before the first boundary, make it 'Introduction'.
    """
    chapter_matches = detect_chapter_boundaries(clean_text)

    if not chapter_matches:
        return [("Introduction", clean_text)]

    chapters = []

    # Intro before first chapter
    if chapter_matches[0][0] > 0:
        intro_text = clean_text[:chapter_matches[0][0]].strip()
        if intro_text:
            chapters.append(("Introduction", intro_text))

    # Each chapter
    for i, (start, title) in enumerate(chapter_matches):
        title_end = clean_text.find("\n", start)
        if title_end == -1:
            title_end = len(clean_text)
        content_start = title_end + 1
        content_end = chapter_matches[i + 1][0] if i < len(chapter_matches) - 1 else len(clean_text)
        content = clean_text[content_start:content_end].strip()
        if title and content:
            chapters.append((title, content))

    return chapters

# ---------------------------
# EPUB creation
# ---------------------------

def chapters_to_epub_items(book, chapters, preserve_pages: bool):
    items = []
    for i, (chapter_title, chapter_content) in enumerate(chapters):
        chapter_file_name = f"chap_{i+1}.xhtml"

        # Build HTML content
        # Split into paragraphs by blank line, but detect PAGE_BREAK_TOKEN and insert HRs.
        parts = chapter_content.split("\n\n")
        html_chunks = [f"<h1>{html.escape(chapter_title)}</h1>"]

        for part in parts:
            p = part.strip()
            if not p:
                continue
            if p == PAGE_BREAK_TOKEN:
                if preserve_pages:
                    html_chunks.append('<hr class="pagebreak" />')
                # if not preserving, we already removed it earlier
                continue
            # Preserve single newlines as <br> within a paragraph
            escaped_para = html.escape(p).replace("\n", "<br>")
            html_chunks.append(f"<p>{escaped_para}</p>")

        chapter_html = "\n".join(html_chunks)

        chapter = epub.EpubHtml(
            title=chapter_title,
            file_name=chapter_file_name,
            content=chapter_html,
        )
        items.append(chapter)
        book.add_item(chapter)
    return items

def create_epub(book_id, title, author, chapters, output_path: Path, cover_path: str = None, preserve_pages: bool = False):
    book = epub.EpubBook()

    book.set_identifier(book_id)
    book.set_title(title)
    book.add_author(author)

    # Optional cover
    if cover_path:
        cover_file = Path(cover_path)
        if cover_file.exists() and cover_file.is_file():
            with open(cover_file, "rb") as cf:
                # create_page=True adds a proper cover page/document
                book.set_cover(cover_file.name, cf.read(), create_page=True)
        else:
            print(f"Warning: Cover image '{cover_path}' not found; skipping.")

    # Add chapters
    epub_items = chapters_to_epub_items(book, chapters, preserve_pages=preserve_pages)

    # TOC: simple linear structure
    book.toc = list(epub_items)

    # NCX/Nav
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # CSS
    style = '''
    @namespace epub "http://www.idpf.org/2007/ops";
    body { font-family: Times, "Times New Roman", serif; line-height: 1.4; }
    h1 { text-align: left; text-transform: none; font-weight: 600; margin: 1em 0 0.5em 0; }
    p { text-indent: 0; margin: 0 0 0.9em 0; }
    hr.pagebreak { page-break-before: always; break-before: page; border: none; }
    ol { list-style-type: none; }
    nav[epub|type~="toc"] > ol > li > ol { list-style-type: none; }
    '''
    nav_css = epub.EpubItem(
        uid="style_nav",
        file_name="style/nav.css",
        media_type="text/css",
        content=style
    )
    book.add_item(nav_css)

    # Spine
    book.spine = ["nav"] + epub_items

    # Output
    epub.write_epub(str(output_path), book)

# ---------------------------
# CLI / main
# ---------------------------

def parse_args():
    load_dotenv()

    default_output_dir = os.getenv("OUTPUT_DIR", "output")

    parser = argparse.ArgumentParser(description="Convert text to EPUB format")
    parser.add_argument("--in", dest="input", type=str,
                        default=f"{default_output_dir}/innerspace_final.txt",
                        help=f"Input file path (default: {default_output_dir}/innerspace_final.txt)")
    parser.add_argument("--out", dest="output", type=str,
                        default=f"{default_output_dir}/innerspace.epub",
                        help=f"Output file path (default: {default_output_dir}/innerspace.epub)")
    parser.add_argument("--title", dest="title", type=str, help="Book title")
    parser.add_argument("--author", dest="author", type=str, help="Author name")
    parser.add_argument("--bookid", dest="bookid", type=str, help="Override generated book identifier")
    parser.add_argument("--cover", dest="cover", type=str, default=None, help="Path to cover image (optional)")
    parser.add_argument("--preserve-pages", dest="preserve_pages", action="store_true",
                        help="Preserve page breaks from input (insert real EPUB page breaks)")
    return parser.parse_args()

def prompt_nonempty(prompt_text: str) -> str:
    while True:
        val = input(prompt_text).strip()
        if val:
            return val
        print("Please enter a non-empty value.")

def main():
    args = parse_args()

    input_file = Path(args.input)
    output_file = Path(args.output)

    if not input_file.exists():
        print(f"Error: Input file '{input_file}' not found.")
        exit(1)

    # Interactive prompts if missing
    title = args.title or prompt_nonempty("Title: ")
    author = args.author or prompt_nonempty("Author: ")

    if args.bookid:
        book_id = args.bookid.strip()
    else:
        book_id = slugify(f"{title}-{author}")

    cover_path = args.cover
    if cover_path is None:
        cover_path = input("Path to cover image (leave empty for none): ").strip() or None

    print("Converting text to EPUB")
    print(f"Input:  {input_file}")
    print(f"Output: {output_file}")
    print(f"Title:  {title}")
    print(f"Author: {author}")
    print(f"BookID: {book_id}")
    print(f"Cover:  {cover_path or 'None'}")
    print(f"Preserve page breaks: {'Yes' if args.preserve_pages else 'No'}")

    with open(input_file, "r", encoding="utf-8") as f:
        raw_text = f.read()

    cleaned = preprocess_text(raw_text, preserve_pages=args.preserve_pages)
    chapters = split_into_chapters(cleaned)
    print(f"Parsed {len(chapters)} chapters")

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    create_epub(
        book_id=book_id,
        title=title,
        author=author,
        chapters=chapters,
        output_path=output_file,
        cover_path=cover_path,
        preserve_pages=args.preserve_pages
    )

    print("EPUB conversion completed!")

if __name__ == "__main__":
    main()

