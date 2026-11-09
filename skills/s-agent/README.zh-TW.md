# S-Agent

> 英文版 [README.md](README.md) 為準，本檔為對照翻譯。

針對 **Codex 與 Claude Code**，依目前工作選角與分派 subagent。
Notion 決定各角色的 model／effort；主 agent 負責協調與驗證。

```text
/s-agent -h
/s-agent 修這個 bug，完成後請另一個 agent review。
```

Codex 使用 `$s-agent`，參數相同。

## 安裝

```bash
npx skills add Jeinn-co/agent-skills@s-agent
```

也可把整個目錄複製到 `~/.codex/skills/s-agent/` 或 `~/.claude/skills/s-agent/`。
沒有出現時開新對話。安裝器需要相容的 Node.js/npm；手動複製不需要。

需要：提供分派工具的 Codex／Claude Code、能讀取 Notion 的連接器或公開網頁工具，
以及驗證／同步使用的 **Python 3.11+**。不包含 API key 或個人路徑。

測試過的平台：

| OS | 狀態 |
|---|---|
| Windows 11（10.0.26300） | 1.0.3，2026-11-09，Python 3.12.10：實際 `--apply` 寫入 Claude Code + Codex 角色檔。未實際派工。 |
| macOS | 未記錄。 |
| Linux | 尚未測試。 |

## Notion 就是設定

[開啟共用 Notion 設定](https://honorable-ground-e97.notion.site/s-agent-config-effort-4118e936085b810891bdc1a77dd59b63)。
**S-Agent configuration** 標題下唯一的 JSON 區塊是設定本體。
修改角色的 `model` 或 `effort`，下次使用 S-Agent 就會自動同步變更。
不必另下 sync，也不必為了新增已支援的模型更版 skill。
可在請求中提供符合相同 schema 的自有 Notion 設定頁 URL。

每次呼叫（含 `-h`）都先嘗試讀 Notion。驗證後設定沒變，就直接使用本機角色，
不寫檔、不建立備份；設定改變或缺少角色時，自動驗證 model／effort、預覽、備份後套用。
不必再輸入 `sync`。`-h` 顯示角色、來源與讀取時間；可同步設定，但不派 agent、不執行任務。

Notion 或讀取工具無法連線時，沿用有效本機角色，明確標示「本機設定；Notion 無法連線」，
不把 local 值當成最新 Notion。沒有可用本機角色時才回報缺少設定。
連線成功但設定格式錯誤、內容不完整或模型不支援時，保留本機檔案並停止派工。

模型版本直接寫在既有的 `model` ID；help 顯示完整 ID。別名會標為別名，
只有 host 回傳解析結果才顯示實際版本；設定不等於已執行該模型。
各角色預設是本設定的選擇，不代表業界統一標準。

自動同步更新 Codex／Claude 原生角色與既有共用角色來源，保留 prompt、工具及權限；
缺少角色時用最小責任說明建立。複雜格式或 symlink 會在寫入前拒絕。
寫入失敗會回復；相同設定不重寫。備份位於 `~/.agents/s-agent-backups/`，
來源 URL 記錄在 `~/.agents/s-agent-source.json`。
舊的 `/s-agent sync [Notion URL]` 仍可相容為只更新、不派工的呼叫，但不是必要步驟。

套用必須有 host 取得的當前能力清單，不能把期望設定當成可用能力。
文件列為支援不代表帳號一定有權限；無法查證支援就不套用。
執行中的 agent 不會換模型；修改角色後可能需要重開 host／新對話。
派工發現設定不符會提示，不會默默使用舊模型。

## 角色與協調

| 角色 | 責任 |
|---|---|
| `pm`／PO | 需求、範圍、優先順序與驗收條件 |
| `designer` | UI／UX、流程與無障礙 |
| `developer` | 追程式、實作與修正 |
| `qa` | 重現、回歸測試與驗收 |
| `reviewer` | 獨立檢查正確性與安全 |
| `devops` | CI/CD、環境、log 與可靠性 |

先用一個 subagent；僅在工作獨立時增加，最多三個且遵守 host 更低上限。
清楚分配檔案責任，有依賴的工作依序執行，相關後續沿用 agent。
小事可由主 agent 直接做；不會從開啟的編輯器檔案自行發明任務。
沒有分派工具時，不宣稱有 agent 執行。

授權限於目前任務與必要後續。原本的核准關卡、瀏覽器偏好與測試環境都要遵守。
要求規劃就只規劃；角色本身不授權部署、發布或外部寫入，也不保證總 token 更省。

## 工具與驗證

Host 讀取 Notion，將嚴格 JSON 與當前能力清單交給
[`scripts/sync_roles.py`](scripts/sync_roles.py)。工具僅用 Python 標準函式庫，
沒有網路或 token 功能；完整流程見 [SKILL.md](SKILL.md)。
CLI `--help` 說明工具參數；`/s-agent -h` 才是會讀 Notion 的 agent 說明。

```bash
python3.11 scripts/sync_roles.py POLICY.json --catalog CATALOG.json  # 預覽
python3.11 scripts/sync_roles.py POLICY.json --catalog CATALOG.json --apply
```

版本 1.0.3：隔離單元測試涵蓋嚴格驗證、保留設定、建立角色、未來模型名稱、
重複套用不寫入、失敗回復，以及 Windows 安全的檔案替換（暫存檔關閉後才改名）。Codex forward-test 曾真正分派修正 Python fixture，
並獨立通過五個回歸案例。這不等於 Claude 實際派工、所有帳號的模型權限或跨平台已驗證；
原生設定驗證也不等於真的呼叫模型。

[English](README.md) ·
[Claude subagents](https://code.claude.com/docs/en/sub-agents) ·
[Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
