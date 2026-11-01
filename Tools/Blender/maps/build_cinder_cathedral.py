"""Cinder Cathedral -- ruined gothic cathedral courtyard at dusk (dark fantasy).

    "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup \\
        -P Tools/Blender/maps/build_cinder_cathedral.py -- [--rebake] [--no-render] [--no-export] [--samples=N]

Outputs (see maplib / CONVENTIONS.md):
  Assets/_Game/Art/Maps/CinderCathedral/{CinderCathedral.fbx, T_*.png, materials.json, layout.json}
  ArtSource/Maps/CinderCathedral.blend
  Logs/maps/CinderCathedral_game.png, CinderCathedral_wide.png
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

MAP = 'CinderCathedral'
TRS = ML.TRS
TAU = math.tau
sm = ML.smoothstep


def C(r, g, b):
    return (r / 255.0, g / 255.0, b / 255.0)


# =============================================================================================
# Materials
# =============================================================================================
def r_stone(F, res, m, rng):
    t = np.clip(0.5 + (F['nL'] - 0.5) * 0.7 + (F['nM'] - 0.5) * 0.6 + (F['nF'] - 0.5) * 0.2, 0, 1)
    alb = ML.ramp(t, [(0.0, C(30, 29, 28)), (0.4, C(52, 50, 48)), (0.65, C(72, 69, 65)), (1.0, C(98, 93, 87))])
    warm = sm(0.65, 0.92, F['nT'])[..., None]
    alb = alb * (1 + warm * np.array([0.16, 0.02, -0.08], np.float32))
    soot = sm(0.6, 0.88, F['nS'])
    pit = (1 - sm(0.04, 0.14, F['vP'])) * sm(0.55, 0.78, F['nW'])
    crack = (1 - sm(0.0, 0.016, F['vC'])) * sm(0.62, 0.78, F['nC'])
    alb = alb * ((0.86 + 0.28 * F['nF']) * (1 - 0.45 * soot) * (1 - 0.45 * pit) * (1 - 0.7 * crack))[..., None]
    h = (F['nM'] - 0.5) * 0.008 + (F['nW'] - 0.5) * 0.003 + (F['nF'] - 0.5) * 0.0012 - pit * 0.002 - crack * 0.004
    rough = 0.84 + (F['nF'] - 0.5) * 0.1 + pit * 0.06 - soot * 0.04
    return dict(albedo=alb, height=h, rough=rough)


STONE_F = {
    'nL': dict(type='noise', f=3, detail=3, rough=0.5),
    'nM': dict(type='noise', f=11, detail=8, rough=0.6),
    'nF': dict(type='noise', f=70, detail=4, rough=0.6),
    'vP': dict(type='voronoi', f=36, feature='F1'),
    'vC': dict(type='voronoi', f=4.5, feature='DISTANCE_TO_EDGE'),
    'nC': dict(type='noise', f=6, detail=4),
    'nS': dict(type='noise', fu=5, fv=0.7, detail=6, rough=0.6),
    'nW': dict(type='noise', f=18, detail=6, dist=1.2),
    'nT': dict(type='noise', f=2.5, detail=3),
}


def r_brick(F, res, m, rng):
    U, V = ML.warp_coords(res, (F['wU'] - 0.5) * 0.004, (F['wV'] - 0.5) * 0.004)
    L = ML.brick_layout(U, V, rng, rows=9, per_row=(4, 6), row_jitter=0.12, len_jitter=0.3)
    T = m.tiling
    d = np.minimum(L['du'], L['dv']) * T - np.clip(F['nE'] - 0.6, 0, 1) * 0.1
    mortar = 1 - sm(0.006, 0.014, d)
    bev = sm(0.004, 0.035, d)
    t = np.clip(L['rnd'] * 0.45 + F['nL'] * 0.3 + (F['nM'] - 0.5) * 0.35 + 0.12, 0, 1)
    blk = ML.ramp(t, [(0.0, C(34, 32, 31)), (0.5, C(58, 55, 51)), (1.0, C(88, 83, 77))])
    mort = np.array(ML.s2l(C(64, 61, 58)), np.float32)
    alb = ML.lerp(blk * (0.88 + 0.24 * F['nF'])[..., None], mort, mortar)
    soot = sm(0.6, 0.88, F['nS'])
    crack = (1 - sm(0.0, 0.015, F['vC'])) * sm(0.62, 0.78, F['nC'])
    alb = alb * ((1 - 0.5 * soot) * (1 - 0.6 * crack))[..., None]
    h = bev * 0.015 + (L['rnd'] - 0.5) * 0.004 * bev + (F['nM'] - 0.5) * 0.005 + (F['nF'] - 0.5) * 0.0012 - crack * 0.003
    rough = 0.85 + mortar * 0.08 + (F['nF'] - 0.5) * 0.08
    return dict(albedo=alb, height=h, rough=rough)


BRICK_F = {
    'nL': dict(type='noise', f=3, detail=3), 'nM': dict(type='noise', f=14, detail=8),
    'nF': dict(type='noise', f=80, detail=4), 'wU': dict(type='noise', f=7, detail=3),
    'wV': dict(type='noise', f=7, detail=3), 'vC': dict(type='voronoi', f=6, feature='DISTANCE_TO_EDGE'),
    'nC': dict(type='noise', f=8, detail=4), 'nS': dict(type='noise', fu=6, fv=1, detail=6),
    'nE': dict(type='noise', f=30, detail=6),
}


def r_floor(F, res, m, rng):
    U, V = ML.warp_coords(res, (F['wU'] - 0.5) * 0.004, (F['wV'] - 0.5) * 0.004)
    L = ML.brick_layout(U, V, rng, rows=7, per_row=(5, 8), row_jitter=0.2, len_jitter=0.3)
    T = m.tiling
    rnd = L['rnd']
    rnd2 = np.abs(np.modf(np.sin(L['rid'].astype(np.float64) * 7.137 + 1.7) * 9631.77)[0]).astype(np.float32)
    d = np.minimum(L['du'], L['dv']) * T - np.clip(F['nE'] - 0.55, 0, 1) * 0.1
    joint = 1 - sm(0.006, 0.016, d)
    bev = sm(0.0, 0.04, d)
    t = np.clip(0.5 + (F['nL'] - 0.5) * 0.6 + (rnd - 0.5) * 0.5 + (F['nM'] - 0.5) * 0.55, 0, 1)
    slab = ML.ramp(t, [(0.0, C(36, 35, 34)), (0.4, C(56, 54, 51)), (0.7, C(74, 71, 67)), (1.0, C(96, 91, 86))])
    slab = slab * (1 + (rnd2 - 0.5)[..., None] * np.array([0.12, 0.03, -0.08], np.float32))
    slab = slab * (0.82 + 0.36 * F['nG'])[..., None]
    dirt = np.array(ML.s2l(C(40, 37, 35)), np.float32)
    ash_col = ML.ramp(F['nG'], [(0.0, C(92, 90, 88)), (1.0, C(132, 129, 125))])
    broken = (rnd2 < 0.3).astype(np.float32)
    crack = np.clip((1 - sm(0.0, 0.014, F['vC'])) * sm(0.6, 0.72, F['nC']) +
                    (1 - sm(0.0, 0.012, F['vD'])) * broken, 0, 1)
    missing = (rnd > 0.96).astype(np.float32)
    h = bev * 0.014 + (rnd - 0.5) * 0.01 * bev + (F['nM'] - 0.5) * 0.004 + (F['nG'] - 0.5) * 0.0015 - crack * 0.005
    h = h * (1 - missing) - missing * 0.012
    alb = slab * (1 - 0.6 * crack)[..., None]
    alb = ML.lerp(alb, dirt, np.clip(joint + missing, 0, 1))
    scorch = sm(0.68, 0.9, F['nS'])
    alb = alb * (1 - 0.55 * scorch)[..., None]
    ash = np.clip(sm(0.6, 0.8, F['nA']) * 0.9 + joint * sm(0.4, 0.6, F['nA']) * 0.8 + missing * 0.6, 0, 1)
    ash_level = 0.003 + (F['nA'] - 0.5) * 0.008
    h = np.where(ash > 0.5, np.maximum(h, ash_level), h)
    alb = ML.lerp(alb, ash_col, ash * 0.85)
    rough = np.clip(0.8 + (F['nG'] - 0.5) * 0.1 + ash * 0.15 - scorch * 0.05, 0, 1)
    return dict(albedo=alb, height=h, rough=rough)


FLOOR_F = {
    'nL': dict(type='noise', f=2.5, detail=3), 'nM': dict(type='noise', f=12, detail=8),
    'nG': dict(type='noise', f=90, detail=4), 'wU': dict(type='noise', f=6, detail=3),
    'wV': dict(type='noise', f=6, detail=3), 'nE': dict(type='noise', f=25, detail=6),
    'vC': dict(type='voronoi', f=5, feature='DISTANCE_TO_EDGE'), 'nC': dict(type='noise', f=7, detail=4),
    'nA': dict(type='noise', f=3, detail=7, rough=0.62), 'nS': dict(type='noise', f=2.5, detail=5),
    'vD': dict(type='voronoi', f=9, feature='DISTANCE_TO_EDGE'),
}


def r_ash(F, res, m, rng):
    t = np.clip(0.5 + (F['nL'] - 0.5) * 0.7 + (F['nM'] - 0.5) * 0.5, 0, 1)
    alb = ML.ramp(t, [(0.0, C(62, 60, 58)), (0.5, C(98, 95, 92)), (1.0, C(134, 130, 126))])
    char = (1 - sm(0.05, 0.12, F['vS'])) * sm(0.55, 0.7, F['nM'])
    alb = ML.lerp(alb, np.array(ML.s2l(C(26, 23, 21)), np.float32), char * 0.9)
    ember = (1 - sm(0.02, 0.05, F['vS'])) * sm(0.86, 0.94, F['nE'])
    alb = ML.lerp(alb, np.array(ML.s2l(C(150, 62, 26)), np.float32), ember)
    alb = alb * (0.9 + 0.2 * F['nF'])[..., None]
    h = (F['nR'] - 0.5) * 0.008 + (F['nM'] - 0.5) * 0.008 + (F['nF'] - 0.5) * 0.0015 + char * 0.001
    return dict(albedo=alb, height=h, rough=0.95 - ember * 0.2)


ASH_F = {
    'nL': dict(type='noise', f=2, detail=3), 'nM': dict(type='noise', f=9, detail=6),
    'nF': dict(type='noise', f=90, detail=3), 'nR': dict(type='noise', fu=14, fv=3, detail=4),
    'vS': dict(type='voronoi', f=50, feature='F1'), 'nE': dict(type='noise', f=30, detail=2),
}


def r_iron(F, res, m, rng):
    rust = sm(0.45, 0.62, F['nR'] * 0.6 + F['nR2'] * 0.4 + (F['nD'] - 0.5) * 0.25)
    iron = ML.ramp(F['nF'] * 0.5 + F['nR2'] * 0.5, [(0.0, C(30, 29, 29)), (1.0, C(66, 63, 60))])
    rc = ML.ramp(F['nK'], [(0.0, C(52, 26, 15)), (0.5, C(94, 46, 23)), (1.0, C(128, 70, 36))])
    alb = ML.lerp(iron, rc, rust)
    pits = (1 - sm(0.03, 0.1, F['vP'])) * rust
    alb = alb * (1 - 0.4 * pits)[..., None]
    h = rust * 0.0008 + (F['nK'] - 0.5) * 0.001 * rust + (F['nR2'] - 0.5) * 0.0005 - pits * 0.0015
    return dict(albedo=alb, height=h, rough=0.48 + (F['nF'] - 0.5) * 0.15 + rust * 0.4, metal=1 - rust * 0.95)


IRON_F = {
    'nR': dict(type='noise', f=5, detail=8), 'nR2': dict(type='noise', f=18, detail=6),
    'nF': dict(type='noise', f=90, detail=3), 'vP': dict(type='voronoi', f=45, feature='F1'),
    'nD': dict(type='noise', f=3, detail=3), 'nK': dict(type='noise', f=30, detail=8, dist=1.0),
}


def r_bark(F, res, m, rng):
    plate = sm(0.0, 0.16, F['vB']) * (0.55 + 0.45 * sm(0.35, 0.7, F['nB']))
    t = np.clip(F['nL'] * 0.5 + F['nB'] * 0.5, 0, 1)
    alb = ML.ramp(t, [(0.0, C(38, 33, 30)), (0.5, C(66, 60, 54)), (1.0, C(94, 88, 82))])
    alb = alb * (0.3 + 0.7 * plate)[..., None]
    dust = sm(0.65, 0.9, F['nK']) * plate
    alb = ML.lerp(alb, np.array(ML.s2l(C(118, 114, 110)), np.float32), dust * 0.6)
    h = plate * 0.02 + (F['nB'] - 0.5) * 0.006 + (F['nF'] - 0.5) * 0.002
    return dict(albedo=alb, height=h, rough=0.9 + dust * 0.05)


BARK_F = {
    'vB': dict(type='voronoi', fu=18, fv=2.5, feature='DISTANCE_TO_EDGE', detail=1.5),
    'nB': dict(type='noise', fu=26, fv=3, detail=6, dist=0.6), 'nF': dict(type='noise', f=60, detail=4),
    'nL': dict(type='noise', f=2, detail=3), 'nK': dict(type='noise', fu=30, fv=6, detail=4),
}


def r_bone(F, res, m, rng):
    t = np.clip(0.5 + (F['nL'] - 0.5) * 0.7 + (F['nM'] - 0.5) * 0.4, 0, 1)
    alb = ML.ramp(t, [(0.0, C(128, 113, 90)), (0.5, C(170, 158, 134)), (1.0, C(200, 190, 166))])
    dirt = sm(0.6, 0.85, F['nD'])
    alb = ML.lerp(alb, np.array(ML.s2l(C(70, 58, 46)), np.float32), dirt * 0.7)
    pores = 1 - sm(0.03, 0.09, F['vP'])
    alb = alb * (1 - 0.3 * pores)[..., None]
    h = (F['nM'] - 0.5) * 0.0015 + (F['nF'] - 0.5) * 0.0004 - pores * 0.0008
    return dict(albedo=alb, height=h, rough=0.6 + dirt * 0.25)


BONE_F = {
    'nL': dict(type='noise', f=3, detail=3), 'nM': dict(type='noise', f=12, detail=6),
    'vP': dict(type='voronoi', f=35, feature='F1'), 'nF': dict(type='noise', f=70, detail=3),
    'nD': dict(type='noise', f=5, detail=5),
}


def r_ember(F, res, m, rng):
    crack = 1 - sm(0.0, 0.07, F['vE'])
    glow = crack * (0.45 + 0.55 * sm(0.35, 0.75, F['nG'])) + 0.3 * sm(0.75, 0.95, F['nM']) * sm(0.5, 0.85, F['nG'])
    coal = ML.ramp(np.clip(F['vC'] * 0.5 + F['nF'] * 0.5, 0, 1), [(0.0, C(13, 11, 10)), (1.0, C(42, 36, 32))])
    gc = ML.ramp(np.clip(glow, 0, 1), [(0.0, C(70, 16, 4)), (0.5, C(255, 92, 18)), (1.0, C(255, 196, 92))])
    alb = ML.lerp(coal, gc, sm(0.1, 0.55, glow))
    h = (1 - crack) * 0.012 + (F['vC'] - 0.5) * 0.01 + (F['nM'] - 0.5) * 0.003
    return dict(albedo=alb, height=h, rough=0.85)


EMBER_F = {
    'vE': dict(type='voronoi', f=7, feature='DISTANCE_TO_EDGE'),
    'vC': dict(type='voronoi', f=7, feature='F1', out='Color'),
    'nM': dict(type='noise', f=14, detail=6), 'nF': dict(type='noise', f=50, detail=4),
    'nG': dict(type='noise', f=3, detail=3),
}


def r_cloth(F, res, m, rng):
    U, V = ML.warp_coords(res, (F['nM'] - 0.5) * 0.0015, None)
    wu = 0.5 + 0.5 * np.sin(U * TAU * 260)
    wv = 0.5 + 0.5 * np.sin(V * TAU * 260)
    weave = np.where(np.sin(U * TAU * 130) * np.sin(V * TAU * 130) > 0, wu, wv)
    t = np.clip(F['nL'] * 0.6 + F['nM'] * 0.4, 0, 1)
    alb = ML.ramp(t, [(0.0, C(36, 13, 12)), (0.5, C(62, 22, 19)), (1.0, C(86, 33, 26))])
    grime = sm(0.55, 0.85, F['nG'])
    alb = ML.lerp(alb, np.array(ML.s2l(C(40, 34, 30)), np.float32), grime * 0.75)
    alb = alb * (0.85 + 0.2 * F['nF'] + 0.1 * weave)[..., None]
    h = (weave - 0.5) * 0.0007 + (F['nM'] - 0.5) * 0.0015
    return dict(albedo=alb, height=h, rough=0.92)


CLOTH_F = {
    'nL': dict(type='noise', f=3, detail=4), 'nM': dict(type='noise', f=10, detail=6),
    'nF': dict(type='noise', fu=200, fv=40, detail=2), 'nG': dict(type='noise', f=3, detail=5),
}


def r_glow(F, res, m, rng):
    alb = ML.ramp(F['nM'], [(0.0, C(170, 82, 36)), (1.0, C(250, 168, 96))])
    alb = alb * (0.9 + 0.2 * F['nF'])[..., None]
    return dict(albedo=alb, height=(F['nF'] - 0.5) * 0.0015, rough=0.9)


GLOW_F = {'nM': dict(type='noise', f=4, detail=4), 'nF': dict(type='noise', f=20, detail=4)}


def materials():
    return [
        ML.MatDef('M_Stone', 2.0, STONE_F, r_stone, tint=(1, 1, 1), seed=11),
        ML.MatDef('M_StoneBrick', 4.0, BRICK_F, r_brick, seed=12),
        ML.MatDef('M_Floor', 6.0, FLOOR_F, r_floor, seed=13),
        ML.MatDef('M_Ash', 3.0, ASH_F, r_ash, seed=14, ao_strength=0.3, normal_strength=2.0),
        ML.MatDef('M_Iron', 1.0, IRON_F, r_iron, seed=15, ao_strength=0.3, normal_strength=3.0),
        ML.MatDef('M_Bark', 2.0, BARK_F, r_bark, seed=16),
        ML.MatDef('M_Bone', 0.5, BONE_F, r_bone, seed=17, ao_strength=0.3, normal_strength=2.0),
        ML.MatDef('M_Ember', 0.8, EMBER_F, r_ember, seed=18, emission=C(255, 120, 45), emission_intensity=5.0,
                  ao_strength=0.2),
        ML.MatDef('M_Cloth', 1.5, CLOTH_F, r_cloth, seed=19, ao_strength=0.2, normal_strength=2.5),
        ML.MatDef('M_Glow', 2.0, GLOW_F, r_glow, seed=20, emission=C(255, 150, 80), emission_intensity=1.6,
                  ao_strength=0.0),
    ]


# =============================================================================================
# Props
# =============================================================================================
def knight_parts(rng, sword=True):
    """Human-scale (1.8 m) armoured figure, origin between the feet, facing +y.
    Returns [(bm, tag)] with tag in legs/body/head/sword."""
    P = []

    def add(bm, M, tag):
        bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
        P.append((bm, tag))

    def tube(a, b, r0, r1, segs=10):
        return ML.bm_tube([Vector(a), Vector(b)], [r0, r1], segs)

    for s in (-1, 1):
        add(ML.bm_box(0.13, 0.3, 0.09, 0.03), TRS((s * 0.12, 0.04, 0.045)), 'legs')
        add(ML.bm_cyl(0.07, 0.088, 0.44, 12), TRS((s * 0.12, 0, 0.08)), 'legs')
        add(ML.bm_sphere(0.085, 12, 8), TRS((s * 0.12, 0.03, 0.53), s=(1, 1.1, 0.85)), 'legs')
        add(ML.bm_cyl(0.095, 0.118, 0.36, 12), TRS((s * 0.12, 0, 0.56)), 'body')
        for k in range(3):
            add(ML.bm_sphere(0.15 - 0.02 * k, 14, 8), TRS((s * (0.25 + 0.01 * k), 0, 1.47 - 0.06 * k),
                                                         (0, s * 0.35, 0), s=(1, 0.95, 0.62)), 'body')
        sh = Vector((s * 0.26, 0.0, 1.40))
        el = Vector((s * 0.29, 0.13, 1.17))
        wr = Vector((s * 0.07, 0.27, 1.12))
        add(tube(sh, el, 0.075, 0.065), Matrix(), 'body')
        add(ML.bm_sphere(0.075, 10, 6), TRS(el), 'body')
        add(tube(el, wr, 0.066, 0.058), Matrix(), 'body')
        add(ML.bm_box(0.1, 0.11, 0.1, 0.02), TRS((s * 0.05, 0.29, 1.12)), 'body')
    add(ML.bm_lathe([(0.17, 0.0), (0.2, 0.12), (0.228, 0.28), (0.222, 0.38), (0.175, 0.47), (0.1, 0.5)], 16),
        TRS((0, 0, 1.0), s=(1, 0.74, 1)), 'body')
    add(ML.bm_lathe([(0.25, 0.0), (0.24, 0.1), (0.205, 0.2), (0.18, 0.25)], 16), TRS((0, 0, 0.82), s=(1, 0.8, 1)),
        'body')
    add(ML.bm_cyl(0.19, 0.19, 0.06, 16), TRS((0, 0, 1.0), s=(1, 0.76, 1)), 'body')
    add(ML.bm_cyl(0.1, 0.085, 0.09, 12), TRS((0, 0, 1.49)), 'body')
    # cape: hangs from the shoulders behind the back
    cape = ML.cloth_bm(0.5, 1.3, 6, 10, rng, folds=2, fold_amp=0.035, tatter=0.0, thickness=0.03, uv_norm=False)
    for v in cape.verts:
        t = -v.co.z / 1.3
        v.co.x *= 1 + 0.6 * t
        v.co.y = -v.co.y - 0.04 - 0.16 * t
    add(cape, TRS((0, -0.18, 1.5)), 'body')
    # helm
    add(ML.bm_lathe([(0.105, 0.0), (0.125, 0.05), (0.128, 0.16), (0.12, 0.21), (0.085, 0.26), (0.0, 0.285)], 14),
        TRS((0, 0, 1.56)), 'head')
    add(ML.bm_box(0.2, 0.03, 0.02, 0.006), TRS((0, 0.117, 1.715)), 'head')
    add(ML.bm_box(0.2, 0.03, 0.02, 0.006), TRS((0, 0.117, 1.67)), 'head')
    add(ML.bm_box(0.022, 0.24, 0.07, 0.008), TRS((0, -0.01, 1.84)), 'head')
    if sword:
        blade = ML.bm_prism([(0, 0), (0.036, 0.12), (0.031, 0.96), (-0.031, 0.96), (-0.036, 0.12)], 0.016)
        add(blade, TRS((0, 0.29, 0.0)), 'sword')
        add(ML.bm_box(0.4, 0.045, 0.045, 0.01), TRS((0, 0.29, 0.98)), 'sword')
        add(ML.bm_cyl(0.019, 0.019, 0.15, 8), TRS((0, 0.29, 1.0)), 'sword')
        add(ML.bm_sphere(0.042, 10, 6), TRS((0, 0.29, 1.18)), 'sword')
    return P


def statue(B, x, y, rot, scale, state, rng, plinth_h=0.9):
    """state: 'standing', 'headless', 'toppled'."""
    cn = 'Statues'
    Mb = TRS((x, y, 0), (0, 0, rot))
    # plinth: stepped base
    pw = 1.15 * scale
    B.add(cn, ML.bm_box(pw * 1.3, pw * 1.3, 0.25, 0.04), 'M_Stone', Mb @ TRS((0, 0, 0.125)))
    body_h = plinth_h - 0.4
    pb = ML.bm_box(pw, pw, body_h, 0.04)
    ML.bm_chip(pb, rng, 2)
    B.add(cn, pb, 'M_Stone', Mb @ TRS((0, 0, 0.25 + body_h / 2)))
    B.add(cn, ML.bm_box(pw * 1.12, pw * 1.12, 0.15, 0.04), 'M_Stone', Mb @ TRS((0, 0, plinth_h - 0.075)))
    parts = knight_parts(rng, sword=True)
    S = Matrix.Diagonal((scale, scale, scale, 1))
    top = Mb @ TRS((0, 0, plinth_h))
    if state in ('standing', 'headless'):
        for bm, tag in parts:
            if state == 'headless' and tag == 'head':
                bm.free()
                continue
            bmesh.ops.transform(bm, matrix=S, verts=bm.verts)
            B.add(cn, bm, 'M_Stone', top)
        if state == 'headless':
            hp = [p for p in knight_parts(rng) if p[1] == 'head']
            Mh = TRS((x + rng.uniform(-1.2, 1.2), y + 1.0, 0.11 * scale), (rng.uniform(1.2, 1.8), 0, rng.uniform(0, TAU)))
            for bm, tag in hp:
                bmesh.ops.transform(bm, matrix=TRS((0, 0, -1.68)) , verts=bm.verts)
                bmesh.ops.transform(bm, matrix=S, verts=bm.verts)
                B.add(cn, bm, 'M_Stone', Mh)
        return
    # toppled: legs stay on the plinth (broken below the knee), the rest lies on the ground
    lying = []
    for bm, tag in parts:
        bmesh.ops.transform(bm, matrix=S, verts=bm.verts)
        if tag == 'legs':
            ML.bm_rough_cut(bm, (0, 0, 0.38 * scale), (rng.uniform(-.4, .4), rng.uniform(-.4, .4), 1), rng, 2, 0.03)
            if bm.verts:
                B.add(cn, bm, 'M_Stone', top)
        else:
            if tag == 'body':
                ML.bm_cut(bm, (0, 0, 0.6 * scale), (0, 0, -1))
            if bm.verts:
                lying.append(bm)
    # fall forward toward +y (rotate about local x by +90deg), slight roll
    roll = rng.uniform(-0.5, 0.5)
    Rf = TRS((0, 0, 0), (math.radians(88), roll, 0))
    ex = rng.uniform(0.3, 0.6)
    pts = []
    for bm in lying:
        for v in bm.verts:
            pts.append(Rf @ v.co)
    minz = min(p.z for p in pts)
    miny = min(p.y for p in pts)
    Mf = Mb @ TRS((ex, pw * 0.5 - miny + 0.15, -minz - 0.06 * scale)) @ Rf
    for bm in lying:
        if rng.random() < 0.2:
            ML.bm_chip(bm, rng, 1, (0.02, 0.06))
        B.add(cn, bm, 'M_Stone', Mf)


def gravestone(B, x, y, rng, kind=None):
    kind = kind or rng.choice(['round', 'gothic', 'cross', 'round', 'slab'])
    w = rng.uniform(0.48, 0.78)
    h = rng.uniform(0.85, 1.35)
    t = rng.uniform(0.12, 0.2)
    if kind == 'round':
        poly = [(-w / 2, 0), (w / 2, 0)] + [(w / 2 * math.cos(a), h - w / 2 + w / 2 * math.sin(a))
                                            for a in np.linspace(0, math.pi, 9)]
    elif kind == 'gothic':
        sp = h - w * 0.75
        pts = []
        for side in (1, -1):
            r = w * 0.85
            off = r - w / 2
            arc = ML.arch_points(0, sp, r, off, 5, 0, side)
            pts.append(arc)
        poly = [(-w / 2, 0), (w / 2, 0)] + pts[0] + list(reversed(pts[1]))[1:]
    elif kind == 'cross':
        a = w * 0.16
        arm = w * 0.5
        cz = h * 0.68
        poly = [(-a, 0), (a, 0), (a, cz - a), (arm, cz - a), (arm, cz + a), (a, cz + a), (a, h), (-a, h),
                (-a, cz + a), (-arm, cz + a), (-arm, cz - a), (-a, cz - a)]
    else:
        poly = [(-w / 2, 0), (w / 2, 0), (w / 2 * 0.92, h * 0.8), (0, h * 0.86), (-w / 2 * 0.92, h * 0.8)]
    # dedupe consecutive points
    clean = []
    for p in poly:
        if not clean or (abs(p[0] - clean[-1][0]) > 1e-4 or abs(p[1] - clean[-1][1]) > 1e-4):
            clean.append(p)
    if abs(clean[0][0] - clean[-1][0]) < 1e-4 and abs(clean[0][1] - clean[-1][1]) < 1e-4:
        clean.pop()
    bm = ML.bm_prism(clean, t, bevel=0.012)
    if rng.random() < 0.3 and kind != 'cross':
        ML.bm_rough_cut(bm, (0, 0, h * rng.uniform(0.45, 0.75)), (rng.uniform(-0.8, 0.8), 0, 1), rng, 2, 0.04)
    elif rng.random() < 0.5:
        ML.bm_chip(bm, rng, 2, (0.03, 0.08))
    sink = rng.uniform(0.08, 0.22)
    M = TRS((x, y, -sink), (rng.uniform(-0.22, 0.22), rng.uniform(-0.18, 0.18), rng.uniform(-0.45, 0.45)))
    B.add('Graves', bm, 'M_Stone', M)
    if rng.random() < 0.4:
        slab = ML.bm_box(w + 0.2, rng.uniform(1.4, 1.9), 0.12, 0.02)
        if rng.random() < 0.5:
            ML.bm_rough_cut(slab, (rng.uniform(-.2, .2), 0, 0), (0.3, 1, 0.1), rng, 2, 0.05)
        B.add('Graves', slab, 'M_Stone', TRS((x, y + 0.9, 0.02), (rng.uniform(-.04, .04), rng.uniform(-.04, .04), rng.uniform(-.1, .1))))


def dead_tree(B, x, y, rng, height=8.0, r0=0.42, lean=(0.0, 0.0), spread=1.0):
    cn = 'Tree'
    tubes = []

    def rvec(a):
        return Vector((rng.uniform(-a, a), rng.uniform(-a, a), rng.uniform(-a, a)))

    def grow(p, d, length, r, depth, maxd):
        n = max(3, int(length / (0.3 + 0.1 * depth)))
        pts = [p.copy()]
        radii = [r]
        cur = p.copy()
        dv = d.normalized()
        for i in range(1, n + 1):
            dv = (dv + rvec(0.32) + Vector((0, 0, 0.05 if depth > 0 else 0.1))).normalized()
            cur = cur + dv * (length / n)
            pts.append(cur.copy())
            radii.append(max(0.012, r * (1 - 0.78 * i / n)))
        segs = [12, 9, 6, 5, 4][min(depth, 4)]
        tubes.append((pts, radii, segs, depth))
        if depth >= maxd:
            return
        nch = rng.randint(2, 3) if depth < 2 else rng.randint(1, 3)
        for k in range(nch):
            i = rng.randint(max(1, int(n * 0.35)), n - 1) if k else n - 1
            base_d = (pts[i] - pts[i - 1]).normalized()
            axis = base_d.orthogonal().normalized()
            axis.rotate(Matrix.Rotation(rng.uniform(0, TAU), 3, base_d))
            nd = base_d.copy()
            nd.rotate(Matrix.Rotation(math.radians(rng.uniform(25, 60)), 3, axis))
            nd = (nd + Vector((0, 0, 0.15))).normalized()
            grow(pts[i], nd, length * rng.uniform(0.5, 0.72), radii[i] * rng.uniform(0.6, 0.78), depth + 1, maxd)

    # trunk with root flare
    base = Vector((x, y, -0.3))
    n = 10
    th = height * 0.5
    pts, radii = [], []
    dv = Vector((lean[0], lean[1], 1)).normalized()
    cur = base.copy()
    for i in range(n + 1):
        z = th * i / n
        pts.append(cur.copy())
        radii.append(r0 * (1 - 0.45 * i / n) * (1 + 0.9 * math.exp(-max(z - 0.3, 0) / 0.45)))
        dv = (dv + Vector((rng.uniform(-0.18, 0.18), rng.uniform(-0.18, 0.18), 0))).normalized()
        cur = cur + dv * (th / n)
    tubes.append((pts, radii, 14, 0))
    top = pts[-1]
    tdir = (pts[-1] - pts[-2]).normalized()
    for k in range(3):
        a = TAU * k / 3 + rng.uniform(-0.4, 0.4)
        d = Vector((math.cos(a) * spread, math.sin(a) * 0.6 * spread, 1.1)) + tdir * 0.5
        grow(top - tdir * 0.2, d, height * rng.uniform(0.38, 0.5), radii[-1] * 0.8, 1, 4)
    # a low side limb
    grow(pts[5], Vector((rng.choice((-1, 1)) * 1.0, 0.3, 0.5)), height * 0.35, radii[5] * 0.5, 2, 4)
    # roots
    for k in range(6):
        a = TAU * k / 6 + rng.uniform(-0.3, 0.3)
        rp = [Vector((x, y, 0.5)), Vector((x + math.cos(a) * 0.6, y + math.sin(a) * 0.6, 0.15)),
              Vector((x + math.cos(a) * 1.4, y + math.sin(a) * 1.4, -0.05)),
              Vector((x + math.cos(a + 0.3) * 2.3, y + math.sin(a + 0.3) * 2.3, -0.25))]
        tubes.append((rp, [r0 * 0.55, r0 * 0.38, r0 * 0.2, 0.04], 8, 1))
    for pts, radii, segs, depth in tubes:
        bm = ML.bm_tube(pts, radii, segs, cap_start=False, cap_end=True, uv_tiling=2.0,
                        lump=0.14 if depth < 2 else 0.06, lump_freq=2.5, seed=rng.randint(0, 999))
        B.add(cn, bm, 'M_Bark', uv='explicit', kind='soft')


def brazier(B, x, y, rng, s=1.0, tall=1.0):
    cn = 'Braziers'
    M = TRS((x, y, 0), (0, 0, rng.uniform(0, TAU)))
    zb = 1.0 * tall * s
    bowl = ML.bm_lathe([(0.05, 0.0), (0.22, 0.04), (0.38, 0.14), (0.46, 0.27), (0.49, 0.32), (0.44, 0.32),
                        (0.40, 0.22), (0.25, 0.12), (0.05, 0.09)], 20, cap_bottom=True, cap_top=True)
    bmesh.ops.scale(bowl, vec=(s, s, s), verts=bowl.verts)
    B.add(cn, bowl, 'M_Iron', M @ TRS((0, 0, zb)), uv='explicit', kind='soft')
    for i in range(10):
        a = TAU * i / 10
        sp = ML.bm_cyl(0.028 * s, 0.0, 0.17 * s, 6)
        B.add(cn, sp, 'M_Iron', M @ TRS((math.cos(a) * 0.465 * s, math.sin(a) * 0.465 * s, zb + 0.31 * s),
                                         (math.cos(a) * 0.25, -math.sin(a) * 0.0, 0)), kind='soft')
    for i in range(3):
        a = TAU * i / 3
        ca, sa = math.cos(a), math.sin(a)
        pts = [Vector((ca * 0.18 * s, sa * 0.18 * s, zb + 0.06 * s)), Vector((ca * 0.36 * s, sa * 0.36 * s, zb * 0.62)),
               Vector((ca * 0.5 * s, sa * 0.5 * s, zb * 0.25)), Vector((ca * 0.62 * s, sa * 0.62 * s, 0.03))]
        B.add(cn, ML.bm_tube(pts, [0.035 * s, 0.032 * s, 0.03 * s, 0.03 * s], 8), 'M_Iron', M, uv='explicit',
              kind='soft')
        B.add(cn, ML.bm_box(0.12 * s, 0.12 * s, 0.04 * s, 0.01), 'M_Iron', M @ TRS((ca * 0.63 * s, sa * 0.63 * s, 0.02)))
    ring = [Vector((math.cos(a) * 0.42 * s, math.sin(a) * 0.42 * s, zb * 0.5)) for a in np.linspace(0, TAU, 25)]
    B.add(cn, ML.bm_tube(ring, [0.022 * s] * 25, 6, False, False), 'M_Iron', M, uv='explicit', kind='soft')
    coals = ML.bm_lathe([(0.43, 0.0), (0.36, 0.08), (0.2, 0.15), (0.0, 0.17)], 16, cap_bottom=True, cap_top=False)
    ML.bm_noise(coals, 0.025, 9.0, rng.randint(0, 99), normal_only=True)
    bmesh.ops.scale(coals, vec=(s, s, s), verts=coals.verts)
    B.add(cn, coals, 'M_Ember', M @ TRS((0, 0, zb + 0.16 * s)), kind='soft')
    for i in range(7):
        a = rng.uniform(0, TAU)
        r = rng.uniform(0, 0.3) * s
        ch = ML.rock_bm(rng, (0.07 * s, 0.06 * s, 0.05 * s), sub=1, flat=0.0, rough=0.3)
        B.add(cn, ch, 'M_Ember', M @ TRS((math.cos(a) * r, math.sin(a) * r, zb + 0.3 * s), (0, 0, a)), kind='soft')
    top = (x, y, zb + 0.38 * s)
    B.add_fx('fire', top, 1.0 * s)
    B.add_fx('embers', (x, y, zb + 0.8 * s), 1.0 * s)
    B.light((x, y, zb + 0.95 * s), C(255, 136, 60), 3.2 * s, 9.0 * s)
    B.preview.append(('flame', Vector(top), s))


def skull(B, cn, M, rng):
    cr = ML.bm_sphere(0.1, 12, 8)
    bmesh.ops.scale(cr, vec=(0.82, 1.05, 0.88), verts=cr.verts)
    B.add(cn, cr, 'M_Bone', M @ TRS((0, -0.02, 0.09)), kind='soft')
    B.add(cn, ML.bm_box(0.11, 0.08, 0.075, 0.02), 'M_Bone', M @ TRS((0, 0.07, 0.04)), kind='soft')
    B.add(cn, ML.bm_box(0.09, 0.07, 0.03, 0.01), 'M_Bone', M @ TRS((0, 0.06, -0.01), (0.3, 0, 0)), kind='soft')


def bone(B, cn, M, rng, L=None):
    L = L or rng.uniform(0.25, 0.45)
    B.add(cn, ML.bm_tube([Vector((0, -L / 2, 0)), Vector((0, L / 2, 0))], [0.018, 0.016], 6, False, False), 'M_Bone',
          M, uv='explicit', kind='soft')
    for s in (-1, 1):
        for k in (-1, 1):
            B.add(cn, ML.bm_sphere(0.024, 6, 4), 'M_Bone', M @ TRS((k * 0.014, s * L / 2, 0)), kind='soft')


def bones_cluster(B, x, y, rng, n=5, skulls=1, spread=0.6):
    cn = 'Bones'
    for i in range(n):
        M = TRS((x + rng.uniform(-spread, spread), y + rng.uniform(-spread, spread), 0.02),
                (0, rng.uniform(-0.2, 0.2), rng.uniform(0, TAU)))
        bone(B, cn, M, rng)
    for i in range(skulls):
        M = TRS((x + rng.uniform(-spread, spread), y + rng.uniform(-spread, spread), 0.0),
                (rng.uniform(-0.4, 0.4), rng.uniform(-0.6, 0.6), rng.uniform(-2.5, 2.5)))
        skull(B, cn, M, rng)
    # a ribcage fragment
    if n >= 4:
        cx, cy = x + rng.uniform(-0.3, 0.3), y + rng.uniform(-0.3, 0.3)
        a0 = rng.uniform(0, TAU)
        Mr = TRS((cx, cy, 0.0), (0, 0, a0))
        B.add(cn, ML.bm_tube([Vector((0, -0.25, 0.04)), Vector((0, 0.25, 0.05))], [0.02, 0.018], 6), 'M_Bone', Mr,
              uv='explicit', kind='soft')
        for k in range(6):
            yy = -0.2 + k * 0.08
            for s in (-1, 1):
                pts = [Vector((0, yy, 0.05)), Vector((s * 0.1, yy, 0.12)), Vector((s * 0.18, yy + 0.02, 0.06)),
                       Vector((s * 0.2, yy + 0.04, 0.0))]
                if rng.random() < 0.8:
                    B.add(cn, ML.bm_tube(pts, [0.009] * 4, 5, False, False), 'M_Bone', Mr, uv='explicit', kind='soft')


def chain(B, cn, p_top, length, rng, link=0.11, r=0.011, mat='M_Iron'):
    """Vertical chain of alternating links hanging down from p_top."""
    n = int(length / (link * 0.78))
    x, y, z = p_top
    for i in range(n):
        zc = z - i * link * 0.78 - link / 2
        pts = []
        for k in range(11):
            t = TAU * k / 10
            pts.append(Vector((0.028 * math.cos(t), 0.0, (link / 2 - 0.02) * math.sin(t))))
        pts[-1] = pts[0].copy()
        bm = ML.bm_tube(pts, [r] * len(pts), 5, False, False)
        B.add(cn, bm, mat, TRS((x, y, zc), (0, 0, (i % 2) * math.pi / 2 + rng.uniform(-0.2, 0.2))), uv='explicit',
              kind='soft')


def gibbet_cage(B, x, y, rng, arm=1.6, h=4.6, cn='Gibbet'):
    """Rusted iron gallows with a hanging cage (and its long-dead occupant). Arm points toward -x."""
    B.add(cn, ML.bm_box(0.9, 0.9, 0.5, 0.04), 'M_Stone', TRS((x, y, 0.25), (0, 0, 0.1)))
    B.add(cn, ML.bm_box(0.15, 0.15, h, 0.01), 'M_Iron', TRS((x, y, 0.5 + h / 2)))
    B.add(cn, ML.bm_box(arm + 0.2, 0.12, 0.12, 0.01), 'M_Iron', TRS((x - arm / 2 + 0.05, y, 0.5 + h - 0.1)))
    br = ML.bm_tube([Vector((x, y, 0.5 + h - 1.1)), Vector((x - 0.9, y, 0.5 + h - 0.12))], [0.04, 0.04], 6, True, True)
    B.add(cn, br, 'M_Iron', uv='explicit', kind='soft')
    B.add(cn, ML.bm_sphere(0.09, 8, 6), 'M_Iron', TRS((x, y, 0.5 + h + 0.05)), kind='soft')
    top = (x - arm + 0.1, y, 0.5 + h - 0.16)
    clen = 1.0
    chain(B, cn, top, clen, rng)
    # cage
    cz1 = top[2] - clen - 0.05
    ch = 1.75
    cz0 = cz1 - ch
    cr = 0.42
    tilt = TRS((top[0], y, cz1), (rng.uniform(-0.06, 0.06), rng.uniform(-0.08, 0.08), rng.uniform(0, TAU)))
    nb = 12
    for k in range(nb):
        a = TAU * k / nb
        pts = []
        for j in range(8):
            t = j / 7
            rr = cr * (0.92 + 0.12 * math.sin(math.pi * t))
            pts.append(Vector((rr * math.cos(a), rr * math.sin(a), -ch * t)))
        B.add(cn, ML.bm_tube(pts, [0.014] * 8, 5, True, True), 'M_Iron', tilt, uv='explicit', kind='soft')
        dome = [Vector((cr * 0.92 * math.cos(a), cr * 0.92 * math.sin(a), 0.0)),
                Vector((cr * 0.6 * math.cos(a), cr * 0.6 * math.sin(a), 0.22)),
                Vector((0.04 * math.cos(a), 0.04 * math.sin(a), 0.32))]
        if k % 2 == 0:
            B.add(cn, ML.bm_tube(dome, [0.013] * 3, 5, False, False), 'M_Iron', tilt, uv='explicit', kind='soft')
    for zz in (0.0, -0.6, -1.2, -ch):
        rr = cr * (0.92 + 0.12 * math.sin(math.pi * (-zz / ch)))
        ring = [Vector((rr * math.cos(t), rr * math.sin(t), zz)) for t in np.linspace(0, TAU, 25)]
        B.add(cn, ML.bm_tube(ring, [0.02] * 25, 5, False, False), 'M_Iron', tilt, uv='explicit', kind='soft')
    B.add(cn, ML.bm_cyl(cr * 0.92, cr * 0.92, 0.03, 16), 'M_Iron', tilt @ TRS((0, 0, -ch - 0.02)), kind='soft')
    B.add(cn, ML.bm_cyl(0.06, 0.06, 0.1, 8), 'M_Iron', tilt @ TRS((0, 0, 0.3)), kind='soft')
    # remains inside
    sk = tilt @ TRS((0.12, 0.05, -ch + 0.03), (0.3, 0.2, 2.2))
    skull(B, cn, sk, rng)
    for k in range(4):
        bone(B, cn, tilt @ TRS((rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2), -ch + 0.05), (0, 0, rng.uniform(0, TAU))), rng)
    B.add(cn, ML.bm_tube([Vector((0, 0, -0.5)), Vector((0.05, 0.02, -1.2))], [0.02, 0.018], 6, False, False), 'M_Bone',
          tilt, uv='explicit', kind='soft')


def rubble_pile(B, x, y, rx, ry, h, n, rng, ember=0, cn='Rubble', mound_mat='M_Ash', size=(0.15, 0.6)):
    mound = ML.mound_bm(rx, ry, h * 0.55, 14, rng, power=1.4, noise_amp=0.3)
    B.add(cn, mound, mound_mat, TRS((x, y, 0)), uv='world', uvoff=False, kind='soft')
    for i in range(n):
        while True:
            u, v = rng.uniform(-1, 1), rng.uniform(-1, 1)
            if u * u + v * v < 1:
                break
        r2 = u * u + v * v
        hz = h * 0.55 * max(0, 1 - r2) ** 1.4 + h * 0.25 * max(0, 1 - r2 * 1.5)
        sz = rng.uniform(*size) * (1.2 - 0.5 * r2)
        mat = 'M_Ember' if (ember and rng.random() < ember) else 'M_Stone'
        if mat == 'M_Ember':
            sz *= 0.45
        bm = ML.rubble_bm(rng, sz * rng.uniform(0.9, 1.6), sz * rng.uniform(0.7, 1.2), sz * rng.uniform(0.5, 0.9))
        B.add(cn, bm, mat, TRS((x + u * rx, y + v * ry, hz - sz * 0.15),
                               (rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), rng.uniform(0, TAU))))


def scatter_small(B, x0, x1, y0, y1, n, rng, maxh=0.25, avoid=None, cn='Debris'):
    """Low debris (stone chips, slab fragments) -- safe for the camera side (< maxh)."""
    for i in range(n):
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        if avoid and avoid(x, y):
            continue
        s = rng.uniform(0.05, min(0.22, maxh))
        if rng.random() < 0.7:
            bm = ML.rubble_bm(rng, s * rng.uniform(1, 1.8), s * rng.uniform(0.8, 1.3), s * rng.uniform(0.4, 0.8), 0.012)
        else:
            bm = ML.bm_box(s * 2.5, s * 1.8, 0.05, 0.01)
            ML.bm_rough_cut(bm, (rng.uniform(-.05, .05), 0, 0), (1, rng.uniform(-1, 1), 0), rng, 2, 0.04)
        B.add(cn, bm, 'M_Stone', TRS((x, y, s * 0.12), (rng.uniform(-.3, .3), rng.uniform(-.3, .3), rng.uniform(0, TAU))))


def ash_patch(B, x, y, rx, ry, h, rng, cn='Ash'):
    B.add(cn, ML.mound_bm(rx, ry, h, 12, rng, power=1.8, noise_amp=0.35, sink=0.02), 'M_Ash', TRS((x, y, 0)),
          uv='world', uvoff=False, kind='soft')


def fence(B, p0, p1, rng, h=1.5):
    cn = 'Fence'
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = d.length
    ang = math.atan2(d.y, d.x)
    M = TRS((p0.x, p0.y, 0), (0, 0, ang))
    n = int(L / 0.15)
    lean = rng.uniform(-0.12, 0.12)
    for i in range(n + 1):
        x = i * L / n
        if rng.random() < 0.12:
            continue
        hh = h * rng.uniform(0.93, 1.0)
        top = Vector((rng.uniform(-0.05, 0.05), lean * hh, hh))
        if rng.random() < 0.15:
            top = Vector((rng.uniform(-0.4, 0.4), rng.uniform(0.1, 0.5), hh * 0.8))
        pts = [Vector((0, 0, -0.1)), Vector((0, 0, hh * 0.5)) + Vector((0, lean * hh * 0.5, 0)), top]
        B.add(cn, ML.bm_tube(pts, [0.013] * 3, 6, False, False), 'M_Iron', M @ TRS((x, 0, 0)), uv='explicit',
              kind='soft')
        tipd = (pts[-1] - pts[-2]).normalized()
        tip = ML.bm_prism([(0, 0.0), (0.035, 0.05), (0, 0.13), (-0.035, 0.05)], 0.012)
        R = tipd.to_track_quat('Z', 'Y').to_matrix().to_4x4()
        B.add(cn, tip, 'M_Iron', M @ TRS((x, 0, 0)) @ Matrix.Translation(top) @ R, kind='soft')
    for zz in (0.18, h - 0.22):
        rail = ML.bm_box(L, 0.025, 0.035, 0.005)
        B.add(cn, rail, 'M_Iron', M @ TRS((L / 2, lean * zz, zz)), kind='soft')
    for xx in (0, L):
        B.add(cn, ML.bm_box(0.1, 0.1, h + 0.1, 0.01), 'M_Iron', M @ TRS((xx, 0, (h + 0.1) / 2 - 0.05)))
        B.add(cn, ML.bm_sphere(0.07, 8, 6), 'M_Iron', M @ TRS((xx, 0, h + 0.1)), kind='soft')


def hanging_banner(B, x, y, ztop, w, h, rng, rot=0.0):
    cn = 'Banners'
    M = TRS((x, y, ztop), (0, 0, rot))
    rod = ML.bm_cyl(0.025, 0.025, w + 0.4, 8)
    B.add(cn, rod, 'M_Iron', M @ TRS((-(w + 0.4) / 2, 0.06, 0.03), (0, math.pi / 2, 0)), kind='soft')
    for s in (-1, 1):
        B.add(cn, ML.bm_box(0.04, 0.12, 0.04, 0.005), 'M_Iron', M @ TRS((s * (w / 2 + 0.15), 0.0, 0.03)))
    cl = ML.cloth_bm(w, h, 12, 26, rng, folds=2.5, fold_amp=0.06, tatter=0.38, holes=0.07, thickness=0.012,
                     uv_norm=False, points=0)
    B.add(cn, cl, 'M_Cloth', M @ TRS((0, 0.1, 0.0)), uv='explicit', kind='soft')


def slab_fragment(B, x, y, rng, cn='Debris'):
    w, d = rng.uniform(0.6, 1.0), rng.uniform(0.45, 0.8)
    bm = ML.bm_box(w, d, 0.12, 0.02)
    ML.bm_rough_cut(bm, (rng.uniform(-.15, .15), 0, 0), (1, rng.uniform(-1, 1), rng.uniform(-.2, .2)), rng, 2, 0.05)
    if rng.random() < 0.5:
        ML.bm_chip(bm, rng, 2)
    B.add(cn, bm, 'M_Stone', TRS((x, y, 0.02), (rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), rng.uniform(0, TAU))))


def column_piece(B, x, y, rng, h, r=0.42, toppled=False, cn='Columns'):
    if not toppled:
        B.add(cn, ML.bm_box(r * 2.6, r * 2.6, 0.3, 0.04), 'M_Stone', TRS((x, y, 0.15), (0, 0, rng.uniform(0, 1))))
        ML.column_drums(B, cn, TRS((x, y, 0.3)), h, r, rng, 'M_Stone', segs=16)
    else:
        a = rng.uniform(0, TAU)
        d = Vector((math.cos(a), math.sin(a), 0))
        z = 0
        pos = Vector((x, y, r * 0.97))
        for k in range(rng.randint(2, 4)):
            dh = rng.uniform(0.5, 0.8)
            bm = ML.bm_cyl(r, r, dh, 16)
            if rng.random() < 0.5:
                ML.bm_rough_cut(bm, (0, 0, dh * 0.8), (rng.uniform(-.5, .5), 0, 1), rng, 2)
            ML.bm_chip(bm, rng, 1)
            gap = rng.uniform(0.0, 0.25)
            off = d * (z + gap)
            jit = rng.uniform(-0.25, 0.25)
            M = TRS(pos + off, (0, 0, 0)) @ Matrix.Rotation(a + jit, 4, 'Z') @ Matrix.Rotation(math.pi / 2, 4, 'Y')
            B.add(cn, bm, 'M_Stone', M)
            z += dh + gap


# =============================================================================================
# Architecture
# =============================================================================================
def string_course(B, cn, M, x0, x1, z, thick, top_fn, rng, hgt=0.22, proud=0.16, openings=()):
    x = x0
    while x < x1 - 0.1:
        L = min(rng.uniform(0.6, 1.1), x1 - x)
        blocked = False
        for o in openings:
            for zz in (z, z + hgt):
                hw = o.hw(zz)
                if hw is not None and abs(x + L / 2 - o.cx) < hw + L / 2:
                    blocked = True
        if not blocked and z + hgt + 0.45 < min(top_fn(x), top_fn(x + L / 2), top_fn(x + L)):
            bm = ML.bm_box(L - 0.006, proud + 0.2, hgt, 0.02)
            ML.bm_cut(bm, (0, (proud + 0.2) / 2, hgt / 2 - 0.06), (0, 0.7, 0.7))
            B.add(cn, bm, 'M_Stone', M @ TRS((x + L / 2, thick / 2 + (proud + 0.2) / 2 - 0.2, z + hgt / 2)))
        x += L


def pinnacle(B, cn, pos, rng, s=1.0, mat='M_Stone'):
    x, y, z = pos
    B.add(cn, ML.bm_cyl(0.32 * s, 0.32 * s, 1.0 * s, 8), mat, TRS((x, y, z)), kind='hard')
    B.add(cn, ML.bm_cyl(0.4 * s, 0.4 * s, 0.14 * s, 8), mat, TRS((x, y, z + 1.0 * s)), kind='hard')
    B.add(cn, ML.bm_cyl(0.34 * s, 0.0, 2.0 * s, 8), mat, TRS((x, y, z + 1.14 * s)), kind='hard')
    for k in range(4):
        a = TAU * k / 4 + 0.4
        zz = z + 1.5 * s + k * 0.3 * s
        rr = 0.3 * s * (1 - (zz - z - 1.14 * s) / (2.0 * s)) + 0.03
        B.add(cn, ML.bm_sphere(0.07 * s, 6, 4), mat, TRS((x + math.cos(a) * rr, y + math.sin(a) * rr, zz)), kind='soft')
    B.add(cn, ML.bm_sphere(0.1 * s, 8, 6), mat, TRS((x, y, z + 3.15 * s)), kind='soft')


def buttress(B, cn, x, y_face, height, rng, top_fn=None, width=1.3, depth=1.3, pin=True, mat='M_Stone',
             freestanding=False):
    """Stepped buttress against a wall face at y_face (projecting toward +y)."""
    z = 0.0
    stages = [0.0, height * 0.42, height * 0.75]
    while z < height - 0.05:
        ch = min(rng.uniform(0.42, 0.6), height - z)
        st = sum(1 for s in stages if z >= s) - 1
        d = depth - 0.3 * st
        w = width - 0.12 * st
        t = top_fn(x) if top_fn else height
        if z > t - 0.1:
            break
        # two blocks per course, alternating split direction
        if int(z / 0.5) % 2:
            parts = [(0, w, d * 0.55, d * 0.275), (0, w, d * 0.45, d * 0.55 + d * 0.225)]
        else:
            parts = [(-w * 0.25, w * 0.5, d, d / 2), (w * 0.25, w * 0.5, d, d / 2)]
        for (ox, pw, pd, py) in parts:
            bm = ML.bm_box(pw - 0.006, pd - 0.006, ch - 0.006, 0.03)
            if z + ch > t:
                ML.bm_rough_cut(bm, (0, 0, t - z - ch / 2), (rng.uniform(-.4, .4), rng.uniform(-.4, .4), 1), rng, 2)
            elif rng.random() < 0.3:
                ML.bm_chip(bm, rng, 1)
            yy = (y_face + py) if not freestanding else (y_face + py - d / 2)
            B.add(cn, bm, mat, TRS((x + ox, yy, z + ch / 2), (0, 0, rng.uniform(-0.01, 0.01))))
        # set-off weathering slope
        nz = z + ch
        for s in stages[1:]:
            if z < s <= nz + 1e-6 and nz < t:
                bm = ML.bm_box(w, 0.42, 0.3, 0.02)
                ML.bm_cut(bm, (0, 0.21, 0.0), (0, 0.6, 0.8))
                yy = y_face + d - 0.21 if not freestanding else y_face + d / 2 - 0.21
                B.add(cn, bm, mat, TRS((x, yy, nz + 0.15)))
        z = nz
    if pin and (top_fn is None or top_fn(x) > height + 0.5):
        d = depth - 0.6
        yy = y_face + d / 2 if not freestanding else y_face
        cap = ML.bm_box(width - 0.2, d, 0.5, 0.03)
        B.add(cn, cap, mat, TRS((x, yy, height + 0.25)))
        pinnacle(B, cn, (x, yy, height + 0.5), rng, 0.9)


def flyer(B, cn, x, y_pier, z_pier, y_wall, z_wall, rng, w=0.75, top_fn=None):
    """Flying buttress arch from a pier top (y_pier, z_pier) to the wall face (y_wall, z_wall)."""
    n = 9
    P0 = Vector((y_pier, z_pier - 1.2))
    P2 = Vector((y_wall, z_wall))
    P1 = Vector((y_pier, z_wall + 0.2))
    T0 = Vector((y_pier, z_pier + 0.3))
    pts = []
    tops = []
    for i in range(n + 1):
        t = i / n
        p = (1 - t) ** 2 * P0 + 2 * (1 - t) * t * P1 + t * t * P2
        pts.append(p)
        tops.append(T0.lerp(Vector((y_wall, z_wall + 1.3)), t))
    for i in range(n):
        a0, a1, b0, b1 = pts[i], pts[i + 1], tops[i], tops[i + 1]
        if top_fn and (a0.y + b1.y) / 2 > 99:
            continue
        q = [(-w / 2, a0.x, a0.y), (w / 2, a0.x, a0.y), (w / 2, a1.x, a1.y), (-w / 2, a1.x, a1.y),
             (-w / 2, b0.x, b0.y), (w / 2, b0.x, b0.y), (w / 2, b1.x, b1.y), (-w / 2, b1.x, b1.y)]
        bm = ML.bm_hex(q, 0.03)
        B.add(cn, bm, 'M_Stone', TRS((x, 0, 0)))


def nave_wall(B, rng):
    """Main midground ruin: arcade + clerestory, collapsed in the middle. Wall front face ~y=-9.3."""
    cn = 'NaveWall'
    L = 81.2
    x0 = -40.6
    yc = -10.0
    thick = 1.4
    M = TRS((x0, yc, 0))
    peaks_w = [(-40.6, 7), (-37, 18.5), (-31, 21.5), (-25, 18), (-19.5, 14.5), (-15, 11.0), (-11.5, 7.5),
               (-9, 4.2), (-6.5, 2.2), (-3.5, 1.2), (0, 0.9), (2.5, 1.3), (5.5, 2.2), (8.0, 4.6), (10.5, 8.0),
               (14, 12.5), (19, 18.0), (24.5, 21.0), (30, 22.5), (35.5, 16), (40.6, 8)]
    peaks = [(x - x0, h) for x, h in peaks_w]
    top = ML.ruin_profile(L, 0, peaks, rng, rough=0.7, seed=3)
    ops = []
    for k in range(-6, 7):
        cx = 6.2 * k - x0
        ops.append(ML.Opening(cx, 4.4, 0.0, 5.4, k=0.8, ring=0.5, shafts=True, hood=True))
        if abs(6.2 * k) > 9:
            ops.append(ML.Opening(cx, 2.3, 12.2, 15.8, k=1.15, ring=0.32, tracery='oculus', hood=True))
    ML.masonry_wall(B, cn, M, L, thick, top, ops, course=(0.36, 0.5), blen=(0.6, 1.3), rng=rng, chip=0.25,
                    plinth=(0.45, 0.1), holes=0.04)
    for zc in (9.6, 17.6):
        string_course(B, cn, M, 0, L, zc, thick, top, rng, openings=ops)
    # attached buttresses at pier centres
    for k in range(-6, 6):
        xw = 6.2 * k + 3.1
        hb = 9.0 if abs(xw) < 12 else 14.5
        buttress(B, cn, xw, yc + thick / 2, hb, rng, top_fn=lambda xx, _t=top: _t(xx - x0) - 0.4, width=1.3,
                 depth=1.15, pin=True)
    return top, x0


def flying_buttresses(B, rng, top, x0):
    cn = 'Buttresses'
    for xw in (-34.1, -27.9, -21.7, -15.5, 15.5, 21.7, 27.9, 34.1):
        wall_top = top(xw - x0)
        h = min(13.0, wall_top - 1.0) if abs(xw) > 16 else 9.5
        h = h + rng.uniform(-0.8, 0.8)
        yp = -5.6
        buttress(B, cn, xw, yp, h, rng, width=1.5, depth=2.4, freestanding=True, pin=True)
        if wall_top > 14.5 and h > 11:
            flyer(B, cn, xw, yp - 1.0, h, -9.25, min(14.2, wall_top - 0.5), rng)


def side_walls(B, rng):
    """Collapsed walls running toward the camera at both sides (frame the stage when panned)."""
    for side in (-1, 1):
        cn = 'SideWalls'
        xw = side * 20.5
        L = 16.0
        # local x runs along -y (from y=-8 toward the camera); face toward the stage (inwards)
        ang = -math.pi / 2 if side > 0 else math.pi / 2
        start = Vector((xw, -8.0 if side > 0 else 8.0, 0))
        M = TRS(start, (0, 0, ang))
        if side < 0:
            peaks = [(0, 1.5), (3, 4), (6, 9.5), (10, 12.5), (13, 13), (16, 10)]
        else:
            peaks = [(0, 11), (3, 13.5), (7, 12), (10, 7.5), (13, 3.5), (16, 1.0)]
        top = ML.ruin_profile(L, 0, peaks, rng, rough=0.6, seed=7 + side)
        ops = [ML.Opening(4.0, 1.9, 2.4, 6.6, k=1.3, ring=0.3, tracery=None, hood=True, shafts=True),
               ML.Opening(10.0, 1.9, 2.4, 6.6, k=1.3, ring=0.3, tracery=None, hood=True, shafts=True)]
        ML.masonry_wall(B, cn, M, L, 1.2, top, ops, course=(0.36, 0.5), rng=rng, plinth=(0.4, 0.08), holes=0.05)
        for xb in (1.0, 7.0, 13.0):
            p = M @ Vector((xb, 0.6, 0))
            h = top(xb) - 0.6
            if h > 1.0:
                # buttress local frame
                bcn = 'SideWalls'
                Mb = M @ TRS((xb, 0.6, 0))
                z = 0
                while z < h:
                    ch = min(rng.uniform(0.42, 0.6), h - z)
                    bm = ML.bm_box(1.1, 0.9, ch - 0.006, 0.03)
                    if z + ch >= h - 0.01:
                        ML.bm_rough_cut(bm, (0, 0, ch / 2 - 0.1), (rng.uniform(-.5, .5), 0.3, 1), rng, 2)
                    B.add(bcn, bm, 'M_Stone', Mb @ TRS((0, 0.45, z + ch / 2)))
                    z += ch


def gable_and_tower(B, rng):
    """Background layer (~25-35 m behind the stage): transept gable with a great window + bell tower stump."""
    cn = 'Background'
    # transept gable wall
    L = 22.0
    x0 = 7.0
    M = TRS((x0, -28.0, 0))
    peaks = [(0, 6), (2.5, 15), (6, 21.0), (11, 24.0), (14.5, 19.5), (17, 13), (19.5, 9), (22, 4)]
    top = ML.ruin_profile(L, 0, peaks, rng, rough=0.8, seed=11)
    ops = [ML.Opening(11.0, 6.2, 4.5, 13.5, k=1.0, ring=0.6, tracery='oculus', hood=True, shafts=True),
           ML.Opening(3.0, 1.8, 6.0, 10.5, k=1.2, ring=0.3, hood=True),
           ML.Opening(19.0, 1.8, 6.0, 10.5, k=1.2, ring=0.3, hood=True)]
    ML.masonry_wall(B, cn, M, L, 1.6, top, ops, course=(0.45, 0.62), blen=(0.8, 1.5), rng=rng, chip=0.2,
                    plinth=(0.5, 0.12))
    for xb in (0.0, 22.0):
        hb = top(xb) - 1.0
        buttress(B, cn, x0 + xb, -28.0 + 0.8, max(hb, 3), rng, width=1.6, depth=1.6, pin=hb > 18)
    # bell tower stump (square, four walls)
    tx, ty, tw = -20.0, -33.0, 7.5
    th = 1.5
    rngt = random.Random(77)
    for i, (sx, sy, ang) in enumerate(((tx - tw / 2, ty + tw / 2, 0.0), (tx + tw / 2, ty - tw / 2, math.pi),
                                       (tx + tw / 2, ty + tw / 2, -math.pi / 2), (tx - tw / 2, ty - tw / 2, math.pi / 2))):
        Mt = TRS((sx, sy, 0), (0, 0, ang))
        pk = [(0, 25 + rngt.uniform(-3, 3)), (tw / 2, 28 + rngt.uniform(-4, 2)), (tw, 23 + rngt.uniform(-3, 3))]
        if i == 0:
            pk = [(0, 27), (2.5, 29.5), (5, 24.5), (tw, 22)]
        topt = ML.ruin_profile(tw, 0, pk, rngt, rough=0.9, seed=20 + i)
        opst = [ML.Opening(tw / 2, 2.0, 17.0, 21.5, k=1.2, ring=0.35, hood=True, shafts=False),
                ML.Opening(tw / 2, 1.2, 8.0, 11.0, k=1.1, ring=0.25, hood=False)]
        ML.masonry_wall(B, cn, Mt, tw, th, topt, opst, course=(0.55, 0.75), blen=(1.0, 1.7), rng=rngt, chip=0.15,
                        jitter=0.006, bevel=0.04)
    for (cx, cy) in ((tx - tw / 2, ty + tw / 2), (tx + tw / 2, ty + tw / 2)):
        buttress(B, cn, cx, cy, 17.0 + rngt.uniform(-2, 2), rngt, width=1.4, depth=1.4, pin=False)


def far_cathedral(B, rng):
    """Huge cathedral silhouette ~160 m away on a plateau. Big masses + glowing windows + spires.
    Sized so the spires just fit under the top of the gameplay frame."""
    cn = 'FarCathedral'
    mat = 'M_StoneBrick'
    xc, yf, zb = 1.0, -150.0, 3.0

    def box(x, y, z, sx, sy, sz, bev=0.15):
        B.add(cn, ML.bm_box(sx, sy, sz, bev), mat, TRS((x, y, z + sz / 2)))

    def arch_poly(w, h, k=1.0):
        sp = h - w * 0.8
        r = w * k
        off = r - w / 2
        poly = [(-w / 2, 0), (w / 2, 0)] + ML.arch_points(0, sp, r, off, 6, 0, 1) + \
            list(reversed(ML.arch_points(0, sp, r, off, 6, 0, -1)))[1:]
        clean = []
        for p in poly:
            if not clean or abs(p[0] - clean[-1][0]) + abs(p[1] - clean[-1][1]) > 1e-4:
                clean.append(p)
        return clean

    def glow_window(x, y, z, w, h, rot=0.0, mull=True):
        B.add(cn, ML.bm_prism(arch_poly(w, h, 1.1), 0.4), 'M_Glow', TRS((x, y, z), (0, 0, rot)))
        frame = ML.bm_prism(arch_poly(w + 0.5, h + 0.35, 1.1), 0.25)
        B.add(cn, frame, mat, TRS((x, y - 0.12, z - 0.05), (0, 0, rot)))
        if mull:
            B.add(cn, ML.bm_box(w * 0.09, 0.7, h * 0.86, 0.02), mat, TRS((x, y, z + h * 0.43), (0, 0, rot)))

    def spire(x, y, z, r, h, broken=False):
        bm = ML.bm_cyl(r, r * 0.04, h, 8)
        if broken:
            ML.bm_rough_cut(bm, (0, 0, h * 0.58), (0.5, 0.2, 1), rng, 3, 0.4, 0.4)
        B.add(cn, bm, mat, TRS((x, y, z), (0, 0, math.pi / 8)))
        for k in range(8):
            a = TAU * k / 8 + math.pi / 8
            for j in range(5 if not broken else 3):
                t = 0.1 + j * 0.15
                rr = r * (1 - t) * 0.93 + 0.12
                B.add(cn, ML.bm_box(0.45, 0.45, 0.7, 0.04), mat,
                      TRS((x + math.cos(a) * rr, y + math.sin(a) * rr, z + t * h), (0, 0, a)))
        for k in range(4):
            a = TAU * k / 4 + math.pi / 4
            pinnacle(B, cn, (x + math.cos(a) * (r + 0.5), y + math.sin(a) * (r + 0.5), z), rng, 1.6, mat)
        if not broken:
            B.add(cn, ML.bm_cyl(0.12, 0.05, 2.5, 6), 'M_Iron', TRS((x, y, z + h - 0.3)))

    # plateau / hill under the cathedral
    hill = ML.mound_bm(120, 60, zb + 3, 22, rng, power=0.6, noise_amp=0.15, noise_freq=0.03, flat_top=0.55)
    B.add(cn, hill, 'M_Ash', TRS((xc, yf - 30, -3)), uv='world', uvoff=False, kind='soft')
    # west towers
    TW, TH = 9.0, 29.0
    for side, broken in ((-1, False), (1, True)):
        tx = xc + side * 12.5
        box(tx, yf - TW / 2, zb, TW, TW, TH)
        for sx in (-1, 1):
            for st, (z0, hh, ww) in enumerate(((0, 11, 2.3), (11, 10, 1.8), (21, 7, 1.4))):
                box(tx + sx * (TW / 2 - 0.2), yf + ww / 2 - 0.2, zb + z0, ww, ww, hh, 0.1)
                wz = ML.bm_box(ww, ww, 1.0, 0.05)
                ML.bm_cut(wz, (0, ww / 2, 0), (0, 0.6, 0.8))
                B.add(cn, wz, mat, TRS((tx + sx * (TW / 2 - 0.2), yf + ww / 2 - 0.2, zb + z0 + hh + 0.5)))
        for lvl, (zz, hh) in enumerate(((7.0, 5.0), (14.5, 5.5), (21.5, 5.5))):
            for k in (-1, 1):
                glow_window(tx + k * 1.9, yf + 0.15, zb + zz, 1.5, hh)
        box(tx, yf - TW / 2, zb + TH, TW + 0.7, TW + 0.7, 1.0)
        for cx in (-1, 1):
            for cy in (-1, 1):
                pinnacle(B, cn, (tx + cx * TW / 2, yf - TW / 2 + cy * TW / 2, zb + TH + 1.0), rng, 1.6, mat)
        spire(tx, yf - TW / 2, zb + TH + 1.0, 3.6, 16.5, broken=broken)
    # central front between the towers
    box(xc, yf - 3, zb, 16.0, 6, 24)
    gable = ML.bm_prism([(-8.0, 0), (8.0, 0), (0, 8.5)], 5.5, 0.1)
    B.add(cn, gable, mat, TRS((xc, yf - 3, zb + 24)))
    for gx in (-1, 0, 1):
        pinnacle(B, cn, (xc + gx * 8.0, yf - 0.5, zb + 24 + (8.5 if gx == 0 else 0)), rng, 1.3, mat)
    rz = zb + 17.0
    B.add(cn, ML.bm_cyl(4.0, 4.0, 0.4, 32), 'M_Glow', TRS((xc, yf + 0.1, rz), (math.pi / 2, 0, 0)))
    B.add(cn, ML.bm_lathe([(4.0, 0), (4.8, 0), (4.8, 0.8), (4.0, 0.8)], 32, False, False), mat,
          TRS((xc, yf + 0.9, rz), (math.pi / 2, 0, 0)))
    for k in range(12):
        a = TAU * k / 12
        B.add(cn, ML.bm_box(0.28, 0.6, 4.0, 0.03), mat, TRS((xc + math.cos(a) * 2.0, yf + 0.3, rz + math.sin(a) * 2.0),
                                                           (0, -a + math.pi / 2, 0)))
    B.add(cn, ML.bm_cyl(0.8, 0.8, 0.7, 16), mat, TRS((xc, yf + 0.65, rz), (math.pi / 2, 0, 0)))
    # portals (stepped dark recesses)
    for px, pw, ph in ((xc, 5.2, 9.5), (xc - 12.5, 3.2, 7.0), (xc + 12.5, 3.2, 7.0)):
        for k in range(4):
            B.add(cn, ML.bm_prism(arch_poly(pw + 1.4 - k * 0.4, ph + 1.2 - k * 0.35, 0.95), 0.5), mat,
                  TRS((px, yf + 0.6 - k * 0.4, zb)))
        B.add(cn, ML.bm_box(pw * 0.8, 0.3, ph * 0.7, 0.02), 'M_Iron', TRS((px, yf - 1.2, zb + ph * 0.35)))
    for k in range(-3, 4):
        glow_window(xc + k * 2.0, yf + 0.15, zb + 11.0, 1.2, 3.6)
    # nave + roof + aisles + flying buttresses
    NL = 70.0
    ny = yf - 6 - NL / 2
    box(xc, ny, zb, 15, NL, 26, 0.2)
    roof = ML.bm_prism([(-8, 0), (8, 0), (0, 9)], NL, 0.1)
    B.add(cn, roof, mat, TRS((xc, ny, zb + 26)))
    for side in (-1, 1):
        box(xc + side * 11, ny, zb, 7, NL, 13, 0.2)
        for k in range(9):
            yy = yf - 12 - k * 7.5
            box(xc + side * 16, yy, zb, 2.0, 2.0, 19, 0.1)
            pinnacle(B, cn, (xc + side * 16, yy, zb + 19), rng, 1.4, mat)
            q = [(xc + side * 15.2, yy - 0.4, zb + 15), (xc + side * 15.2, yy + 0.4, zb + 15),
                 (xc + side * 7.6, yy + 0.4, zb + 22), (xc + side * 7.6, yy - 0.4, zb + 22),
                 (xc + side * 15.2, yy - 0.4, zb + 17), (xc + side * 15.2, yy + 0.4, zb + 17),
                 (xc + side * 7.6, yy + 0.4, zb + 24), (xc + side * 7.6, yy - 0.4, zb + 24)]
            B.add(cn, ML.bm_hex(q, 0.05), mat)
            glow_window(xc + side * 7.55, yy - 3.7, zb + 14.5, 1.6, 7.0, rot=math.pi / 2, mull=False)
    # transept arms with gable ends facing the sides
    for side in (-1, 1):
        box(xc + side * 18, yf - 42, zb, 21, 15, 25, 0.2)
        g = ML.bm_prism([(-7.5, 0), (7.5, 0), (0, 8)], 2.0, 0.1)
        B.add(cn, g, mat, TRS((xc + side * 27.5, yf - 42, zb + 25), (0, 0, math.pi / 2)))
        glow_window(xc + side * 18, yf - 34.4, zb + 8, 3.8, 11.5)
        for cx in (-1, 1):
            pinnacle(B, cn, (xc + side * 18 + cx * 10.2, yf - 34.8, zb + 25), rng, 1.6, mat)
    # crossing tower + great spire
    box(xc, yf - 42, zb + 26, 13, 13, 12)
    for k in (-1, 0, 1):
        glow_window(xc + k * 3.6, yf - 35.4, zb + 29, 1.9, 7.0)
    box(xc, yf - 42, zb + 38, 13.6, 13.6, 0.8)
    spire(xc, yf - 42, zb + 38.8, 5.4, 19.5)
    # ruined outbuildings / towers on the plateau
    for sx in (-1, 1):
        for k in range(3):
            tx = xc + sx * (36 + k * 16 + rng.uniform(-3, 3))
            ty = yf + rng.uniform(-25, 10)
            h = rng.uniform(12, 22) - k * 2
            bm = ML.bm_box(6.5, 6.5, h, 0.15)
            ML.bm_rough_cut(bm, (0, 0, h / 2 - rng.uniform(1, 4)), (rng.uniform(-.6, .6), rng.uniform(-.6, .6), 1), rng, 3,
                            1.0, 0.5)
            B.add(cn, bm, mat, TRS((tx, ty, zb - 1 + h / 2)))
            if rng.random() < 0.6:
                glow_window(tx, ty + 3.35, zb + h * 0.35, 1.4, 4.0)


def mid_ruins(B, rng):
    """Layer between the background gable and the far cathedral (y -40 .. -120): broken walls,
    towers, colonnades, dead trees, fires.  Kept low in the centre so the cathedral reads.
    Large blocks to save triangles."""
    cn = 'MidRuins'
    specs = [(-36, -46, 14, 0.15, 11), (30, -50, 12, -0.2, 12), (-60, -68, 18, 0.35, 16), (52, -72, 16, -0.4, 15),
             (-8, -62, 16, 0.05, 4.5), (16, -92, 14, -0.1, 7), (78, -100, 20, -0.5, 18), (-82, -105, 22, 0.4, 17),
             (-30, -98, 14, 0.2, 10)]
    for i, (x, y, L, ang, h) in enumerate(specs):
        r = random.Random(500 + i)
        M = TRS((x - L / 2 * math.cos(ang), y - L / 2 * math.sin(ang), 0), (0, 0, ang))
        peaks = [(0, h * r.uniform(0.2, 0.5)), (L * 0.3, h * r.uniform(0.6, 1.0)), (L * 0.6, h),
                 (L, h * r.uniform(0.1, 0.5))]
        if i % 2:
            peaks = [(p[0], peaks[len(peaks) - 1 - k][1]) for k, p in enumerate(peaks)]
        top = ML.ruin_profile(L, 0, peaks, r, rough=0.8, seed=40 + i)
        ops = []
        n = max(1, int(L / 5.5))
        for k in range(n):
            cx = (k + 0.5) * L / n
            if r.random() < 0.7 and h > 6:
                ops.append(ML.Opening(cx, 2.4, 0.0 if r.random() < 0.4 else 3.0, 6.0, k=1.1, ring=0.4, hood=False))
        ML.masonry_wall(B, cn, M, L, 1.8, top, ops, course=(0.7, 0.9), blen=(1.4, 2.4), bevel=0.06, rng=r,
                        chip=0.1, jitter=0.004, protrude=0.04)
    for (x, y, h) in ((-30, -58, 21), (36, -64, 24), (-52, -90, 28), (40, -112, 20)):
        bm = ML.bm_box(6, 6, h, 0.12)
        ML.bm_rough_cut(bm, (0, 0, h / 2 - 2), (rng.uniform(-.6, .6), rng.uniform(-.6, .6), 1), rng, 3, 1.0, 0.5)
        B.add(cn, bm, 'M_StoneBrick', TRS((x, y, h / 2), (0, 0, rng.uniform(-.3, .3))))
    # colonnade of broken columns (left-centre)
    for k in range(9):
        r = random.Random(900 + k)
        x = 8 + k * 4.2
        h = r.uniform(2.0, 8.5) if k % 3 else r.uniform(0.6, 2.5)
        ML.column_drums(B, cn, TRS((x, -42.0, 0)), h, 0.7, r, 'M_Stone', drum=(0.9, 1.3), segs=14)
    # distant fires (glowing heaps, fx only -- no point lights that far)
    for (x, y) in ((-22, -55), (24, -78), (-48, -96), (6, -70)):
        rubble_pile(B, x, y, 3.0, 2.5, 1.6, 10, rng, ember=0.5, cn=cn, size=(0.4, 1.0))
        B.add_fx('fire', (x, y, 1.2), 2.0)
        B.add_fx('embers', (x, y, 3.0), 2.0)
        B.preview.append(('flame', Vector((x, y, 1.0)), 2.2))
    # dead trees on the ridge
    for (x, y, hh) in ((-34, -58, 7), (40, -62, 9), (-70, -90, 10), (64, -96, 9), (-14, -78, 6)):
        dead_tree(B, x, y, random.Random(int(x * 7 + y)), height=hh, r0=0.35)


def terrain(B, rng):
    # courtyard floor (flagstones) + surrounding ash ground, very slight undulation outside the stage
    def zf(x, y):
        if abs(x) < 12 and -6 < y < 9:
            return 0.0
        d = max(abs(x) - 12, 0) + max(-6 - y, 0) * 0.6 + max(y - 9, 0)
        k = min(1.0, d / 10.0)
        return k * (0.25 * mnoise.noise(Vector((x * 0.08, y * 0.08, 0.3))) + 0.12)

    def matf(x, y):
        return 0 if (abs(x) < 26 and -16 < y < 14) else 1
    bm = ML.heightfield_bm(-60, 60, -60, 20, 80, 50, zf, matf)
    B.add('Floor', bm, ['M_Floor', 'M_Ash'], uv='world', uvoff=False, kind='soft')
    # distant ground out to the far plateau
    def zf2(x, y):
        base = 0.15 if y > -100 else 0.15 + (-100 - y) * 0.02
        return base + 2.5 * (0.5 + mnoise.noise(Vector((x * 0.02, y * 0.02, 1.7)))) * min(1, (-60 - y) / 30.0)
    bm = ML.heightfield_bm(-260, 260, -260, -59.5, 52, 40, zf2)
    B.add('FarGround', bm, 'M_Ash', uv='world', uvoff=False, kind='soft')
    # broad side ground strips (|x| 60..260 near field)
    for sx in (-1, 1):
        bm = ML.heightfield_bm(60 if sx > 0 else -260, 260 if sx > 0 else -60, -60, 40, 20, 10,
                               lambda x, y: 0.3 + 1.5 * (0.5 + mnoise.noise(Vector((x * 0.03, y * 0.03, 2.2)))))
        B.add('FarGround', bm, 'M_Ash', uv='world', uvoff=False, kind='soft')


def far_ridges(B, rng):
    """Low craggy ridges flanking the plateau so the horizon line is never empty."""
    cn = 'FarRidges'
    for i in range(14):
        sx = -1 if i % 2 else 1
        x = sx * rng.uniform(50, 240)
        y = rng.uniform(-260, -110)
        rx, ry = rng.uniform(30, 60), rng.uniform(20, 40)
        h = rng.uniform(10, 26)
        B.add(cn, ML.mound_bm(rx, ry, h, 12, rng, power=0.9, noise_amp=0.35, noise_freq=0.05), 'M_Ash',
              TRS((x, y, -1)), uv='world', uvoff=False, kind='soft')
        for k in range(rng.randint(2, 5)):
            s = rng.uniform(3, 9)
            rk = ML.rock_bm(rng, (s * 1.4, s, s * 1.6), 2, 0.3, 0.3)
            u, v = rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4)
            hz = h * max(0.0, 1 - (u * u + v * v)) ** 0.9 * 0.75 - 1 - s * 0.4
            B.add(cn, rk, 'M_Stone', TRS((x + u * rx, y + v * ry, hz), (0, 0, rng.uniform(0, TAU))), kind='soft')


# =============================================================================================
# Scene assembly
# =============================================================================================
def build(B):
    rng = random.Random(1234)
    terrain(B, rng)
    top, x0 = nave_wall(B, random.Random(1))
    flying_buttresses(B, random.Random(2), top, x0)
    side_walls(B, random.Random(3))
    gable_and_tower(B, random.Random(4))
    mid_ruins(B, random.Random(5))
    far_cathedral(B, random.Random(6))
    far_ridges(B, random.Random(8))

    r = random.Random(9)
    # --- near backdrop: low broken parapet with gaps along y=-4.6
    cn = 'Parapet'
    for (xa, xb) in ((-11.5, -6.8), (-5.0, -1.4), (1.2, 4.6), (6.4, 11.2)):
        L = xb - xa
        M = TRS((xa, -4.7, 0))
        pk = [(0, r.uniform(0.3, 1.2)), (L * 0.5, r.uniform(0.9, 1.3)), (L, r.uniform(0.3, 1.1))]
        tp = ML.ruin_profile(L, 0, pk, r, rough=0.25, seed=int(xa * 10))
        ML.masonry_wall(B, cn, M, L, 0.6, tp, [], course=(0.28, 0.36), blen=(0.4, 0.8), rng=r, chip=0.4,
                        bevel=0.025)
        x = 0
        while x < L - 0.3:
            cl = min(r.uniform(0.6, 1.0), L - x)
            if tp(x + cl / 2) > 1.0 and r.random() < 0.8:
                bm = ML.bm_box(cl - 0.01, 0.78, 0.16, 0.03)
                ML.bm_cut(bm, (0, 0.39, 0.03), (0, 0.4, 1))
                B.add(cn, bm, 'M_Stone', M @ TRS((x + cl / 2, 0.0, tp(x + cl / 2) + 0.04),
                                                (0, r.uniform(-.04, .04), r.uniform(-.03, .03))))
            x += cl
    # statues on plinths behind the parapet
    statue(B, 8.0, -6.6, r.uniform(-0.2, 0.0) - 0.15, 1.75, 'headless', r, plinth_h=1.3)
    statue(B, -8.2, -6.8, 0.2, 1.75, 'standing', r, plinth_h=1.3)
    # toppled statue at the stage's left edge (screen left = +x)
    statue(B, 15.0, -1.5, 0.35, 1.8, 'toppled', r, plinth_h=0.9)
    # braziers
    brazier(B, 10.9, -1.2, r, 1.0, 1.05)
    brazier(B, -10.9, -1.3, r, 1.0, 1.05)
    brazier(B, 4.4, -3.7, r, 0.9, 1.0)
    brazier(B, -4.4, -3.7, r, 0.9, 1.0)
    gibbet_cage(B, 11.6, -4.7, random.Random(44))
    # dead tree, right side of screen (-x)
    dead_tree(B, -14.2, -2.6, random.Random(31), height=9.0, r0=0.45, lean=(0.25, 0.05), spread=1.0)
    # graveyard around the tree
    for i in range(16):
        while True:
            x = r.uniform(-19.5, -11.2)
            y = r.uniform(-6.5, 3.5)
            if abs(x + 14.2) < 1.6 and abs(y + 2.6) < 1.6:
                continue
            if y > 1.9 and x > -15.2:
                continue
            break
        gravestone(B, x, y, r)
    for i in range(6):
        gravestone(B, r.uniform(11.5, 19.0), r.uniform(-6.5, -3.0), r)
    fence(B, (-19.6, 4.0), (-14.6, 4.4), r, 1.4)
    fence(B, (-19.8, -7.2), (-19.8, 3.6), r, 1.4)
    # side columns
    column_piece(B, 12.8, 1.4, r, 2.6, 0.45)
    column_piece(B, -11.6, 1.6, r, 1.3, 0.42)
    column_piece(B, 17.5, 1.5, r, 0, 0.45, toppled=True)
    column_piece(B, -17.0, -6.0, r, 0, 0.42, toppled=True)
    column_piece(B, 18.6, -5.5, r, 5.5, 0.5)
    # rubble piles: base of the collapsed nave, sides
    for (x, y, rx, ry, h, n, em) in ((-1.5, -8.0, 4.5, 1.6, 1.6, 150, 0.05), (5.5, -7.6, 2.8, 1.3, 1.1, 60, 0.06),
                                     (-7.2, -7.8, 2.6, 1.2, 1.3, 60, 0.0), (12.5, -7.2, 2.4, 1.6, 1.2, 45, 0.0),
                                     (-12.5, -7.5, 2.0, 1.3, 0.9, 22, 0.0), (16.0, 2.2, 2.0, 1.4, 0.7, 22, 0.0),
                                     (-17.5, 0.0, 1.6, 1.2, 0.6, 14, 0.0), (22.0, -6.0, 3.0, 2.0, 1.5, 40, 0.0),
                                     (-22.5, -4.0, 3.0, 2.4, 1.6, 40, 0.0), (0.5, -15.0, 6.0, 3.0, 2.2, 170, 0.04)):
        rubble_pile(B, x, y, rx, ry, h, n, r, ember=em)
    B.light((-1.5, -7.0, 1.6), C(255, 110, 40), 1.6, 5.0)
    B.add_fx('embers', (-1.5, -7.6, 1.3), 1.5)
    B.light((5.6, -6.9, 1.2), C(255, 110, 40), 1.2, 4.0)
    B.add_fx('embers', (5.5, -7.4, 1.0), 1.0)
    # background pyre between the nave wall and the gable
    rubble_pile(B, -9.0, -19.0, 2.4, 2.0, 1.5, 24, r, ember=0.6)
    B.add_fx('fire', (-9.0, -19.0, 1.4), 2.2)
    B.add_fx('embers', (-9.0, -19.0, 3.5), 2.0)
    B.light((-9.0, -18.5, 3.0), C(255, 130, 55), 5.0, 16.0)
    B.preview.append(('flame', Vector((-9.0, -19.0, 1.25)), 2.0))
    # banners on the nave wall (tattered)
    for (x, z, w, h) in ((-9.3, 6.0, 1.15, 3.9), (9.3, 5.6, 1.15, 3.6), (-15.5, 8.6, 1.4, 5.0),
                         (15.5, 8.2, 1.4, 4.8)):
        hanging_banner(B, x, -10.0 + 0.7 + 1.15 + 0.08, z, w, h, random.Random(int(x * 3)))
    # ash drifts at wall bases and corners (+ thin patches in front of the stage, < 0.15 m)
    for (x, y, rx, ry, h) in ((-11.0, -4.2, 2.5, 1.0, 0.35), (11.3, -4.4, 2.2, 1.0, 0.3), (0, -5.6, 5.0, 0.9, 0.22),
                              (-17.0, -8.0, 3.5, 1.5, 0.5), (17.5, -8.2, 3.5, 1.6, 0.5), (-14.0, 4.5, 3.0, 1.6, 0.25),
                              (13.5, 4.8, 3.2, 1.5, 0.22), (-6.0, 5.5, 2.4, 1.3, 0.1), (5.5, 6.5, 2.6, 1.2, 0.1),
                              (0.5, 8.5, 3.0, 1.2, 0.08), (-25, -6, 4, 3, 0.8), (25, -5, 4, 3, 0.8)):
        ash_patch(B, x, y, rx, ry, h, r)
    # flagstone fragments and bones at the sides and the camera side (all < 0.3 m tall there)
    for i in range(14):
        x = r.choice((-1, 1)) * r.uniform(10.6, 17)
        slab_fragment(B, x, r.uniform(-6, 5), r)
    for i in range(6):
        slab_fragment(B, r.uniform(-9, 9), r.uniform(-7.2, -5.6), r)

    def camera_side_avoid(x, y):
        return abs(x) < 10.6 and abs(y) < 3.0

    scatter_small(B, -16, 16, -7.5, 11, 240, r, 0.22, avoid=camera_side_avoid)
    for (x, y, n, s) in ((-12.5, 2.8, 6, 1), (13.2, 3.2, 5, 1), (7.0, 4.2, 3, 1), (-6.5, 5.0, 3, 0),
                         (16.0, -0.5, 6, 2), (-16.5, -5.0, 6, 1), (2.0, -6.2, 4, 1)):
        bones_cluster(B, x, y, r, n, s, 0.6)
    for (xa, xb, yy) in ((6.5, 13.5, 5.6), (-14.0, -7.0, 6.2)):
        L = xb - xa
        M = TRS((xa, yy, 0), (0, 0, 0.06 if xa > 0 else -0.05))
        tp = ML.ruin_profile(L, 0, [(0, 0.12), (L * 0.4, 0.27), (L, 0.2)], r, rough=0.04, seed=int(xa))
        ML.masonry_wall(B, 'Debris', M, L, 0.7, lambda x, _t=tp: min(_t(x), 0.27), [], course=(0.24, 0.26),
                        blen=(0.5, 0.9), rng=r, chip=0.5, bevel=0.025, holes=0.15)
        ash_patch(B, (xa + xb) / 2, yy + 0.6, L * 0.45, 0.9, 0.12, r)
    # broken sword lying in the foreground
    sw = ML.bm_prism([(0, 0), (0.035, 0.1), (0.03, 0.62), (-0.03, 0.62), (-0.035, 0.1)], 0.012)
    B.add('Debris', sw, 'M_Iron', TRS((-3.0, 4.6, 0.02), (math.pi / 2, 0, 1.1)))
    B.add('Debris', ML.bm_box(0.3, 0.04, 0.04, 0.008), 'M_Iron', TRS((-2.75, 4.95, 0.03), (0, 0, 1.1 + math.pi / 2)))


def make_layout(B):
    pitch, yaw = 18.0, 200.0
    ud, bd = ML.sun_vectors(pitch, yaw)
    return {
        "_notes": "Positions in Blender coordinates (metres, Z up); Unity = (-x, z, -y). Colours are sRGB "
                  "(as typed in Unity's inspector). sun.direction_deg = Unity directional-light Euler "
                  "[pitch(X), yaw(Y)]; sun.direction_blender = the light's travel direction in Blender axes. "
                  "Fog is linear (Unity RenderSettings.fogMode = Linear). Point-light intensity is Unity URP "
                  "intensity; range in metres. fx.scale ~1 = one brazier-sized fire.",
        "sun": {"direction_deg": [pitch, yaw], "direction_blender": [round(v, 4) for v in bd],
                "color": [round(c, 3) for c in C(255, 156, 96)], "intensity": 1.8},
        "ambient": {"sky": [round(c, 3) for c in C(72, 80, 100)], "equator": [round(c, 3) for c in C(90, 84, 90)],
                    "ground": [round(c, 3) for c in C(34, 31, 32)]},
        "fog": {"color": [round(c, 3) for c in C(132, 114, 106)], "start": 10.0, "end": 270.0},
        "background": [round(c, 3) for c in C(132, 114, 106)],
        "pointLights": B.lights,
        "fx": B.fx + [{"type": "ash", "pos": [0.0, -1.0, 9.0], "scale": 22.0},
                      {"type": "ash", "pos": [0.0, -18.0, 14.0], "scale": 40.0}],
    }


def preview_extras(B, coll, fog):
    """Not exported: flames for the fires and two fighter-sized mannequins for scale."""
    fmat = ML.emissive_material('PV_Flame', C(255, 150, 60), 18.0, fog)
    fmat2 = ML.emissive_material('PV_FlameCore', C(255, 220, 140), 30.0, fog)
    rng = random.Random(5)
    for kind, pos, s in B.preview:
        for k in range(4):
            prof = [(0.0, 0.0)] + [(0.22 * s * (1 - k * 0.2) * math.sin(math.pi * t ** 0.6) * (1 - t) ** 0.3,
                                    t * 0.9 * s * (1 - k * 0.15)) for t in np.linspace(0.05, 1.0, 10)]
            prof[-1] = (0.0, prof[-1][1])
            bm = ML.bm_lathe([(max(r, 0.0), z) for r, z in prof], 10, False, False)
            ML.bm_noise(bm, 0.04 * s, 6.0, rng.randint(0, 99))
            me = bpy.data.meshes.new('PV_flame')
            bm.to_mesh(me)
            bm.free()
            ob = bpy.data.objects.new('PV_flame', me)
            ob.location = pos + Vector((rng.uniform(-0.12, 0.12) * s, rng.uniform(-0.12, 0.12) * s, 0))
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


def check_clear(B):
    """Validate the playable strip and the camera-side height limits."""
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
    return bad_play, bad_cam


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
    cam_w = ML.add_camera('Cam_Wide', (-10, 27, 12.5), (1, -20, 5), 55, pcoll)
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
