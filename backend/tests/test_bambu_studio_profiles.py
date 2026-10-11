"""Testes contra os presets reais do Bambu Studio instalado (pulados se ausente)."""

import pytest
from fastapi.testclient import TestClient

from filamentor.catalog import STAINLESS_STEEL_HRC, first, get_catalog
from filamentor.config import get_settings
from filamentor.main import app

pytestmark = pytest.mark.skipif(
    not get_settings().profiles_dir.is_dir(), reason="Bambu Studio não instalado"
)

A1 = "Bambu Lab A1 0.4 nozzle"
A1_MINI = "Bambu Lab A1 mini 0.4 nozzle"


@pytest.fixture(scope="module")
def catalog():
    return get_catalog()


def test_all_a1_and_a1_mini_nozzles_are_available(catalog):
    found = {(p.key, p.nozzle) for p in catalog.printers()}
    assert found == {(key, n) for key in ("A1", "A1M") for n in (0.2, 0.4, 0.6, 0.8)}


def test_build_volumes(catalog):
    by_preset = {p.preset: p for p in catalog.printers()}
    assert (by_preset[A1].bed_x, by_preset[A1].bed_y, by_preset[A1].max_z) == (256, 256, 256)
    mini = by_preset[A1_MINI]
    assert (mini.bed_x, mini.bed_y, mini.max_z) == (180, 180, 180)


def test_every_nozzle_has_processes_and_filaments(catalog):
    for printer in catalog.printers():
        assert catalog.processes(printer.preset), printer.preset
        materials = {f.material for f in catalog.filaments(printer.preset)}
        # A Bambu não publica presets de TPU para o bico 0.2 (risco de entupimento).
        expected = {"PLA", "PETG"} if printer.nozzle == 0.2 else {"PLA", "PETG", "TPU"}
        assert materials == expected, printer.preset


def test_no_abrasive_or_support_filaments(catalog):
    for printer in catalog.printers():
        for filament in catalog.filaments(printer.preset):
            preset = catalog.library.resolve(filament.preset)
            assert int(first(preset["required_nozzle_HRC"])) <= STAINLESS_STEEL_HRC
            assert first(preset["filament_is_support"]) != "1"
            assert "CF" not in filament.preset


def test_material_variants_are_grouped_into_families(catalog):
    """TPU para AMS Lite e PLA Aero têm `filament_type` próprio, mas pertencem às famílias."""
    tpu = {f.preset: f for f in catalog.filaments(A1_MINI, "TPU")}
    assert tpu["Bambu TPU for AMS @BBL A1M"].filament_type == "TPU-AMS"
    pla = {f.preset: f for f in catalog.filaments(A1, "PLA")}
    assert pla["Bambu PLA Aero @BBL A1"].filament_type == "PLA-AERO"


def test_resolved_filament_has_what_the_cli_needs(catalog):
    """O CLI zerou o peso com o preset não achatado; o achatado deve ter densidade e tipo."""
    preset = catalog.library.resolve("Bambu PETG HF @BBL A1")
    assert first(preset["filament_type"]) == "PETG"
    assert float(first(preset["filament_density"])) > 1
    assert first(preset["nozzle_temperature"]) == "240"
    assert "inherits" not in preset


def test_api_endpoints():
    client = TestClient(app)
    assert client.get("/api/health").json()["status"] == "ok"
    assert len(client.get("/api/printers").json()) == 8
    tpu = client.get("/api/filaments", params={"machine": A1_MINI, "material": "TPU"}).json()
    assert tpu and all(f["material"] == "TPU" for f in tpu)
    abs_response = client.get("/api/filaments", params={"machine": A1, "material": "ABS"})
    assert abs_response.status_code == 422
    x1_response = client.get("/api/processes", params={"machine": "Bambu Lab X1 0.4 nozzle"})
    assert x1_response.status_code == 404
    assert client.get("/").status_code == 200
