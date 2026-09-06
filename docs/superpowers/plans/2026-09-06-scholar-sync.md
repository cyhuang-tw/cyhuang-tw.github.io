# Google Scholar 論文同步 — 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每月檢查 Google Scholar。發現新論文時開啟一個 pull request，內含草稿檔。

**Architecture:** 一個 Python 指令碼負責抓取、解析、比對和產生草稿檔。它在本機和 GitHub Actions 都能執行。顯示的邏輯搬到共用的 Liquid include，所以 `authors` 欄位只放純文字。

**Tech Stack:** Python 3.8+（本機）/ 3.12（CI）、requests、beautifulsoup4、PyYAML、unittest、gh CLI、Jekyll 3.9、Liquid。

**Spec:** `docs/superpowers/specs/2026-09-06-scholar-sync-design.md`

## Global Constraints

- 分支：`scholar-sync`。不要直接提交到 `master`。
- 機器人的分支前綴是 `scholar-update/`。不可以用 `scholar-sync/`，因為 Git 不允許同名的 ref 同時是檔案和資料夾。
- 機器人的分支名稱包含日期和時間，所以每次執行都是新的分支。這樣就不需要 force push。
- 建置網站時一定要設定 UTF-8 語系：`LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8`。否則 SCSS 轉換會失敗。
- 指令碼的語法必須相容 Python 3.8。不可以用 `X | Y` 型別聯集，不可以用 `match` 陳述式。
- 測試只用標準函式庫的 `unittest`。測試不可以連網路。
- Scholar 的使用者代號是 `1Xfc3ikAAAAJ`。
- `site.author.name` 的值是 `Chien-yu Huang`。
- 指令碼絕對不可以修改已存在的 `_publications/*.md` 檔案。
- 抓取失敗時，指令碼必須回傳非零值，而且不可以開啟 PR。

---

### Task 1: 作者欄位的格式遷移

把顯示的邏輯搬到共用的 include。把 13 個檔案的 `authors` 改成純文字。網站的顯示結果不可以改變。

**Files:**
- Create: `_includes/publication-authors.html`
- Modify: `_includes/archive-single.html:46`
- Modify: `_includes/archive-single-publication-cv.html:32`
- Modify: `_publications/*.md`（13 個檔案）

**Interfaces:**
- Consumes: 無。這是第一個任務。
- Produces: `_publications/*.md` 的新格式。`authors` 是純文字字串。`co_first` 是選用的名字清單。Task 4 產生的草稿檔要用這個格式。

- [ ] **Step 1: 記錄遷移前的基準**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 bundle exec jekyll build
mkdir -p /tmp/scholar-baseline
cp _site/index.html /tmp/scholar-baseline/index.html
cp _site/publications/index.html /tmp/scholar-baseline/publications.html
grep -c 'class="publication-authors"' /tmp/scholar-baseline/index.html
grep -c '<sub>(co-first)</sub>' /tmp/scholar-baseline/index.html
```

預期輸出：`13` 和 `3`。這兩個數字是遷移的基準。

- [ ] **Step 2: 建立共用的 include**

建立 `_includes/publication-authors.html`。整個檔案就是下面這一行內容，不要有結尾的換行以外的空白：

```liquid
{%- assign rendered = include.post.authors -%}
{%- if include.post.co_first -%}
{%- for n in include.post.co_first -%}
{%- capture marked -%}{{ n }}<sub>(co-first)</sub>{%- endcapture -%}
{%- assign rendered = rendered | replace: n, marked -%}
{%- endfor -%}
{%- endif -%}
{%- capture me -%}<u>{{ site.author.name }}</u>{%- endcapture -%}
{%- assign rendered = rendered | replace: site.author.name, me -%}
{{- rendered -}}
```

順序不可以顛倒。先加 `<sub>`，再加 `<u>`。這樣 `Chien-yu Huang` 會變成 `<u>Chien-yu Huang</u><sub>(co-first)</sub>`。

- [ ] **Step 3: 修改兩個呼叫的位置**

`_includes/archive-single.html` 第 46 行，把

```liquid
          <p> {{ post.authors }} </p>
```

改成

```liquid
          <p> {% include publication-authors.html post=post %} </p>
```

`_includes/archive-single-publication-cv.html` 第 32 行，把

```liquid
    <div class="publication-authors"><font size="3">{{ post.authors }}</font></div>
```

改成

```liquid
    <div class="publication-authors"><font size="3">{% include publication-authors.html post=post %}</font></div>
```

- [ ] **Step 4: 遷移 13 個檔案**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
python3 - <<'PY'
import io, re, glob
CO_FIRST = {
  '_publications/2021-interspeech-mos.md': ['Wei-Cheng Tseng', 'Chien-yu Huang'],
  '_publications/2026-arxiv-bagpiper.md': ['Chien-yu Huang'],
}
for path in sorted(glob.glob('_publications/*.md')):
    s = io.open(path, encoding='utf-8').read()
    m = re.search(r'^authors:\s*"(.*)"\s*$', s, re.M)
    if not m:
        print('SKIP (no authors field):', path)
        continue
    plain = m.group(1)
    plain = plain.replace('<u>', '').replace('</u>', '')
    plain = plain.replace('<sub>(co-first)</sub>', '')
    new_line = 'authors: "%s"' % plain
    names = CO_FIRST.get(path)
    if names:
        new_line += '\nco_first:\n' + '\n'.join('  - %s' % n for n in names)
    s = s[:m.start()] + new_line + s[m.end():]
    io.open(path, 'w', encoding='utf-8').write(s)
    print('migrated:', path, '| co_first:', names or '-')
PY
```

預期輸出：13 行 `migrated:`。其中兩行的 `co_first` 不是 `-`。

- [ ] **Step 5: 確認沒有殘留的標記**

```bash
grep -rn "<u>\|</u>\|<sub>(co-first)</sub>" _publications/ && echo "!! 還有殘留的標記" || echo "OK: 沒有殘留的標記"
```

預期輸出：`OK: 沒有殘留的標記`。

- [ ] **Step 6: 重新建置並且比對**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 bundle exec jekyll build
diff /tmp/scholar-baseline/index.html _site/index.html && echo "OK: index.html 完全相同"
diff /tmp/scholar-baseline/publications.html _site/publications/index.html && echo "OK: publications 完全相同"
```

預期輸出：兩行 `OK`，而且 `diff` 沒有任何輸出。

整個檔案必須逐位元組相同。這個檢查比只比對作者欄位更嚴格，它會抓到任何非預期的改變。

如果 `diff` 顯示差異，先看差異的內容：

- 只有空白的差異，代表 include 的空白控制有問題。檢查 `{%- -%}` 和 `{{- rendered -}}`。
- 標記的差異，代表替換的順序有問題。`<sub>` 必須在 `<u>` 之前處理。

不論哪一種，都要修正 include 或遷移的指令碼，不可以修改基準檔。

- [ ] **Step 7: 提交**

```bash
git add _includes _publications
git commit -m "Move author markup out of front matter into a shared include

authors is now plain text. Co-first authorship is a co_first list.
The <u> and <sub> markup is rendered by _includes/publication-authors.html.
Rendered output is unchanged."
```

---

### Task 2: 抓取與解析 Google Scholar

建立指令碼的骨架、測試資料和解析的函式。

**Files:**
- Create: `scripts/scholar_sync.py`
- Create: `scripts/requirements.txt`
- Create: `scripts/tests/fixtures/profile.html`
- Create: `scripts/tests/fixtures/detail.html`
- Create: `scripts/tests/test_scholar_sync.py`
- Modify: `_config.yml`（`exclude:` 加入 `scripts`）

**Interfaces:**
- Consumes: 無。
- Produces:
  - `Entry = namedtuple("Entry", "scholar_id title year")`
  - `class FetchError(Exception)`
  - `fetch(url)` 回傳 `str`。非 200 時 raise `FetchError`。
  - `parse_listing(html)` 回傳 `list[Entry]`。有 CAPTCHA 或零筆時 raise `FetchError`。
  - `parse_detail(html)` 回傳 `dict`，鍵值是 `authors`、`date`、`venue`，型別都是 `str`。
  - `PROFILE_URL`、`DETAIL_URL`、`SCHOLAR_USER` 常數。

- [ ] **Step 1: 準備測試資料**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
mkdir -p scripts/tests/fixtures
S=/private/tmp/claude-501/-Users-cyhuang-cyhuang-tw-github-io/dccb82b4-d53a-4c42-9d89-01c324f29e82/scratchpad
cp "$S/scholar.html" scripts/tests/fixtures/profile.html
cp "$S/detail.html" scripts/tests/fixtures/detail.html
grep -c 'gsc_a_tr' scripts/tests/fixtures/profile.html
```

如果 scratchpad 的檔案不見了，改用下面的指令重新抓取。重新抓取之後，`profile.html` 的論文數可能不是 16。這時要把 Step 2 測試中的 `16` 改成實際的數字。

```bash
curl -sS -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36" \
  -o scripts/tests/fixtures/profile.html \
  "https://scholar.google.com/citations?user=1Xfc3ikAAAAJ&hl=en&cstart=0&pagesize=100"
curl -sS -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36" \
  -o scripts/tests/fixtures/detail.html \
  "https://scholar.google.com/citations?view_op=view_citation&hl=en&user=1Xfc3ikAAAAJ&citation_for_view=1Xfc3ikAAAAJ:Se3iqnhoufwC"
```

- [ ] **Step 2: 寫失敗的測試**

建立 `scripts/tests/test_scholar_sync.py`：

```python
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import scholar_sync


def fixture(name):
    with io.open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as fh:
        return fh.read()


class TestParseListing(unittest.TestCase):
    def test_finds_all_rows(self):
        entries = scholar_sync.parse_listing(fixture("profile.html"))
        self.assertEqual(len(entries), 16)

    def test_row_fields(self):
        entries = scholar_sync.parse_listing(fixture("profile.html"))
        by_id = dict((e.scholar_id, e) for e in entries)
        entry = by_id["1Xfc3ikAAAAJ:Se3iqnhoufwC"]
        self.assertTrue(entry.title.startswith("Dynamic-superb phase-2"))
        self.assertEqual(entry.year, "2025")

    def test_captcha_page_raises(self):
        with self.assertRaises(scholar_sync.FetchError):
            scholar_sync.parse_listing("<html><body>Please show you're not a robot</body></html>")

    def test_empty_page_raises(self):
        with self.assertRaises(scholar_sync.FetchError):
            scholar_sync.parse_listing("<html><body><p>nothing here</p></body></html>")


class TestParseDetail(unittest.TestCase):
    def test_extracts_fields(self):
        detail = scholar_sync.parse_detail(fixture("detail.html"))
        self.assertTrue(detail["authors"].startswith("Chien-yu Huang, Wei-Chih Chen, Shu-wen Yang"))
        self.assertEqual(detail["date"], "2025/4")
        self.assertEqual(detail["venue"], "International Conference on Learning Representations 2025")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 執行測試，確認它失敗**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
python3 -m unittest discover -s scripts/tests -v
```

預期結果：FAIL，錯誤訊息是 `ModuleNotFoundError: No module named 'scholar_sync'`。

- [ ] **Step 4: 寫最小的實作**

建立 `scripts/requirements.txt`：

```
requests>=2.28
beautifulsoup4>=4.12
PyYAML>=6.0
```

建立 `scripts/scholar_sync.py`：

```python
#!/usr/bin/env python3
"""Check Google Scholar for publications that are not on the site yet."""

import re
from collections import namedtuple

import requests
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
BLOCK_MARKERS = ("captcha", "unusual traffic", "not a robot")

Entry = namedtuple("Entry", "scholar_id title year")


class FetchError(Exception):
    """Raised when Scholar cannot be read. Never treat this as 'no new papers'."""


def fetch(url):
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    if response.status_code != 200:
        raise FetchError("Scholar returned HTTP %s for %s" % (response.status_code, url))
    return response.text


def parse_listing(html):
    lowered = html.lower()
    for marker in BLOCK_MARKERS:
        if marker in lowered:
            raise FetchError("Scholar returned a block page (matched %r)" % marker)
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
```

- [ ] **Step 5: 執行測試，確認它通過**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
python3 -m unittest discover -s scripts/tests -v
```

預期結果：5 個測試全部 PASS。

- [ ] **Step 6: 把 scripts 加進 Jekyll 的排除清單**

在 `_config.yml` 的 `exclude:` 清單中，把 `  - package.json` 那一行的前面加入 `  - scripts`（保持字母順序）。然後驗證：

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 bundle exec jekyll build
ls -d _site/scripts 2>/dev/null && echo "!! scripts 被發布了" || echo "OK: _site/scripts 不存在"
```

預期輸出：`OK: _site/scripts 不存在`。

- [ ] **Step 7: 提交**

```bash
git add scripts _config.yml
git commit -m "Add Google Scholar fetching and parsing with tests"
```

---

### Task 3: 比對網站與忽略清單

判斷哪些論文是新的。

**Files:**
- Modify: `scripts/scholar_sync.py`
- Modify: `scripts/tests/test_scholar_sync.py`
- Create: `scripts/scholar_ignore.yml`

**Interfaces:**
- Consumes: Task 2 的 `Entry`。
- Produces:
  - `normalize_title(title)` 回傳 `str`。
  - `site_titles(pub_dir)` 回傳 `set` of `str`（正規化後的標題）。
  - `load_ignore(path)` 回傳 `set` of `str`（正規化後的標題）。
  - `find_new(entries, known)` 回傳 `list[Entry]`。

- [ ] **Step 1: 寫失敗的測試**

把下面的內容加到 `scripts/tests/test_scholar_sync.py`，放在 `if __name__` 那一段的前面：

```python
import shutil
import tempfile


class TestMatching(unittest.TestCase):
    def test_normalize_ignores_case_and_punctuation(self):
        self.assertEqual(
            scholar_sync.normalize_title("Dynamic-SUPERB Phase-2: A Benchmark"),
            scholar_sync.normalize_title("Dynamic-superb phase-2: a benchmark"),
        )

    def test_site_titles_reads_front_matter(self):
        tmp = tempfile.mkdtemp()
        try:
            with io.open(os.path.join(tmp, "a.md"), "w", encoding="utf-8") as fh:
                fh.write('---\ntitle: "Defending Your Voice"\nvenue: x\n---\n')
            titles = scholar_sync.site_titles(tmp)
            self.assertEqual(titles, set([scholar_sync.normalize_title("Defending your voice")]))
        finally:
            shutil.rmtree(tmp)

    def test_load_ignore_reads_titles(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "ignore.yml")
            with io.open(path, "w", encoding="utf-8") as fh:
                fh.write('- title: "Some Old Paper"\n  reason: "not mine"\n')
            self.assertEqual(
                scholar_sync.load_ignore(path),
                set([scholar_sync.normalize_title("some old paper")]),
            )
        finally:
            shutil.rmtree(tmp)

    def test_load_ignore_missing_file_is_empty(self):
        self.assertEqual(scholar_sync.load_ignore("/nonexistent/ignore.yml"), set())

    def test_find_new_excludes_known(self):
        entries = [
            scholar_sync.Entry("a", "Known Paper", "2024"),
            scholar_sync.Entry("b", "Brand New Paper", "2026"),
        ]
        known = set([scholar_sync.normalize_title("known paper")])
        new = scholar_sync.find_new(entries, known)
        self.assertEqual([e.title for e in new], ["Brand New Paper"])

    def test_real_profile_against_real_site(self):
        entries = scholar_sync.parse_listing(fixture("profile.html"))
        repo = os.path.dirname(os.path.dirname(HERE))
        known = scholar_sync.site_titles(os.path.join(repo, "_publications"))
        new = scholar_sync.find_new(entries, known)
        titles = sorted(e.title for e in new)
        self.assertEqual(len(titles), 3)
        self.assertTrue(any("Causal tracing" in t for t in titles))
        self.assertTrue(any("PlanRAG-Audio" in t for t in titles))
        self.assertTrue(any("cross-lingual" in t for t in titles))
```

- [ ] **Step 2: 執行測試，確認它失敗**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
python3 -m unittest discover -s scripts/tests -v
```

預期結果：新增的 6 個測試 FAIL，錯誤是 `AttributeError: module 'scholar_sync' has no attribute 'normalize_title'`。

- [ ] **Step 3: 寫實作**

在 `scripts/scholar_sync.py` 的 import 區塊加入：

```python
import glob
import io
import os

import yaml
```

在 `parse_detail` 的後面加入：

```python
def normalize_title(title):
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def site_titles(pub_dir):
    titles = set()
    for path in glob.glob(os.path.join(pub_dir, "*.md")):
        with io.open(path, encoding="utf-8") as fh:
            text = fh.read()
        match = re.search(r'^title:\s*"(.*?)"\s*$', text, re.M)
        if match:
            titles.add(normalize_title(match.group(1)))
    return titles


def load_ignore(path):
    if not os.path.exists(path):
        return set()
    with io.open(path, encoding="utf-8") as fh:
        items = yaml.safe_load(fh) or []
    return set(normalize_title(item["title"]) for item in items if item.get("title"))


def find_new(entries, known):
    return [e for e in entries if normalize_title(e.title) not in known]
```

- [ ] **Step 4: 建立忽略清單**

建立 `scripts/scholar_ignore.yml`：

```yaml
# Papers on the Google Scholar profile that should NOT appear on the site.
# Matching uses the normalized title, not scholar_id. The scholar_id is
# recorded for reference only; Scholar reassigns it when the list reorders.
- title: "Improving cross-lingual reading comprehension with self-training"
  scholar_id: "1Xfc3ikAAAAJ:9yKSN-GCB0IC"
  reason: "Not a primary contribution; deliberately left off the site."
```

- [ ] **Step 5: 執行測試，確認它通過**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
python3 -m unittest discover -s scripts/tests -v
```

預期結果：11 個測試全部 PASS。

- [ ] **Step 6: 手動確認忽略清單有效**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
python3 - <<'PY'
import io, os, sys
sys.path.insert(0, 'scripts')
import scholar_sync as s
html = io.open('scripts/tests/fixtures/profile.html', encoding='utf-8').read()
entries = s.parse_listing(html)
known = s.site_titles('_publications') | s.load_ignore('scripts/scholar_ignore.yml')
new = s.find_new(entries, known)
print('new papers:', len(new))
for e in new:
    print(' -', e.year, e.title)
PY
```

預期輸出：`new papers: 2`，兩篇都是 2026 年的論文。2021 年那一篇不可以出現。

- [ ] **Step 7: 提交**

```bash
git add scripts
git commit -m "Add site matching and the Scholar ignore list"
```

---

### Task 4: 產生草稿檔

把一筆新論文轉成 `_publications/` 的檔案內容。

**Files:**
- Modify: `scripts/scholar_sync.py`
- Modify: `scripts/tests/test_scholar_sync.py`

**Interfaces:**
- Consumes: Task 2 的 `Entry` 和 `parse_detail` 的回傳值。
- Produces:
  - `venue_slug(venue)` 回傳 `str`。
  - `title_slug(title)` 回傳 `str`。
  - `parse_date(text)` 回傳 tuple `(iso_date_str, precision_int)`。`precision` 是 1、2 或 3。
  - `render_stub(entry, detail)` 回傳 tuple `(filename_str, content_str)`。

- [ ] **Step 1: 寫失敗的測試**

加到 `scripts/tests/test_scholar_sync.py`：

```python
class TestStub(unittest.TestCase):
    def test_venue_slug_known(self):
        self.assertEqual(scholar_sync.venue_slug("ICASSP 2024 - IEEE Conference"), "icassp")
        self.assertEqual(
            scholar_sync.venue_slug("International Conference on Learning Representations 2025"),
            "iclr",
        )
        self.assertEqual(scholar_sync.venue_slug("2021 IEEE Spoken Language Technology Workshop"), "slt")

    def test_venue_slug_unknown_is_arxiv(self):
        self.assertEqual(scholar_sync.venue_slug(""), "arxiv")
        self.assertEqual(scholar_sync.venue_slug("Some Unlisted Venue"), "arxiv")

    def test_title_slug_drops_stopwords(self):
        self.assertEqual(
            scholar_sync.title_slug("Causal tracing of audio-text fusion in large audio language models"),
            "causal-tracing-audio-text",
        )

    def test_parse_date_precision(self):
        self.assertEqual(scholar_sync.parse_date("2025/4"), ("2025-04-01", 2))
        self.assertEqual(scholar_sync.parse_date("2025/4/24"), ("2025-04-24", 3))
        self.assertEqual(scholar_sync.parse_date("2026"), ("2026-01-01", 1))

    def test_render_stub(self):
        entry = scholar_sync.Entry("1Xfc3ikAAAAJ:abc", "Causal tracing of audio-text fusion", "2026")
        detail = {"authors": "A Author, Chien-yu Huang, B Author", "date": "2026/1", "venue": ""}
        filename, content = scholar_sync.render_stub(entry, detail)
        self.assertEqual(filename, "2026-arxiv-causal-tracing-audio-text.md")
        self.assertIn('authors: "A Author, Chien-yu Huang, B Author"', content)
        self.assertIn("permalink: /publication/2026-arxiv-causal-tracing-audio-text", content)
        self.assertIn("date: 2026-01-01", content)
        self.assertIn("# scholar_id: 1Xfc3ikAAAAJ:abc", content)
        self.assertNotIn("<u>", content)
        self.assertNotIn("co_first:", content)
```

- [ ] **Step 2: 執行測試，確認它失敗**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
python3 -m unittest discover -s scripts/tests -v
```

預期結果：新增的 5 個測試 FAIL，錯誤是 `AttributeError: module 'scholar_sync' has no attribute 'venue_slug'`。

- [ ] **Step 3: 寫實作**

加到 `scripts/scholar_sync.py`：

```python
VENUE_SLUGS = (
    ("icassp", "icassp"),
    ("interspeech", "interspeech"),
    ("learning representations", "iclr"),
    ("iclr", "iclr"),
    ("spoken language technology", "slt"),
    ("automatic speech recognition and understanding", "asru"),
    ("neural information processing", "neurips"),
    ("association for computational linguistics", "acl"),
    ("empirical methods", "emnlp"),
)
STOPWORDS = frozenset(
    ["a", "an", "the", "of", "for", "and", "with", "on", "in", "to", "via", "towards", "toward"]
)


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
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 else 1
    day = int(parts[2]) if len(parts) > 2 else 1
    return ("%04d-%02d-%02d" % (year, month, day), len(parts))


def render_stub(entry, detail):
    venue = detail.get("venue") or ""
    stem = "%s-%s-%s" % (entry.year or "0000", venue_slug(venue), title_slug(entry.title))
    iso_date, precision = parse_date(detail.get("date") or entry.year)
    date_note = "" if precision == 3 else "  # TODO: Scholar gave %r; missing parts defaulted" % (
        detail.get("date") or entry.year
    )
    lines = [
        "---",
        'title: "%s"  # TODO: fix capitalisation, Scholar lowercases titles' % entry.title,
        'authors: "%s"  # TODO: verify the list is complete, Scholar truncates long ones'
        % (detail.get("authors") or ""),
        "collection: publications",
        "permalink: /publication/%s" % stem,
        "excerpt: ''",
        "date: %s%s" % (iso_date, date_note),
        "venue: '%s'  # TODO: verify" % (venue or "Preprint"),
        "paperurl: ''  # TODO: fill in",
        "# TODO: if you are a co-first author, add a co_first list here",
        "# scholar_id: %s" % entry.scholar_id,
        "---",
        "",
    ]
    return (stem + ".md", "\n".join(lines))
```

- [ ] **Step 4: 執行測試，確認它通過**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
python3 -m unittest discover -s scripts/tests -v
```

預期結果：16 個測試全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add scripts
git commit -m "Generate draft publication entries from Scholar metadata"
```

---

### Task 5: 主流程與 pull request

把所有部分接起來，加上 `--dry-run`，並且開啟 PR。

**Files:**
- Modify: `scripts/scholar_sync.py`
- Modify: `scripts/tests/test_scholar_sync.py`

**Interfaces:**
- Consumes: Task 2 到 Task 4 的全部函式。
- Produces:
  - `PR_MARKER_RE`：比對 PR 內文中 `<!-- scholar-sync: <normalized title> -->` 的正規表示式。
  - `open_pr_titles()` 回傳 `set` of `str`。
  - `pr_body(created)` 回傳 `str`。`created` 是 `list` of tuple `(Entry, filename)`。
  - `main(argv)` 回傳 `int`（結束碼）。

- [ ] **Step 1: 寫失敗的測試**

加到 `scripts/tests/test_scholar_sync.py`：

```python
class TestPullRequest(unittest.TestCase):
    def test_pr_body_contains_machine_marker(self):
        entry = scholar_sync.Entry("1Xfc3ikAAAAJ:abc", "Brand New Paper", "2026")
        body = scholar_sync.pr_body([(entry, "2026-arxiv-brand-new-paper.md")])
        marker = "<!-- scholar-sync: %s -->" % scholar_sync.normalize_title("Brand New Paper")
        self.assertIn(marker, body)
        self.assertIn("2026-arxiv-brand-new-paper.md", body)
        self.assertIn("co_first", body)

    def test_pr_marker_round_trips(self):
        entry = scholar_sync.Entry("x", "Brand New Paper", "2026")
        body = scholar_sync.pr_body([(entry, "f.md")])
        found = scholar_sync.PR_MARKER_RE.findall(body)
        self.assertEqual(found, [scholar_sync.normalize_title("Brand New Paper")])
```

- [ ] **Step 2: 執行測試，確認它失敗**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
python3 -m unittest discover -s scripts/tests -v
```

預期結果：新增的 2 個測試 FAIL，錯誤是 `AttributeError: module 'scholar_sync' has no attribute 'pr_body'`。

- [ ] **Step 3: 寫實作**

在 `scripts/scholar_sync.py` 的 import 區塊加入：

```python
import argparse
import datetime
import json
import subprocess
import sys
import time
```

加到檔案的結尾：

```python
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
    except (subprocess.CalledProcessError, OSError):
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    options = parser.parse_args(argv)

    entries = parse_listing(fetch(PROFILE_URL.format(user=SCHOLAR_USER)))
    print("Scholar entries: %d" % len(entries))

    known = site_titles(PUB_DIR) | load_ignore(IGNORE_PATH) | open_pr_titles()
    new = find_new(entries, known)
    if not new:
        print("No new publications.")
        return 0
    print("New publications: %d" % len(new))

    created = []
    for index, entry in enumerate(new):
        if index:
            time.sleep(2)
        try:
            detail = parse_detail(
                fetch(DETAIL_URL.format(user=SCHOLAR_USER, cid=entry.scholar_id))
            )
        except FetchError as error:
            print("  detail fetch failed for %r: %s" % (entry.title, error))
            detail = {"authors": "", "date": entry.year, "venue": ""}
        filename, content = render_stub(entry, detail)
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
    run(["git", "checkout", "-B", branch])
    run(["git", "add", "_publications"])
    run(["git", "commit", "-m", "Add draft entries for %d new publication(s)" % len(created)])
    run(["git", "push", "origin", branch])
    run(
        [
            "gh", "pr", "create",
            "--base", "master",
            "--head", branch,
            "--title", "Add %d new publication(s) from Google Scholar" % len(created),
            "--body", pr_body(created),
        ]
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as error:
        sys.stderr.write("FETCH FAILED: %s\n" % error)
        sys.stderr.write("This is NOT the same as 'no new papers'. No pull request was opened.\n")
        sys.exit(1)
```

- [ ] **Step 4: 執行測試，確認它通過**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
python3 -m unittest discover -s scripts/tests -v
```

預期結果：18 個測試全部 PASS。

- [ ] **Step 5: 用 --dry-run 做端對端的手動測試**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
python3 scripts/scholar_sync.py --dry-run
git status --short
```

預期輸出：`Scholar entries: 16`、`New publications: 2`、兩個檔名，然後印出 PR 的內文。`git status --short` 不可以出現任何 `_publications/` 的新檔案。

- [ ] **Step 6: 提交**

```bash
git add scripts
git commit -m "Wire up the end-to-end run and pull request creation"
```

---

### Task 6: GitHub Actions workflow

每月自動執行，並且支援手動觸發。

**Files:**
- Create: `.github/workflows/scholar-check.yml`

**Interfaces:**
- Consumes: Task 5 的 `scripts/scholar_sync.py` 和 `scripts/requirements.txt`。
- Produces: 無。這是最後一個任務。

- [ ] **Step 1: 建立 workflow**

建立 `.github/workflows/scholar-check.yml`：

```yaml
name: Check Google Scholar

on:
  schedule:
    # 每月 1 日 06:00 UTC
    - cron: "0 6 1 * *"
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r scripts/requirements.txt

      - name: Run unit tests
        run: python -m unittest discover -s scripts/tests -v

      - name: Configure git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

      - name: Check Scholar and open a pull request
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python scripts/scholar_sync.py
```

`fetch-depth: 0` 是必要的。`git push` 需要完整的歷史。

- [ ] **Step 2: 驗證 YAML 語法**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
ruby -ryaml -e 'c=YAML.load_file(".github/workflows/scholar-check.yml"); puts "YAML ok"; puts c["jobs"]["check"]["steps"].length.to_s + " steps"'
```

預期輸出：`YAML ok` 和 `6 steps`。

- [ ] **Step 3: 確認 workflow 不會被發布**

```bash
cd /Users/cyhuang/cyhuang-tw.github.io
LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 bundle exec jekyll build
ls -d _site/.github 2>/dev/null && echo "!! .github 被發布了" || echo "OK: _site/.github 不存在"
```

預期輸出：`OK: _site/.github 不存在`。

- [ ] **Step 4: 提交並且推送分支**

```bash
git add .github
git commit -m "Add the monthly Google Scholar check workflow"
git push -u origin scholar-sync
```

- [ ] **Step 5: 開啟功能的 pull request**

```bash
gh pr create --base master --head scholar-sync \
  --title "Add automated Google Scholar publication sync" \
  --body "See docs/superpowers/specs/2026-09-06-scholar-sync-design.md for the design."
```

- [ ] **Step 6: 合併之前要做的人工設定**

這兩件事必須由使用者操作，指令碼和 workflow 都無法設定：

1. 前往 Settings → Actions → General → Workflow permissions。開啟 **Allow GitHub Actions to create and approve pull requests**。如果沒有開啟，workflow 會在 `gh pr create` 那一步失敗。
2. 合併之後，前往 Actions 分頁，手動執行一次 **Check Google Scholar**。這是為了確認 Scholar 沒有封鎖 GitHub Actions 的 IP。如果失敗而且錯誤訊息是 `Scholar returned a block page`，就改用本機執行：`python3 scripts/scholar_sync.py`。

---

## 完成後的狀態

- 網站的顯示結果和遷移前完全相同。
- `_publications/*.md` 的 `authors` 只放純文字。
- 18 個單元測試通過，而且不連網路。
- `python3 scripts/scholar_sync.py --dry-run` 回報 2 篇新論文。
- 每月 1 日 06:00 UTC 自動檢查一次。
