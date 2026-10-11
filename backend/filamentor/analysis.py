"""Análise geométrica de modelos STL/3MF para impressão FDM.

Convenções: unidades em mm, eixo Z para cima, mesa em z = mínimo da peça. O ângulo de
overhang segue o Bambu Studio (`support_threshold_angle`): é a inclinação da superfície
voltada para baixo em relação à horizontal — 0° é um teto plano, 90° é uma parede vertical.
Superfícies com inclinação abaixo do limite precisam de suporte.
"""

import io
from dataclasses import dataclass, field
from pathlib import PurePath

import numpy as np
import trimesh

from .catalog import Printer

OVERHANG_THRESHOLDS = (30, 45, 60)
DEFAULT_OVERHANG_THRESHOLD = 45
NOZZLES = (0.2, 0.4, 0.6, 0.8)

# Faces a até esta altura da mesa contam como apoiadas (não são overhang).
BED_TOLERANCE_MM = 0.2
# Corpos minúsculos e sem volume são lixo de exportação (comum em modelos gerados por IA).
FRAGMENT_MAX_EXTENT_MM = 0.5
FRAGMENT_MAX_VOLUME_MM3 = 0.1
# Modelos fora desta faixa provavelmente foram exportados na unidade errada.
SUSPICIOUS_MIN_MM = 5.0
SUSPICIOUS_MAX_MM = 1000.0
THICKNESS_SAMPLES = 20_000
# Largura de linha típica = 1,05 × diâmetro do bico (padrão dos presets Bambu).
LINE_WIDTH_FACTOR = 1.05
ORIENTATION_CANDIDATES = 8


class AnalysisError(Exception):
    pass


@dataclass
class MeshHealth:
    watertight: bool
    winding_consistent: bool
    bodies: int
    fragments_removed: int
    boundary_edges: int
    non_manifold_edges: int
    degenerate_faces: int


@dataclass
class Overhang:
    threshold_deg: int
    area_mm2: float
    ratio: float


@dataclass
class Orientation:
    label: str
    rotation: list[list[float]]
    height_mm: float
    overhang_ratio: float
    contact_area_mm2: float
    score: float


@dataclass
class PrinterFit:
    printer: str
    fits: bool
    max_uniform_scale: float


@dataclass
class ThinWalls:
    sampled_points: int
    # Fração da superfície mais fina que a largura de linha de cada bico.
    below_line_width: dict[str, float]
    thickness_p5_mm: float | None


@dataclass
class Analysis:
    filename: str
    triangles: int
    dimensions_mm: list[float]
    volume_mm3: float
    # Malha aberta não tem volume definido: usamos o casco convexo (superestima).
    volume_is_estimate: bool
    surface_area_mm2: float
    health: MeshHealth
    overhangs: list[Overhang]
    contact_area_mm2: float
    slenderness: float | None
    thin_walls: ThinWalls
    fits: list[PrinterFit]
    orientations: list[Orientation]
    warnings: list[str] = field(default_factory=list)


def load_mesh(data: bytes, filename: str) -> trimesh.Trimesh:
    suffix = PurePath(filename).suffix.lower().lstrip(".")
    if suffix not in ("stl", "3mf"):
        raise AnalysisError("Formato não suportado: envie um arquivo .stl ou .3mf")
    try:
        loaded = trimesh.load(io.BytesIO(data), file_type=suffix, force="mesh")
    except Exception as exc:
        raise AnalysisError(f"Não foi possível ler o arquivo: {exc}") from exc
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
        raise AnalysisError("O arquivo não contém nenhuma malha")
    return loaded


def remove_fragments(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, int, int]:
    """Remove corpos desprezíveis. Retorna (malha, corpos mantidos, fragmentos removidos)."""
    bodies = mesh.split(only_watertight=False)
    if len(bodies) <= 1:
        return mesh, len(bodies), 0
    # Fragmentos degenerados geram divisão por zero no cálculo de centro de massa.
    with np.errstate(divide="ignore", invalid="ignore"):
        kept = [
            body
            for body in bodies
            if body.extents.max() > FRAGMENT_MAX_EXTENT_MM
            or abs(body.volume) > FRAGMENT_MAX_VOLUME_MM3
        ]
    if not kept:
        return mesh, len(bodies), 0
    cleaned = trimesh.util.concatenate(kept) if len(kept) > 1 else kept[0]
    return cleaned, len(kept), len(bodies) - len(kept)


def edge_defects(mesh: trimesh.Trimesh) -> tuple[int, int]:
    """Arestas de borda (buracos) e não-manifold (compartilhadas por 3+ faces)."""
    _, inverse = trimesh.grouping.unique_rows(mesh.edges_sorted)
    counts = np.bincount(inverse)
    return int((counts == 1).sum()), int((counts > 2).sum())


def overhang_mask(normals_z: np.ndarray, centers_z: np.ndarray, threshold_deg: float) -> np.ndarray:
    above_bed = centers_z > centers_z.min() + BED_TOLERANCE_MM
    return above_bed & (normals_z < -np.cos(np.radians(threshold_deg)))


def contact_area(normals_z: np.ndarray, centers_z: np.ndarray, areas: np.ndarray) -> float:
    on_bed = (centers_z < centers_z.min() + 0.05) & (normals_z < -0.95)
    return float(areas[on_bed].sum())


def evaluate_orientation(mesh: trimesh.Trimesh, rotation: np.ndarray, label: str) -> Orientation:
    normals_z = mesh.face_normals @ rotation[2]
    centers_z = mesh.triangles_center @ rotation[2]
    vertices_z = mesh.vertices @ rotation[2]
    areas = mesh.area_faces
    overhang = areas[overhang_mask(normals_z, centers_z, DEFAULT_OVERHANG_THRESHOLD)].sum()
    overhang_ratio = float(overhang / areas.sum())
    contact = contact_area(normals_z, centers_z, areas)
    height = float(vertices_z.max() - vertices_z.min())
    return Orientation(
        label=label,
        rotation=np.round(rotation, 6).tolist(),
        height_mm=round(height, 2),
        overhang_ratio=round(overhang_ratio, 4),
        contact_area_mm2=round(contact, 1),
        score=0.0,
    )


def score_orientations(candidates: list[Orientation]) -> None:
    """Qualidade primeiro: suporte (marcas na superfície) pesa mais; depois adesão à mesa;
    a altura entra só como desempate (mais camadas = mais tempo, não pior qualidade)."""
    max_contact = max(c.contact_area_mm2 for c in candidates) or 1.0
    max_height = max(c.height_mm for c in candidates) or 1.0
    for c in candidates:
        c.score = round(
            -3.0 * c.overhang_ratio
            + 1.0 * c.contact_area_mm2 / max_contact
            - 0.2 * c.height_mm / max_height,
            4,
        )


def suggest_orientations(mesh: trimesh.Trimesh) -> list[Orientation]:
    candidates = [evaluate_orientation(mesh, np.eye(3), "original")]
    try:
        transforms, probabilities = trimesh.poses.compute_stable_poses(mesh, n_samples=1)
    except Exception:
        transforms, probabilities = [], []
    order = np.argsort(probabilities)[::-1][:ORIENTATION_CANDIDATES]
    for rank, index in enumerate(order, start=1):
        rotation = np.asarray(transforms[index])[:3, :3]
        if np.allclose(rotation, np.eye(3), atol=1e-3):
            continue
        candidates.append(evaluate_orientation(mesh, rotation, f"estável #{rank}"))
    score_orientations(candidates)
    return sorted(candidates, key=lambda o: o.score, reverse=True)


def wall_thickness(mesh: trimesh.Trimesh, samples: int = THICKNESS_SAMPLES) -> ThinWalls:
    """Espessura local: raio disparado de pontos da superfície para dentro (-normal)."""
    rng = np.random.default_rng(0)
    areas = mesh.area_faces
    faces = rng.choice(len(mesh.faces), size=min(samples, len(mesh.faces)), p=areas / areas.sum())
    normals = mesh.face_normals[faces]
    origins = mesh.triangles_center[faces] - normals * 1e-4
    locations, ray_index, _ = mesh.ray.intersects_location(origins, -normals, multiple_hits=False)
    thickness = np.full(len(faces), np.inf)
    thickness[ray_index] = np.linalg.norm(locations - origins[ray_index], axis=1)
    finite = thickness[np.isfinite(thickness)]
    return ThinWalls(
        sampled_points=len(faces),
        below_line_width={
            f"{nozzle:.1f}": round(float((thickness < nozzle * LINE_WIDTH_FACTOR).mean()), 4)
            for nozzle in NOZZLES
        },
        thickness_p5_mm=round(float(np.percentile(finite, 5)), 2) if len(finite) else None,
    )


def printer_fit(dimensions: np.ndarray, printer: Printer) -> PrinterFit:
    bed = np.array([printer.bed_x, printer.bed_y, printer.max_z])
    # Permite girar a peça 90° em Z: compara as duas maiores medidas do plano com a mesa.
    xy = np.sort(dimensions[:2])[::-1]
    bed_xy = np.sort(bed[:2])[::-1]
    limits = np.concatenate([bed_xy / np.maximum(xy, 1e-9), [bed[2] / max(dimensions[2], 1e-9)]])
    max_scale = float(limits.min())
    return PrinterFit(
        printer=printer.model, fits=max_scale >= 1.0, max_uniform_scale=round(max_scale, 3)
    )


def analyze(data: bytes, filename: str, printers: list[Printer]) -> Analysis:
    mesh = load_mesh(data, filename)
    mesh, bodies, fragments = remove_fragments(mesh)
    mesh.apply_translation([0, 0, -mesh.bounds[0][2]])

    warnings = []
    dimensions = mesh.extents
    if dimensions.max() < SUSPICIOUS_MIN_MM:
        warnings.append("units_too_small")
    elif dimensions.max() > SUSPICIOUS_MAX_MM:
        warnings.append("units_too_large")

    boundary, non_manifold = edge_defects(mesh)
    watertight = mesh.is_watertight
    if not watertight:
        warnings.append("not_watertight")
    if fragments:
        warnings.append("fragments_removed")

    normals_z = mesh.face_normals[:, 2]
    centers_z = mesh.triangles_center[:, 2]
    areas = mesh.area_faces
    total_area = float(areas.sum())
    overhangs = []
    for threshold in OVERHANG_THRESHOLDS:
        area = float(areas[overhang_mask(normals_z, centers_z, threshold)].sum())
        overhangs.append(Overhang(threshold, round(area, 1), round(area / total_area, 4)))

    contact = contact_area(normals_z, centers_z, areas)
    # Altura dividida pelo "diâmetro" equivalente da área de apoio: alto e fino tende a tombar.
    base_width = 2 * np.sqrt(contact / np.pi) if contact > 0 else 0.0
    slenderness = float(dimensions[2] / base_width) if base_width else float("inf")
    if slenderness > 3:
        warnings.append("tipping_risk")

    unique_fits = {p.model: p for p in printers}
    return Analysis(
        filename=PurePath(filename).name,
        triangles=len(mesh.faces),
        dimensions_mm=np.round(dimensions, 2).tolist(),
        volume_mm3=round(float(abs(mesh.volume if watertight else mesh.convex_hull.volume)), 1),
        volume_is_estimate=not watertight,
        surface_area_mm2=round(total_area, 1),
        health=MeshHealth(
            watertight=watertight,
            winding_consistent=bool(mesh.is_winding_consistent),
            bodies=bodies,
            fragments_removed=fragments,
            boundary_edges=boundary,
            non_manifold_edges=non_manifold,
            degenerate_faces=int((areas < 1e-12).sum()),
        ),
        overhangs=overhangs,
        contact_area_mm2=round(contact, 1),
        slenderness=round(slenderness, 2) if np.isfinite(slenderness) else None,
        thin_walls=wall_thickness(mesh),
        fits=[printer_fit(dimensions, p) for p in unique_fits.values()],
        orientations=suggest_orientations(mesh),
        warnings=warnings,
    )
