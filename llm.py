import os
from openai import OpenAI
from cache import cached


@cached("llm", expiry=60*60*24*7)
def ask(prompt, model="google/gemini-3-flash-preview", timeout=30, max_tokens=2000, temperature=0.5):
  client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
  )
  response = client.chat.completions.create(
    model=model,
    temperature=temperature,
    max_completion_tokens=max_tokens,
    messages=[{"role": "user", "content": prompt}],
    timeout=timeout,
  )
  return response.choices[0].message.content
