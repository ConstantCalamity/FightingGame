"""Thornwall Keep -- a northern castle's inner courtyard in winter (grounded medieval).

    "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup \\
        -P Tools/Blender/maps/build_thornwall_keep.py -- [--rebake] [--no-render] [--no-export] [--samples=N]

Outputs (see maplib / CONVENTIONS.md):
  Assets/_Game/Art/Maps/ThornwallKeep/{ThornwallKeep.fbx, T_*.png, materials.json, layout.json}
  ArtSource/Maps/ThornwallKeep.blend
  Logs/maps/ThornwallKeep_game.png, ThornwallKeep_wide.png

Heraldry: the house banner is an original design -- a black thorned branch on a deep red field with a
black border, drawn procedurally in r_banner().
"""
import os
import sys
import math
import random

sys.dont_write_bytecode = True          # keep Tools/ free of __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
import maplib as ML
importlib.reload(ML)

import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix, Euler
from mathutils import noise as mnoise

MAP = 'ThornwallKeep'
TRS = ML.TRS
TAU = math.tau
sm = ML.smoothstep

# wall layout
WALL_Y = -21.5       # curtain wall centre line
WALL_T = 3.0         # thickness  (courtyard face at y = -20)
WALK_Z = 7.5         # wall-walk height
GATE_TX = 6.2        # gate tower centres at x = +-GATE_TX
GATE_TR = 3.7


def C(r, g, b):
    return (r / 255.0, g / 255.0, b / 255.0)


def arr(c):
    return np.array(ML.s2l(c), np.float32)


# =============================================================================================
# Materials
# =============================================================================================
def r_stone(F, res, m, rng):
    t = np.clip(0.5 + (F['nL'] - 0.5) * 0.6 + (F['nM'] - 0.5) * 0.5, 0, 1)
    alb = ML.ramp(t, [(0.0, C(66, 68, 71)), (0.5, C(98, 100, 103)), (1.0, C(132, 133, 133))])
    spk = F['vS']
    alb = alb * (1 - 0.35 * (spk < 0.12) + 0.25 * (spk > 0.9))[..., None]
    alb = alb * (0.86 + 0.28 * F['nF'])[..., None]
    dirt = sm(0.6, 0.88, F['nS'])
    alb = ML.lerp(alb, arr(C(56, 52, 48)), dirt * 0.45)
    lichen = sm(0.8, 0.95, F['nT']) * sm(0.4, 0.7, F['nM'])
    alb = ML.lerp(alb, arr(C(118, 120, 98)), lichen * 0.45)
    crack = (1 - sm(0.0, 0.016, F['vC'])) * sm(0.62, 0.78, F['nC'])
    alb = alb * (1 - 0.6 * crack)[..., None]
    h = (F['nM'] - 0.5) * 0.007 + (F['nF'] - 0.5) * 0.0015 + (spk > 0.9) * 0.0004 - crack * 0.003
    return dict(albedo=alb, height=h, rough=0.8 + (F['nF'] - 0.5) * 0.1 + lichen * 0.08)


STONE_F = {
    'nL': dict(type='noise', f=3, detail=3), 'nM': dict(type='noise', f=12, detail=8),
    'nF': dict(type='noise', f=80, detail=4), 'vS': dict(type='voronoi', f=110, feature='F1', out='Color'),
    'vC': dict(type='voronoi', f=4.5, feature='DISTANCE_TO_EDGE'), 'nC': dict(type='noise', f=6, detail=4),
    'nS': dict(type='noise', fu=5, fv=0.7, detail=6), 'nT': dict(type='noise', f=4, detail=5),
}


def r_wall(F, res, m, rng):
    U, V = ML.warp_coords(res, (F['wU'] - 0.5) * 0.004, (F['wV'] - 0.5) * 0.004)
    L = ML.brick_layout(U, V, rng, rows=8, per_row=(4, 6), row_jitter=0.1, len_jitter=0.3)
    T = m.tiling
    d = np.minimum(L['du'], L['dv']) * T - np.clip(F['nE'] - 0.6, 0, 1) * 0.08
    mortar = 1 - sm(0.006, 0.016, d)
    bev = sm(0.004, 0.035, d)
    t = np.clip(L['rnd'] * 0.45 + F['nL'] * 0.3 + (F['nM'] - 0.5) * 0.35 + 0.12, 0, 1)
    blk = ML.ramp(t, [(0.0, C(70, 72, 75)), (0.5, C(100, 102, 104)), (1.0, C(132, 132, 131))])
    alb = ML.lerp(blk * (0.88 + 0.24 * F['nF'])[..., None], arr(C(150, 148, 142)), mortar)
    dirt = sm(0.6, 0.88, F['nS'])
    alb = ML.lerp(alb, arr(C(60, 56, 52)), dirt * 0.4)
    h = bev * 0.015 + (L['rnd'] - 0.5) * 0.004 * bev + (F['nM'] - 0.5) * 0.005 + (F['nF'] - 0.5) * 0.0012
    return dict(albedo=alb, height=h, rough=0.84 + mortar * 0.06)


WALL_F = {
    'nL': dict(type='noise', f=3, detail=3), 'nM': dict(type='noise', f=14, detail=8),
    'nF': dict(type='noise', f=80, detail=4), 'wU': dict(type='noise', f=7, detail=3),
    'wV': dict(type='noise', f=7, detail=3), 'nS': dict(type='noise', fu=6, fv=1, detail=6),
    'nE': dict(type='noise', f=30, detail=6),
}


def r_cobble(F, res, m, rng):
    vE, vC = F['vE'], F['vC']
    dome = sm(0.0, 0.3, vE) ** 0.7
    hc = dome * 0.035 + (vC - 0.5) * 0.008 + (F['nM'] - 0.5) * 0.003 + (F['nF'] - 0.5) * 0.001
    t = np.clip(vC * 0.65 + F['nL'] * 0.2 + (F['nF'] - 0.5) * 0.15 + 0.08, 0, 1)
    cob = ML.ramp(t, [(0.0, C(50, 51, 54)), (0.4, C(78, 79, 82)), (0.75, C(104, 103, 100)), (1.0, C(120, 112, 100))])
    cob = cob * (0.7 + 0.3 * dome + 0.2 * (F['nF'] - 0.5))[..., None]
    gap = 1 - sm(0.0, 0.09, vE)
    mud = ML.ramp(F['nM'], [(0.0, C(30, 26, 23)), (1.0, C(52, 45, 38))])
    alb = ML.lerp(cob, mud, gap)
    wet = sm(0.66, 0.86, F['nW'])
    alb = alb * (1 - 0.3 * wet)[..., None]
    # snow: packed into the joints everywhere, plus mid-frequency dusting on the stones
    lvl = 0.016 + (F['nA2'] - 0.5) * 0.02 + sm(0.55, 0.85, F['nA']) * 0.012 - wet * 0.012
    snow = sm(-0.002, 0.003, lvl - hc)
    dust = sm(0.62, 0.86, F['nA2']) * dome * 0.55
    snow = np.clip(np.maximum(snow, dust), 0, 1)
    scol = ML.ramp(F['nF'], [(0.0, C(172, 178, 188)), (1.0, C(212, 218, 226))])
    alb = ML.lerp(alb, scol, snow)
    alb = alb * (0.92 + 0.16 * F['nL'])[..., None]
    h = np.maximum(hc, lvl * (snow > 0.5)) + (F['nF'] - 0.5) * 0.001 * snow
    rough = 0.7 - 0.35 * wet * (1 - snow) - 0.2 * gap * (1 - snow) + (F['nF'] - 0.5) * 0.06
    rough = np.where(snow > 0.5, 0.62, rough)
    return dict(albedo=alb, height=h, rough=rough)


COBBLE_F = {
    'vE': dict(type='voronoi', f=32, feature='DISTANCE_TO_EDGE', rand=0.8, seed=77),
    'vC': dict(type='voronoi', f=32, feature='F1', out='Color', rand=0.8, seed=77),
    'nM': dict(type='noise', f=20, detail=6), 'nF': dict(type='noise', f=160, detail=4),
    'nL': dict(type='noise', f=3, detail=4), 'nW': dict(type='noise', f=4, detail=5),
    'nA': dict(type='noise', f=5, detail=7, rough=0.6), 'nA2': dict(type='noise', f=14, detail=5),
}


def r_snow(F, res, m, rng):
    t = np.clip(0.5 + (F['nM'] - 0.5) * 0.6 + (F['nL'] - 0.5) * 0.5, 0, 1)
    alb = ML.ramp(t, [(0.0, C(190, 198, 212)), (0.6, C(222, 228, 236)), (1.0, C(240, 243, 247))])
    dirty = sm(0.8, 0.95, F['nD'])
    alb = ML.lerp(alb, arr(C(150, 146, 140)), dirty * 0.35)
    h = (F['nM'] - 0.5) * 0.016 + (F['nR'] - 0.5) * 0.006 + (F['nF'] - 0.5) * 0.0015
    return dict(albedo=alb, height=h, rough=0.6 + (F['nF'] - 0.5) * 0.1)


SNOW_F = {
    'nM': dict(type='noise', f=6, detail=6), 'nL': dict(type='noise', f=2, detail=3),
    'nF': dict(type='noise', f=90, detail=3), 'nR': dict(type='noise', fu=10, fv=3, detail=4),
    'nD': dict(type='noise', f=3, detail=5),
}


def r_wood(F, res, m, rng):
    U, V = ML.warp_coords(res, None, (F['wV'] - 0.5) * 0.003)
    L = ML.brick_layout(U, V, rng, rows=9, per_row=(1, 2), row_jitter=0.25, len_jitter=0.35)
    T = m.tiling
    rnd = L['rnd']
    seam_v = 1 - sm(0.002, 0.007, L['dv'] * T)
    seam_u = 1 - sm(0.002, 0.006, L['du'] * T)
    seam = np.maximum(seam_v, seam_u)
    rings = 0.5 + 0.5 * np.sin((V * 60 + F['nG'] * 6.0 + rnd * 10) * TAU)
    g = np.clip(F['nG'] * 0.55 + rings * 0.25 + F['nF'] * 0.2, 0, 1)
    wood = ML.ramp(g, [(0.0, C(34, 27, 22)), (0.5, C(58, 46, 36)), (1.0, C(84, 70, 56))])
    wood = wood * (0.8 + 0.4 * rnd)[..., None]
    grey = sm(0.55, 0.85, F['nW'])
    wood = ML.lerp(wood, arr(C(86, 82, 76)), grey * 0.45)
    knot = (1 - sm(0.02, 0.06, F['vK'])) * (rnd > 0.5)
    wood = wood * (1 - 0.5 * knot)[..., None]
    alb = ML.lerp(wood, arr(C(16, 13, 11)), seam)
    h = (g - 0.5) * 0.002 + (F['nF'] - 0.5) * 0.001 - seam * 0.004 + (rnd - 0.5) * 0.002 - knot * 0.001
    return dict(albedo=alb, height=h, rough=0.74 + grey * 0.1)


WOOD_F = {
    'nG': dict(type='noise', fu=2.5, fv=70, detail=6, dist=0.4), 'nF': dict(type='noise', fu=6, fv=200, detail=3),
    'wV': dict(type='noise', f=5, detail=3), 'nW': dict(type='noise', f=3, detail=5),
    'vK': dict(type='voronoi', fu=4, fv=12, feature='F1'),
}


def r_iron(F, res, m, rng):
    rust = sm(0.62, 0.8, F['nR'] * 0.6 + F['nR2'] * 0.4)
    ham = F['vH']
    iron = ML.ramp(np.clip(F['nF'] * 0.5 + ham * 0.5, 0, 1), [(0.0, C(30, 31, 33)), (1.0, C(62, 63, 66))])
    alb = ML.lerp(iron, ML.ramp(F['nK'], [(0.0, C(58, 34, 22)), (1.0, C(104, 62, 36))]), rust)
    h = (ham - 0.5) * 0.0015 + rust * 0.0006
    return dict(albedo=alb, height=h, rough=0.45 + (F['nF'] - 0.5) * 0.15 + rust * 0.4, metal=1 - rust * 0.9)


IRON_F = {
    'nR': dict(type='noise', f=5, detail=8), 'nR2': dict(type='noise', f=18, detail=6),
    'nF': dict(type='noise', f=90, detail=3), 'vH': dict(type='voronoi', f=24, feature='F1'),
    'nK': dict(type='noise', f=30, detail=6),
}


def draw_sigil(res, W, H):
    """Original house sigil: a black thorned branch on red with a black border. Returns coverage (res,res)
    in texture space (row 0 = bottom, u = 0 at the banner's left edge as seen from the front)."""
    px = W / res
    py = H / res
    cov = np.zeros((res, res), np.float32)
    xs = (np.arange(res, dtype=np.float32) + 0.5) * px
    ys = (np.arange(res, dtype=np.float32) + 0.5) * py
    aa = max(px, py) * 1.2

    def window(xmin, xmax, ymin, ymax):
        i0 = max(0, int(xmin / px) - 2)
        i1 = min(res, int(xmax / px) + 3)
        j0 = max(0, int(ymin / py) - 2)
        j1 = min(res, int(ymax / py) + 3)
        X, Y = np.meshgrid(xs[i0:i1], ys[j0:j1])
        return (j0, j1, i0, i1), X, Y

    def capsule(p0, p1, r0, r1):
        (j0, j1, i0, i1), X, Y = window(min(p0[0], p1[0]) - max(r0, r1), max(p0[0], p1[0]) + max(r0, r1),
                                        min(p0[1], p1[1]) - max(r0, r1), max(p0[1], p1[1]) + max(r0, r1))
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L2 = max(dx * dx + dy * dy, 1e-9)
        t = np.clip(((X - p0[0]) * dx + (Y - p0[1]) * dy) / L2, 0, 1)
        d = np.hypot(X - (p0[0] + t * dx), Y - (p0[1] + t * dy)) - (r0 + (r1 - r0) * t)
        c = 1 - sm(-aa, aa, d)
        cov[j0:j1, i0:i1] = np.maximum(cov[j0:j1, i0:i1], c)

    def tri(a, b, c3):
        (j0, j1, i0, i1), X, Y = window(min(a[0], b[0], c3[0]), max(a[0], b[0], c3[0]),
                                        min(a[1], b[1], c3[1]), max(a[1], b[1], c3[1]))
        pts = [a, b, c3]
        area = (b[0] - a[0]) * (c3[1] - a[1]) - (b[1] - a[1]) * (c3[0] - a[0])
        sgn = 1.0 if area > 0 else -1.0
        sd = np.full(X.shape, -1e9, np.float32)
        for k in range(3):
            p, q = pts[k], pts[(k + 1) % 3]
            ex, ey = q[0] - p[0], q[1] - p[1]
            ln = math.hypot(ex, ey) + 1e-9
            # outward distance from edge (positive outside)
            d = -sgn * ((X - p[0]) * ey - (Y - p[1]) * ex) / ln * -1
            sd = np.maximum(sd, d)
        c = 1 - sm(-aa, aa, sd)
        cov[j0:j1, i0:i1] = np.maximum(cov[j0:j1, i0:i1], c)

    def stroke(path, r0, r1, thorn_side_start=1, thorn_every=0.1, thorn_len=0.085, thorn_w=0.035):
        n = len(path)
        for k in range(n - 1):
            t0, t1 = k / (n - 1), (k + 1) / (n - 1)
            capsule(path[k], path[k + 1], r0 + (r1 - r0) * t0, r0 + (r1 - r0) * t1)
        # thorns
        acc = 0.0
        side = thorn_side_start
        for k in range(n - 1):
            p0, p1 = path[k], path[k + 1]
            seg = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            acc += seg
            if acc < thorn_every or k < 1 or k > n - 3:
                continue
            acc = 0.0
            tx, ty = (p1[0] - p0[0]) / seg, (p1[1] - p0[1]) / seg
            nx, ny = -ty * side, tx * side
            r = r0 + (r1 - r0) * k / (n - 1)
            base = (p0[0] + nx * r * 0.7, p0[1] + ny * r * 0.7)
            # thorn leans toward the tip of the branch
            dx, dy = nx * 0.8 + tx * 0.6, ny * 0.8 + ty * 0.6
            dl = math.hypot(dx, dy)
            dx, dy = dx / dl, dy / dl
            tip = (base[0] + dx * thorn_len, base[1] + dy * thorn_len)
            b0 = (base[0] - tx * thorn_w, base[1] - ty * thorn_w)
            b1 = (base[0] + tx * thorn_w, base[1] + ty * thorn_w)
            tri(b0, b1, tip)
            side = -side

    def curve(f, t0, t1, n):
        return [f(t0 + (t1 - t0) * i / (n - 1)) for i in range(n)]

    cx = W / 2

    def stem(t):
        return (cx + 0.15 * W * math.sin(t * math.pi * 1.7 + 0.35), H * (0.14 + 0.7 * t))
    main = curve(stem, 0.0, 1.0, 46)
    stroke(main, 0.055 * W, 0.016 * W, 1, 0.12, 0.1 * W / 1.0, 0.03)
    # pointed tip
    tp = main[-1]
    tri((tp[0] - 0.02 * W, tp[1] - 0.02), (tp[0] + 0.02 * W, tp[1] - 0.02), (tp[0] + 0.01 * W, tp[1] + 0.16))
    # cut end at the bottom (diagonal)
    b = main[0]
    tri((b[0] - 0.07 * W, b[1] + 0.03), (b[0] + 0.07 * W, b[1] - 0.02), (b[0] - 0.06 * W, b[1] - 0.06))
    # side twigs
    for (t, side, ln) in ((0.24, 1, 0.28), (0.42, -1, 0.25), (0.6, 1, 0.28), (0.77, -1, 0.22)):
        p = stem(t)
        q = stem(t + 0.01)
        tx, ty = q[0] - p[0], q[1] - p[1]
        tl = math.hypot(tx, ty)
        tx, ty = tx / tl, ty / tl

        def twig(s, p=p, side=side, ln=ln, tx=tx, ty=ty):
            ang = math.radians(55) * side
            dx = tx * math.cos(ang) - ty * math.sin(ang)
            dy = tx * math.sin(ang) + ty * math.cos(ang)
            bend = 0.35 * s * s
            return (p[0] + (dx * s + (-dy * side) * 0 + tx * bend * 0.3) * ln * W,
                    p[1] + (dy * s + bend * 0.5) * ln * W)
        pts = curve(twig, 0.0, 1.0, 14)
        stroke(pts, 0.024 * W, 0.007 * W, -side, 0.09, 0.07 * W, 0.022)
        e = pts[-1]
        d0 = (pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
        dl = math.hypot(*d0)
        tri((e[0] - d0[1] / dl * 0.012, e[1] + d0[0] / dl * 0.012), (e[0] + d0[1] / dl * 0.012, e[1] - d0[0] / dl * 0.012),
            (e[0] + d0[0] / dl * 0.08, e[1] + d0[1] / dl * 0.08))
    # border (bordure)
    bw = 0.05 * W
    ins = 0.06 * W
    X, Y = np.meshgrid(xs, ys)
    inner = (X > ins + bw) & (X < W - ins - bw) & (Y > 0.1 * H + bw) & (Y < H - ins - bw)
    outer = (X > ins) & (X < W - ins) & (Y > 0.1 * H) & (Y < H - ins)
    cov = np.maximum(cov, (outer & ~inner).astype(np.float32))
    return np.clip(cov, 0, 1)


def r_banner(F, res, m, rng):
    W, H = m.tiling, m.tile_v
    U, V = ML.warp_coords(res)
    wu = 0.5 + 0.5 * np.sin(U * TAU * 400)
    wv = 0.5 + 0.5 * np.sin(V * TAU * 1000)
    weave = np.where(np.sin(U * TAU * 200) * np.sin(V * TAU * 500) > 0, wu, wv)
    t = np.clip(F['nL'] * 0.6 + F['nM'] * 0.4, 0, 1)
    red = ML.ramp(t, [(0.0, C(84, 12, 14)), (0.5, C(112, 18, 20)), (1.0, C(134, 30, 28))])
    sig = draw_sigil(res, W, H)
    black = ML.ramp(t, [(0.0, C(14, 12, 12)), (1.0, C(30, 26, 26))])
    alb = ML.lerp(red, black, sig)
    grime = np.clip(sm(0.55, 0.85, F['nG']) * 0.5 + (1 - V) ** 3 * 0.6, 0, 1)
    alb = ML.lerp(alb, arr(C(46, 32, 28)), grime * 0.45)
    alb = alb * (0.88 + 0.12 * weave + 0.1 * (F['nF'] - 0.5))[..., None]
    h = (weave - 0.5) * 0.0006 + sig * 0.0006 + (F['nM'] - 0.5) * 0.001
    return dict(albedo=alb, height=h, rough=0.9 - sig * 0.15)


BANNER_F = {
    'nL': dict(type='noise', f=2, detail=4), 'nM': dict(type='noise', f=8, detail=6),
    'nG': dict(type='noise', f=3, detail=5), 'nF': dict(type='noise', fu=40, fv=100, detail=3),
}


def r_straw(F, res, m, rng):
    f1, f2 = F['nF1'], F['nF2']
    t = np.clip(f1 * 0.6 + f2 * 0.4, 0, 1)
    alb = ML.ramp(t, [(0.0, C(96, 76, 44)), (0.45, C(150, 122, 70)), (0.8, C(182, 152, 92)), (1.0, C(200, 176, 118))])
    grey = sm(0.55, 0.85, F['nW'])
    alb = ML.lerp(alb, arr(C(128, 120, 102)), grey * 0.5)
    dark = 1 - sm(0.15, 0.4, f2)
    alb = alb * (1 - 0.5 * dark)[..., None]
    h = (f1 - 0.5) * 0.004 + (f2 - 0.5) * 0.003 + (F['nM'] - 0.5) * 0.006
    return dict(albedo=alb, height=h, rough=0.82)


STRAW_F = {
    'nF1': dict(type='noise', fu=5, fv=150, detail=4, dist=0.6), 'nF2': dict(type='noise', fu=12, fv=300, detail=3),
    'nW': dict(type='noise', f=3, detail=5), 'nM': dict(type='noise', f=8, detail=5),
}


def r_plaster(F, res, m, rng):
    t = np.clip(0.5 + (F['nL'] - 0.5) * 0.6 + (F['nM'] - 0.5) * 0.4, 0, 1)
    alb = ML.ramp(t, [(0.0, C(160, 150, 132)), (0.5, C(186, 178, 160)), (1.0, C(204, 198, 182))])
    stain = sm(0.6, 0.9, F['nS'])
    alb = ML.lerp(alb, arr(C(120, 106, 86)), stain * 0.5)
    wattle = sm(0.82, 0.9, F['nP'])
    crack = (1 - sm(0.0, 0.012, F['vC'])) * sm(0.55, 0.75, F['nM'])
    wat = ML.ramp(F['nF'], [(0.0, C(62, 48, 34)), (1.0, C(100, 80, 58))])
    alb = ML.lerp(alb * (1 - 0.5 * crack)[..., None], wat, wattle)
    alb = alb * (0.92 + 0.16 * F['nF'])[..., None]
    h = (F['nM'] - 0.5) * 0.004 + (F['nF'] - 0.5) * 0.001 - wattle * 0.008 - crack * 0.002
    return dict(albedo=alb, height=h, rough=0.9)


PLASTER_F = {
    'nL': dict(type='noise', f=2.5, detail=3), 'nM': dict(type='noise', f=10, detail=7),
    'nS': dict(type='noise', fu=4, fv=1, detail=6), 'nP': dict(type='noise', f=3, detail=6),
    'vC': dict(type='voronoi', f=5, feature='DISTANCE_TO_EDGE'), 'nF': dict(type='noise', f=80, detail=3),
}


def r_fire(F, res, m, rng):
    crack = 1 - sm(0.0, 0.08, F['vE'])
    glow = crack * (0.5 + 0.5 * sm(0.3, 0.7, F['nG'])) + 0.35 * sm(0.7, 0.95, F['nM'])
    coal = ML.ramp(np.clip(F['vC'] * 0.5 + F['nF'] * 0.5, 0, 1), [(0.0, C(16, 13, 11)), (1.0, C(46, 38, 32))])
    gc = ML.ramp(np.clip(glow, 0, 1), [(0.0, C(80, 20, 6)), (0.5, C(255, 104, 24)), (1.0, C(255, 204, 110))])
    alb = ML.lerp(coal, gc, sm(0.1, 0.55, glow))
    h = (1 - crack) * 0.01 + (F['vC'] - 0.5) * 0.008
    return dict(albedo=alb, height=h, rough=0.85)


FIRE_F = {
    'vE': dict(type='voronoi', f=8, feature='DISTANCE_TO_EDGE'),
    'vC': dict(type='voronoi', f=8, feature='F1', out='Color'),
    'nM': dict(type='noise', f=12, detail=6), 'nF': dict(type='noise', f=50, detail=4),
    'nG': dict(type='noise', f=3, detail=3),
}


def materials():
    return [
        ML.MatDef('M_Stone', 2.0, STONE_F, r_stone, seed=31),
        ML.MatDef('M_StoneWall', 4.0, WALL_F, r_wall, seed=32),
        ML.MatDef('M_Cobble', 6.0, COBBLE_F, r_cobble, seed=33),
        ML.MatDef('M_Snow', 3.0, SNOW_F, r_snow, seed=34, ao_strength=0.25, normal_strength=1.5),
        ML.MatDef('M_Wood', 2.0, WOOD_F, r_wood, seed=35, normal_strength=1.5),
        ML.MatDef('M_Iron', 1.0, IRON_F, r_iron, seed=36, ao_strength=0.3, normal_strength=2.5),
        ML.MatDef('M_Banner', 2.0, BANNER_F, r_banner, seed=37, tile_v=5.0, uv_space='normalized',
                  ao_strength=0.2, normal_strength=2.0),
        ML.MatDef('M_Straw', 1.5, STRAW_F, r_straw, seed=38, ao_strength=0.5),
        ML.MatDef('M_Plaster', 2.0, PLASTER_F, r_plaster, seed=39, ao_strength=0.4),
        ML.MatDef('M_Fire', 0.6, FIRE_F, r_fire, seed=40, emission=C(255, 140, 60), emission_intensity=6.0,
                  ao_strength=0.2),
    ]


# =============================================================================================
# helpers
# =============================================================================================
def swap_uv(bm):
    uvl = bm.loops.layers.uv.active
    if uvl is None:
        return bm
    for f in bm.faces:
        for l in f.loops:
            u, v = l[uvl].uv
            l[uvl].uv = (v, u)
    return bm


def beam(B, cn, p0, p1, w=0.2, h=None, mat='M_Wood', bevel=0.015, rot=0.0):
    """A squared timber between two points (grain along its length)."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = d.length
    h = h or w
    bm = ML.bm_box(L, w, h, bevel)
    q = d.normalized().to_track_quat('X', 'Z')
    M = Matrix.Translation((p0 + p1) / 2) @ q.to_matrix().to_4x4() @ Matrix.Rotation(rot, 4, 'X')
    B.add(cn, bm, mat, M, grain=0)


def plank_panel(B, cn, M, w, h, t=0.05, plank=0.22, rng=None, mat='M_Wood', vertical=True, gap=0.008):
    """Panel of individual planks in local XZ (centred on x, from z=0)."""
    rng = rng or random.Random(0)
    n = max(1, int(round((w if vertical else h) / plank)))
    for i in range(n):
        if vertical:
            pw = w / n
            x = -w / 2 + (i + 0.5) * pw
            hh = h * rng.uniform(0.985, 1.0)
            B.add(cn, ML.bm_box(pw - gap, t, hh, 0.006), mat, M @ TRS((x, rng.uniform(-0.006, 0.006), hh / 2)), grain=2)
        else:
            ph = h / n
            z = (i + 0.5) * ph
            B.add(cn, ML.bm_box(w * rng.uniform(0.99, 1.0), t, ph - gap, 0.006), mat,
                  M @ TRS((0, rng.uniform(-0.006, 0.006), z)), grain=0)


def snow_drift(B, x, y, rx, ry, h, rng, rot=0.0, cn='Snow'):
    bm = ML.mound_bm(rx, ry, h, 16, rng, power=1.5, noise_amp=0.3, noise_freq=0.8, sink=0.03, outline=0.4)
    B.add(cn, bm, 'M_Snow', TRS((x, y, 0), (0, 0, rot)), uv='world', uvoff=False, kind='soft')


def wall_drift(B, x0, x1, y, depth, h, rng, cn='Snow', face=1):
    """Long snow drift against a wall running along x; face=+1 means the drift lies at +y of the wall."""
    n = max(3, int((x1 - x0) / 2.5))
    for i in range(n):
        x = x0 + (i + 0.5) * (x1 - x0) / n + rng.uniform(-0.6, 0.6)
        rx = (x1 - x0) / n * rng.uniform(0.75, 1.0)
        snow_drift(B, x, y + face * depth * 0.25, rx, depth * rng.uniform(0.8, 1.2), h * rng.uniform(0.7, 1.2), rng,
                   cn=cn)


def icicles(B, cn, p0, p1, rng, n=None, maxlen=0.35):
    p0, p1 = Vector(p0), Vector(p1)
    n = n or int((p1 - p0).length / 0.25)
    for i in range(n):
        if rng.random() < 0.35:
            continue
        p = p0.lerp(p1, (i + rng.random()) / n)
        L = rng.uniform(0.05, maxlen)
        B.add(cn, ML.bm_cyl(0.025, 0.0, L, 5), 'M_Snow', TRS((p.x, p.y, p.z - L), (0, 0, 0)), kind='soft')


# =============================================================================================
# props
# =============================================================================================
def barrel(B, x, y, rng, rot=0.0, lying=False, cn='Props', snow=True):
    prof = [(0.25, 0.0), (0.29, 0.12), (0.315, 0.3), (0.32, 0.42), (0.315, 0.54), (0.29, 0.72), (0.25, 0.84)]
    bm = ML.bm_lathe(prof, 16, cap_bottom=True, cap_top=True)
    swap_uv(bm)
    M = TRS((x, y, 0.0), (0, 0, rot))
    if lying:
        M = TRS((x, y, 0.3), (math.pi / 2, 0, rot)) @ TRS((0, 0, -0.42))
    B.add(cn, bm, 'M_Wood', M, uv='explicit', kind='soft')
    for z in (0.1, 0.3, 0.54, 0.74):
        r = 0.255 + 0.07 * math.sin(math.pi * z / 0.84) + 0.006
        ring = ML.bm_lathe([(r, z - 0.025), (r + 0.006, z), (r, z + 0.025)], 16, False, False)
        B.add(cn, ring, 'M_Iron', M, uv='explicit', kind='soft')
    if snow and not lying and rng.random() < 0.8:
        ML.snow_on_top(B, 'Snow', x, y, 0.84, 0.44, 0.44, rng, depth=0.07, rot=rot)


def crate(B, x, y, z, s, rng, rot=0.0, cn='Props', snow=True):
    M = TRS((x, y, z), (0, 0, rot))
    B.add(cn, ML.bm_box(s - 0.04, s - 0.04, s - 0.04, 0.01), 'M_Wood', M @ TRS((0, 0, s / 2)), grain=0)
    e = 0.07
    for (a, b) in (((-1, -1), (1, -1)), ((-1, 1), (1, 1))):
        for zz in (e / 2, s - e / 2):
            for yy in (-s / 2 + e / 2, s / 2 - e / 2):
                B.add(cn, ML.bm_box(s, e, e, 0.008), 'M_Wood', M @ TRS((0, yy, zz)), grain=0)
            for xx in (-s / 2 + e / 2, s / 2 - e / 2):
                B.add(cn, ML.bm_box(e, s, e, 0.008), 'M_Wood', M @ TRS((xx, 0, zz)), grain=1)
        break
    for xx in (-s / 2 + e / 2, s / 2 - e / 2):
        for yy in (-s / 2 + e / 2, s / 2 - e / 2):
            B.add(cn, ML.bm_box(e, e, s, 0.008), 'M_Wood', M @ TRS((xx, yy, s / 2)), grain=2)
    if snow and rng.random() < 0.85:
        ML.snow_on_top(B, 'Snow', x, y, z + s, s, s, rng, depth=0.08, rot=rot)


def hay_bale(B, x, y, z, rng, rot=0.0, cn='Props', snow=False):
    M = TRS((x, y, z), (0, 0, rot))
    bm = ML.bm_box(1.0, 0.5, 0.45, 0.07, segs=2)
    ML.bm_noise(bm, 0.015, 6.0, rng.randint(0, 99))
    B.add(cn, bm, 'M_Straw', M @ TRS((0, 0, 0.225)), kind='soft', grain=0)
    for xx in (-0.25, 0.25):
        B.add(cn, ML.bm_box(0.025, 0.52, 0.47, 0.004), 'M_Wood', M @ TRS((xx, 0, 0.225)), kind='soft')
    if snow:
        ML.snow_on_top(B, 'Snow', x, y, z + 0.45, 0.95, 0.45, rng, depth=0.08, rot=rot)


def torch_head(B, cn, pos, rng, scale=1.0, light=True, fx_scale=0.8):
    x, y, z = pos
    B.add(cn, ML.bm_lathe([(0.036, -0.1), (0.06, -0.06), (0.072, 0.06), (0.055, 0.15), (0.0, 0.19)], 8),
          'M_Fire', TRS((x, y, z)), uv='explicit', kind='soft')
    B.add(cn, ML.bm_cyl(0.026, 0.036, 0.52, 8), 'M_Wood', TRS((x, y, z - 0.6)), kind='soft', grain=2)
    for zz in (-0.08, -0.02):
        B.add(cn, ML.bm_cyl(0.05, 0.05, 0.025, 8), 'M_Iron', TRS((x, y, z + zz)), kind='soft')
    B.add_fx('fire', (x, y, z + 0.25), fx_scale)
    if light:
        B.light((x, y, z + 0.5), C(255, 150, 72), 2.6, 8.0)
    B.preview.append(('flame', Vector((x, y, z + 0.12)), 0.55))


def wall_sconce(B, x, y, z, rng, face=(0, 1), cn='Props'):
    """Iron bracket on a wall facing direction `face` (unit xy) holding a torch."""
    fx, fy = face
    a = math.atan2(fy, fx)
    M = TRS((x, y, z), (0, 0, a))
    B.add(cn, ML.bm_box(0.06, 0.22, 0.34, 0.01), 'M_Iron', M @ TRS((0.03, 0, 0)))
    B.add(cn, ML.bm_box(0.36, 0.04, 0.04, 0.005), 'M_Iron', M @ TRS((0.2, 0, -0.08), (0, -0.5, 0)))
    ring = [Vector((0.34 + 0.07 * math.cos(t), 0.07 * math.sin(t), 0.02)) for t in np.linspace(0, TAU, 13)]
    B.add(cn, ML.bm_tube(ring, [0.012] * 13, 5, False, False), 'M_Iron', M, uv='explicit', kind='soft')
    tp = M @ Vector((0.34, 0, 0.32))
    torch_head(B, cn, (tp.x, tp.y, tp.z), rng)


def torch_post(B, x, y, rng, h=2.3, cn='Props'):
    B.add(cn, ML.bm_box(0.18, 0.18, h, 0.02), 'M_Wood', TRS((x, y, h / 2), (0, 0, rng.uniform(-.2, .2))), grain=2)
    for k in range(4):
        a = TAU * k / 4
        beam(B, cn, (x + math.cos(a) * 0.5, y + math.sin(a) * 0.5, 0.0), (x + math.cos(a) * 0.06, y + math.sin(a) * 0.06, 0.55),
             0.08)
    # iron fire basket
    for k in range(6):
        a = TAU * k / 6
        pts = [Vector((x + math.cos(a) * 0.08, y + math.sin(a) * 0.08, h - 0.05)),
               Vector((x + math.cos(a) * 0.2, y + math.sin(a) * 0.2, h + 0.25)),
               Vector((x + math.cos(a) * 0.19, y + math.sin(a) * 0.19, h + 0.38))]
        B.add(cn, ML.bm_tube(pts, [0.012] * 3, 5, False, False), 'M_Iron', uv='explicit', kind='soft')
    for zz in (h + 0.12, h + 0.32):
        rr = 0.13 + (zz - h) * 0.3
        ring = [Vector((x + rr * math.cos(t), y + rr * math.sin(t), zz)) for t in np.linspace(0, TAU, 17)]
        B.add(cn, ML.bm_tube(ring, [0.012] * 17, 5, False, False), 'M_Iron', uv='explicit', kind='soft')
    coals = ML.bm_lathe([(0.17, 0.0), (0.13, 0.08), (0.0, 0.13)], 10, cap_bottom=True, cap_top=False)
    ML.bm_noise(coals, 0.02, 9.0, rng.randint(0, 99), normal_only=True)
    B.add(cn, coals, 'M_Fire', TRS((x, y, h + 0.15)), kind='soft')
    B.add_fx('fire', (x, y, h + 0.35), 1.0)
    B.add_fx('embers', (x, y, h + 0.8), 0.6)
    B.light((x, y, h + 0.7), C(255, 150, 72), 3.2, 9.0)
    B.preview.append(('flame', Vector((x, y, h + 0.25)), 0.75))


def training_dummy(B, x, y, rng, rot=0.0, helm=False, cn='Props'):
    M = TRS((x, y, 0), (0, 0, rot))
    B.add(cn, ML.bm_box(0.13, 0.13, 1.85, 0.015), 'M_Wood', M @ TRS((0, 0, 0.925)), grain=2)
    for a in (0, math.pi / 2):
        B.add(cn, ML.bm_box(0.9, 0.12, 0.1, 0.015), 'M_Wood', M @ TRS((0, 0, 0.05), (0, 0, a)), grain=0)
    B.add(cn, ML.bm_box(1.25, 0.09, 0.09, 0.012), 'M_Wood', M @ TRS((0, 0, 1.42), (0, rng.uniform(-.08, .08), 0)),
          grain=0)
    body = ML.bm_lathe([(0.16, 0.0), (0.22, 0.12), (0.25, 0.32), (0.24, 0.55), (0.2, 0.7), (0.12, 0.76)], 12)
    ML.bm_noise(body, 0.02, 7.0, rng.randint(0, 99))
    swap_uv(body)
    B.add(cn, body, 'M_Straw', M @ TRS((0, 0, 0.82), s=None), uv='explicit', kind='soft')
    for z in (0.92, 1.18, 1.44):
        r = 0.23 if z < 1.4 else 0.18
        ring = ML.bm_lathe([(r, -0.02), (r + 0.012, 0.0), (r, 0.02)], 12, False, False)
        B.add(cn, ring, 'M_Wood', M @ TRS((0, 0, z)), uv='explicit', kind='soft')
    for s in (-1, 1):
        arm = ML.bm_lathe([(0.07, 0.0), (0.09, 0.15), (0.08, 0.35), (0.05, 0.42)], 8)
        B.add(cn, arm, 'M_Straw', M @ TRS((s * 0.3, 0, 1.42), (0, s * math.pi / 2, 0)), uv='explicit', kind='soft')
    head = ML.bm_sphere(0.15, 12, 8)
    ML.bm_noise(head, 0.015, 6.0, rng.randint(0, 99))
    B.add(cn, head, 'M_Straw', M @ TRS((0, 0, 1.78), s=None), kind='soft')
    if helm:
        h = ML.bm_lathe([(0.17, 0.0), (0.175, 0.06), (0.16, 0.14), (0.1, 0.2), (0.0, 0.22)], 12)
        B.add(cn, h, 'M_Iron', M @ TRS((0, 0, 1.76), (rng.uniform(-.15, .15), 0.12, 0)), uv='explicit', kind='soft')
        B.add(cn, ML.bm_box(0.03, 0.06, 0.16, 0.005), 'M_Iron', M @ TRS((0, 0.17, 1.76)))


def weapon_rack(B, x, y, rng, rot=0.0, cn='Props'):
    M = TRS((x, y, 0), (0, 0, rot))
    L = 2.4
    for s in (-1, 1):
        beam(B, cn, M @ Vector((s * L / 2, -0.35, 0)), M @ Vector((s * L / 2, 0, 1.45)), 0.1)
        beam(B, cn, M @ Vector((s * L / 2, 0.35, 0)), M @ Vector((s * L / 2, 0, 1.45)), 0.1)
    beam(B, cn, M @ Vector((-L / 2 - 0.1, 0, 1.4)), M @ Vector((L / 2 + 0.1, 0, 1.4)), 0.1)
    beam(B, cn, M @ Vector((-L / 2, 0.18, 0.35)), M @ Vector((L / 2, 0.18, 0.35)), 0.08)
    # polearms / spears leaning on the top rail
    for i in range(7):
        xx = -L / 2 + 0.25 + i * (L - 0.5) / 6 + rng.uniform(-0.05, 0.05)
        top = M @ Vector((xx + rng.uniform(-0.1, 0.1), -0.05, 2.2 + rng.uniform(-0.2, 0.3)))
        bot = M @ Vector((xx, 0.3, 0.0))
        B.add(cn, ML.bm_tube([bot, top], [0.018, 0.016], 6, True, True, uv_swap=True), 'M_Wood', uv='explicit',
              kind='soft')
        d = (top - bot).normalized()
        R = d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
        kind = i % 3
        if kind == 0:
            blade = ML.bm_prism([(0, 0), (0.035, 0.06), (0.02, 0.3), (0, 0.36), (-0.02, 0.3), (-0.035, 0.06)], 0.012)
            B.add(cn, blade, 'M_Iron', Matrix.Translation(top) @ R @ TRS((0, 0, -0.02)))
        elif kind == 1:
            axe = ML.bm_prism([(0, 0), (0.02, 0), (0.2, -0.08), (0.22, 0.12), (0.02, 0.16), (0, 0.16)], 0.014)
            B.add(cn, axe, 'M_Iron', Matrix.Translation(top) @ R @ TRS((0, 0, -0.3)))
            B.add(cn, ML.bm_cyl(0.008, 0.0, 0.2, 5), 'M_Iron', Matrix.Translation(top) @ R)
        else:
            B.add(cn, ML.bm_cyl(0.012, 0.0, 0.25, 6), 'M_Iron', Matrix.Translation(top) @ R)
    # swords hanging point-down from the lower rail
    for i, xx in enumerate((-0.7, -0.35, 0.4, 0.75)):
        blade = ML.bm_prism([(0, 0), (0.025, 0.08), (0.022, 0.8), (-0.022, 0.8), (-0.025, 0.08)], 0.008)
        B.add(cn, blade, 'M_Iron', M @ TRS((xx, 0.24, 0.02)))
        B.add(cn, ML.bm_box(0.2, 0.03, 0.03, 0.005), 'M_Iron', M @ TRS((xx, 0.24, 0.84)))
        B.add(cn, ML.bm_cyl(0.014, 0.014, 0.16, 6), 'M_Wood', M @ TRS((xx, 0.24, 0.85)), kind='soft')
        B.add(cn, ML.bm_sphere(0.025, 6, 4), 'M_Iron', M @ TRS((xx, 0.24, 1.03)), kind='soft')
    # round shields leaning against the end posts
    for s in (-1, 1):
        sh = ML.bm_cyl(0.42, 0.42, 0.04, 20)
        Ms = M @ TRS((s * (L / 2 + 0.25), 0.25, 0.42), (math.radians(80), 0, s * 0.35)) @ TRS((0, 0, -0.02))
        B.add(cn, sh, 'M_Wood', Ms, grain=1)
        ring = ML.bm_lathe([(0.41, 0.0), (0.43, 0.0), (0.43, 0.05), (0.41, 0.05)], 20, False, False)
        B.add(cn, ring, 'M_Iron', Ms @ TRS((0, 0, -0.005)), uv='explicit', kind='soft')
        B.add(cn, ML.bm_sphere(0.09, 10, 6), 'M_Iron', Ms @ TRS((0, 0, 0.04), s=(1, 1, 0.6)), kind='soft')
    ML.snow_on_top(B, 'Snow', *(M @ Vector((0, 0, 1.45)))[:3], L + 0.2, 0.1, rng, depth=0.04, rot=rot)


def well(B, x, y, rng, cn='Well'):
    ML.ring_wall(B, cn, x, y, 1.0, 0.32, 0.85, rng, 'M_Stone', course=(0.28, 0.3), blen=0.6, bevel=0.02)
    for k in range(10):
        a = TAU * (k + 0.5) / 10
        a0, a1 = a - TAU / 20 + 0.01, a + TAU / 20 - 0.01
        q = []
        for zz in (0.85, 1.0):
            q += [(x + 0.64 * math.cos(a0), y + 0.64 * math.sin(a0), zz), (x + 1.06 * math.cos(a0), y + 1.06 * math.sin(a0), zz),
                  (x + 1.06 * math.cos(a1), y + 1.06 * math.sin(a1), zz), (x + 0.64 * math.cos(a1), y + 0.64 * math.sin(a1), zz)]
        B.add(cn, ML.bm_hex(q, 0.02), 'M_Stone')
    # dark water disk inside
    B.add(cn, ML.bm_cyl(0.68, 0.68, 0.05, 16), 'M_Iron', TRS((x, y, 0.3)))
    for s in (-1, 1):
        B.add(cn, ML.bm_box(0.16, 0.16, 2.4, 0.015), 'M_Wood', TRS((x + s * 0.92, y, 1.2)), grain=2)
    B.add(cn, ML.bm_box(2.2, 0.14, 0.14, 0.015), 'M_Wood', TRS((x, y, 2.3)), grain=0)
    # little gable roof
    for s in (-1, 1):
        q = [(x - 1.25, y, 2.95), (x + 1.25, y, 2.95), (x + 1.25, y + s * 0.95, 2.25), (x - 1.25, y + s * 0.95, 2.25),
             (x - 1.25, y, 3.02), (x + 1.25, y, 3.02), (x + 1.25, y + s * 0.95, 2.32), (x - 1.25, y + s * 0.95, 2.32)]
        B.add(cn, ML.bm_hex(q, 0.01), 'M_Wood', grain=0)
        q = [(x - 1.2, y, 3.02), (x + 1.2, y, 3.02), (x + 1.2, y + s * 0.85, 2.38), (x - 1.2, y + s * 0.85, 2.38),
             (x - 1.2, y, 3.12), (x + 1.2, y, 3.12), (x + 1.2, y + s * 0.85, 2.44), (x - 1.2, y + s * 0.85, 2.44)]
        B.add(cn, ML.bm_hex(q, 0.02), 'M_Snow', uv='world', uvoff=False, kind='soft')
        icicles(B, cn, (x - 1.2, y + s * 0.95, 2.25), (x + 1.2, y + s * 0.95, 2.25), rng, maxlen=0.25)
    # windlass + crank + rope + bucket
    wl = ML.bm_cyl(0.11, 0.11, 1.7, 10)
    B.add(cn, wl, 'M_Wood', TRS((x - 0.85, y, 1.75), (0, math.pi / 2, 0)), kind='soft', grain=2)
    B.add(cn, ML.bm_box(0.04, 0.04, 0.35, 0.005), 'M_Iron', TRS((x + 1.0, y, 1.6)))
    B.add(cn, ML.bm_box(0.25, 0.04, 0.04, 0.005), 'M_Iron', TRS((x + 1.1, y, 1.45)))
    B.add(cn, ML.bm_cyl(0.012, 0.012, 0.65, 5), 'M_Straw', TRS((x + 0.1, y, 1.05)), kind='soft')
    bucket = ML.bm_lathe([(0.15, 0.0), (0.18, 0.3), (0.17, 0.3), (0.0, 0.02)], 12, cap_bottom=True, cap_top=False)
    swap_uv(bucket)
    B.add(cn, bucket, 'M_Wood', TRS((x + 0.85, y + 0.2, 1.0)), uv='explicit', kind='soft')
    ML.snow_on_top(B, 'Snow', x + 0.85, y + 0.2, 1.3, 0.3, 0.3, rng, 0.03)


def cart(B, x, y, rng, rot=0.0, cn='Props'):
    M = TRS((x, y, 0), (0, 0, rot))
    zb = 0.78
    plank_panel(B, cn, M @ TRS((0, 0.65, zb), (math.pi / 2, 0, 0)), 2.6, 1.3, 0.06, 0.26, rng, vertical=True)
    for s in (-1, 1):
        plank_panel(B, cn, M @ TRS((0, s * 0.63, zb), (0, 0, 0)), 2.6, 0.4, 0.05, 0.2, rng, vertical=False)
        beam(B, cn, M @ Vector((-1.3, s * 0.5, zb - 0.05)), M @ Vector((-3.2, s * 0.32, 0.05)), 0.1)
    plank_panel(B, cn, M @ TRS((1.28, 0, zb), (0, 0, math.pi / 2)), 1.3, 0.4, 0.05, 0.2, rng, vertical=False)
    beam(B, cn, M @ Vector((0.2, -0.9, 0.6)), M @ Vector((0.2, 0.9, 0.6)), 0.08)
    for s in (-1, 1):
        cy = s * 0.85
        rim = [Vector((0.2 + 0.6 * math.cos(t), cy, 0.6 + 0.6 * math.sin(t))) for t in np.linspace(0, TAU, 25)]
        B.add(cn, ML.bm_tube(rim, [0.045] * 25, 6, False, False, uv_swap=True), 'M_Wood', M, uv='explicit',
              kind='soft')
        for k in range(8):
            t = TAU * k / 8 + 0.2
            B.add(cn, ML.bm_tube([Vector((0.2, cy, 0.6)), Vector((0.2 + 0.57 * math.cos(t), cy, 0.6 + 0.57 * math.sin(t)))],
                                 [0.025, 0.02], 5, False, False, uv_swap=True), 'M_Wood', M, uv='explicit', kind='soft')
        B.add(cn, ML.bm_cyl(0.1, 0.1, 0.25, 10), 'M_Wood', M @ TRS((0.2, cy - 0.125, 0.6), (-math.pi / 2, 0, 0)),
              kind='soft')
        ring = [Vector((0.2 + 0.64 * math.cos(t), cy, 0.6 + 0.64 * math.sin(t))) for t in np.linspace(0, TAU, 25)]
        B.add(cn, ML.bm_tube(ring, [0.015] * 25, 5, False, False), 'M_Iron', M, uv='explicit', kind='soft')
    hay = ML.mound_bm(1.2, 0.6, 0.55, 10, rng, power=0.7, noise_amp=0.3, noise_freq=2.0, sink=0.0)
    B.add(cn, hay, 'M_Straw', M @ TRS((0, 0, zb + 0.05)), uv='world', kind='soft')
    snow = ML.mound_bm(0.9, 0.45, 0.62, 8, rng, power=0.7, noise_amp=0.3, noise_freq=2.0, sink=0.0)
    B.add('Snow', snow, 'M_Snow', M @ TRS((0.1, 0, zb + 0.06)), uv='world', uvoff=False, kind='soft')


def firewood(B, x, y, rng, rot=0.0, w=2.0, h=1.0, cn='Props'):
    M = TRS((x, y, 0), (0, 0, rot))
    z = 0.06
    row = 0
    while z < h:
        xx = -w / 2 + 0.06
        while xx < w / 2 - 0.06:
            r = rng.uniform(0.06, 0.1)
            L = rng.uniform(0.5, 0.65)
            log = ML.bm_tube([Vector((0, -L / 2, 0)), Vector((0, L / 2, 0))], [r, r * 0.95], 7, True, True, uv_swap=True)
            B.add(cn, log, 'M_Wood', M @ TRS((xx + r, rng.uniform(-0.04, 0.04), z + r), (0, 0, rng.uniform(-.06, .06))),
                  uv='explicit', kind='soft')
            xx += 2 * r + 0.005
        z += 0.17
        row += 1
    ML.snow_on_top(B, 'Snow', *(M @ Vector((0, 0, z + 0.02)))[:3], w, 0.55, rng, 0.08, rot=rot)


def archery_target(B, x, y, rng, rot=0.0, cn='Props'):
    M = TRS((x, y, 0), (0, 0, rot))
    for (a, b) in (((-0.5, -0.35, 0), (0, 0.05, 1.6)), ((0.5, -0.35, 0), (0, 0.05, 1.6)), ((0, 0.55, 0), (0, 0.05, 1.6))):
        beam(B, cn, M @ Vector(a), M @ Vector(b), 0.07)
    tgt = ML.bm_cyl(0.55, 0.55, 0.28, 20)
    ML.bm_noise(tgt, 0.012, 6.0, rng.randint(0, 99))
    B.add(cn, tgt, 'M_Straw', M @ TRS((0, 0.12, 1.05), (math.radians(-80), 0, 0)), kind='soft', grain=1)
    for k in range(4):
        a, r = rng.uniform(0, TAU), rng.uniform(0, 0.35)
        p = M @ Vector((r * math.cos(a), 0.3, 1.05 + r * math.sin(a)))
        d = (M.to_3x3() @ Vector((rng.uniform(-.2, .2), 1, rng.uniform(-.1, .2)))).normalized()
        B.add(cn, ML.bm_tube([p, p + d * 0.55], [0.006, 0.006], 4, False, False), 'M_Wood', uv='explicit', kind='soft')


def chopping_block(B, x, y, rng, cn='Props'):
    B.add(cn, ML.bm_cyl(0.3, 0.28, 0.5, 12), 'M_Wood', TRS((x, y, 0)), kind='soft', grain=2)
    a = rng.uniform(0, TAU)
    hd = Vector((x + 0.05, y, 0.55))
    B.add(cn, ML.bm_tube([hd, hd + Vector((math.cos(a) * 0.6, math.sin(a) * 0.6, 0.35))], [0.02, 0.018], 6,
                         uv_swap=True), 'M_Wood', uv='explicit', kind='soft')
    axe = ML.bm_prism([(0, 0), (0.02, 0), (0.17, -0.07), (0.19, 0.1), (0.02, 0.14), (0, 0.14)], 0.016)
    B.add(cn, axe, 'M_Iron', TRS((x + 0.05, y, 0.45), (0, 0, a + math.pi / 2)))
    for k in range(5):
        r = rng.uniform(0.6, 1.2)
        b = rng.uniform(0, TAU)
        sp = ML.bm_box(rng.uniform(0.3, 0.45), 0.09, 0.07, 0.01)
        B.add(cn, sp, 'M_Wood', TRS((x + r * math.cos(b), y + r * math.sin(b), 0.035), (0, 0, rng.uniform(0, TAU))),
              grain=0)


def hanging_banner(B, x, y, ztop, w, h, rng, rot=0.0, cn='Banners', pole=True):
    M = TRS((x, y, ztop), (0, 0, rot))
    if pole:
        B.add(cn, ML.bm_cyl(0.035, 0.035, w + 0.5, 8), 'M_Wood', M @ TRS((-(w + 0.5) / 2, 0.07, 0.04), (0, math.pi / 2, 0)),
              kind='soft', grain=2)
        for s in (-1, 1):
            B.add(cn, ML.bm_sphere(0.06, 8, 6), 'M_Iron', M @ TRS((s * (w + 0.5) / 2, 0.07, 0.04)), kind='soft')
    cl = ML.cloth_bm(w, h, 14, 30, rng, folds=2.0, fold_amp=0.045, tatter=0.0, holes=0.0, thickness=0.01,
                     uv_norm=True, swallow=0.0, points=2)
    B.add(cn, cl, 'M_Banner', M @ TRS((0, 0.1, 0.0)), uv='explicit', kind='soft')


def pennant(B, x, y, z, rng, cn='Banners'):
    B.add(cn, ML.bm_cyl(0.05, 0.03, 3.0, 6), 'M_Wood', TRS((x, y, z)), kind='soft', grain=2)
    cl = ML.cloth_bm(0.9, 2.2, 6, 12, rng, folds=1.5, fold_amp=0.12, thickness=0.01, uv_norm=True, swallow=0.35,
                     sway=0.0)
    for v in cl.verts:
        t = -v.co.z / 2.2
        v.co.y += 0.25 * t * t
    B.add(cn, cl, 'M_Banner', TRS((x, y, z + 2.95), (0, -math.pi / 2, 0)), uv='explicit', kind='soft')


# =============================================================================================
# buildings
# =============================================================================================
def timber_frame_face(B, cn, M, L, z0, z1, rng, posts=1.6, braces=True, openings=()):
    """Timber frame on a wall face (local x 0..L, face plane y=0 facing +y) from z0 to z1.
    openings: [(x0, x1, zb, zt)] where rails and braces are omitted."""
    n = max(1, int(round(L / posts)))
    xs = [i * L / n for i in range(n + 1)]
    w = 0.2
    for x in xs:
        xx = min(max(x, w / 2), L - w / 2)
        B.add(cn, ML.bm_box(w, 0.22, z1 - z0, 0.015), 'M_Wood', M @ TRS((xx, 0.0, (z0 + z1) / 2), (0, rng.uniform(-.006, .006), 0)),
              grain=2)
    for z in (z0 + 0.1, z1 - 0.1):
        B.add(cn, ML.bm_box(L + 0.1, 0.24, 0.2, 0.015), 'M_Wood', M @ TRS((L / 2, 0.01, z)), grain=0)
    zm = (z0 + z1) / 2
    for i in range(n):
        xa, xb = xs[i], xs[i + 1]
        blocked = any(o[0] < xb and o[1] > xa for o in openings)
        if not blocked:
            B.add(cn, ML.bm_box(xb - xa - 0.2, 0.2, 0.16, 0.012), 'M_Wood', M @ TRS(((xa + xb) / 2, 0.0, zm)), grain=0)
            if braces and rng.random() < 0.7:
                if rng.random() < 0.5:
                    p0, p1 = (xa + 0.1, 0, z0 + 0.2), (xb - 0.1, 0, zm - 0.08)
                else:
                    p0, p1 = (xa + 0.1, 0, zm + 0.08), (xb - 0.1, 0, z1 - 0.2)
                if rng.random() < 0.5:
                    p0, p1 = (p0[0], 0, p1[2]), (p1[0], 0, p0[2])
                beam(B, cn, M @ Vector(p0), M @ Vector(p1), 0.16, 0.16)


def timber_house(B, x0, x1, yb, yf, hw, rng, roof='thatch', door=None, windows=(), cn='Buildings',
                 chimney=None):
    """Timber-framed building: footprint x0..x1 (along x), yb..yf (front face at yf facing +y).
    Gable roof with ridge along x."""
    w, d = x1 - x0, yf - yb
    plinth = 0.55
    # stone plinth (four sides)
    sides = [(TRS((x0, yf - 0.25, 0)), w), (TRS((x1, yb + 0.25, 0), (0, 0, math.pi)), w),
             (TRS((x0 + 0.25, yb, 0), (0, 0, math.pi / 2)), d), (TRS((x1 - 0.25, yf, 0), (0, 0, -math.pi / 2)), d)]
    for (Ms, L) in sides:
        ML.masonry_wall(B, cn, Ms, L, 0.5, lambda xx: plinth, [], course=(0.27, 0.28), blen=(0.4, 0.8), rng=rng,
                        bevel=0.02, chip=0.3, jitter=0.0)
    # plaster walls
    hp = hw - plinth
    B.add(cn, ML.bm_box(w - 0.3, d - 0.3, hp, 0.02), 'M_Plaster', TRS(((x0 + x1) / 2, (yb + yf) / 2, plinth + hp / 2)))
    # timber frames per face
    ops = []
    if door:
        ops.append((door[0] - x0 - 0.8, door[0] - x0 + 0.8, 0, 2.4))
    for wx in windows:
        ops.append((wx - x0 - 0.6, wx - x0 + 0.6, 1.2, 2.2))
    Mf = TRS((x0, yf - 0.12, 0))
    timber_frame_face(B, cn, Mf, w, plinth, hw, rng, openings=ops)
    Mb = TRS((x1, yb + 0.12, 0), (0, 0, math.pi))
    timber_frame_face(B, cn, Mb, w, plinth, hw, rng)
    Ml = TRS((x0 + 0.12, yb, 0), (0, 0, math.pi / 2))
    timber_frame_face(B, cn, Ml, d, plinth, hw, rng)
    Mr = TRS((x1 - 0.12, yf, 0), (0, 0, -math.pi / 2))
    timber_frame_face(B, cn, Mr, d, plinth, hw, rng)
    # door
    if door:
        dx = door[0]
        dw = door[1] if len(door) > 1 else 1.4
        plank_panel(B, cn, TRS((dx, yf - 0.05, plinth)), dw, 2.1, 0.07, 0.2, rng)
        for zz in (plinth + 0.4, plinth + 1.7):
            B.add(cn, ML.bm_box(dw * 0.8, 0.02, 0.06, 0.004), 'M_Iron', TRS((dx, yf + 0.0, zz)))
        B.add(cn, ML.bm_box(dw + 0.4, 0.26, 0.22, 0.02), 'M_Wood', TRS((dx, yf - 0.1, plinth + 2.2)), grain=0)
        for s in (-1, 1):
            B.add(cn, ML.bm_box(0.2, 0.26, 2.2, 0.015), 'M_Wood', TRS((dx + s * (dw / 2 + 0.1), yf - 0.1, plinth + 1.1)),
                  grain=2)
    for wx in windows:
        B.add(cn, ML.bm_box(0.9, 0.1, 0.8, 0.01), 'M_Iron', TRS((wx, yf - 0.1, plinth + 1.3)))
        for s in (-1, 1):
            plank_panel(B, cn, TRS((wx + s * 0.75, yf + 0.05, plinth + 0.92), (0, 0, s * 0.5)), 0.5, 0.8, 0.04, 0.17, rng)
        B.add(cn, ML.bm_box(1.1, 0.3, 0.12, 0.01), 'M_Wood', TRS((wx, yf + 0.0, plinth + 0.86)), grain=0)
        ML.snow_on_top(B, 'Snow', wx, yf + 0.03, plinth + 0.92, 1.05, 0.26, rng, 0.05)
    # roof (45 deg) with overhang
    ov = 0.6
    hr = d / 2 + ov
    ym = (yb + yf) / 2
    rt = 0.32 if roof == 'thatch' else 0.14
    mat = 'M_Straw' if roof == 'thatch' else 'M_Wood'
    for s in (-1, 1):
        ye = ym + s * (d / 2 + ov)
        ze = hw - ov
        zr = hw + d / 2
        q = [(x0 - 0.5, ym, zr), (x1 + 0.5, ym, zr), (x1 + 0.5, ye, ze), (x0 - 0.5, ye, ze),
             (x0 - 0.5, ym, zr + rt), (x1 + 0.5, ym, zr + rt), (x1 + 0.5, ye, ze + rt), (x0 - 0.5, ye, ze + rt)]
        bm = ML.bm_hex(q, 0.04 if roof == 'thatch' else 0.01)
        B.add(cn, bm, mat, grain=0 if roof != 'thatch' else 1)
        # snow blanket on the roof plane
        sn = ML.bm_hex([(x0 - 0.45, ym, zr + rt), (x1 + 0.45, ym, zr + rt), (x1 + 0.45, ye - s * 0.15, ze + rt + 0.12),
                        (x0 - 0.45, ye - s * 0.15, ze + rt + 0.12),
                        (x0 - 0.45, ym, zr + rt + 0.2), (x1 + 0.45, ym, zr + rt + 0.2),
                        (x1 + 0.45, ye - s * 0.15, ze + rt + 0.26), (x0 - 0.45, ye - s * 0.15, ze + rt + 0.26)], 0.08, 2)
        B.add('Snow', sn, 'M_Snow', uv='world', uvoff=False, kind='soft')
        icicles(B, cn, (x0 - 0.4, ye - s * 0.1, ze + rt * 0.5), (x1 + 0.4, ye - s * 0.1, ze + rt * 0.5), rng, maxlen=0.4)
    B.add(cn, ML.bm_box(w + 1.0, 0.22, 0.22, 0.02), 'M_Wood', TRS(((x0 + x1) / 2, ym, hw + d / 2 + 0.05)), grain=0)
    # gables: plaster triangles + timbers
    for (gx, sg) in ((x0 + 0.15, -1), (x1 - 0.15, 1)):
        tri = ML.bm_prism([(-d / 2 + 0.15, 0), (d / 2 - 0.15, 0), (0, d / 2 - 0.15)], 0.24)
        B.add(cn, tri, 'M_Plaster', TRS((gx, ym, hw), (0, 0, math.pi / 2)))
        beam(B, cn, (gx + sg * 0.05, ym, hw), (gx + sg * 0.05, ym, hw + d / 2 - 0.1), 0.2)
        for s in (-1, 1):
            beam(B, cn, (gx + sg * 0.05, ym + s * (d / 2 - 0.2), hw + 0.1), (gx + sg * 0.05, ym + s * 0.5, hw + d / 2 - 0.6), 0.16)
            beam(B, cn, (gx + sg * 0.32, ym + s * (d / 2 + ov - 0.05), hw - ov + 0.25), (gx + sg * 0.32, ym, hw + d / 2 + 0.35),
                 0.14, 0.24)
    if chimney:
        cx, cy = chimney
        h = hw + d / 2 + 1.4
        for z in np.arange(0, h, 0.32):
            for k in range(4):
                a = k * math.pi / 2
                B.add(cn, ML.bm_box(0.95, 0.24, 0.31, 0.02), 'M_Stone',
                      TRS((cx + math.cos(a) * 0.36, cy + math.sin(a) * 0.36, z + 0.155), (0, 0, a + math.pi / 2 + (z % 0.64 > 0.3) * 0)))
        ML.snow_on_top(B, 'Snow', cx, cy, h + 0.15, 0.95, 0.95, rng, 0.06)


def smithy(B, x0, x1, yb, yf, rng, cn='Buildings'):
    """Open-fronted lean-to forge. Front (open) at yf facing +y, back wall at yb."""
    w, d = x1 - x0, yf - yb
    hb, hf = 4.2, 3.0
    # back wall: stone lower + timber/plaster upper
    Mb = TRS((x1, yb + 0.3, 0), (0, 0, math.pi))
    ML.masonry_wall(B, cn, Mb, w, 0.6, lambda xx: 1.8, [], course=(0.3, 0.36), blen=(0.45, 0.9), rng=rng, bevel=0.025)
    B.add(cn, ML.bm_box(w, 0.22, hb - 1.8, 0.02), 'M_Plaster', TRS(((x0 + x1) / 2, yb + 0.3, 1.8 + (hb - 1.8) / 2)))
    Mbf = TRS((x0, yb + 0.43, 0))
    timber_frame_face(B, cn, Mbf, w, 1.8, hb, rng, posts=1.5)
    # side wall (outer end) planked
    for s, xx in ((1, x1), (-1, x0)):
        if s < 0:
            continue
        Ms = TRS((xx - 0.1, (yb + yf) / 2, 0), (0, 0, math.pi / 2))
        plank_panel(B, cn, Ms, d, hf, 0.06, 0.22, rng)
    # front posts + beam
    for i in range(4):
        x = x0 + 0.15 + i * (w - 0.3) / 3
        B.add(cn, ML.bm_box(0.22, 0.22, hf, 0.02), 'M_Wood', TRS((x, yf, hf / 2)), grain=2)
        if i < 3:
            beam(B, cn, (x + 0.1, yf, hf - 0.7), (x + 0.75, yf, hf - 0.1), 0.14)
        if i > 0:
            beam(B, cn, (x - 0.1, yf, hf - 0.7), (x - 0.75, yf, hf - 0.1), 0.14)
    B.add(cn, ML.bm_box(w + 0.3, 0.24, 0.24, 0.02), 'M_Wood', TRS(((x0 + x1) / 2, yf, hf + 0.05)), grain=0)
    # shed roof
    ov = 0.7
    q = [(x0 - 0.4, yb - 0.3, hb + 0.2), (x1 + 0.4, yb - 0.3, hb + 0.2), (x1 + 0.4, yf + ov, hf + 0.1 - 0.25),
         (x0 - 0.4, yf + ov, hf + 0.1 - 0.25)]
    q = q + [(p[0], p[1], p[2] + 0.12) for p in q]
    B.add(cn, ML.bm_hex(q, 0.01), 'M_Wood', grain=1)
    sq = [(x0 - 0.35, yb - 0.25, hb + 0.32), (x1 + 0.35, yb - 0.25, hb + 0.32), (x1 + 0.35, yf + ov - 0.1, hf - 0.03),
          (x0 - 0.35, yf + ov - 0.1, hf - 0.03)]
    sq = sq + [(p[0], p[1], p[2] + 0.2) for p in sq]
    B.add('Snow', ML.bm_hex(sq, 0.08, 2), 'M_Snow', uv='world', uvoff=False, kind='soft')
    icicles(B, cn, (x0 - 0.3, yf + ov - 0.05, hf - 0.1), (x1 + 0.3, yf + ov - 0.05, hf - 0.1), rng, maxlen=0.5)
    # forge hearth + hood + chimney
    fx, fy = x1 - 1.6, yb + 1.2
    for z in (0.0, 0.3, 0.6):
        for k in range(3):
            B.add(cn, ML.bm_box(0.7, 1.6, 0.3, 0.02), 'M_Stone', TRS((fx - 0.7 + k * 0.7, fy, z + 0.15), (0, 0, rng.uniform(-.02, .02))))
    coals = ML.bm_lathe([(0.75, 0.0), (0.6, 0.1), (0.3, 0.18), (0.0, 0.2)], 14, cap_bottom=True, cap_top=False)
    ML.bm_noise(coals, 0.03, 7.0, 3, normal_only=True)
    B.add(cn, coals, 'M_Fire', TRS((fx, fy, 0.9), s=None), kind='soft')
    B.add_fx('fire', (fx, fy, 1.05), 1.2)
    B.add_fx('embers', (fx, fy, 1.6), 0.8)
    B.light((fx, fy + 0.9, 1.6), C(255, 136, 60), 3.6, 10.0)
    B.preview.append(('flame', Vector((fx, fy, 0.95)), 0.6))
    hood = ML.bm_hex([(fx - 1.1, fy - 0.8, 2.0), (fx + 1.1, fy - 0.8, 2.0), (fx + 1.1, fy + 0.8, 2.0), (fx - 1.1, fy + 0.8, 2.0),
                      (fx - 0.4, fy - 0.4, 3.2), (fx + 0.4, fy - 0.4, 3.2), (fx + 0.4, fy + 0.2, 3.2), (fx - 0.4, fy + 0.2, 3.2)], 0.03)
    B.add(cn, hood, 'M_Stone')
    for z in np.arange(3.2, hb + 2.0, 0.34):
        B.add(cn, ML.bm_box(0.9, 0.7, 0.33, 0.02), 'M_Stone', TRS((fx, fy - 0.1, z + 0.17), (0, 0, rng.uniform(-.03, .03))))
    ML.snow_on_top(B, 'Snow', fx, fy - 0.1, hb + 2.0 + 0.04, 0.9, 0.7, rng, 0.06)
    B.add(cn, ML.bm_box(0.1, 0.1, 1.2, 0.01), 'M_Wood', TRS((fx + 1.2, fy + 0.6, 0.6)), grain=2)
    # anvil on a stump
    ax, ay = x0 + w * 0.45, yf - 1.6
    B.add(cn, ML.bm_cyl(0.32, 0.3, 0.55, 12), 'M_Wood', TRS((ax, ay, 0)), kind='soft', grain=2)
    anv = ML.bm_prism([(-0.35, 0), (0.25, 0), (0.25, 0.08), (0.12, 0.12), (0.12, 0.22), (0.35, 0.24), (0.55, 0.3),
                       (0.25, 0.32), (-0.35, 0.32), (-0.35, 0.22), (-0.18, 0.12), (-0.18, 0.08)], 0.22, 0.01)
    B.add(cn, anv, 'M_Iron', TRS((ax - 0.05, ay, 0.55), (0, 0, 0.3)))
    B.add(cn, ML.bm_box(0.05, 0.05, 0.3, 0.005), 'M_Wood', TRS((ax + 0.2, ay + 0.3, 0.12), (0.9, 0, 0.4)), grain=2)
    # quench barrel + tools on the back wall
    barrel(B, x0 + 1.0, yb + 1.1, rng, snow=False, cn=cn)
    for i in range(5):
        xx = x0 + 2.2 + i * 0.35
        B.add(cn, ML.bm_box(0.03, 0.03, 0.7, 0.004), 'M_Iron', TRS((xx, yb + 0.48, 2.2), (0, rng.uniform(-.1, .1), 0)))
        B.add(cn, ML.bm_box(0.12, 0.05, 0.08, 0.005), 'M_Iron', TRS((xx, yb + 0.48, 1.85)))
    B.add(cn, ML.bm_box(2.2, 0.12, 0.08, 0.01), 'M_Wood', TRS((x0 + 2.9, yb + 0.48, 2.55)), grain=0)


def stair(B, x_bot, x_top, y_face, width, z_top, rng, cn='Walkways'):
    """Timber stair against a wall face (y_face, stair at +y of it) rising from x_bot (z=0) to x_top (z=z_top)."""
    run = x_top - x_bot
    n = int(z_top / 0.24)
    sgn = 1 if run > 0 else -1
    yc = y_face + width / 2 + 0.05
    for s in (-1, 1):
        beam(B, cn, (x_bot - sgn * 0.2, yc + s * width / 2, 0.0), (x_top, yc + s * width / 2, z_top), 0.1, 0.32)
    for i in range(n):
        t = (i + 0.5) / n
        x = x_bot + run * t
        z = z_top * t + 0.05
        B.add(cn, ML.bm_box(0.32, width + 0.1, 0.06, 0.008), 'M_Wood', TRS((x, yc, z), (0, 0, rng.uniform(-.02, .02))),
              grain=1)
        if rng.random() < 0.6:
            ML.snow_on_top(B, 'Snow', x, yc + rng.uniform(-0.1, 0.1), z + 0.03, 0.26, width * rng.uniform(0.4, 0.9), rng,
                           0.03)
    # support posts + railing
    for i in range(0, 5):
        t = (i + 0.5) / 5
        x = x_bot + run * t
        z = z_top * t
        B.add(cn, ML.bm_box(0.16, 0.16, z, 0.01), 'M_Wood', TRS((x, yc + width / 2, z / 2)), grain=2)
        B.add(cn, ML.bm_box(0.1, 0.1, 1.05, 0.01), 'M_Wood', TRS((x, yc + width / 2, z + 0.5)), grain=2)
        beam(B, cn, (x, yc + width / 2, z * 0.4), (x, y_face + 0.1, z * 0.85), 0.12)
    beam(B, cn, (x_bot, yc + width / 2, 1.0), (x_top, yc + width / 2, z_top + 1.0), 0.08)
    beam(B, cn, (x_bot, yc + width / 2, 0.5), (x_top, yc + width / 2, z_top + 0.5), 0.06)


# =============================================================================================
# castle architecture
# =============================================================================================
def curtain_walls(B, rng):
    cn = 'CurtainWall'
    for (xa, xb) in ((GATE_TX + 2.6, 31.0), (-31.0, -GATE_TX - 2.6)):
        L = xb - xa
        M = TRS((xa, WALL_Y, 0))
        ops = [ML.Opening(L * 0.5 + rng.uniform(-3, 3), 0.18, 3.4, 4.6, kind='rect', ring=0.3, hood=False)]
        ML.masonry_wall(B, cn, M, L, WALL_T, lambda x: WALK_Z, ops, course=(0.42, 0.56), blen=(0.7, 1.4), rng=rng,
                        chip=0.25, bevel=0.035, plinth=(0.5, 0.12))
        # outer parapet with merlons (seen above the wall from the courtyard)
        Mp = TRS((xa, WALL_Y - WALL_T / 2 + 0.35, 0))
        ML.merlons(B, cn, Mp, L, WALK_Z, 0.7, rng, 'M_Stone', mw=1.1, gw=0.7, mh=1.35, base=0.75)
        # inner low parapet / coping
        Mi = TRS((xa, WALL_Y + WALL_T / 2 - 0.2, 0))
        ML.merlons(B, cn, Mi, L, WALK_Z, 0.4, rng, 'M_Stone', mw=L, gw=0.0, mh=0.0, base=0.45)
        # snow on the wall walk + along the top of the parapet
        for k in range(int(L / 3)):
            x = xa + (k + 0.5) * L / int(L / 3)
            ML.snow_on_top(B, 'Snow', x, WALL_Y + 0.1, WALK_Z, L / int(L / 3), WALL_T - 1.3, rng, 0.14)
            ML.snow_on_top(B, 'Snow', x, WALL_Y + WALL_T / 2 - 0.2, WALK_Z + 0.45, L / int(L / 3), 0.42, rng, 0.07)
        wall_drift(B, xa + 0.5, xb - 0.5, -20.0, 1.8, 0.7, rng, face=1)
    # corner towers (square) at the ends
    for sx in (-1, 1):
        cx = sx * 33.5
        tw = 7.0
        r2 = random.Random(70 + sx)
        for i, (px, py, ang) in enumerate(((cx - tw / 2, WALL_Y + tw / 2, 0.0), (cx + tw / 2, WALL_Y - tw / 2, math.pi),
                                           (cx + tw / 2, WALL_Y + tw / 2, -math.pi / 2), (cx - tw / 2, WALL_Y - tw / 2, math.pi / 2))):
            Mt = TRS((px, py, 0), (0, 0, ang))
            ML.masonry_wall(B, 'Towers', Mt, tw, 1.4, lambda x: 12.0, [ML.Opening(tw / 2, 0.2, 6.0, 7.4, kind='rect', ring=0.3)],
                            course=(0.5, 0.65), blen=(0.9, 1.5), rng=r2, chip=0.2, bevel=0.04)
            Mm = TRS((px, py, 0), (0, 0, ang)) @ TRS((0, 0.35, 0))
            ML.merlons(B, 'Towers', Mm, tw, 12.0, 0.7, r2, 'M_Stone', mw=1.0, gw=0.7, mh=1.3, base=0.6)
        ML.snow_on_top(B, 'Snow', cx, WALL_Y, 12.0, tw - 1.6, tw - 1.6, r2, 0.18)
    # side walls (running toward the camera, enclosing the courtyard)
    for sx in (-1, 1):
        L = 26.0
        ang = -math.pi / 2 if sx > 0 else math.pi / 2
        start = Vector((sx * 32.0, -18.0 if sx > 0 else 8.0, 0))
        M = TRS(start, (0, 0, ang))
        ML.masonry_wall(B, 'SideWalls', M, L, 2.4, lambda x: WALK_Z, [], course=(0.6, 0.8), blen=(1.2, 2.0), rng=rng,
                        chip=0.15, bevel=0.04, jitter=0.004)
        Mp = M @ TRS((0, -0.85, 0))
        ML.merlons(B, 'SideWalls', Mp, L, WALK_Z, 0.7, rng, 'M_Stone', mw=1.1, gw=0.7, mh=1.35, base=0.75)


def gatehouse(B, rng):
    cn = 'Gatehouse'
    # round towers
    for sx in (-1, 1):
        cx, cy = sx * GATE_TX, WALL_Y + 0.3
        r2 = random.Random(100 + sx)
        slits = [(math.pi / 2 + sx * 0.5, 3.0, 4.4, 0.08), (math.pi / 2 - sx * 0.3, 7.2, 8.6, 0.08),
                 (math.pi / 2 + sx * 0.9, 10.4, 11.8, 0.08)]
        ML.ring_wall(B, cn, cx, cy, GATE_TR, 1.3, 14.0, r2, 'M_Stone', course=(0.42, 0.56), blen=1.0, bevel=0.035,
                     slits=slits)
        # plinth batter ring
        for k in range(24):
            a0, a1 = TAU * k / 24, TAU * (k + 1) / 24
            q = []
            for zz, rr in ((0.0, GATE_TR + 0.45), (0.9, GATE_TR + 0.05)):
                q += [(cx + (GATE_TR - 0.6) * math.cos(a0), cy + (GATE_TR - 0.6) * math.sin(a0), zz),
                      (cx + rr * math.cos(a0), cy + rr * math.sin(a0), zz),
                      (cx + rr * math.cos(a1), cy + rr * math.sin(a1), zz),
                      (cx + (GATE_TR - 0.6) * math.cos(a1), cy + (GATE_TR - 0.6) * math.sin(a1), zz)]
            B.add(cn, ML.bm_hex(q, 0.03), 'M_Stone')
        # string course
        for k in range(28):
            a0, a1 = TAU * k / 28, TAU * (k + 1) / 28
            q = []
            for zz, rr in ((9.0, GATE_TR + 0.02), (9.25, GATE_TR + 0.18)):
                q += [(cx + (GATE_TR - 0.5) * math.cos(a0), cy + (GATE_TR - 0.5) * math.sin(a0), zz),
                      (cx + rr * math.cos(a0), cy + rr * math.sin(a0), zz),
                      (cx + rr * math.cos(a1), cy + rr * math.sin(a1), zz),
                      (cx + (GATE_TR - 0.5) * math.cos(a1), cy + (GATE_TR - 0.5) * math.sin(a1), zz)]
            B.add(cn, ML.bm_hex(q, 0.02), 'M_Stone')
        # timber hoarding around the top (wooden gallery on putlog beams) + conical roof
        hz = 14.0
        hr = GATE_TR + 0.7
        n = 18
        for k in range(n):
            a = TAU * k / n
            p0 = Vector((cx + (GATE_TR - 0.6) * math.cos(a), cy + (GATE_TR - 0.6) * math.sin(a), hz - 0.15))
            p1 = Vector((cx + (hr + 0.25) * math.cos(a), cy + (hr + 0.25) * math.sin(a), hz - 0.15))
            beam(B, cn, p0, p1, 0.22, 0.24)
            beam(B, cn, (cx + hr * math.cos(a), cy + hr * math.sin(a), hz), (cx + hr * math.cos(a), cy + hr * math.sin(a), hz + 2.3), 0.16)
            beam(B, cn, (cx + (hr + 0.2) * math.cos(a), cy + (hr + 0.2) * math.sin(a), hz - 0.15),
                 (cx + (GATE_TR - 0.1) * math.cos(a), cy + (GATE_TR - 0.1) * math.sin(a), hz - 1.4), 0.14)
            a0, a1 = a, TAU * (k + 1) / n
            mid = (a0 + a1) / 2
            seg = 2 * hr * math.sin((a1 - a0) / 2)
            Mp = TRS((cx + hr * math.cos(mid) * math.cos((a1 - a0) / 2), cy + hr * math.sin(mid) * math.cos((a1 - a0) / 2), hz),
                     (0, 0, mid + math.pi / 2))
            if k % 3 == 1:
                plank_panel(B, cn, Mp, seg - 0.05, 0.9, 0.05, 0.22, rng)
                plank_panel(B, cn, Mp @ TRS((0, 0, 1.6)), seg - 0.05, 0.7, 0.05, 0.22, rng)
            else:
                plank_panel(B, cn, Mp, seg - 0.05, 2.3, 0.05, 0.22, rng)
        floor = ML.bm_cyl(hr + 0.1, hr + 0.1, 0.12, n)
        B.add(cn, floor, 'M_Wood', TRS((cx, cy, hz - 0.03)), grain=0)
        ML.cone_roof(B, cn, cx, cy, hz + 2.3, hr + 0.15, 6.2, r2, 'M_Wood', 'M_Snow', segs=n, overhang=0.45,
                     finial_mat='M_Iron')
        pennant(B, cx, cy, hz + 2.3 + 6.0, r2)
    # gate block between the towers
    L = 2 * GATE_TX
    M = TRS((-GATE_TX, WALL_Y, 0))
    gw = 4.2
    ops = [ML.Opening(L / 2, gw, 0.0, 3.4, kind='round', ring=0.6, hood=True, shafts=False),
           ML.Opening(L / 2 - 2.2, 0.16, 7.0, 8.3, kind='rect', ring=0.3, hood=False),
           ML.Opening(L / 2 + 2.2, 0.16, 7.0, 8.3, kind='rect', ring=0.3, hood=False)]
    ML.masonry_wall(B, cn, M, L, WALL_T + 1.0, lambda x: 12.0, ops, course=(0.42, 0.56), blen=(0.7, 1.3), rng=rng,
                    chip=0.25, bevel=0.035, snap=(3.4, 7.0))
    Mp = TRS((-GATE_TX + 1.0, WALL_Y + (WALL_T + 1.0) / 2 - 0.35, 0))
    ML.merlons(B, cn, Mp, L - 2.0, 12.0, 0.7, rng, 'M_Stone', mw=1.0, gw=0.7, mh=1.3, base=0.6)
    Mp = TRS((-GATE_TX + 1.0, WALL_Y - (WALL_T + 1.0) / 2 + 0.35, 0))
    ML.merlons(B, cn, Mp, L - 2.0, 12.0, 0.7, rng, 'M_Stone', mw=1.0, gw=0.7, mh=1.3, base=0.6)
    ML.snow_on_top(B, 'Snow', 0, WALL_Y, 12.0, L - 3, WALL_T - 0.6, rng, 0.16)
    # machicolation corbels above the gate
    for k in range(7):
        x = -1.8 + k * 0.6
        bm = ML.bm_box(0.3, 0.6, 0.7, 0.02)
        ML.bm_cut(bm, (0, 0.3, -0.35), (0, 0.6, -0.8))
        B.add(cn, bm, 'M_Stone', TRS((x, WALL_Y + (WALL_T + 1.0) / 2 + 0.3, 10.4)))
    B.add(cn, ML.bm_box(4.6, 0.7, 0.5, 0.03), 'M_Stone', TRS((0, WALL_Y + (WALL_T + 1.0) / 2 + 0.35, 11.0)))
    # portcullis (half raised) in the passage
    py = WALL_Y + 1.2
    zb = 2.4
    for i in range(13):
        x = -2.2 + i * 4.4 / 12
        B.add(cn, ML.bm_box(0.08, 0.08, 6.0, 0.008), 'M_Iron', TRS((x, py, zb + 3.0)))
        sp = ML.bm_cyl(0.05, 0.0, 0.25, 4)
        B.add(cn, sp, 'M_Iron', TRS((x, py, zb + 0.02), (math.pi, 0, math.pi / 4)))
    for j in range(13):
        z = zb + 0.2 + j * 0.45
        B.add(cn, ML.bm_box(4.5, 0.07, 0.07, 0.008), 'M_Iron', TRS((0, py - 0.06, z)))
    # inner wooden gate leaves, swung open against the passage walls
    for s in (-1, 1):
        plank_panel(B, cn, TRS((s * (gw / 2 - 0.12), WALL_Y - 0.4, 0.0), (0, 0, math.pi / 2)), 2.2, 3.3, 0.12, 0.25, rng)
    # passage floor + outside road
    B.add(cn, ML.bm_box(gw + 0.2, WALL_T + 1.2, 0.04, 0.0), 'M_Cobble', TRS((0, WALL_Y, -0.01)), uv='world', uvoff=False)
    # the big house banner over the gate
    hanging_banner(B, 0, WALL_Y + (WALL_T + 1.0) / 2 + 0.75, 11.0, 1.9, 4.75, random.Random(5))
    # sconces flanking the gate
    for s in (-1, 1):
        wall_sconce(B, s * 3.1, WALL_Y + (WALL_T + 1.0) / 2 + 0.02, 3.4, rng, (0, 1))


def outside(B, rng):
    """What is seen through the gate and over the walls: road, snowy fields, hills, distant towers."""
    cn = 'Outside'
    # keep (donjon) behind the gatehouse, off-centre to the right of the frame (-x)
    kx, ky, ks, kh = -15.0, -52.0, 17.0, 31.0
    B.add(cn, ML.bm_box(ks, ks, kh, 0.2), 'M_StoneWall', TRS((kx, ky, kh / 2)))
    B.add(cn, ML.bm_box(ks + 2, ks + 2, 2.0, 0.15), 'M_StoneWall', TRS((kx, ky, 1.0)))
    for sx in (-1, 1):
        for sy in (-1, 1):
            tx, ty = kx + sx * ks / 2, ky + sy * ks / 2
            B.add(cn, ML.bm_cyl(2.2, 2.2, kh + 4, 16), 'M_StoneWall', TRS((tx, ty, 0)))
            ML.cone_roof(B, cn, tx, ty, kh + 4, 2.4, 5.0, rng, 'M_Wood', 'M_Snow', segs=16, overhang=0.3, finial_mat='M_Iron')
    for side in range(4):
        a = side * math.pi / 2
        Mm = TRS((kx, ky, 0), (0, 0, a)) @ TRS((-ks / 2 + 2.2, ks / 2 - 0.35, 0))
        ML.merlons(B, cn, Mm, ks - 4.4, kh, 0.7, rng, 'M_Stone', mw=1.2, gw=0.8, mh=1.5, base=0.7)
    for k in range(3):
        for lvl in range(3):
            B.add(cn, ML.bm_box(0.5, 0.3, 1.6, 0.02), 'M_Iron', TRS((kx - 4 + k * 4, ky + ks / 2 + 0.05, 10 + lvl * 7)))
    ML.snow_on_top(B, 'Snow', kx, ky, kh, ks - 1.6, ks - 1.6, rng, 0.3)
    pennant(B, kx + ks / 2, ky + ks / 2, kh + 9.0, rng)
    # round tower to the left (+x)
    rx, ry = 21.0, -47.0
    B.add(cn, ML.bm_cyl(5.0, 4.6, 25.0, 24), 'M_StoneWall', TRS((rx, ry, 0)))
    ML.cone_roof(B, cn, rx, ry, 25.0, 4.9, 10.0, rng, 'M_Wood', 'M_Snow', segs=24, overhang=0.6, finial_mat='M_Iron')
    pennant(B, rx, ry, 34.5, rng)
    for k in range(4):
        B.add(cn, ML.bm_box(0.4, 0.3, 1.4, 0.02), 'M_Iron', TRS((rx + 2.5 * math.cos(1.2 + k * 0.25), ry + 4.8, 6 + k * 4.5)))
    # outer curtain linking the far towers
    for (xa, xb, y, h) in ((-50, -24, -60, 9), (-6, 16, -58, 9), (26, 60, -54, 9)):
        L = xb - xa
        B.add(cn, ML.bm_box(L, 2.5, h, 0.12), 'M_StoneWall', TRS(((xa + xb) / 2, y, h / 2)))
        ML.merlons(B, cn, TRS((xa, y + 0.9, 0)), L, h, 0.7, rng, 'M_Stone', mw=1.2, gw=0.8, mh=1.4, base=0.5)
        ML.snow_on_top(B, 'Snow', (xa + xb) / 2, y, h, L - 0.4, 1.6, rng, 0.15)
    # road out of the gate
    B.add(cn, ML.heightfield_bm(-2.6, 2.6, -48, -23.5, 4, 12, lambda x, y: 0.02), 'M_Cobble', uv='world', uvoff=False,
          kind='soft')
    # hills + mountains
    for i in range(16):
        sx = -1 if i % 2 else 1
        x = sx * rng.uniform(10, 260) if i > 3 else rng.uniform(-90, 90)
        y = rng.uniform(-330, -110)
        rx_, ry_ = rng.uniform(40, 90), rng.uniform(30, 60)
        h = rng.uniform(18, 50) * (1.0 if y < -200 else 0.6)
        B.add(cn, ML.mound_bm(rx_, ry_, h, 22, rng, power=0.9, noise_amp=0.3, noise_freq=0.03), 'M_Snow',
              TRS((x, y, -1)), uv='world', uvoff=False, kind='soft')
        for k in range(rng.randint(2, 5)):
            s = rng.uniform(4, 12)
            u, v = rng.uniform(-0.45, 0.45), rng.uniform(-0.45, 0.45)
            hz = h * max(0.0, 1 - (u * u + v * v)) ** 0.9 - 1 - s * 0.5
            B.add(cn, ML.rock_bm(rng, (s * 1.5, s, s * 1.3), 2, 0.3, 0.3), 'M_Stone',
                  TRS((x + u * rx_, y + v * ry_, hz), (0, 0, rng.uniform(0, TAU))), kind='soft')
    for i in range(5):
        x = rng.uniform(-260, 260)
        y = rng.uniform(-250, -210)
        h = rng.uniform(55, 90)
        B.add(cn, ML.mound_bm(rng.uniform(90, 140), rng.uniform(50, 80), h, 20, rng, power=0.7, noise_amp=0.35,
                              noise_freq=0.02), 'M_Snow', TRS((x, y, -2)), uv='world', uvoff=False, kind='soft')
    # bare trees outside the walls
    for i in range(18):
        x = rng.uniform(-70, 70)
        y = rng.uniform(-100, -64)
        if abs(x) < 6 and y > -80:
            continue
        bare_tree(B, x, y, random.Random(i * 13 + 1), rng.uniform(6, 11))


def bare_tree(B, x, y, rng, height, cn='Trees'):
    tubes = []

    def grow(p, d, length, r, depth):
        n = max(3, int(length / 0.5))
        pts, radii = [p.copy()], [r]
        cur, dv = p.copy(), d.normalized()
        for i in range(1, n + 1):
            dv = (dv + Vector((rng.uniform(-.25, .25), rng.uniform(-.25, .25), rng.uniform(-.1, .2)))).normalized()
            cur = cur + dv * (length / n)
            pts.append(cur.copy())
            radii.append(max(0.015, r * (1 - 0.8 * i / n)))
        tubes.append((pts, radii, [8, 6, 4, 3][min(depth, 3)]))
        if depth >= 3:
            return
        for k in range(rng.randint(2, 3)):
            i = rng.randint(max(1, n // 3), n - 1)
            bd = (pts[i] - pts[i - 1]).normalized()
            ax = bd.orthogonal().normalized()
            ax.rotate(Matrix.Rotation(rng.uniform(0, TAU), 3, bd))
            nd = bd.copy()
            nd.rotate(Matrix.Rotation(math.radians(rng.uniform(25, 50)), 3, ax))
            grow(pts[i], nd, length * 0.62, radii[i] * 0.7, depth + 1)
    grow(Vector((x, y, -0.2)), Vector((0, 0, 1)), height * 0.55, height * 0.04, 0)
    for pts, radii, segs in tubes:
        B.add(cn, ML.bm_tube(pts, radii, segs, False, True, uv_swap=True), 'M_Wood', uv='explicit', kind='soft')


def terrain(B, rng):
    def zf(x, y):
        if abs(x) < 30 and -20 < y < 26:
            return 0.0
        return 0.02 + 0.3 * (0.5 + mnoise.noise(Vector((x * 0.07, y * 0.07, 0.4)))) * min(1.0, (abs(y + 20) + max(abs(x) - 30, 0)) / 6)

    def matf(x, y):
        return 0 if (abs(x) < 31 and -20.5 < y < 16) else 1
    B.add('Floor', ML.heightfield_bm(-70, 70, -70, 24, 70, 47, zf, matf), ['M_Cobble', 'M_Snow'], uv='world', uvoff=False,
          kind='soft')
    B.add('FarGround', ML.heightfield_bm(-320, 320, -440, -69.5, 40, 30,
                                         lambda x, y: 0.3 + 3.0 * (0.5 + mnoise.noise(Vector((x * 0.015, y * 0.015, 2.0))))),
          'M_Snow', uv='world', uvoff=False, kind='soft')
    for sx in (-1, 1):
        B.add('FarGround', ML.heightfield_bm(70 if sx > 0 else -320, 320 if sx > 0 else -70, -70, 40, 25, 11,
                                             lambda x, y: 0.4 + 2.0 * (0.5 + mnoise.noise(Vector((x * 0.03, y * 0.03, 3.0))))),
              'M_Snow', uv='world', uvoff=False, kind='soft')


def training_rail(B, rng, cn='Props'):
    """Low timber rail fence marking the back of the training ground (y ~ -4)."""
    for (xa, xb) in ((-9.6, -3.2), (3.4, 9.6)):
        n = int((xb - xa) / 1.6)
        for i in range(n + 1):
            x = xa + i * (xb - xa) / n
            h = 1.05 + rng.uniform(-0.04, 0.04)
            B.add(cn, ML.bm_box(0.14, 0.14, h + 0.3, 0.015), 'M_Wood', TRS((x, -4.0, (h - 0.3) / 2 + 0.0), (0, rng.uniform(-.03, .03), rng.uniform(-.1, .1))), grain=2)
            ML.snow_on_top(B, 'Snow', x, -4.0, h - 0.15, 0.14, 0.14, rng, 0.05)
        for z in (0.45, 0.9):
            beam(B, cn, (xa - 0.1, -3.95, z + rng.uniform(-.03, .03)), (xb + 0.1, -3.95, z + rng.uniform(-.03, .03)), 0.09, 0.12)
        ML.snow_on_top(B, 'Snow', (xa + xb) / 2, -3.95, 0.96, xb - xa, 0.08, rng, 0.04)


def build(B):
    rng = random.Random(4321)
    terrain(B, rng)
    curtain_walls(B, random.Random(1))
    gatehouse(B, random.Random(2))
    outside(B, random.Random(3))
    r = random.Random(9)
    # buildings: stable (left of screen, +x) and smithy (right, -x)
    timber_house(B, 11.5, 21.5, -12.5, -6.5, 3.8, r, roof='thatch', door=(16.5, 1.8), windows=(13.2, 19.8))
    smithy(B, -20.0, -11.6, -11.5, -5.8, r)
    # a second, taller house deeper on the left against the wall
    timber_house(B, 23.0, 30.0, -19.4, -13.2, 5.2, r, roof='shingle', door=(25.0, 1.3), windows=(28.0,), chimney=(29.0, -16.3))
    # stair up to the wall walk on the right (-x) + covered walkway on the wall top
    stair(B, -12.5, -24.0, -20.0, 1.3, WALK_Z, r)
    for i in range(6):
        x = -14.0 - i * 2.8
        B.add('Walkways', ML.bm_box(0.18, 0.18, 2.4, 0.015), 'M_Wood', TRS((x, -20.2, WALK_Z + 1.2)), grain=2)
    q = [(-29.0, -20.6, WALK_Z + 2.4), (-13.0, -20.6, WALK_Z + 2.4), (-13.0, -23.2, WALK_Z + 2.0), (-29.0, -23.2, WALK_Z + 2.0)]
    q = q + [(p[0], p[1], p[2] + 0.12) for p in q]
    B.add('Walkways', ML.bm_hex(q, 0.01), 'M_Wood', grain=0)
    q2 = [(p[0] + (0.05 if p[0] > -20 else -0.05), p[1], p[2] + 0.12) for p in q[:4]]
    q2 = q2 + [(p[0], p[1], p[2] + 0.18) for p in q2]
    B.add('Snow', ML.bm_hex(q2, 0.06, 2), 'M_Snow', uv='world', uvoff=False, kind='soft')
    beam(B, 'Walkways', (-29.0, -20.2, WALK_Z + 2.35), (-13.0, -20.2, WALK_Z + 2.35), 0.2)
    icicles(B, 'Walkways', (-28.8, -20.5, WALK_Z + 2.35), (-13.2, -20.5, WALK_Z + 2.35), r)
    # torches
    torch_post(B, 8.9, -3.45, r)
    torch_post(B, -8.9, -3.45, r)
    wall_sconce(B, 11.5 + 2.5, -6.5 + 0.13, 2.3, r, (0, 1))
    wall_sconce(B, -12.0, -5.8 + 0.15, 2.0, r, (0, 1))
    wall_sconce(B, GATE_TX + GATE_TR * math.cos(1.2), WALL_Y + 0.3 + GATE_TR * math.sin(1.2) + 0.05, 4.2, r,
                (math.cos(1.2), math.sin(1.2)))
    wall_sconce(B, -GATE_TX + GATE_TR * math.cos(math.pi - 1.2), WALL_Y + 0.3 + GATE_TR * math.sin(math.pi - 1.2) + 0.05,
                4.2, r, (math.cos(math.pi - 1.2), math.sin(math.pi - 1.2)))
    # banners on the curtain wall (courtyard side)
    for x in (-17.0, 16.0):
        hanging_banner(B, x, -20.0 + 0.6, WALK_Z + 0.2, 1.8, 4.5, random.Random(int(x)))
    # training ground behind the stage
    training_rail(B, r)
    training_dummy(B, 6.3, -6.2, r, rot=0.2, helm=True)
    training_dummy(B, -7.0, -6.6, r, rot=-0.3)
    weapon_rack(B, -1.6, -7.4, r, rot=0.05)
    archery_target(B, 2.8, -10.5, r, rot=-0.15)
    # left side framing: hay cart + bales
    cart(B, 14.6, 0.6, r, rot=math.radians(62))
    for (x, y, z, rot) in ((12.0, -2.6, 0.0, 0.1), (12.0, -3.2, 0.0, 0.05), (12.1, -2.9, 0.45, -0.05), (13.2, -3.0, 0.0, 1.5),
                           (11.8, -1.6, 0.0, 0.3)):
        hay_bale(B, x, y, z, r, rot, snow=(z > 0.3 or rot > 1.0))
    ML.snow_on_top(B, 'Snow', 12.1, -2.9, 0.9, 0.95, 0.45, r, 0.08)
    # right side framing: well, barrels, crates, chopping block, firewood
    well(B, -12.9, -0.6, r)
    chopping_block(B, -11.3, -3.4, r)
    firewood(B, -21.2, -8.0, r, rot=math.pi / 2, w=2.6, h=1.3)
    for (x, y) in ((-11.0, -5.0), (-10.5, -5.5), (-11.6, -5.6)):
        barrel(B, x, y, r, rot=r.uniform(0, TAU))
    barrel(B, 10.9, -5.6, r)
    barrel(B, 11.6, -5.9, r)
    barrel(B, 10.6, -6.4, r, lying=True, rot=0.4)
    crate(B, 22.0, -5.5, 0.0, 0.9, r, 0.2)
    crate(B, 22.4, -6.4, 0.0, 0.8, r, -0.1)
    crate(B, 22.1, -5.9, 0.9, 0.7, r, 0.4)
    crate(B, 4.5, -18.6, 0.0, 0.9, r, 0.1)
    crate(B, 5.3, -18.7, 0.0, 0.8, r, -0.3)
    barrel(B, -4.6, -18.7, r)
    barrel(B, -5.3, -18.4, r)
    barrel(B, -23.0, -18.4, r)
    barrel(B, -23.6, -17.8, r)
    crate(B, 9.0, -16.0, 0.0, 0.9, r, 0.3)
    # snow drifts around the courtyard edges, buildings and props (low ones on the camera side)
    for (x, y, rx, ry, h, rot) in ((11.0, -6.8, 1.6, 0.8, 0.35, 0.0), (21.6, -7.0, 1.4, 0.9, 0.45, 0.2),
                                    (-11.0, -6.3, 1.6, 0.8, 0.3, 0.0), (-20.4, -6.5, 1.8, 1.0, 0.5, 0.0),
                                    (-14.6, 1.1, 1.5, 0.9, 0.35, 0.3), (-11.2, 1.0, 1.0, 0.8, 0.25, 0.0),
                                    (16.8, 2.0, 1.8, 1.0, 0.3, 0.4), (12.6, -0.5, 1.2, 0.8, 0.3, 0.0),
                                    (0.5, -4.55, 3.2, 0.5, 0.1, 0.0), (6.4, -4.5, 2.2, 0.5, 0.12, 0.0),
                                    (-6.2, -4.5, 2.4, 0.5, 0.12, 0.0),
                                    (-26.5, -12.0, 3.0, 2.0, 0.6, 0.0), (26.0, -9.0, 3.0, 2.2, 0.6, 0.0),
                                    (-3.8, -14.0, 1.8, 1.2, 0.3, 0.2), (8.5, -13.0, 2.2, 1.3, 0.35, 0.0)):
        snow_drift(B, x, y, rx, ry, h, r, rot)
    # small stones / dropped things on the camera side (all < 0.3 m)
    for i in range(60):
        x, y = r.uniform(-16, 16), r.uniform(-3.5, 10)
        if abs(x) < 10.6 and abs(y) < 3.0:
            continue
        s = r.uniform(0.05, 0.16)
        B.add('Props', ML.rock_bm(r, (s * 1.3, s, s * 0.7), 1, 0.3, 0.3), 'M_Stone',
              TRS((x, y, 0.0), (0, 0, r.uniform(0, TAU))), kind='soft')
    for i in range(30):
        x, y = r.uniform(-16, 16), r.uniform(-4.5, 9)
        if abs(x) < 10.6 and abs(y) < 3.0:
            continue
        st = ML.bm_box(r.uniform(0.3, 0.6), 0.02, 0.02, 0.0)
        B.add('Props', st, 'M_Straw', TRS((x, y, 0.015), (0, 0, r.uniform(0, TAU))), grain=0)


def make_layout(B):
    pitch, yaw = 48.0, 32.0
    ud, bd = ML.sun_vectors(pitch, yaw)
    return {
        "_notes": "Positions in Blender coordinates (metres, Z up); Unity = (-x, z, -y). Colours are sRGB "
                  "(as typed in Unity's inspector). sun.direction_deg = Unity directional-light Euler "
                  "[pitch(X), yaw(Y)]; sun.direction_blender = the light's travel direction in Blender axes. "
                  "Fog is linear (Unity RenderSettings.fogMode = Linear). Point-light intensity is Unity URP "
                  "intensity; range in metres. fx.scale ~1 = one torch/brazier-sized fire.",
        "sun": {"direction_deg": [pitch, yaw], "direction_blender": [round(v, 4) for v in bd],
                "color": [round(c, 3) for c in C(222, 230, 244)], "intensity": 1.05},
        "ambient": {"sky": [round(c, 3) for c in C(150, 160, 178)], "equator": [round(c, 3) for c in C(124, 130, 140)],
                    "ground": [round(c, 3) for c in C(84, 86, 92)]},
        "fog": {"color": [round(c, 3) for c in C(176, 184, 196)], "start": 10.0, "end": 280.0},
        "background": [round(c, 3) for c in C(176, 184, 196)],
        "pointLights": B.lights,
        "fx": B.fx + [{"type": "snow", "pos": [0.0, -1.0, 12.0], "scale": 30.0},
                      {"type": "snow", "pos": [0.0, -30.0, 22.0], "scale": 70.0}],
    }


def preview_extras(B, coll, fog):
    fmat = ML.emissive_material('PV_Flame', C(255, 150, 60), 18.0, fog)
    fmat2 = ML.emissive_material('PV_FlameCore', C(255, 220, 140), 30.0, fog)
    rng = random.Random(5)
    for kind, pos, s in B.preview:
        for k in range(4):
            prof = [(0.0, 0.0)] + [(0.22 * s * (1 - k * 0.2) * math.sin(math.pi * t ** 0.6) * (1 - t) ** 0.3,
                                    t * 0.9 * s * (1 - k * 0.15)) for t in np.linspace(0.05, 1.0, 10)]
            prof[-1] = (0.0, prof[-1][1])
            bm = ML.bm_lathe([(max(rr, 0.0), z) for rr, z in prof], 10, False, False)
            ML.bm_noise(bm, 0.04 * s, 6.0, rng.randint(0, 99))
            me = bpy.data.meshes.new('PV_flame')
            bm.to_mesh(me)
            bm.free()
            ob = bpy.data.objects.new('PV_flame', me)
            ob.location = pos + Vector((rng.uniform(-0.1, 0.1) * s, rng.uniform(-0.1, 0.1) * s, 0))
            ob.rotation_euler = (rng.uniform(-0.12, 0.12), rng.uniform(-0.12, 0.12), rng.uniform(0, TAU))
            me.materials.append(fmat2 if k == 3 else fmat)
            coll.objects.link(ob)
    mq = ML.plain_material('PV_Mannequin', C(70, 72, 78), 0.5, fog)
    for x in (2.2, -2.2):
        for (r0, h, z) in ((0.17, 0.9, 0.0), (0.2, 0.62, 0.9)):
            bm = ML.bm_cyl(r0, r0, h, 16)
            me = bpy.data.meshes.new('PV_mq')
            bm.to_mesh(me)
            ob = bpy.data.objects.new('PV_mq', me)
            ob.location = (x, 0, z)
            me.materials.append(mq)
            coll.objects.link(ob)
        bm = ML.bm_sphere(0.13, 16, 10)
        me = bpy.data.meshes.new('PV_mq')
        bm.to_mesh(me)
        ob = bpy.data.objects.new('PV_mq', me)
        ob.location = (x, 0, 1.68)
        me.materials.append(mq)
        coll.objects.link(ob)
    # falling snow specks (preview only)
    smat = ML.emissive_material('PV_Snowflake', C(240, 244, 250), 1.2, fog)
    bm = bmesh.new()
    for i in range(2500):
        p = Vector((rng.uniform(-22, 22), rng.uniform(-25, 4), rng.uniform(0.2, 14)))
        s = rng.uniform(0.012, 0.026)
        ico = ML.bm_ico(s, 0)
        bmesh.ops.translate(ico, vec=p, verts=ico.verts)
        ML.bm_merge(bm, ico)
        ico.free()
    me = bpy.data.meshes.new('PV_snow')
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new('PV_snow', me)
    me.materials.append(smat)
    coll.objects.link(ob)


def check_clear(B):
    bad_play, bad_cam = 0, 0
    offenders = {}
    for name, ch in B.chunks.items():
        for (x, y, z) in ch.co:
            if abs(x) <= 10 and abs(y) <= 2.5 and z > 0.002 and name not in ('Floor',):
                bad_play += 1
                offenders.setdefault(name, (round(x, 2), round(y, 2), round(z, 2)))
            if y > 2.5 and abs(x) < 14 and z > 0.3:
                bad_cam += 1
                offenders.setdefault(name + '_cam', (round(x, 2), round(y, 2), round(z, 2)))
    if offenders:
        ML.log('clearance offenders:', offenders)
    ML.log('clearance check: verts in play strip above floor = %d, camera-side verts above 0.3 m = %d'
           % (bad_play, bad_cam))


def main():
    opts = ML.parse_args()
    paths = ML.map_paths(MAP)
    ML.reset_scene()
    mats = materials()
    ML.bake_materials(mats, paths['art'], opts.res, opts.rebake, opts.only)
    if opts.rebake or not os.path.exists(os.path.join(paths['logs'], MAP + '_textures.png')):
        ML.contact_sheet(mats, paths['art'], os.path.join(paths['logs'], MAP + '_textures.png'))
    B = ML.Builder(mats, seed=7)
    build(B)
    tris, per = B.tri_count()
    ML.log('triangles: %d' % tris, sorted(per.items(), key=lambda kv: -kv[1]))
    check_clear(B)
    layout = make_layout(B)
    sc = bpy.context.scene
    coll = bpy.data.collections.new(MAP)
    sc.collection.children.link(coll)
    mobj = ML.make_materials(mats, paths['art'], layout['fog'])
    objs = B.finalize(coll, mobj)
    ML.write_json(os.path.join(paths['art'], 'materials.json'), [m.json() for m in mats])
    ML.write_json(os.path.join(paths['art'], 'layout.json'), layout)
    if not opts.no_export:
        ML.export_fbx(objs, os.path.join(paths['art'], MAP + '.fbx'))
    pcoll = bpy.data.collections.new('PreviewOnly')
    sc.collection.children.link(pcoll)
    ML.setup_world_and_lights(layout, pcoll)
    preview_extras(B, pcoll, layout['fog'])
    cam_g = ML.add_camera('Cam_Game', (0, 10, 2.4), (0, 0, 1.2), 48, pcoll)
    cam_w = ML.add_camera('Cam_Wide', (-22, 26, 15), (2, -12, 4), 50, pcoll)
    sc.camera = cam_g
    if not opts.no_export:
        try:
            bpy.ops.file.make_paths_relative()
        except Exception:
            pass
        bpy.context.preferences.filepaths.save_version = 0   # no .blend1 backups
        bpy.ops.wm.save_as_mainfile(filepath=paths['blend'], compress=True)
        ML.log('saved', paths['blend'])
    if opts.cams:
        for (pos, tgt, fov, name) in opts.cams:
            cam = ML.add_camera('Cam_' + name, pos, tgt, fov, pcoll)
            ML.render_still(cam, os.path.join(paths['logs'], '_test', name + '.png'), opts.samples, (1200, 675))
        return
    if not opts.no_render:
        ML.render_still(cam_g, os.path.join(paths['logs'], MAP + '_game.png'), opts.samples)
        if not opts.game_only:
            ML.render_still(cam_w, os.path.join(paths['logs'], MAP + '_wide.png'), opts.samples)
    ML.log('done')


main()
