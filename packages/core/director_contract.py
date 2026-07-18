from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_STYLE = "clean_product"
DEFAULT_PROFILE = "douyin_product"
OPEN_SOURCE_PROFILE = "open_source_project_intro"
PRODUCT_INTRO_PROFILE = "product_intro"
TUTORIAL_PROFILE = "tutorial_guide"
REVIEW_PROFILE = "review_comparison"
ECOMMERCE_PROFILE = "ecommerce_sales"
KNOWLEDGE_PROFILE = "knowledge_explainer"
MAX_PRIMARY_MOTIONS = 2
MIN_BLUEPRINT_VARIETY_FOR_MULTI_SCENE = 3
MIN_MOTION_VOCAB_FOR_MULTI_SCENE = 3
MIN_OPEN_SOURCE_EVIDENCE_RECIPES = 3
MIN_KEYFRAMES_PER_DIRECTOR_SCENE = 3
MAX_OPENING_KEYFRAME_RATIO = 0.20
MIN_MIDDLE_KEYFRAME_RATIO = 0.25
MAX_MIDDLE_KEYFRAME_RATIO = 0.70
MIN_KEYFRAME_DURATION_COVERAGE_RATIO = 0.75
PUBLISH_GRADE_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
STATIC_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
DIRECTOR_HOST_ADAPTERS = {
    "lingjian_hyperframes_director",
    "lingjian_remotion_director",
    "lingjian_seedance_generator",
}
STOCK_IMAGE_SOURCE_PRIORITY = [
    "用户自有图片/截图",
    "国内 CC0/公共领域/免费源:cc0.cn、泼辣有图、hippopx、别样网",
    "海外公开源:Unsplash、Pexels、StockSnap",
    "AI 生图兜底",
]

STYLE_LOCKS: dict[str, dict[str, Any]] = {
    "clean_product": {
        "label_zh": "清爽产品说明",
        "palette": ["#0F172A", "#14B8A6", "#F8FAFC"],
        "lighting": "柔和侧光,高对比但不过曝",
        "stroke": "1.5px 半透明描边",
        "radius": "8px",
        "font_tone": "现代无衬线,中文标题短促有力",
        "motion_language": "清晰推进、轻量缩放、信息层次逐步展开",
        "negative_space": "画面下方留字幕安全区,主体不压底部",
        "decoration_rules": [
            "禁止随机闪光",
            "禁止火箭/彩带等无关装饰",
            "禁止一行一个图标",
            "所有装饰必须能通过 removal_test",
        ],
    },
    "bold_news": {
        "label_zh": "强钩子资讯",
        "palette": ["#111827", "#F97316", "#FFFFFF"],
        "lighting": "硬朗顶光,重点元素高亮",
        "stroke": "2px 深色描边",
        "radius": "6px",
        "font_tone": "新闻感粗体,关键词优先",
        "motion_language": "快速切入、停顿强调、证据放大",
        "negative_space": "主体居中偏上,底部字幕区保持干净",
        "decoration_rules": ["禁止无关爆炸贴纸", "禁止闪屏堆叠", "装饰不超过两类"],
    },
    "warm_lifestyle": {
        "label_zh": "生活方式温和",
        "palette": ["#1F2937", "#F59E0B", "#FFF7ED"],
        "lighting": "暖色自然光",
        "stroke": "1px 柔和描边",
        "radius": "8px",
        "font_tone": "亲和、少字、留白",
        "motion_language": "缓慢推近、轻轻跟随、少跳切",
        "negative_space": "保留呼吸感,底部不放主体脸部/产品关键点",
        "decoration_rules": ["禁止密集贴纸", "禁止大面积渐变光斑", "装饰必须服务叙事"],
    },
    "tech_minimal": {
        "label_zh": "科技极简",
        "palette": ["#020617", "#38BDF8", "#E2E8F0"],
        "lighting": "冷色边缘光",
        "stroke": "1px 蓝色细线",
        "radius": "4px",
        "font_tone": "克制、数据优先",
        "motion_language": "线框展开、数据聚焦、镜头稳定",
        "negative_space": "大面积深色留白,字幕区固定不占信息面板",
        "decoration_rules": ["禁止赛博乱码堆叠", "禁止无意义扫描线", "只保留解释结构的线框"],
    },
    # ── 4 套已实现风格库(各套真实模板 + STYLE_BASE);
    #    完整方法论见 styles/<key>.md,换风格=复用横切能力换皮,不重做 ──
    "vox_cut": {
        "label_zh": "VOX 编辑剪影",
        "style_archive": "styles/vox_cut.md",
        "palette": ["#1B1B19", "#F7F1E4", "#E0402A"],
        "lighting": "平面新闻杂志感,无戏剧打光",
        "stroke": "朱红错位描边",
        "radius": "0px",
        "font_tone": "GlowSansSC 发光标题 + 思源黑正文,活泼工具感",
        "motion_language": "分帧逐层入场 · 12fps 抖帧,元素依次入场,不匀速推拉",
        "negative_space": "编辑栅格留白放大字标题,底部字幕安全区",
        "decoration_rules": ["黑白半调网点底", "朱红只点重点不铺满", "抠图剪影,禁写实照片直接贴"],
    },
    "dark_keynote": {
        "label_zh": "暗场发布(史诗)",
        "style_archive": "styles/dark_keynote.md",
        "palette": ["#0E0E10", "#C9A15A", "#EDE8DF"],
        "lighting": "近黑舞台,主体暖金精工描边微微发光",
        "stroke": "暖金精工细描边",
        "radius": "2px",
        "font_tone": "GlowSansSC 标题 + 思源黑字幕(统一思源黑),米白大字",
        "motion_language": "推拉揭示,景别递进,缓慢电影级运镜",
        "negative_space": "大面积近黑留白,米白大字居中,底部字幕区干净",
        "decoration_rules": [
            "禁霓虹/粒子撒特效",
            "暖金只用于精工描边与重点",
            "真实史料为主 AI 补意象",
        ],
    },
    "cinematic": {
        "label_zh": "写实电影感(人文)",
        "style_archive": "styles/cinematic.md",
        "palette": ["#0e0b08", "#c98b3a", "#efd9ab"],
        "lighting": "电影级调色 + 景深 + 暗角,暗场矿物色金",
        "stroke": "无描边(写实)",
        "radius": "0px",
        "font_tone": "HanSans 思源系,克制有叙事重量",
        "motion_language": "Seedance 缓慢运镜,一条旁白到底、音画卡帧",
        "negative_space": "电影构图留白,字幕逐句卡配音,底部安全区",
        "decoration_rules": ["禁网红调色", "写实景深不过度虚化", "矿物金只作点睛"],
    },
    "neue_sachlichkeit": {
        "label_zh": "新客观主义(实物档案)",
        "style_archive": "styles/neue_sachlichkeit.md",
        "palette": ["#4A4A47", "#BFA06A", "#F2EFEA"],
        "lighting": "平光均匀无戏剧打光,高调 high-key(85% 浅色)",
        "stroke": "无描边",
        "radius": "0px",
        "font_tone": "无彩色克制,画面内无字,文字卡代旁白",
        "motion_language": "静物陈列 / 微距极简;摆放→曝晒→显影 物理母题",
        "negative_space": "浅灰白工作台背景,大面积浅色留白",
        "decoration_rules": [
            "剔除主观创作/摆拍/电影感调色",
            "无彩色为主,唯一暖色牛皮纸暗黄褐",
            "画面内绝无文字",
            "要手正面清楚拍自然五指,禁凭空手",
        ],
    },
}

PROFILE_PRESETS: dict[str, dict[str, Any]] = {
    OPEN_SOURCE_PROFILE: {
        "label_zh": "开源项目介绍",
        "platform": "douyin",
        "ratio": "9:16",
        "duration_sec": 45,
        "scene_count": 5,
        "first_3_sec": "先点名 AI 小白做视频的真实困难,再亮出一句话触发工作流。",
        "cut_density": "每 3-4 秒推进一个真实证据或流程状态",
        "subtitle_limit": 15,
        "bgm_strategy": "科技感轻节奏 BGM,人声优先,BGM 比人声低 16dB",
        "publish_window_hint": "AI/开源受众晚间高活跃时段优先,仅作建议",
        "narrative_arc": ["hook", "pain", "solution", "proof", "cta"],
        "required_evidence": [
            "GitHub repo",
            "README 顶部安装入口",
            "Codex app 对话触发",
            "终端/QA 证据",
            "导出包或 Star CTA",
        ],
        "visual_types": [
            "真实界面录屏",
            "证据墙",
            "流程动效",
            "终端/QA 仪表盘",
            "Star 行动收束",
        ],
        "transition_strategy": "从问题压迫到流程收束,再到证据放大和 CTA 锁定。",
        "sfx_strategy": "键盘、点击、勾选和轻 whoosh,只服务操作反馈。",
        "cta_strategy": "引导关注开源项目并 star,不要夸大传播效果。",
        "forbidden": [
            "全片抽象模板换字",
            "没有 GitHub/README/Codex/终端/QA 任一真实证据画面",
            "用静态图片或模板循环冒充产品演示",
        ],
        "qa_checkpoints": [
            "至少一个真实项目/流程/证据镜头",
            "CTA 明确指向 star 或关注开源项目",
            "画面不能只靠抽象图形解释产品",
        ],
    },
    PRODUCT_INTRO_PROFILE: {
        "label_zh": "产品介绍",
        "platform": "douyin",
        "ratio": "9:16",
        "duration_sec": 45,
        "scene_count": 5,
        "first_3_sec": "先说清产品解决的具体问题,再给出一个可见产品锚点。",
        "cut_density": "每 3-5 秒推进一个功能、流程或结果证据",
        "subtitle_limit": 15,
        "bgm_strategy": "克制科技感 BGM,人声优先,BGM 比人声低 16dB",
        "publish_window_hint": "新品/工具类受众午后或晚间浏览时段优先,仅作建议",
        "narrative_arc": ["hook", "problem", "feature", "workflow", "proof", "cta"],
        "required_evidence": ["产品界面", "核心工作流", "真实结果", "行动入口"],
        "visual_types": ["产品界面录屏", "功能聚焦", "流程动效", "结果证明", "CTA"],
        "transition_strategy": "从问题到功能,再到结果证明和行动收束。",
        "sfx_strategy": "点击、状态切换、结果落定音,不抢人声。",
        "cta_strategy": "引导试用、关注、Star 或进入项目页,不夸大效果。",
        "forbidden": ["只用抽象图形介绍产品", "没有真实界面或结果证据", "满屏功能清单"],
        "qa_checkpoints": ["至少一个真实产品/流程画面", "功能和口播一一对应"],
    },
    "douyin_product": {
        "label_zh": "抖音-带货",
        "platform": "douyin",
        "ratio": "9:16",
        "duration_sec": 45,
        "scene_count": 5,
        "first_3_sec": "先抛痛点或反差收益,3秒内给出视觉锚点",
        "cut_density": "每 3-5 秒一个信息变化",
        "subtitle_limit": 16,
        "bgm_strategy": "轻节奏 BGM,人声优先,BGM 比人声低 16dB",
        "publish_window_hint": "午休/晚间高活跃时段优先,仅作建议",
        "narrative_arc": ["hook", "pain", "solution", "proof", "cta"],
        "required_evidence": ["产品 UI", "真实使用场景", "收益证据"],
        "visual_types": ["产品演示", "前后对比", "卖点聚焦", "结果证明"],
        "transition_strategy": "痛点压近、产品登场、证据放大、CTA 收束。",
        "sfx_strategy": "点击、切换和卖点落定音,避免抢人声。",
        "cta_strategy": "给出明确行动,但不承诺转化。",
        "forbidden": ["没有产品真实素材时硬做发布级", "满屏卖点文字"],
        "qa_checkpoints": ["至少一个真实产品/流程画面", "CTA 不遮挡字幕"],
    },
    ECOMMERCE_PROFILE: {
        "label_zh": "带货转化",
        "platform": "douyin",
        "ratio": "9:16",
        "duration_sec": 45,
        "scene_count": 5,
        "first_3_sec": "先给使用场景或反差痛点,再出现商品真实画面。",
        "cut_density": "每 2-4 秒切一个场景、卖点或证据",
        "subtitle_limit": 14,
        "bgm_strategy": "轻快但不压人声,BGM 比人声低 16dB",
        "publish_window_hint": "晚间消费决策时段优先,仅作建议",
        "narrative_arc": ["hook", "pain", "use_case", "benefit", "proof", "cta"],
        "required_evidence": ["商品实拍视频", "使用场景", "卖点证据", "购买/咨询入口"],
        "visual_types": ["商品特写", "使用前后", "场景演示", "证据放大", "行动按钮"],
        "transition_strategy": "痛点快切、商品登场、证据放大、CTA 锁定。",
        "sfx_strategy": "卖点落定音、点击音、轻 whoosh,避免吵闹。",
        "cta_strategy": "给明确购买/咨询行动,不承诺不实转化。",
        "forbidden": ["无商品真实素材", "虚假功效承诺", "只用贴纸和大字卖点"],
        "qa_checkpoints": ["商品主体清晰", "卖点有画面证据", "CTA 不遮挡字幕"],
    },
    TUTORIAL_PROFILE: {
        "label_zh": "教程演示",
        "platform": "douyin",
        "ratio": "9:16",
        "duration_sec": 60,
        "scene_count": 6,
        "first_3_sec": "先展示最终效果或最常见卡点,让用户知道学完能做到什么。",
        "cut_density": "每 4-6 秒推进一个步骤或操作状态",
        "subtitle_limit": 16,
        "bgm_strategy": "极轻 BGM 或无 BGM,步骤说明和操作音优先",
        "publish_window_hint": "工作日晚间或周末学习时段优先,仅作建议",
        "narrative_arc": ["hook", "result_preview", "step_1", "step_2", "step_3", "recap_cta"],
        "required_evidence": ["最终效果", "逐步操作录屏", "关键按钮/命令", "常见错误提醒"],
        "visual_types": ["操作录屏", "鼠标/光标 callout", "步骤编号", "结果对比", "总结卡"],
        "transition_strategy": "步骤之间清晰分段,用编号/进度条承接,不做花哨跳切。",
        "sfx_strategy": "点击、勾选、错误提示音,只服务操作反馈。",
        "cta_strategy": "引导收藏/关注下一节,不承诺一次学会所有复杂场景。",
        "forbidden": ["只讲概念不展示操作", "步骤跳跃", "字幕遮挡按钮/命令"],
        "qa_checkpoints": ["每个关键步骤有可见操作证据", "字幕不遮挡按钮或命令"],
    },
    REVIEW_PROFILE: {
        "label_zh": "测评对比",
        "platform": "douyin",
        "ratio": "9:16",
        "duration_sec": 60,
        "scene_count": 6,
        "first_3_sec": "先给测评结论或最大反差,再说明评测维度。",
        "cut_density": "每 4-5 秒推进一个维度、对比或证据",
        "subtitle_limit": 15,
        "bgm_strategy": "中性克制 BGM,人声和证据读数优先",
        "publish_window_hint": "决策类内容晚间收藏/对比时段优先,仅作建议",
        "narrative_arc": ["hook", "criteria", "test_1", "test_2", "tradeoff", "verdict"],
        "required_evidence": ["评测对象实拍", "对比维度", "测试过程", "结论依据"],
        "visual_types": ["对比表", "实测镜头", "数据/打分", "优缺点分屏", "结论卡"],
        "transition_strategy": "维度卡片切换、证据扫描、结论锁定。",
        "sfx_strategy": "维度切换提示音和结论落定音,避免情绪化夸张。",
        "cta_strategy": "引导评论补充场景或关注后续测评,不冒充权威认证。",
        "forbidden": ["无测试证据直接下结论", "只讲主观感受", "结论和证据不匹配"],
        "qa_checkpoints": ["每个结论有画面或数据依据", "优缺点同屏可比较"],
    },
    KNOWLEDGE_PROFILE: {
        "label_zh": "知识科普",
        "platform": "douyin",
        "ratio": "9:16",
        "duration_sec": 60,
        "scene_count": 5,
        "first_3_sec": "先给一个具体误区、问题或结论,再展开解释。",
        "cut_density": "每 5-7 秒推进一个概念层级或例子",
        "subtitle_limit": 17,
        "bgm_strategy": "低存在感 BGM 或无 BGM,概念解释优先",
        "publish_window_hint": "晚间知识消费时段优先,仅作建议",
        "narrative_arc": ["hook", "misconception", "explain", "example", "recap_cta"],
        "required_evidence": ["概念图解", "例子或场景", "结论复盘"],
        "visual_types": ["动态图解", "类比画面", "因果链", "例子拆解", "结论卡"],
        "transition_strategy": "概念层级递进,用图解 morph 或 clean wipe 承接。",
        "sfx_strategy": "轻提示音、分层展开音,可无音效。",
        "cta_strategy": "引导关注后续知识,不承诺立刻改变结果。",
        "forbidden": ["概念堆叠无例子", "大段定义文字", "伪科学或无来源结论"],
        "qa_checkpoints": ["概念有例子支撑", "结论不夸大", "字幕可读"],
    },
    "xiaohongshu_life": {
        "label_zh": "小红书-生活",
        "platform": "xiaohongshu",
        "ratio": "3:4",
        "duration_sec": 45,
        "scene_count": 5,
        "first_3_sec": "先给具体场景和真实困扰",
        "cut_density": "节奏略慢,每 4-6 秒一处变化",
        "subtitle_limit": 14,
        "bgm_strategy": "低存在感生活感 BGM,避免压人声",
        "publish_window_hint": "通勤后/晚间收藏决策时段优先,仅作建议",
        "narrative_arc": ["hook", "pain", "solution", "proof", "cta"],
        "required_evidence": ["真实生活场景", "前后对比", "步骤截图"],
        "visual_types": ["生活场景", "清单卡", "细节特写", "收藏 CTA"],
        "transition_strategy": "轻推近、柔和 wipe、场景自然切换。",
        "sfx_strategy": "轻提示音和纸张/标记音,保持温和。",
        "cta_strategy": "收藏/关注,避免强销售口吻。",
        "forbidden": ["密集贴纸", "大段口播文字覆盖画面"],
        "qa_checkpoints": ["场景可信", "字幕不遮挡主体"],
    },
    "shipinhao_knowledge": {
        "label_zh": "视频号-知识",
        "platform": "shipinhao",
        "ratio": "9:16",
        "duration_sec": 60,
        "scene_count": 5,
        "first_3_sec": "先给结论或问题,随后给结构化解释",
        "cut_density": "每 5-7 秒推进一个论点",
        "subtitle_limit": 18,
        "bgm_strategy": "极轻 BGM 或无 BGM,清晰口播优先",
        "publish_window_hint": "工作日晚间/周末上午优先,仅作建议",
        "narrative_arc": ["hook", "pain", "solution", "proof", "cta"],
        "required_evidence": ["概念图解", "案例画面", "结论复盘"],
        "visual_types": ["动态图解", "步骤拆解", "案例对照", "结论卡"],
        "transition_strategy": "清晰段落切换,少花哨动效。",
        "sfx_strategy": "轻勾选/分段提示音,可无 BGM。",
        "cta_strategy": "关注获取后续知识,不承诺结果。",
        "forbidden": ["概念堆叠无例子", "字幕过密"],
        "qa_checkpoints": ["论点递进清楚", "字幕可读"],
    },
}

HOOK_LIBRARY: dict[str, list[str]] = {
    OPEN_SOURCE_PROFILE: ["痛点直击", "过程窥视", "反差结果", "失败现场", "Star CTA"],
    PRODUCT_INTRO_PROFILE: ["痛点直击", "产品锚点", "工作流预告", "结果先看"],
    "douyin_product": ["反常识收益", "自曝痛点", "前后对比", "数字承诺"],
    ECOMMERCE_PROFILE: ["使用场景", "反差痛点", "前后对比", "卖点证据"],
    TUTORIAL_PROFILE: ["最终效果先看", "卡点直击", "三步完成", "错误提醒"],
    REVIEW_PROFILE: ["结论先行", "最大反差", "维度对比", "值不值得"],
    KNOWLEDGE_PROFILE: ["误区纠正", "问题先行", "结论先行", "类比解释"],
    "xiaohongshu_life": ["真实场景", "避坑提醒", "体验前后", "省心清单"],
    "shipinhao_knowledge": ["结论先行", "误区纠正", "三步解释", "案例引入"],
}

DIRECTOR_KNOWLEDGE_BASE: dict[str, dict[str, Any]] = {
    "hook_patterns": {
        "pain_direct": "先说具体痛点,首屏文字不超过 12 个汉字。",
        "process_peek": "先展示可见流程,让观众看到会发生什么。",
        "proof_first": "先给可复核证据,再解释机制。",
    },
    "motion_rules": {
        "discrete-text-sequence": "文字按语义节奏分批出现,禁止一次性倒完。",
        "cursor-click-ripple": "点击反馈只服务操作证明,不做装饰堆砌。",
        "coordinate-target-zoom": "镜头推近到证据点,停留足够可读。",
        "stat-bars-and-fills": "数据变化必须有起点、增长和落点。",
    },
    "transition_rules": {
        "ticker-crash": "用于钩子到痛点的强切换。",
        "clean-wipe": "用于流程/界面演示的干净切换。",
        "scan-focus": "用于证据墙或 QA 结果聚焦。",
        "cta-morph": "用于证明到行动按钮的收束。",
    },
    "caption_rules": {
        "bottom_safe_area_cjk": "中文字幕固定底部安全区,每行短句,不遮主体/CTA。",
    },
    "sound_rules": {
        "voice_first_mix": "人声优先,BGM 比人声低 16dB,音效只提示动作。",
        "proof_tick": "证据/QA 勾选用短提示音,避免连续吵闹。",
    },
    "asset_strategies": {
        "open_source_evidence": "优先 GitHub、README、Codex 操作、终端、QA、导出包等真实证据画面。",
        "user_video_primary": "用户视频素材直接作为主画面,引擎只做字幕/callout/overlay。",
        "dynamic_generation": "HyperFrames/Remotion 输出 mp4/mov/m4v 动态视频资产。",
    },
    "forbidden_items": {
        "static_as_video": "不要把一张图放几秒、Ken Burns 或轻微缩放说成发布级视频。",
        "template_loop": "不要把内置模板闪动或同模板换字说成真实动态画面。",
        "llm_self_eval": "质量门不能依赖 LLM 自评,必须基于真跑证据。",
    },
}

OPEN_SOURCE_PROFILE_KEYWORDS = {
    "开源",
    "github",
    "git hub",
    "star",
    "readme",
    "仓库",
    "项目",
    "灵剪",
    "codex",
}

PROFILE_KEYWORDS: dict[str, set[str]] = {
    TUTORIAL_PROFILE: {
        "教程",
        "教学",
        "怎么用",
        "如何使用",
        "使用方法",
        "步骤",
        "操作指南",
        "上手",
        "演示",
        "guide",
        "tutorial",
        "how to",
    },
    REVIEW_PROFILE: {
        "测评",
        "评测",
        "体验",
        "对比",
        "优缺点",
        "值不值得",
        "开箱",
        "review",
        "comparison",
    },
    ECOMMERCE_PROFILE: {
        "带货",
        "下单",
        "购买",
        "优惠",
        "种草",
        "卖点",
        "商品",
        "转化",
        "ecommerce",
        "sales",
    },
    KNOWLEDGE_PROFILE: {
        "知识科普",
        "科普",
        "解释",
        "原理",
        "概念",
        "观点",
        "为什么",
        "explain",
        "knowledge",
    },
    PRODUCT_INTRO_PROFILE: {
        "产品介绍",
        "功能介绍",
        "产品发布",
        "介绍产品",
        "能做什么",
        "解决什么问题",
        "product intro",
        "launch",
    },
}

PAID_GENERATORS = {
    "volcengine_tts": "火山豆包云 TTS 按账号套餐/用量计费,调用前需要用户确认已开通并接受费用。",
    "fal": "Fal 属第三方付费生成服务,调用前需要用户确认账号和费用。",
    "picsart": "Picsart 属第三方付费/账号能力,调用前需要用户确认账号和费用。",
}

DETERMINISTIC_RULES = [
    "禁止 Date.now/未播种 random",
    "禁止 setTimeout 作为渲染时序",
    "禁止渲染期网络请求",
    "禁止 repeat:-1 无限循环",
    "使用 paused master timeline 或帧驱动时间线",
    "固定 width/height/fps",
    "字幕最后叠加且在底部安全区",
    "剪切点使用 30ms 音频淡入淡出,不在词中切",
    "BGM 比人声低 16dB",
]

DIRECTOR_BLUEPRINTS: dict[str, dict[str, Any]] = {
    "hook_codex_prompt": {
        "role": "hook",
        "visual_archetype": "codex_prompt_capture",
        "asset_recipe_id": "codex_prompt_or_reconstructed_ui",
        "material_key": "prompt_terminal_surface",
        "transition_family": "ticker-crash",
        "motion_rule_ids": [
            "discrete-text-sequence",
            "context-sensitive-cursor",
            "cursor-click-ripple",
        ],
        "scene_goal": "3 秒内建立钩子,让 AI 小白知道这不是泛泛工具介绍,而是能从一句话开始做视频。",
        "visual_content": "全屏开场,一句用户指令变成短视频生产流程的可视化入口。",
        "composition": (
            "全屏大标题居上,中部放输入框/命令气泡,"
            "右侧出现逐步点亮的流程节点,底部留字幕安全区。"
        ),
        "focus": "第一眼看输入框里的短句,第二眼看流程节点亮起。",
        "motion_design": "输入框轻微推近,文字逐字出现,流程节点从左到右点亮,背景网格有缓慢视差。",
        "transition_in": "从黑场快速淡入到输入框聚焦。",
        "transition_out": "流程节点向下一镜滑出,形成问题场景承接。",
        "sfx": "轻微键盘输入音 + 第一个节点点亮提示音。",
    },
    "hook_ticker_takeover": {
        "role": "hook",
        "visual_archetype": "kinetic_ticker_takeover",
        "asset_recipe_id": "motion_graphic_hook",
        "material_key": "kinetic_type_field",
        "transition_family": "zoom-through",
        "motion_rule_ids": [
            "kinetic-beat-slam",
            "vertical-spring-ticker",
            "reactive-displacement",
        ],
        "scene_goal": "用快速变量替换制造注意力,把“普通剪辑工具”替换成“可审计发布工作流”。",
        "visual_content": "关键词快速轮换,最终被灵剪工作流入口撞入并接管画面。",
        "composition": "中部大字 + 右侧流程锁定标记,底部留字幕安全区。",
        "focus": "先看轮换关键词,再看最终锁定的灵剪定位。",
        "motion_design": "关键词竖向 ticker,最终词撞开旧词,流程节点从右侧锁定。",
        "transition_in": "硬切进入快速 ticker。",
        "transition_out": "撞入元素推开旧画面,进入痛点镜头。",
        "sfx": "两次轻提示音 + 低频撞击 whoosh。",
    },
    "hook_product_flash": {
        "role": "hook",
        "visual_archetype": "product_flash_montage",
        "asset_recipe_id": "repo_and_cli_flash",
        "material_key": "fast_evidence_tiles",
        "transition_family": "grid-dissolve",
        "motion_rule_ids": [
            "center-outward-expansion",
            "motion-blur-streak",
            "scale-swap-transition",
        ],
        "scene_goal": "在前 3 秒给出真实产品证据,让观众知道这是开源项目而不是概念片。",
        "visual_content": "GitHub、终端、分镜、QA 四个证据瞬间闪现并合成产品名。",
        "composition": "四宫格证据卡快速组装,中心露出项目名。",
        "focus": "先看真实证据碎片,再看中心项目名。",
        "motion_design": "四张卡片从边缘带 motion blur 飞入,中心 scale-swap 成项目名。",
        "transition_in": "快速网格溶解进入。",
        "transition_out": "网格向外散开,露出痛点场景。",
        "sfx": "短促卡片划入音,最后一声锁定提示。",
    },
    "pain_overwhelm_board": {
        "role": "pain",
        "visual_archetype": "overwhelm_task_board",
        "asset_recipe_id": "reconstructed_user_pain_ui",
        "material_key": "chaos_cards",
        "transition_family": "glitch-pressure",
        "motion_rule_ids": [
            "depth-scatter-assemble",
            "center-outward-expansion",
            "motion-blur-streak",
        ],
        "scene_goal": "放大普通用户做短视频时的混乱和返工感。",
        "visual_content": "脚本、配音、画面三个任务卡片堆叠,旁边出现返工箭头和时间消耗提示。",
        "composition": "左右分栏:左侧是凌乱任务堆,右侧是时间轴被拉长;底部字幕区保持干净。",
        "focus": "先看混乱卡片,再看右侧时间被拉长的视觉反馈。",
        "motion_design": "卡片错位滑入、返工箭头循环一次后停止,时间轴被拖长并轻微震动。",
        "transition_in": "从上一镜流程节点甩入凌乱卡片。",
        "transition_out": "凌乱卡片被收束成三步结构,接方案镜。",
        "sfx": "低频 whoosh + 轻微卡片碰撞音。",
    },
    "pain_dataviz_cost": {
        "role": "pain",
        "visual_archetype": "cost_dataviz",
        "asset_recipe_id": "workflow_cost_data_viz",
        "material_key": "dark_data_panel",
        "transition_family": "focus-pull",
        "motion_rule_ids": [
            "counting-dynamic-scale",
            "stat-bars-and-fills",
            "coordinate-target-zoom",
        ],
        "scene_goal": "用数据化方式呈现返工成本,让小白用户理解为什么需要流程门禁。",
        "visual_content": "返工次数、素材缺口、发布失败风险三个指标快速上升。",
        "composition": "一大两小数据面板,大数字居中偏上,底部字幕区保持干净。",
        "focus": "先看上升数字,再看三项风险标签。",
        "motion_design": "数字放大计数,柱状条同步增长,镜头推向最高风险项。",
        "transition_in": "从混乱卡片 blur 到数据面板。",
        "transition_out": "最高风险项被划掉,进入解决方案。",
        "sfx": "轻微计数 tick + 风险项落定声。",
    },
    "pain_spatial_stations": {
        "role": "pain",
        "visual_archetype": "spatial_pain_stations",
        "asset_recipe_id": "workflow_station_map",
        "material_key": "oversized_canvas",
        "transition_family": "push-squeeze",
        "motion_rule_ids": [
            "viewport-change",
            "asr-keyword-glow",
            "depth-of-field-blur",
        ],
        "scene_goal": "把脚本、配音、画面、导出这些节点做成一张被卡住的路线图。",
        "visual_content": "巨大流程地图上多个站点被红色提示卡住,镜头依次扫过。",
        "composition": "超大画布 + 虚拟镜头横移,每个站点只显示短标签。",
        "focus": "跟随镜头看每个卡点,最后停在“发布失败”。",
        "motion_design": "viewport 横移到每个站点,关键词 glow,末尾景深聚焦失败节点。",
        "transition_in": "前一镜元素被挤压成路线图。",
        "transition_out": "失败节点翻转成解决方案入口。",
        "sfx": "连续轻提示音,最后一声低频停顿。",
    },
    "solution_three_gate_flow": {
        "role": "solution",
        "visual_archetype": "three_gate_workflow",
        "asset_recipe_id": "lingjian_artifact_flow",
        "material_key": "workflow_steps",
        "transition_family": "card-morph",
        "motion_rule_ids": [
            "center-outward-expansion",
            "svg-path-draw",
            "viewport-change",
        ],
        "scene_goal": "讲清灵剪的核心方法:脚本、配音、画面三步拆开审。",
        "visual_content": "三段式流程板:脚本审阅、配音审阅、画面审阅依次展开,每步有确认状态。",
        "composition": "中轴三段阶梯结构,每段有短标题和状态灯,主体不压底部字幕。",
        "focus": "沿中轴从上到下看三步,理解每步先审再往下走。",
        "motion_design": "三段阶梯依次展开,状态灯逐个点亮,镜头轻微下移跟随流程。",
        "transition_in": "凌乱卡片吸附到中轴,变成三步流程。",
        "transition_out": "三步流程收束成审批印章/检查线,接证明镜。",
        "sfx": "三次短促确认提示音,音量低于人声。",
    },
    "solution_cursor_demo": {
        "role": "solution",
        "visual_archetype": "cursor_ui_demo",
        "asset_recipe_id": "codex_operation_capture",
        "material_key": "product_window",
        "transition_family": "clean-wipe",
        "motion_rule_ids": [
            "3d-page-scroll",
            "cursor-click-ripple",
            "camera-cursor-tracking",
        ],
        "scene_goal": "让用户看到 Codex 里一句话触发灵剪主线,降低安装和使用心智成本。",
        "visual_content": "Codex 对话框、能力门诊、三审入口依次被 cursor 点亮。",
        "composition": "倾斜产品窗口占主体,右侧短标签解释当前步骤,底部留字幕。",
        "focus": "跟随 cursor 看每一次点击和状态变化。",
        "motion_design": "窗口 3D 倾斜滚动,cursor 点击后 ripple,镜头锁定到当前状态。",
        "transition_in": "流程卡 morph 成 Codex 窗口。",
        "transition_out": "窗口缩成一个通过状态,进入证据镜。",
        "sfx": "轻点击音 + 状态通过提示。",
    },
    "solution_asset_pipeline": {
        "role": "solution",
        "visual_archetype": "asset_pipeline",
        "asset_recipe_id": "visual_asset_generation_queue",
        "material_key": "asset_grid",
        "transition_family": "grid-align",
        "motion_rule_ids": [
            "center-outward-expansion",
            "svg-icon-enrichment",
            "scale-swap-transition",
        ],
        "scene_goal": "解释画面资产不是一张图凑出来,而是每镜动态视频资产进入管线。",
        "visual_content": "每镜 mp4 资产格子从待生成到已通过,再流入渲染队列。",
        "composition": "上半区资产网格,中部队列箭头,底部字幕安全区。",
        "focus": "先看每镜资产状态,再看渲染队列合流。",
        "motion_design": "资产卡逐个展开,状态角标点亮,最后 scale-swap 到合成轨道。",
        "transition_in": "Codex 窗口切成资产网格。",
        "transition_out": "资产轨道向右推进到 QA 证据墙。",
        "sfx": "状态切换提示音,每次很轻。",
    },
    "proof_qa_evidence_wall": {
        "role": "proof",
        "visual_archetype": "qa_evidence_wall",
        "asset_recipe_id": "qa_report_capture",
        "material_key": "evidence_wall",
        "transition_family": "scan-focus",
        "motion_rule_ids": [
            "center-outward-expansion",
            "svg-path-draw",
            "coordinate-target-zoom",
        ],
        "scene_goal": "证明灵剪不是黑盒生成,而是可审计、可复跑、可回看的生产线。",
        "visual_content": "审批记录、产物文件、QA 检查项以证据墙形式排列,关键项逐个打勾。",
        "composition": "网格证据墙布局,左上放主结论,中部三张证据卡,右下保留 CTA 预热空间。",
        "focus": "先看主结论,再看三个证据卡依次点亮。",
        "motion_design": "证据卡翻入,检查项逐项描边高亮,镜头轻微推近到 QA 通过状态。",
        "transition_in": "审批印章变成证据墙标题。",
        "transition_out": "证据墙缩成一个 Star/关注行动按钮,接 CTA 镜。",
        "sfx": "轻微盖章音 + 三个勾选提示音。",
    },
    "proof_ffprobe_dashboard": {
        "role": "proof",
        "visual_archetype": "ffprobe_dashboard",
        "asset_recipe_id": "ffprobe_terminal_capture",
        "material_key": "terminal_dashboard",
        "transition_family": "terminal-scan",
        "motion_rule_ids": [
            "hacker-flip-3d",
            "asr-keyword-glow",
            "svg-path-draw",
        ],
        "scene_goal": "用真实技术体检结果证明视频有 h264/aac、无静态图和模板循环。",
        "visual_content": "ffprobe 输出、QA 结果、strict 通过状态组成技术仪表盘。",
        "composition": "终端窗口居中,右侧是三条大勾,底部字幕安全区。",
        "focus": "先看 strict 通过,再看 h264/aac 两项证据。",
        "motion_design": "终端字符 decode 出现,关键词 glow,勾选线条自绘。",
        "transition_in": "证据卡切到终端 scan。",
        "transition_out": "strict 通过徽章 morph 到 CTA 按钮。",
        "sfx": "终端短 beep + 勾选提示。",
    },
    "proof_manifest_timeline": {
        "role": "proof",
        "visual_archetype": "manifest_timeline",
        "asset_recipe_id": "render_manifest_capture",
        "material_key": "timeline_manifest",
        "transition_family": "timeline-push",
        "motion_rule_ids": [
            "viewport-change",
            "stat-bars-and-fills",
            "depth-of-field-blur",
        ],
        "scene_goal": "把 render_manifest 和三审记录变成可回看的证据时间线。",
        "visual_content": "脚本、配音、画面、渲染、QA、导出沿时间线依次通过。",
        "composition": "纵向时间线从上到下推进,每个节点有短证据标签。",
        "focus": "跟随时间线看每一步都有记录。",
        "motion_design": "viewport 下移,节点依次高亮,背景虚化未到节点。",
        "transition_in": "QA 仪表盘折叠成时间线。",
        "transition_out": "时间线末端推出 Star CTA。",
        "sfx": "连续极轻通过音。",
    },
    "cta_repo_star_press": {
        "role": "cta",
        "visual_archetype": "repo_star_press",
        "asset_recipe_id": "github_repo_star_capture",
        "material_key": "repo_cta_card",
        "transition_family": "cta-morph",
        "motion_rule_ids": [
            "scale-swap-transition",
            "cursor-click-ripple",
            "press-release-spring",
        ],
        "scene_goal": "明确行动:关注开源项目并 star,让用户知道下一步怎么做。",
        "visual_content": "项目名、GitHub star 行动、关注提示和一句结果承诺组成收尾画面。",
        "composition": "居中 CTA 卡片 + 下方简洁步骤,背景保留品牌色动线,字幕不遮 CTA。",
        "focus": "第一眼看 Star/关注按钮,第二眼看项目名。",
        "motion_design": (
            "CTA 卡片从证据墙缩放落位,Star 按钮发光一次后保持静止,"
            "背景线条向中心汇聚。"
        ),
        "transition_in": "证据墙缩放成 CTA 卡片。",
        "transition_out": "尾帧保留 0.5 秒给用户看清项目名和行动。",
        "sfx": "轻微完成音,无抢口播的夸张音效。",
    },
    "cta_install_flow": {
        "role": "cta",
        "visual_archetype": "install_flow_cta",
        "asset_recipe_id": "readme_install_capture",
        "material_key": "install_steps",
        "transition_family": "button-press",
        "motion_rule_ids": [
            "3d-page-scroll",
            "css-marker-patterns",
            "cursor-click-ripple",
        ],
        "scene_goal": "让小白用户知道项目怎么开始用,降低 star 之后的行动阻力。",
        "visual_content": "README 顶部安装入口、Codex app 触发语和 GitHub Star 按钮依次出现。",
        "composition": "README 页面 3D 滚动 + 安装命令高亮 + Star 行动浮层。",
        "focus": "先看安装入口,再看 Star 行动。",
        "motion_design": "页面 3D scroll 到安装区,marker 高亮,Star 按钮轻按反馈。",
        "transition_in": "证明时间线滚动到 README 页面。",
        "transition_out": "尾帧停在项目名和 Star。",
        "sfx": "marker 划过音 + 轻点击音。",
    },
    "cta_brand_lockup": {
        "role": "cta",
        "visual_archetype": "brand_lockup",
        "asset_recipe_id": "brand_outro_motion",
        "material_key": "brand_lockup",
        "transition_family": "logo-lockup",
        "motion_rule_ids": [
            "svg-path-draw",
            "orbit-3d-entry",
            "ambient-glow-bloom",
        ],
        "scene_goal": "用干净品牌收束记忆点,把关注和 star 留在最后一眼。",
        "visual_content": "灵剪项目名、开源地址、关注/star 行动组成尾帧。",
        "composition": "中心品牌 lockup,下方两步行动,底部字幕区不遮挡。",
        "focus": "看清项目名和 star 行动。",
        "motion_design": "线条自绘组成项目名,行动按钮轻微聚光一次后保持。",
        "transition_in": "上一镜 CTA 按钮扩展成品牌 lockup。",
        "transition_out": "保持 0.5 秒静止可读。",
        "sfx": "轻微完成音。",
    },
}

ROLE_BLUEPRINT_CANDIDATES: dict[str, list[str]] = {
    "hook": ["hook_codex_prompt", "hook_ticker_takeover", "hook_product_flash"],
    "pain": ["pain_overwhelm_board", "pain_dataviz_cost", "pain_spatial_stations"],
    "solution": [
        "solution_three_gate_flow",
        "solution_cursor_demo",
        "solution_asset_pipeline",
    ],
    "proof": [
        "proof_qa_evidence_wall",
        "proof_ffprobe_dashboard",
        "proof_manifest_timeline",
    ],
    "cta": ["cta_repo_star_press", "cta_install_flow", "cta_brand_lockup"],
}

REAL_EVIDENCE_ASSET_RECIPES = {
    "codex_operation_capture",
    "ffprobe_terminal_capture",
    "github_repo_star_capture",
    "lingjian_artifact_flow",
    "qa_report_capture",
    "readme_install_capture",
    "render_manifest_capture",
    "repo_and_cli_flash",
    "visual_asset_generation_queue",
}


def normalize_style(style: str | None) -> str:
    return style if style in STYLE_LOCKS else DEFAULT_STYLE


def normalize_profile(profile: str | None, platform: str = "douyin") -> str:
    if profile in PROFILE_PRESETS:
        return str(profile)
    for key, value in PROFILE_PRESETS.items():
        if value["platform"] == platform:
            return key
    return DEFAULT_PROFILE


def infer_content_profile(
    *,
    text: str = "",
    type_: str = "",
    platform: str = "douyin",
    profile: str | None = None,
) -> str:
    if profile and profile in PROFILE_PRESETS and profile != DEFAULT_PROFILE:
        return profile
    haystack = f"{type_} {text}".lower()
    if any(keyword in haystack for keyword in OPEN_SOURCE_PROFILE_KEYWORDS):
        return OPEN_SOURCE_PROFILE
    for profile_key, keywords in PROFILE_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return profile_key
    return normalize_profile(profile, platform)


def style_lock(style: str | None) -> dict[str, Any]:
    return deepcopy(STYLE_LOCKS[normalize_style(style)])


def profile_preset(profile: str | None, platform: str = "douyin") -> dict[str, Any]:
    return deepcopy(PROFILE_PRESETS[normalize_profile(profile, platform)])


def hook_library(profile: str | None, platform: str = "douyin") -> list[str]:
    key = normalize_profile(profile, platform)
    return list(HOOK_LIBRARY.get(key, HOOK_LIBRARY[DEFAULT_PROFILE]))


def director_knowledge_refs(
    *,
    profile: str | None,
    platform: str,
    blueprint_id: str,
) -> dict[str, Any]:
    profile_key = normalize_profile(profile, platform)
    blueprint = DIRECTOR_BLUEPRINTS.get(blueprint_id, {})
    return {
        "knowledge_base_version": "v1",
        "profile": profile_key,
        "profile_label_zh": PROFILE_PRESETS[profile_key]["label_zh"],
        "hook_patterns": _knowledge_ids_for_profile(profile_key),
        "blueprint_id": blueprint_id,
        "visual_archetype": blueprint.get("visual_archetype"),
        "asset_strategy": _asset_strategy_ref(profile_key, blueprint),
        "motion_rules": list(blueprint.get("motion_rule_ids") or []),
        "transition_rule": blueprint.get("transition_family"),
        "caption_rule": "bottom_safe_area_cjk",
        "sound_rules": ["voice_first_mix", "proof_tick"],
        "forbidden_items": [
            "static_as_video",
            "template_loop",
            "llm_self_eval",
        ],
    }


def director_knowledge_base_v1() -> dict[str, Any]:
    return {
        "version": "v1",
        "profiles": deepcopy(PROFILE_PRESETS),
        "knowledge": deepcopy(DIRECTOR_KNOWLEDGE_BASE),
    }


def plan_summary(
    *,
    platform: str,
    ratio: str,
    duration: int,
    scene_count: int,
    style: str | None,
    profile: str | None,
) -> str:
    style_data = style_lock(style)
    profile_data = profile_preset(profile, platform)
    fallback_arc = ["hook", "pain", "solution", "proof", "cta"]
    narrative_arc = "→".join(
        _narrative_arc_label(str(item))
        for item in profile_data.get("narrative_arc", fallback_arc)
    )
    return (
        f"平台 {platform},画幅 {ratio},目标 {duration} 秒,"
        f"叙事弧 {narrative_arc},"
        f"风格 {style_data['label_zh']},镜数 {scene_count},"
        f"节奏 {profile_data['cut_density']}。"
    )


def script_generation_contract(
    *,
    type_: str,
    platform: str,
    language: str,
    ratio: str,
    duration: int,
    style: str | None,
    profile: str | None,
) -> dict[str, Any]:
    profile_data = profile_preset(profile, platform)
    return {
        "type": type_,
        "platform": platform,
        "language": language,
        "ratio": profile_data.get("ratio") or ratio,
        "target_duration_sec": int(profile_data.get("duration_sec") or duration),
        "style": normalize_style(style),
        "profile": normalize_profile(profile, platform),
        "style_lock": style_lock(style),
        "profile_preset": profile_data,
        "hook_library": hook_library(profile, platform),
        "script_rules": {
            "narrative_arc": list(
                profile_data.get("narrative_arc", ["hook", "pain", "solution", "proof", "cta"])
            ),
            "first_3_sec": profile_data["first_3_sec"],
            "completion_oriented": True,
            "honesty": "提高成片确定性,不承诺爆款或传播。",
        },
    }


def layout_contract(index: int, ratio: str, role: str | None = None) -> dict[str, Any]:
    title_tier = "hero" if index == 1 or role == "hook" else "scene"
    if ratio == "16:9":
        return {
            "textRect": {"x": 96, "y": 80, "w": 700, "h": 220},
            "subjectRect": {"x": 820, "y": 110, "w": 960, "h": 660},
            "ctaRect": {"x": 1360, "y": 760, "w": 360, "h": 110},
            "quiet_text_zone": {"x": 220, "y": 880, "w": 1480, "h": 150},
            "safeBottomY": 1000,
            "title_tier": title_tier,
            "cjk_limits": {"title": 16, "data": 10, "subtitle_line": 18},
            "conflict_policy": "图文冲突时重生成,不将就。",
        }
    return {
        "textRect": {"x": 72, "y": 120, "w": 936, "h": 360},
        "subjectRect": {"x": 96, "y": 420, "w": 888, "h": 860},
        "ctaRect": {"x": 700, "y": 1120, "w": 300, "h": 150},
        "quiet_text_zone": {"x": 64, "y": 1320, "w": 952, "h": 280},
        "safeBottomY": 1510 if ratio == "9:16" else 1240,
        "title_tier": title_tier,
        "cjk_limits": {"title": 14, "data": 8, "subtitle_line": 16},
        "conflict_policy": "图文冲突时重生成,不将就。",
    }


def motion_contract(index: int, role: str | None = None) -> dict[str, Any]:
    template_id = _template_id(index, role)
    blueprint = DIRECTOR_BLUEPRINTS[template_id]
    role_motion = {
        "hook": "注意力钩子推进",
        "pain": "痛点聚焦",
        "solution": "方案展开",
        "proof": "证据放大",
        "cta": "行动收束",
    }
    return {
        "main_motion_intent": role_motion.get(str(role or ""), "信息层次推进"),
        "transition_intent": "语义切换,不在词中切",
        "transition_family": blueprint["transition_family"],
        "motion_rule_ids": list(blueprint["motion_rule_ids"]),
        "max_primary_motions": MAX_PRIMARY_MOTIONS,
        "develop_full_duration": True,
        "forbidden_negative": [
            "入场后冻结",
            "所有关键 beat 只使用 opacity+纵移",
            "同一镜头超过 2 个主运动",
        ],
        "deterministic_rules": DETERMINISTIC_RULES,
        "motion_index": index,
    }


def scene_director_contract(
    *,
    scene_id: str,
    index: int,
    role: str | None,
    ratio: str,
    style: str | None,
) -> dict[str, Any]:
    template_id = _template_id(index, role)
    blueprint = DIRECTOR_BLUEPRINTS[template_id]
    return {
        "template_id": template_id,
        "blueprint_id": template_id,
        "visual_archetype": blueprint["visual_archetype"],
        "asset_recipe_id": blueprint["asset_recipe_id"],
        "material_key": blueprint["material_key"],
        "compiler_policy": {
            "llm_may_choose_templates": True,
            "invent_geometry": False,
            "invent_motion": False,
        },
        "replaceable_fields": ["title", "body", "evidence", "data", "cta"],
        "non_replaceable_fields": [
            "template_id",
            "layout_contract",
            "motion_intent",
            "transition_plan",
            "style_lock",
            "deterministic_rules",
        ],
        "layout_contract": layout_contract(index, ratio, role),
        "motion_intent": motion_contract(index, role),
        "transition_plan": _transition_plan(index, role, blueprint),
        "requires_real_evidence_asset": (
            blueprint["asset_recipe_id"] in REAL_EVIDENCE_ASSET_RECIPES
        ),
        "quality_checks": [
            "相邻镜头蓝图/转场/主运动不得重复。",
            "产品介绍片必须包含真实产品/流程/证据画面。",
            "镜头内 reveal 应按口播节奏分布,不能开场一次性倒完。",
            "发布级 strict 必须通过静态图、模板循环、字幕安全区和运动检查。",
        ],
        "style_lock": style_lock(style),
        "inherits_design": True,
        "develop_full_duration": True,
        "removal_test": "删除任一装饰后表达不变则应删除该装饰。",
        "scene_contract_id": f"{scene_id}:{template_id}",
    }


def director_board(
    *,
    scene_id: str,
    index: int,
    role: str | None,
    narration_text: str,
    on_screen_text: str,
    duration_sec: float,
    generator: str,
    expected_asset_path: str | None,
    ratio: str,
    style: str | None,
    profile: str | None,
    platform: str,
) -> dict[str, Any]:
    template_id = _template_id(index, role)
    blueprint = DIRECTOR_BLUEPRINTS[template_id]
    style_data = style_lock(style)
    profile_data = profile_preset(profile, platform)
    short_text = _short_text(on_screen_text or narration_text, 24)
    keyframes = _keyframes(duration_sec, blueprint, short_text)
    return {
        "scene_id": scene_id,
        "blueprint_id": template_id,
        "visual_archetype": blueprint["visual_archetype"],
        "scene_goal": blueprint["scene_goal"],
        "visual_content": blueprint["visual_content"],
        "asset_strategy": _asset_strategy(generator, expected_asset_path),
        "asset_recipe_id": blueprint["asset_recipe_id"],
        "composition": blueprint["composition"],
        "focus": blueprint["focus"],
        "required_elements": [
            short_text,
            f"{template_id} 专属版式",
            "底部字幕安全区",
        ],
        "forbidden_elements": [
            "静态图片停留几秒",
            "Ken Burns/轻微缩放冒充视频",
            "整句旁白作为画面大字重复出现",
            "同一模板只换文字",
            "随机闪光/火箭/装饰堆砌",
        ],
        "motion_design": blueprint["motion_design"],
        "motion_rule_ids": list(blueprint["motion_rule_ids"]),
        "keyframes": keyframes,
        "transition": _transition_plan(index, role, blueprint),
        "subtitle_strategy": {
            "position": "底部安全区",
            "max_chars_per_line": profile_data["subtitle_limit"],
            "split_policy": "按语义短句拆分,避免一行塞满。",
            "style": "白字 + 深色半透明遮罩/描边,优先保证口播可读。",
            "avoidance": "不遮挡主体、CTA、按钮、产品关键区域。",
        },
        "color_mood": {
            "style": style_data["label_zh"],
            "palette": style_data["palette"],
            "lighting": style_data["lighting"],
            "atmosphere": style_data["motion_language"],
        },
        "audio_sfx_notes": {
            "bgm": profile_data["bgm_strategy"],
            "sfx": blueprint["sfx"],
            "mix": "人声优先,BGM 比人声低 16dB。",
        },
        "acceptance_checks": [
            "相邻镜头版式和主运动不同。",
            "相邻镜头转场 family 不重复。",
            "全片至少包含真实产品/流程/证据画面。",
            "画面全时长有开场/中段/收束变化,不是入场后冻结。",
            "字幕位于底部安全区且不遮挡主体。",
            "输出为真实动态视频资产,不是静态图片或模板循环。",
        ],
        "narration_text": narration_text,
        "duration_sec": duration_sec,
        "ratio": ratio,
    }


def asset_diagnosis(
    *,
    generator: str,
    expected_asset_path: str | None,
    asset_path: str | None = None,
) -> dict[str, Any]:
    path = str(asset_path or expected_asset_path or "")
    suffix = _path_suffix(path)
    if generator == "user-asset" and suffix in PUBLISH_GRADE_VIDEO_EXTENSIONS:
        return {
            "asset_status": "ready_user_video",
            "asset_kind": "dynamic_video",
            "publish_grade_visual": True,
            "source_zh": "用户提供的真实动态视频素材",
            "next_action_zh": "可进入画面三审;仍需确认字幕避让、主体不被遮挡和音画节奏。",
        }
    if generator == "user-asset" and suffix in STATIC_IMAGE_EXTENSIONS:
        return {
            "asset_status": "reference_only_static_image",
            "asset_kind": "static_image",
            "publish_grade_visual": False,
            "source_zh": "用户提供的是静态图片,只能作参考/封面/贴图。",
            "next_action_zh": (
                "请为这一镜提供 mp4/mov/m4v 视频素材,"
                "或启用 HyperFrames/Remotion 生成动态视频。"
            ),
        }
    if generator in {"hyperframes", "remotion", "seedance"}:
        return {
            "asset_status": "pending_dynamic_generation",
            "asset_kind": "dynamic_video",
            "publish_grade_visual": True,
            "source_zh": f"等待 {generator} 或宿主视频能力生成动态视频资产。",
            "next_action_zh": (
                f"按分镜生成 {path or 'assets/scenes/<scene_id>.mp4'};"
                "失败时不要改用静态图,应回到用户补视频素材或修复生成器。"
            ),
        }
    if generator == "image-gen" or suffix in STATIC_IMAGE_EXTENSIONS:
        return {
            "asset_status": "reference_only_generated_image",
            "asset_kind": "static_image",
            "publish_grade_visual": False,
            "source_zh": "imagegen/图片只能做视觉参考或分镜草图。",
            "next_action_zh": "请把参考图进一步生成动态视频,或提供同镜头 mp4/mov/m4v 视频素材。",
        }
    return {
        "asset_status": "blocked_missing_video_asset",
        "asset_kind": "missing",
        "publish_grade_visual": False,
        "source_zh": "当前没有发布级真实动态视频素材。",
        "next_action_zh": "请提供这一镜 mp4/mov/m4v 视频素材,或先启用 Codex app 中的视频生成插件。",
    }


def director_route_policy(
    *,
    generator: str,
    profile: str | None,
    platform: str,
    blueprint_id: str,
    expected_asset_path: str | None,
    asset_path: str | None = None,
) -> dict[str, Any]:
    profile_key = normalize_profile(profile, platform)
    profile_data = PROFILE_PRESETS[profile_key]
    blueprint = DIRECTOR_BLUEPRINTS.get(blueprint_id, {})
    diagnosis = asset_diagnosis(
        generator=generator,
        expected_asset_path=expected_asset_path,
        asset_path=asset_path,
    )
    if generator == "user-asset" and diagnosis["publish_grade_visual"]:
        route_id = "direct_user_video"
        selected_engine = "user_video"
        route_reason = "用户已提供动态视频素材,直接作为主画面,灵剪只处理字幕/叠加/QA。"
    elif generator == "remotion":
        route_id = "remotion_precision_opt_in"
        selected_engine = "remotion"
        route_reason = (
            "该镜可由 Remotion 执行精密时间轴、数据图表、复杂转场或 overlay;"
            "启用前必须保留 license/cost 提示。"
        )
    elif generator == "hyperframes":
        route_id = "hyperframes_default_motion"
        selected_engine = "hyperframes"
        route_reason = "该镜适合 HyperFrames 生成产品说明、界面演示或短视频动效 mp4。"
    elif generator == "seedance":
        route_id = "seedance_text_to_video"
        selected_engine = "seedance"
        route_reason = "该镜由 Seedance 文生视频(火山方舟 ARK)生成发布级真实动态视频 mp4。"
    elif generator == "image-gen":
        route_id = "static_reference_only"
        selected_engine = "imagegen_reference"
        route_reason = "imagegen 只能生成静态参考图,不能满足发布级动态画面。"
    else:
        route_id = "blocked_missing_dynamic_video"
        selected_engine = "needs_video_asset"
        route_reason = "当前缺发布级动态视频素材或宿主视频生成能力。"
    return {
        "route_id": route_id,
        "engine_policy": {
            "selected_engine": selected_engine,
            "generator": generator,
            "publish_grade_candidate": bool(diagnosis["publish_grade_visual"]),
            "remotion_license_required": generator == "remotion",
            "remotion_license_confirmed": False if generator == "remotion" else None,
            "core_must_not_bundle_engine_sdk": True,
        },
        "route_reason": route_reason,
        "asset_strategy_v2": asset_strategy_v2(
            generator=generator,
            profile=profile_key,
            blueprint_id=blueprint_id,
            expected_asset_path=expected_asset_path,
            asset_path=asset_path,
            diagnosis=diagnosis,
        ),
        "expected_real_evidence": _expected_real_evidence(profile_data, blueprint),
        "director_knowledge_refs": director_knowledge_refs(
            profile=profile_key,
            platform=platform,
            blueprint_id=blueprint_id,
        ),
        "caption_contract": {
            "rule_id": "bottom_safe_area_cjk",
            "position": "底部安全区",
            "max_chars_per_line": profile_data["subtitle_limit"],
            "avoid_subject_and_cta": True,
        },
    }


def asset_strategy_v2(
    *,
    generator: str,
    profile: str,
    blueprint_id: str,
    expected_asset_path: str | None,
    asset_path: str | None,
    diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnosis = diagnosis or asset_diagnosis(
        generator=generator,
        expected_asset_path=expected_asset_path,
        asset_path=asset_path,
    )
    profile_key = normalize_profile(profile)
    profile_data = PROFILE_PRESETS[profile_key]
    return {
        "profile": profile_key,
        "blueprint_id": blueprint_id,
        "required_evidence": list(profile_data.get("required_evidence") or []),
        "accepted_asset_formats": ["mp4", "mov", "m4v", "webm"],
        "rejected_as_publish_grade": ["png", "jpg", "jpeg", "webp", "kenburns", "template_loop"],
        "current_asset_kind": diagnosis["asset_kind"],
        "current_asset_status": diagnosis["asset_status"],
        "publish_grade_visual": diagnosis["publish_grade_visual"],
        "next_action_zh": diagnosis["next_action_zh"],
        "stock_image_policy": stock_image_policy(
            profile=profile_key,
            blueprint_id=blueprint_id,
        ),
    }


def stock_image_policy(*, profile: str, blueprint_id: str) -> dict[str, Any]:
    profile_key = normalize_profile(profile)
    return {
        "allowed": True,
        "allowed_when": "用户未提供自有图/截图,且这一镜确实需要配图或视觉设计层。",
        "requires_user_consent": True,
        "ask_user_before_fetch": True,
        "user_choices_zh": [
            "使用自有图片/截图",
            "授权从公开免费图库找图",
            "改用图形化无图方案",
            "AI 生图兜底",
        ],
        "source_priority": STOCK_IMAGE_SOURCE_PRIORITY,
        "license_fields_required": [
            "source",
            "sourceUrl",
            "license",
            "license_verification_status",
        ],
        "license_unverified_value": "UNVERIFIED",
        "not_evidence": True,
        "does_not_satisfy_real_evidence": True,
        "profile": profile_key,
        "blueprint_id": blueprint_id,
        "processing_requirements": [
            "裁切与构图要避开主体、CTA、底部字幕和平台 UI。",
            "必要时做透明背景处理、描边、遮罩或柔化边缘。",
            "统一调色和明暗,避免廉价图库感。",
            "只作为贴图/主体/氛围层进入动态画面,不能静态停留冒充视频。",
            "进入发布级前仍要接受运动、字幕避让、像素和人工观看验收。",
        ],
    }


def director_review_sheet_v2(
    *,
    scene_id: str,
    index: int,
    role: str | None,
    narration_text: str,
    on_screen_text: str,
    duration_sec: float,
    generator: str,
    expected_asset_path: str | None,
    asset_path: str | None,
    ratio: str,
    style: str | None,
    profile: str | None,
    platform: str,
    board: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    board = board or director_board(
        scene_id=scene_id,
        index=index,
        role=role,
        narration_text=narration_text,
        on_screen_text=on_screen_text,
        duration_sec=duration_sec,
        generator=generator,
        expected_asset_path=expected_asset_path,
        ratio=ratio,
        style=style,
        profile=profile,
        platform=platform,
    )
    contract = contract or scene_director_contract(
        scene_id=scene_id,
        index=index,
        role=role,
        ratio=ratio,
        style=style,
    )
    layout = contract.get("layout_contract") or layout_contract(index, ratio, role)
    motion = contract.get("motion_intent") or motion_contract(index, role)
    transition = contract.get("transition_plan") or board.get("transition") or {}
    route_policy = contract.get("director_route") or {}
    diagnosis = asset_diagnosis(
        generator=generator,
        expected_asset_path=expected_asset_path,
        asset_path=asset_path,
    )
    return {
        "version": "v2",
        "scene_id": scene_id,
        "scene_number": index,
        "narrative_function": role or board.get("scene_goal") or "未指定叙事功能",
        "narration_text": narration_text,
        "screen_text": on_screen_text,
        "visual_content": board.get("visual_content"),
        "asset_source": diagnosis["source_zh"],
        "asset_status": diagnosis,
        "asset_gap": diagnosis["next_action_zh"],
        "engine_recommendation": _engine_recommendation(generator),
        "engine_policy": route_policy.get("engine_policy"),
        "route_reason": route_policy.get("route_reason"),
        "asset_strategy_v2": route_policy.get("asset_strategy_v2"),
        "stock_image_policy": (route_policy.get("asset_strategy_v2") or {}).get(
            "stock_image_policy"
        ),
        "expected_real_evidence": route_policy.get("expected_real_evidence"),
        "director_knowledge_refs": route_policy.get("director_knowledge_refs"),
        "subject_region": layout.get("subjectRect"),
        "caption_region": {
            "label_zh": "底部安全区",
            "quiet_text_zone": layout.get("quiet_text_zone"),
            "safeBottomY": layout.get("safeBottomY"),
        },
        "caption_contract": route_policy.get("caption_contract"),
        "mask_avoidance_rules": [
            "主体、CTA、按钮和产品关键区域不得被字幕或贴纸遮挡。",
            "字幕固定在底部安全区,必要时给半透明底或描边。",
            "图文冲突时重生成,不要将就。",
        ],
        "composition": board.get("composition"),
        "visual_elements": board.get("required_elements", []),
        "color_mood": board.get("color_mood"),
        "primary_motion": motion.get("main_motion_intent") or board.get("motion_design"),
        "secondary_motion": motion.get("motion_rule_ids") or board.get("motion_rule_ids") or [],
        "transition": transition,
        "keyframes": board.get("keyframes", []),
        "entrance_animation": transition.get("in"),
        "exit_animation": transition.get("out"),
        "bgm": (board.get("audio_sfx_notes") or {}).get("bgm"),
        "sfx_points": (board.get("audio_sfx_notes") or {}).get("sfx"),
        "subtitle_split": (board.get("subtitle_strategy") or {}).get("split_policy"),
        "subtitle_position_size": {
            "position": (board.get("subtitle_strategy") or {}).get("position"),
            "max_chars_per_line": (board.get("subtitle_strategy") or {}).get(
                "max_chars_per_line"
            ),
            "style": (board.get("subtitle_strategy") or {}).get("style"),
        },
        "forbidden_items": board.get("forbidden_elements", []),
        "qa_checkpoints": board.get("acceptance_checks", []),
    }


def director_review_sheet_markdown(visual_plan: dict[str, Any]) -> str:
    sheet = visual_plan.get("director_review_sheet_v2") or {}
    scenes = [scene for scene in sheet.get("scenes", []) if isinstance(scene, dict)]
    asset_summary = visual_plan.get("asset_diagnosis_summary") or {}
    lines = [
        "# 导演分镜确认单 v2",
        "",
        "这份确认单用于画面三审。用户批准的是下面这份导演执行契约,不是抽象分镜或文件路径。",
        "",
        f"- 风格: {_md_value(visual_plan.get('style'))}",
        f"- 内容类型: {_md_value(visual_plan.get('profile'))}",
        f"- 画幅: {_md_value(visual_plan.get('ratio'))}",
        f"- 镜头数: {_md_value(visual_plan.get('visual_total') or len(scenes))}",
        f"- 非发布级素材缺口: {_md_value(asset_summary.get('non_publish_grade_count', 0))}",
    ]
    next_action = str(asset_summary.get("single_next_action_zh") or "").strip()
    if next_action:
        lines.append(f"- 当前最短补齐动作: {next_action}")
    lines.append("")
    for scene in scenes:
        lines.extend(_director_scene_markdown(scene))
    lines.extend(
        [
            "## 用户反馈入口",
            "",
            "- 批准画面分镜",
            "- 修改某一镜:请说清镜头编号和要改的地方",
            "- 补充素材:请拖入每镜真实视频素材或授权宿主插件生成动态视频",
            "- 重做分镜",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _director_scene_markdown(scene: dict[str, Any]) -> list[str]:
    scene_number = scene.get("scene_number") or scene.get("scene_id") or "?"
    title = f"## 镜头 {scene_number}: {_md_value(scene.get('narrative_function'))}"
    transition = scene.get("transition") if isinstance(scene.get("transition"), dict) else {}
    lines = [
        title,
        "",
        f"- 镜头编号: {_md_value(scene.get('scene_id'))}",
        f"- 镜头目标: {_md_value(scene.get('narrative_function'))}",
        f"- 叙事作用: {_md_value(scene.get('narrative_function'))}",
        f"- 口播文本: {_md_value(scene.get('narration_text'))}",
        f"- 屏幕短文案: {_md_value(scene.get('screen_text'))}",
        f"- 画面内容: {_md_value(scene.get('visual_content'))}",
        f"- 素材来源: {_md_value(scene.get('asset_source'))}",
        f"- 素材状态: {_asset_status_text(scene.get('asset_status'))}",
        f"- 免费图库策略: {_stock_image_policy_text(scene.get('stock_image_policy'))}",
        f"- Profile 证据要求: {_md_list(_scene_required_evidence(scene))}",
        f"- 引擎路由: {_engine_policy_text(scene)}",
        f"- 构图: {_md_value(scene.get('composition'))}",
        f"- 主体区域: {_md_value(scene.get('subject_region'))}",
        f"- 字幕区域: {_md_value(scene.get('caption_region'))}",
        f"- 遮罩/避让规则: {_md_list(scene.get('mask_avoidance_rules'))}",
        f"- 视觉元素: {_md_list(scene.get('visual_elements'))}",
        f"- 色彩/氛围: {_md_value(scene.get('color_mood'))}",
        f"- 主运动: {_md_value(scene.get('primary_motion'))}",
        f"- 辅助运动: {_md_list(scene.get('secondary_motion'))}",
        f"- 转场: {_transition_text(transition)}",
        f"- 关键帧: {_keyframes_text(scene.get('keyframes'))}",
        f"- 入场动画: {_md_value(scene.get('entrance_animation'))}",
        f"- 出场动画: {_md_value(scene.get('exit_animation'))}",
        f"- BGM 情绪: {_md_value(scene.get('bgm'))}",
        f"- 音效点: {_md_value(scene.get('sfx_points'))}",
        f"- 字幕切分: {_md_value(scene.get('subtitle_split'))}",
        f"- 字幕位置/大小: {_md_value(scene.get('subtitle_position_size'))}",
        f"- 禁止项: {_md_list(scene.get('forbidden_items'))}",
        f"- QA 检查点: {_md_list(scene.get('qa_checkpoints'))}",
        "",
        f"这一镜批准前你要看: {_approval_focus(scene)}",
        "",
    ]
    return lines


def _scene_required_evidence(scene: dict[str, Any]) -> list[str]:
    strategy = scene.get("asset_strategy_v2")
    if isinstance(strategy, dict) and isinstance(strategy.get("required_evidence"), list):
        return [str(item) for item in strategy["required_evidence"] if str(item).strip()]
    expected = scene.get("expected_real_evidence")
    if isinstance(expected, list):
        return [str(item) for item in expected if str(item).strip()]
    return []


def _asset_status_text(value: Any) -> str:
    if not isinstance(value, dict):
        return _md_value(value)
    return (
        f"{_md_value(value.get('asset_status'))}; "
        f"发布级={_md_value(value.get('publish_grade_visual'))}; "
        f"下一步={_md_value(value.get('next_action_zh'))}"
    )


def _stock_image_policy_text(value: Any) -> str:
    if not isinstance(value, dict):
        return _md_value(value)
    allowed = "可作为授权配图" if value.get("allowed") else "不使用"
    consent = "需先征询用户" if value.get("requires_user_consent") else "无需额外确认"
    not_evidence = "不能替代真实动态 evidence" if value.get("not_evidence") else ""
    allowed_when = str(value.get("allowed_when") or "").strip()
    return "；".join(part for part in (allowed, consent, allowed_when, not_evidence) if part)


def _engine_policy_text(scene: dict[str, Any]) -> str:
    policy = scene.get("engine_policy") if isinstance(scene.get("engine_policy"), dict) else {}
    engine = policy.get("selected_engine") or scene.get("engine_recommendation")
    reason = scene.get("route_reason")
    return f"{_md_value(engine)}; 原因={_md_value(reason)}"


def _transition_text(transition: dict[str, Any]) -> str:
    if not transition:
        return "未声明"
    family = transition.get("family") or transition.get("transition_family")
    in_motion = transition.get("in")
    out_motion = transition.get("out")
    return f"{_md_value(family)}; 入场={_md_value(in_motion)}; 出场={_md_value(out_motion)}"


def _keyframes_text(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "未声明"
    parts = []
    for item in value:
        if isinstance(item, dict):
            time_value = _first_present_value(item, "time_sec", "time", "at")
            desc = item.get("state") or item.get("description") or item.get("action") or item
            parts.append(f"{_md_value(time_value)}s:{_md_value(desc)}")
        else:
            parts.append(_md_value(item))
    return " / ".join(parts)


def _first_present_value(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source:
            return source[key]
    return None


def _approval_focus(scene: dict[str, Any]) -> str:
    visual = _md_value(scene.get("visual_content"))
    asset = scene.get("asset_status")
    next_action = asset.get("next_action_zh") if isinstance(asset, dict) else ""
    return (
        f"画面是否真的生成“{visual}”,字幕是否在底部避让主体,"
        f"且素材策略是否满足发布级。{_md_value(next_action)}"
    )


def _md_list(value: Any) -> str:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "；".join(items) if items else "未声明"
    return _md_value(value)


def _md_value(value: Any) -> str:
    if value is None or value == "":
        return "未声明"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, dict):
        return "；".join(f"{key}={_md_value(val)}" for key, val in value.items())
    if isinstance(value, list):
        return _md_list(value)
    return str(value)


def asset_diagnosis_summary(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    diagnostics = [
        scene.get("asset_diagnosis")
        or _review_sheet_asset_status(scene)
        for scene in scenes
    ]
    valid = [item for item in diagnostics if isinstance(item, dict)]
    blockers = [
        {
            "scene_id": scene.get("scene_id"),
            "asset_status": item.get("asset_status"),
            "next_action_zh": item.get("next_action_zh"),
        }
        for scene, item in zip(scenes, diagnostics, strict=False)
        if isinstance(item, dict) and not item.get("publish_grade_visual")
    ]
    return {
        "total": len(scenes),
        "publish_grade_candidate_count": sum(
            1 for item in valid if item.get("publish_grade_visual")
        ),
        "non_publish_grade_count": len(blockers),
        "blockers": blockers,
        "single_next_action_zh": blockers[0]["next_action_zh"] if blockers else "",
    }


def _review_sheet_asset_status(scene: dict[str, Any]) -> dict[str, Any] | None:
    for sheet in _scene_review_sheets(scene):
        status = sheet.get("asset_status")
        if isinstance(status, dict):
            return status
    return None


def visual_brief(
    *,
    ratio: str,
    style: str | None,
    profile: str | None,
    platform: str,
) -> dict[str, Any]:
    preset = profile_preset(profile, platform)
    preset["ratio"] = ratio
    preset["platform"] = platform
    return {
        "aspect": ratio,
        "safe_zone": "底部安全区保留字幕与平台 UI,不要放主体/CTA",
        "style_lock": style_lock(style),
        "profile": preset,
        "deterministic_rules": DETERMINISTIC_RULES,
        "forbidden": [
            "画面别再嵌大段文字",
            "不要把图片/模板循环当发布级视频",
            "不要随机闪光/火箭/一行一图标/装饰堆",
        ],
        "subtitle_policy": "口播全文只由灵剪底部字幕承载。",
    }


def paid_engine_notice(engine_id: str) -> str | None:
    return PAID_GENERATORS.get(engine_id)


def remotion_license_notice() -> str:
    return (
        "Remotion 为 opt-in 第二渲染引擎;个人/非营利/≤3 员工营利组织通常可免费,"
        "更大营利组织需确认 remotion.pro 商用许可;需要 Node 与 Chrome Headless。"
    )


def self_check_visual_scenes(
    scenes: list[dict[str, Any]],
    *,
    ratio: str,
    style: str | None,
    max_rounds: int = 2,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checked = deepcopy(scenes)
    attempts: list[dict[str, str | int]] = []
    for round_index in range(1, max_rounds + 1):
        target = _first_repairable_scene(checked)
        if target is None:
            break
        scene_index, finding = target
        repaired = _repair_scene_contract(
            checked[scene_index],
            finding["code"],
            index=scene_index + 1,
            ratio=ratio,
            style=style,
        )
        attempts.append(
            {
                "round": round_index,
                "scene_id": str(checked[scene_index].get("scene_id") or f"s{scene_index + 1}"),
                "finding_code": finding["code"],
                "action": repaired,
            }
        )
        if repaired == "needs_human_review":
            break
    status = "passed" if _first_repairable_scene(checked) is None else "needs_review"
    return checked, {
        "max_rounds": max_rounds,
        "attempts": attempts,
        "status": status,
        "policy": "生成后、人工画面三审前最多修两轮;每轮只改一个最弱 layout/motion 问题。",
    }


def motion_quality_findings(scene: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    motion = scene.get("motion_intent") or scene.get("motion_spec") or scene.get("motion") or {}
    primary_count = _primary_motion_count(motion)
    if primary_count > MAX_PRIMARY_MOTIONS:
        findings.append(
            {
                "code": "RELEASE_VISUAL_TOO_MANY_PRIMARY_MOTIONS",
                "message_zh": "单镜头主运动超过 2 个,容易失焦。",
            }
        )
    beats = motion.get("beats")
    if isinstance(beats, list) and beats:
        if all(_is_opacity_vertical_beat(beat) for beat in beats if isinstance(beat, dict)):
            findings.append(
                {
                    "code": "RELEASE_VISUAL_MOTION_TOO_WEAK",
                    "message_zh": "关键 beat 只使用 opacity+纵移,更像 PPT 入场动画。",
                }
            )
    if motion.get("develop_full_duration") is False or scene.get("develop_full_duration") is False:
        findings.append(
            {
                "code": "RELEASE_VISUAL_FREEZES_AFTER_ENTRY",
                "message_zh": "镜头入场后冻结,未持续发展完整时长。",
            }
        )
    keyframes = _scene_keyframes(scene)
    if _scene_has_director_contract(scene) and len(keyframes) < MIN_KEYFRAMES_PER_DIRECTOR_SCENE:
        findings.append(
            {
                "code": "RELEASE_VISUAL_KEYFRAMES_INSUFFICIENT",
                "message_zh": (
                    "导演分镜缺少开场/中段/收束 3 个关键帧,"
                    "无法证明镜头全时长有视觉发展。"
                ),
            }
        )
    keyframe_states = [_keyframe_state_text(item) for item in keyframes]
    known_keyframe_states = [state for state in keyframe_states if state]
    if (
        _scene_has_director_contract(scene)
        and len(keyframes) >= MIN_KEYFRAMES_PER_DIRECTOR_SCENE
        and len(known_keyframe_states) < MIN_KEYFRAMES_PER_DIRECTOR_SCENE
    ):
        findings.append(
            {
                "code": "RELEASE_VISUAL_KEYFRAMES_STATE_MISSING",
                "message_zh": "导演关键帧缺少可审计的视觉状态说明,无法证明每个 beat 真有画面变化。",
            }
        )
    if (
        _scene_has_director_contract(scene)
        and len(known_keyframe_states) >= MIN_KEYFRAMES_PER_DIRECTOR_SCENE
        and len({_normalize_keyframe_state(state) for state in known_keyframe_states})
        < MIN_KEYFRAMES_PER_DIRECTOR_SCENE
    ):
        findings.append(
            {
                "code": "RELEASE_VISUAL_KEYFRAMES_STATE_REPEATED",
                "message_zh": "导演关键帧视觉状态重复,无法证明开场/中段/收束是不同画面发展。",
            }
        )
    keyframe_times = [_keyframe_time_sec(item) for item in keyframes]
    known_keyframe_times = [value for value in keyframe_times if value is not None]
    duration_sec = _scene_duration_sec(scene)
    has_timed_director_keyframes = (
        _scene_has_director_contract(scene)
        and len(known_keyframe_times) >= MIN_KEYFRAMES_PER_DIRECTOR_SCENE
        and duration_sec is not None
    )
    if (
        has_timed_director_keyframes
        and min(known_keyframe_times) > duration_sec * MAX_OPENING_KEYFRAME_RATIO
    ):
        findings.append(
            {
                "code": "RELEASE_VISUAL_KEYFRAMES_MISSING_OPENING_BEAT",
                "message_zh": "导演关键帧缺少镜头开场 beat,无法证明画面从开头就有设计。",
            }
        )
    if has_timed_director_keyframes and not any(
        duration_sec * MIN_MIDDLE_KEYFRAME_RATIO
        <= value
        <= duration_sec * MAX_MIDDLE_KEYFRAME_RATIO
        for value in known_keyframe_times
    ):
        findings.append(
            {
                "code": "RELEASE_VISUAL_KEYFRAMES_MISSING_MIDDLE_BEAT",
                "message_zh": "导演关键帧缺少镜头中段 beat,无法证明画面中段持续发展。",
            }
        )
    if (
        has_timed_director_keyframes
        and max(known_keyframe_times) < duration_sec * MIN_KEYFRAME_DURATION_COVERAGE_RATIO
    ):
        findings.append(
            {
                "code": "RELEASE_VISUAL_KEYFRAMES_DO_NOT_COVER_DURATION",
                "message_zh": "导演关键帧集中在前半段,未覆盖镜头后段,容易变成入场后静止。",
            }
        )
    return findings


def layout_quality_findings(scene: dict[str, Any]) -> list[dict[str, str]]:
    contract = scene.get("layout_contract") or {}
    required = {"textRect", "subjectRect", "quiet_text_zone", "safeBottomY", "title_tier"}
    if not required.issubset(contract):
        return [
            {
                "code": "RELEASE_VISUAL_LAYOUT_CONTRACT_MISSING",
                "message_zh": "缺少生图/视频生成前锁定的 layout contract。",
            }
        ]
    findings: list[dict[str, str]] = []
    if _rects_overlap(contract.get("subjectRect"), contract.get("quiet_text_zone")):
        findings.append(
            {
                "code": "RELEASE_VISUAL_LAYOUT_CONFLICT",
                "message_zh": "主体区域与字幕/安静文字区冲突,应重生成而非将就。",
            }
        )
    caption_zone = _caption_quiet_zone(scene, contract)
    if _caption_zone_too_high(caption_zone, contract.get("safeBottomY")):
        findings.append(
            {
                "code": "RELEASE_CAPTION_SAFE_AREA_INVALID",
                "message_zh": "字幕安静区未落在底部安全区,可能遮挡主体或平台 UI。",
            }
        )
    if (
        caption_zone != contract.get("quiet_text_zone")
        and _rects_overlap(contract.get("subjectRect"), caption_zone)
    ):
        findings.append(
            {
                "code": "RELEASE_CAPTION_OVERLAPS_SUBJECT",
                "message_zh": "分镜确认单中的字幕区域与主体区域重叠。",
            }
        )
    cta_regions = _scene_cta_regions(scene, contract)
    if _scene_requires_cta_region(scene) and not cta_regions:
        findings.append(
            {
                "code": "RELEASE_CTA_REGION_NOT_DECLARED",
                "message_zh": "CTA/行动收束镜头未声明按钮或行动区域,无法证明字幕和贴纸避让 CTA。",
            }
        )
    if caption_zone and any(_rects_overlap(region, caption_zone) for region in cta_regions):
        findings.append(
            {
                "code": "RELEASE_CAPTION_OVERLAPS_CTA",
                "message_zh": "字幕安静区与 CTA/按钮区域重叠,发布级行动按钮必须可见。",
            }
        )
    caption_contract = _caption_contract(scene)
    if caption_contract:
        if not _caption_declares_bottom_safe_area(caption_contract):
            findings.append(
                {
                    "code": "RELEASE_CAPTION_SAFE_AREA_NOT_DECLARED",
                    "message_zh": "字幕契约未声明底部安全区,不能证明字幕避开主体。",
                }
            )
        if caption_contract.get("avoid_subject_and_cta") is not True:
            findings.append(
                {
                    "code": "RELEASE_CAPTION_AVOIDANCE_NOT_DECLARED",
                    "message_zh": "字幕契约未声明避让主体/CTA。",
                }
            )
    return findings


def director_route_findings(scene: dict[str, Any]) -> list[dict[str, str]]:
    if not _scene_has_director_contract(scene):
        return []
    required = {
        "engine_policy",
        "route_reason",
        "asset_strategy_v2",
        "director_knowledge_refs",
        "caption_contract",
    }
    missing = [key for key in required if not scene.get(key)]
    findings: list[dict[str, str]] = []
    if missing:
        findings.append(
            {
                "code": "RELEASE_VISUAL_DIRECTOR_ROUTE_MISSING",
                "message_zh": "导演路由字段缺失,无法证明每镜引擎选择和素材策略。",
            }
        )
    policy = scene.get("engine_policy") or {}
    if isinstance(policy, dict):
        scene_generator = str(scene.get("generator") or "").strip()
        policy_generator = str(policy.get("generator") or "").strip()
        if scene_generator and policy_generator and scene_generator != policy_generator:
            findings.append(
                {
                    "code": "RELEASE_VISUAL_DIRECTOR_ROUTE_MISMATCH",
                    "message_zh": (
                        "导演路由记录的 generator 与实际镜头 generator 不一致,"
                        "无法证明内部引擎分派真实执行。"
                    ),
                }
            )
        expected_engine = _expected_selected_engine_for_scene(scene, policy)
        selected_engine = str(policy.get("selected_engine") or "").strip()
        if expected_engine and selected_engine and selected_engine != expected_engine:
            findings.append(
                {
                    "code": "RELEASE_VISUAL_DIRECTOR_ROUTE_MISMATCH",
                    "message_zh": (
                        "导演路由与实际画面 generator 不一致,"
                        "无法证明普通用户看到的是正确的内部引擎分派。"
                    ),
                }
            )
    if (
        isinstance(policy, dict)
        and policy.get("selected_engine") == "remotion"
        and policy.get("remotion_license_required") is not True
    ):
        findings.append(
            {
                "code": "RELEASE_VISUAL_REMOTION_LICENSE_NOTICE_MISSING",
                "message_zh": "Remotion 路由缺少 license/cost gate 标记。",
            }
        )
    if (
        isinstance(policy, dict)
        and policy.get("selected_engine") == "remotion"
        and policy.get("remotion_license_required") is True
        and not _remotion_license_confirmed(scene, policy)
    ):
        findings.append(
            {
                "code": "RELEASE_VISUAL_REMOTION_LICENSE_NOT_CONFIRMED",
                "message_zh": (
                    "Remotion 已被选为发布级画面执行器,"
                    "但缺少用户确认 license 的可审计记录。"
                ),
            }
        )
    return findings


def _expected_selected_engine_for_scene(
    scene: dict[str, Any],
    policy: dict[str, Any],
) -> str:
    generator = str(policy.get("generator") or scene.get("generator") or "").strip()
    if generator == "hyperframes":
        return "hyperframes"
    if generator == "seedance":
        return "seedance"
    if generator == "remotion":
        return "remotion"
    if generator == "image-gen":
        return "imagegen_reference"
    if generator == "fallback_solid":
        return "needs_video_asset"
    if generator == "user-asset":
        path = str(scene.get("asset_path") or scene.get("expected_asset_path") or "")
        if _path_suffix(path) in PUBLISH_GRADE_VIDEO_EXTENSIONS:
            return "user_video"
        return "needs_video_asset"
    return ""


def _remotion_license_confirmed(scene: dict[str, Any], policy: dict[str, Any]) -> bool:
    if policy.get("remotion_license_confirmed") is True:
        return True
    if scene.get("remotion_license_confirmed") is True:
        return True
    for value in (
        policy.get("license_confirmation"),
        scene.get("license_confirmation"),
        scene.get("remotion_license_confirmation"),
    ):
        if not isinstance(value, dict):
            continue
        status = str(value.get("status") or "").strip().lower()
        if status in {"confirmed", "accepted", "approved"}:
            return True
        if value.get("confirmed") is True:
            return True
    return False


def host_generation_contract_findings(scene: dict[str, Any]) -> list[dict[str, str]]:
    if not _scene_uses_director_host_adapter(scene):
        return []
    contract = scene.get("host_generation_contract")
    if not isinstance(contract, dict):
        return [
            {
                "code": "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE",
                "message_zh": "宿主画面生成器未回写导演契约消费证据,无法证明生成时使用了分镜规格。",
            }
        ]

    missing: list[str] = []
    if contract.get("contract_confirmed_by_generator") is not True:
        missing.append("contract_confirmed_by_generator")
    _require_equal(contract, "blueprint_id", scene.get("blueprint_id"), missing)
    _require_equal(contract, "visual_archetype", scene.get("visual_archetype"), missing)
    _require_equal(contract, "asset_recipe_id", scene.get("asset_recipe_id"), missing)
    _require_equal(contract, "material_key", scene.get("material_key"), missing)
    if scene.get("layout_contract") and not str(contract.get("layout_signature") or "").strip():
        missing.append("layout_signature")
    transition_plan = scene.get("transition_plan")
    if isinstance(transition_plan, dict):
        _require_equal(contract, "transition_family", transition_plan.get("family"), missing)
    expected_motion = set(_motion_rule_ids(scene))
    if expected_motion:
        actual_motion = (
            {str(item) for item in contract.get("motion_rule_ids", []) if item}
            if isinstance(contract.get("motion_rule_ids"), list)
            else set()
        )
        if not expected_motion.issubset(actual_motion):
            missing.append("motion_rule_ids")
    keyframes = _scene_keyframes(scene)
    if keyframes:
        expected_keyframe_count = len(keyframes)
        keyframe_count = _contract_int(contract.get("keyframe_count"))
        if keyframe_count < expected_keyframe_count:
            missing.append("keyframe_count")
        expected_state_count = len(
            {
                _normalize_keyframe_state(state)
                for state in (_keyframe_state_text(item) for item in keyframes)
                if state
            }
        )
        if expected_state_count:
            keyframe_state_count = _contract_int(contract.get("keyframe_state_count"))
            if keyframe_state_count < expected_state_count:
                missing.append("keyframe_state_count")
    evidence_refs = scene.get("evidence_asset_refs")
    if isinstance(evidence_refs, list) and evidence_refs:
        try:
            evidence_ref_count = int(contract.get("evidence_ref_count"))
        except (TypeError, ValueError):
            evidence_ref_count = 0
        if evidence_ref_count < len(evidence_refs):
            missing.append("evidence_ref_count")
        evidence_media_count = _evidence_media_ref_count(evidence_refs)
        if evidence_media_count:
            try:
                consumed_media_count = int(contract.get("evidence_media_count"))
            except (TypeError, ValueError):
                consumed_media_count = 0
            if consumed_media_count < evidence_media_count:
                missing.append("evidence_media_count")
        if (
            _evidence_video_media_ref_count(evidence_refs)
            and str(contract.get("evidence_media_hero_kind") or "") != "video"
        ):
            missing.append("evidence_media_hero_kind")
        if _evidence_video_media_ref_count(evidence_refs):
            if str(contract.get("evidence_media_hero_role") or "") != "primary_visual":
                missing.append("evidence_media_hero_role")
            if contract.get("template_body_suppressed_for_evidence") is not True:
                missing.append("template_body_suppressed_for_evidence")

    if not missing:
        return []
    return [
        {
            "code": "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE",
            "message_zh": (
                "宿主画面生成器回写的导演契约消费证据不完整:"
                f"{', '.join(dict.fromkeys(missing))}。"
            ),
        }
    ]


def _contract_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def director_diversity_findings(scenes: list[dict[str, Any]]) -> list[dict[str, str]]:
    rich_scenes = [
        scene
        for scene in scenes
        if isinstance(scene, dict)
        and (
            scene.get("template_id")
            or scene.get("blueprint_id")
            or scene.get("visual_archetype")
            or scene.get("transition_plan")
            or scene.get("host_generation_contract")
            or scene.get("layout_contract")
            or _scene_review_sheets(scene)
        )
    ]
    if len(rich_scenes) < 2:
        return []

    findings: list[dict[str, str]] = []
    blueprint_ids = [_scene_value(scene, "blueprint_id", "template_id") for scene in rich_scenes]
    transition_families = [
        _scene_transition_family(scene)
        for scene in rich_scenes
    ]
    material_keys = [str(scene.get("material_key") or "") for scene in rich_scenes]
    layout_signatures = [_layout_signature(scene) for scene in rich_scenes]
    motion_rules = [
        set(_motion_rule_ids(scene))
        for scene in rich_scenes
    ]

    if _has_adjacent_repeat(blueprint_ids):
        findings.append(
            {
                "code": "RELEASE_VISUAL_BLUEPRINT_REPEATED",
                "message_zh": "相邻镜头使用同一导演蓝图,容易呈现模板循环感。",
            }
        )
    if len(rich_scenes) >= MIN_BLUEPRINT_VARIETY_FOR_MULTI_SCENE:
        unique_blueprints = {value for value in blueprint_ids if value}
        if len(unique_blueprints) < MIN_BLUEPRINT_VARIETY_FOR_MULTI_SCENE:
            findings.append(
                {
                    "code": "RELEASE_VISUAL_BLUEPRINT_VARIETY_TOO_LOW",
                    "message_zh": "全片导演蓝图种类不足,画面容易显得单一。",
                }
            )

    if _has_adjacent_repeat(transition_families):
        findings.append(
            {
                "code": "RELEASE_VISUAL_TRANSITION_REPEATED",
                "message_zh": "相邻镜头转场语法重复,缺少语义变化。",
            }
        )

    if _has_three_consecutive_repeat(material_keys):
        findings.append(
            {
                "code": "RELEASE_VISUAL_MATERIAL_TOO_UNIFORM",
                "message_zh": "连续多个镜头使用同一背景/材质系统,观感过于单一。",
            }
        )
    if _has_three_consecutive_repeat(layout_signatures):
        findings.append(
            {
                "code": "RELEASE_VISUAL_LAYOUT_TOO_UNIFORM",
                "message_zh": "连续多个镜头使用同一执行布局/构图签名,容易像同一模板换字。",
            }
        )

    unique_motion_rules = set().union(*motion_rules) if motion_rules else set()
    if len(rich_scenes) >= 3 and len(unique_motion_rules) < MIN_MOTION_VOCAB_FOR_MULTI_SCENE:
        findings.append(
            {
                "code": "RELEASE_VISUAL_MOTION_VOCAB_TOO_THIN",
                "message_zh": "全片主运动词汇过少,容易像同一模板反复换字。",
            }
        )

    required_evidence = [
        scene
        for scene in rich_scenes
        if scene.get("requires_real_evidence_asset") is True
    ]
    has_real_evidence_recipe = any(
        _scene_has_real_evidence_recipe(scene) for scene in rich_scenes
    )
    if required_evidence and not has_real_evidence_recipe:
        findings.append(
            {
                "code": "RELEASE_VISUAL_LACKS_REAL_EVIDENCE_ASSET",
                "message_zh": "导演契约要求真实产品/流程/证据素材,但全片缺少对应素材策略。",
            }
        )
    if _is_open_source_video(rich_scenes):
        evidence_recipes = {
            recipe
            for scene in rich_scenes
            for recipe in [_real_evidence_recipe_id(scene)]
            if recipe
        }
        if len(evidence_recipes) < MIN_OPEN_SOURCE_EVIDENCE_RECIPES:
            findings.append(
                {
                    "code": "RELEASE_VISUAL_EVIDENCE_DENSITY_TOO_LOW",
                    "message_zh": (
                        "开源项目介绍片真实证据镜头类型不足;"
                        "至少需要 GitHub/README/Codex 操作/终端/QA/导出包等 3 类证据。"
                    ),
                }
            )

    return findings


def _scene_has_director_contract(scene: dict[str, Any]) -> bool:
    return bool(
        scene.get("template_id")
        or scene.get("blueprint_id")
        or scene.get("visual_archetype")
        or scene.get("asset_recipe_id")
        or scene.get("transition_plan")
        or scene.get("motion_intent")
        or scene.get("layout_contract")
        or scene.get("host_generation_contract")
        or scene.get("director_board")
        or scene.get("director_review_sheet_v2")
        or scene.get("director_review_sheet")
        or scene.get("director_knowledge_refs")
        or scene.get("asset_strategy_v2")
        or scene.get("expected_real_evidence")
    )


def _scene_uses_director_host_adapter(scene: dict[str, Any]) -> bool:
    origin = str(scene.get("asset_origin") or "")
    if origin in DIRECTOR_HOST_ADAPTERS:
        return True
    contract = scene.get("host_generation_contract")
    if isinstance(contract, dict) and str(contract.get("adapter") or "") in DIRECTOR_HOST_ADAPTERS:
        return True
    return str(scene.get("generator") or "") in {
        "hyperframes",
        "remotion",
    } and _scene_has_director_contract(scene)


def _require_equal(
    contract: dict[str, Any],
    key: str,
    expected: Any,
    missing: list[str],
) -> None:
    if expected in (None, "", []):
        return
    if str(contract.get(key) or "") != str(expected):
        missing.append(key)


def _first_repairable_scene(scenes: list[dict[str, Any]]) -> tuple[int, dict[str, str]] | None:
    for index, scene in enumerate(scenes):
        findings = layout_quality_findings(scene) + motion_quality_findings(scene)
        for finding in findings:
            if finding["code"] in {
                "RELEASE_VISUAL_LAYOUT_CONTRACT_MISSING",
                "RELEASE_VISUAL_LAYOUT_CONFLICT",
                "RELEASE_VISUAL_TOO_MANY_PRIMARY_MOTIONS",
                "RELEASE_VISUAL_MOTION_TOO_WEAK",
                "RELEASE_VISUAL_FREEZES_AFTER_ENTRY",
            }:
                return index, finding
    return None


def _repair_scene_contract(
    scene: dict[str, Any],
    code: str,
    *,
    index: int,
    ratio: str,
    style: str | None,
) -> str:
    role = scene.get("role")
    if code in {"RELEASE_VISUAL_LAYOUT_CONTRACT_MISSING", "RELEASE_VISUAL_LAYOUT_CONFLICT"}:
        scene["layout_contract"] = layout_contract(index, ratio, str(role) if role else None)
        return "reset_layout_contract"
    if code == "RELEASE_VISUAL_TOO_MANY_PRIMARY_MOTIONS":
        motion = scene.get("motion_intent") or scene.get("motion_spec") or {}
        if isinstance(motion.get("primary_motions"), list):
            motion["primary_motions"] = motion["primary_motions"][:MAX_PRIMARY_MOTIONS]
            scene["motion_intent"] = motion
            return "trim_primary_motions"
        if isinstance(motion.get("motions"), list):
            motion["motions"] = motion["motions"][:MAX_PRIMARY_MOTIONS]
            scene["motion_intent"] = motion
            return "trim_primary_motions"
    if code in {"RELEASE_VISUAL_MOTION_TOO_WEAK", "RELEASE_VISUAL_FREEZES_AFTER_ENTRY"}:
        scene["motion_intent"] = motion_contract(index, str(role) if role else None)
        scene["develop_full_duration"] = True
        scene["style_lock"] = style_lock(style)
        return "reset_motion_contract"
    return "needs_human_review"


def _template_id(index: int, role: str | None) -> str:
    role_key = str(role or "").strip()
    candidates = ROLE_BLUEPRINT_CANDIDATES.get(role_key)
    if not candidates:
        role_cycle = ["hook", "pain", "solution", "proof", "cta"]
        candidates = ROLE_BLUEPRINT_CANDIDATES[role_cycle[(index - 1) % len(role_cycle)]]
    return candidates[(index - 1) % len(candidates)]


def _transition_plan(
    index: int,
    role: str | None,
    blueprint: dict[str, Any],
) -> dict[str, Any]:
    family = str(blueprint["transition_family"])
    return {
        "family": family,
        "semantic": _transition_semantic(role),
        "in": blueprint["transition_in"],
        "out": blueprint["transition_out"],
        "cut_policy": "不在词中切,必要时 30ms 淡入淡出。",
        "diversity_policy": "相邻镜头不得复用同一 transition family。",
        "transition_index": index,
    }


def _asset_strategy(generator: str, expected_asset_path: str | None) -> str:
    if generator in {"hyperframes", "remotion", "seedance"}:
        return (
            f"由 {generator} 或 Codex 宿主视频生成能力输出真实动态 mp4 到 "
            f"{expected_asset_path};失败时必须回到用户补素材,不能用静态图冒充。"
        )
    if generator == "user-asset":
        return f"使用用户提供的视频素材 {expected_asset_path};若是图片则只能样片预览。"
    if generator == "image-gen":
        return "imagegen 只能生成参考图/分镜草图,发布级必须再转成动态视频。"
    return "当前缺真实画面能力,只能生成占位样片;发布级必须补每镜视频资产。"


def _asset_strategy_ref(profile_key: str, blueprint: dict[str, Any]) -> str:
    recipe = str(blueprint.get("asset_recipe_id") or "")
    if profile_key == OPEN_SOURCE_PROFILE:
        return "open_source_evidence"
    if recipe in REAL_EVIDENCE_ASSET_RECIPES:
        return "dynamic_generation"
    return "user_video_primary"


def _knowledge_ids_for_profile(profile_key: str) -> list[str]:
    if profile_key == OPEN_SOURCE_PROFILE:
        return ["pain_direct", "process_peek", "proof_first"]
    if profile_key == PRODUCT_INTRO_PROFILE:
        return ["pain_direct", "process_peek", "proof_first"]
    if profile_key == TUTORIAL_PROFILE:
        return ["process_peek", "proof_first"]
    if profile_key == REVIEW_PROFILE:
        return ["proof_first", "pain_direct"]
    if profile_key == ECOMMERCE_PROFILE:
        return ["pain_direct", "proof_first"]
    if profile_key == KNOWLEDGE_PROFILE:
        return ["proof_first", "process_peek"]
    if profile_key == "shipinhao_knowledge":
        return ["proof_first", "process_peek"]
    return ["pain_direct", "process_peek"]


def _narrative_arc_label(item: str) -> str:
    labels = {
        "hook": "Hook",
        "pain": "痛点",
        "problem": "问题",
        "solution": "方案",
        "feature": "功能",
        "workflow": "流程",
        "proof": "证明",
        "cta": "CTA",
        "use_case": "场景",
        "benefit": "收益",
        "result_preview": "效果预览",
        "step_1": "步骤1",
        "step_2": "步骤2",
        "step_3": "步骤3",
        "recap_cta": "复盘CTA",
        "criteria": "评测维度",
        "test_1": "测试1",
        "test_2": "测试2",
        "tradeoff": "取舍",
        "verdict": "结论",
        "misconception": "误区",
        "explain": "解释",
        "example": "例子",
    }
    return labels.get(item, item)


def _expected_real_evidence(
    profile_data: dict[str, Any],
    blueprint: dict[str, Any],
) -> list[str]:
    evidence = list(profile_data.get("required_evidence") or [])
    recipe = str(blueprint.get("asset_recipe_id") or "")
    if recipe and recipe in REAL_EVIDENCE_ASSET_RECIPES:
        evidence.append(recipe)
    return evidence


def _engine_recommendation(generator: str) -> str:
    if generator == "hyperframes":
        return "HyperFrames:默认主执行器,适合产品说明、Codex 操作、GitHub 页面和短视频动效。"
    if generator == "remotion":
        return (
            "Remotion:opt-in 精密执行器,适合数据图表、复杂转场、overlay "
            "和参数化镜头;启用前需确认 license。"
        )
    if generator == "user-asset":
        return "用户视频素材:直接作为主画面,灵剪只叠字幕/callout/overlay。"
    if generator == "image-gen":
        return "imagegen:只能生成静态参考图,发布级必须转成动态视频。"
    return "阻塞:缺真实动态视频素材或宿主视频生成能力。"


def _path_suffix(path: str) -> str:
    return Path(path).suffix.lower() if path else ""


def _transition_semantic(role: str | None) -> str:
    semantics = {
        "hook": "快速建立视觉锚点并制造继续观看理由。",
        "pain": "把注意力压向混乱、成本或失败风险。",
        "solution": "从混乱收束到可执行流程。",
        "proof": "进入证据和可复核结果,让画面变得可信。",
        "cta": "从证明收束到行动按钮,给用户清晰下一步。",
    }
    return semantics.get(str(role or ""), "服务当前叙事关系,避免装饰性转场。")


def _scene_value(scene: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = scene.get(key)
        if value:
            return str(value)
    return ""


def _transition_family(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("family") or value.get("type") or "")
    if isinstance(value, str):
        return value
    return ""


def _scene_transition_family(scene: dict[str, Any]) -> str:
    family = _transition_family(scene.get("transition_plan") or scene.get("transition"))
    if family:
        return family
    for sheet in _scene_review_sheets(scene):
        family = _transition_family(sheet.get("transition"))
        if family:
            return family
    return ""


def _layout_signature(scene: dict[str, Any]) -> str:
    host_contract = scene.get("host_generation_contract")
    if isinstance(host_contract, dict):
        for key in ("layout_signature", "layout_id", "layout_class"):
            value = host_contract.get(key)
            if value:
                return str(value)
    for key in ("layout_signature", "layout_id", "layout_class", "visual_archetype"):
        value = scene.get(key)
        if value:
            return str(value)
    layout = scene.get("layout_contract")
    if isinstance(layout, dict):
        for key in ("layout_signature", "layout_id", "layout_class", "template_id"):
            value = layout.get(key)
            if value:
                return str(value)
        geometry = _layout_geometry_signature(layout)
        if geometry:
            return geometry
    for sheet in _scene_review_sheets(scene):
        if sheet.get("composition"):
            return str(sheet["composition"])
    return ""


def _evidence_media_ref_count(refs: list[Any]) -> int:
    count = 0
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        raw = str(
            ref.get("media_path")
            or ref.get("evidence_clip_path")
            or ref.get("path")
            or ""
        )
        if Path(raw).suffix.lower() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".mp4",
            ".mov",
            ".m4v",
            ".webm",
        }:
            count += 1
    return count


def _evidence_video_media_ref_count(refs: list[Any]) -> int:
    count = 0
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        raw = str(
            ref.get("media_path")
            or ref.get("evidence_clip_path")
            or ref.get("path")
            or ""
        )
        if Path(raw).suffix.lower() in {
            ".mp4",
            ".mov",
            ".m4v",
            ".webm",
        }:
            count += 1
    return count


def _layout_geometry_signature(layout: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("textRect", "subjectRect", "ctaRect", "quiet_text_zone"):
        rect = layout.get(key)
        if isinstance(rect, dict):
            values = []
            for field in ("x", "y", "w", "h"):
                try:
                    values.append(str(int(float(rect.get(field)))))
                except (TypeError, ValueError):
                    values.append("")
            parts.append(f"{key}:{','.join(values)}")
    safe_bottom = layout.get("safeBottomY")
    if safe_bottom is not None:
        try:
            parts.append(f"safeBottomY:{int(float(safe_bottom))}")
        except (TypeError, ValueError):
            parts.append(f"safeBottomY:{safe_bottom}")
    title_tier = layout.get("title_tier")
    if title_tier:
        parts.append(f"title_tier:{title_tier}")
    return "|".join(parts)


def _motion_rule_ids(scene: dict[str, Any]) -> list[str]:
    direct = scene.get("motion_rule_ids")
    if isinstance(direct, list):
        return [str(item) for item in direct if item]
    board = scene.get("director_board")
    if isinstance(board, dict) and isinstance(board.get("motion_rule_ids"), list):
        return [str(item) for item in board["motion_rule_ids"] if item]
    motion = scene.get("motion_intent") or scene.get("motion_spec") or {}
    if isinstance(motion, dict) and isinstance(motion.get("motion_rule_ids"), list):
        return [str(item) for item in motion["motion_rule_ids"] if item]
    for sheet in _scene_review_sheets(scene):
        secondary = sheet.get("secondary_motion")
        if isinstance(secondary, list):
            return [str(item) for item in secondary if item]
    return []


def _scene_keyframes(scene: dict[str, Any]) -> list[Any]:
    direct = scene.get("keyframes") or scene.get("keyframe_beats")
    if isinstance(direct, list):
        return [item for item in direct if item is not None]
    board = scene.get("director_board")
    if isinstance(board, dict):
        board_keyframes = board.get("keyframes") or board.get("keyframe_beats")
        if isinstance(board_keyframes, list):
            return [item for item in board_keyframes if item is not None]
    for sheet in _scene_review_sheets(scene):
        sheet_keyframes = sheet.get("keyframes") or sheet.get("keyframe_beats")
        if isinstance(sheet_keyframes, list):
            return [item for item in sheet_keyframes if item is not None]
    return []


def _keyframe_time_sec(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("time_sec", "time", "at_sec", "at"):
            parsed = _float_or_none(value.get(key))
            if parsed is not None:
                return parsed
    return _float_or_none(value)


def _keyframe_state_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("state", "description", "visual_state", "action", "beat"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
    if isinstance(value, str):
        return value.strip()
    return ""


def _normalize_keyframe_state(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _scene_duration_sec(scene: dict[str, Any]) -> float | None:
    for key in ("duration_sec", "duration"):
        parsed = _float_or_none(scene.get(key))
        if parsed is not None and parsed > 0:
            return parsed
    return None


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().removesuffix("s").strip()
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _has_adjacent_repeat(values: list[str]) -> bool:
    previous = ""
    for value in values:
        if value and previous and value == previous:
            return True
        previous = value
    return False


def _has_three_consecutive_repeat(values: list[str]) -> bool:
    streak = 0
    previous = ""
    for value in values:
        if value and value == previous:
            streak += 1
        else:
            streak = 1
            previous = value
        if value and streak >= 3:
            return True
    return False


def _scene_has_real_evidence_recipe(scene: dict[str, Any]) -> bool:
    return bool(_real_evidence_recipe_id(scene))


def _real_evidence_recipe_id(scene: dict[str, Any]) -> str:
    recipe_id = str(scene.get("asset_recipe_id") or "")
    if recipe_id in REAL_EVIDENCE_ASSET_RECIPES:
        return recipe_id
    board = scene.get("director_board")
    if isinstance(board, dict):
        board_recipe = str(board.get("asset_recipe_id") or "")
        if board_recipe in REAL_EVIDENCE_ASSET_RECIPES:
            return board_recipe
    return ""


def _is_open_source_video(scenes: list[dict[str, Any]]) -> bool:
    for scene in scenes:
        refs = scene.get("director_knowledge_refs")
        if isinstance(refs, dict) and refs.get("profile") == OPEN_SOURCE_PROFILE:
            return True
        strategy = scene.get("asset_strategy_v2")
        if isinstance(strategy, dict) and strategy.get("profile") == OPEN_SOURCE_PROFILE:
            return True
    return False


def _keyframes(
    duration_sec: float,
    blueprint: dict[str, Any],
    short_text: str,
) -> list[dict[str, Any]]:
    duration = max(float(duration_sec), 0.5)
    middle = round(duration * 0.45, 2)
    end = round(max(duration - 0.35, 0.5), 2)
    return [
        {
            "time_sec": 0.0,
            "state": f"{short_text} 的主视觉入场,建立本镜焦点。",
        },
        {
            "time_sec": middle,
            "state": blueprint["motion_design"],
        },
        {
            "time_sec": end,
            "state": f"{blueprint['transition_out']} 并为下一镜留出清晰收束。",
        },
    ]


def _short_text(value: str, limit: int) -> str:
    normalized = str(value or "").replace("\n", " ").strip()
    if not normalized:
        return "灵剪"
    return normalized[:limit]


def _primary_motion_count(motion: dict[str, Any]) -> int:
    if isinstance(motion.get("primary_motions"), list):
        return len(motion["primary_motions"])
    if isinstance(motion.get("motions"), list):
        return len(motion["motions"])
    if motion.get("max_primary_motions"):
        return 1
    if motion.get("main") or motion.get("main_motion_intent"):
        return 1
    return 0


def _is_opacity_vertical_beat(beat: dict[str, Any]) -> bool:
    props = beat.get("properties") or beat.get("props") or []
    if isinstance(props, str):
        props = [props]
    if not isinstance(props, list):
        return False
    normalized = {str(item).lower() for item in props}
    return normalized.issubset({"opacity", "y", "translatey", "vertical"}) and bool(normalized)


def _caption_quiet_zone(scene: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any] | None:
    for sheet in _scene_review_sheets(scene):
        region = sheet.get("caption_region")
        if isinstance(region, dict) and isinstance(region.get("quiet_text_zone"), dict):
            return region["quiet_text_zone"]
    zone = contract.get("quiet_text_zone")
    return zone if isinstance(zone, dict) else None


def _caption_contract(scene: dict[str, Any]) -> dict[str, Any] | None:
    contract = scene.get("caption_contract")
    if isinstance(contract, dict):
        return contract
    for sheet in _scene_review_sheets(scene):
        if isinstance(sheet.get("caption_contract"), dict):
            return sheet["caption_contract"]
    board = scene.get("director_board")
    if isinstance(board, dict) and isinstance(board.get("subtitle_strategy"), dict):
        return board["subtitle_strategy"]
    return None


def _scene_review_sheets(scene: dict[str, Any]) -> list[dict[str, Any]]:
    sheets: list[dict[str, Any]] = []
    for key in ("director_review_sheet_v2", "director_review_sheet"):
        sheet = scene.get(key)
        if isinstance(sheet, dict):
            sheets.append(sheet)
    return sheets


def _scene_cta_regions(scene: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for key in ("ctaRect", "cta_rect", "buttonRect", "button_rect"):
        value = contract.get(key)
        if isinstance(value, dict):
            regions.append(value)
    for sheet in _scene_review_sheets(scene):
        for key in ("cta_region", "ctaRegion", "button_region", "buttonRegion"):
            value = sheet.get(key)
            if isinstance(value, dict):
                regions.append(value)
    return regions


def _scene_requires_cta_region(scene: dict[str, Any]) -> bool:
    markers: list[str] = []
    for key in (
        "role",
        "template_id",
        "blueprint_id",
        "visual_archetype",
        "asset_recipe_id",
        "material_key",
    ):
        value = scene.get(key)
        if value:
            markers.append(str(value).lower())
    for sheet in _scene_review_sheets(scene):
        for key in ("scene_goal", "visual_content", "visual_elements", "qa_checkpoints"):
            value = sheet.get(key)
            if value:
                markers.append(str(value).lower())
    marker_text = " ".join(markers)
    return any(token in marker_text for token in ("cta", "call to action", "行动", "star"))


def _caption_declares_bottom_safe_area(contract: dict[str, Any]) -> bool:
    position = str(contract.get("position") or "").lower()
    rule_id = str(contract.get("rule_id") or "").lower()
    return "底部" in position or "bottom_safe_area" in position or "bottom_safe_area" in rule_id


def _caption_zone_too_high(zone: Any, safe_bottom_y: Any) -> bool:
    if not isinstance(zone, dict):
        return False
    try:
        y = float(zone["y"])
        height = float(zone["h"])
        safe_y = float(safe_bottom_y)
    except (KeyError, TypeError, ValueError):
        return False
    if height <= 0 or safe_y <= 0:
        return True
    return y < max(0.0, safe_y - height)


def _rects_overlap(left: Any, right: Any) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    try:
        lx, ly, lw, lh = (float(left[key]) for key in ("x", "y", "w", "h"))
        rx, ry, rw, rh = (float(right[key]) for key in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    return lx < rx + rw and lx + lw > rx and ly < ry + rh and ly + lh > ry
