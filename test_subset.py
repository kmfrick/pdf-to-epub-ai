from openai_cleaner import split_text_into_chunks, call_openai_api, count_tokens
from openai import OpenAI
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()
client = OpenAI()

with open('output/innerspace_clean.txt', 'r', encoding='utf-8') as f:
    text = f.read()

chunks = split_text_into_chunks(text, max_tokens=1000, model='gpt-4.1')
print(f'Processing first 1 chunk out of {len(chunks)} total...')

# Process first 1 chunk only
processed_chunks = []
for i, chunk in enumerate(tqdm(chunks[:1], desc="Processing test chunks")):
    print(f"\nProcessing chunk {i+1}/1 ({count_tokens(chunk, 'gpt-4.1'):,} tokens)...")
    processed_chunk = call_openai_api(client, chunk, model='gpt-4.1')
    processed_chunks.append(processed_chunk)

# Combine and save test result
final_text = '\n\n'.join(processed_chunks)
with open('output/innerspace_test.txt', 'w', encoding='utf-8') as f:
    f.write(final_text)

print(f"\nTest completed! Wrote {len(final_text):,} characters to output/innerspace_test.txt")
