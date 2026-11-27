# S-Agent

在 **Codex、Claude Code 與 Antigravity（Gemini）** 中（支援 **macOS、Linux 與 Windows**），對齊 `/uu`（`ai-usage`）的工作模式：日常開發、規劃、維運與 UI/UX 留在主線配 Skills，獨立審查（`reviewer`）與安全掃描（`security`）由 Notion 同步型號／effort 後開乾淨 subagent，並規定無關專案或純問答的外部 AI CLI 一律切到無專案的暫存目錄（macOS/Linux 用 `/tmp`；Windows 用 `$env:TEMP` / `%TEMP%`）執行以免重專案前綴狂燒 token。

```text
/s-agent -h
/s-agent 用乾淨暫存目錄開 Codex 幫我想這個重試佇列設計。
/s-agent 請獨立 reviewer 檢查這段 diff。
```

Codex 使用 `$s-agent`，參數相同。

## 安裝

安裝器需要 Node.js 22.20+ 與 npm；skill 與自動更新器執行時只需要 Python。一次安裝給三個工具：

```bash
npx skills add Jeinn-co/agent-skills -g --skill s-agent -a codex claude-code antigravity-cli -y
```

`-a` 只保留你使用且受支援的工具；不加 `-g` 則安裝到目前專案。預設共用模式將一份實體檔案放在 `~/.agents/skills/`，再接到各工具入口。沒有 Node/npm 時，請複製整個 skill 目錄（含 scripts、data、references）；不要將本機 symlink 提交到 repo。

需要：提供分派或 CLI 能力的 Codex／Claude Code／Antigravity、能讀取 Notion 的連接器或公開網頁工具，以及驗證／同步使用的 **Python 3.11+**。不包含 API key 或個人路徑；`ai-usage`、UI skills、`playwright-cli` 僅為選用搭配，沒有安裝也能跑。

## Skill 自動更新

每次 `/s-agent`（含 `-h`）先解析已安裝的 skill 路徑，從工作目錄執行（Windows 用 `py -3.11`，不要切進即將替換的 skill 目錄）：

```bash
python3.11 "<skill-dir>/scripts/check_update.py" --apply
```

有新版就自動下載安裝，不需 y/n；agent 重新讀取更新後的 `SKILL.md` 再繼續原本工作。開發用 checkout 不會被覆寫。檢查或下載失敗會顯示原因與本機版本，有可用本機副本時直接繼續。省略 `--apply` 可只查不更新。

## Notion 就是設定

[開啟共用 Notion 設定](https://honorable-ground-e97.notion.site/s-agent-config-effort-4118e936085b810891bdc1a77dd59b63)。
**S-Agent configuration** 下的 JSON 提供 `reviewer` 與 `security` 的 `model`／`effort`，**My usage configuration** 提供 `/uu` 與主線日常的 `daily` 設定。每次呼叫（含 `-h`）先嘗試讀 Notion；設定沒變就直接用本機，不寫檔也不建備份；設定有變或缺少檔案時，自動驗證能力清單、備份到 `~/.agents/s-agent-backups/` 並同步更新。

無法連線時沿用有效本機角色並標示「本機設定；Notion 無法連線」；格式錯誤或模型不支援時保留本機並停止派工。自動同步更新 Codex（`~/.codex/agents/`）、Claude（`~/.claude/agents/`）、共用來源（`~/.agents/roles/`）及 Antigravity（`~/.gemini/config/agents/`，`model: inherit`）的 `reviewer` 與 `security`，保留原有 prompt、工具與權限。來源 URL 記在 `~/.agents/s-agent-source.json`。

## 對齊 `/uu` 的模式與乾淨暫存目錄隔離規則

| 模式／角色 | 職責 | 執行方式 |
|---|---|---|
| 主線 + Skills | 規劃、實作、維運、UI/UX 設計 | 留主對話用 `daily` 型號／effort＋按需載入已安裝 Skills（如 Claude 用 `frontend-design`、Codex 用 `impeccable`、Antigravity 用 `ui-ux-pro-max`，皆可搭 `web-design-guidelines`）。 |
| `reviewer` | 獨立審查與 QA | 獨立乾淨上下文（嚴禁 fork），套用 Notion `reviewer` 設定。 |
| `security` | 唯讀安全掃描 | 獨立唯讀乾淨上下文（嚴禁 fork），套用 Notion `security` 設定。 |
| 乾淨暫存目錄外部 CLI | 純問答、第二意見、無關當前 repo 的查詢 | 切到 `/tmp`（macOS/Linux）或 `$env:TEMP`／`%TEMP%`（Windows，或 `codex exec -C`；不用 `cd /tmp` 與 PS 5.1 不支援的 `&&`）再啟動外部 CLI；Claude `claude -p` 加 `--strict-mcp-config --setting-sources user`（純問答加 `--no-session-persistence --tools ""`，不預設加會跳過 OAuth 登入的 `--bare`）。 |

在 Antigravity 預設優先使用 `invoke_subagent`（`model: inherit`）；僅在明確要求或高風險掃描需鎖定精確 `[gemini]` 型號／強度（如 `gemini-4-neon` / `xhigh`）時，才切到目標 repo 以 `agy --agent <role> --model <model> --effort <effort> -p <handoff>` 執行（唯讀任務加 `--mode plan`）。派工前必先告知使用者派了誰與怎麼派。

## 工具與驗證

Host 讀取 Notion 後，將 JSON 與當前能力清單交給 [`scripts/sync_roles.py`](scripts/sync_roles.py)（僅用 Python 標準函式庫；過渡期也相容舊 Notion 的 4 個 legacy role key，但不會寫出舊角色檔）。完整流程見 [SKILL.md](SKILL.md)。

```bash
python3.11 scripts/sync_roles.py POLICY.json --catalog CATALOG.json  # 預覽
python3.11 scripts/sync_roles.py POLICY.json --catalog CATALOG.json --apply  # 加 --codex-daily／--claude-daily MODEL:EFFORT 與 --gemini-daily "<agy label>" 可讓主線預設對齊 Notion daily
```

[English](README.md) ·
[Claude subagents](https://code.claude.com/docs/en/sub-agents) ·
[Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) ·
[Antigravity subagents](https://antigravity.google/docs/subagents)
