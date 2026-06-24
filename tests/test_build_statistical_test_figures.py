import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_statistical_test_figures import build_statistical_test_figures


def test_builds_statistical_test_figure_pack_from_aggregate_docs(tmp_path):
    root = Path(__file__).resolve().parent.parent
    report = build_statistical_test_figures(
        input_dir=root / "docs" / "statistical_test_outputs",
        output_dir=tmp_path / "figures",
        command="pytest statistical figures",
    )

    index = pd.read_csv(tmp_path / "figures" / "statistical_test_figure_index.csv")
    questions = (tmp_path / "figures" / "statistical_test_figure_questions.md").read_text(
        encoding="utf-8"
    )
    manifest = json.loads(
        (tmp_path / "figures" / "statistical_test_figure_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert report["metrics"]["figure_count"] == 17
    assert len(index) == 17
    assert "H1 sentiment category shares" in set(index["figure"])
    assert "Chinese city/platform friction status" in set(index["figure"])
    assert "Hypothesis results at a glance" in set(index["figure"])
    assert "Within-English Sentiment Drivers" in set(index["figure"])
    assert "row-level post/review text" in questions
    assert "not nationality" in "\n".join(report["caveats"])
    assert manifest["kind"] == "statistical_test_figure_pack"
    assert manifest["command"] == "pytest statistical figures"

    for path_text in index["path"]:
        path = Path(path_text)
        assert path.exists()
        svg = path.read_text(encoding="utf-8")
        assert "<svg" in svg
        assert "placeholder" not in svg.lower()
