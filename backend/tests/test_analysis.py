import io

import numpy as np
import pytest
import trimesh

from filamentor.analysis import AnalysisError, analyze, load_mesh
from filamentor.catalog import Printer

PRINTERS = [
    Printer("Bambu Lab A1 0.4 nozzle", "A1", "Bambu Lab A1", 0.4, 256, 256, 256),
    Printer("Bambu Lab A1 mini 0.4 nozzle", "A1M", "Bambu Lab A1 mini", 0.4, 180, 180, 180),
]


def stl(mesh: trimesh.Trimesh) -> bytes:
    return mesh.export(file_type="stl")


def run(mesh: trimesh.Trimesh, filename="model.stl"):
    data = mesh.export(file_type=filename.rsplit(".", 1)[1])
    return analyze(data, filename, PRINTERS)


def box(x, y, z, center=(0, 0, 0)):
    mesh = trimesh.creation.box(extents=(x, y, z))
    mesh.apply_translation(center)
    return mesh


def mushroom():
    """Pilar 10×10×20 com "chapéu" 30×30×5 por cima, como um sólido único (união booleana)."""
    return box(10, 10, 20, (0, 0, 10)).union(box(30, 30, 5, (0, 0, 22.5)))


def overhang_45(result):
    return next(o for o in result.overhangs if o.threshold_deg == 45)


def test_cube_is_clean_and_fully_supported():
    result = run(box(20, 20, 20))
    assert result.dimensions_mm == [20, 20, 20]
    assert result.volume_mm3 == pytest.approx(8000)
    assert not result.volume_is_estimate
    assert result.health.watertight
    assert result.health.boundary_edges == 0
    assert overhang_45(result).ratio == 0
    assert result.contact_area_mm2 == pytest.approx(400)
    assert result.warnings == []


def test_mushroom_cap_is_an_overhang():
    # A parte de baixo do chapéu (30×30 menos o encaixe do pilar 10×10) fica no ar.
    result = run(mushroom())
    assert overhang_45(result).area_mm2 == pytest.approx(30 * 30 - 10 * 10, rel=0.01)
    assert result.contact_area_mm2 == pytest.approx(100)


def test_upside_down_mushroom_is_suggested():
    best = run(mushroom()).orientations[0]
    # Virado de cabeça para baixo, o chapéu vira base: sem overhang e com mais contato.
    assert best.label != "original"
    assert best.overhang_ratio == 0
    assert best.contact_area_mm2 == pytest.approx(900, rel=0.01)


def test_thin_plate_is_detected():
    result = run(box(40, 40, 0.3))
    walls = result.thin_walls.below_line_width
    assert walls["0.4"] > 0.9  # 0,3 mm < largura de linha do bico 0.4 (0,42 mm)
    assert walls["0.2"] < 0.1  # mas é imprimível com bico 0.2 (0,21 mm)... nas faces largas


def test_open_mesh_is_flagged():
    mesh = box(20, 20, 20)
    mesh.update_faces(np.arange(len(mesh.faces)) != 0)
    result = run(mesh)
    assert not result.health.watertight
    assert result.health.boundary_edges > 0
    assert result.volume_is_estimate
    assert "not_watertight" in result.warnings


def test_tiny_fragments_are_removed():
    sliver = trimesh.Trimesh(
        vertices=[[50, 50, 5], [50.01, 50, 5], [50, 50.01, 5]], faces=[[0, 1, 2]]
    )
    result = run(trimesh.util.concatenate([box(20, 20, 20), sliver]))
    assert result.health.fragments_removed == 1
    assert result.health.watertight
    assert result.dimensions_mm == [20, 20, 20]
    assert "fragments_removed" in result.warnings


def test_suspicious_units_and_printer_fit():
    tiny = run(box(0.05, 0.05, 0.1))
    assert "units_too_small" in tiny.warnings

    big = run(box(200, 100, 50))
    fits = {f.printer: f for f in big.fits}
    assert fits["Bambu Lab A1"].fits
    assert not fits["Bambu Lab A1 mini"].fits
    assert fits["Bambu Lab A1 mini"].max_uniform_scale == pytest.approx(0.9)


def test_tall_thin_part_has_tipping_risk():
    result = run(box(5, 5, 60))
    assert result.slenderness > 3
    assert "tipping_risk" in result.warnings


def test_3mf_is_supported():
    result = run(box(10, 20, 30), filename="part.3mf")
    assert sorted(result.dimensions_mm) == [10, 20, 30]


def test_invalid_input():
    with pytest.raises(AnalysisError, match="Formato"):
        load_mesh(b"x", "model.obj")
    with pytest.raises(AnalysisError):
        load_mesh(b"not an stl at all", "model.stl")


def test_api_analyze_endpoint(monkeypatch):
    from fastapi.testclient import TestClient

    from filamentor import main

    monkeypatch.setattr(
        main, "get_catalog", lambda: type("C", (), {"printers": lambda self: PRINTERS})()
    )
    client = TestClient(main.app)
    files = {"file": ("cube.stl", io.BytesIO(stl(box(20, 20, 20))), "model/stl")}
    response = client.post("/api/analyze", files=files)
    assert response.status_code == 200
    assert response.json()["dimensions_mm"] == [20, 20, 20]
    bad = client.post("/api/analyze", files={"file": ("x.obj", io.BytesIO(b"x"), "text/plain")})
    assert bad.status_code == 422
