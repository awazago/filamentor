"""3MF no formato de projeto do Bambu Studio: componentes em arquivos separados e placas."""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from filamentor import main
from filamentor.analysis import AnalysisError, analyze
from filamentor.catalog import Printer
from filamentor.threemf import ThreeMFError, read_3mf

PRINTERS = [Printer("Bambu Lab A1 0.4 nozzle", "A1", "Bambu Lab A1", 0.4, 256, 256, 256)]

CUBE_VERTICES = [(x, y, z) for z in (0, 10) for y in (0, 10) for x in (0, 10)]
CUBE_TRIANGLES = [
    (0, 2, 1), (1, 2, 3), (4, 5, 6), (5, 7, 6), (0, 1, 4), (1, 5, 4),
    (2, 6, 3), (3, 6, 7), (0, 4, 2), (2, 4, 6), (1, 3, 5), (3, 7, 5),
]  # fmt: skip

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PROD = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"


def mesh_xml(object_id, scale=1.0):
    vertices = "".join(
        f'<vertex x="{x * scale}" y="{y * scale}" z="{z * scale}"/>' for x, y, z in CUBE_VERTICES
    )
    triangles = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in CUBE_TRIANGLES)
    return (
        f'<object id="{object_id}" type="model"><mesh><vertices>{vertices}</vertices>'
        f"<triangles>{triangles}</triangles></mesh></object>"
    )


def bambu_project() -> bytes:
    """Duas placas: placa 1 com um cubo de 10 mm; placa 2 com um cubo esticado 3× em Z,
    posicionado 300 mm ao lado (como o Bambu Studio faz com placas extras)."""
    sub_model = (
        f'<model xmlns="{CORE}" unit="millimeter"><resources>'
        f"{mesh_xml(1)}{mesh_xml(3)}</resources><build/></model>"
    )
    root_model = (
        f'<model xmlns="{CORE}" xmlns:p="{PROD}" unit="millimeter" requiredextensions="p">'
        "<resources>"
        '<object id="2" type="model"><components>'
        '<component p:path="/3D/Objects/object_1.model" objectid="1" '
        'transform="1 0 0 0 1 0 0 0 1 0 0 0"/></components></object>'
        '<object id="4" type="model"><components>'
        '<component p:path="/3D/Objects/object_1.model" objectid="3" '
        'transform="1 0 0 0 1 0 0 0 3 0 0 0"/></components></object>'
        "</resources><build>"
        '<item objectid="2" transform="1 0 0 0 1 0 0 0 1 128 128 0" printable="1"/>'
        '<item objectid="4" transform="1 0 0 0 1 0 0 0 1 428 128 0" printable="1"/>'
        "</build></model>"
    )
    settings = (
        "<config>"
        '<object id="2"><metadata key="name" value="Base"/></object>'
        '<object id="4"><metadata key="name" value="Torre"/></object>'
        '<plate><metadata key="plater_id" value="1"/><metadata key="plater_name" value="Branco"/>'
        '<model_instance><metadata key="object_id" value="2"/></model_instance></plate>'
        '<plate><metadata key="plater_id" value="2"/><metadata key="plater_name" value="Preto"/>'
        '<model_instance><metadata key="object_id" value="4"/></model_instance></plate>'
        "</config>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("3D/3dmodel.model", root_model)
        z.writestr("3D/Objects/object_1.model", sub_model)
        z.writestr("Metadata/model_settings.config", settings)
    return buffer.getvalue()


def plain_3mf(unit="millimeter", scale=1.0) -> bytes:
    model = (
        f'<model xmlns="{CORE}" unit="{unit}"><resources>{mesh_xml(1, scale)}</resources>'
        '<build><item objectid="1"/></build></model>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("3D/3dmodel.model", model)
    return buffer.getvalue()


def test_bambu_plates_are_read_separately():
    plates = read_3mf(bambu_project())
    assert [(p.index, p.name, [o.name for o in p.objects]) for p in plates] == [
        (1, "Branco", ["Base"]),
        (2, "Preto", ["Torre"]),
    ]
    assert plates[0].mesh().extents.tolist() == pytest.approx([10, 10, 10])
    # Transform do componente (3× em Z) e do item (deslocamento da placa 2) aplicados.
    tower = plates[1].mesh()
    assert tower.extents.tolist() == pytest.approx([10, 10, 30])
    assert tower.bounds[0].tolist() == pytest.approx([428, 128, 0])


def test_analysis_is_per_plate():
    first = analyze(bambu_project(), "projeto.3mf", PRINTERS)
    assert first.plate == 1
    assert [p.name for p in first.plates] == ["Branco", "Preto"]
    assert first.dimensions_mm == pytest.approx([10, 10, 10])

    second = analyze(bambu_project(), "projeto.3mf", PRINTERS, plate=2)
    assert second.dimensions_mm == pytest.approx([10, 10, 30])
    with pytest.raises(AnalysisError, match="Placa 9"):
        analyze(bambu_project(), "projeto.3mf", PRINTERS, plate=9)


def test_plain_3mf_and_units():
    plates = read_3mf(plain_3mf())
    assert len(plates) == 1 and plates[0].objects[0].name == "objeto 1"
    centimeters = read_3mf(plain_3mf(unit="centimeter", scale=0.1))
    assert centimeters[0].mesh().extents.tolist() == pytest.approx([10, 10, 10])


def test_broken_3mf():
    with pytest.raises(ThreeMFError, match="ZIP"):
        read_3mf(b"not a zip")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("3D/3dmodel.model", f'<model xmlns="{CORE}"><resources/><build/></model>')
    with pytest.raises(ThreeMFError, match="imprimível"):
        read_3mf(buffer.getvalue())


def test_upload_plate_switch_and_mesh(monkeypatch):
    monkeypatch.setattr(
        main, "get_catalog", lambda: type("C", (), {"printers": lambda self: PRINTERS})()
    )
    client = TestClient(main.app)
    files = {"file": ("projeto.3mf", io.BytesIO(bambu_project()), "model/3mf")}
    first = client.post("/api/analyze", files=files).json()
    assert first["plate"] == 1 and first["upload_id"]

    second = client.get(f"/api/uploads/{first['upload_id']}/analysis", params={"plate": 2})
    assert second.json()["dimensions_mm"] == pytest.approx([10, 10, 30])

    mesh = client.get(f"/api/uploads/{first['upload_id']}/mesh", params={"plate": 2})
    assert mesh.status_code == 200
    assert mesh.headers["content-type"] == "model/stl"
    assert len(mesh.content) == 84 + 50 * 12  # STL binário: cabeçalho + 12 triângulos

    assert client.get("/api/uploads/inexistente/mesh").status_code == 404
