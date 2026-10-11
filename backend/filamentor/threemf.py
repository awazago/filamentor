"""Leitura de 3MF com suporte ao formato de projeto do Bambu Studio.

Projetos Bambu usam a extensão de produção do 3MF: o modelo raiz (`3D/3dmodel.model`) só
referencia componentes guardados em outros arquivos (`3D/Objects/object_N.model`), e as
placas ficam em `Metadata/model_settings.config`. Cada placa tem seus objetos posicionados
lado a lado no mesmo sistema de coordenadas — por isso não dá para juntar tudo numa peça só.

3MF genérico (sem `model_settings.config`) vira uma única placa com todos os itens do build.
"""

import io
import zipfile
from dataclasses import dataclass, field

import numpy as np
import trimesh
from lxml import etree

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PRODUCTION_NS = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
MODEL_REL_TYPE = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
UNIT_TO_MM = {
    "micron": 0.001,
    "millimeter": 1.0,
    "centimeter": 10.0,
    "inch": 25.4,
    "foot": 304.8,
    "meter": 1000.0,
}
# Limite de segurança contra "zip bombs": soma dos arquivos de modelo descompactados.
MAX_UNCOMPRESSED_MODEL_BYTES = 2 * 1024**3


class ThreeMFError(Exception):
    pass


@dataclass
class ModelObject:
    id: str
    name: str
    mesh: trimesh.Trimesh


@dataclass
class Plate:
    index: int
    name: str
    objects: list[ModelObject] = field(default_factory=list)

    def mesh(self) -> trimesh.Trimesh:
        meshes = [o.mesh for o in self.objects]
        return trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]


def _tag(name: str) -> str:
    return f"{{{CORE_NS}}}{name}"


def _matrix(text: str | None) -> np.ndarray:
    """Transform 3MF: 12 números, matriz 4×3 aplicada a vetores-linha [x y z 1]."""
    if not text:
        return np.eye(4)
    values = np.array(text.split(), dtype=float)
    if values.size != 12:
        raise ThreeMFError(f"Transformação inválida: {text}")
    m = np.eye(4)
    m[:3, :3] = values[:9].reshape(3, 3).T
    m[:3, 3] = values[9:]
    return m


class _Package:
    def __init__(self, data: bytes):
        try:
            self.zip = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise ThreeMFError("Arquivo 3MF corrompido (não é um ZIP válido)") from exc
        model_bytes = sum(i.file_size for i in self.zip.infolist() if i.filename.endswith(".model"))
        if model_bytes > MAX_UNCOMPRESSED_MODEL_BYTES:
            raise ThreeMFError("3MF grande demais depois de descompactado")
        self._names = {n.lstrip("/"): n for n in self.zip.namelist()}
        self._models: dict[str, tuple[float, dict[str, etree._Element]]] = {}

    def read(self, path: str) -> bytes | None:
        name = self._names.get(path.lstrip("/"))
        return self.zip.read(name) if name else None

    def root_model_path(self) -> str:
        rels = self.read("_rels/.rels")
        if rels:
            for rel in etree.fromstring(rels).iter(f"{{{RELS_NS}}}Relationship"):
                if rel.get("Type") == MODEL_REL_TYPE:
                    return rel.get("Target", "").lstrip("/")
        return "3D/3dmodel.model"

    def model(self, path: str) -> tuple[float, dict[str, etree._Element], etree._Element]:
        path = path.lstrip("/")
        raw = self.read(path)
        if raw is None:
            raise ThreeMFError(f"Arquivo interno ausente no 3MF: {path}")
        parser = etree.XMLParser(huge_tree=True, resolve_entities=False, no_network=True)
        root = etree.fromstring(raw, parser)
        scale = UNIT_TO_MM.get(root.get("unit", "millimeter"), 1.0)
        objects = {obj.get("id"): obj for obj in root.iter(_tag("object"))}
        return scale, objects, root

    def resolve(self, path: str, object_id: str, transform: np.ndarray, depth=0) -> list:
        """Malhas (vértices já transformados, faces) de um objeto, seguindo componentes."""
        if depth > 16:
            raise ThreeMFError("Componentes aninhados demais no 3MF")
        if path not in self._models:
            scale, objects, _ = self.model(path)
            self._models[path] = (scale, objects)
        _, objects = self._models[path]
        obj = objects.get(object_id)
        if obj is None:
            raise ThreeMFError(f"Objeto {object_id} não encontrado em {path}")

        parts = []
        mesh = obj.find(_tag("mesh"))
        if mesh is not None:
            vertices = np.array(
                [(v.get("x"), v.get("y"), v.get("z")) for v in mesh.iter(_tag("vertex"))],
                dtype=float,
            )
            faces = np.array(
                [(t.get("v1"), t.get("v2"), t.get("v3")) for t in mesh.iter(_tag("triangle"))],
                dtype=np.int64,
            )
            if len(vertices) and len(faces):
                homogeneous = np.c_[vertices, np.ones(len(vertices))]
                parts.append(((homogeneous @ transform.T)[:, :3], faces))
        components = obj.find(_tag("components"))
        if components is not None:
            for component in components.iter(_tag("component")):
                sub_path = component.get(f"{{{PRODUCTION_NS}}}path") or path
                sub_transform = transform @ _matrix(component.get("transform"))
                parts += self.resolve(
                    sub_path.lstrip("/"), component.get("objectid"), sub_transform, depth + 1
                )
        return parts


def _bambu_metadata(package: _Package) -> tuple[list[tuple[int, str, list[str]]], dict[str, str]]:
    """Placas [(índice, nome, ids de objeto)] e nomes dos objetos, se for projeto Bambu."""
    raw = package.read("Metadata/model_settings.config")
    if not raw:
        return [], {}
    root = etree.fromstring(raw, etree.XMLParser(resolve_entities=False, no_network=True))

    def meta(element, key):
        for m in element.findall("metadata"):
            if m.get("key") == key:
                return m.get("value")
        return None

    names = {obj.get("id"): meta(obj, "name") or "" for obj in root.findall("object")}
    plates = []
    for plate in root.findall("plate"):
        index = int(meta(plate, "plater_id") or len(plates) + 1)
        ids = [meta(instance, "object_id") for instance in plate.findall("model_instance")]
        plates.append((index, meta(plate, "plater_name") or "", [i for i in ids if i]))
    return plates, names


def read_3mf(data: bytes) -> list[Plate]:
    package = _Package(data)
    root_path = package.root_model_path()
    # A unidade do modelo raiz vale para tudo (vértices e translações).
    scale, root_objects, root = package.model(root_path)
    unit = np.diag([scale, scale, scale, 1.0])

    objects: dict[str, ModelObject] = {}
    build = root.find(_tag("build"))
    for item in build.iter(_tag("item")) if build is not None else []:
        if item.get("printable") == "0":
            continue
        object_id = item.get("objectid")
        transform = unit @ _matrix(item.get("transform"))
        parts = package.resolve(root_path, object_id, transform)
        if not parts:
            continue
        meshes = [trimesh.Trimesh(vertices=v, faces=f, process=True) for v, f in parts]
        mesh = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
        objects[object_id] = ModelObject(id=object_id, name="", mesh=mesh)

    if not objects:
        raise ThreeMFError("O 3MF não contém nenhum objeto imprimível")

    plate_specs, names = _bambu_metadata(package)
    for object_id, obj in objects.items():
        element = root_objects.get(object_id)
        fallback = element.get("name") if element is not None else None
        obj.name = names.get(object_id) or fallback or f"objeto {object_id}"

    plates = [
        Plate(index=index, name=name, objects=[objects[i] for i in ids if i in objects])
        for index, name, ids in plate_specs
    ]
    plates = [p for p in plates if p.objects]
    if not plates:
        plates = [Plate(index=1, name="", objects=list(objects.values()))]
    return sorted(plates, key=lambda p: p.index)
