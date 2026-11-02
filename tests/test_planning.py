from novel_pipeline.planning import DEFAULT_SCENE_PROMPT, ScenePlan


def test_empty_scene_plan_asks_internal_questions() -> None:
    assert ScenePlan().to_prompt() == DEFAULT_SCENE_PROMPT
    assert "想要什么" in DEFAULT_SCENE_PROMPT
    assert "情感从哪里蓄力" in DEFAULT_SCENE_PROMPT


def test_scene_plan_renders_only_filled_fields() -> None:
    prompt = ScenePlan(
        goal="拿到城防图",
        obstacle="老周不肯交底",
        emotional_target="警惕→短暂信任",
        aftertaste="雨声盖住关门声",
    ).to_prompt()

    assert "视角人物此刻想要：拿到城防图" in prompt
    assert "阻碍：老周不肯交底" in prompt
    assert "情感任务（先→再）：警惕→短暂信任" in prompt
    assert "章末余韵：雨声盖住关门声" in prompt
    assert "失败/拒绝的代价" not in prompt


def test_scene_plan_carries_cross_chapter_emotional_debt() -> None:
    prompt = ScenePlan(
        debt_paid="第 3 章阿棠替他挡刀，他一直没道谢",
        debt_opened="阿棠发现药瓶是空的，以为他骗她",
        witnesses="阿棠在场，裴照不在场",
    ).to_prompt()

    assert "兑现的前文情感债：第 3 章阿棠替他挡刀，他一直没道谢" in prompt
    assert "本章新欠下的情感债：阿棠发现药瓶是空的，以为他骗她" in prompt
    assert "在场/缺席（爆发时谁看见）：阿棠在场，裴照不在场" in prompt
    assert ScenePlan(debt_paid="   ").is_empty()


def test_scene_plan_makes_the_reader_payoff_explicit() -> None:
    prompt = ScenePlan(
        opening_hook="飞升大典上，仙尊被雷劈成焦炭",
        reader_promise="读者想看新人当众拆穿丹王",
        suppression="丹王有权有势，官方已经定调为雷劫失败",
        payoff_tool="315 封条 + 检测玉简 + 留影玉镜",
        payoff="许青当众封店，丹王被迫认赔",
        payoff_type="打脸/识破",
        bystander_reaction="围观修士把留影玉镜举高",
        next_hook="丹王背后是雷部",
    ).to_prompt()

    assert "开篇钩子（前 3 段）：飞升大典上，仙尊被雷劈成焦炭" in prompt
    assert "读者这一章想看到的赢面：读者想看新人当众拆穿丹王" in prompt
    assert "压制/不公平（谁或什么规则）：丹王有权有势" in prompt
    assert "兑现用的前文工具/信息/规则：315 封条" in prompt
    assert "本章兑现（谁被打脸/得到什么/谁看见）：许青当众封店" in prompt
    assert "兑现类型：打脸/识破" in prompt
    assert "旁观者反应：围观修士把留影玉镜举高" in prompt
    assert "兑现后更大的问题：丹王背后是雷部" in prompt

    # A payoff-only plan is not "empty"; the writer must see it.
    assert not ScenePlan(payoff="许青封店").is_empty()
