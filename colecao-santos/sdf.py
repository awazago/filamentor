"""Mini-motor de SDF (signed distance fields) para esculpir estátuas imprimíveis.

Cada peça da estátua é uma função de distância com uma caixa envolvente (AABB).
A cena é avaliada em uma grade regular, em fatias, e cada peça só é calculada
dentro da própria caixa — isso torna viável usar centenas de primitivas
(penas, cachos de cabelo, escamas) em resolução de impressão (~0,25 mm).

Unidade: milímetros. Eixo Z para cima, mesa em Z = 0, frente da estátua em -Y.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

Vec = np.ndarray
SdfFn = Callable[[Vec], Vec]  # recebe (N, 3) e devolve (N,)


# --------------------------------------------------------------------------- utilidades


def v(*xs: float) -> Vec:
    return np.asarray(xs, dtype=np.float64)


def norm(a: Vec) -> Vec:
    return a / np.linalg.norm(a)


def smin(a: Vec, b: Vec, k: float) -> Vec:
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def smax(a: Vec, b: Vec, k: float) -> Vec:
    return -smin(-a, -b, k)


def frame(forward: Vec, up_hint: Vec | None = None) -> np.ndarray:
    """Base ortonormal (linhas = eixo local x=forward, y=lado, z=cima)."""
    up_hint = v(0, 0, 1) if up_hint is None else up_hint
    f = norm(forward)
    side = np.cross(up_hint, f)
    if np.linalg.norm(side) < 1e-6:
        side = np.cross(v(0, 1, 0), f)
    side = norm(side)
    up = np.cross(f, side)
    return np.stack([f, side, up])


def to_local(p: Vec, center: Vec, basis: np.ndarray) -> Vec:
    return (p - center) @ basis.T


# --------------------------------------------------------------------------- primitivas


def sphere(p: Vec, c: Vec, r: float) -> Vec:
    return np.linalg.norm(p - c, axis=1) - r


def ellipsoid_local(q: Vec, radii: Vec) -> Vec:
    k0 = np.linalg.norm(q / radii, axis=1)
    k1 = np.linalg.norm(q / (radii * radii), axis=1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def ellipsoid(p: Vec, c: Vec, radii: Vec, basis: np.ndarray | None = None) -> Vec:
    q = p - c if basis is None else to_local(p, c, basis)
    return ellipsoid_local(q, np.asarray(radii, dtype=np.float64))


def capsule(p: Vec, a: Vec, b: Vec, ra: float, rb: float | None = None) -> Vec:
    rb = ra if rb is None else rb
    pa = p - a
    ba = b - a
    h = np.clip((pa @ ba) / float(ba @ ba), 0.0, 1.0)
    r = ra + (rb - ra) * h
    return np.linalg.norm(pa - h[:, None] * ba, axis=1) - r


def box_local(q: Vec, half: Vec, round_r: float = 0.0) -> Vec:
    d = np.abs(q) - (np.asarray(half) - round_r)
    outside = np.linalg.norm(np.maximum(d, 0.0), axis=1)
    inside = np.minimum(np.max(d, axis=1), 0.0)
    return outside + inside - round_r


# --------------------------------------------------------------------------- cena


@dataclass
class Part:
    fn: SdfFn
    lo: Vec
    hi: Vec
    k: float = 0.0
    sub: bool = False  # True = subtrai (entalhe)
    name: str = ""


class Scene:
    def __init__(self) -> None:
        self.parts: list[Part] = []

    def add(self, fn: SdfFn, lo, hi, k: float = 0.0, name: str = "") -> None:
        self.parts.append(Part(fn, np.asarray(lo, float), np.asarray(hi, float), k, False, name))

    def cut(self, fn: SdfFn, lo, hi, k: float = 0.0, name: str = "") -> None:
        self.parts.append(Part(fn, np.asarray(lo, float), np.asarray(hi, float), k, True, name))

    # atalhos com caixa automática ---------------------------------------
    def sphere(self, c, r, k=0.0, name="", sub=False):
        c = np.asarray(c, float)
        m = r + k + 0.5
        (self.cut if sub else self.add)(lambda p: sphere(p, c, r), c - m, c + m, k, name)

    def ellipsoid(self, c, radii, k=0.0, basis=None, name="", sub=False):
        c = np.asarray(c, float)
        radii = np.asarray(radii, float)
        m = radii.max() + k + 0.5
        (self.cut if sub else self.add)(
            lambda p: ellipsoid(p, c, radii, basis), c - m, c + m, k, name
        )

    def capsule(self, a, b, ra, rb=None, k=0.0, name="", sub=False):
        a = np.asarray(a, float)
        b = np.asarray(b, float)
        rb = ra if rb is None else rb
        m = max(ra, rb) + k + 0.5
        lo = np.minimum(a, b) - m
        hi = np.maximum(a, b) + m
        (self.cut if sub else self.add)(lambda p: capsule(p, a, b, ra, rb), lo, hi, k, name)

    def translate_since(self, start: int, offset) -> None:
        """Desloca as peças adicionadas a partir do índice `start`."""
        off = np.asarray(offset, float)
        for i in range(start, len(self.parts)):
            part = self.parts[i]
            fn = part.fn
            part.fn = (lambda f: lambda p: f(p - off))(fn)
            part.lo = part.lo + off
            part.hi = part.hi + off

    # avaliação -------------------------------------------------------------
    def bounds(self) -> tuple[Vec, Vec]:
        lo = np.min([p.lo for p in self.parts if not p.sub], axis=0)
        hi = np.max([p.hi for p in self.parts if not p.sub], axis=0)
        return lo, hi

    def evaluate(self, voxel: float, pad: float = 1.5, slab: int = 24, verbose=True):
        lo, hi = self.bounds()
        lo = lo - pad
        hi = hi + pad
        lo[2] = max(lo[2], -voxel)  # nada abaixo da mesa
        xs = np.arange(lo[0], hi[0] + voxel, voxel)
        ys = np.arange(lo[1], hi[1] + voxel, voxel)
        zs = np.arange(lo[2], hi[2] + voxel, voxel)
        vol = np.full((len(xs), len(ys), len(zs)), 50.0, dtype=np.float32)
        if verbose:
            n = vol.size / 1e6
            print(
                f"grade {len(xs)}×{len(ys)}×{len(zs)} = {n:.1f} M pontos, {len(self.parts)} peças"
            )
        t0 = time.time()
        for z0 in range(0, len(zs), slab):
            z1 = min(z0 + slab, len(zs))
            zc = zs[z0:z1]
            block = np.full((len(xs), len(ys), len(zc)), 50.0, dtype=np.float64)
            for part in self.parts:
                m = part.k + 1.0
                if part.hi[2] + m < zc[0] or part.lo[2] - m > zc[-1]:
                    continue
                i0, i1 = np.searchsorted(xs, [part.lo[0] - m, part.hi[0] + m])
                j0, j1 = np.searchsorted(ys, [part.lo[1] - m, part.hi[1] + m])
                k0, k1 = np.searchsorted(zc, [part.lo[2] - m, part.hi[2] + m])
                if i1 <= i0 or j1 <= j0 or k1 <= k0:
                    continue
                gx, gy, gz = np.meshgrid(xs[i0:i1], ys[j0:j1], zc[k0:k1], indexing="ij")
                pts = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)
                d = part.fn(pts).reshape(gx.shape)
                cur = block[i0:i1, j0:j1, k0:k1]
                if part.sub:
                    block[i0:i1, j0:j1, k0:k1] = smax(cur, -d, part.k)
                else:
                    block[i0:i1, j0:j1, k0:k1] = smin(cur, d, part.k)
            vol[:, :, z0:z1] = block.astype(np.float32)
            if verbose:
                el = time.time() - t0
                print(f"  z {zc[0]:6.1f}→{zc[-1]:6.1f} mm  ({el:5.1f} s)", flush=True)
        # mesa: tudo abaixo de z=0 é vazio (garante base plana)
        vol[:, :, zs < 0] = np.maximum(vol[:, :, zs < 0], 0.5)
        return vol, (xs, ys, zs)


def to_mesh(vol, axes, voxel: float):
    import trimesh
    from skimage import measure

    xs, ys, zs = axes
    # valores exatamente na superfície geram vértices repetidos e triângulos de área zero,
    # que quebram a malha quando o fatiador funde vértices do STL → afasta-os de 0.
    vol = vol.copy()
    vol[np.abs(vol) < 2e-3] = 2e-3
    verts, faces, _, _ = measure.marching_cubes(vol, level=0.0, spacing=(voxel,) * 3)
    verts += np.array([xs[0], ys[0], zs[0]])
    mesh = trimesh.Trimesh(
        verts, faces, process=False
    )  # process=True funde vértices próximos e quebra a malha
    # descarta fragmentos soltos (ex.: ponta de detalhe que ficou isolada)
    parts = mesh.split(only_watertight=False)
    if len(parts) > 1:
        parts = sorted(parts, key=lambda m: len(m.faces), reverse=True)
        mesh = parts[0]
    if mesh.volume < 0:
        mesh.invert()
    return mesh
