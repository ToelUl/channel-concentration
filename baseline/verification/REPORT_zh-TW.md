# 公開候選包驗證報告

候選識別：CC-NUMERICAL-BASELINE-20260909 / rc1。狀態：本地程式與數值證據封裝驗證通過；尚未公開發布。整體論文 A1 驗收仍為 NOT_PASSED。

- 在新建的 conda 環境安裝固定版本依賴，未修改凍結的生產環境。
- 三個版本各自的 wheel 與 sdist 均安裝成功。從封裝檔解出測試後，在套件來源目錄之外執行，確認載入安裝到 site-packages 的程式。
- 0.5.0.dev0：45 項通過；0.5.1.dev0：58 項通過；0.5.2.dev0：69 項通過。這些測試包含重疊功能，不是 172 個不同科學任務。
- 五條 current 後處理流程通過：Potts FSS、Potts ranked、NNN ranked、Potts 7/5 與條件式 projector enclosure。前四條共六個 CSV 與基準逐位元組一致；enclosure 的數值結構與前提逐項一致。所有原始輸入保持原樣，未重跑大型求解。
- 額外執行 exact fast、Potts L6、NNN L6 J2=0.2 小型新計算，全部成功；依賴一致性檢查通過。
- 重核先前本地基準索引的 1,123 檔，全部未改動。
- 四份含私人路徑或本機識別碼的非必要原始憑證另存公開投影，明列原檔雜湊與改動欄位。已驗證的原始 checkpoint、數值與來源程式保持原樣。

詳細結果見 CLEAN_INSTALL_AND_REPLAY.json；隱私、封裝內容與來源一致性見 PAYLOAD_AUDIT.json。根目錄 MANIFEST.json 與 SHA256SUMS 綁定此候選的實際交付位元組。

檢查範圍不含 GitHub hosted CI、完整大型重算、稿件修訂或出版圖面驗收。程式與數據可先作為範圍明確的 development release；請保留 docs/KNOWN_LIMITATIONS.md 的所有科學限制。
