# 灵剪固化能力库（capabilities）

> 全比例、全风格通用的**横切能力**——分镜 / 配音 / 画面 / 声音各关都调用它们。
> 这些是灵剪区别于「一句话丢给大模型直出」的差异化内核:把 AI 黑箱拆成可读、可审、可复用的关卡能力。换比例、换风格 = 复用这些能力换皮重排,不重做。

| 能力 | 是什么 | 关键文件 | 治什么病 |
|---|---|---|---|
| **director-board**（在仓库根 `director-board/`） | 分帧动效**导演板**:数据驱动的关卡确认台旗舰,逐镜卡 + 能量曲线 + 用户确认 | `board.schema.json`·`render.js`·`standalone.html` | 把 AI 黑箱打开成可读可审可交互,逐镜确认再往下 |
| **transition-library** | 转场库:四象限谱系 + 内容匹配器,按能量差/语义荐转场、强转场稀缺 | `transitions.json`·`match.js`·`TRANSITION_LIBRARY.md`·`test/match.test.js` | 廉价花活满屏、强转场滥用;稀缺守卫默认配额 ≤3 |
| **cadence** | 精确卡点:`silencedetect` 测配音停顿 → 语音段起点,画面砸词卡在起点 | `cadence.py` | 画面比配音快、砸词早于词;比按字数估准 |
| **sfx-strategy** | 音效策略:动作→音效映射 + 五铁律,每个音效必须对应画面动作 | `SFX_STRATEGY.md`·`sfx_mix.py`·`example.hits.json` | 莫名音效满天飞;没对应画面动作的一律删 |
| **layout-safety** | 版式安全:粗黑大字-标签间距等硬规则 | `TYPOGRAPHY_RULES.md` | inspect 查不出的字形级溢出(大字压标签、越界) |

## 怎么用

- **导演板**:分镜关把每镜的素材/构图/动效/转场/字幕/声音/验收点摊在 `localhost` 本地页面给用户逐镜确认(见根 `director-board/README.md`)。控制台永远是本机服务,不走任何云端地址。
- **转场匹配**:`node capabilities/transition-library/test/match.test.js` 可复现匹配器 + 稀缺守卫。分镜关据此按内容荐转场。
- **卡点**:`python3 capabilities/cadence/cadence.py <配音.mp3>` 输出语音段起点;画面事件 `start` 不早于对应词起点。灵剪主线的 `voice_plan.voice_cadence` 用同一 `silencedetect` 逻辑(`noise=-30dB, d=0.05`)自动测。
- **音效 / 版式**:按 `SFX_STRATEGY.md` / `TYPOGRAPHY_RULES.md` 的硬规则约束生成与校验。

> 诚实边界:转场库 42 项的跨镜成片实现为已规格化 `spec`,随主线画面执行逐步集成;默认以硬切 concat 兜底。匹配逻辑已用 node 测试验证自洽。
