"""Overlay text layout (scripts/overlay_layout.py) — parity with the plugin.

The plugin's TS implementation and this Python one must agree, otherwise the
offline preview would flatter (or slander) what the reader actually sees.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "overlay_layout", SCRIPTS / "overlay_layout.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["overlay_layout"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


layout = load_module()


def test_font_size_shrinks_to_fit_and_gives_up():
    loose = layout.fit_font_size("短句。", 300, 120)
    assert loose is not None and loose > 10
    # 400 Chinese characters cannot fit into 40x20 px at the minimum size.
    assert layout.fit_font_size("模型" * 400, 40, 20) is None


def test_wrapped_lines_fit_inside_the_box():
    text = (
        "摘要。近期文本到图像生成系统的进展在很大程度上由扩散模型驱动。然而，"
        "单阶段文本到图像扩散模型在计算效率和图像细节精修方面仍面临挑战。"
    )
    width, height = 340.0, 90.0
    size = layout.fit_font_size(text, width, height)
    assert size is not None
    lines = layout.wrap_estimated(text, size, width - 2)
    assert layout.fits(lines, size, height - 1, width - 2)


def test_latin_words_are_not_split():
    lines = layout.wrap_estimated("CogView3 优于 SDXL，性能提升 77.0%。", 12, 90)
    assert len(lines) > 1
    for line in lines:
        assert not line.startswith(("ogView3", "DXL", "7.0"))


def test_closing_punctuation_never_starts_a_line():
    lines = layout.wrap_estimated("扩散模型效率提升明显。然而单阶段模型仍有挑战。", 12, 96)
    assert len(lines) > 1
    for line in lines:
        assert line[0] not in "，。、；：！？"
