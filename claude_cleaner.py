#!/usr/bin/env python3
"""
claude_cleaner.py - Claude-based refinement for OCR cleaned text
Uses Anthropic Claude API to correct spelling, punctuation and OCR errors
"""

import os
import argparse
from dotenv import load_dotenv
from anthropic import Anthropic
from tqdm import tqdm
from pathlib import Path
import time
import re
from concurrent.futures import ThreadPoolExecutor
import threading

# Optional: if you have tiktoken installed we'll use it for a rough estimate.
# (Claude doesn't use cl100k_base, but this is "good enough" for budgeting)
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    print("Warning: tiktoken not available, using word count estimation")


def count_tokens(text, model="claude-sonnet-4-20250514"):
    """
    Rough token estimation for budgeting/splitting.
    NOTE: This is approximate. Claude's tokenizer differs from tiktoken.
    """
    if TIKTOKEN_AVAILABLE:
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception as e:
            print(f"Warning: tiktoken error {e}, falling back to estimation")
            word_count = len(text.split())
            return int(word_count / 0.75)
    else:
        # Conservative estimation: ~0.6 words per token
        word_count = len(text.split())
        return int(word_count / 0.6)


def split_text_into_chunks(text, max_tokens=2500, model="claude-sonnet-4-20250514"):
    """
    Split text into larger paragraph-based chunks for better context and efficiency.
    Each chunk contains several paragraphs up to the token limit (approximate).
    """
    paragraphs = text.split('\n\n')

    chunks = []
    current_chunk = []
    current_tokens = 0

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        para_tokens = count_tokens(paragraph, model)

        if para_tokens > max_tokens:
            # Flush current
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk, current_tokens = [], 0

            # Split big paragraph by sentences
            sentences = re.split(r'(?<=[.!?])\s+', paragraph)
            temp_chunk, temp_tokens = [], 0
            for sentence in sentences:
                sentence_tokens = count_tokens(sentence, model)
                if temp_tokens + sentence_tokens > max_tokens and temp_chunk:
                    chunks.append(' '.join(temp_chunk))
                    temp_chunk, temp_tokens = [sentence], sentence_tokens
                else:
                    temp_chunk.append(sentence)
                    temp_tokens += sentence_tokens
            if temp_chunk:
                chunks.append(' '.join(temp_chunk))

        elif current_tokens + para_tokens > max_tokens and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk, current_tokens = [paragraph], para_tokens
        else:
            current_chunk.append(paragraph)
            current_tokens += para_tokens

    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks


# Global cost/usage tracking
cost_lock = threading.Lock()
total_cost = 0.0
total_input_tokens = 0
total_output_tokens = 0

# Claude pricing (per 1K tokens). Adjust if needed via env or below.
# Defaults reflect common public prices; they may change.
PRICING = {
    # 2025 Sonnet 4
    'claude-sonnet-4-20250514': {'input': 0.0030, 'output': 0.0150},
    # Sonnet 3.7
    'claude-3-7-sonnet-20250219': {'input': 0.0030, 'output': 0.0150},
    # Sonnet 3.5 (deprecated but still around in some accounts)
    'claude-3-5-sonnet-20240620': {'input': 0.0030, 'output': 0.0150},
    # Haiku 3.5 (updated pricing late 2024)
    'claude-3-5-haiku-20241022': {'input': 0.0008, 'output': 0.0040},
    # Opus 3
    'claude-3-opus-20240229': {'input': 0.0150, 'output': 0.0750},
}

def calculate_cost(input_tokens, output_tokens, model):
    """Calculate approximate cost based on token usage."""
    p = PRICING.get(model) or PRICING.get('claude-sonnet-4-20250514')
    return input_tokens * p['input'] / 1000.0 + output_tokens * p['output'] / 1000.0


def _extract_text_from_message(message):
    """
    Claude Messages API returns a list of content blocks.
    We concatenate all text blocks.
    """
    pieces = []
    for block in getattr(message, "content", []) or []:
        # New SDK returns objects with .type/.text; older may be dicts
        if getattr(block, "type", None) == "text" and getattr(block, "text", None) is not None:
            pieces.append(block.text)
        elif isinstance(block, dict) and block.get("type") == "text":
            pieces.append(block.get("text", ""))
    return "".join(pieces).strip()


def call_claude_api(client: Anthropic, text, model="claude-sonnet-4-20250514", retries=3, max_output_tokens=4000):
    """
    Call Anthropic Claude API with retry logic and usage/cost tracking.
    """
    global total_cost, total_input_tokens, total_output_tokens

    system_prompt = (
        "You are a proof-reader. Return the text corrected for spelling, "
        "punctuation and OCR errors only. Preserve all headings and blank lines. "
        "DO NOT summarise or omit content."
    )

    for attempt in range(retries):
        try:
            message = client.messages.create(
                model=model,
                system=system_prompt,
                messages=[{"role": "user", "content": text}],
                temperature=0.1,
                max_tokens=max_output_tokens,  # output tokens
            )

            # Usage tracking
            usage = getattr(message, "usage", None)
            if usage:
                input_tokens = getattr(usage, "input_tokens", 0)
                output_tokens = getattr(usage, "output_tokens", 0)
            else:
                input_tokens = output_tokens = 0

            cost = calculate_cost(input_tokens, output_tokens, model)

            with cost_lock:
                total_cost += cost
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens

            return _extract_text_from_message(message) or text

        except Exception as e:
            wait_time = 2 ** attempt
            print(f"\nError: {e}")
            if attempt < retries - 1:
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print("Failed after all retries.")
                return text  # fall back to original on failure


def process_text(input_file, output_file, model="claude-sonnet-4-20250514"):
    """
    Process the cleaned text file with Claude correction using concurrency.
    """
    global total_cost, total_input_tokens, total_output_tokens
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0

    # Configuration
    max_tokens_per_chunk = int(os.getenv('MAX_TOKENS_PER_CHUNK', '3000'))  # approx input tokens per chunk
    max_cost_limit = float(os.getenv('MAX_COST_LIMIT', '10.00'))
    track_usage = os.getenv('TRACK_USAGE', 'true').lower() == 'true'
    max_output_tokens = int(os.getenv('MAX_OUTPUT_TOKENS', '4000'))  # per-response output cap

    # Read input
    print(f"Reading {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        text = f.read()

    print(f"Total characters: {len(text):,}")
    total_tokens_est = count_tokens(text, model)
    print(f"Estimated input tokens: {total_tokens_est:,}")

    # Pre-flight cost estimate
    if track_usage:
        estimated_cost = calculate_cost(total_tokens_est, int(total_tokens_est * 0.5), model)
        print(f"Estimated cost: ${estimated_cost:.4f}")
        if estimated_cost > max_cost_limit:
            print(f"WARNING: Estimated cost (${estimated_cost:.4f}) exceeds limit (${max_cost_limit:.2f})")
            response = input("Continue? (y/N): ")
            if response.lower() != 'y':
                print("Processing cancelled.")
                return

    # Chunking
    print("\nSplitting text into chunks...")
    chunks = split_text_into_chunks(text, max_tokens=max_tokens_per_chunk, model=model)
    print(f"Created {len(chunks)} chunks")

    chunk_sizes = [count_tokens(chunk, model) for chunk in chunks]
    print(f"Chunk sizes - Min: {min(chunk_sizes)}, Max: {max(chunk_sizes)}, Avg: {sum(chunk_sizes)//len(chunk_sizes)}")

    # Process with concurrency
    batch_size = int(os.getenv('BATCH_SIZE', '5'))
    processed_chunks = [None] * len(chunks)
    start_time = time.time()

    # Create a single client reused across threads
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    with ThreadPoolExecutor(max_workers=batch_size) as executor:
        for batch_start in tqdm(range(0, len(chunks), batch_size), desc="Processing batches"):
            batch_end = min(batch_start + batch_size, len(chunks))
            futures = []
            for idx in range(batch_start, batch_end):
                futures.append((idx, executor.submit(
                    call_claude_api, client, chunks[idx], model, 3, max_output_tokens
                )))

            for idx, fut in futures:
                try:
                    processed_chunks[idx] = fut.result(timeout=180)
                except Exception as e:
                    print(f"\nError processing chunk {idx}: {e}")
                    processed_chunks[idx] = chunks[idx]

            with cost_lock:
                current_cost = total_cost
                current_input_tokens = total_input_tokens
                current_output_tokens = total_output_tokens

            elapsed = time.time() - start_time
            chunks_done = batch_end
            rate = chunks_done / elapsed if elapsed > 0 else 0
            remaining = len(chunks) - chunks_done
            eta = remaining / rate if rate > 0 else 0

            if chunks_done > 0:
                avg_cost_per_chunk = current_cost / chunks_done
                estimated_total_cost = avg_cost_per_chunk * len(chunks)
            else:
                estimated_total_cost = 0

            print(f"\n{'='*60}")
            print(f"PROGRESS: {chunks_done}/{len(chunks)} chunks ({chunks_done/len(chunks)*100:.1f}%)")
            print(f"COST SO FAR: ${current_cost:.4f}")
            print(f"ESTIMATED TOTAL COST: ${estimated_total_cost:.4f}")
            print(f"TOKENS: {current_input_tokens:,} in, {current_output_tokens:,} out")
            print(f"RATE: {rate*60:.1f} chunks/hour")
            print(f"ETA: {eta/60:.1f} minutes remaining")
            print(f"{'='*60}")

    final_text = '\n\n'.join(processed_chunks)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(final_text)

    elapsed_time = time.time() - start_time
    print(f"\n=== PROCESSING COMPLETE ===")
    print(f"Processed {len(chunks)} chunks in {elapsed_time/60:.1f} minutes")
    print(f"Input tokens: {total_input_tokens:,}")
    print(f"Output tokens: {total_output_tokens:,}")
    print(f"Total cost: ${total_cost:.4f}")
    print(f"Average cost per chunk: ${total_cost/len(chunks):.4f}")
    print(f"Wrote {len(final_text):,} characters to {output_file}")


def main():
    """CLI entry point."""
    load_dotenv()

    # Defaults
    default_output_dir = os.getenv('OUTPUT_DIR', 'output')
    default_model = os.getenv('AI_MODEL', 'claude-sonnet-4-20250514')

    # Check API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not found in environment variables.")
        print("Please create a .env file with your Anthropic API key.")
        exit(1)

    parser = argparse.ArgumentParser(
        description='Refine cleaned OCR text using Anthropic Claude'
    )
    parser.add_argument(
        '--in',
        dest='input',
        type=str,
        default=f'{default_output_dir}/innerspace_clean.txt',
        help=f'Input file path (default: {default_output_dir}/innerspace_clean.txt)'
    )
    parser.add_argument(
        '--out',
        dest='output',
        type=str,
        default=f'{default_output_dir}/innerspace_final.txt',
        help=f'Output file path (default: {default_output_dir}/innerspace_final.txt)'
    )
    parser.add_argument(
        '--model',
        type=str,
        default=default_model,
        help=f'Claude model to use (default: {default_model})'
    )

    args = parser.parse_args()

    input_file = Path(args.input)
    output_file = Path(args.output)

    if not input_file.exists():
        print(f"Error: Input file '{input_file}' not found.")
        exit(1)

    print(f"Claude Text Refinement")
    print(f"Input: {input_file}")
    print(f"Output: {output_file}")
    print(f"Model: {args.model}")
    print()

    process_text(input_file, output_file, model=args.model)


if __name__ == "__main__":
    main()

