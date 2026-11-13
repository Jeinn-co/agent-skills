"""Model facts and the dated personal role assignments; no rendering or network I/O."""

GEMINI_MODELS = {'gemini-4-hydrogen': {'name': 'Gemini 4 Hydrogen',
                       'efforts': ('low', 'medium', 'high', 'xhigh'),
                       'default_effort': 'high',
                       'use_cases': ('Everyday coding and agent execution; recommended upgrade '
                                     'from 3.8 Flash.',
                                     '日常程式與 agent 實作；3.8 Flash 的建議升級版。')},
 'gemini-4-carbon': {'name': 'Gemini 4 Carbon',
                     'efforts': ('low', 'medium', 'high'),
                     'default_effort': 'medium',
                     'use_cases': ("Google's strongest frontier model, for complex architecture, "
                                   'difficult debugging and security audits.',
                                   'Google 定位最強的前沿模型，適用複雜架構、疑難除錯與安全稽核。')},
 'gemini-4-argon': {'name': 'Gemini 4 Argon',
                    'efforts': ('low', 'medium', 'high'),
                    'default_effort': 'medium',
                    'use_cases': ('Advanced long-horizon tasks.', '進階長時程任務。')},
 'gemini-3.8-flash': {'name': 'Gemini 3.8 Flash',
                      'efforts': ('low', 'medium', 'high'),
                      'default_effort': 'medium',
                      'use_cases': ('Previous-generation everyday model; Google recommends '
                                    'upgrading to Hydrogen.',
                                    '上一代日常模型；Google 建議升級至 Hydrogen。')}}

ROLE_ASSIGNMENTS = ({'role': 'Planner',
  'description': ('executable plan with scope, acceptance criteria and steps',
                  '可執行的 plan（範圍、驗收條件與步驟）'),
  'models': {'anth': ('Opus 5.5', 'high'),
             'oai': ('GPT-6.1-Sol', 'high'),
             'gemini': ('Gemini 4 Hydrogen', 'high')}},
 {'role': 'Designer',
  'description': ('UI, interaction and accessibility', 'UI、互動與無障礙'),
  'models': {'anth': ('Opus 5.5', 'high'),
             'oai': ('GPT-6.1-Terra', 'high'),
             'gemini': ('Gemini 4 Hydrogen', 'high')}},
 {'role': 'Executor',
  'description': ('implements an approved plan step by step', '照已核准的 plan 逐步實作'),
  'models': {'anth': ('Sonnet 5.5', 'medium'),
             'oai': ('GPT-6.1-Sol', 'medium'),
             'gemini': ('Gemini 4 Hydrogen', 'high')}},
 {'role': 'Reviewer',
  'description': ('independent review and testing', '獨立審查與測試'),
  'models': {'anth': ('Opus 5.5', 'high'),
             'oai': ('GPT-6.1-Sol', 'high'),
             'gemini': ('Gemini 4 Hydrogen', 'high')}},
 {'role': 'DevOps',
  'description': ('environments and operations', '環境與維運'),
  'models': {'anth': ('Opus 5.5', 'high'),
             'oai': ('GPT-6.1-Sol', 'high'),
             'gemini': ('Gemini 4 Hydrogen', 'high')}},
 {'role': 'Security',
  'description': ('scans code, dependencies and configuration', '程式碼、相依套件與設定的安全掃描'),
  'models': {'anth': ('Opus 5.5', 'max'),
             'oai': ('GPT-6 Astra', 'max'),
             'gemini': ('Gemini 4 Carbon', 'high')}})

# Personal selection policy; the source's benchmark data and account support stay intact.
EXCLUDED_GEMINI_PICKS = {"gemini-4-argon"}
ROLE_POLICY_NOTE = (
    "Local selection draft based on Notion v2.2: Argon is excluded because of cost. "
    "Planner, Designer, Executor, Reviewer and DevOps use Hydrogen / high; Security "
    "keeps Carbon / high with safety and correctness first. Not synced to Notion.",
    "以 Notion v2.2 為基準的本機選型草案：因成本排除 Argon。Planner、Designer、Executor、"
    "Reviewer、DevOps 使用 Hydrogen / high；Security 保留 Carbon / high，安全性與正確性優先。尚未同步 Notion。",
)
ROLE_SOURCE_NOTE = (
    "Source: Notion v2.2 plus the user's local selection changes. The table is a local "
    "draft, not the current Notion JSON or a live sync. No active agent settings were changed.",
    "來源：Notion v2.2 加上本次使用者的本機選型調整。此表是本機草案，不代表目前 Notion JSON 或即時同步結果；未變更正在使用的 agent 設定。",
)
