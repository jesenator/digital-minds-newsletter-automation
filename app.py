# Run: streamlit run app.py
import os
import streamlit as st
from dotenv import load_dotenv
load_dotenv()

from pipeline import NewsletterPipeline

DEFAULT_REFERENCE_URL = "https://www.digitalminds.news/p/the-vatican-ai-legal-personhood-and"
TEST_LINKS_FILE = "newsletter-1-links.txt"

st.set_page_config(page_title="Digital Minds Newsletter", layout="wide")

def check_password():
  if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
  if st.session_state.authenticated:
    return True
  st.title("Digital Minds Newsletter Builder")
  password = st.text_input("Password", type="password")
  if not password:
    st.stop()
  if password == os.environ.get("APP_PASSWORD", ""):
    st.session_state.authenticated = True
    st.rerun()
  else:
    st.error("Incorrect password.")
    st.stop()

check_password()

st.title("Digital Minds Newsletter Builder")

max_links = 500

reference_url = st.text_input(
  "Reference newsletter URL (scraped for style/context)",
  value=DEFAULT_REFERENCE_URL,
)

link_sources = ["Paste", "Upload file"]
if os.path.exists(TEST_LINKS_FILE):
  link_sources.append("Load from newsletter #1")
link_source = st.radio("Link source", link_sources, horizontal=True)

links_text = ""
if link_source == "Paste":
  links_text = st.text_area("Paste links (one per line)", height=250)
elif link_source == "Upload file":
  uploaded = st.file_uploader("Upload a .txt file with links", type=["txt"])
  if uploaded:
    links_text = uploaded.read().decode("utf-8")
else:
  with open(TEST_LINKS_FILE) as f:
    links_text = f.read()
  n_links = len([l for l in links_text.strip().splitlines() if l.strip()])
  st.caption(f"Loaded {n_links} links from `{TEST_LINKS_FILE}`")

if st.button("Run Pipeline", type="primary", use_container_width=True):
  urls = [l.strip() for l in links_text.strip().splitlines() if l.strip()] if links_text else []
  if not urls:
    st.error("No links provided.")
    st.stop()

  reference_text = ""
  if reference_url.strip():
    with st.spinner("Scraping reference newsletter..."):
      reference_text = NewsletterPipeline.fetch_reference(reference_url.strip())
      if reference_text:
        st.success(f"Reference newsletter scraped ({len(reference_text):,} chars)")
      else:
        st.warning("Could not scrape reference newsletter")

  pipeline = NewsletterPipeline(reference_text)
  progress = st.progress(0)

  for done, total in pipeline.fetch(urls, max_links):
    progress.progress(done / total * 0.5, text=f"Fetching {done}/{total}...")
  results = pipeline.fetch_results

  ok_n = sum(1 for r in results if r["ok"])
  st.info(f"Fetched {ok_n}/{len(results)} articles successfully")

  for done, total in pipeline.summarize(results):
    progress.progress(0.5 + done / total * 0.5, text=f"Summarizing {done}/{total}...")
  results = pipeline.summarize_results
  progress.progress(1.0, text="Done!")

  s = pipeline.stats(results)
  c1, c2, c3 = st.columns(3)
  c1.metric("Usable", len(s["usable"]))
  c2.metric("Unusable content", len(s["unusable"]))
  c3.metric("Failed to fetch", len(s["failed"]))

  if s["unusable"] or s["failed"]:
    with st.expander("Excluded links"):
      for r in s["unusable"]:
        st.text(f"[unusable]  {r['url']}")
      for r in s["failed"]:
        st.text(f"[failed]    {r['url']}")

  prompt = pipeline.build_prompt(results)

  header_col, dl_col = st.columns([4, 1])
  with header_col:
    st.subheader("Generated Prompt")
  with dl_col:
    st.download_button("Download", prompt, file_name="prompt.txt")

  with st.container(height=500):
    st.code(prompt, language=None, wrap_lines=True)
