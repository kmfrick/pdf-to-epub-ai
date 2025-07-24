#!/usr/bin/env python3
"""
openai_cleaner.py - GPT-4.1 refinement for OCR cleaned text
Uses OpenAI API to correct spelling, punctuation and OCR errors
"""

import os
import argparse
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm
from pathlib import Path
import time
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    print("Warning: tiktoken not available, using word count estimation")


def count_tokens(text, model="gpt-4.1"):
    """
    Count tokens in text using tiktoken if available, otherwise estimate.
    
    Args:
        text (str): Text to count tokens for
        model (str): Model name for tokenizer
        
    Returns:
        int: Token count
    """
    if TIKTOKEN_AVAILABLE:
        try:
            # Use cl100k_base encoding for GPT-4 models
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception as e:
            print(f"Warning: tiktoken error {e}, falling back to estimation")
            # Fallback estimation
            word_count = len(text.split())
            return int(word_count / 0.75)
    else:
        # More conservative estimation: ~0.6 words per token
        word_count = len(text.split())
        return int(word_count / 0.6)


def split_text_into_chunks(text, max_tokens=2500, model="gpt-4.1"):
    """
    Split text into larger paragraph-based chunks for better context and efficiency.
    Each chunk contains several paragraphs up to the token limit.
    
    Args:
        text (str): Text to split
        max_tokens (int): Maximum tokens per chunk (increased for better context)
        model (str): Model name for tokenizer
        
    Returns:
        list: List of text chunks
    """
    # Split into paragraphs first
    paragraphs = text.split('\n\n')
    
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
            
        # Estimate tokens for this paragraph
        para_tokens = count_tokens(paragraph, model)
        
        # If this single paragraph is too large, split it further
        if para_tokens > max_tokens:
            # If we have accumulated content, save it first
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_tokens = 0
            
            # Split large paragraph by sentences
            sentences = re.split(r'(?<=[.!?])\s+', paragraph)
            temp_chunk = []
            temp_tokens = 0
            
            for sentence in sentences:
                sentence_tokens = count_tokens(sentence, model)
                
                if temp_tokens + sentence_tokens > max_tokens and temp_chunk:
                    chunks.append(' '.join(temp_chunk))
                    temp_chunk = [sentence]
                    temp_tokens = sentence_tokens
                else:
                    temp_chunk.append(sentence)
                    temp_tokens += sentence_tokens
            
            if temp_chunk:
                chunks.append(' '.join(temp_chunk))
        
        # If adding this paragraph would exceed limit
        elif current_tokens + para_tokens > max_tokens and current_chunk:
            # Save current chunk
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = [paragraph]
            current_tokens = para_tokens
        else:
            # Add paragraph to current chunk
            current_chunk.append(paragraph)
            current_tokens += para_tokens
    
    # Don't forget the last chunk
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    
    return chunks


# Global cost tracking
cost_lock = threading.Lock()
total_cost = 0.0
total_input_tokens = 0
total_output_tokens = 0

# GPT-4.1 pricing (as of 2024)
PRICING = {
    'gpt-4': {'input': 0.03 / 1000, 'output': 0.06 / 1000},
    'gpt-4.1': {'input': 0.002 / 1000, 'output': 0.008 / 1000}, 
    'gpt-4o': {'input': 0.005 / 1000, 'output': 0.015 / 1000},
}

def calculate_cost(input_tokens, output_tokens, model):
    """Calculate the cost of API call based on token usage."""
    if model in PRICING:
        input_cost = input_tokens * PRICING[model]['input']
        output_cost = output_tokens * PRICING[model]['output']
        return input_cost + output_cost
    else:
        # Default to GPT-4 pricing
        return (input_tokens * PRICING['gpt-4']['input'] + 
                output_tokens * PRICING['gpt-4']['output'])

def call_openai_api(client, text, model="gpt-4.1", retries=3):
    """
    Call OpenAI's API with retry logic and cost tracking.

    Args:
        client: OpenAI client instance
        text (str): Text to be corrected
        model (str): Model to use
        retries (int): Number of retries on failure

    Returns:
        str: Corrected text returned by OpenAI
    """
    global total_cost, total_input_tokens, total_output_tokens
    
    system_prompt = (
        "You are a proof-reader. Return the text corrected for spelling, "
        "punctuation and OCR errors only. Preserve all headings and blank lines. "
        "DO NOT summarise or omit content."
    )
    
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.1,  # Low temperature for consistency
                max_tokens=4000  # Allow room for expansion
            )
            
            # Track costs
            usage = response.usage
            input_tokens = usage.prompt_tokens
            output_tokens = usage.completion_tokens
            cost = calculate_cost(input_tokens, output_tokens, model)
            
            with cost_lock:
                global total_cost, total_input_tokens, total_output_tokens
                total_cost += cost
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            wait_time = 2 ** attempt
            print(f"\nError: {e}")
            if attempt < retries - 1:
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print("Failed after all retries.")
                return text  # Return original text if all retries fail

def process_chunk_batch(client, chunk_batch, model):
    """
    Process a batch of chunks concurrently.
    
    Args:
        client: OpenAI client
        chunk_batch: List of (index, chunk_text) tuples
        model: Model to use
        
    Returns:
        List of (index, processed_text) tuples
    """
    results = []
    for chunk_idx, chunk_text in chunk_batch:
        processed_text = call_openai_api(client, chunk_text, model=model)
        results.append((chunk_idx, processed_text))
    return results


def process_text(input_file, output_file, model="gpt-4.1"):
    """
    Process the cleaned text file with OpenAI's API correction using concurrency.

    Args:
        input_file (Path): Path to input file
        output_file (Path): Path to output file
        model (str): Model to use
    """
    global total_cost, total_input_tokens, total_output_tokens
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    
    # Read input file
    print(f"Reading {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        text = f.read()
    
    print(f"Total characters: {len(text):,}")
    total_tokens = count_tokens(text, model)
    print(f"Estimated input tokens: {total_tokens:,}")
    
    # Split into larger chunks for better context
    print("\nSplitting text into chunks...")
    chunks = split_text_into_chunks(text, max_tokens=2500, model=model)
    print(f"Created {len(chunks)} chunks")
    
    # Show chunk size distribution
    chunk_sizes = [count_tokens(chunk, model) for chunk in chunks]
    print(f"Chunk sizes - Min: {min(chunk_sizes)}, Max: {max(chunk_sizes)}, Avg: {sum(chunk_sizes)//len(chunk_sizes)}")
    
    # Process chunks in batches of 5 with concurrency
    batch_size = 5
    processed_chunks = [None] * len(chunks)  # Pre-allocate to maintain order
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=batch_size) as executor:
        # Process chunks in batches
        for batch_start in tqdm(range(0, len(chunks), batch_size), desc="Processing batches"):
            batch_end = min(batch_start + batch_size, len(chunks))
            batch_chunks = [(i, chunks[i]) for i in range(batch_start, batch_end)]
            
            # Submit batch for processing
            futures = []
            for chunk_idx, chunk_text in batch_chunks:
                future = executor.submit(call_openai_api, OpenAI(), chunk_text, model)
                futures.append((chunk_idx, future))
            
            # Collect results
            for chunk_idx, future in futures:
                try:
                    processed_chunks[chunk_idx] = future.result(timeout=120)  # 2 minute timeout
                except Exception as e:
                    print(f"\nError processing chunk {chunk_idx}: {e}")
                    processed_chunks[chunk_idx] = chunks[chunk_idx]  # Use original on error
            
            # Show detailed progress with cost breakdown
            with cost_lock:
                current_cost = total_cost
                current_input_tokens = total_input_tokens
                current_output_tokens = total_output_tokens
            
            elapsed = time.time() - start_time
            chunks_done = min(batch_end, len(chunks))
            rate = chunks_done / elapsed if elapsed > 0 else 0
            remaining = len(chunks) - chunks_done
            eta = remaining / rate if rate > 0 else 0
            
            # Estimate total cost based on current progress
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
    
    # Combine processed chunks
    final_text = '\n\n'.join(processed_chunks)
    
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Write output
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(final_text)
    
    # Final statistics
    elapsed_time = time.time() - start_time
    print(f"\n=== PROCESSING COMPLETE ===")
    print(f"Processed {len(chunks)} chunks in {elapsed_time/60:.1f} minutes")
    print(f"Input tokens: {total_input_tokens:,}")
    print(f"Output tokens: {total_output_tokens:,}")
    print(f"Total cost: ${total_cost:.4f}")
    print(f"Average cost per chunk: ${total_cost/len(chunks):.4f}")
    print(f"Wrote {len(final_text):,} characters to {output_file}")


def main():
    """Main entry point with CLI argument handling."""
    load_dotenv()
    
    # Set API key if needed (new client will use it from environment)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not found in environment variables.")
        print("Please create a .env file with your OpenAI API key.")
        exit(1)

    parser = argparse.ArgumentParser(
        description='Refine cleaned OCR text using OpenAI GPT-4.1'
    )
    parser.add_argument(
        '--in', 
        dest='input',
        type=str,
        default='output/innerspace_clean.txt',
        help='Input file path (default: output/innerspace_clean.txt)'
    )
    parser.add_argument(
        '--out',
        dest='output',
        type=str,
        default='output/innerspace_final.txt',
        help='Output file path (default: output/innerspace_final.txt)'
    )
    parser.add_argument(
        '--model',
        type=str,
        default='gpt-4.1',
        help='OpenAI model to use (default: gpt-4.1)'
    )

    args = parser.parse_args()

    input_file = Path(args.input)
    output_file = Path(args.output)
    
    if not input_file.exists():
        print(f"Error: Input file '{input_file}' not found.")
        exit(1)

    print(f"OpenAI Text Refinement")
    print(f"Input: {input_file}")
    print(f"Output: {output_file}")
    print(f"Model: {args.model}")
    print()

    process_text(input_file, output_file, model=args.model)


if __name__ == "__main__":
    main()
