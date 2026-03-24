import os, hashlib
from openai import OpenAI
from cache import cached, FileCache


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


def ask_stream(prompt, model="google/gemini-3-flash-preview", timeout=30, max_tokens=2000, temperature=0.5):
  """Yields text chunks as they arrive. Caches the full result when done."""
  cache = FileCache("llm")
  key = hashlib.md5(str(((prompt,), {"model": model, "timeout": timeout, "max_tokens": max_tokens, "temperature": temperature})).encode()).hexdigest()
  hit = cache.get(key)
  if hit is not None:
    yield hit
    return

  client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
  )
  stream = client.chat.completions.create(
    model=model,
    temperature=temperature,
    max_completion_tokens=max_tokens,
    messages=[{"role": "user", "content": prompt}],
    timeout=timeout,
    stream=True,
  )
  full = []
  for chunk in stream:
    delta = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta.content else None
    if delta:
      full.append(delta)
      yield delta
  cache.set(key, "".join(full), 60*60*24*7)
