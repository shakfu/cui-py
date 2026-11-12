"""Value types, buffers and constants."""

import datetime

import pytest

import cui


def test_version() -> None:
    assert cui.CUI_VERSION == "1.4.0"
    assert cui.__version__


def test_constants() -> None:
    assert isinstance(cui.BUTTON_PRIMARY, int)
    assert cui.KEY_A != cui.KEY_B
    assert isinstance(cui.ICON_PLUS, str) and len(cui.ICON_PLUS) == 1
    assert cui.COLOR_ACCENT.a == 0  # a theme token, not an RGBA color
    assert cui.MOD_PRIMARY in (cui.MOD_CTRL, cui.MOD_SUPER)


def test_rgb() -> None:
    assert cui.rgb(0x123456) == cui.Color(0x12, 0x34, 0x56, 255)
    assert cui.rgba(0x12345678) == cui.Color(0x12, 0x34, 0x56, 0x78)
    with pytest.raises(ValueError):
        cui.rgb(0x1000000)
    with pytest.raises(ValueError):
        cui.rgb(-1)


def test_sizes() -> None:
    assert cui.px(10) == cui.Size(cui.SIZE_FIXED, 10.0)
    assert cui.pct(50).kind == cui.SIZE_PERCENT
    assert cui.grow(2) == cui.Size(cui.SIZE_GROW, 2.0)
    assert cui.FILL == cui.grow()
    assert cui.FIT.kind == cui.SIZE_FIT


def test_text_buffer() -> None:
    b = cui.TextBuffer(8, "abc")
    assert b.value == "abc" and str(b) == "abc" and b.capacity == 8
    b.value = "1234567"  # 7 bytes and the NUL
    assert b.value == "1234567"
    with pytest.raises(ValueError):
        b.value = "12345678"
    assert b.value == "1234567"  # a failed set keeps the old text
    with pytest.raises(ValueError):
        b.value = "a\0b"
    b.value = "é"  # two bytes in UTF-8
    assert b.value == "é"
    with pytest.raises(ValueError):
        cui.TextBuffer(0)


def test_records() -> None:
    item = cui.VizItem(label="a", value=1.0)
    assert item.color is None  # unset fields default to None, which CUI reads as zero
    assert cui.Series._fields == ("name", "values", "color")  # `count` is derived


def test_date_today() -> None:
    d = cui.date_today()
    assert isinstance(d, datetime.date)
    assert cui.date_from_days(cui.date_to_days(d)) == d


def test_pure_functions() -> None:
    white = cui.oklch(1, 0, 0, 1)
    assert white[:3] == (255, 255, 255)
    mid = cui.mix(white, cui.rgb(0), 0.5)
    assert 90 < mid.r < 140
    assert cui.alpha(cui.rgb(0x123456), 0.5).a == 128
    assert cui.http_reason(404) == "Not Found"
    assert cui.key_name(cui.KEY_ENTER)
