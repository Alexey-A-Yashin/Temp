#!/usr/bin/env python3
"""Отрисовать уровень с заданной камеры. См. render_scene_lib для пояснений."""
import sys, math, pathlib, time
import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from render_scene_lib import (WORLD_SCALE, HEIGHT_SCALE, FULL_EXIT, IMP_ENTER,
                              COVER_HIDE, COVER_KINDS, KIND_NAMES, TARGET_H,
                              BIOME_COL, load_regions, load_plants, load_mesh,
                              decimate, build_terrain, Raster)

SOLID_U = SOLID_V = 0.125


BASIS = None


def set_camera(eye, target):
    """Камера смотрит в точку — так же, как орбитальная камера игры, у которой в
    HUD печатаются положение и цель. Собственные yaw/pitch не нужны и только
    вносят расхождение соглашений об осях."""
    global BASIS
    fwd = target - eye
    fwd = fwd / np.linalg.norm(fwd)
    up0 = np.array([0.0, 1.0, 0.0], np.float32)
    right = np.cross(fwd, up0)
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    BASIS = np.stack([right, up, -fwd])      # строки — оси камеры


def project(P, eye, yaw, pitch, W, H, fov):
    V = (P - eye) @ BASIS.T
    zz = -V[:, 2]
    f = (H * 0.5) / math.tan(math.radians(fov) / 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        sx = W * 0.5 + V[:, 0] * f / zz
        sy2 = H * 0.5 - V[:, 1] * f / zz
    return sx, sy2, zz


def main():
    d = pathlib.Path(sys.argv[1])
    out = sys.argv[2]
    # Аргументы: X Z азимут наклон — камера ставится НА ЗЕМЛЮ в этой точке,
    # на высоте глаз игрока, и смотрит по азимуту. Подбирать положение и цель
    # орбитальной камеры из HUD не нужно: судить об уровне надо с той высоты, с
    # которой по нему ходят.
    ex, ez = float(sys.argv[3]), float(sys.argv[5])
    eye_extra = float(sys.argv[4])          # надбавка к высоте глаз
    yaw = math.radians(float(sys.argv[6]))
    pitch = math.radians(float(sys.argv[7]))
    W, H = 1100, 620
    FOV = 62.0
    t0 = time.time()

    atlas = np.asarray(Image.open(sys.argv[8]).convert("RGBA")).astype(np.float32) / 255.0

    rx, rz, rel, rb, riv, wlev = load_regions(d / "regions.txt")
    wx, wz, wy, biome, river, water, elev, mapsize = build_terrain(rx, rz, rel, rb, riv, wlev)
    res = wx.shape[0]

    def ground(x, z):
        i = int(np.clip((x / WORLD_SCALE + mapsize / 2) / mapsize * (res - 1), 0, res - 1))
        j = int(np.clip((z / WORLD_SCALE + mapsize / 2) / mapsize * (res - 1), 0, res - 1))
        return float(wy[i, j])

    ey = ground(ex, ez) + 1.70 / 10.0 + eye_extra
    eye = np.array([ex, ey, ez], np.float32)
    look = np.array([ex + math.sin(yaw) * 30, ey + math.tan(pitch) * 30,
                     ez + math.cos(yaw) * 30], np.float32)
    set_camera(eye, look)
    print(f"камера ({ex:.1f}, {ey:.2f}, {ez:.1f}), земля {ground(ex, ez):.2f}")
    ras = Raster(W, H)

    # ---- рельеф ----
    P = np.stack([wx.ravel(), wy.ravel(), wz.ravel()], 1).astype(np.float32)
    light = np.array([-0.40, 0.75, 0.53], np.float32); light /= np.linalg.norm(light)
    cols = np.zeros((len(P), 3), np.float32)
    bflat = biome.ravel()
    for b, c in BIOME_COL.items():
        cols[bflat == b] = c
    # затенение по уклону сетки
    gy, gx = np.gradient(wy)
    n = np.stack([-gx.ravel(), np.ones(len(P), np.float32) * (wx[1, 0] - wx[0, 0]), -gy.ravel()], 1)
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    lam = np.clip(n @ light, 0, 1)
    cols *= (0.45 + 0.55 * lam)[:, None]
    # вода
    wmask = (river.ravel() == 1)
    P[wmask, 1] = np.maximum(P[wmask, 1], np.power(np.maximum(water.ravel()[wmask], 0.01), 1.15) * HEIGHT_SCALE)
    cols[wmask] = np.array([0.55, 0.72, 0.88], np.float32) * (0.6 + 0.4 * lam[wmask])[:, None]

    idx = np.arange(res * res).reshape(res, res)
    f0 = np.stack([idx[:-1, :-1].ravel(), idx[1:, :-1].ravel(), idx[:-1, 1:].ravel()], 1)
    f1 = np.stack([idx[1:, :-1].ravel(), idx[1:, 1:].ravel(), idx[:-1, 1:].ravel()], 1)
    faces = np.concatenate([f0, f1])
    Vc = (P - eye) @ BASIS.T
    Vc = np.stack([Vc[:, 0], Vc[:, 1], -Vc[:, 2]], 1)     # z вперёд
    fpx = (H * 0.5) / math.tan(math.radians(FOV) / 2)
    ras.tris(None, None, None, cols, faces, vcam=Vc, f=fpx)
    print(f"рельеф: {len(faces)} треугольников, {time.time()-t0:.1f} c")

    # ---- растения ----
    plants = load_plants(d / "plants.txt")
    px, pz, kind, variant, scale, pyaw = (plants[:, 0], plants[:, 1],
        plants[:, 2].astype(int), plants[:, 3].astype(int), plants[:, 4], plants[:, 5])
    cx = mapsize * 0.5
    wpx = (px - cx) * WORLD_SCALE
    wpz = (pz - cx) * WORLD_SCALE
    # высота земли под растением — из той же сетки
    gi = np.clip(((px / mapsize) * (res - 1)).astype(int), 0, res - 1)
    gj = np.clip(((pz / mapsize) * (res - 1)).astype(int), 0, res - 1)
    wpy = wy[gi, gj]

    dist = np.sqrt((wpx - ex) ** 2 + (wpy - ey) ** 2 + (wpz - ez) ** 2)
    bucket = np.full(len(px), 2)
    bucket[dist <= IMP_ENTER] = 1
    bucket[dist <= FULL_EXIT] = 0
    cover = np.isin(kind, list(COVER_KINDS))
    bucket[cover & (dist <= COVER_HIDE)] = 0
    bucket[cover & (dist > COVER_HIDE)] = 3

    stats = {}
    for k in range(9):
        m = kind == k
        stats[KIND_NAMES[k]] = [int((m & (bucket == b)).sum()) for b in range(4)]

    meshes, lods = {}, {}
    for k in range(9):
        for v in range(5):
            f = d / "meshes" / f"{k}_{v}.mesh"
            if not f.exists():
                continue
            M = load_mesh(f)
            meshes[(k, v)] = M
            lods[(k, v)] = decimate(*M, SOLID_U, SOLID_V)

    order = np.argsort(-dist)
    drawn = 0
    for i in order:
        b = bucket[i]
        if b == 3:
            continue
        k, v = kind[i], variant[i]
        if (k, v) not in meshes:
            continue
        localH = max(meshes[(k, v)][0][:, 1].max(), 1e-3)
        s = TARGET_H[k] * scale[i] / localH
        if b == 0:
            Pm, UV, C, F = meshes[(k, v)]
        elif b == 1:
            Pm, UV, C, F = lods[(k, v)]
        else:
            # Импостор: плоская карточка размером с крону, лицом к камере.
            Pm0 = meshes[(k, v)][0]
            hh = Pm0[:, 1].max()
            rr = float(np.sqrt(Pm0[:, 0] ** 2 + Pm0[:, 2] ** 2).max())
            Pm = np.array([[-rr, 0, 0], [rr, 0, 0], [rr, hh, 0], [-rr, hh, 0]], np.float32)
            UV = np.array([[0.02, 0.27], [0.23, 0.27], [0.23, 0.48], [0.02, 0.48]], np.float32)
            C = np.tile(meshes[(k, v)][2].mean(0), (4, 1)).astype(np.float32)
            F = np.array([[0, 1, 2], [0, 2, 3]], np.int32)
            a = math.atan2(ex - wpx[i], ez - wpz[i])
            ca, sa = math.cos(a), math.sin(a)
            R = np.array([[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]], np.float32)
            Pm = Pm @ R.T
        if b != 2:
            a = pyaw[i]
            ca, sa = math.cos(a), math.sin(a)
            R = np.array([[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]], np.float32)
            Pm = Pm @ R.T
        Pw = Pm * s + np.array([wpx[i], wpy[i], wpz[i]], np.float32)
        sx, sy, zz = project(Pw, eye, yaw, pitch, W, H, FOV)
        if (zz <= 0.05).all():
            continue
        if sx.max() < 0 or sx.min() > W or sy.max() < 0 or sy.min() > H:
            continue
        ras.tris(sx, sy, zz, C, F, atlas, UV)
        drawn += 1

    print(f"нарисовано растений: {drawn}, всего {time.time()-t0:.1f} c")
    print(f"{'вид':<11}{'LOD0':>7}{'LOD1':>7}{'имп.':>8}{'скрыто':>8}")
    for k in range(9):
        s = stats[KIND_NAMES[k]]
        print(f"{KIND_NAMES[k]:<11}{s[0]:>7}{s[1]:>7}{s[2]:>8}{s[3]:>8}")

    Image.fromarray((np.clip(ras.img, 0, 1) * 255).astype(np.uint8)).save(out)
    print("записано:", out)


if __name__ == "__main__":
    main()
