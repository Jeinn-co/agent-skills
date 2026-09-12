# Jeinn Agent Skills

> 中文版。英文版 [README.md](README.md) 為準，本檔為對照翻譯，兩邊同步更新。

給 Claude Code、Codex CLI、Grok Build，以及任何讀 `SKILL.md` 慣例的 agent 使用的
skills。內容不綁定任何特定 host。

```bash
npx skills add Jeinn-co/agent-skills@ai-usage
```

[在 skills.sh 上瀏覽](https://skills.sh/jeinn-co/agent-skills) · English: [README.md](README.md)

> 安裝前請先讀該 skill 自己的 README —— 裡面列出你機器上需要先有什麼。

## Skills

| Skill | 做什麼 | 說明文件 |
|---|---|---|
| [`ai-usage`](skills/ai-usage/) | 一份報表看完 Claude、ChatGPT、Grok 三邊訂閱還剩多少 —— 用掉幾 %、各視窗何時重置、還有多少加購額度。 | [English](skills/ai-usage/README.md) · [中文](skills/ai-usage/README.zh-TW.md) |

## 安裝

```bash
npx skills add Jeinn-co/agent-skills@ai-usage     # 只裝這一個 skill
npx skills add Jeinn-co/agent-skills              # 裝整個 repo
```

或是直接把 skill 目錄複製到你的 agent skills 資料夾 —— `~/.claude/skills/`、
`~/.codex/skills/`、`~/.grok/skills/`。

**安裝前請先讀該 skill 自己的 README** —— 每個 skill 都列出了它需要你機器上先有什麼。
安裝時只會複製該 skill 的目錄，所以它的 README 會跟著走，而這一頁不會。

## 慣例

- **英文為準。** 文件旁邊的 `.zh-TW.md` 是鏡像；一邊改動，另一邊在同一個 commit 裡跟著改。
- **說明跟著 skill 走。** 使用者裝完之後會需要的內容，一律放在 `skills/<name>/` 裡面，
  不放在這裡。這一頁只是索引。
- **版本靠手動維護。** `SKILL.md` frontmatter 裡有 `metadata.version`，skill 執行時也會
  印出自己的版本，讓已安裝的副本能自報身分。但工具鏈不會讀也不會強制檢查任何一邊 ——
  安裝 skill 就只是複製檔案，不會留下任何來源紀錄。

## 授權

MIT
