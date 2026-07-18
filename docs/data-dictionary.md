# 數據字典

Open Data 套件以三個主要資源組成：

- `warning-series.csv`：每行一組官方雷暴警告；官方起止時間不會被新聞稿內容覆蓋。
- `bulletin-events.csv`：每行一份已解析公告，記錄發出、延長、更新或取消及新有效時間。
- `source-references.csv`：適合只需追溯來源、而不需公告全文的輕量表。

時間均以 ISO 8601 儲存並保留當時香港時區 offset；歷史夏令時間為 `+09:00`，
標準時間為 `+08:00`。`start_utc_offset` 及 `end_utc_offset` 分開保存，令橫跨轉鐘時刻
的警告仍可準確表達（例如1975-04-19一組由 `+08:00` 轉為 `+09:00`）。
`terminal_type` 是專案分類，
`terminal_inferred=1` 表示結束類型並非直接由取消稿確認。`reported_warning_started_at`
及 `official_start_delta_minutes` 專門保留天氣稿所述開始時間與官方系列時間的差異。

`weather_bulletin_status`：

- `available`：有可配對天氣稿；
- `not_archived`：該年代或日期沒有可用政府 HTML archive；
- `not_downloaded`：尚未成功檢查；
- `archive_incomplete`：政府 archive 索引存在，但沒有可配對稿件。

完整欄位定義亦會寫入套件內的 `datapackage.json`。所有列均應透過
`official_source_url` 或 `source_url` 追溯原始來源。
