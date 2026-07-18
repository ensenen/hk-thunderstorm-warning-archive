# 香港雷暴警告資料

[Wiki 草稿](docs/wiki/雷暴警告.md) · [數據字典](docs/data-dictionary.md) ·
[參與貢獻](CONTRIBUTING.md) · [數據授權](LICENSE-DATA.md)

下載及保存香港政府新聞公報中的「雷暴警告」天氣稿，並與香港天文台由1967年起的
官方警告起訖記錄配對。現時已處理所有官方可取得年份；網上天氣稿 archive 由1998年起。

## 原則

- 原始 HTML 永久保留，解析資料可以隨時重新產生。
- 每個檔案另存 SHA-256、下載時間、來源 URL 及 HTTP metadata。
- 重複執行預設不會重新下載已有檔案。
- 先下載每日天氣稿索引，再從索引尋找雷暴警告詳情頁。

## 使用方法

```bash
python3 scripts/download_2026.py --start 2026-01-01 --end 2026-01-07
```

確認小範圍結果後，可下載全年截至今日的資料：

```bash
python3 scripts/download_2026.py
```

資料目錄：

```text
data/raw/info-gov-hk/
  indexes/2026/01/01.html
  bulletins/2026/01/01/<政府稿件ID>.html
  metadata/...
```

網站未有該日頁面、連線錯誤等情況會寫入 `data/raw/info-gov-hk/download-log.jsonl`。

## 解析已下載天氣稿

```bash
python3 scripts/parse_bulletins.py
```

衍生資料會寫入 `data/processed/bulletin-events.jsonl`。無法識別嘅稿件會記錄於
`data/processed/parse-errors.jsonl`，原始 HTML 不會被修改。
每個事件均保留政府天氣稿 `source_url`；每組警告亦會輸出完整
`source_references`，方便介面及匯出資料連回官方原文。

將公告組合成每一組警告，並推導自然過期或提早取消：

```bash
python3 scripts/build_series.py
python3 scripts/validate_series.py
```

保存及按十年批次審核天文台官方雷暴警告資料庫：

```bash
python3 scripts/download_warning_database.py
python3 scripts/audit_warning_database.py
```

完整年代兼容性結果見 `data/processed/compatibility-report.md`。

## 互動網站

網站使用Python標準函式庫及SQLite，毋須額外安裝套件：

```bash
python3 app.py
```

本機瀏覽 <http://127.0.0.1:8000>；其他Meshnet裝置使用
`http://<此電腦的Meshnet-IP>:8000`。伺服器預設監聽 `0.0.0.0`，可用
`--host 127.0.0.1` 限制只供本機使用。支援年度圖表、結果／資料完整度篩選、原文搜尋、
分頁、警告卡及完整事件時間線。

另外設有：

- `/evolution.html`：警告用字、模板及高影響天氣字句演化；
- `/analysis.html`：月份／時段熱圖、有效時間、延長及取消、地區與極端個案、
  archive完整度、跨暴雨／熱帶氣旋警告，以及觀測雷暴日數對照。

分析用外部官方資料可獨立更新：

```bash
python3 scripts/download_analysis_sources.py
```

所有跨警告結果按生效區間重疊計算；氣候對照只描述相關性，不代表因果。

## SQLite資料庫

```bash
python3 scripts/build_database.py
```

輸出為 `data/thunderstorm-warnings.sqlite3`。原始HTML及DAT仍然保留；SQLite用作查詢層。
`warning_series.weather_bulletin_status` 會區分：

- `available`：已有天氣稿及reference URL
- `not_archived`：舊年份沒有政府HTML archive
- `not_downloaded`：archive年代內但尚未下載或找到
- `archive_incomplete`：確認舊archive有缺漏

## 靜態網站及GitHub Pages

互動網站可以輸出成完全不需要Python server或SQLite嘅靜態版本：

```bash
python3 scripts/build_static_site.py
```

輸出位於 `dist/site/`。Build會預先產生搜尋／排序索引、分析資料，以及每組警告獨立
JSON；篩選、分頁及排序會喺瀏覽器執行，警告詳情則按需要載入。所有asset使用相對路徑，
所以同時支援 GitHub Pages project site（例如 `/repository-name/`）及custom domain。

Repository內嘅 `.github/workflows/pages.yml` 會在推送到 `main` 後重建SQLite、產生靜態網站
並部署到GitHub Pages。首次使用前，請在GitHub repository的 **Settings → Pages → Source**
選擇 **GitHub Actions**，並確保初始 `data/processed/bulletin-events.jsonl`、archive狀態及
分析JSON已加入repository。

全量下載所有官方雷暴警告生效日期上可取得嘅天氣稿：

```bash
python3 scripts/download_all_bulletins.py
```

下載器支援續跑，已保存HTML不會重複下載，已確認404日期會跳過。

重建、匯出及完整性審核：

```bash
python3 scripts/parse_bulletins.py
python3 scripts/build_database.py
python3 scripts/export_jsonl.py
python3 scripts/audit_full_dataset.py
```

## 每日更新及Open Data

每日流程會重新下載天文台官方記錄、覆查最近政府新聞稿，亦會自動追查狀態基線中
未曾檢查的警告日期，然後重建SQLite、JSONL、預先生成分析JSON及CSV Open Data套件：

```bash
python3 scripts/update_daily.py
```

輸出位於 `dist/open-data/`，包括 `warning-series.csv`、`bulletin-events.csv`、
`source-references.csv` 及 Frictionless Data `datapackage.json`。首次發布 repository
時須加入 `data/processed/` 內由 `.gitignore` 明確保留的解析及archive狀態基線，之後每日
流程只需合併新稿。GitHub Actions範本會在香港時間每日02:25執行，保存增量解析狀態，
並建立按日期命名的Open Data及近期原始HTML snapshot；正式發布前應把
`softprops/action-gh-release` 鎖定至已審核的 commit SHA。

程式碼採用MIT License；專案原創文件採用CC BY 4.0；政府來源及衍生數據按
[DATA.GOV.HK使用條款](https://data.gov.hk/tc/terms-and-conditions) 處理。詳情見
`LICENSE-DATA.md`。本專案並非香港天文台認可或提供的即時警告服務。
