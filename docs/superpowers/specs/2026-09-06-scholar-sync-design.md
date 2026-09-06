# Google Scholar 論文同步 — 設計文件

日期：2026-09-06
分支：`scholar-sync`
狀態：已核准，等待實作計畫

---

## 1. 目標

網站的論文清單目前由手動維護。這份設計要加入一個自動檢查的機制。

這個機制每月檢查一次 Google Scholar。如果有新論文，它開啟一個 pull request。
這個 PR 包含草稿檔。你檢查草稿檔，補上缺少的欄位，然後合併。

這個機制不自動發布任何內容。你保有完整的控制權。

---

## 2. 已驗證的事實

以下每一項都在 2026-09-06 實際測試過。

| 項目 | 結果 |
|---|---|
| 抓取個人頁面 | HTTP 200。沒有 CAPTCHA。從本機 IP 測試。 |
| 頁面參數 | `?user=1Xfc3ikAAAAJ&hl=en&cstart=0&pagesize=100` 一次取得全部論文。 |
| Scholar 論文數 | 16 筆。 |
| 網站論文數 | 13 筆。 |
| 未收錄的論文 | 3 筆。見第 7 節。 |
| 標題比對 | 正規化標題比對成功 13/13。 |
| 詳細頁面 | 提供完整作者名字、`YYYY/M` 日期、完整會議名稱。 |
| 詳細頁面的限制 | 作者名單有上限。測試的那一篇在第 21 位停止。 |
| 列表頁面的限制 | 作者用縮寫並且截斷。會議名稱截斷。 |
| 標題的限制 | Scholar 把標題轉成句首大寫。例如 `Dynamic-superb phase-2`、`Desta2. 5-audio`。 |
| 穩定編號 | 每一筆有 `citation_for_view` 編號。 |
| 本機環境 | Python 3.8.11、requests 2.28.1、bs4 4.14.3。沒有 PyYAML。 |
| gh CLI | 2.93.0。已登入 cyhuang-tw。權限包含 repo 和 workflow。 |

---

## 3. 範圍

### 包含

- 每月檢查一次 Google Scholar。
- 比對 Scholar 和 `_publications/` 的差異。
- 為新論文產生草稿檔。
- 開啟一個 pull request。
- 修改 `authors` 欄位的格式。加入 `co_first` 欄位。

### 不包含

- 自動修改已存在的 `_publications/*.md` 檔案。
- 處理 preprint 變成正式論文的情況。
- 自動合併 pull request。
- 從 DBLP 或 Semantic Scholar 取得資料。

---

## 4. 元件

新增三個檔案：

| 檔案 | 用途 |
|---|---|
| `scripts/scholar_sync.py` | 抓取、解析、比對、產生草稿檔。本機和 CI 都能執行。 |
| `scripts/scholar_ignore.yml` | 忽略清單。你手動編輯。 |
| `.github/workflows/scholar-check.yml` | 每月排程。也支援手動觸發。 |

修改的檔案：

| 檔案 | 修改內容 |
|---|---|
| `_config.yml` | 在 `exclude:` 加入 `scripts` 和 `docs`。 |
| `_includes/publication-authors.html` | 新增。共用的作者名單顯示邏輯。 |
| `_includes/archive-single.html` | 第 46 行改成呼叫共用 include。 |
| `_includes/archive-single-publication-cv.html` | 第 32 行改成呼叫共用 include。 |
| `_publications/*.md` | 13 個檔案。移除 HTML 標記。加入 `co_first` 欄位。 |

`_config.yml` 的 `exclude` 很重要。如果沒有這一項，Jekyll 會把 `scripts/` 和 `docs/`
複製到 `_site/`。然後這些檔案會出現在 chien-yu.com 上。

`.github/` 不需要處理。Jekyll 自動略過以點開頭的資料夾。

---

## 5. 資料格式的修改

### 5.1 修改的原因

目前 `authors` 欄位包含 HTML 標記。範例：

```yaml
authors: "Wei-Cheng Tseng<sub>(co-first)</sub>, <u>Chien-yu Huang</u><sub>(co-first)</sub>, Wei-Tsung Kao, Yist Y Lin, Hung-yi Lee"
```

這個格式有三個問題。第一，作者名單很長，標記難以閱讀。第二，每一篇論文都要重複寫
`<u>`。第三，自動化必須產生 HTML，這會增加出錯的機會。

### 5.2 新的格式

`authors` 只放純文字。`co_first` 是一份名單。

```yaml
authors: "Wei-Cheng Tseng, Chien-yu Huang, Wei-Tsung Kao, Yist Y Lin, Hung-yi Lee"
co_first:
  - Wei-Cheng Tseng
  - Chien-yu Huang
```

13 個檔案中有 11 個不需要 `co_first`。只有兩個檔案需要它：

| 檔案 | `co_first` 名單 |
|---|---|
| `2021-interspeech-mos.md` | Wei-Cheng Tseng、Chien-yu Huang |
| `2026-arxiv-bagpiper.md` | Chien-yu Huang |

Bagpiper 保持原樣。名單只放一個名字。這和目前網站的顯示相同。

### 5.3 顯示的邏輯

新的 include 是 `_includes/publication-authors.html`。它有兩個步驟：

1. 處理 `co_first`。對名單中的每個名字，在後面加上 `<sub>(co-first)</sub>`。
2. 處理你的名字。用 `site.author.name` 比對，前後加上 `<u>` 和 `</u>`。

順序不能顛倒。第 1 步產生 `Chien-yu Huang<sub>(co-first)</sub>`。
第 2 步把 `Chien-yu Huang` 換成 `<u>Chien-yu Huang</u>`。
結果是 `<u>Chien-yu Huang</u><sub>(co-first)</sub>`。

`site.author.name` 的值是 `Chien-yu Huang`。這個值已經在 `_config.yml` 裡面。

### 5.4 遷移

遷移移除 13 個檔案中的 `<u>`、`</u>` 和 `<sub>(co-first)</sub>`。
遷移為兩個檔案加上 `co_first` 名單。

遷移不改變網站的顯示結果。第 9.2 節說明驗證的方法。

---

## 6. 資料流程

1. 指令碼抓取個人頁面。它使用 `pagesize=100` 和瀏覽器的 User-Agent。
2. 指令碼檢查回應。三種情況下它回傳非零值並且停止：狀態碼不是 200、頁面有 CAPTCHA
   標記、解析結果是零筆。
3. 指令碼解析每一列。每一列包含 `citation_for_view` 編號、標題和年份。
4. 指令碼建立「已知」集合。這個集合包含 `_publications/*.md` 的標題和忽略清單的項目。
5. 指令碼計算差集。差集就是新論文。
6. 如果差集是空的，指令碼回傳零並且結束。它不開啟 PR。
7. 對每一篇新論文，指令碼抓取詳細頁面。它在每次抓取之間等待兩秒。
8. 指令碼寫入草稿檔。它推送分支 `scholar-update/<yyyy-mm>`。它開啟一個 PR。
   一個 PR 包含全部的新論文。

第 2 步是安全機制。抓取失敗和「沒有新論文」必須是兩種不同的結果。
如果沒有這個檢查，被封鎖的執行會看起來像正常的執行。

---

## 7. 比對規則

### 7.1 比對的鍵值

比對用「正規化標題」。正規化的方法是轉成小寫，然後移除所有非英數字元。

Scholar 改變標題的大小寫，但是不改變標題的文字。所以正規化之後可以正確比對。
測試結果是 13/13。

指令碼不用 `citation_for_view` 當主要鍵值。這個編號的後半段是位置編碼，不是內容雜湊。
不同的 Scholar 帳號會出現相同的值。論文清單重新排序時，這個值也會改變。
所以它不能當穩定的識別碼。

指令碼只在單次執行中使用這個編號。它用這個編號組出詳細頁面的網址。
指令碼把這個編號寫進草稿檔的註解，僅供查詢。

### 7.2 忽略清單

`scripts/scholar_ignore.yml` 放你不想放上網站的論文。格式如下：

```yaml
- title: "Improving cross-lingual reading comprehension with self-training"
  scholar_id: "1Xfc3ikAAAAJ:9yKSN-GCB0IC"
  reason: "不是主要貢獻"
```

`reason` 欄位讓未來的你記得排除的原因。

目前 Scholar 上有 3 筆不在網站上：

| 年份 | 標題 | 處理方式 |
|---|---|---|
| 2026 | Causal tracing of audio-text fusion in large audio language models | 第一次執行時產生草稿檔 |
| 2026 | PlanRAG-Audio: Planning and Retrieval Augmented Generation for Long-form Audio Understanding | 第一次執行時產生草稿檔 |
| 2021 | Improving cross-lingual reading comprehension with self-training | 放進忽略清單 |

### 7.3 已知的缺點

如果你大幅修改網站上的標題，指令碼會認為那是新論文。然後它會開啟重複的 PR。
PR 的內容會說明解法：把那一筆加入忽略清單。

---

## 8. 草稿檔的格式

草稿檔使用第 5.2 節的新格式。指令碼填入它能確定的欄位。它用 TODO 註解標記其他欄位。

```yaml
---
title: "Causal tracing of audio-text fusion in large audio language models" # TODO: 修正大小寫
authors: "A Author, Chien-yu Huang, B Author" # TODO: 確認名單完整，Scholar 有上限
collection: publications
permalink: /publication/2026-arxiv-causal-tracing
excerpt: ''
date: 2026-01-01 # TODO: Scholar 只給 2026/1，日期用預設值
venue: 'Preprint' # TODO: 確認
paperurl: '' # TODO: 填入
# scholar_id: 1Xfc3ikAAAAJ:xxxxxxxx
---
```

指令碼不加 `<u>` 標記。顯示的邏輯會處理底線。
指令碼不加 `co_first` 欄位。它無法知道共同第一作者的資訊。

YAML 註解是合法的 front matter。網站不顯示這些註解。
`_exps/04-2021-mediatek-engineer.md` 已經有一行註解掉的欄位，所以這個做法有先例。

### 8.1 檔名的規則

現有的檔名格式是 `<年份>-<會議代號>-<簡稱>.md`。範例：`2025-iclr-dynamic-superb.md`。

指令碼用一份對照表產生會議代號：ICASSP、Interspeech、ICLR、SLT、ASRU、NeurIPS、ACL。
如果對照表沒有相符的項目，指令碼用 `arxiv`。PR 的內容會提醒你檢查檔名。

---

## 9. 測試

### 9.1 指令碼的單元測試

測試用先前抓下來的頁面當測試資料。測試不連網路。
測試資料放在 `scripts/tests/fixtures/`。

| 測試 | 預期結果 |
|---|---|
| 解析列表頁面 | 16 筆。每一筆有編號、標題、年份。 |
| 解析詳細頁面 | 完整作者名字、`2025/4` 日期、完整會議名稱。 |
| 比對邏輯 | 輸入假的論文目錄和忽略清單。輸出預期的新論文集合。 |
| 產生草稿檔 | 輸出符合預期的 YAML 文字。 |
| 偵測 CAPTCHA | 指令碼回報錯誤。 |
| 偵測零筆結果 | 指令碼回報錯誤。 |

開發用測試先行的方式。先寫測試，再寫實作。

### 9.2 遷移的驗證

驗證分成四步：

1. 在遷移之前建置網站。保存 `_site/index.html` 和 `_site/publications/index.html`。
2. 執行遷移。
3. 再建置一次網站。
4. 比對兩次的輸出。

兩次的輸出必須完全相同。如果有差異，遷移就有錯誤。

---

## 10. 錯誤處理

| 情況 | 處理方式 |
|---|---|
| 抓取失敗 | 回傳非零值。不開啟 PR。workflow 失敗。GitHub 寄信通知。 |
| 詳細頁面失敗 | 改用列表頁面的資料。加上 TODO 註解。不中止整次執行。 |
| 重複的 PR | 先用 `gh pr list` 檢查。如果同一篇論文已經有開啟中的 PR，跳過它。 |
| 請求頻率 | 每次抓取詳細頁面之間等待兩秒。只有新論文需要抓取詳細頁面。 |

---

## 11. 限制與風險

| 項目 | 說明 |
|---|---|
| GitHub 設定 | 你必須開啟 Settings → Actions → General 的 "Allow GitHub Actions to create and approve pull requests"。workflow 檔案無法設定這一項。 |
| 排程停用 | 儲存庫 60 天沒有活動時，GitHub 停用排程 workflow。GitHub 會先寄信。你可以一鍵重新啟用。 |
| 分支名稱 | 機器人的分支前綴是 `scholar-update/`。它不能用 `scholar-sync/`。原因是本次開發的分支叫 `scholar-sync`，而 Git 不允許同名的 ref 同時是檔案和資料夾。 |
| workflow 權限 | workflow 需要 `contents: write` 和 `pull-requests: write`。 |
| Python 版本 | 本機是 3.8.11。指令碼寫成相容 3.8 的語法。CI 固定用 3.12。 |
| 本機套件 | 本機需要執行一次 `pip install pyyaml`。requests 和 bs4 已經安裝。 |
| Actions 的 IP | 我們還不知道 Scholar 是否封鎖 Actions 的 IP。第一次執行才知道。如果被封鎖，workflow 失敗，不會產生錯誤的 PR。備援方法是在本機執行同一個指令碼。 |
| 名字的形式 | 顯示的邏輯用字串比對。如果某一篇的作者名單寫成 `C. Huang`，底線不會出現。網站不報錯。遷移之後要檢查每一筆的輸出。 |
| Scholar 的服務條款 | Scholar 沒有公開 API。這個做法抓取公開頁面。頻率是每月一次，而且只抓你自己的個人頁面。 |
