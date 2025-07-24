from openai_cleaner import split_text_into_chunks, count_tokens

with open('output/innerspace_clean.txt', 'r', encoding='utf-8') as f:
    text = f.read()

chunks = split_text_into_chunks(text, max_tokens=1500, model='gpt-4.1')
print(f'Total chunks: {len(chunks)}')
print(f'First chunk tokens: {count_tokens(chunks[0], "gpt-4.1")}')
print(f'First chunk preview: {chunks[0][:200]}...')

# Test with a very small chunk to ensure API call works
if len(chunks) > 0:
    print(f"\nTesting first few chunks:")
    for i in range(min(3, len(chunks))):
        tokens = count_tokens(chunks[i], "gpt-4.1")
        print(f"Chunk {i+1}: {tokens} tokens, length: {len(chunks[i])} chars")
