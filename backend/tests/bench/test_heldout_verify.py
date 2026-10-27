"""The held-out folder's seals, inventory and plant files (Phase 6 spec 6.1, P6-1, P6-3; plan
PR 1, G9, G10; acceptance 1). Every test builds a synthetic sealed folder in `tmp_path`: no
held-out file is ever opened here (CLAUDE.md §5)."""

import hashlib
import json
from pathlib import Path

import heldout_verify
import pytest

from guideword.bench.heldout import (
    check_seals,
    classify,
    frozen_lines,
    inventory,
    read_seals,
    seal_info,
    validate_plants,
)
from guideword.reference import load_reference_set

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_PLANT = ROOT / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
# text that must never reach the output: it stands for a package's and a key's contents
SECRET = "SENTINEL-the-root-cause-is-a-secret"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _folder(tmp_path: Path, *, star: bool = False) -> Path:
    """Two packages, one plant file, the keys, sealed in `sha256sum`'s format."""
    folder = tmp_path / "heldout"
    (folder / "keys").mkdir(parents=True)
    (folder / "case_k_tank_farm.md").write_text(f"# Case K\n{SECRET}\n", encoding="utf-8")
    (folder / "case_l_reactor.md").write_text(f"# Case L\n{SECRET}\n", encoding="utf-8")
    plant = json.loads(EXAMPLE_PLANT.read_text(encoding="utf-8"))
    (folder / "case_k.json").write_text(json.dumps(plant), encoding="utf-8")
    keys = [{"case_id": "K", "root_cause": SECRET, "match_phrases": [SECRET]}]
    (folder / "keys" / "answer_keys.json").write_text(json.dumps(keys), encoding="utf-8")
    _seal(folder, star=star)
    return folder


def _seal(folder: Path, *, star: bool = False) -> None:
    files = sorted(
        p
        for p in folder.rglob("*")
        if p.is_file() and p.name != "SEALS.txt" and ".git" not in p.parts
    )
    mark = "*" if star else " "
    lines = [f"{_sha(p)} {mark}{p.relative_to(folder).as_posix()}" for p in files]
    (folder / "SEALS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- seals -----------------------------------------------------------------------------------


def test_a_sealed_folder_passes(tmp_path: Path) -> None:
    check = check_seals(_folder(tmp_path))
    assert check.passed
    assert (check.listed, check.ok) == (4, 4)


def test_both_sha256sum_formats_are_read(tmp_path: Path) -> None:
    assert check_seals(_folder(tmp_path, star=True)).passed


def test_one_changed_byte_fails_naming_the_file(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    path = folder / "case_l_reactor.md"
    data = bytearray(path.read_bytes())
    data[0] ^= 1
    path.write_bytes(bytes(data))
    check = check_seals(folder)
    assert not check.passed and check.mismatched == ["case_l_reactor.md"]


def test_a_missing_file_fails(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    (folder / "case_k.json").unlink()
    check = check_seals(folder)
    assert not check.passed and check.missing == ["case_k.json"]


def test_an_unlisted_package_or_key_fails(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    (folder / "case_z_extra.md").write_text("extra", encoding="utf-8")
    (folder / "keys" / "case_z.json").write_text("{}", encoding="utf-8")
    check = check_seals(folder)
    assert not check.passed and check.unlisted == ["case_z_extra.md", "keys/case_z.json"]


def test_an_unlisted_file_inside_cases_or_keys_fails(tmp_path: Path) -> None:
    folder = _dated_folder(tmp_path)
    (folder / "cases" / "notes.md").write_text("extra", encoding="utf-8")
    check = check_seals(folder)
    assert not check.passed and check.unlisted == ["cases/notes.md"]


def test_an_unlisted_file_outside_cases_and_keys_is_reported_not_failed(tmp_path: Path) -> None:
    """The folder's own README, template, seal script and log aren't cases (2026-10-26)."""
    folder = _dated_folder(tmp_path)
    for name in ("README.md", "case-template.md", "seal.sh", "selection-log.md"):
        (folder / name).write_text("tooling", encoding="utf-8")
    check = check_seals(folder)
    assert check.passed and check.unlisted == []
    assert check.unsealed_other == ["README.md", "case-template.md", "seal.sh", "selection-log.md"]


def test_a_new_plant_file_is_allowed_unsealed_and_listed(tmp_path: Path) -> None:
    """P6-12: plant files converted after sealing can't be in SEALS.txt; they're frozen apart."""
    folder = _dated_folder(tmp_path)
    (folder / "plants").mkdir()
    (folder / "plants" / "case_k.json").write_text(EXAMPLE_PLANT.read_text("utf-8"), "utf-8")
    check = check_seals(folder)
    assert check.passed and check.unsealed_plants == ["plants/case_k.json"]


def test_the_script_validates_and_freezes_new_plant_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _dated_folder(tmp_path)
    (folder / "plants").mkdir()
    (folder / "plants" / "case_k.json").write_text(EXAMPLE_PLANT.read_text("utf-8"), "utf-8")
    (folder / "README.md").write_text("tooling", encoding="utf-8")
    frozen = tmp_path / "heldout-frozen.txt"
    assert heldout_verify.main([str(folder), "--frozen-out", str(frozen)]) == 0
    assert frozen.read_text(encoding="utf-8") == frozen_lines(folder, ["plants/case_k.json"])
    out = capsys.readouterr().out
    assert "new plant file (frozen separately): plants/case_k.json" in out
    assert "not a case file (not sealed, not checked): README.md" in out
    assert "inventory: package 2, plant 1, keys 2, unclassified 0" in out


def test_a_git_folder_is_not_counted_as_unlisted(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    (folder / ".git").mkdir()
    (folder / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    assert check_seals(folder).passed


def test_a_line_that_isnt_a_seal_is_reported_by_number_only(tmp_path: Path) -> None:
    seals, bad = read_seals(f"{'a' * 64}  case_k.json\nnot a seal line {SECRET}\n")
    assert seals == {"case_k.json": "a" * 64} and bad == [2]


def test_a_folder_with_no_seals_file_fails(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    (folder / "SEALS.txt").unlink()
    with pytest.raises(FileNotFoundError, match="SEALS.txt"):
        check_seals(folder)


# --- inventory -------------------------------------------------------------------------------


def test_files_are_classified_by_pattern() -> None:
    assert classify("case_k_tank_farm.md") == "package"
    assert classify("packages/case_s_terminal.md") == "package"
    assert classify("case_k.json") == "plant"
    assert classify("plants/case_m_plant.json") == "plant"
    assert classify("keys/answer_keys.json") == "keys"
    assert classify("keys/notes.json") == "unclassified"
    assert classify("README.md") == "unclassified"


def test_the_inventory_counts_and_names_key_fields_only(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    found = inventory(folder, read_seals((folder / "SEALS.txt").read_text("utf-8"))[0])
    assert found.counts == {"package": 2, "plant": 1, "keys": 1, "unclassified": 0}
    assert found.key_fields == ["case_id", "match_phrases", "root_cause"]
    assert SECRET not in repr(found)


def test_key_fields_are_read_from_a_mapping_of_cases_too(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    keys = {"K": {"case_id": "K", "source": SECRET}, "L": {"case_id": "L", "consequence": SECRET}}
    (folder / "keys" / "answer_keys.json").write_text(json.dumps(keys), encoding="utf-8")
    found = inventory(folder, {"keys/answer_keys.json": ""})
    assert found.key_fields == ["case_id", "consequence", "source"]


# --- plant files -----------------------------------------------------------------------------


def test_a_valid_plant_has_no_errors(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    assert validate_plants(folder, ["case_k.json"], load_reference_set()) == {"case_k.json": []}


def test_a_plant_that_doesnt_validate_is_listed_by_id_and_field(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    plant = json.loads((folder / "case_k.json").read_text(encoding="utf-8"))
    plant["equipment"][0]["colour"] = "red"
    (folder / "case_k.json").write_text(json.dumps(plant), encoding="utf-8")
    [issue] = validate_plants(folder, ["case_k.json"], load_reference_set())["case_k.json"]
    assert issue.code == "unknown_field" and "colour" in issue.message
    assert issue.object_id == plant["equipment"][0]["id"]


def test_the_frozen_hashes_cover_plant_files_only(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    text = frozen_lines(folder, ["case_k.json"])
    assert text == f"{_sha(folder / 'case_k.json')}  case_k.json\n"


def test_seal_info_gives_only_the_seal_files_size_and_time(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    size, when = seal_info(folder)
    assert size == (folder / "SEALS.txt").stat().st_size
    assert when.endswith("Z")


# --- the script ------------------------------------------------------------------------------


def test_the_script_passes_and_writes_the_frozen_hashes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    frozen = tmp_path / "heldout-frozen.txt"
    assert heldout_verify.main([str(folder), "--frozen-out", str(frozen)]) == 0
    assert frozen.read_text(encoding="utf-8") == frozen_lines(folder, ["case_k.json"])
    out = capsys.readouterr().out
    assert "4 of 4 files match" in out and SECRET not in out


def test_the_script_fails_on_a_mismatch_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    (folder / "case_k_tank_farm.md").write_text("changed", encoding="utf-8")
    frozen = tmp_path / "heldout-frozen.txt"
    assert heldout_verify.main([str(folder), "--frozen-out", str(frozen)]) == 1
    out = capsys.readouterr().out
    assert "mismatch: case_k_tank_farm.md" in out and not frozen.exists()


def test_the_script_fails_on_an_invalid_plant_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    plant = json.loads((folder / "case_k.json").read_text(encoding="utf-8"))
    plant["equipment"][0]["colour"] = "red"
    (folder / "case_k.json").write_text(json.dumps(plant), encoding="utf-8")
    _seal(folder)
    frozen = tmp_path / "heldout-frozen.txt"
    assert heldout_verify.main([str(folder), "--frozen-out", str(frozen)]) == 1
    assert "case_k.json: unknown_field" in capsys.readouterr().out and not frozen.exists()


def test_the_output_never_holds_a_files_contents(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    heldout_verify.main([str(folder), "--seal-info"])
    out = capsys.readouterr().out
    assert SECRET not in out
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix == ".md":
            for line in path.read_text(encoding="utf-8").splitlines()[1:]:
                assert line not in out


# --- the real folder's layout (2026-10-26): a date column, per-case keys --------------------


def _dated_folder(tmp_path: Path) -> Path:
    """The layout the held-out folder has: packages in cases/, one key per case in keys/, and
    SEALS.txt lines with a third column, the seal date."""
    folder = tmp_path / "dated"
    (folder / "cases").mkdir(parents=True)
    (folder / "keys").mkdir()
    (folder / "cases" / "case_k_batch-unit.md").write_text(f"# K\n{SECRET}\n", encoding="utf-8")
    (folder / "cases" / "case_l_tank-farm.md").write_text(f"# L\n{SECRET}\n", encoding="utf-8")
    for x in "kl":
        key = {"case_id": f"case_{x}", "root_cause": SECRET, "source": {"reference": SECRET}}
        (folder / "keys" / f"case_{x}.json").write_text(json.dumps(key), encoding="utf-8")
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    lines = [f"{_sha(p)}  {p.relative_to(folder).as_posix()}  2026-10-14" for p in files]
    (folder / "SEALS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def test_a_seal_line_with_a_date_column_reads_its_path_only() -> None:
    seals, bad = read_seals(f"{'a' * 64}  cases/case_k_batch-unit.md  2026-10-14\n")
    assert seals == {"cases/case_k_batch-unit.md": "a" * 64} and bad == []


def test_a_dated_sealed_folder_passes(tmp_path: Path) -> None:
    check = check_seals(_dated_folder(tmp_path))
    assert check.passed and (check.listed, check.ok) == (4, 4)


def test_per_case_key_files_are_keys_and_their_fields_are_listed(tmp_path: Path) -> None:
    folder = _dated_folder(tmp_path)
    assert classify("keys/case_k.json") == "keys"
    found = inventory(folder, read_seals((folder / "SEALS.txt").read_text("utf-8"))[0])
    assert found.counts == {"package": 2, "plant": 0, "keys": 2, "unclassified": 0}
    assert found.key_fields == ["case_id", "root_cause", "source"]
    assert SECRET not in repr(found)
