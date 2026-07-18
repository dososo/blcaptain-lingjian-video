from packages.core.director_contract import (
    asset_diagnosis,
    asset_diagnosis_summary,
    director_board,
    director_diversity_findings,
    director_knowledge_base_v1,
    director_review_sheet_markdown,
    director_review_sheet_v2,
    director_route_findings,
    director_route_policy,
    hook_library,
    host_generation_contract_findings,
    infer_content_profile,
    layout_contract,
    layout_quality_findings,
    motion_quality_findings,
    paid_engine_notice,
    profile_preset,
    remotion_license_notice,
    scene_director_contract,
    script_generation_contract,
    self_check_visual_scenes,
    style_lock,
    visual_brief,
)


def test_style_lock_is_deterministic_and_contains_design_rules():
    first = style_lock("tech_minimal")
    second = style_lock("tech_minimal")

    assert first == second
    assert first["palette"]
    assert "motion_language" in first
    assert any("禁止" in rule for rule in first["decoration_rules"])


def test_profile_sets_multiple_runtime_parameters():
    profile = profile_preset("xiaohongshu_life")

    assert profile["platform"] == "xiaohongshu"
    assert profile["ratio"] == "3:4"
    assert profile["duration_sec"] == 45
    assert profile["subtitle_limit"] == 14
    assert profile["bgm_strategy"]


def test_open_source_profile_is_inferred_from_user_goal_text():
    profile = infer_content_profile(
        text="我要做一条灵剪是什么的开源项目介绍,让观众 star GitHub 项目。",
        type_="video",
        platform="douyin",
        profile="douyin_product",
    )

    assert profile == "open_source_project_intro"
    preset = profile_preset(profile)
    assert "GitHub repo" in preset["required_evidence"]
    assert "全片抽象模板换字" in preset["forbidden"]


def test_content_profiles_cover_core_creator_types():
    knowledge = director_knowledge_base_v1()
    profiles = knowledge["profiles"]

    assert "open_source_project_intro" in profiles
    assert "product_intro" in profiles
    assert "tutorial_guide" in profiles
    assert "review_comparison" in profiles
    assert "ecommerce_sales" in profiles
    assert "knowledge_explainer" in profiles
    assert "逐步操作录屏" in profiles["tutorial_guide"]["required_evidence"]
    assert "测试过程" in profiles["review_comparison"]["required_evidence"]
    assert "商品实拍视频" in profiles["ecommerce_sales"]["required_evidence"]


def test_infer_content_profile_routes_common_creator_goals():
    cases = {
        "帮我做一个软件产品介绍,讲清它能做什么和解决什么问题": "product_intro",
        "做一条三步上手教程,教小白怎么用这个功能": "tutorial_guide",
        "做一条真实测评视频,对比优缺点和值不值得买": "review_comparison",
        "做一条带货短视频,突出商品卖点并引导下单": "ecommerce_sales",
        "做一条知识科普,解释这个概念为什么重要": "knowledge_explainer",
    }

    for text, expected in cases.items():
        assert (
            infer_content_profile(
                text=text,
                type_="video",
                platform="douyin",
                profile="douyin_product",
            )
            == expected
        )


def test_script_generation_contract_includes_hook_library_and_honesty():
    contract = script_generation_contract(
        type_="product",
        platform="douyin",
        language="zh-CN",
        ratio="9:16",
        duration=45,
        style="bold_news",
        profile="douyin_product",
    )

    assert contract["style"] == "bold_news"
    assert contract["profile"] == "douyin_product"
    assert "反常识收益" in contract["hook_library"]
    assert contract["script_rules"]["completion_oriented"] is True
    assert "不承诺爆款" in contract["script_rules"]["honesty"]


def test_script_generation_contract_uses_profile_narrative_arc():
    contract = script_generation_contract(
        type_="tutorial",
        platform="douyin",
        language="zh-CN",
        ratio="9:16",
        duration=60,
        style="clean_product",
        profile="tutorial_guide",
    )

    assert contract["profile"] == "tutorial_guide"
    assert contract["script_rules"]["narrative_arc"] == [
        "hook",
        "result_preview",
        "step_1",
        "step_2",
        "step_3",
        "recap_cta",
    ]
    assert "最终效果先看" in contract["hook_library"]
    assert "逐步操作录屏" in contract["profile_preset"]["required_evidence"]


def test_director_knowledge_base_v1_contains_publish_quality_rules():
    knowledge = director_knowledge_base_v1()

    assert knowledge["version"] == "v1"
    assert "open_source_project_intro" in knowledge["profiles"]
    assert "bottom_safe_area_cjk" in knowledge["knowledge"]["caption_rules"]
    assert "static_as_video" in knowledge["knowledge"]["forbidden_items"]


def test_scene_contract_locks_non_replaceable_fields_and_layout():
    contract = scene_director_contract(
        scene_id="s1",
        index=1,
        role="hook",
        ratio="9:16",
        style="clean_product",
    )

    assert contract["template_id"] == "hook_codex_prompt"
    assert contract["blueprint_id"] == "hook_codex_prompt"
    assert contract["visual_archetype"] == "codex_prompt_capture"
    assert contract["transition_plan"]["family"]
    assert contract["motion_intent"]["motion_rule_ids"]
    assert contract["compiler_policy"]["invent_geometry"] is False
    assert "layout_contract" in contract["non_replaceable_fields"]
    assert "transition_plan" in contract["non_replaceable_fields"]
    assert contract["layout_contract"]["safeBottomY"] > 0
    assert contract["develop_full_duration"] is True
    assert contract["inherits_design"] is True


def test_layout_contract_uses_landscape_regions_for_16x9():
    contract = layout_contract(1, "16:9", "hook")

    assert contract["textRect"]["w"] > contract["textRect"]["h"]
    assert contract["subjectRect"]["x"] > contract["textRect"]["x"]
    assert contract["subjectRect"]["y"] < contract["quiet_text_zone"]["y"]
    assert contract["subjectRect"]["y"] + contract["subjectRect"]["h"] < contract[
        "quiet_text_zone"
    ]["y"]
    assert contract["safeBottomY"] == 1000


def test_director_board_contains_publishable_scene_requirements():
    board = director_board(
        scene_id="s1",
        index=1,
        role="hook",
        narration_text="一句话开始做视频。",
        on_screen_text="一句话做视频",
        duration_sec=3.5,
        generator="hyperframes",
        expected_asset_path="assets/scenes/s1.mp4",
        ratio="9:16",
        style="clean_product",
        profile="douyin_product",
        platform="douyin",
    )

    assert board["scene_goal"]
    assert board["blueprint_id"] == "hook_codex_prompt"
    assert board["motion_rule_ids"]
    assert board["transition"]["family"]
    assert board["asset_strategy"]
    assert board["composition"]
    assert board["motion_design"]
    assert len(board["keyframes"]) == 3
    assert board["subtitle_strategy"]["position"] == "底部安全区"
    assert board["color_mood"]["palette"]
    assert "静态图片停留几秒" in board["forbidden_elements"]
    assert any("相邻镜头" in item for item in board["acceptance_checks"])


def test_director_route_policy_explains_engine_choice_and_assets():
    route = director_route_policy(
        generator="remotion",
        profile="open_source_project_intro",
        platform="douyin",
        blueprint_id="proof_ffprobe_dashboard",
        expected_asset_path="assets/scenes/s4.mp4",
        asset_path=None,
    )

    assert route["engine_policy"]["selected_engine"] == "remotion"
    assert route["engine_policy"]["remotion_license_required"] is True
    assert route["engine_policy"]["remotion_license_confirmed"] is False
    assert "license" in route["route_reason"].lower()
    assert "ffprobe_terminal_capture" in route["expected_real_evidence"]
    assert route["director_knowledge_refs"]["caption_rule"] == "bottom_safe_area_cjk"


def test_asset_strategy_records_stock_image_user_consent_boundary():
    route = director_route_policy(
        generator="hyperframes",
        profile="knowledge_explainer",
        platform="douyin",
        blueprint_id="concept_diagram",
        expected_asset_path="assets/scenes/s1.mp4",
        asset_path=None,
    )

    policy = route["asset_strategy_v2"]["stock_image_policy"]
    assert policy["allowed_when"] == (
        "用户未提供自有图/截图,且这一镜确实需要配图或视觉设计层。"
    )
    assert policy["requires_user_consent"] is True
    assert policy["not_evidence"] is True
    assert policy["does_not_satisfy_real_evidence"] is True
    assert "sourceUrl" in policy["license_fields_required"]
    assert "国内 CC0" in policy["source_priority"][1]
    assert any("透明背景" in item for item in policy["processing_requirements"])


def test_director_review_sheet_markdown_shows_stock_image_policy():
    route = director_route_policy(
        generator="hyperframes",
        profile="knowledge_explainer",
        platform="douyin",
        blueprint_id="concept_diagram",
        expected_asset_path="assets/scenes/s1.mp4",
        asset_path=None,
    )
    sheet = director_review_sheet_v2(
        scene_id="s1",
        index=1,
        role="hook",
        narration_text="没有截图时先确认素材策略。",
        on_screen_text="缺图先问",
        duration_sec=3.0,
        generator="hyperframes",
        expected_asset_path="assets/scenes/s1.mp4",
        asset_path=None,
        ratio="9:16",
        style="clean_product",
        profile="knowledge_explainer",
        platform="douyin",
        contract={"director_route": route},
    )
    markdown = director_review_sheet_markdown(
        {
            "style": "clean_product",
            "profile": "knowledge_explainer",
            "ratio": "9:16",
            "director_review_sheet_v2": {"scenes": [sheet]},
        }
    )

    assert sheet["stock_image_policy"]["requires_user_consent"] is True
    assert "免费图库策略" in markdown
    assert "需先征询用户" in markdown
    assert "不能替代真实动态 evidence" in markdown


def test_director_route_findings_require_policy_fields_for_director_scenes():
    findings = director_route_findings(
        {
            "scene_id": "s1",
            "blueprint_id": "hook_codex_prompt",
            "layout_contract": {"safeBottomY": 1510},
        }
    )

    assert findings[0]["code"] == "RELEASE_VISUAL_DIRECTOR_ROUTE_MISSING"


def test_director_route_findings_block_generator_engine_mismatch():
    route = director_route_policy(
        generator="hyperframes",
        profile="open_source_project_intro",
        platform="douyin",
        blueprint_id="hook_codex_prompt",
        expected_asset_path="assets/scenes/s1.mp4",
        asset_path=None,
    )
    route["engine_policy"]["selected_engine"] = "remotion"

    findings = director_route_findings(
        {"scene_id": "s1", "blueprint_id": "hook_codex_prompt", **route}
    )

    assert any(
        finding["code"] == "RELEASE_VISUAL_DIRECTOR_ROUTE_MISMATCH"
        for finding in findings
    )


def test_director_route_findings_allow_matching_user_video_route():
    route = director_route_policy(
        generator="user-asset",
        profile="open_source_project_intro",
        platform="douyin",
        blueprint_id="hook_codex_prompt",
        expected_asset_path="assets/scenes/s1.mp4",
        asset_path="assets/scenes/s1.mp4",
    )

    findings = director_route_findings(
        {
            "scene_id": "s1",
            "generator": "user-asset",
            "asset_path": "assets/scenes/s1.mp4",
            "blueprint_id": "hook_codex_prompt",
            **route,
        }
    )

    assert "RELEASE_VISUAL_DIRECTOR_ROUTE_MISMATCH" not in {
        finding["code"] for finding in findings
    }


def test_director_route_findings_require_remotion_license_confirmation():
    route = director_route_policy(
        generator="remotion",
        profile="open_source_project_intro",
        platform="douyin",
        blueprint_id="proof_ffprobe_dashboard",
        expected_asset_path="assets/scenes/s4.mp4",
        asset_path=None,
    )

    findings = director_route_findings(
        {"scene_id": "s1", "blueprint_id": "proof_ffprobe_dashboard", **route}
    )

    assert any(
        finding["code"] == "RELEASE_VISUAL_REMOTION_LICENSE_NOT_CONFIRMED"
        for finding in findings
    )


def test_director_route_findings_allow_confirmed_remotion_license():
    route = director_route_policy(
        generator="remotion",
        profile="open_source_project_intro",
        platform="douyin",
        blueprint_id="proof_ffprobe_dashboard",
        expected_asset_path="assets/scenes/s4.mp4",
        asset_path=None,
    )
    route["engine_policy"]["license_confirmation"] = {"status": "confirmed"}

    findings = director_route_findings(
        {"scene_id": "s1", "blueprint_id": "proof_ffprobe_dashboard", **route}
    )

    assert "RELEASE_VISUAL_REMOTION_LICENSE_NOT_CONFIRMED" not in {
        finding["code"] for finding in findings
    }


def test_asset_diagnosis_marks_static_images_as_reference_only():
    diagnosis = asset_diagnosis(
        generator="user-asset",
        expected_asset_path="assets/scenes/s1.png",
        asset_path="assets/scenes/s1.png",
    )

    assert diagnosis["publish_grade_visual"] is False
    assert diagnosis["asset_kind"] == "static_image"
    assert "mp4/mov/m4v" in diagnosis["next_action_zh"]


def test_director_review_sheet_v2_contains_full_user_review_fields():
    sheet = director_review_sheet_v2(
        scene_id="s1",
        index=1,
        role="hook",
        narration_text="一句话开始做视频。",
        on_screen_text="一句话做视频",
        duration_sec=3.0,
        generator="fallback_solid",
        expected_asset_path=None,
        asset_path=None,
        ratio="9:16",
        style="clean_product",
        profile="douyin_product",
        platform="douyin",
    )

    required_keys = {
        "scene_id",
        "narrative_function",
        "narration_text",
        "screen_text",
        "visual_content",
        "asset_source",
        "asset_status",
        "asset_gap",
        "engine_recommendation",
        "subject_region",
        "caption_region",
        "mask_avoidance_rules",
        "composition",
        "visual_elements",
        "color_mood",
        "primary_motion",
        "secondary_motion",
        "transition",
        "keyframes",
        "entrance_animation",
        "exit_animation",
        "bgm",
        "sfx_points",
        "subtitle_split",
        "subtitle_position_size",
        "forbidden_items",
        "qa_checkpoints",
    }
    assert required_keys.issubset(sheet)
    assert sheet["asset_status"]["publish_grade_visual"] is False
    assert "请提供" in sheet["asset_gap"]
    assert "底部安全区" in str(sheet["caption_region"])


def test_asset_diagnosis_summary_returns_single_next_action_for_user():
    summary = asset_diagnosis_summary(
        [
            {
                "scene_id": "s1",
                "asset_diagnosis": asset_diagnosis(
                    generator="fallback_solid",
                    expected_asset_path=None,
                    asset_path=None,
                ),
            }
        ]
    )

    assert summary["non_publish_grade_count"] == 1
    assert summary["single_next_action_zh"].startswith("请提供")


def test_asset_diagnosis_summary_uses_review_sheet_v2_asset_status():
    summary = asset_diagnosis_summary(
        [
            {
                "scene_id": "s1",
                "director_review_sheet_v2": {
                    "asset_status": {
                        "asset_status": "blocked_missing_video_asset",
                        "publish_grade_visual": False,
                        "next_action_zh": "请提供第 1 镜真实动态视频素材。",
                    }
                },
            }
        ]
    )

    assert summary["non_publish_grade_count"] == 1
    assert summary["blockers"][0]["asset_status"] == "blocked_missing_video_asset"
    assert summary["single_next_action_zh"] == "请提供第 1 镜真实动态视频素材。"


def test_scene_contract_rotates_blueprints_for_repeated_roles():
    first = scene_director_contract(
        scene_id="s1",
        index=1,
        role="hook",
        ratio="9:16",
        style="clean_product",
    )
    second = scene_director_contract(
        scene_id="s2",
        index=2,
        role="hook",
        ratio="9:16",
        style="clean_product",
    )

    assert first["blueprint_id"] != second["blueprint_id"]
    assert first["transition_plan"]["family"] != second["transition_plan"]["family"]


def test_director_diversity_flags_repeated_blueprints_and_transitions():
    findings = director_diversity_findings(
        [
            {
                "scene_id": "s1",
                "blueprint_id": "same",
                "transition_plan": {"family": "same-transition"},
                "material_key": "same-material",
                "motion_rule_ids": ["a"],
            },
            {
                "scene_id": "s2",
                "blueprint_id": "same",
                "transition_plan": {"family": "same-transition"},
                "material_key": "same-material",
                "motion_rule_ids": ["a"],
            },
            {
                "scene_id": "s3",
                "blueprint_id": "same",
                "transition_plan": {"family": "different-transition"},
                "material_key": "same-material",
                "motion_rule_ids": ["a"],
            },
        ]
    )

    codes = {finding["code"] for finding in findings}
    assert "RELEASE_VISUAL_BLUEPRINT_REPEATED" in codes
    assert "RELEASE_VISUAL_BLUEPRINT_VARIETY_TOO_LOW" in codes
    assert "RELEASE_VISUAL_TRANSITION_REPEATED" in codes
    assert "RELEASE_VISUAL_MATERIAL_TOO_UNIFORM" in codes
    assert "RELEASE_VISUAL_MOTION_VOCAB_TOO_THIN" in codes


def test_director_diversity_flags_repeated_execution_layout_signature():
    findings = director_diversity_findings(
        [
            {
                "scene_id": "s1",
                "blueprint_id": "hook_a",
                "transition_plan": {"family": "a"},
                "material_key": "material-a",
                "motion_rule_ids": ["a", "b"],
                "host_generation_contract": {"layout_signature": "same-layout"},
            },
            {
                "scene_id": "s2",
                "blueprint_id": "pain_b",
                "transition_plan": {"family": "b"},
                "material_key": "material-b",
                "motion_rule_ids": ["c", "d"],
                "host_generation_contract": {"layout_signature": "same-layout"},
            },
            {
                "scene_id": "s3",
                "blueprint_id": "proof_c",
                "transition_plan": {"family": "c"},
                "material_key": "material-c",
                "motion_rule_ids": ["e", "f"],
                "host_generation_contract": {"layout_signature": "same-layout"},
            },
        ]
    )

    codes = {finding["code"] for finding in findings}
    assert "RELEASE_VISUAL_LAYOUT_TOO_UNIFORM" in codes


def test_director_diversity_uses_review_sheet_v2_composition_as_layout_signature():
    findings = director_diversity_findings(
        [
            {
                "scene_id": "s1",
                "blueprint_id": "hook_a",
                "transition_plan": {"family": "a"},
                "material_key": "material-a",
                "motion_rule_ids": ["a", "b"],
                "director_review_sheet_v2": {"composition": "同一中心卡片构图"},
            },
            {
                "scene_id": "s2",
                "blueprint_id": "pain_b",
                "transition_plan": {"family": "b"},
                "material_key": "material-b",
                "motion_rule_ids": ["c", "d"],
                "director_review_sheet_v2": {"composition": "同一中心卡片构图"},
            },
            {
                "scene_id": "s3",
                "blueprint_id": "proof_c",
                "transition_plan": {"family": "c"},
                "material_key": "material-c",
                "motion_rule_ids": ["e", "f"],
                "director_review_sheet_v2": {"composition": "同一中心卡片构图"},
            },
        ]
    )

    codes = {finding["code"] for finding in findings}
    assert "RELEASE_VISUAL_LAYOUT_TOO_UNIFORM" in codes


def test_director_diversity_checks_review_sheet_v2_only_scenes():
    findings = director_diversity_findings(
        [
            {
                "scene_id": "s1",
                "director_review_sheet_v2": {"composition": "同一中心卡片构图"},
            },
            {
                "scene_id": "s2",
                "director_review_sheet_v2": {"composition": "同一中心卡片构图"},
            },
            {
                "scene_id": "s3",
                "director_review_sheet_v2": {"composition": "同一中心卡片构图"},
            },
        ]
    )

    codes = {finding["code"] for finding in findings}
    assert "RELEASE_VISUAL_LAYOUT_TOO_UNIFORM" in codes


def test_director_diversity_uses_review_sheet_v2_transition_family():
    findings = director_diversity_findings(
        [
            {
                "scene_id": "s1",
                "director_review_sheet_v2": {
                    "transition": {"family": "same-wipe"},
                    "secondary_motion": ["scan-line-pass", "cursor-click-ripple"],
                },
            },
            {
                "scene_id": "s2",
                "director_review_sheet_v2": {
                    "transition": {"family": "same-wipe"},
                    "secondary_motion": ["counting-dynamic-scale", "stat-bars-and-fills"],
                },
            },
        ]
    )

    codes = {finding["code"] for finding in findings}
    assert "RELEASE_VISUAL_TRANSITION_REPEATED" in codes


def test_director_diversity_uses_review_sheet_v2_secondary_motion_vocab():
    findings = director_diversity_findings(
        [
            {
                "scene_id": "s1",
                "director_review_sheet_v2": {
                    "transition": {"family": "a"},
                    "secondary_motion": ["scan-line-pass", "cursor-click-ripple"],
                },
            },
            {
                "scene_id": "s2",
                "director_review_sheet_v2": {
                    "transition": {"family": "b"},
                    "secondary_motion": ["counting-dynamic-scale", "stat-bars-and-fills"],
                },
            },
            {
                "scene_id": "s3",
                "director_review_sheet_v2": {
                    "transition": {"family": "c"},
                    "secondary_motion": ["3d-page-scroll", "viewport-change"],
                },
            },
        ]
    )

    codes = {finding["code"] for finding in findings}
    assert "RELEASE_VISUAL_MOTION_VOCAB_TOO_THIN" not in codes


def test_director_diversity_flags_repeated_layout_contract_geometry():
    layout = layout_contract(2, "9:16", "pain")
    findings = director_diversity_findings(
        [
            {
                "scene_id": "s1",
                "blueprint_id": "hook_a",
                "transition_plan": {"family": "a"},
                "material_key": "material-a",
                "motion_rule_ids": ["a", "b"],
                "layout_contract": layout,
            },
            {
                "scene_id": "s2",
                "blueprint_id": "pain_b",
                "transition_plan": {"family": "b"},
                "material_key": "material-b",
                "motion_rule_ids": ["c", "d"],
                "layout_contract": layout,
            },
            {
                "scene_id": "s3",
                "blueprint_id": "proof_c",
                "transition_plan": {"family": "c"},
                "material_key": "material-c",
                "motion_rule_ids": ["e", "f"],
                "layout_contract": layout,
            },
        ]
    )

    codes = {finding["code"] for finding in findings}
    assert "RELEASE_VISUAL_LAYOUT_TOO_UNIFORM" in codes


def test_director_diversity_passes_varied_director_scenes():
    findings = director_diversity_findings(
        [
            {
                "scene_id": "s1",
                "blueprint_id": "hook_codex_prompt",
                "transition_plan": {"family": "ticker-crash"},
                "material_key": "prompt_terminal_surface",
                "motion_rule_ids": ["discrete-text-sequence", "cursor-click-ripple"],
            },
            {
                "scene_id": "s2",
                "blueprint_id": "pain_dataviz_cost",
                "transition_plan": {"family": "focus-pull"},
                "material_key": "dark_data_panel",
                "motion_rule_ids": ["counting-dynamic-scale", "stat-bars-and-fills"],
            },
            {
                "scene_id": "s3",
                "blueprint_id": "solution_cursor_demo",
                "transition_plan": {"family": "clean-wipe"},
                "material_key": "product_window",
                "motion_rule_ids": ["3d-page-scroll", "cursor-click-ripple"],
            },
        ]
    )

    assert findings == []


def test_open_source_intro_requires_multiple_real_evidence_recipes():
    scenes = [
        {
            "scene_id": "s1",
            "blueprint_id": "proof_qa_evidence_wall",
            "transition_plan": {"family": "scan-focus"},
            "material_key": "evidence_wall",
            "motion_rule_ids": ["scan-line-pass", "checklist-stroke"],
            "asset_recipe_id": "qa_report_capture",
            "director_knowledge_refs": {"profile": "open_source_project_intro"},
        },
        {
            "scene_id": "s2",
            "blueprint_id": "proof_qa_evidence_wall_alt",
            "transition_plan": {"family": "clean-wipe"},
            "material_key": "terminal_panel",
            "motion_rule_ids": ["terminal-line-reveal", "scan-line-pass"],
            "asset_recipe_id": "qa_report_capture",
            "director_knowledge_refs": {"profile": "open_source_project_intro"},
        },
    ]

    codes = {finding["code"] for finding in director_diversity_findings(scenes)}

    assert "RELEASE_VISUAL_EVIDENCE_DENSITY_TOO_LOW" in codes


def test_open_source_intro_passes_with_three_evidence_recipe_types():
    scenes = [
        {
            "scene_id": "s1",
            "blueprint_id": "hook_codex_prompt",
            "transition_plan": {"family": "ticker-crash"},
            "material_key": "prompt_terminal_surface",
            "motion_rule_ids": ["discrete-text-sequence", "cursor-click-ripple"],
            "asset_recipe_id": "codex_operation_capture",
            "director_knowledge_refs": {"profile": "open_source_project_intro"},
        },
        {
            "scene_id": "s2",
            "blueprint_id": "solution_readme_scroll",
            "transition_plan": {"family": "clean-wipe"},
            "material_key": "readme_surface",
            "motion_rule_ids": ["3d-page-scroll", "viewport-change"],
            "asset_recipe_id": "readme_install_capture",
            "director_knowledge_refs": {"profile": "open_source_project_intro"},
        },
        {
            "scene_id": "s3",
            "blueprint_id": "proof_qa_evidence_wall",
            "transition_plan": {"family": "scan-focus"},
            "material_key": "evidence_wall",
            "motion_rule_ids": ["scan-line-pass", "checklist-stroke"],
            "asset_recipe_id": "qa_report_capture",
            "director_knowledge_refs": {"profile": "open_source_project_intro"},
        },
    ]

    codes = {finding["code"] for finding in director_diversity_findings(scenes)}

    assert "RELEASE_VISUAL_EVIDENCE_DENSITY_TOO_LOW" not in codes


def test_director_board_keeps_readable_short_visual_text():
    board = director_board(
        scene_id="s3",
        index=3,
        role="solution",
        narration_text="灵剪把它拆成三步。",
        on_screen_text="① 脚本  ② 配音  ③ 画面",
        duration_sec=6.0,
        generator="hyperframes",
        expected_asset_path="assets/scenes/s3.mp4",
        ratio="9:16",
        style="clean_product",
        profile="douyin_product",
        platform="douyin",
    )

    assert "① 脚本  ② 配音  ③ 画面" in board["required_elements"]


def test_visual_brief_carries_deterministic_rules_and_profile():
    brief = visual_brief(
        ratio="16:9",
        style="warm_lifestyle",
        profile="douyin_product",
        platform="douyin_xiaohongshu",
    )

    assert "禁止 Date.now/未播种 random" in brief["deterministic_rules"]
    assert brief["subtitle_policy"] == "口播全文只由灵剪底部字幕承载。"
    assert brief["profile"]["ratio"] == "16:9"
    assert brief["profile"]["platform"] == "douyin_xiaohongshu"


def test_motion_quality_flags_too_many_motions_and_weak_beats():
    findings = motion_quality_findings(
        {
            "motion_intent": {
                "primary_motions": ["pan", "zoom", "rotate"],
                "beats": [
                    {"properties": ["opacity", "translateY"]},
                    {"properties": ["opacity", "y"]},
                ],
            }
        }
    )

    codes = {item["code"] for item in findings}
    assert "RELEASE_VISUAL_TOO_MANY_PRIMARY_MOTIONS" in codes
    assert "RELEASE_VISUAL_MOTION_TOO_WEAK" in codes


def test_motion_quality_requires_director_keyframes_for_review_sheet_v2():
    findings = motion_quality_findings(
        {
            "director_review_sheet_v2": {
                "visual_content": "Codex 对话和 GitHub README 双栏展示。",
                "keyframes": [
                    {"time_sec": 0.0, "state": "Codex 对话窗口入场。"},
                    {"time_sec": 1.5, "state": "GitHub README 证据卡展开。"},
                ],
            }
        }
    )

    codes = {item["code"] for item in findings}
    assert "RELEASE_VISUAL_KEYFRAMES_INSUFFICIENT" in codes


def test_motion_quality_accepts_three_review_sheet_v2_keyframes():
    findings = motion_quality_findings(
        {
            "director_review_sheet_v2": {
                "visual_content": "Codex 对话和 GitHub README 双栏展示。",
                "keyframes": [
                    {"time_sec": 0.0, "state": "Codex 对话窗口入场。"},
                    {"time_sec": 1.5, "state": "GitHub README 证据卡展开。"},
                    {"time_sec": 3.0, "state": "Star CTA 聚焦收束。"},
                ],
            }
        }
    )

    codes = {item["code"] for item in findings}
    assert "RELEASE_VISUAL_KEYFRAMES_INSUFFICIENT" not in codes


def test_motion_quality_flags_keyframes_not_covering_duration():
    findings = motion_quality_findings(
        {
            "duration_sec": 6.0,
            "director_review_sheet_v2": {
                "visual_content": "Codex 对话和 GitHub README 双栏展示。",
                "keyframes": [
                    {"time_sec": 0.0, "state": "Codex 对话窗口入场。"},
                    {"time_sec": 1.0, "state": "GitHub README 证据卡展开。"},
                    {"time_sec": 2.0, "state": "Star CTA 过早出现。"},
                ],
            },
        }
    )

    codes = {item["code"] for item in findings}
    assert "RELEASE_VISUAL_KEYFRAMES_DO_NOT_COVER_DURATION" in codes


def test_motion_quality_accepts_keyframes_covering_duration():
    findings = motion_quality_findings(
        {
            "duration_sec": 6.0,
            "director_review_sheet_v2": {
                "visual_content": "Codex 对话和 GitHub README 双栏展示。",
                "keyframes": [
                    {"time_sec": 0.0, "state": "Codex 对话窗口入场。"},
                    {"time_sec": 3.0, "state": "GitHub README 证据卡展开。"},
                    {"time_sec": 5.5, "state": "Star CTA 聚焦收束。"},
                ],
            },
        }
    )

    codes = {item["code"] for item in findings}
    assert "RELEASE_VISUAL_KEYFRAMES_DO_NOT_COVER_DURATION" not in codes
    assert "RELEASE_VISUAL_KEYFRAMES_MISSING_OPENING_BEAT" not in codes
    assert "RELEASE_VISUAL_KEYFRAMES_MISSING_MIDDLE_BEAT" not in codes
    assert "RELEASE_VISUAL_KEYFRAMES_STATE_MISSING" not in codes
    assert "RELEASE_VISUAL_KEYFRAMES_STATE_REPEATED" not in codes


def test_motion_quality_flags_missing_opening_keyframe():
    findings = motion_quality_findings(
        {
            "duration_sec": 6.0,
            "director_review_sheet_v2": {
                "visual_content": "Codex 对话和 GitHub README 双栏展示。",
                "keyframes": [
                    {"time_sec": 1.5, "state": "Codex 对话窗口才开始入场。"},
                    {"time_sec": 3.0, "state": "GitHub README 证据卡展开。"},
                    {"time_sec": 5.5, "state": "Star CTA 聚焦收束。"},
                ],
            },
        }
    )

    codes = {item["code"] for item in findings}
    assert "RELEASE_VISUAL_KEYFRAMES_MISSING_OPENING_BEAT" in codes


def test_motion_quality_flags_missing_middle_keyframe():
    findings = motion_quality_findings(
        {
            "duration_sec": 6.0,
            "director_review_sheet_v2": {
                "visual_content": "Codex 对话和 GitHub README 双栏展示。",
                "keyframes": [
                    {"time_sec": 0.0, "state": "Codex 对话窗口入场。"},
                    {"time_sec": 1.0, "state": "GitHub README 证据卡过早展开。"},
                    {"time_sec": 5.5, "state": "Star CTA 聚焦收束。"},
                ],
            },
        }
    )

    codes = {item["code"] for item in findings}
    assert "RELEASE_VISUAL_KEYFRAMES_MISSING_MIDDLE_BEAT" in codes


def test_motion_quality_flags_keyframes_without_visual_state():
    findings = motion_quality_findings(
        {
            "duration_sec": 6.0,
            "director_review_sheet_v2": {
                "visual_content": "Codex 对话和 GitHub README 双栏展示。",
                "keyframes": [
                    {"time_sec": 0.0},
                    {"time_sec": 3.0},
                    {"time_sec": 5.5},
                ],
            },
        }
    )

    codes = {item["code"] for item in findings}
    assert "RELEASE_VISUAL_KEYFRAMES_STATE_MISSING" in codes


def test_motion_quality_flags_repeated_keyframe_states():
    findings = motion_quality_findings(
        {
            "duration_sec": 6.0,
            "director_review_sheet_v2": {
                "visual_content": "Codex 对话和 GitHub README 双栏展示。",
                "keyframes": [
                    {"time_sec": 0.0, "state": "同一模板面板停留。"},
                    {"time_sec": 3.0, "state": "同一模板面板停留。"},
                    {"time_sec": 5.5, "state": "同一模板面板停留。"},
                ],
            },
        }
    )

    codes = {item["code"] for item in findings}
    assert "RELEASE_VISUAL_KEYFRAMES_STATE_REPEATED" in codes


def test_layout_quality_flags_missing_and_conflicting_contracts():
    missing = layout_quality_findings({})
    conflict = layout_quality_findings(
        {
            "layout_contract": {
                "textRect": {"x": 0, "y": 0, "w": 100, "h": 100},
                "subjectRect": {"x": 0, "y": 100, "w": 100, "h": 100},
                "quiet_text_zone": {"x": 0, "y": 100, "w": 100, "h": 100},
                "safeBottomY": 150,
                "title_tier": "scene",
            }
        }
    )

    assert missing[0]["code"] == "RELEASE_VISUAL_LAYOUT_CONTRACT_MISSING"
    assert conflict[0]["code"] == "RELEASE_VISUAL_LAYOUT_CONFLICT"


def test_layout_quality_flags_caption_safe_area_and_subject_overlap():
    contract = scene_director_contract(
        scene_id="s1",
        index=1,
        role="hook",
        ratio="9:16",
        style="clean_product",
    )["layout_contract"]

    valid = layout_quality_findings(
        {
            "layout_contract": contract,
            "caption_contract": {
                "rule_id": "bottom_safe_area_cjk",
                "position": "底部安全区",
                "avoid_subject_and_cta": True,
            },
        }
    )
    bad_caption_contract = layout_quality_findings(
        {
            "layout_contract": contract,
            "caption_contract": {
                "rule_id": "center_caption",
                "position": "画面中部",
                "avoid_subject_and_cta": False,
            },
        }
    )
    too_high_contract = dict(contract)
    too_high_contract["quiet_text_zone"] = {"x": 0, "y": 480, "w": 40, "h": 280}
    too_high = layout_quality_findings({"layout_contract": too_high_contract})
    overlap = layout_quality_findings(
        {
            "layout_contract": contract,
            "director_review_sheet": {
                "caption_region": {
                    "quiet_text_zone": {"x": 96, "y": 1240, "w": 888, "h": 280},
                }
            },
        }
    )

    bad_caption_codes = {item["code"] for item in bad_caption_contract}
    assert valid == []
    assert "RELEASE_CAPTION_SAFE_AREA_NOT_DECLARED" in bad_caption_codes
    assert "RELEASE_CAPTION_AVOIDANCE_NOT_DECLARED" in bad_caption_codes
    assert too_high[0]["code"] == "RELEASE_CAPTION_SAFE_AREA_INVALID"
    assert overlap[0]["code"] == "RELEASE_CAPTION_OVERLAPS_SUBJECT"


def test_layout_quality_uses_review_sheet_v2_caption_quiet_zone():
    contract = scene_director_contract(
        scene_id="s1",
        index=1,
        role="hook",
        ratio="9:16",
        style="clean_product",
    )["layout_contract"]

    findings = layout_quality_findings(
        {
            "layout_contract": contract,
            "director_review_sheet_v2": {
                "caption_region": {
                    "quiet_text_zone": {"x": 96, "y": 1240, "w": 888, "h": 280},
                }
            },
        }
    )

    assert findings[0]["code"] == "RELEASE_CAPTION_OVERLAPS_SUBJECT"


def test_layout_quality_requires_cta_region_for_cta_scenes():
    contract = layout_contract(5, "9:16", "cta")
    contract.pop("ctaRect")

    findings = layout_quality_findings(
        {
            "role": "cta",
            "blueprint_id": "cta_repo_star_press",
            "layout_contract": contract,
            "caption_contract": {
                "rule_id": "bottom_safe_area_cjk",
                "position": "底部安全区",
                "avoid_subject_and_cta": True,
            },
        }
    )

    assert any(item["code"] == "RELEASE_CTA_REGION_NOT_DECLARED" for item in findings)


def test_layout_quality_accepts_cta_region_from_review_sheet_v2():
    contract = layout_contract(5, "9:16", "cta")
    contract.pop("ctaRect")

    findings = layout_quality_findings(
        {
            "role": "cta",
            "blueprint_id": "cta_repo_star_press",
            "layout_contract": contract,
            "director_review_sheet_v2": {
                "cta_region": {"x": 120, "y": 1180, "w": 840, "h": 120},
            },
            "caption_contract": {
                "rule_id": "bottom_safe_area_cjk",
                "position": "底部安全区",
                "avoid_subject_and_cta": True,
            },
        }
    )

    codes = {item["code"] for item in findings}
    assert "RELEASE_CTA_REGION_NOT_DECLARED" not in codes
    assert "RELEASE_CAPTION_OVERLAPS_CTA" not in codes


def test_layout_quality_flags_caption_overlapping_cta_region():
    contract = layout_contract(5, "9:16", "cta")
    contract["ctaRect"] = {"x": 64, "y": 1320, "w": 952, "h": 220}

    findings = layout_quality_findings(
        {
            "role": "cta",
            "layout_contract": contract,
            "caption_contract": {
                "rule_id": "bottom_safe_area_cjk",
                "position": "底部安全区",
                "avoid_subject_and_cta": True,
            },
        }
    )

    assert any(item["code"] == "RELEASE_CAPTION_OVERLAPS_CTA" for item in findings)


def test_layout_quality_flags_review_sheet_v2_cta_overlap():
    contract = layout_contract(5, "9:16", "cta")
    contract.pop("ctaRect")

    findings = layout_quality_findings(
        {
            "role": "cta",
            "layout_contract": contract,
            "director_review_sheet_v2": {
                "cta_region": {"x": 64, "y": 1320, "w": 952, "h": 220},
            },
            "caption_contract": {
                "rule_id": "bottom_safe_area_cjk",
                "position": "底部安全区",
                "avoid_subject_and_cta": True,
            },
        }
    )

    assert any(item["code"] == "RELEASE_CAPTION_OVERLAPS_CTA" for item in findings)


def test_host_generation_contract_treats_review_sheet_v2_as_director_contract():
    findings = host_generation_contract_findings(
        {
            "scene_id": "s1",
            "generator": "hyperframes",
            "director_review_sheet_v2": {"visual_content": "Codex 对话框点亮灵剪流程。"},
        }
    )

    assert any(
        item["code"] == "RELEASE_HOST_GENERATION_CONTRACT_INCOMPLETE"
        for item in findings
    )


def test_cost_gate_and_remotion_notice_are_explicit():
    assert "费用" in paid_engine_notice("volcengine_tts")
    assert paid_engine_notice("hyperframes") is None
    notice = remotion_license_notice()
    assert "remotion.pro" in notice
    assert "Node" in notice


def test_hook_library_is_profile_specific():
    assert hook_library("shipinhao_knowledge", "shipinhao")[0] == "结论先行"


def test_self_check_repairs_one_weak_visual_issue_per_round():
    scenes = [
        {
            "scene_id": "s1",
            "role": "hook",
            "motion_intent": {
                "beats": [
                    {"properties": ["opacity", "y"]},
                    {"properties": ["opacity", "translateY"]},
                ]
            },
        }
    ]

    repaired, report = self_check_visual_scenes(
        scenes,
        ratio="9:16",
        style="tech_minimal",
        max_rounds=2,
    )

    assert len(report["attempts"]) == 2
    assert report["attempts"][0]["finding_code"] == "RELEASE_VISUAL_LAYOUT_CONTRACT_MISSING"
    assert report["attempts"][1]["finding_code"] == "RELEASE_VISUAL_MOTION_TOO_WEAK"
    assert report["status"] == "passed"
    assert repaired[0]["layout_contract"]["safeBottomY"]
    assert repaired[0]["motion_intent"]["develop_full_duration"] is True
