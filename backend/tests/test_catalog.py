import json

import pytest

from filamentor.catalog import Catalog, CatalogError, PresetLibrary


def write(root, kind, data):
    folder = root / kind
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{data['name']}.json").write_text(json.dumps(data))


@pytest.fixture
def profiles(tmp_path):
    write(tmp_path, "machine", {"name": "machine_common", "instantiation": "false", "gcode": "G28"})
    write(
        tmp_path,
        "machine",
        {
            "name": "start template",
            "instantiation": "false",
            "machine_start_gcode": "START",
        },
    )
    write(
        tmp_path,
        "machine",
        {
            "name": "Bambu Lab A1 0.4 nozzle",
            "inherits": "machine_common",
            "include": ["start template"],
            "instantiation": "true",
            "setting_id": "GM1",
            "printer_model": "Bambu Lab A1",
            "nozzle_diameter": ["0.4"],
            "printable_area": ["0x0", "256x0", "256x256", "0x256"],
            "printable_height": "256",
        },
    )
    write(
        tmp_path,
        "machine",
        {
            "name": "Bambu Lab X1 0.4 nozzle",
            "inherits": "machine_common",
            "instantiation": "true",
            "printer_model": "Bambu Lab X1",
            "nozzle_diameter": ["0.4"],
            "printable_area": ["0x0", "256x0", "256x256", "0x256"],
            "printable_height": "256",
        },
    )
    write(
        tmp_path,
        "process",
        {
            "name": "process_common",
            "instantiation": "false",
            "setting_id": "BASE",
            "layer_height": "0.2",
            "wall_loops": "2",
        },
    )
    write(
        tmp_path,
        "process",
        {
            "name": "0.20mm Standard @BBL A1",
            "inherits": "process_common",
            "instantiation": "true",
            "compatible_printers": ["Bambu Lab A1 0.4 nozzle"],
        },
    )
    filament_base = {
        "instantiation": "false",
        "filament_type": ["PLA"],
        "filament_vendor": ["Generic"],
        "filament_density": ["1.24"],
        "nozzle_temperature": ["220"],
        "nozzle_temperature_range_low": ["190"],
        "nozzle_temperature_range_high": ["240"],
        "filament_max_volumetric_speed": ["12"],
        "required_nozzle_HRC": ["3"],
        "filament_is_support": ["0"],
    }
    write(tmp_path, "filament", {"name": "fdm_filament_pla", **filament_base})
    leaf = {"instantiation": "true", "compatible_printers": ["Bambu Lab A1 0.4 nozzle"]}
    write(
        tmp_path,
        "filament",
        {
            "name": "Generic PLA @BBL A1",
            "inherits": "fdm_filament_pla",
            **leaf,
            "nozzle_temperature": ["215"],
        },
    )
    write(
        tmp_path,
        "filament",
        {
            "name": "Generic PLA-CF @BBL A1",
            "inherits": "fdm_filament_pla",
            **leaf,
            "filament_type": ["PLA-CF"],
            "required_nozzle_HRC": ["40"],
        },
    )
    write(
        tmp_path,
        "filament",
        {
            "name": "Abrasive PLA @BBL A1",
            "inherits": "fdm_filament_pla",
            **leaf,
            "required_nozzle_HRC": ["40"],
        },
    )
    write(
        tmp_path,
        "filament",
        {
            "name": "Support For PLA @BBL A1",
            "inherits": "fdm_filament_pla",
            **leaf,
            "filament_is_support": ["1"],
        },
    )
    write(
        tmp_path,
        "filament",
        {
            "name": "Generic PLA @BBL X1",
            "inherits": "fdm_filament_pla",
            "instantiation": "true",
            "compatible_printers": ["Bambu Lab X1 0.4 nozzle"],
        },
    )
    # Arquivo auxiliar sem "name" deve ser ignorado.
    (tmp_path / "filament" / "filament_id_map.json").write_text(json.dumps({"GF1": "x"}))
    return tmp_path


def test_resolve_merges_parent_include_and_own_keys(profiles):
    preset = PresetLibrary.load(profiles).resolve("Bambu Lab A1 0.4 nozzle")
    assert preset["gcode"] == "G28"
    assert preset["machine_start_gcode"] == "START"
    assert preset["name"] == "Bambu Lab A1 0.4 nozzle"
    assert preset["setting_id"] == "GM1"
    assert "inherits" not in preset
    assert "include" not in preset


def test_resolve_child_overrides_parent(profiles):
    preset = PresetLibrary.load(profiles).resolve("Generic PLA @BBL A1")
    assert preset["nozzle_temperature"] == ["215"]
    assert preset["filament_density"] == ["1.24"]


def test_resolve_does_not_inherit_identity_keys(profiles):
    preset = PresetLibrary.load(profiles).resolve("0.20mm Standard @BBL A1")
    assert "setting_id" not in preset
    assert preset["instantiation"] == "true"
    assert preset["wall_loops"] == "2"


def test_resolve_returns_independent_copies(profiles):
    library = PresetLibrary.load(profiles)
    library.resolve("Generic PLA @BBL A1")["nozzle_temperature"] = ["999"]
    assert library.resolve("Generic PLA @BBL A1")["nozzle_temperature"] == ["215"]


def test_resolve_detects_cycles(tmp_path):
    write(tmp_path, "process", {"name": "a", "inherits": "b"})
    write(tmp_path, "process", {"name": "b", "inherits": "a"})
    with pytest.raises(CatalogError, match="circular"):
        PresetLibrary.load(tmp_path).resolve("a")


def test_unknown_preset_and_missing_dir(tmp_path, profiles):
    with pytest.raises(CatalogError):
        PresetLibrary.load(profiles).resolve("não existe")
    with pytest.raises(CatalogError, match="FILAMENTOR_PROFILES_DIR"):
        PresetLibrary.load(tmp_path / "inexistente")


def test_catalog_keeps_only_supported_printers(profiles):
    printers = Catalog(PresetLibrary.load(profiles)).printers()
    assert [(p.key, p.nozzle, p.bed_x, p.bed_y, p.max_z) for p in printers] == [
        ("A1", 0.4, 256, 256, 256)
    ]


def test_catalog_filters_filaments(profiles):
    catalog = Catalog(PresetLibrary.load(profiles))
    names = [f.preset for f in catalog.filaments("Bambu Lab A1 0.4 nozzle")]
    assert names == ["Generic PLA @BBL A1"]
    assert catalog.filaments("Bambu Lab A1 0.4 nozzle", "PETG") == []


def test_catalog_rejects_out_of_scope_printer(profiles):
    catalog = Catalog(PresetLibrary.load(profiles))
    with pytest.raises(CatalogError):
        catalog.processes("Bambu Lab X1 0.4 nozzle")
