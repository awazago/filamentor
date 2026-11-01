"""São Miguel Arcanjo — Coleção de Santos Filamentor (peça nº 1).

Iconografia: o Arcanjo de pé sobre o dragão (Ap 12,7-9), couraça romana, túnica,
manto, asas abertas descendo até o chão, auréola, lança com cruz cravada no
pescoço do dragão e escudo com a cruz.

Projetado para FDM em uma cor (PLA mármore branco) na Bambu Lab A1 / A1 mini:
- tudo nasce da base: asas, manto, lança e escudo tocam a rocha/pedestal;
- braços descem do ombro até um ponto apoiado (mão na lança / no escudo);
- barra da túnica com fundo cônico a 45° e auréola em disco (sem “teto”);
- base plana e larga (Ø 70 mm em escala 1) → dispensa brim.

Uso:
    .venv/bin/python colecao-santos/sao_miguel.py --altura 150 --voxel 0.25
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from sdf import Scene, box_local, ellipsoid_local, frame, norm, to_local, v

# --------------------------------------------------------------------------- terreno

PED_TOP = 8.4
MOUND_C = v(0, 0, 8.0)
MOUND_R = v(30.0, 26.0, 9.5)


def mound_height(x: float, y: float) -> float:
    q = (x / MOUND_R[0]) ** 2 + (y / MOUND_R[1]) ** 2
    if q >= 1:
        return PED_TOP
    return MOUND_C[2] + MOUND_R[2] * math.sqrt(1 - q)


def pedestal(p):
    rho = np.hypot(p[:, 0], p[:, 1])
    z = p[:, 2]
    r = np.where(z < 2.5, 35.0, np.where(z < 4.5, 35.0 - (z - 2.5), 33.0))
    r = r - np.maximum(0.0, 0.7 - np.abs(z - 6.4))  # friso em V (45°)
    return np.maximum.reduce([rho - r, -z, z - PED_TOP])


def rock(p):
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    d = ellipsoid_local(p - MOUND_C, MOUND_R)
    noise = (
        0.9 * np.sin(0.45 * x + 1.0) * np.sin(0.5 * y + 2.0)
        + 0.45 * np.sin(1.1 * x + 0.7 * y) * np.sin(0.9 * y - 0.4 * z)
        + 0.25 * np.sin(2.3 * x - 1.7 * z) * np.sin(2.1 * y + 0.5)
    )
    return np.maximum(d - noise, 7.0 - z)


# --------------------------------------------------------------------------- dragão


def catmull_rom(points: np.ndarray, samples_per_seg: int) -> np.ndarray:
    pts = np.vstack([points[0], points, points[-1]])
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for t in np.linspace(0, 1, samples_per_seg, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(
                0.5
                * (
                    2 * p1
                    + (-p0 + p2) * t
                    + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                    + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
                )
            )
    out.append(points[-1])
    return np.asarray(out)


def add_dragon(s: Scene) -> dict:
    ctrl_xy = [
        (11, -13), (4, -12.5), (-5, -11), (-14, -8), (-21, 0), (-19, 11), (-9, 18),
        (4, 20), (15, 14), (21, 4), (24, -6), (26, -12), (25.5, -17), (22.5, -19.5), (20.5, -16.5),
    ]  # fmt: skip
    radii = [4.0, 4.4, 4.8, 5.0, 5.0, 4.8, 4.6, 4.3, 4.0, 3.6, 3.0, 2.4, 1.8, 1.2, 0.6]
    ctrl = np.array(
        [
            (x, y, mound_height(x, y) + 0.35 * r - 0.5)
            for (x, y), r in zip(ctrl_xy, radii, strict=True)
        ]
    )
    path = catmull_rom(np.column_stack([ctrl, radii]), 6)
    pts, rr = path[:, :3], path[:, 3]
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])

    def seg_fn(a, b, ra, rb, s0, length):
        ba = b - a

        def fn(p):
            pa = p - a
            h = np.clip((pa @ ba) / float(ba @ ba), 0.0, 1.0)
            r = ra + (rb - ra) * h
            band = 0.22 * np.sin(2 * np.pi * (s0 + h * length) / 2.0)  # anéis de escama
            return np.linalg.norm(pa - h[:, None] * ba, axis=1) - (r + band * min(1, ra / 2))

        return fn

    for i in range(len(pts) - 1):
        a, b, ra, rb = pts[i], pts[i + 1], rr[i], rr[i + 1]
        m = max(ra, rb) + 1.0
        s.add(
            seg_fn(a, b, ra, rb, arc[i], arc[i + 1] - arc[i]),
            np.minimum(a, b) - m,
            np.maximum(a, b) + m,
            k=0.4,
            name="dragão-corpo",
        )
    # crista de espinhos no dorso
    for i in range(2, len(pts) - 14, 3):
        tan = norm(pts[i + 1] - pts[i - 1])
        base = pts[i] + v(0, 0, rr[i] * 0.75)
        tip = pts[i] + v(0, 0, rr[i] + 2.0 * min(1.0, rr[i] / 4)) - tan * 1.2
        s.capsule(base, tip, 0.9 * min(1.0, rr[i] / 3.5), 0.15, k=0.4, name="dragão-espinho")

    # cabeça: olha para a frente-direita, apoiada na rocha
    H = v(15.0, -19.0, 14.6)
    f = norm(v(0.25, -1.0, -0.12))
    B = frame(f)  # x=frente, y=lado, z=cima
    side, up = B[1], B[2]
    s.ellipsoid(H, (5.5, 3.7, 3.0), k=1.2, basis=B, name="dragão-crânio")
    s.ellipsoid(H + f * 4.6 - up * 0.2, (4.2, 2.6, 2.0), k=1.0, basis=B, name="focinho")
    jaw_b = frame(f * math.cos(0.3) - up * math.sin(0.3))
    s.ellipsoid(H + f * 3.6 - up * 2.6, (4.3, 2.4, 1.1), k=0.8, basis=jaw_b, name="mandíbula")
    s.ellipsoid(H + f * 6.0 - up * 1.45, (3.2, 1.9, 0.75), k=0.3, basis=B, sub=True, name="boca")
    for sg in (-1, 1):
        s.sphere(H + f * 1.6 + side * sg * 2.6 + up * 1.7, 1.25, k=0.6, name="sobrancelha")
        s.sphere(H + f * 2.4 + side * sg * 2.75 + up * 1.0, 0.75, k=0.2, name="olho")
        s.capsule(
            H - f * 1.5 + side * sg * 2.0 + up * 2.0,
            H - f * 6.5 + side * sg * 3.6 + up * 5.0,
            1.15,
            0.3,
            k=0.6,
            name="chifre",
        )
        s.sphere(H + f * 8.6 + side * sg * 0.9 + up * 0.5, 0.45, k=0.2, sub=True, name="narina")
        for tooth in (5.0, 6.6):  # presas
            a = H + f * tooth + side * sg * 1.6 - up * 0.9
            s.capsule(a, a - up * 1.3 - f * 0.2, 0.45, 0.12, k=0.15, name="presa")
    return {"neck": H - f * 5.0, "path": pts, "radii": rr}


# --------------------------------------------------------------------------- figura


def add_figure(s: Scene, coil_top_left: float) -> dict:
    # ---- pernas (perna esquerda avança e pisa o dragão)
    foot_r_bottom = mound_height(6, -3) - 0.4
    legs = {
        "dir": dict(knee=v(6, -2.5, 41), ankle=v(6.2, -1.0, foot_r_bottom + 3.7)),
        "esq": dict(knee=v(-6, -8.5, 42), ankle=v(-6.2, -10.5, coil_top_left + 3.4)),
    }
    for leg in legs.values():
        knee, ankle = leg["knee"], leg["ankle"]
        s.capsule(knee + v(0, 1.0, 5), knee, 3.6, 3.3, k=1.0, name="coxa")
        s.sphere(knee + v(0, -0.6, 0), 3.0, k=0.8, name="joelheira")
        s.capsule(knee, ankle, 3.0, 2.3, k=0.8, name="canela")
        # caneleira com tiras (botas romanas)
        for t in (0.3, 0.55, 0.8):
            c = knee + (ankle - knee) * t
            r = 3.0 + (2.3 - 3.0) * t
            s.capsule(c + v(-r, -0.2, 0), c + v(r, -0.2, 0), 0.45, k=0.3, name="tira")
        s.ellipsoid(ankle + v(0, -2.8, -1.6), (2.7, 5.0, 2.2), k=1.0, name="pé")
        s.ellipsoid(ankle + v(0, 0.6, -0.4), (2.6, 2.6, 2.4), k=0.8, name="calcanhar")

    # ---- túnica (saia com pregas; fundo cônico a 45° → sem suporte)
    Z_HEM, Z_WAIST, R_HEM, R_WAIST, YS = 44.0, 64.0, 13.5, 9.5, 0.78

    def skirt(p):
        x, y, z = p[:, 0], p[:, 1] + 0.5, p[:, 2]
        t = np.clip((Z_WAIST - z) / (Z_WAIST - Z_HEM), 0, 1)
        phi = np.arctan2(y / YS, x)
        r = R_WAIST + (R_HEM - R_WAIST) * t**1.3
        r = r + (0.25 + 0.75 * t) * np.sin(13 * phi + 0.4)
        rho = np.hypot(x, y / YS)
        side = (rho - r) * 0.72
        bottom_cone = (Z_HEM - (R_HEM - rho)) - z  # cone 45° por baixo da barra
        return np.maximum.reduce([side, z - Z_WAIST - 1.0, bottom_cone, Z_HEM - 0.6 - z])

    s.add(skirt, (-16, -14, 26), (16, 13, 66), k=1.0, name="túnica")
    # tiras de couro (pteruges) sobre a túnica
    for i in range(14):
        ang = -math.pi / 2 + (i - 6.5) * 0.36
        if abs(ang + math.pi / 2) > 1.9:
            continue
        top = v(10.0 * math.cos(ang), -0.5 + 10.0 * YS * math.sin(ang), 64.0)
        bot = v(11.6 * math.cos(ang), -0.5 + 11.6 * YS * math.sin(ang), 55.0)
        s.capsule(top, bot, 1.45, 1.25, k=0.25, name="pteruge")

    # ---- tronco com couraça anatômica
    s.ellipsoid(v(0, 0, 76), (10.3, 6.9, 13.5), k=0.0, name="tronco")
    s.ellipsoid(v(0, -0.6, 82), (11.0, 7.2, 6.6), k=2.0, name="peito")
    for sg in (-1, 1):
        s.ellipsoid(v(sg * 4.0, -5.6, 81.2), (4.4, 2.2, 3.4), k=1.4, name="peitoral")
    for zc in (73.5, 70.0):  # abdômen da couraça
        for sg in (-1, 1):
            s.ellipsoid(v(sg * 2.3, -6.0, zc), (2.0, 1.4, 1.6), k=1.0, name="abdômen")
    s.capsule(v(0, -7.2, 85.5), v(0, -6.6, 68.5), 0.35, k=0.25, sub=True, name="linha-esterno")

    def belt(p):
        x, y, z = p[:, 0], p[:, 1] + 0.3, p[:, 2]
        rho_e = np.hypot(x / 10.0, y / 7.3)
        return np.sqrt(((rho_e - 1.0) * 8.6) ** 2 + (z - 64.8) ** 2) - 1.3

    s.add(belt, (-12, -9, 62.5), (12, 9, 67), k=0.4, name="cinto")
    s.sphere(v(0, -8.0, 64.8), 1.6, k=0.4, name="fivela")

    # ---- ombreiras em lâminas
    for sg in (-1, 1):
        s.ellipsoid(v(sg * 12.4, 0.4, 86.6), (4.8, 4.6, 3.5), k=1.0, name="ombreira")
        s.ellipsoid(v(sg * 13.4, 0.4, 84.2), (4.5, 4.4, 2.6), k=0.3, name="ombreira-2")
        s.ellipsoid(v(sg * 14.2, 0.4, 82.2), (4.0, 4.0, 2.2), k=0.3, name="ombreira-3")

    # ---- braço direito: segura a lança e crava no dragão (mão = ponto mais baixo)
    sh_r, el_r, ha_r = v(12.5, 0.5, 85.5), v(19.5, -3.0, 80.5), v(14.0, -14.0, 78.0)
    s.capsule(sh_r, el_r, 3.2, 2.9, k=1.0, name="braço-dir")
    s.capsule(el_r, ha_r, 2.8, 2.3, k=0.8, name="antebraço-dir")
    s.capsule(el_r + (ha_r - el_r) * 0.45, el_r + (ha_r - el_r) * 0.8, 2.85, 2.55, k=0.3)
    s.ellipsoid(ha_r + v(0, 0, 0.5), (2.6, 2.6, 3.0), k=0.8, name="mão-dir")
    s.capsule(ha_r + v(-1.8, -1.4, 2.4), ha_r + v(-1.8, -1.4, -1.6), 0.95, k=0.5, name="dedos")

    # ---- braço esquerdo: desce até o escudo
    sh_l, el_l, ha_l = v(-12.5, 0.5, 85.5), v(-18.5, 1.5, 69.0), v(-15.4, -5.9, 51.5)
    s.capsule(sh_l, el_l, 3.2, 2.9, k=1.0, name="braço-esq")
    s.capsule(el_l, ha_l, 2.8, 2.3, k=0.8, name="antebraço-esq")
    s.capsule(el_l + (ha_l - el_l) * 0.45, el_l + (ha_l - el_l) * 0.8, 2.85, 2.55, k=0.3)
    s.ellipsoid(ha_l, (2.5, 2.5, 2.9), k=0.8, name="mão-esq")

    # ---- pescoço e cabeça (montados na altura de referência e depois baixados)
    head_start = len(s.parts)
    s.capsule(v(0, 0.4, 86.5), v(0, -0.3, 97.5), 3.3, 3.0, k=1.5, name="pescoço")
    HC, HR = v(0, -0.5, 103.0), v(5.2, 6.2, 6.6)
    s.ellipsoid(HC, HR, k=1.6, name="cabeça")
    s.sphere(v(0, -5.4, 98.4), 1.9, k=1.2, name="queixo")
    for sg in (-1, 1):
        s.ellipsoid(v(sg * 3.4, -4.6, 100.6), (1.6, 1.4, 1.6), k=1.0, name="maçã do rosto")
        s.ellipsoid(v(sg * 5.0, -0.3, 102.6), (0.9, 1.4, 2.0), k=0.6, name="orelha")
    s.capsule(v(-3.4, -5.85, 105.2), v(3.4, -5.85, 105.2), 0.75, k=0.6, name="sobrancelhas")
    s.capsule(v(0, -6.35, 104.6), v(0, -7.35, 101.9), 0.55, 1.0, k=0.5, name="nariz")
    for sg in (-1, 1):
        s.sphere(v(sg * 2.15, -6.0, 103.9), 1.1, k=0.4, sub=True, name="órbita")
        s.sphere(v(sg * 2.15, -5.55, 103.9), 0.85, k=0.2, name="olho")
    s.capsule(v(-1.3, -6.75, 100.3), v(1.3, -6.75, 100.3), 0.33, k=0.2, sub=True, name="boca")
    s.ellipsoid(v(0, -6.7, 99.6), (1.1, 0.5, 0.45), k=0.3, name="lábio")

    # cabelo encaracolado (tampa + cachos em espiral de Fibonacci)
    s.ellipsoid(v(0, 0.7, 104.0), (5.5, 6.0, 6.6), k=1.0, name="cabelo")
    n = 170
    gold = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        zz = 1 - 2 * (i + 0.5) / n
        rr = math.sqrt(1 - zz * zz)
        dx, dy, dz = math.cos(gold * i) * rr, math.sin(gold * i) * rr, zz
        if dz < -0.38:
            continue  # abaixo da nuca
        if dy < -0.25 and dz < 0.62:
            continue  # rosto
        if dy < 0.1 and abs(dx) > 0.78 and dz < 0.1:
            continue  # orelhas / maxilar
        c = HC + v(0, 0.9, 1.0) + v(dx, dy, dz) * (HR + v(0.35, 0.1, 0.1))
        s.sphere(c, 1.45 + 0.25 * math.sin(i * 1.7), k=0.35, name="cacho")

    # ---- auréola em disco (vertical, sem teto) com raios em relevo
    HALO_C, HALO_R = v(0, 7.9, 106.0), 10.5
    B_halo = np.stack([v(1, 0, 0), v(0, 0, 1), v(0, 1, 0)])  # local z = eixo y do mundo

    def halo(p):
        q = to_local(p, HALO_C, B_halo)
        rho = np.hypot(q[:, 0], q[:, 1])
        disk = np.maximum(rho - HALO_R, np.abs(q[:, 2]) - 0.7)
        rim = np.sqrt((rho - HALO_R + 0.7) ** 2 + (q[:, 2] + 0.35) ** 2) - 0.85
        ang = np.arctan2(q[:, 1], q[:, 0])
        rays = np.maximum.reduce(
            [
                np.abs(np.sin(8 * ang)) * rho - 0.45,
                rho - HALO_R + 1.8,
                7.0 - rho,
                np.abs(q[:, 2] + 0.85) - 0.35,
            ]
        )
        return np.minimum.reduce([disk, rim, rays])

    s.add(
        halo,
        HALO_C - v(HALO_R + 1, 2, HALO_R + 1),
        HALO_C + v(HALO_R + 1, 2, HALO_R + 1),
        k=0.3,
        name="auréola",
    )

    # ---- manto (casca fina presa nos ombros, desce até a rocha)
    def cloak(p):
        x, y, z = p[:, 0], p[:, 1] + 1.0, p[:, 2]
        rho = np.hypot(x, y)
        phi = np.arctan2(y, x)
        t = np.clip((86.0 - z) / 76.0, 0, 1)
        r = 10.8 + 13.0 * t**1.2 + 1.3 * t**0.7 * np.sin(11 * phi)
        d_rad = np.abs(rho - r) - 1.1
        d_ang = (np.abs(phi - math.pi / 2) - math.radians(62)) * rho
        return np.maximum.reduce([d_rad, d_ang, z - 86.5, 9.0 - z])

    s.translate_since(head_start, v(0, 0, -2.8))

    s.add(cloak, (-26, -2, 8.5), (26, 26, 87), k=0.8, name="manto")
    s.capsule(v(-10.5, 6.0, 85.5), v(10.5, 6.0, 85.5), 3.6, k=2.0, name="manto-gola")
    for sg in (-1, 1):  # broches do manto
        s.sphere(v(sg * 9.0, -2.0, 88.5), 1.5, k=0.5, name="broche")

    return {"hand_r": ha_r, "hand_l": ha_l}


# --------------------------------------------------------------------------- asas


def add_wing(s: Scene, sg: int) -> None:
    root = v(sg * 5.0, 7.0, 84.0)
    ang = math.radians(30)
    u = v(sg * math.cos(ang), math.sin(ang), 0)
    w = np.cross(u, v(0, 0, 1))
    B = np.stack([u, v(0, 0, 1), w])  # local: s (envergadura), t (altura), w (espessura)

    def t_top(s_):
        return 46.0 - 46.0 * ((s_ - 24.0) / 24.0) ** 2

    def s_in(t):
        return np.clip(-0.22 * t, 0.0, 30.0)

    def s_out(t):
        return 24.0 + 9.0 * np.clip((t + 78.0) / 118.0, 0.0, 1.0)

    def outline(ls, lt):
        return np.maximum.reduce([lt - t_top(ls), s_in(lt) - ls, ls - s_out(lt), -79.0 - lt])

    corners = [root + u * a + v(0, 0, b) for a in (-3, 36) for b in (-80, 48)]
    corners += [c + w * sg2 * 4 for c in corners for sg2 in (-1, 1)]
    lo, hi = np.min(corners, axis=0), np.max(corners, axis=0)

    def membrane(p):
        q = to_local(p, root, B)
        return np.maximum(outline(q[:, 0], q[:, 1]), np.abs(q[:, 2]) - 1.0)

    s.add(membrane, lo, hi, k=0.8, name="asa-membrana")

    def feather(sc, tc, half_w, half_l, wc, tilt, rachis=False):
        ca, sa = math.cos(tilt), math.sin(tilt)

        def fn(p):
            q = to_local(p, root, B)
            ds0, dt0 = q[:, 0] - sc, q[:, 1] - tc
            ds = ca * ds0 - sa * dt0
            dt = sa * ds0 + ca * dt0
            dw = q[:, 2] - wc
            tn = dt / half_l
            powr = np.where(tn < 0, 2.0, 6.0)  # ponta afinada para baixo, ombro reto em cima
            a = half_w * np.sqrt(np.clip(1.0 - np.abs(tn) ** powr, 0.0, 1.0))
            a = np.maximum(a, 1e-3)
            lens = (np.sqrt((ds / a) ** 2 + (dw / 0.8) ** 2) - 1.0) * np.minimum(a, 0.8)
            d = np.maximum(lens, np.abs(dt) - half_l)
            if rachis:
                shaft = np.sqrt(ds**2 + (dw - np.sign(wc) * 0.7) ** 2) - 0.42
                shaft = np.maximum(shaft, np.abs(dt + 0.1 * half_l) - 0.85 * half_l)
                d = np.minimum(d, shaft)
            return np.maximum(d, outline(q[:, 0], q[:, 1]) + 0.05)

        rad = max(half_w, half_l) + 1.5
        center = root + u * sc + v(0, 0, tc)
        fl = center - rad
        fh = center + rad
        fl, fh = np.maximum(fl, lo), np.minimum(fh, hi)
        s.add(fn, fl, fh, k=0.12, name="pena")

    rows = [  # (afastamento do bordo, comprimento, largura, w do centro, defasagem)
        (21.0, 22.0, 5.6, 1.35, 0.0),  # secundárias (por baixo)
        (12.0, 10.0, 5.0, 1.6, 0.5),  # coberteiras grandes
        (7.5, 8.0, 4.6, 1.8, 0.0),
        (3.6, 6.5, 4.2, 2.0, 0.5),  # coberteiras pequenas (por cima)
    ]
    for wside in (-1, 1):
        # primárias longas: do meio da asa até a base (nascem apoiadas na rocha)
        for sc in np.arange(8.0, 33.0, 4.3):
            ts = np.linspace(-79, 46, 600)
            ok = (s_in(ts) <= sc - 1.0) & (sc + 1.0 <= s_out(ts)) & (ts <= t_top(sc) - 15.0)
            if ok.sum() < 10:
                continue
            t_lo, t_hi = ts[ok].min(), ts[ok].max()
            feather(sc, (t_lo + t_hi) / 2, 3.1, (t_hi - t_lo) / 2, wside * 1.1, 0.0, rachis=True)
        for off, length, width, wc, phase in rows:
            step = width * 0.82
            for sc in np.arange(1.5 + phase * step, 33.5, step):
                tc = t_top(sc) - off
                if outline(np.array([sc]), np.array([tc]))[0] > -0.5:
                    continue
                tilt = sg * 0.0 + 0.12 * (sc - 16) / 16
                feather(sc, tc, width / 2, length / 2, wside * wc, tilt, rachis=length > 15)


# --------------------------------------------------------------------------- lança e escudo


def add_spear(s: Scene, x: float, y: float) -> None:
    s.capsule(v(x, y, 12.5), v(x, y, 118.0), 2.25, 1.8, k=0.5, name="haste")
    # lâmina em folha, meio cravada no pescoço do dragão
    s.ellipsoid(v(x, y, 19.0), (3.0, 0.95, 6.0), k=0.6, name="lâmina")
    s.capsule(v(x - 3.2, y, 25.2), v(x + 3.2, y, 25.2), 0.9, k=0.6, name="guarda")
    for zc in (60.0, 96.0):
        s.capsule(v(x, y, zc - 1.2), v(x, y, zc + 1.2), 2.6, k=0.4, name="anel")
    # cruz no topo: braços com seção em losango (faces a 45°, imprimem sem suporte)
    rot = np.stack([v(1, 0, 0), norm(v(0, 1, 1)), norm(v(0, -1, 1))])
    cz = 111.5

    def cross_arm(p):
        q = to_local(p, v(x, y, cz), rot)
        return box_local(q, v(5.2, 1.25, 1.25), 0.35)

    s.add(cross_arm, v(x - 6.5, y - 3, cz - 3), v(x + 6.5, y + 3, cz + 3), k=0.5, name="cruz")
    s.sphere(v(x, y, 118.4), 2.0, k=0.6, name="pomo")


def add_shield(s: Scene, hand: np.ndarray) -> None:
    n = norm(v(-0.8, -0.6, 0))
    h = norm(np.cross(v(0, 0, 1), n))
    C = v(-17.5, -7.5, 45.0)
    B = np.stack([h, v(0, 0, 1), n])
    A, BT, BB = 12.0, 9.0, 27.0

    def outline2(a, b):
        top = (np.hypot(a / A, np.maximum(b, 0) / BT) - 1.0) * A
        kite = (np.abs(a) - A * (1 + np.minimum(b, 0) / BB)) * (BB / math.hypot(A, BB))
        return np.where(b >= 0, top, np.maximum(kite, -BB - b))

    def shield(p):
        q = to_local(p, C, B)
        a, b, c = q[:, 0], q[:, 1], q[:, 2]
        e = outline2(a, b)
        bulge = 1.4 * np.clip(1 - (a / A) ** 2 - ((b - 2) / 20) ** 2, 0, 1)
        face = c - 0.7 * bulge
        body = np.maximum(e, np.abs(face) - 1.2)
        rim = np.maximum.reduce([e, -e - 1.6, np.abs(face - 0.5) - 1.6])
        cross2 = np.minimum(
            box_local(np.column_stack([a, b + 2.0, 0 * a]), v(1.5, 16.0, 1.0), 0.4),
            box_local(np.column_stack([a, b - 5.0, 0 * a]), v(7.5, 1.5, 1.0), 0.4),
        )
        cross3 = np.maximum(cross2, np.abs(face - 1.55) - 0.75)
        boss = ellipsoid_local(np.column_stack([a, b - 5.0, face - 1.6]), v(2.4, 2.4, 1.6))
        return np.minimum.reduce([body, rim, cross3, boss])

    m = 30
    s.add(shield, C - m, C + v(m, m, 12), k=0.5, name="escudo")
    s.capsule(hand, C + v(0, 0, 6.0) - n * 0.8, 1.6, k=0.8, name="alça")


# --------------------------------------------------------------------------- montagem


def build_scene() -> Scene:
    s = Scene()
    s.add(pedestal, (-36, -36, -0.5), (36, 36, PED_TOP + 0.5), name="pedestal")
    s.add(rock, (-31, -27, 6.5), (31, 27, 19), k=1.5, name="rocha")
    dragon = add_dragon(s)
    # altura do topo do dragão sob o pé esquerdo
    pts, rr = dragon["path"], dragon["radii"]
    i = int(np.argmin(np.hypot(pts[:, 0] + 6.2, pts[:, 1] + 13.0)))
    dist = math.hypot(pts[i, 0] + 6.2, pts[i, 1] + 13.0)
    coil_top = pts[i, 2] + math.sqrt(max(rr[i] ** 2 - dist**2, 0.0))
    fig = add_figure(s, coil_top - 0.6)
    for sg in (-1, 1):
        add_wing(s, sg)
    add_spear(s, 14.0, -14.0)
    add_shield(s, fig["hand_l"])
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--altura", type=float, default=150.0, help="altura final em mm")
    ap.add_argument("--voxel", type=float, default=0.25, help="resolução da grade (mm, escala 1)")
    ap.add_argument("--faces", type=int, default=0, help="simplificar para N faces (0 = não)")
    ap.add_argument("--saida", type=Path, default=Path(__file__).parent / "saida")
    args = ap.parse_args()

    from sdf import to_mesh

    scene = build_scene()
    vol, axes = scene.evaluate(args.voxel)
    mesh = to_mesh(vol, axes, args.voxel)
    print(f"malha bruta: {len(mesh.faces):,} faces, watertight={mesh.is_watertight}")
    if args.faces and len(mesh.faces) > args.faces:
        import trimesh

        verts, faces = __import__("fast_simplification").simplify(
            mesh.vertices, mesh.faces, target_reduction=1 - args.faces / len(mesh.faces)
        )
        simple = trimesh.Trimesh(verts, faces, process=False)
        if simple.is_watertight:
            mesh = simple
        else:
            print("simplificação quebrou a malha; mantendo a malha completa")
        print(f"simplificada: {len(mesh.faces):,} faces, watertight={mesh.is_watertight}")
    # espelha em X: a figura foi modelada com a lança em +X; espelhada, a lança fica
    # na mão direita do santo (à esquerda de quem olha de frente).
    import trimesh

    mesh = trimesh.Trimesh(
        mesh.vertices * np.array([-1.0, 1.0, 1.0]), mesh.faces[:, ::-1], process=False
    )
    mesh.apply_translation([0, 0, -mesh.bounds[0][2]])
    scale = args.altura / mesh.extents[2]
    mesh.apply_scale(scale)
    args.saida.mkdir(parents=True, exist_ok=True)
    stem = f"sao_miguel_arcanjo_{int(round(args.altura))}mm"
    mesh.export(args.saida / f"{stem}.stl")
    mesh.export(args.saida / f"{stem}.3mf")
    ext = mesh.extents
    print(f"escala {scale:.3f} → {ext[0]:.1f} × {ext[1]:.1f} × {ext[2]:.1f} mm")
    print(f"volume {mesh.volume / 1000:.1f} cm³, área {mesh.area / 100:.0f} cm²")
    print(f"arquivos em {args.saida}/{stem}.(stl|3mf)")


if __name__ == "__main__":
    main()
