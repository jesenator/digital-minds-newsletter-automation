# Run: streamlit run app.py
import streamlit as st
from dotenv import load_dotenv
load_dotenv()

from concurrent.futures import ThreadPoolExecutor, as_completed
from scraper import fetch_one
from pipeline import NewsletterPipeline, NO_CONTENT

DEFAULT_REFERENCE_URL = "https://www.digitalminds.news/p/the-vatican-ai-legal-personhood-and"

st.set_page_config(page_title="Digital Minds Newsletter", layout="wide")
st.title("Digital Minds Newsletter Builder")

max_links = st.sidebar.slider("Max links", 10, 500, 100)

reference_url = st.text_input(
  "Reference newsletter URL (scraped for style/context)",
  value=DEFAULT_REFERENCE_URL,
)

links_text = st.text_area("Paste links (one per line)", height=250)
uploaded = st.file_uploader("Or upload a .txt file with links", type=["txt"])
if uploaded:
  links_text = uploaded.read().decode("utf-8")

if st.button("Run Pipeline", type="primary", use_container_width=True):
  urls = [l.strip() for l in links_text.strip().splitlines() if l.strip()] if links_text else []
  if not urls:
    st.error("No links provided.")
    st.stop()
  urls = urls[:max_links]
  n = len(urls)

  reference_text = ""
  if reference_url.strip():
    with st.spinner("Scraping reference newsletter..."):
      ref = fetch_one(reference_url.strip())
      if ref["ok"]:
        reference_text = ref["text"]
        st.success(f"Reference newsletter scraped ({ref['length']:,} chars)")
      else:
        st.warning(f"Could not scrape reference newsletter: {ref['error']}")

  pipeline = NewsletterPipeline(reference_text)

  progress = st.progress(0, text=f"Fetching 0/{n}...")
  results = [None] * n
  done = 0
  with ThreadPoolExecutor(max_workers=15) as pool:
    futs = {pool.submit(fetch_one, u): i for i, u in enumerate(urls)}
    for f in as_completed(futs):
      results[futs[f]] = f.result()
      done += 1
      progress.progress(done / n * 0.5, text=f"Fetching {done}/{n}...")

  ok_items = [(i, r) for i, r in enumerate(results) if r["ok"]]
  ok_n = len(ok_items)
  st.info(f"Fetched {ok_n}/{n} articles successfully")

  out = [{**r, "summary": None} for r in results]
  done = 0
  if ok_n > 0:
    progress.progress(0.5, text=f"Summarizing 0/{ok_n}...")
    with ThreadPoolExecutor(max_workers=10) as pool:
      futs = {pool.submit(pipeline.summarize_one, r["url"], r["text"]): i for i, r in ok_items}
      for f in as_completed(futs):
        idx = futs[f]
        summary = f.result()
        usable = NO_CONTENT not in (summary or "")
        out[idx] = {**results[idx], "summary": summary if usable else None, "usable": usable}
        done += 1
        progress.progress(0.5 + done / ok_n * 0.5, text=f"Summarizing {done}/{ok_n}...")

  results = out
  progress.progress(1.0, text="Done!")

  bad = [r for r in results if r.get("ok") and not r.get("usable", True)]
  failed = [r for r in results if not r.get("ok")]
  usable = [r for r in results if r.get("ok") and r.get("usable", True)]

  c1, c2, c3 = st.columns(3)
  c1.metric("Usable", len(usable))
  c2.metric("Unusable content", len(bad))
  c3.metric("Failed to fetch", len(failed))

  if bad or failed:
    with st.expander("Excluded links"):
      for r in bad:
        st.text(f"[unusable]  {r['url']}")
      for r in failed:
        st.text(f"[failed]    {r['url']}")

  prompt = pipeline.build_prompt(results)

  st.subheader("Generated Prompt")
  st.code(prompt, language=None, wrap_lines=True)
  st.download_button("Download prompt.txt", prompt, file_name="prompt.txt", use_container_width=True)
