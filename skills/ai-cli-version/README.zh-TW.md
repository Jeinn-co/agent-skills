# ai-cli-version

> 中文版。英文版 [README.md](README.md) 為準，本檔為對照翻譯，兩邊同步更新。

一份報表看你的 Claude Code、Codex、Grok Build、Muse Code CLI 是不是最新版 —— 你目前的版本和安裝時間，
以及最新版本和發佈時間。

版本檢查永遠是唯讀的。有任一 CLI 不是最新版時，agent 會提供兩個選項：按 `y` 更新全部
過期 CLI，按 `Esc` 全部跳過。

可在 Claude Code、Codex CLI、Grok Build，以及任何讀 `SKILL.md` 慣例的 agent 使用，
不綁定特定 host。

> **目前已在 Windows 與 macOS 上測過，Linux 尚未測試。** 程式有 Linux 的處理，安裝路徑
> 也對照過各家安裝腳本，但尚未在 Linux 上實際執行。如果出錯，請附上 `./run.sh` 的輸出
> 開 issue。

## 安裝前必讀

### 1. Python 3.9 以上

只用標準函式庫，不需要 `pip install`，不需要虛擬環境。

```bash
python --version     # 或: python3 --version   /   py --version  (Windows)
```

Windows 上請避開 `python3` 這個別名：它常常是 Microsoft Store 的 stub，執行後會跳出
商店頁面而不是跑程式。

macOS 的 `/usr/bin/python3`（3.9）來自 Xcode Command Line Tools；沒裝的話，第一次執行會跳出
安裝視窗。Homebrew 的 `python3` 也可以。如果 Python 是從 python.org 裝的，請先執行一次它附的
`Install Certificates.command` —— 沒跑的話所有 HTTPS 請求都會出現 `CERTIFICATE_VERIFY_FAILED`，
每個工具都顯示 `check failed`。

### 2. 你想檢查的 CLI

| 工具 | CLI |
|---|---|
| Claude Code | `claude` |
| Codex | `codex` |
| Grok Build | `grok` |
| Muse Code | `muse` |

**四個不必裝滿。** 沒裝的工具會印 `not installed`，其他照常執行。讀取版本不需要登入。

### 3. 網路與 subprocess 權限

這個 skill 會執行上面的 CLI，並對 `registry.npmjs.org` 和 `api.github.com` 發 HTTPS
請求。**不需要 npm 或 Node.js** —— 直接查 npm registry。

## 安裝

Global 安裝，一次裝到三個 CLI：

```bash
npx skills add Jeinn-co/agent-skills@ai-cli-version -g -a claude-code codex grok -y
```

拿掉 `-a ...` 會改成互動式選擇，也可以只列你有在用的。`-g` 會裝在家目錄，所有專案都看得到：

| Agent（`-a`） | Global skills 資料夾 |
|---|---|
| `claude-code` | `~/.claude/skills/`（或 `$CLAUDE_CONFIG_DIR/skills/`） |
| `codex` | `~/.codex/skills/`（或 `$CODEX_HOME/skills/`） |
| `grok` | `~/.grok/skills/`（或 `$GROK_HOME/skills/`） |

不加 `-g` 則是裝進目前的專案。

也可以自己把 `skills/ai-cli-version/` 目錄複製到上面的資料夾。Windows 上請複製，不要用
symlink。macOS 或 Linux 複製後請確認 `run.sh` 仍可執行（`chmod +x run.sh`）。

如果 `/ai-cli-version` 沒有立刻出現，請開新對話或重新啟動 agent，讓它重新載入 skill 清單。

## 更新

```bash
npx skills update ai-cli-version -g -y    # global 安裝
npx skills update ai-cli-version -p -y    # project 安裝
```

手動複製的 skill 不會被追蹤；需要再次複製目錄才能更新。

## 使用

把 skill 名稱當 slash command 輸入：

    /ai-cli-version

或直接問 ——「CLI 是最新版嗎？」、「檢查更新」、「這版 Codex 什麼時候發佈的？」。每次都即時查詢，
沒有快取也沒有參數。有一個以上版本過期時，它會先顯示報表，並等你明確輸入 `y` 才執行更新；
輸入 `Esc` 則不變更任何 CLI。

在 agent 外面執行時，先切到已安裝的 `ai-cli-version` 目錄 —— 例如
`~/.claude/skills/ai-cli-version` —— 再用對應平台的啟動方式：

```bash
./run.sh          # macOS 或 Linux（如果執行權限不見了，改用 `sh run.sh`）
py -3 run.py      # Windows；沒有 `py` 就用 `python run.py`
```

加上 `--version` 會只印出 skill 版本。在 agent 外面執行時看到的是原始的 tab 分隔輸出，
不是排好版的報表。

## 輸出範例

`/ai-cli-version` 在 09-27 執行，四個 CLI 都是最新版：

![ai-cli-version 報表](images/demo.png)

每一列顯示你裝的版本與安裝時間、最新版本與發佈時間、狀態，以及更新 channel。Grok Build
的發佈時間來自第三方鏡像，所以加上 `≤` 和 `*` 註腳；Muse Code 的 channel 不帶日期，發佈
時間一律是 `?`。最後一行是 `All up to date.`，或列出有更新的 CLI。

有 CLI 過期時，該列會在最後附上更新指令，agent 會先問過你才執行。純文字版，一個 CLI 過期的例子：

```
CLI VERSIONS — 09-24

  Tool          Installed                     Latest                             Status
  Claude Code   2.1.274 (09/17 11:20)         2.1.274 (released 09/17 06:36)     ✓ up to date   channel: latest
  Codex         0.153.4 (09/07 11:03)         0.154.0 (released 09/10 06:40)     ↑ update → codex update
  Grok Build    1.0.34 (09/17 09:28)          1.0.34 (released ≤ 09/17 03:32*)   ✓ up to date   channel: stable
  Muse Code     1.3.0-R3401.1 (09/24 11:08)   1.3.0-R3401.1 (released ?)         ✓ up to date   channel: muse-stable

  * Grok release time is approximate (third-party mirror); official: x.ai/build/changelog
  → 1 update available: Codex.

  現在更新 1 個過期的 CLI？
  [y] 全部更新    [Esc] 跳過
```

這個選項只會在 agent 裡出現。單獨執行 `run.py` / `run.sh` 永遠只檢查，仍會輸出原始報表資料，
也不會接受更新選項。

## 每個數值的來源

| 工具 | 本機版本 | 安裝時間 | 最新版本 | 發佈時間 |
|---|---|---|---|---|
| Claude Code | `claude --version` | `~/.local/share/claude/versions/<本機版本>` | npm registry，dist-tag = `settings.json` 的 `autoUpdatesChannel`（預設 `latest`） | npm 發佈時間 |
| Codex | `codex --version` | `$CODEX_HOME/packages/standalone/releases/<本機版本>-*` | npm registry，`@openai/codex` 的 `latest` | npm 發佈時間 |
| Grok Build | `grok update --check --json` | `~/.grok/downloads/grok-<本機版本>-*` | 同一個指令 | `timoteuszelle/x.ai-grok` 的 GitHub release（近似值） |
| Muse Code | `muse --version` | `muse` launcher 旁邊的 `muse-bin-<本機版本>*` | `https://api.meta.ai/muse-code/channels/<channel>`（公開，就是 launcher 讀的那個檔） | 無（`?`） |

`settings.json` 從 `$CLAUDE_CONFIG_DIR` 讀，沒設就讀 `~/.claude`。`$CODEX_HOME` 預設是
`~/.codex`。如果安裝時間的路徑不存在 —— 例如 npm 或 Homebrew 安裝，或是 macOS/Linux 的
Grok installer 把檔案存成不含版號的 `~/.grok/downloads/grok-<platform>` —— 就改看指令背後
實際的執行檔。

為什麼不用 CLI 自己的更新指令：`claude update` 和 `codex update` 會直接安裝，沒有只檢查
的選項。`grok update --check` 有，所以 Grok 用它。Muse 完全沒有更新子指令：它的
launcher 每次執行都會在背景自我更新。檢查時設 `MUSE_NO_AUTO_UPDATE=1` 保持唯讀；提供的
更新指令設 `MUSE_SYNC_UPDATE=1`，讓 launcher 立刻更新。

## 限制與已知問題

**Grok 的發佈時間是近似值。** 官方 changelog `x.ai/build/changelog` 對腳本請求回 403，
`grok update --check --json` 也沒有日期。這裡的時間來自第三方的 NixOS 套件：它偵測到
Grok Build 新版時會發 GitHub release，所以官方發佈時間*不晚於*這個時間。如果那個 mirror
停止更新，Grok 的發佈時間會顯示 `?`。

**Muse 沒有發佈時間。** channel manifest 只有版本、沒有日期，所以 Muse 的發佈時間一律
顯示 `?`。channel 取 `$MUSE_CHANNEL`，沒設就讀 launcher 旁邊的 `.muse-channel`，再沒有就是
`muse-stable`。

**假設原生版跟 npm 同步。** Claude Code 和 Codex 的原生安裝版不是透過 npm 發佈的。這個
skill 假設原生版的版號跟 npm 套件一致；驗證時版號確實相同，但沒有官方文件說明這一點。

**安裝時間取決於檔案系統。** Windows 和 macOS 會記錄資料夾建立時間。Linux 無法從 Python
取得建立時間，所以改用資料夾的修改時間，可能比實際安裝時間晚。早於 2015 年的時間戳一律捨棄。

**安裝時間的路徑是各家目前的原生安裝結構。** 如果路徑改變，skill 會改看實際的執行檔，
準確度可能下降。

**更新指令只在原生安裝版上驗證過。** 列出的是 CLI 自己的更新指令。如果你是用 Homebrew 或 npm
安裝，用同一個套件管理工具更新（`brew upgrade`、`npm install -g`）比較保險。

**下載量。** `@openai/codex` 的 npm registry 文件約 14 MB（列出所有版本），每次執行約需一兩秒。

**已驗證**：2026-09-17，Windows 11（zh-TW，Python 3.12），`claude` 2.1.274、
`codex` 0.154.0、`grok` 1.0.34。同一天已對照 Codex 與 Grok 的安裝腳本
（`chatgpt.com/codex/install.sh`、`x.ai/cli/install.sh`）確認路徑。

**已驗證**：2026-09-18，macOS 26.6.2（arm64，Python 3.10.8），`claude` 2.1.273、
`codex` 0.154.0、`grok` 1.0.34。唯讀檢查 launcher、版本與安裝時間查詢，以及安裝到
Claude Code、Codex、Grok Build 三個 agent 的 global 安裝流程皆成功。Linux 尚未測試。

**已驗證** 2026-09-24 在 Windows 11（zh-TW、Python 3.12）上針對 Muse Code 1.3.0-R3401.1：
版本、安裝時間、channel 查詢，以及更新指令在 bash 與 PowerShell 下都能執行。Muse 在
macOS 與 Linux 尚未測試；POSIX launcher（`api.meta.ai/muse-launcher.sh`）用的是同樣的檔名與變數。

## 授權

MIT
