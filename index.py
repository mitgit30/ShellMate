from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key= ""
)

response = client.chat.completions.create(
    model="nvidia/nemotron-3-ultra-550b-a55b:free",
    messages=[{"role": "user", "content": "Check disk usage"}]
)
print(response.choices[0].message.content)