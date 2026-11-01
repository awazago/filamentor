"""Renderiza vistas (frente, 3/4, perfil, costas) de um STL em PNG, sem OpenGL.

.venv/bin/python colecao-santos/preview.py saida/arquivo.stl saida/preview.png
"""

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402


def render(ax, mesh, azim_deg, title):
    a = np.radians(azim_deg)
    # câmera olhando para +Y girada em torno de Z (azim 0 = frente)
    rot = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    vtx = mesh.vertices @ rot.T
    tri = vtx[mesh.faces]
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    visible = nrm[:, 1] < 0  # face voltada para a câmera (em -Y)
    tri, nrm = tri[visible], nrm[visible]
    order = np.argsort(-tri[:, :, 1].mean(axis=1))  # pintor: do fundo para a frente
    tri, nrm = tri[order], nrm[order]
    light = np.array([-0.45, -0.75, 0.55])
    light /= np.linalg.norm(light)
    shade = np.clip(nrm @ light, 0, 1) * 0.75 + 0.22
    base = np.array([0.93, 0.92, 0.89])  # mármore branco
    colors = np.clip(base[None, :] * shade[:, None], 0, 1)
    pc = PolyCollection(tri[:, :, [0, 2]], facecolors=colors, edgecolors="none", antialiased=False)
    ax.add_collection(pc)
    ax.set_xlim(vtx[:, 0].min() - 3, vtx[:, 0].max() + 3)
    ax.set_ylim(vtx[:, 2].min() - 3, vtx[:, 2].max() + 3)
    ax.set_aspect("equal")
    ax.set_facecolor("#2b2f36")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, color="white", fontsize=11)


def main():
    src, out = sys.argv[1], sys.argv[2]
    zoom = len(sys.argv) > 3 and sys.argv[3] == "rosto"
    mesh = trimesh.load(src)
    if zoom:
        top = mesh.bounds[1][2]
        h = mesh.extents[2]
        zc = mesh.triangles_center
        keep = (
            (zc[:, 2] > top - h * 0.36) & (zc[:, 2] < top - h * 0.17) & (np.abs(zc[:, 0]) < h * 0.2)
        )
        mesh = trimesh.Trimesh(mesh.vertices, mesh.faces[keep], process=False)
        mesh.remove_unreferenced_vertices()
    views = [(0, "Frente"), (35, "3/4"), (90, "Perfil"), (180, "Costas")]
    fig, axes = plt.subplots(1, 4, figsize=(20, 8), facecolor="#2b2f36")
    for ax, (az, title) in zip(axes, views, strict=True):
        render(ax, mesh, az, title)
    plt.tight_layout()
    plt.savefig(out, dpi=110, facecolor=fig.get_facecolor())
    print(out)


if __name__ == "__main__":
    main()
