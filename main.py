# Run: python main.py
import json
from dotenv import load_dotenv
load_dotenv()

from concurrent.futures import ThreadPoolExecutor, as_completed
from scraper import fetch_one, fetch_all
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


def load_links(path="newsletter-1-links.txt"):
  with open(path) as f:
    return [l.strip() for l in f if l.strip()]


def summarize_one(url, text):
  if len(text) < MIN_TEXT_FOR_SUMMARY:
    return text
  return llm_ask(SUMMARIZE_PROMPT.format(text=text), model=SUMMARIZE_MODEL, timeout=30)


def summarize_all(results, max_links=None, workers=10):
  results = results[:max_links]
  out = [{**r, "summary": None} for r in results]
  ok_results = [(i, r) for i, r in enumerate(results) if r["ok"]]

  with ThreadPoolExecutor(max_workers=workers) as pool:
    futures = {pool.submit(summarize_one, r["url"], r["text"]): i for i, r in ok_results}
    for future in as_completed(futures):
      idx = futures[future]
      summary = future.result()
      usable = NO_CONTENT not in (summary or "")
      out[idx] = {**results[idx], "summary": summary if usable else None, "usable": usable}

  return out


def print_unusable(results):
  bad = [r for r in results if r.get("ok") and not r.get("usable", True)]
  failed = [r for r in results if not r.get("ok")]
  if bad or failed:
    print(f"\n--- Excluded from prompt: {len(bad)} unusable, {len(failed)} failed ---")
    for r in bad:
      print(f"  [unusable]  {r['url']}")
    for r in failed:
      print(f"  [failed]    {r['url']}")
    print()


def print_table(results):
  ok_count = sum(1 for r in results if r["ok"])
  fail_count = len(results) - ok_count

  print(f"\n{'#':>4}  {'Len':>7}  {'OK':>3}  URL")
  print("-" * 90)

  for i, r in enumerate(results, 1):
    ok_str = "Y" if r["ok"] else "N"
    err = f"  ({r['error'][:40]})" if r["error"] else ""
    print(f"{i:>4}  {r['length']:>7}  {ok_str:>3}  {r['url'][:60]}{err}")

  print("-" * 90)
  print(f"Total: {len(results)}  |  OK: {ok_count}  |  Failed: {fail_count}\n")


def save_results(results, path="results.json"):
  with open(path, "w") as f:
    json.dump(results, f, indent=2)
  print(f"Saved to {path}")


def build_prompt(results):
  with open("newsletter-2-text.txt") as f:
    newsletter_2_text = f.read().strip()

  articles = ""
  for i, r in enumerate(results, 1):
    if not r.get("ok") or not r.get("usable", True):
      continue
    summary = r.get("summary") or "(no summary)"
    articles += f"<article>\n"
    articles += f"  <url>{r['url']}</url>\n"
    articles += f"  <title>{r['title']}</title>\n"
    articles += f"  <summary>\n{summary}\n</summary>\n"
    articles += f"</article>\n"

  prompt = f"""You are writing a draft of the next edition of the Digital Minds Newsletter, a curated newsletter covering digital minds, AI consciousness, and moral status.

<previous_newsletter>
{newsletter_2_text}
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
  return prompt

if __name__ == "__main__":
  urls = load_links()
  max_links = 30
  print(f"Fetching {max_links or len(urls)} links...")
  results = fetch_all(urls, max_links=max_links)
  print_table(results)
  save_results(results)
  # exit()
  results = summarize_all(results, max_links=max_links)
  save_results(results, "results_summarized.json")

  prompt = build_prompt(results)
  print_unusable(results)
  with open("prompt.txt", "w") as f:
    f.write(prompt)
  print(f"Prompt saved to prompt.txt ({len(prompt.split()):,} words)")
