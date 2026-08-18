#!/usr/bin/env python3
"""Отрисовка УРОВНЯ ЦЕЛИКОМ без Godot.

ЗАЧЕМ. Прежние проверки мерили отдельное растение и число экземпляров в таблице.
Ни одна из них не могла показать того, что видно на кадре: что половина
растительности скрыта по дистанции, что деревья собрались в валы вдоль реки, что
породный состав перевёрнут. Судить об уровне надо по сцене с камеры, а не по
таблице, и вот она.

Что воспроизводится:
  - рельеф: сетка высот по обратно-взвешенному расстоянию до регионов, тот же
    показатель 1.15 и HeightScale, что в LevelView3D;
  - вода: регионы русла заливаются на уровне воды;
  - окраска: приблизительная палитра биомов (сравнивать имеет смысл СОСТАВ И
    ПЛОТНОСТЬ растительности, а не оттенок);
  - растения: реальные меши из каталога, реальные положение, масштаб и поворот;
  - ПОЛОСЫ LOD И СКРЫТИЯ — те же, что в игре: полный меш, прореженный, карточка,
    скрытие покрытий. Именно они и определяют, что попадёт в кадр.

Чего НЕТ: теней, шейдера рельефа с наземной детализацией, настоящего атласа
импосторов (дальнее дерево рисуется плоской карточкой размером с крону).
"""
import sys, math, pathlib
import numpy as np
from PIL import Image

WORLD_SCALE = 0.16
HEIGHT_SCALE = 48.0
METRES_PER_UNIT = 10.0

# Полосы LOD из LevelView3D (V100).
FULL_EXIT = 4.5
IMP_ENTER = 16.0
COVER_HIDE = 14.0

COVER_KINDS = {6, 7, 8}          # GrassTuft, Moss, Stone
KIND_NAMES = ["Pine", "Fir", "Deciduous", "Bush", "Flower", "Reed",
              "GrassTuft", "Moss", "Stone"]

# Целевые высоты в мировых единицах (LevelView3D).
TARGET_H = {0: 28/METRES_PER_UNIT, 1: 31/METRES_PER_UNIT, 2: 25/METRES_PER_UNIT,
            3: 3.0/METRES_PER_UNIT, 4: 0.5/METRES_PER_UNIT, 5: 2.5/METRES_PER_UNIT,
            6: 0.5/METRES_PER_UNIT, 7: 0.2/METRES_PER_UNIT, 8: 0.7/METRES_PER_UNIT}

BIOME_COL = {
    0: (0.35, 0.52, 0.68), 1: (0.42, 0.60, 0.75), 2: (0.80, 0.76, 0.60),
    3: (0.47, 0.68, 0.32), 4: (0.30, 0.50, 0.26), 5: (0.52, 0.60, 0.34),
    6: (0.58, 0.56, 0.54), 7: (0.92, 0.93, 0.95), 8: (0.40, 0.55, 0.40),
    9: (0.62, 0.60, 0.56),
}


def load_regions(path):
    a = np.loadtxt(path)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3].astype(int), a[:, 4].astype(int), a[:, 5]


def load_plants(path):
    a = np.loadtxt(path)
    return a


def load_mesh(path):
    P, UV, C, F = [], [], [], []
    for line in pathlib.Path(path).read_text().splitlines():
        if line[0] == "v":
            p = line.split()
            P.append((float(p[1]), float(p[2]), float(p[3])))
            UV.append((float(p[4]), float(p[5])))
            C.append((float(p[6]), float(p[7]), float(p[8])))
        else:
            p = line.split()
            F.append((int(p[1]), int(p[2]), int(p[3])))
    return (np.array(P, np.float32), np.array(UV, np.float32),
            np.array(C, np.float32), np.array(F, np.int32))


def decimate(P, UV, C, F, solid_u, solid_v):
    """Прореживание как в LevelView3D.BuildLodMesh: листва и древесина
    разбираются раздельно, каждая со своим шагом, площадь компенсируется."""
    q = len(F) // 2
    if q == 0:
        return P, UV, C, F
    quads = F.reshape(-1, 6)[:, :1].ravel() if False else None
    idx = F.reshape(-1)
    quad_first = idx[::6]
    is_leaf = (np.abs(UV[quad_first, 0] - solid_u) > 1e-4) | (np.abs(UV[quad_first, 1] - solid_v) > 1e-4)
    leaf_q, wood_q = int(is_leaf.sum()), int((~is_leaf).sum())
    t_leaf = max(1, min(120, leaf_q // 5))
    t_wood = max(1, min(60, wood_q // 5))
    s_leaf = min(max(leaf_q // t_leaf, 1), 9)
    s_wood = min(max(wood_q // t_wood, 1), 4)
    keep = np.zeros(q, bool)
    ls = ws = 0
    for i in range(q):
        if is_leaf[i]:
            if ls % s_leaf == 0:
                keep[i] = True
            ls += 1
        else:
            if ws % s_wood == 0:
                keep[i] = True
            ws += 1
    tri = F.reshape(-1, 3)
    mask = np.repeat(keep, 2)
    return P, UV, C, tri[mask]


def build_terrain(rx, rz, rel, rb, riv, wlev, res=170):
    """Сетка высот по обратно-взвешенному расстоянию до ближайших регионов."""
    mx = max(rx.max(), rz.max())
    gx = np.linspace(0, mx, res)
    X, Z = np.meshgrid(gx, gx, indexing="ij")
    pts = np.stack([rx, rz], 1)

    from scipy.spatial import cKDTree
    tree = cKDTree(pts)
    q = np.stack([X.ravel(), Z.ravel()], 1)
    d, i = tree.query(q, k=6)
    w = 1.0 / np.maximum(d, 1e-3) ** 2
    w /= w.sum(1, keepdims=True)
    elev = (rel[i] * w).sum(1).reshape(res, res)
    # Биом — по ближайшему региону, без сглаживания: границы должны быть видны.
    biome = rb[i[:, 0]].reshape(res, res)
    river = riv[i[:, 0]].reshape(res, res)
    water = (wlev[i] * w).sum(1).reshape(res, res)

    cx = mx * 0.5
    wx = (X - cx) * WORLD_SCALE
    wz = (Z - cx) * WORLD_SCALE
    wy = np.power(np.maximum(elev, 0.01), 1.15) * HEIGHT_SCALE
    return wx, wz, wy, biome, river, water, elev, mx


class Raster:
    def __init__(self, W, H, bg=(0.62, 0.72, 0.86)):
        self.W, self.H = W, H
        self.img = np.zeros((H, W, 3), np.float32) + np.array(bg, np.float32)
        self.z = np.full((H, W), 1e18, np.float32)

    def tris(self, sx, sy, zz, cols, faces, atlas=None, uvs=None,
             vcam=None, f=None):
        """Растеризация пачки треугольников.

        Если передан vcam (координаты в пространстве камеры) и фокусное f, то
        треугольник СНАЧАЛА отсекается по ближней плоскости и только потом
        проецируется. Без этого крупная ячейка рельефа, одна вершина которой
        оказалась за камерой, либо выбрасывалась целиком (дыра под ногами), либо
        проецировалась в бесконечность и заливала кадр.
        """
        W, H = self.W, self.H
        NEAR = 0.05
        ah = aw = 0
        if atlas is not None:
            ah, aw = atlas.shape[0], atlas.shape[1]

        def emit(pts):
            """pts: список (x_cam, y_cam, z_cam, color, uv) уже за ближней плоскостью."""
            for t in range(1, len(pts) - 1):
                tri = (pts[0], pts[t], pts[t + 1])
                X = [W * 0.5 + q[0] * f / q[2] for q in tri]
                Y = [H * 0.5 - q[1] * f / q[2] for q in tri]
                Z = [q[2] for q in tri]
                CC = [q[3] for q in tri]
                UU = [q[4] for q in tri]
                self._raster(X, Y, Z, CC, UU, atlas, aw, ah)

        def clip(pts):
            out = []
            n = len(pts)
            for i in range(n):
                a, b = pts[i], pts[(i + 1) % n]
                za, zb = a[2], b[2]
                ina, inb = za >= NEAR, zb >= NEAR
                if ina:
                    out.append(a)
                if ina != inb:
                    tt = (NEAR - za) / (zb - za)
                    out.append(tuple(
                        a[k] + (b[k] - a[k]) * tt if k < 3 else a[k] + (b[k] - a[k]) * tt
                        for k in range(3)) +
                        (a[3] + (b[3] - a[3]) * tt, a[4] + (b[4] - a[4]) * tt))
            return out

        if vcam is not None:
            uv = uvs if uvs is not None else np.zeros((len(vcam), 2), np.float32)
            for face in faces:
                i0, i1, i2 = face
                P = [(float(vcam[i, 0]), float(vcam[i, 1]), float(vcam[i, 2]),
                      cols[i], uv[i]) for i in (i0, i1, i2)]
                if all(q[2] < NEAR for q in P):
                    continue
                if any(q[2] < NEAR for q in P):
                    P = clip(P)
                    if len(P) < 3:
                        continue
                emit(P)
            return

        for face in faces:
            i0, i1, i2 = face
            if zz[i0] <= NEAR or zz[i1] <= NEAR or zz[i2] <= NEAR:
                continue
            self._raster([sx[i0], sx[i1], sx[i2]], [sy[i0], sy[i1], sy[i2]],
                         [zz[i0], zz[i1], zz[i2]],
                         [cols[i0], cols[i1], cols[i2]],
                         [uvs[i0], uvs[i1], uvs[i2]] if uvs is not None else None,
                         atlas, aw, ah)

    def _raster(self, X, Y, Z, C, UV, atlas, aw, ah):
        W, H = self.W, self.H
        x0, x1, x2 = X
        y0, y1, y2 = Y
        minx = int(max(0, math.floor(min(x0, x1, x2))))
        maxx = int(min(W - 1, math.ceil(max(x0, x1, x2))))
        miny = int(max(0, math.floor(min(y0, y1, y2))))
        maxy = int(min(H - 1, math.ceil(max(y0, y1, y2))))
        if minx > maxx or miny > maxy:
            return
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            return
        ys, xs = np.mgrid[miny:maxy + 1, minx:maxx + 1]
        px, py = xs + 0.5, ys + 0.5
        w0 = ((x1 - px) * (y2 - py) - (x2 - px) * (y1 - py)) / area
        w1 = ((x2 - px) * (y0 - py) - (x0 - px) * (y2 - py)) / area
        w2 = 1.0 - w0 - w1
        m = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not m.any():
            return
        zi = w0 * Z[0] + w1 * Z[1] + w2 * Z[2]
        sub = self.z[miny:maxy + 1, minx:maxx + 1]
        m &= zi < sub
        if not m.any():
            return
        if atlas is not None and UV is not None:
            u = w0 * UV[0][0] + w1 * UV[1][0] + w2 * UV[2][0]
            v = w0 * UV[0][1] + w1 * UV[1][1] + w2 * UV[2][1]
            ax = np.clip((u * aw).astype(np.int32), 0, aw - 1)
            ay = np.clip((v * ah).astype(np.int32), 0, ah - 1)
            tex = atlas[ay, ax]
            m &= tex[..., 3] >= 0.5
            if not m.any():
                return
            col = (w0[..., None] * C[0] + w1[..., None] * C[1] + w2[..., None] * C[2]) * tex[..., :3]
        else:
            col = w0[..., None] * C[0] + w1[..., None] * C[1] + w2[..., None] * C[2]
        self.img[miny:maxy + 1, minx:maxx + 1][m] = col[m]
        sub[m] = zi[m]
