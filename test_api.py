from openai_cleaner import split_text_into_chunks, call_openai_api
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

with open('output/innerspace_clean.txt', 'r', encoding='utf-8') as f:
    text = f.read()

chunks = split_text_into_chunks(text, max_tokens=2000, model='gpt-4.1')
print(f'Testing with first chunk ({len(chunks[0])} chars)...')

client = OpenAI()
result = call_openai_api(client, chunks[0][:500], model='gpt-4.1')  # Test with just first 500 chars
print("API call successful!")
print(f"Original: {chunks[0][:200]}...")
print(f"Processed: {result[:200]}...")
