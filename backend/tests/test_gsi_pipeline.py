"""GSI drop-folder pipeline: discovery, metadata merge without invention, no-files behaviour."""
import asyncio
import pathlib

import yaml

import scripts.import_gsi as pipeline

def test_discovery_matches_bhukosh_style_names(tmp_path, monkeypatch):
    for name in ["Landslide_Inventory_Meghalaya.zip", "NLSM_Susceptibility_Assam.zip", "readme.txt", ".DS_Store"]:
        (tmp_path / name).write_bytes(b"")
    monkeypatch.setattr(pipeline, "GSI_DIR", tmp_path)
    found = pipeline.discover()
    assert found["landslide_inventory"].name == "Landslide_Inventory_Meghalaya.zip" and found["landslide_susceptibility"].name == "NLSM_Susceptibility_Assam.zip"

def test_build_config_uses_real_metadata_and_never_invents(tmp_path):
    meta = {"dataset_version": "Bhukosh 2025-03", "downloaded_at": "2026-09-08", "period_start": "2001-01-01", "period_end": "2024-12-31", "license": "NDSAP"}
    cfg = yaml.safe_load(pipeline.build_config("landslide_inventory", meta, tmp_path, pathlib.Path("Landslide_Inventory_Meghalaya.zip")).read_text())
    d = cfg["dataset"]
    assert d["dataset_version"] == "Bhukosh 2025-03" and d["period_end"] == "2024-12-31" and d["license"] == "NDSAP" and d["provenance_type"] == "historical" and d["layer_type"] == "landslide_inventory"
    assert "published_at" not in d and d["coverage_area"].startswith("unspecified") and d["source_metadata"]["source_file"] == "Landslide_Inventory_Meghalaya.zip"
    assert "format" not in cfg  # zip → GeoJSON, so the CSV format hint is dropped
    bare = yaml.safe_load(pipeline.build_config("landslide_susceptibility", {}, tmp_path, pathlib.Path("x.geojson")).read_text())["dataset"]
    assert not any(isinstance(v, str) and v.startswith("<") for v in bare.values())

def test_no_files_exits_without_database_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "GSI_DIR", tmp_path); monkeypatch.setattr(pipeline, "REPORTS", tmp_path / "reports")
    assert asyncio.run(pipeline.run(check_only=True, mode="skip-existing")) == 2
    assert (tmp_path / "reports" / "last_run.json").exists()
