from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import project_config


def write(project_dir: Path, data: dict) -> Path:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.json").write_text(json.dumps(data, indent=2) + "\n")
    return project_dir


GOOD_PIPELINE = {
    "schema": 1,
    "name": "oldenlabs",
    "type": "pipeline",
    "unit": "oldenlabs",
    "code_repo": "neu-oldenlabs",
    "data_root": "/data/olden",
    "lane": "oldenlabs/dacruz-study2",
    "status": "active",
}


def test_loads_a_valid_pipeline_config(tmp_path):
    d = write(tmp_path / "oldenlabs", GOOD_PIPELINE)
    cfg = project_config.load(d)
    assert cfg.name == "oldenlabs"
    assert cfg.type == "pipeline"
    assert cfg.unit == "oldenlabs"
    assert cfg.data_root == Path("/data/olden")
    assert cfg.source_studies == ()
    assert cfg.path == d


def test_optional_fields_default_to_none(tmp_path):
    d = write(tmp_path / "alz-olf", {
        "schema": 1, "name": "alz-olf", "type": "paper", "status": "active",
    })
    cfg = project_config.load(d)
    assert cfg.data_root is None
    assert cfg.paper_repo is None
    assert cfg.lane is None


def test_source_studies_becomes_a_tuple(tmp_path):
    d = write(tmp_path / "astro_atp", {
        "schema": 1, "name": "astro_atp", "type": "paper", "status": "active",
        "source_studies": ["oldenlabs/dacruz/study2"],
    })
    assert project_config.load(d).source_studies == ("oldenlabs/dacruz/study2",)


def test_missing_file_names_the_path(tmp_path):
    d = tmp_path / "nothing"
    d.mkdir()
    with pytest.raises(project_config.ConfigError) as e:
        project_config.load(d)
    assert "project.json" in str(e.value)
    assert str(d) in str(e.value)


def test_malformed_json_names_the_path(tmp_path):
    d = tmp_path / "broken"
    d.mkdir()
    (d / "project.json").write_text("{not json")
    with pytest.raises(project_config.ConfigError) as e:
        project_config.load(d)
    assert str(d / "project.json") in str(e.value)


def test_unknown_type_is_rejected_and_lists_valid_types(tmp_path):
    d = write(tmp_path / "x", {
        "schema": 1, "name": "x", "type": "pipeline+paper", "status": "active",
    })
    with pytest.raises(project_config.ConfigError) as e:
        project_config.load(d)
    assert "pipeline+paper" in str(e.value)
    assert "paper" in str(e.value) and "pipeline" in str(e.value)


def test_unknown_status_is_rejected(tmp_path):
    d = write(tmp_path / "x", {
        "schema": 1, "name": "x", "type": "paper", "status": "wip",
    })
    with pytest.raises(project_config.ConfigError):
        project_config.load(d)


def test_name_must_match_directory(tmp_path):
    d = write(tmp_path / "alz-olf", {
        "schema": 1, "name": "alz_olf", "type": "paper", "status": "active",
    })
    with pytest.raises(project_config.ConfigError) as e:
        project_config.load(d)
    assert "alz_olf" in str(e.value) and "alz-olf" in str(e.value)


def test_relative_data_root_is_rejected(tmp_path):
    d = write(tmp_path / "x", {
        "schema": 1, "name": "x", "type": "paper", "status": "active",
        "data_root": "../data",
    })
    with pytest.raises(project_config.ConfigError) as e:
        project_config.load(d)
    assert "absolute" in str(e.value).lower()


def test_unknown_schema_version_is_rejected(tmp_path):
    d = write(tmp_path / "x", {
        "schema": 99, "name": "x", "type": "paper", "status": "active",
    })
    with pytest.raises(project_config.ConfigError) as e:
        project_config.load(d)
    assert "99" in str(e.value)


def test_source_studies_must_be_a_list(tmp_path):
    d = write(tmp_path / "x", {
        "schema": 1, "name": "x", "type": "paper", "status": "active",
        "source_studies": "oldenlabs/dacruz/study2",
    })
    with pytest.raises(project_config.ConfigError) as e:
        project_config.load(d)
    assert "source_studies" in str(e.value)
