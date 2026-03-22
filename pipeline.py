import json
from dotenv import load_dotenv
load_dotenv()

from concurrent.futures import ThreadPoolExecutor, as_completed
from scraper import fetch_one
from llm import ask as llm_ask


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

PROMPT_TEMPLATE = """You are writing a draft of the next edition of the Digital Minds Newsletter, a curated newsletter covering digital minds, AI consciousness, and moral status.

<previous_newsletter>
{reference_text}
</previous_newsletter>

<articles>
{articles}
</articles>

<instructions>
Write the next edition following the structure and style of the previous newsletter. This is a draft that will be reviewed and edited by the newsletter authors.

STRUCTURE (use these exact sections):
1. Highlights - The most important developments, written in multi-paragraph narrative form. This section is handwritten/editorial in nature.
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

WRITING RULES:
- The above structures is a guide. Especially for the sub sections, you can use your judgement to determine the best structure.
- Use people's full names on first mention, then last name only.
- Write in present tense (e.g. "argues" not "argued").
- Ouput the article in a artifact using markdown formatting
  - Use markdown formatting for with inline links: [anchor text](url)
- Each entry in the deeper dive sections should be 1-2 sentences with a link.
- Group related items together (e.g. multiple posts from the same author/blog).
- An article may appear in both the Selected Reading section AND the Deeper Dive section if relevant.
- Do NOT include links that were already covered in the previous newsletter (Newsletter #2). Only include new content.
- Do NOT fabricate or hallucinate any links, names, or claims. Only use information from the provided article summaries.
- For content that is important but which you are not sure about, include an indicator, such as "[add more details]"
- For podcasts and videos, mention the guest/speaker and what was discussed.
- For job/fellowship listings, mention the organization, what the role is, and link to apply.
- For events, mention the organizer, location, and dates.
- For calls for papers, mention the venue and deadline.
</instructions>"""


class NewsletterPipeline:
  def __init__(self, reference_text=""):
    self.reference_text = reference_text

  @staticmethod
  def fetch_reference(url):
    result = fetch_one(url)
    if result["ok"]:
      return result["text"]
    return ""

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

  def build_prompt(self, results):
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
    return PROMPT_TEMPLATE.format(reference_text=self.reference_text, articles=articles)

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

  with open("newsletter-2-text.txt") as f:
    reference_text = f.read().strip()
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
