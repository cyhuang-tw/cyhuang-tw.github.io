#!/usr/bin/env python3
"""Check Google Scholar for publications that are not on the site yet."""

import argparse
import datetime
import glob
import io
import json
import os
import re
import subprocess
import sys
import time
from collections import namedtuple

import requests
import yaml
from bs4 import BeautifulSoup

SCHOLAR_USER = "1Xfc3ikAAAAJ"
PROFILE_URL = (
    "https://scholar.google.com/citations"
    "?user={user}&hl=en&cstart=0&pagesize=100"
)
DETAIL_URL = (
    "https://scholar.google.com/citations"
    "?view_op=view_citation&hl=en&user={user}&citation_for_view={cid}"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
BLOCK_MARKERS = (r"\bcaptcha\b", "unusual traffic", "not a robot")
FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)

Entry = namedtuple("Entry", "scholar_id title year")


class FetchError(Exception):
    """Raised when Scholar cannot be read. Never treat this as 'no new papers'."""


def fetch(url):
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    except requests.RequestException as exc:
        raise FetchError("Scholar request failed: %s" % exc)
    if response.status_code != 200:
        raise FetchError("Scholar returned HTTP %s for %s" % (response.status_code, url))
    return response.text


def check_not_blocked(html):
    """Raise FetchError if `html` looks like a Scholar block/CAPTCHA page.

    Shared by parse_listing and parse_detail: a blocked *detail* page (a
    realistic 429 shape once the listing itself already succeeded) must
    raise exactly like a blocked listing page does, instead of silently
    parsing out empty fields.
    """
    lowered = html.lower()
    for marker in BLOCK_MARKERS:
        if re.search(marker, lowered):
            raise FetchError("Scholar returned a block page (matched %r)" % marker)


def parse_listing(html):
    check_not_blocked(html)
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for row in soup.select("tr.gsc_a_tr"):
        link = row.select_one("a.gsc_a_at")
        if link is None:
            continue
        match = re.search(r"citation_for_view=([^&]+)", link.get("href", ""))
        year_el = row.select_one(".gsc_a_h")
        entries.append(
            Entry(
                match.group(1) if match else "",
                link.get_text(strip=True),
                year_el.get_text(strip=True) if year_el else "",
            )
        )
    if not entries:
        raise FetchError("No publication rows found. The page layout changed or the request was blocked.")
    return entries


def parse_detail(html):
    check_not_blocked(html)
    soup = BeautifulSoup(html, "html.parser")
    detail = {"authors": "", "date": "", "venue": ""}
    keys = {
        "authors": "authors",
        "publication date": "date",
        "conference": "venue",
        "journal": "venue",
        "book": "venue",
        "source": "venue",
    }
    for field in soup.select(".gsc_oci_field"):
        value = field.find_next_sibling("div", class_="gsc_oci_value")
        if value is None:
            continue
        target = keys.get(field.get_text(strip=True).lower())
        if target and not detail[target]:
            detail[target] = value.get_text(strip=True)
    return detail


def normalize_title(title):
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def site_titles(pub_dir):
    """Read the titles of every publication under `pub_dir`.

    A hand-edited entry can have malformed YAML front matter, or a `title`
    that parsed but is not a string (a bare number, a YAML list, ...). Either
    would otherwise reach __main__ as a bare traceback and kill the whole
    monthly run. Skip just that one file instead, with a WARNING naming it:
    the paper it describes drops out of `known` and could be re-reported as
    new, but a spurious draft PR is recoverable and a crashed job is not.
    """
    titles = set()
    for path in glob.glob(os.path.join(pub_dir, "*.md")):
        with io.open(path, encoding="utf-8") as fh:
            text = fh.read()
        match = FRONT_MATTER_RE.match(text)
        if not match:
            continue
        try:
            data = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as error:
            sys.stderr.write(
                "WARNING: skipping %s: could not parse YAML front matter (%s)\n"
                % (path, error)
            )
            continue
        title = data.get("title")
        if not title:
            continue
        if not isinstance(title, str):
            sys.stderr.write(
                "WARNING: skipping %s: title is not a string (%r)\n"
                % (path, title)
            )
            continue
        titles.add(normalize_title(title))
    return titles


def load_ignore(path):
    """Read the normalized titles listed in the hand-edited ignore file.

    Like `site_titles()`, this reads a file a human edits by hand, so a
    malformed edit must not crash the monthly run. Treat an unparseable
    ignore file as an empty ignore set, with a WARNING naming it: the worst
    case is that a paper the owner meant to suppress gets drafted once, which
    is recoverable, whereas a crashed job is not.
    """
    if not os.path.exists(path):
        return set()
    with io.open(path, encoding="utf-8") as fh:
        try:
            items = yaml.safe_load(fh) or []
        except yaml.YAMLError as error:
            sys.stderr.write(
                "WARNING: could not parse %s (%s); treating it as empty\n"
                % (path, error)
            )
            return set()
    titles = set()
    for item in items:
        if isinstance(item, dict) and item.get("title"):
            titles.add(normalize_title(item["title"]))
    return titles


def find_new(entries, known):
    return [e for e in entries if normalize_title(e.title) not in known]


VENUE_SLUGS = (
    ("icassp", "icassp"),
    ("interspeech", "interspeech"),
    ("learning representations", "iclr"),
    ("iclr", "iclr"),
    ("spoken language technology", "slt"),
    ("automatic speech recognition and understanding", "asru"),
    ("neural information processing", "neurips"),
    # NAACL needles must be checked before the ACL needle below: NAACL's full
    # name ("... North American Chapter of the Association for Computational
    # Linguistics ...") also contains the ACL substring, and the first
    # matching tuple wins regardless of where the match falls in the string.
    ("north american chapter", "naacl"),
    ("naacl", "naacl"),
    ("association for computational linguistics", "acl"),
    ("empirical methods", "emnlp"),
    ("transactions on audio, speech and language processing", "taslp"),
    ("transactions on audio, speech, and language processing", "taslp"),
    ("taslp", "taslp"),
    ("international conference on computational linguistics", "coling"),
    ("coling", "coling"),
    ("international conference on machine learning", "icml"),
    ("icml", "icml"),
)
STOPWORDS = frozenset(
    ["a", "an", "the", "of", "for", "and", "with", "on", "in", "to", "via", "towards", "toward"]
)


def yaml_dq_escape(value):
    """Escape a third-party string for safe interpolation inside a YAML
    double-quoted scalar ("..."). Backslash MUST be escaped before the quote,
    or a value ending in a backslash would swallow the closing quote."""
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def venue_slug(venue):
    lowered = (venue or "").lower()
    for needle, slug in VENUE_SLUGS:
        if needle in lowered:
            return slug
    return "arxiv"


def title_slug(title, words=3):
    cleaned = re.sub(r"[^a-z0-9\s-]", " ", (title or "").lower()).split()
    kept = [w for w in cleaned if w not in STOPWORDS]
    return "-".join(kept[:words]) or "untitled"


def parse_date(text):
    parts = [p for p in (text or "").split("/") if p.strip()]
    if not parts:
        return ("1900-01-01", 1)
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
    except ValueError:
        # Scholar dates are not always clean slash-separated digits (e.g. a
        # scraped "circa 2020"). Degrade to the same sentinel used for empty
        # input rather than let this escape as an uncaught exception.
        return ("1900-01-01", 1)
    precision = min(len(parts), 3)
    return ("%04d-%02d-%02d" % (year, month, day), precision)


def render_stub(entry, detail):
    venue = detail.get("venue") or ""
    stem = "%s-%s-%s" % (entry.year or "0000", venue_slug(venue), title_slug(entry.title))
    iso_date, precision = parse_date(detail.get("date") or entry.year)
    date_note = "" if precision == 3 else "  # TODO: Scholar gave %r; missing parts defaulted" % (
        detail.get("date") or entry.year
    )
    authors = detail.get("authors") or ""
    authors_todo = (
        "verify the list is complete, Scholar truncates long ones"
        if authors
        else "Scholar returned no authors for this entry; fill in manually"
    )
    lines = [
        "---",
        'title: "%s"  # TODO: fix capitalisation, Scholar lowercases titles' % yaml_dq_escape(entry.title),
        'authors: "%s"  # TODO: %s' % (yaml_dq_escape(authors), authors_todo),
        "collection: publications",
        "permalink: /publication/%s" % stem,
        "excerpt: ''",
        "date: %s%s" % (iso_date, date_note),
        'venue: "%s"  # TODO: verify' % yaml_dq_escape(venue or "Preprint"),
        "paperurl: ''  # TODO: fill in",
        "# TODO: if you are a co-first author, add a co_first list here",
        "# scholar_id: %s" % entry.scholar_id,
        "---",
        "",
    ]
    return (stem + ".md", "\n".join(lines))


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB_DIR = os.path.join(REPO_ROOT, "_publications")
IGNORE_PATH = os.path.join(REPO_ROOT, "scripts", "scholar_ignore.yml")
BRANCH_PREFIX = "scholar-update/"
# 每次執行都用不同的分支名稱。如果重複使用同一個分支，
# 第二次執行的 force push 會刪掉第一個 PR 裡面的草稿檔。
PR_MARKER_RE = re.compile(r"<!-- scholar-sync: (.*?) -->")


def open_pr_titles():
    try:
        raw = subprocess.check_output(
            ["gh", "pr", "list", "--state", "open", "--limit", "50", "--json", "body"],
            cwd=REPO_ROOT,
            universal_newlines=True,
        )
    except (subprocess.CalledProcessError, OSError) as error:
        sys.stderr.write(
            "WARNING: could not list open pull requests via `gh` (%s); "
            "continuing as if none are open. Papers that already have an "
            "open PR may be re-drafted this run.\n" % error
        )
        return set()
    found = set()
    for item in json.loads(raw):
        found.update(PR_MARKER_RE.findall(item.get("body") or ""))
    return found


def pr_body(created):
    lines = [
        "Found on the Google Scholar profile but missing from `_publications/`.",
        "",
        "Each entry below is a draft. Check every `TODO` comment before merging.",
        "",
    ]
    for entry, filename in created:
        lines.append("### %s" % entry.title)
        lines.append("")
        lines.append("- File: `_publications/%s`" % filename)
        lines.append("- Scholar year: %s" % (entry.year or "unknown"))
        lines.append("- Check the title capitalisation. Scholar lowercases titles.")
        lines.append("- Check the author list is complete, and add a `co_first` list if needed.")
        lines.append("- Fill in `paperurl`, and add `repo` if there is code.")
        lines.append("- Check the filename and `permalink` match how you name papers.")
        lines.append("")
        lines.append("<!-- scholar-sync: %s -->" % normalize_title(entry.title))
        lines.append("")
    lines.append("If a paper here should never appear on the site, add it to")
    lines.append("`scripts/scholar_ignore.yml` and close this pull request.")
    return "\n".join(lines)


def run(args):
    subprocess.check_call(args, cwd=REPO_ROOT)


def run_git_sequence(branch, created):
    """Run the checkout/add/commit/push/PR-create sequence one step at a
    time. If a step raises `subprocess.CalledProcessError`, report which
    step failed, the branch involved, and what state that leaves behind —
    instead of letting a bare traceback reach the operator — and return
    False. The failure is never swallowed: the caller still has to turn a
    False return into a non-zero exit code.
    """
    # Only the files this run actually generated, never the whole directory:
    # `git add _publications` would sweep in any uncommitted local edits
    # already sitting in _publications/ on whatever branch was checked out,
    # which is exactly the state a local fallback run is likely to be in.
    filenames = [os.path.join("_publications", filename) for _, filename in created]
    steps = [
        (
            "git checkout -B %s" % branch,
            ["git", "checkout", "-B", branch],
            "No branch, commit, or push happened yet. The draft files "
            "written under _publications/ are untracked on whatever "
            "branch was checked out before this ran.",
        ),
        (
            "git add %s" % " ".join(filenames),
            ["git", "add"] + filenames,
            "Branch %r was created locally. The draft files are still "
            "untracked in _publications/ on that branch." % branch,
        ),
        (
            "git commit",
            [
                "git", "commit", "-m",
                "Add draft entries for %d new publication(s)" % len(created),
            ],
            "Branch %r was created locally with the draft files staged "
            "but not committed." % branch,
        ),
        (
            "git push origin %s" % branch,
            ["git", "push", "origin", branch],
            "Branch %r exists locally with a commit, but nothing was "
            "pushed. The commit only exists in this local checkout." % branch,
        ),
        (
            "gh pr create",
            [
                "gh", "pr", "create",
                "--base", "master",
                "--head", branch,
                "--title", "Add %d new publication(s) from Google Scholar" % len(created),
                "--body", pr_body(created),
            ],
            "Branch %r was pushed to origin, but no pull request was "
            "created. An orphan branch now exists on the remote with no "
            "PR pointing at it. open_pr_titles() only sees open PRs, so "
            "leaving this branch in place means next month's run drafts "
            "the same papers again on a second branch. To recover, delete "
            "the orphan branch so the next run starts clean: "
            "git push origin --delete %s" % (branch, branch),
        ),
    ]
    for step, args, left_behind in steps:
        try:
            run(args)
        except subprocess.CalledProcessError as error:
            sys.stderr.write(
                "GIT/GH STEP FAILED: %s (exit code %s)\n"
                "Branch: %s\n"
                "What this means: %s\n"
                % (step, error.returncode, branch, left_behind)
            )
            return False
        except OSError as error:
            # Raised (FileNotFoundError, a subclass, in the common case)
            # when the `git` or `gh` executable itself is not on PATH.
            # Without this, that escapes run_git_sequence entirely and
            # produces a bare traceback instead of the diagnostic below.
            sys.stderr.write(
                "GIT/GH STEP FAILED: %s (%s)\n"
                "Branch: %s\n"
                "What this means: %s\n"
                % (step, error, branch, left_behind)
            )
            return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    options = parser.parse_args(argv)

    entries = parse_listing(fetch(PROFILE_URL.format(user=SCHOLAR_USER)))
    print("Scholar entries: %d" % len(entries))

    site_known = site_titles(PUB_DIR)
    if len(entries) < len(site_known):
        # The Scholar profile is *usually* a superset of the site, but not
        # always: the owner can add papers before Scholar indexes them
        # (arXiv lag around a deadline), or delete duplicate entries from
        # the Scholar profile, which lowers the count permanently. Neither
        # is a fetch failure, so a listing merely shorter than the site is
        # only worth a warning. A listing that falls below roughly half the
        # site's publication count, though, is no longer explainable by
        # either of those -- that is a truncated or partially blocked fetch,
        # and must not be read as "no new papers". This floor uses
        # site_known alone (not the ignore/open-PR union below), since
        # those two sets can only shrink `new`, never explain away a
        # listing that is short of the site's own publication count.
        floor = max(1, len(site_known) // 2)
        if len(entries) < floor:
            raise FetchError(
                "Scholar listed %d entries but the site has %d publications. "
                "The listing is truncated or partially blocked."
                % (len(entries), len(site_known))
            )
        sys.stderr.write(
            "WARNING: Scholar listed %d entries but the site has %d "
            "publications. This is normal when the site has papers Scholar "
            "has not indexed yet; continuing.\n" % (len(entries), len(site_known))
        )

    known = site_known | load_ignore(IGNORE_PATH) | open_pr_titles()
    new = find_new(entries, known)
    if not new:
        print("No new publications.")
        return 0
    print("New publications: %d" % len(new))

    stubs = []
    detail_failures = 0
    for index, entry in enumerate(new):
        if index:
            time.sleep(2)
        try:
            detail = parse_detail(
                fetch(DETAIL_URL.format(user=SCHOLAR_USER, cid=entry.scholar_id))
            )
        except FetchError as error:
            sys.stderr.write("  detail fetch failed for %r: %s\n" % (entry.title, error))
            detail = {"authors": "", "date": entry.year, "venue": ""}
            detail_failures += 1
        filename, content = render_stub(entry, detail)
        stubs.append((entry, filename, content))

    if detail_failures == len(new) and len(new) >= 2:
        # Every detail fetch failed, and there were at least two of them.
        # That is Scholar blocking or rate-limiting this run, not N papers
        # that all happen to lack metadata -- raise instead of silently
        # opening a PR of empty stubs (or, worse, exiting 0 on --dry-run).
        # A genuine block hits every request, and a block month almost
        # never happens to have exactly one new paper, so the single-paper
        # case below is handled separately instead of tripping this rule.
        raise FetchError(
            "All %d detail fetches failed; Scholar is likely blocking or "
            "rate-limiting this run rather than every entry genuinely "
            "lacking metadata." % detail_failures
        )
    if detail_failures == len(new) and len(new) == 1:
        # Exactly one new paper, and its detail fetch failed -- the most
        # common monthly shape, and a single ordinary HTTP 404 here is not
        # evidence of a block. Degrade the same way the per-entry handler
        # above already has (the stub was written with blank fields and its
        # own TODO comments); just make the sparse draft visible instead of
        # throwing the whole run away over one bad page.
        sys.stderr.write(
            "WARNING: the detail page for the only new paper could not be "
            "read; the draft is therefore sparse (blank fields).\n"
        )

    created = []
    for entry, filename, content in stubs:
        print("  %s" % filename)
        if not options.dry_run:
            with io.open(os.path.join(PUB_DIR, filename), "w", encoding="utf-8") as fh:
                fh.write(content)
        created.append((entry, filename))

    if options.dry_run:
        print("\n--dry-run: nothing written.")
        print(pr_body(created))
        return 0

    branch = BRANCH_PREFIX + datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    if not run_git_sequence(branch, created):
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as error:
        sys.stderr.write("FETCH FAILED: %s\n" % error)
        sys.stderr.write("This is NOT the same as 'no new papers'. No pull request was opened.\n")
        sys.exit(1)
