# S-Agent

> 英文版 [README.md](README.md) 為準，本檔為對照翻譯。

針對 **Codex、Claude Code 與 Antigravity（Gemini）**，依目前工作選角與分派 subagent。
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
尚未測試 Windows／Linux。

## Skill 新版檢查

每次 `/s-agent`（含 `-h`）先向 GitHub 查詢已發布的 skill 版本。
有新版時，選 `y` 更新或 `n` 跳過，再繼續原本請求。不會自動安裝更新；
查詢失敗仍可使用已安裝的 skill，但不宣稱已是最新版。

檢查程式只用 Python 標準函式庫，發送一次公開 HTTPS 請求，10 秒逾時，
不讀取憑證。也可直接執行：

```bash
python3.11 scripts/check_update.py
```

Skill 新版檢查與 Notion 的 model／effort 自動同步是兩件事。

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


## Gemini 角色設定

在 Notion JSON 的六個角色都加入 `gemini`，欄位為 `model` 與 `effort`。
舊有只含 `codex`、`claude` 的設定仍可使用。能力清單也必須包含 Gemini。
完整型號與強度存於 `~/.agents/roles/<role>.toml`，原生角色說明存於
`~/.gemini/config/agents/<role>.md`，模型層級設為 `inherit`。

派工時以 `agy --agent <role> --model <model> --effort <effort> -p <handoff>`
明確套用設定。原生 subagent 的層級本身無法證明完整型號與強度。
預設依目前主工具選平台：Gemini／Antigravity 使用 Notion 的 `gemini` 設定；
跨平台派工需要使用者明確指定，不會更換主 agent 的模型。只分析、審查或規劃的
CLI 派工明確加上 `--mode plan`，交接需附禁止編輯與專案測試限制。獨立 CLI session
不會自動繼承主 agent 的權限與 sandbox；派工前必須確認並套用同等限制，做不到就
留在原本已授權的 host。實際使用仍需登入與對應方案，主 agent 負責驗證結果。

Hydrogen 角色設定 `"effort": "high"` 時，預設使用 high。
單次需要 xhigh，可說 `/s-agent 這次用 Gemini reviewer / xhigh 審查這個修改`。
S-Agent 先驗證支援，再回報實際強度並傳入 `--effort xhigh`；不修改 Notion 或
已儲存的角色預設，後續派工回到設定值。`-h` 會列出預設 high 與可選 xhigh，
尚未確認執行支援時會明確標示。沒有自動升級。

## 角色與協調

| 角色 | 責任 |
|---|---|
| `planner` | 可執行的 plan：範圍、驗收條件、步驟與檢查 |
| `designer` | UI／UX、流程與無障礙 |
| `executor` | 照已核准的 plan 逐步實作 |
| `reviewer` | 獨立審查與測試 |
| `devops` | CI/CD、環境、log 與可靠性 |
| `security` | 程式碼、相依套件與設定的安全掃描 |

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

版本 1.0.2：隔離單元測試涵蓋嚴格驗證、保留設定、建立角色、未來模型名稱、
重複套用不寫入與失敗回復。Codex forward-test 曾真正分派修正 Python fixture，
並獨立通過五個回歸案例。這不等於 Claude 實際派工、所有帳號的模型權限或跨平台已驗證；
原生設定驗證也不等於真的呼叫模型。

[English](README.md) ·
[Claude subagents](https://code.claude.com/docs/en/sub-agents) ·
[Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)

[Antigravity subagents](https://antigravity.google/docs/subagents) · [Antigravity CLI](https://antigravity.google/docs/cli/reference/)
