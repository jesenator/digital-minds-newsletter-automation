import os, json, re, http.client
from concurrent.futures import ThreadPoolExecutor, as_completed
from cache import cached

MAX_TEXT_LENGTH = 200_000
IMG_RE = re.compile(r'!?\[([^\]]*)\]\([^)]*\)', re.DOTALL)


def _clean_text(text):
  text = IMG_RE.sub('', text)
  text = re.sub(r'\n{3,}', '\n\n', text)
  return text[:MAX_TEXT_LENGTH]


@cached("scrape", expiry=60*60*24*7)
def _scrape_webpage(url):
  conn = http.client.HTTPSConnection("scrape.serper.dev")
  payload = json.dumps({"url": url, "includeMarkdown": True})
  headers = {"X-API-KEY": os.environ["SERPER_API_KEY"], "Content-Type": "application/json"}
  conn.request("POST", "/", payload, headers)
  res = conn.getresponse()
  return json.loads(res.read().decode("utf-8"))


def _is_youtube(url):
  return "youtube.com" in url or "youtu.be" in url


def _youtube_video_id(url):
  if "youtu.be/" in url:
    return url.split("youtu.be/")[1].split("?")[0].split("&")[0]
  m = re.search(r'[?&]v=([^&]+)', url)
  return m.group(1) if m else None


@cached("yt-dlp", expiry=60*60*24*30)
def _fetch_youtube_info(url):
  import yt_dlp
  vid = _youtube_video_id(url)
  if not vid:
    return None
  try:
    with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
      info = ydl.extract_info(url, download=False)
      return {
        "title": info.get("title", ""),
        "description": info.get("description", ""),
        "channel": info.get("uploader", ""),
        "upload_date": info.get("upload_date", ""),
        "duration": info.get("duration", 0),
        "tags": info.get("tags", []),
      }
  except Exception as e:
    print(f"yt-dlp failed for {url}: {e}")
    return None


def fetch_one(url):
  try:
    result = _scrape_webpage(url)
    text = result.get("markdown") or result.get("text") or ""
    title = (result.get("metadata") or {}).get("title", "")
    text = _clean_text(text)

    if _is_youtube(url):
      info = _fetch_youtube_info(url)
      if info:
        title = info.get("title") or title
        channel = info.get("channel", "")
        desc = info.get("description", "")
        date = info.get("upload_date", "")
        tags = ", ".join(info.get("tags", [])[:10])
        parts = [f"YouTube video: {title}"]
        if channel: parts.append(f"Channel: {channel}")
        if date: parts.append(f"Upload date: {date}")
        if tags: parts.append(f"Tags: {tags}")
        if desc: parts.append(f"\nDescription:\n{desc}")
        text = "\n".join(parts)

    ok = bool(text and len(text) > 50)
    return {"url": url, "title": title, "ok": ok, "length": len(text), "text": text, "error": None}
  except Exception as e:
    return {"url": url, "title": "", "ok": False, "length": 0, "text": "", "error": str(e)}


def fetch_all(urls, max_links=None, workers=20):
  urls = urls[:max_links]
  results = [None] * len(urls)
  with ThreadPoolExecutor(max_workers=workers) as pool:
    futures = {pool.submit(fetch_one, url): i for i, url in enumerate(urls)}
    for future in as_completed(futures):
      idx = futures[future]
      results[idx] = future.result()
  return results
