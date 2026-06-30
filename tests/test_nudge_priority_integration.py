import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_fix_it_requires_supported_non_thin_driving_language():
    opportunity = load_module(
        "poi_opportunity_language_gate_test",
        ROOT / "scripts" / "build_poi_opportunity_index.py",
    )
    rows = []

    def add_poi(poi_id, n_reviews, language_group, transport_positive):
        for index in range(n_reviews):
            row = {
                "poi_id": poi_id,
                "poi_name": poi_id,
                "poi_category": "attraction",
                "review_rating": 4,
                "city": "Fukui",
                "prefecture": "Fukui",
                "language_group": language_group(index),
            }
            row.update({aspect: 0 for aspect in opportunity.ASPECTS})
            row["transport_access"] = int(index < transport_positive)
            rows.append(row)

    add_poi("thin", 20, lambda index: "chinese" if index < 2 else "japanese", 2)
    add_poi("supported", 20, lambda index: "english", 3)
    add_poi("background", 200, lambda index: "japanese", 0)

    result, _ = opportunity.build_index(pd.DataFrame(rows))
    by_name = result.set_index("poi_name")

    assert bool(by_name.loc["thin", "is_fix_it"]) is False
    assert bool(by_name.loc["thin", "membership_thin_language_blocked"]) is True
    assert bool(by_name.loc["supported", "is_fix_it"]) is True
