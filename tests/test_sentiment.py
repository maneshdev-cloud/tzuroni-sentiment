import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.sentiment import direction_label, score_text


def test_english_bullish():
    assert score_text("Tencent beats estimates, shares surge on strong demand") > 0.1


def test_english_bearish():
    assert score_text("Alibaba plunges after downgrade, weak demand warning") < -0.1


def test_chinese_bullish():
    assert score_text("騰訊急升，突破新高，買入評級") > 0


def test_chinese_bearish():
    assert score_text("小米大跌，跌穿支持，盈警告急") < 0


def test_korean_bullish():
    assert score_text("삼성전자 주가 상승, 신고가 경신, 매수 의견") > 0


def test_korean_bearish():
    assert score_text("카카오 주가 급락, 악재에 약세 지속") < 0


def test_neutral_and_empty():
    assert score_text("") == 0.0
    assert direction_label(0.0) == "Neutral"
    assert direction_label(0.2) == "Bullish"
    assert direction_label(-0.2) == "Bearish"
