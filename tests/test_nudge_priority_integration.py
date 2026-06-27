import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parent.parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_priority_getter_requires_one_rank():
    deck = load_module(
        "nudge_priority_html_test",
        ROOT / "scripts" / "build_nudge_seminar_slides.py",
    )
    data = pd.DataFrame(
        [
            {"rank": 1, "solution_id": "first"},
            {"rank": 2, "solution_id": "second"},
        ]
    )
    assert deck.priority_value(1, "solution_id")(data) == "first"
    with pytest.raises(KeyError, match="expected one"):
        deck.priority_value(3, "solution_id")(data)
    with pytest.raises(KeyError, match="expected one"):
        deck.priority_value(1, "solution_id")(pd.concat([data, data.iloc[[0]]]))


def test_html_deck_and_register_share_priority_order():
    priorities = pd.read_csv(
        ROOT / "output" / "nudge_analysis" / "cross_language_solution_priorities.csv"
    )
    expected = priorities.sort_values("rank")["solution_label_en"].tolist()

    deck = load_module(
        "nudge_priority_html_order_test",
        ROOT / "scripts" / "build_nudge_seminar_slides.py",
    )
    deck.load()
    html = deck.build()
    assert html.count('<div class="slide ') == 13
    positions = [html.index(label) for label in expected]
    assert positions == sorted(positions)
    assert "Begin with priority" in html

    register = load_module(
        "nudge_priority_register_test",
        ROOT / "scripts" / "build_nudge_experiment_register.py",
    )
    register.load()
    register_html = register.build_html()
    register_positions = [register_html.index(label) for label in expected]
    assert register_positions == sorted(register_positions)


def test_pptx_has_final_priority_slide_before_discussion():
    pptx_builder = load_module(
        "nudge_priority_pptx_test",
        ROOT / "scripts" / "build_nudge_pptx.py",
    )
    presentation = pptx_builder.build()
    assert len(presentation.slides) == 13

    priority_text = " ".join(
        shape.text
        for shape in presentation.slides[10].shapes
        if hasattr(shape, "text")
    )
    discussion_text = " ".join(
        shape.text
        for shape in presentation.slides[11].shapes
        if hasattr(shape, "text")
    )
    assert "Rank common nudges by impact, then ease" in priority_text
    assert "What this can and cannot claim" in discussion_text
