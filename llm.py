import os, hashlib
from openai import OpenAI
from cache import cached, FileCache


@cached("llm", expiry=60*60*24*7)
def ask(prompt, model="google/gemini-3-flash-preview", timeout=30, max_tokens=2000, temperature=0.5, thinking_budget=None):
  client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
  )
  kwargs = dict(
    model=model,
    temperature=temperature,
    max_completion_tokens=max_tokens,
    messages=[{"role": "user", "content": prompt}],
    timeout=timeout,
  )
  if thinking_budget:
    kwargs["extra_body"] = {"reasoning": {"max_tokens": thinking_budget}}
    kwargs["temperature"] = 1
  response = client.chat.completions.create(**kwargs)
  return response.choices[0].message.content


def ask_stream(prompt, model="google/gemini-3-flash-preview", timeout=30, max_tokens=2000, temperature=0.5, thinking_budget=None):
  """Yields text chunks as they arrive. Caches the full result when done."""
  cache = FileCache("llm")
  key = hashlib.md5(str(((prompt,), {"model": model, "timeout": timeout, "max_tokens": max_tokens, "temperature": temperature, "thinking_budget": thinking_budget})).encode()).hexdigest()
  hit = cache.get(key)
  if hit is not None:
    yield hit
    return

  client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
  )
  kwargs = dict(
    model=model,
    temperature=temperature,
    max_completion_tokens=max_tokens,
    messages=[{"role": "user", "content": prompt}],
    timeout=timeout,
    stream=True,
  )
  if thinking_budget:
    kwargs["extra_body"] = {"reasoning": {"max_tokens": thinking_budget}}
    kwargs["temperature"] = 1
  stream = client.chat.completions.create(**kwargs)
  full = []
  for chunk in stream:
    delta = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta.content else None
    if delta:
      full.append(delta)
      yield delta
  cache.set(key, "".join(full), 60*60*24*7)
