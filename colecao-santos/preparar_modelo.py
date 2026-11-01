"""Prepara um modelo gerado por IA (Meshy, Hitem3D, Tripo, TRELLIS…) para a coleção.

Etapas:
 1. carrega STL/OBJ/GLB/3MF (GLB/3MF com várias malhas → uma só);
 2. limpa: funde vértices, remove faces degeneradas/duplicadas, descarta fragmentos e
    cascas internas soltas, corrige normais e fecha furos pequenos;
 3. orienta em pé (Z para cima; `--eixo-y-para-cima` para GLB/OBJ, que usam Y para cima)
    e centraliza;
 4. escala para a altura da coleção (padrão 150 mm);
 5. aplaina a base: corta `--corte` mm do fundo (pés/rocha irregulares viram apoio plano)
    e, opcionalmente, adiciona um pedestal cilíndrico chanfrado (`--pedestal`);
 6. roda a análise do Filamentor (malha, overhang, paredes finas, encaixe A1/A1 mini).

    .venv/bin/python colecao-santos/preparar_modelo.py modelo_meshy.glb --eixo-y-para-cima \
        --altura 150 --corte 0.6 --pedestal
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from filamentor.analysis import analyze, remove_fragments  # noqa: E402
from filamentor.catalog import Printer  # noqa: E402

PRINTERS = [
    Printer("Bambu Lab A1 0.4 nozzle", "a1", "A1", 0.4, 256, 256, 256),
    Printer("Bambu Lab A1 mini 0.4 nozzle", "a1m", "A1 mini", 0.4, 180, 180, 180),
]


def load(path: Path) -> trimesh.Trimesh:
    obj = trimesh.load(path, force="scene")
    meshes = [g for g in obj.dump() if isinstance(g, trimesh.Trimesh) and len(g.faces)]
    if not meshes:
        raise SystemExit(f"nenhuma malha encontrada em {path}")
    return trimesh.util.concatenate(meshes)


def clean(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, list[str]]:
    log = []
    mesh = trimesh.Trimesh(mesh.vertices, mesh.faces, process=True)  # funde vértices
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    mesh, bodies, fragments = remove_fragments(mesh)
    if fragments:
        log.append(f"{fragments} fragmento(s) descartado(s)")
    parts = mesh.split(only_watertight=False)
    if len(parts) > 1:
        # cascas totalmente contidas no corpo principal (comuns em IA) não somam nada
        parts = sorted(parts, key=lambda m: m.area, reverse=True)
        main = parts[0]
        keep = [main]
        dropped = 0
        for p in parts[1:]:
            inside = (
                main.is_watertight
                and main.contains(p.vertices[:: max(1, len(p.vertices) // 50)]).all()
            )
            if inside:
                dropped += 1
            else:
                keep.append(p)
        if dropped:
            log.append(f"{dropped} casca(s) interna(s) descartada(s)")
        mesh = trimesh.util.concatenate(keep)
    trimesh.repair.fix_winding(mesh)
    trimesh.repair.fix_inversion(mesh)
    if not mesh.is_watertight:
        import pymeshfix

        fixer = pymeshfix.MeshFix(mesh.vertices, mesh.faces)
        fixer.repair(
            remove_smallest_components=False
        )  # fecha furos e remove auto-interseções / arestas não-manifold
        mesh = trimesh.Trimesh(fixer.points, fixer.faces, process=True)
        log.append("furos fechados (pymeshfix)" if mesh.is_watertight else "malha ainda aberta")
    return mesh, log


def flatten_base(mesh: trimesh.Trimesh, cut: float) -> trimesh.Trimesh:
    if cut <= 0:
        return mesh
    import manifold3d as mf

    m = mf.Manifold(mf.Mesh(mesh.vertices.astype(np.float32), mesh.faces.astype(np.uint32)))
    ext = mesh.extents
    box = mf.Manifold.cube([ext[0] * 3, ext[1] * 3, cut], center=False).translate(
        [-ext[0] * 1.5, -ext[1] * 1.5, -0.001]
    )
    if m.is_empty():
        raise SystemExit("malha não-manifold: o corte da base falhou (rode sem --corte)")
    out = (m - box).to_mesh()
    res = trimesh.Trimesh(out.vert_properties[:, :3], out.tri_verts, process=True)
    res.apply_translation([0, 0, -res.bounds[0][2]])
    return res


def add_pedestal(mesh: trimesh.Trimesh, height: float) -> trimesh.Trimesh:
    import manifold3d as mf

    # raio = maior distância do eixo entre os pontos que tocam a mesa + margem
    v = mesh.vertices
    foot = v[v[:, 2] < 1.0]
    cx, cy = (foot[:, 0].min() + foot[:, 0].max()) / 2, (foot[:, 1].min() + foot[:, 1].max()) / 2
    r = float(np.hypot(foot[:, 0] - cx, foot[:, 1] - cy).max()) + 4.0
    seg = 128
    base = mf.Manifold.cylinder(height - 1.0, r, r, seg).translate([cx, cy, 1.0])
    chamfer = mf.Manifold.cylinder(1.0, r - 1.0, r, seg).translate(
        [cx, cy, 0.0]
    )  # 45°, sem pé de elefante
    ped = base + chamfer
    m = mf.Manifold(mf.Mesh(v.astype(np.float32), mesh.faces.astype(np.uint32))).translate(
        [0, 0, height - 0.4]
    )
    out = (ped + m).to_mesh()
    return trimesh.Trimesh(out.vert_properties[:, :3], out.tri_verts, process=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("entrada", type=Path)
    ap.add_argument("--altura", type=float, default=150.0, help="altura final (mm)")
    ap.add_argument("--eixo-y-para-cima", action="store_true", help="GLB/OBJ com Y para cima")
    ap.add_argument("--girar-z", type=float, default=0.0, help="gira em Z (graus) p/ frente em -Y")
    ap.add_argument("--corte", type=float, default=0.6, help="mm cortados do fundo (0 = não)")
    ap.add_argument("--pedestal", action="store_true", help="adiciona pedestal chanfrado")
    ap.add_argument("--altura-pedestal", type=float, default=6.0)
    ap.add_argument("--saida", type=Path, default=None)
    args = ap.parse_args()

    mesh = load(args.entrada)
    print(f"entrada: {len(mesh.faces):,} faces, {mesh.extents.round(2)} (unidades do arquivo)")
    if args.eixo_y_para_cima:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    if args.girar_z:
        mesh.apply_transform(
            trimesh.transformations.rotation_matrix(np.radians(args.girar_z), [0, 0, 1])
        )
    mesh, log = clean(mesh)
    for line in log:
        print(" -", line)

    ped_h = args.altura_pedestal if args.pedestal else 0.0
    body_h = args.altura - ped_h + (0.4 if args.pedestal else 0.0) + args.corte
    mesh.apply_scale(body_h / mesh.extents[2])
    c = mesh.bounds.mean(axis=0)
    mesh.apply_translation([-c[0], -c[1], -mesh.bounds[0][2]])
    mesh = flatten_base(mesh, args.corte)
    if args.pedestal:
        mesh = add_pedestal(mesh, ped_h)
    mesh.apply_translation([0, 0, -mesh.bounds[0][2]])

    out = args.saida or args.entrada.with_name(f"{args.entrada.stem}_{int(args.altura)}mm.stl")
    mesh.export(out)
    print(f"saída: {out}  ({mesh.extents.round(1)} mm, {len(mesh.faces):,} faces)")

    a = analyze(out.read_bytes(), out.name, PRINTERS)
    d = dataclasses.asdict(a)
    resumo = {
        "malha": d["health"],
        "volume_cm3": round(d["volume_mm3"] / 1000, 1),
        "area_cm2": round(d["surface_area_mm2"] / 100),
        "overhang_45": d["overhangs"][1]["ratio"],
        "contato_mesa_mm2": d["contact_area_mm2"],
        "paredes_finas_bico_0.4": d["thin_walls"]["below_line_width"]["0.4"],
        "cabe": {f["printer"]: f["fits"] for f in d["fits"]},
        "melhor_orientacao": d["orientations"][0]["label"],
        "avisos": d["warnings"],
    }
    print(json.dumps(resumo, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
