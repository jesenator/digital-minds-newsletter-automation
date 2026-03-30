import json, http.client, re, xml.etree.ElementTree as ET
from dotenv import load_dotenv
load_dotenv()

from concurrent.futures import ThreadPoolExecutor, as_completed
from scraper import fetch_one
from llm import ask as llm_ask, ask_stream as llm_ask_stream
import html2text


NO_CONTENT = "NO_USABLE_CONTENT"

SUMMARIZE_PROMPT = """Summarize this webpage for inclusion in a newsletter about AI consciousness, digital minds, and moral status.

Focus on:
- The main claim, finding, or argument (not methodology)
- Key people involved (full names) and their affiliations
- Specific dates, if mentioned (publication date, event dates, deadlines)
- Why this matters for AI consciousness, welfare, or moral status
- For podcasts/videos: who the guest/speaker is and what they discussed
- For job listings/events: the organization, role/topic, location, dates, and how to apply
- For academic papers: the core thesis and conclusion, not the abstract structure

Keep it to one paragraph. Be specific and concrete, not generic.

If the text is not usable content (e.g. just navigation elements, cookie notices, login pages, error pages, generic site descriptions, or otherwise contains no substantive article/page content), output exactly: """ + NO_CONTENT + """

<text>{text}</text>"""

SUMMARIZE_MODEL = "google/gemini-3-flash-preview"
MIN_TEXT_FOR_SUMMARY = 200

DEFAULT_INSTRUCTIONS = """Write the next edition following the structure and style of the previous newsletter. This is a draft that will be reviewed and edited by the newsletter authors.

APPROXIMATE STRUCTURE:
1. Highlights - DO NOT WRITE THIS SECTION -- it is handwritten by the editors.
2. Field Developments - Updates from specific organizations (use ### subheadings for each org). Include "Highlights From The Field" and "More From The Field" subsections.
3. Opportunities - Split into:
   - Job Opportunities, Funding, and Fellowships (who, what the role/grant is, how to apply)
   - Events and Networks (who runs it, where, when; chronological order)
   - Calls for Papers (chronological by deadline)
4. Selected Reading, Watching, and Listening - Split into:
   - Books and Book Reviews
   - Podcasts (what was discussed, who it was discussed with)
   - Videos
   - Blogs, Magazines, and Written Resources
   Group multiple items from the same blog/podcast/channel together.
5. Press and Public Discourse - Notable media coverage, organized by theme.
6. A Deeper Dive by Area - Longer list of developments organized into subsections:
   - Governance, Policy, and Macrostrategy
   - Consciousness Research
   - Seemingly Conscious AI
   - Doubts About Digital Minds
   - Social Science Research
   - Ethics and Digital Minds
   - AI Safety and AI Welfare
   - AI Cognition and Agency
   - AI and Robotics Developments
   - Brain-Inspired Technologies

DO NOT WRITE:
- The welcome/intro paragraph, table of contents, subscribe callouts, header image, closing message, credits/acknowledgments, or things like this. These are added by the editors. Start your output directly with section 2.
- Do not include meta-commentary about ordering in the draft output (e.g. "In chronological order." or "Listed alphabetically."). Just list the items in the correct order without announcing it.

WRITING RULES:
- The above structure is a guide. Especially for the sub sections, you can use your judgement to determine the best structure.
- Output the article using markdown formatting with inline links: [anchor text](url)
- Each entry in the deeper dive sections should be 1-2 sentences with a link.
- Group related items together (e.g. multiple posts from the same author/blog).
- Each article/link should appear in exactly ONE section. Place it in the single most appropriate section; do not duplicate it across multiple sections.
- The previous newsletter is provided ONLY as a style and format reference. Do NOT repeat, paraphrase, or reference any specific content from it. If a link from <articles> also appeared in the previous newsletter, skip it entirely.
- Do NOT fabricate or hallucinate any links, names, or claims. Only use information from the provided article summaries.
- For content that is important but which you are not sure about, include an indicator, such as "[add more details]"
- For podcasts and videos, mention the guest/speaker and what was discussed.
- For job/fellowship listings, mention the organization, what the role is, and link to apply.
- For events, mention the organizer, location, and dates.
- For calls for papers, mention the venue and deadline.

NAMING AND ATTRIBUTION:
- Always mention first names of authors on first reference, then last name only after.
- Use the name that researchers publish under (e.g. "Robert Long" not "Rob Long").
- Say "and collaborators" instead of "et al." or "and colleagues".

STYLE AND LANGUAGE:
- Write in present tense when describing what is said in written work (e.g. "argues" not "argued").
- Use "and" rather than "&" in writing.
- Use "and" to mark the last item in lists (for audio readability).
- Write in complete sentences throughout.
- Use "post" rather than "article" when referring to blog posts.
- Reserve "published" for non-blog venues (journals, books, reports, etc.).
- Avoid using the word "assert".
- Avoid language that implies endorsement of disputable claims.
- Avoid making predictions, including for mundane things. Instead of saying something "will be released", say it "is set for release".

LINKING:
- When linking to papers, link to the webpage where you can find them (e.g. the journal or repository page), not directly to the PDF.
- When linking to books, link to the publisher's page rather than Amazon or another vendor.
- Convert links into sentences that convey the key idea from the piece.

BOOKS SECTION:
- List published books first, followed by not-yet-published books.
- Note that "not yet published" is not the same as "forthcoming" -- use the correct term.

FORMAT:
- Ensure format uniformity across sections and entries.
- Use the correct markdown heading levels (# for title, ## for sections, ### for subsections) to ensure proper formatting when pasted into Substack.
- Within each section or subsection, list entries in alphabetical order by the first word of the entry (typically the author's or organization's name). The exceptions are "Events and Networks" and "Calls for Papers", which should remain in chronological order as noted above.

SELF-CHECK:
- Before finalizing, review the draft for adherence to all the above rules."""

PROMPT_TEMPLATE = """You are writing a draft of the next edition of the Digital Minds Newsletter, a curated newsletter covering digital minds, AI consciousness, and moral status.

<articles>
{articles}
</articles>

The following is the PREVIOUS edition of the newsletter. It is provided ONLY so you can match its structure, tone, and formatting style. Do NOT copy, repeat, or paraphrase any of its content. Your draft must be entirely new.
<previous_newsletter>
{reference_text}
</previous_newsletter>

<instructions>
{instructions}
</instructions>"""


class NewsletterPipeline:
  def __init__(self, reference_text=""):
    self.reference_text = reference_text

  @staticmethod
  def fetch_reference(url):
    """Fetch newsletter content via Substack RSS feed, falling back to scraping."""
    try:
      domain = url.split("//")[1].split("/")[0]
      slug = url.rstrip("/").split("/")[-1]
      conn = http.client.HTTPSConnection(domain)
      conn.request("GET", "/feed")
      res = conn.getresponse()
      root = ET.fromstring(res.read().decode("utf-8"))
      ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
      for item in root.findall(".//item"):
        link = item.find("link").text or ""
        if slug in link:
          html_content = item.find("content:encoded", ns)
          if html_content is not None and html_content.text:
            h = html2text.HTML2Text()
            h.body_width = 0
            h.ignore_images = True
            return h.handle(html_content.text).strip()
    except Exception:
      pass
    result = fetch_one(url)
    return result["text"] if result["ok"] else ""

  def fetch(self, urls, max_links=None):
    """Yields (done, total) as articles are fetched. Access .fetch_results after."""
    urls = urls[:max_links]
    n = len(urls)
    self.fetch_results = [None] * n
    with ThreadPoolExecutor(max_workers=15) as pool:
      futs = {pool.submit(fetch_one, u): i for i, u in enumerate(urls)}
      done = 0
      for f in as_completed(futs):
        self.fetch_results[futs[f]] = f.result()
        done += 1
        yield done, n

  def _summarize_one(self, url, text):
    if len(text) < MIN_TEXT_FOR_SUMMARY:
      return text
    return llm_ask(SUMMARIZE_PROMPT.format(text=text), model=SUMMARIZE_MODEL, timeout=30)

  def summarize(self, results):
    """Yields (done, total) as articles are summarized. Access .summarize_results after."""
    self.summarize_results = [{**r, "summary": None} for r in results]
    ok_items = [(i, r) for i, r in enumerate(results) if r["ok"]]
    ok_n = len(ok_items)
    if ok_n == 0:
      return
    with ThreadPoolExecutor(max_workers=10) as pool:
      futs = {pool.submit(self._summarize_one, r["url"], r["text"]): i for i, r in ok_items}
      done = 0
      for f in as_completed(futs):
        idx = futs[f]
        summary = f.result()
        usable = NO_CONTENT not in (summary or "")
        self.summarize_results[idx] = {
          **results[idx],
          "summary": summary if usable else None,
          "usable": usable,
        }
        done += 1
        yield done, ok_n

  def build_prompt(self, results, instructions=None):
    if instructions is None:
      instructions = DEFAULT_INSTRUCTIONS
    articles = ""
    for r in results:
      if not r.get("ok") or not r.get("usable", True):
        continue
      summary = r.get("summary") or "(no summary)"
      articles += f"<article>\n"
      articles += f"  <url>{r['url']}</url>\n"
      articles += f"  <title>{r['title']}</title>\n"
      articles += f"  <summary>\n{summary}\n</summary>\n"
      articles += f"</article>\n"
    return PROMPT_TEMPLATE.format(
      reference_text=self.reference_text,
      articles=articles,
      instructions=instructions,
    )

  GENERATE_MODEL = "anthropic/claude-opus-4.6"

  def generate(self, prompt):
    return llm_ask(prompt, model=self.GENERATE_MODEL, timeout=600, max_tokens=128000, temperature=0.5)

  def generate_stream(self, prompt):
    """Yields text chunks as the model streams its response."""
    yield from llm_ask_stream(prompt, model=self.GENERATE_MODEL, timeout=600, max_tokens=128000, temperature=0.5)

  def stats(self, results):
    usable = [r for r in results if r.get("ok") and r.get("usable", True)]
    unusable = [r for r in results if r.get("ok") and not r.get("usable", True)]
    failed = [r for r in results if not r.get("ok")]
    return {"usable": usable, "unusable": unusable, "failed": failed}


def load_links(path="newsletter-1-links.txt"):
  with open(path) as f:
    return [l.strip() for l in f if l.strip()]


if __name__ == "__main__":
  urls = load_links()
  max_links = 30

  ref_url = "https://www.digitalminds.news/p/the-vatican-ai-legal-personhood-and"
  print(f"Fetching reference newsletter from {ref_url}...")
  reference_text = NewsletterPipeline.fetch_reference(ref_url)
  print(f"  Got {len(reference_text):,} chars")
  pipeline = NewsletterPipeline(reference_text)

  print(f"Fetching {max_links or len(urls)} links...")
  for done, total in pipeline.fetch(urls, max_links):
    print(f"  {done}/{total}", end="\r")
  results = pipeline.fetch_results
  print()

  ok = sum(1 for r in results if r["ok"])
  fail = len(results) - ok
  print(f"Total: {len(results)}  |  OK: {ok}  |  Failed: {fail}")

  print("Summarizing...")
  for done, total in pipeline.summarize(results):
    print(f"  {done}/{total}", end="\r")
  results = pipeline.summarize_results
  print()

  prompt = pipeline.build_prompt(results)
  with open("prompt.txt", "w") as f:
    f.write(prompt)
  print(f"Prompt saved to prompt.txt ({len(prompt.split()):,} words)")

  with open("results.json", "w") as f:
    json.dump(results, f, indent=2)
