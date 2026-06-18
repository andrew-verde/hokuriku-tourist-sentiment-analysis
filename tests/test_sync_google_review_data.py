import json
from pathlib import Path

from scripts.sync_google_review_data import sync_google_review_data


def test_sync_google_review_data_copies_review_artifacts_and_skips_surveys(tmp_path):
    source = tmp_path / "english-fukui-tourism"
    checkpoints = source / "output" / "checkpoints"
    multilingual = source / "output" / "multilingual_review_analysis"
    survey = source / "output" / "official_fukui"
    checkpoints.mkdir(parents=True)
    multilingual.mkdir(parents=True)
    survey.mkdir(parents=True)

    (checkpoints / "google_fukui.json").write_text('{"reviews": []}\n', encoding="utf-8")
    (multilingual / "reviews_multilingual.csv").write_text(
        "city,language_group,review_text\nFukui,english,Great\n",
        encoding="utf-8",
    )
    (survey / "ftas_tagged_survey.csv").write_text("survey row\n", encoding="utf-8")

    out = tmp_path / "hokuriku" / "output"
    manifest = sync_google_review_data(source, out)

    assert (out / "checkpoints" / "google_fukui.json").exists()
    assert (out / "multilingual_review_analysis" / "reviews_multilingual.csv").exists()
    assert not (out / "official_fukui").exists()
    assert "output/official_fukui" in manifest["skipped"]

    manifest_on_disk = json.loads((out / "google_review_sync_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest_on_disk["files"]) == 2
