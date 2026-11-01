from novel_pipeline.quality.models import Severity
from novel_pipeline.quality.rules import RuleEngine

CLEAN_SAMPLE = """夜色从屋檐上落下来，街面上的水光一层层铺开。老周把最后一箱书搬进店里，肩膀被纸箱勒出一道红印。

他先烧水，再把窗缝一条条检查过去。风从北边来，带着潮气，门轴响了两声。

柜台上摊着白天收来的旧书，纸页发脆，边角卷起。老周用软布擦去灰，指腹沾了薄薄一层黑。

九点过后，巷子里安静下来。偶尔有自行车经过，铃铛响一下，很快又被雨声盖住。

他给自己泡了杯茶，坐在门边的小凳上。茶很烫，他吹了两口，视线落在对面那扇没有亮灯的窗上。

那扇窗空了半年。以前住着一个教书的先生，总在夜里读诗，声音不大，隔着雨听不真切。

老周起身去关半扇门。门轴又响了一声，这次比先前长，像有人在外头轻轻推了一下。

他停住，侧耳听。雨还在下，檐口的水连成线，落在石阶上，碎成一片细响。

没有人。他嗯了一声。把门合上，插好门闩，回到柜台后面。茶已经温了，表面浮着一层薄薄的光。

他翻开账本，写下今天的日期，又停住笔。窗外那扇黑着的窗里，有什么东西动了一下。
"""


def findings_by_id(text: str) -> dict[str, object]:
    engine = RuleEngine()
    return {finding.rule_id: finding for finding in engine.check(text)}


def test_clean_sample_has_no_findings() -> None:
    assert RuleEngine().check(CLEAN_SAMPLE) == []


def test_q01_flags_consecutive_single_sentence_paragraphs() -> None:
    text = """他停下。

他回头。

他听见雨声。

柜台上的灯闪了两下，随后稳住。老周把账本合上，手指在封皮上敲了敲。

风从门缝里挤进来，带着潮湿的纸味。他打了个喷嚏，又揉了揉鼻子。

巷子深处传来一声关门响。声音很轻，却让他停了半拍。

他走到窗边，撩起一角帘子。外头没有人，只有雨线在路灯下斜斜地落。

他回到柜台，把台灯调暗了一些。"""
    finding = findings_by_id(text)["Q01"]
    assert finding.severity is Severity.MAJOR
    assert "连续单句段" in finding.evidence


def test_q02_flags_uniform_paragraph_lengths() -> None:
    paragraph = "段落内容段落内容段落内容。段落内容段落内容。"
    text = "\n\n".join(paragraph for _ in range(20))
    finding = findings_by_id(text)["Q02"]
    assert finding.severity is Severity.MAJOR
    assert "变异系数" in finding.evidence


def test_q03_flags_emphasis_density() -> None:
    text = "正文" + "**强调**" * 20 + "。" * 100
    finding = findings_by_id(text)["Q03"]
    assert finding.severity is Severity.MAJOR
    assert "强调标记" in finding.evidence


def test_q04_flags_cliche_density() -> None:
    text = "总之，然而值得注意的是，与此同时，毫无疑问。" * 10
    finding = findings_by_id(text)["Q04"]
    assert finding.severity is Severity.MAJOR
    assert "套话" in finding.evidence


def test_q05_flags_uniform_sentence_lengths() -> None:
    sentence = "这是一个长度大约二十个字的句子用于测试。"
    text = sentence * 30
    finding = findings_by_id(text)["Q05"]
    assert finding.severity is Severity.MINOR
    assert "平均句长" in finding.evidence


def test_q06_flags_repeated_four_gram() -> None:
    text = "甲乙丙丁" * 10 + "戊己庚辛" * 90
    finding = findings_by_id(text)["Q06"]
    assert finding.severity is Severity.MINOR
    assert "重复" in finding.evidence
