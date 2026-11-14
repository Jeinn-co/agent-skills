# Prompt audit：自寫的 command 與 skill（2026-11-14）

用 `/claude-api prompt-audit` 的流程，檢查使用者自己寫的 command 與 skill 裡有沒有過時、互相矛盾或只對舊模型有用的寫法。

## 前提

- **目標模型**：Claude Opus 5.5（由使用者指定，也是執行審查的模型）。
- **範圍**：
  - `~/.claude/commands/*.md`，共 19 個。
  - `~/jeInn/agent-skills/skills/` 的 ai-usage、ai-cli-version、s-agent。
  - 自寫的 skill：check-uu、pp、feats、fix-git-gpg、show-tk、w-report、pack4prod、staging-basic-auth。
- **不在範圍**：
  - `~/.agents/.skill-lock.json` 登記的第三方 skill。
  - impeccable、ponytail、playwright-cli、caveman 等從上游安裝的 skill。這些改了也會被上游更新蓋掉。
- **影響範圍**：除了 ai-usage 的原始碼，其餘都是使用者層級的設定，改動會影響所有專案。
- **ai-usage**：安裝版會被自動更新覆蓋，所以修改要改在 `~/jeInn/agent-skills` 的原始碼。

## 結論

整體很乾淨。沒有大寫強調堆疊，沒有「think step by step」或 scratchpad 這類給舊模型的寫法，也沒有固定的進度回報節奏。問題集中在三類：

1. **說明過時。** `/uu` 和 `/check-uu` 列出的支援工具比 skill 現在少。
2. **兩份規則打架。** `/d-report w` 和 `/w-report` 對週報的規定不同。
3. **規則只寫在文字裡，工具沒有擋。** `cclean` 的刪除限制只是文字，`allowed-tools` 卻允許任何 `rm -rf`。

各組數量：

- 第 1 組（過時的提示文字）：4 項。
- 第 2 組（skill 與設定檔脆弱處）：7 項。
- 第 3 組（tool 描述）：不適用。
- 第 4 組（架構）：2 項。

## 發現與處理

| # | 位置 | 問題 | 對應規則 | 信心 | 處理 |
|---|---|---|---|---|---|
| 1 | `~/.claude/commands/uu.md:3-4` | 寫「Claude, ChatGPT, Grok and Muse, CursorBench」。實際上 ai-usage 現在包含 Gemini，分數來源是 Artificial Analysis | 2：過時內容 | 高 | 已改寫 |
| 2 | `~/.claude/commands/check-uu.md:3`<br>`~/.claude/skills/check-uu/SKILL.md:3` | 只寫「Claude Code, Codex and Grok Build」。實際上 ai-cli-version 也會查 Muse 和 Antigravity | 2：過時內容 | 高 | 已改寫 |
| 3 | `skills/ai-usage/references/providers.md:171` | 「will be removed on 2026-11-18」寫的是未來式，過了那天就錯了 | 2：會隨時間失效的內容 | 中 | 已改寫 |
| 4 | `skills/ai-usage/references/providers.md:175` | 標題「(moved from SKILL.md)」是在描述跟舊版本的差異，讀的模型看不到舊版本 | 1d：相對舊版的寫法 | 中 | 已改寫 |
| 5 | `~/.claude/commands/d-report.md:118` | 「目前 2026-Q3 頁：URL」，現在已經是 Q4 | 2：過時內容 | 高 | 已刪除這行，之後整個 d-report 也移除 |
| 6 | `~/.claude/commands/d-report.md:124` | 「（曾犯此錯：7/1 偷懶…）」是事件紀錄。上面 121-123 行已經把規則寫清楚了 | 2：事件紀錄 | 中 | 已刪除這行，之後整個 d-report 也移除 |
| 7 | `~/.claude/skills/w-report/SKILL.md:35` | 「曾經把上週五算成 9/26」，原因值得留，事件細節不用 | 2：事件紀錄 | 中 | 已改寫 |
| 8 | `~/.claude/commands/hotfix.md:29-33`<br>`~/.agents/skills/feats/SKILL.md:34-38` | 「不要進 plan mode、不要寫 code、STOP、不准自動往下做」同一件事講了 4 次。重複強調會讓模型過度套用 | 1a 強調用語、1c 填充 | 中 | 已合併成一句 |
| 9 | `~/.claude/commands/cclean.md:4,15-28` | 刪除規則只寫在文字裡，`Bash(rm -rf *)` 權限沒有限制範圍 | 1d：沒有被執行的規則 | 中 | 已改用 `git clean`，它本來就只刪未追蹤的檔案 |
| 10 | `~/.claude/commands/wo-time.md`（說明第 5 行） | 要模型自己重算每段工時和每日小計，算術應該交給程式 | 1b 計算交給程式、第 4 組 | 中 | 使用者決定不再使用：wo-time、wo-set、wo-reset 都移到垃圾桶 |
| 11 | `~/.claude/commands/d-report.md:66-77` | 日期計算和 JSONL 解析每次都由模型手動做。`w-report` 已經改用 `collect.py`，原因就是模型算錯日期 | 第 4 組：固定流程交給模型 | 中 | 使用者決定不再使用：d-report 移到垃圾桶 |

## 衝突的處理結果（使用者已決定）

- **A：週報格式。**
  - 原本 `d-report w` 用「下午報告」格式，`w-report` 用「M/D (五) 報告」格式，兩者寫進同一個 Notion 頁。
  - 處理：留 `w-report`。`d-report.md` 整個移到 `~/.Trash/`。
- **B：測試規則。**
  - 原本全域 `AGENTS.md` 規定沒有明確要求就不跑檢查，但 `pp` 會主動跑 formatting 和 static checks，`sync-spec` 會主動跑 `/bb`。
  - 處理：兩個都拿掉。
    - `pp/SKILL.md:19` 改成「Do not run formatting, static checks or tests unless the user asks for them」。
    - `sync-spec.md` 刪掉 `/bb` 驗證步驟，以及 `-f` 說明裡的「verify」。
- **C：重複定義。**
  - `/uu` 和 `/check-uu` 各有三份定義：command、`~/.claude/skills` 裡的 skill、`~/.agents/skills` 裡的 symlink。
  - 處理：只修文字，不刪檔。原因是不確定刪掉 command 後 symlink 會不會接手。
- **範圍外的 bug。**
  - `wo-set.md:11` 會把訊息直接塞進 Python 程式碼，有注入問題。
  - 處理：`wo-set.md` 已隨 wo-time 一起移除。

## 已知風險

- **#9**：`git clean -x` 也會刪掉列出路徑底下被 git 忽略的檔案，例如 `.env`。指令只列 artifact 路徑來降低這個風險。
- **#3、#4**：改在 agent-skills repo，還沒 commit，也還沒發佈。

## 之後

每次換新的模型世代，都再跑一次 `/claude-api prompt-audit`。Codex 的獨立掃描結果附在下方。

## Codex 獨立掃描（同一範圍）

Codex 一共列出 25 項。下面依目前狀態分組。

**已經不適用，或已經修好：**

| Codex 項目 | 狀態 |
|---|---|
| 1、10-15、25（d-report 部分） | 相關檔案已經移除：wo-time、wo-set、wo-reset、d-report |
| 5（pp / sync-spec 自動跑檢查） | 已修，見衝突 B |
| 18（providers.md） | 抓到本次改錯的地方：「removed on 2026-11-18」那天還沒到。已改成「announced the removal of … on 2026-11-18」 |

**還成立，等使用者決定要不要修：**

| # | 位置 | 問題 | 建議 |
|---|---|---|---|
| C1 | `~/.claude/commands/local-stop.md:4` | `pkill -x devtunnel` 會把 `/localv` 的 tunnel 一起停掉 | 改成 `pkill -f "devtunnel host dkk-local"` |
| C2 | `~/.claude/skills/check-uu/SKILL.md:14-17` | 不管什麼情況都會執行 `run.sh`。這跟原 skill 的 setup 模式衝突（setup 不該跑報告），參數也沒有傳下去 | 刪掉執行區塊，只轉交給原 skill 並傳遞參數 |
| C3 | `~/.claude/commands/cclean.md` | 會直接刪掉未追蹤的 `*.png`、`public/*.svg`，這些可能是使用者還沒 commit 的原始素材。全域 AGENTS.md 規定破壞性動作要先確認 | 刪除前先列出檔案清單並詢問 |
| C4 | `~/.agents/skills/staging-basic-auth/SKILL.md:54` | 「Use the first tool you already have」會在沒有 playwright-cli 時默默換成別的工具。AGENTS.md 規定這種情況要先回報 | 改成：沒有 playwright-cli 時先回報 |
| C5 | `~/.claude/skills/show-tk/SKILL.md:87` | `transitionJiraIssue` 只帶 `sprintId`。依 Codex 的說法，這不符合工具的參數規格（尚未驗證） | 先查 Atlassian MCP 實際怎麼把單放進 sprint |
| C6 | `~/.claude/commands/bb.md:15,19` | 用 `awk '{print $2}'` 解析檔名，遇到空白或改名會出錯；`npx`/`bunx` 可能自動下載套件，違反「不安裝」 | 改用 NUL 分隔的 git 輸出，只用本地已安裝的執行檔 |
| C7 | `~/.claude/commands/sync-spec.md:33,49` | spec 下載兩次，兩次之間後端如果更新，產出的型別和存下的 spec 會不一致；提早結束時也沒有比對目的檔 | 用同一份下載的檔案產生型別；每次都同步目的檔 |
| C8 | `skills/ai-cli-version/references/markdown-report.md:48,64` | 有工具檢查失敗時，標題仍可能顯示「全部是最新」；也留著舊的 HTML 規則 | 有失敗時標成「檢查未完成」，並刪掉重複的 HTML 規則 |
| C9 | `skills/ai-usage/references/setup.md:9`<br>`providers.md:53-89` | setup 只列出已安裝 CLI 的服務，但 Claude 其實可以只靠瀏覽器取得用量；providers.md 混著調查過程的紀錄 | 把瀏覽器來源也列進可選服務；調查紀錄移到維護筆記 |
| C10 | `skills/s-agent/SKILL.md:47,71,196` | 「先更新、讀取、同步」的流程在好幾段重複寫 | 合併成一段共用的前置流程 |
| C11 | `~/.claude/skills/fix-git-gpg/SKILL.md:25-34` | 寫死 `gpg.format ssh`，另外加的 husky hook 也是多餘的 | 先確認 repo 實際用的簽章格式，只修本機設定 |
| C12 | `~/.claude/skills/w-report/SKILL.md:44` | 父頁名稱寫死「work report 2026」 | 年份改由報告日期計算 |

### C1-C12 的處理結果（使用者決定全部處理）

| # | 結果 |
|---|---|
| C1 | `local-stop` 改成只停 `dkk-local`：`pkill -f "devtunnel host dkk-local"` |
| C2 | check-uu alias 拿掉直接執行 `run.sh` 的區塊，改成轉交給 ai-cli-version 並傳遞參數 |
| C3 | cclean 改成先列出檔案清單和大小，問過使用者才用 `git clean -fdx -- <確認的路徑>` 刪除；`allowed-tools` 拿掉 `git clean`，所以刪除前一定會跳出權限確認 |
| C4 | staging-basic-auth 預設用 playwright-cli；沒有時先回報，再改用 Playwright MCP 或 `login.mjs`；使用者有指定工具就照指定 |
| C5 | 經查 `transitionJiraIssue` 的參數規格，只帶 `sprintId` 是合法的，Codex 這點判斷錯誤，所以不改。另外 Step 3 原本沒讀目前 sprint，現在補上從 `customFields.Sprint` 讀 |
| C6 | bb 改用 NUL 分隔的 `git diff`/`git ls-files` 取檔名，只執行 `node_modules/.bin/` 裡的工具；script 會影響整個 repo 時要在報告裡說明 |
| C7 | sync-spec 改成從同一份已存的 spec 產生型別；spec 或 api.ts 沒變時也照樣同步 `all-models.ts`；`-f` 改成「即使 spec 沒變也重新產生」 |
| C8 | markdown-report：有檢查失敗時，標題寫 `check incomplete`；刪掉跟 `SKILL.md` 重複的 HTML 規則（程式碼本來就會印出 Check failed，不用改） |
| C9 | ai-usage：setup 允許在沒有 Claude CLI、但有連接瀏覽器時選 Claude；Requirements 補上瀏覽器來源；providers.md 的調查經過改成精簡的維護筆記和「Unsupported routes」 |
| C10 | s-agent：「先更新、讀取、同步」只在〈Load the current configuration〉寫一次，刪掉 help 和 dispatch 段落裡重複的提醒 |
| C11 | fix-git-gpg：先查 repo 實際用的簽章格式（ssh 或 openpgp）再設定本機；只有本機設定也一直被重設時，才加 husky hook |
| C12 | w-report：父頁名稱改成用報告日的年份，例如「work report <年>」；該年的父頁不存在時先問使用者 |

這些修改都沒有實際跑指令測過（依使用者的規則）。
