#!/usr/bin/env python3
"""Обход уровня НА СТЕНДЕ — та же арифметика, что у клавиши T в игре.

Нужен, чтобы правки расстановки проверялись до отправки, а не после прогона у
пользователя. Считает то же самое: сколько экземпляров каждого вида попадает в
ближние корзины вокруг наблюдателя и какого они экранного размера.
"""
import sys, math, pathlib
import numpy as np

WORLD_SCALE = 0.16
HEIGHT_SCALE = 48.0
MPU = 10.0
FULL_EXIT, IMP_ENTER, COVER_HIDE = 4.5, 16.0, 6.0
COVER = {6, 7, 8}
NAMES = ["Pine", "Fir", "Deciduous", "Bush", "Flower", "Reed", "GrassTuft", "Moss", "Stone"]
TARGET_H = {0: 2.8, 1: 3.1, 2: 2.5, 3: 0.30, 4: 0.05, 5: 0.25,
            6: 0.05, 7: 0.02, 8: 0.07}
BIOME = {3: "луг", 4: "лес", 5: "кустарник", 6: "скала", 9: "осыпь", 8: "болото"}


def main():
    d = pathlib.Path(sys.argv[1])
    W, H, FOV = 2268.0, 1200.0, 75.0
    px_per_rad = H / (2 * math.tan(math.radians(FOV) / 2))

    R = np.loadtxt(d / "regions.txt")
    rx, rz, rel, rb = R[:, 0], R[:, 1], R[:, 2], R[:, 3].astype(int)
    P = np.loadtxt(d / "plants.txt")
    px, pz, kind, variant, scale = (P[:, 0], P[:, 1], P[:, 2].astype(int),
                                    P[:, 3].astype(int), P[:, 4])
    PR = np.loadtxt(d / "protos.txt")
    proto_h = {(int(r[0]), int(r[1])): (r[2], r[3]) for r in PR}

    mapsize = max(rx.max(), rz.max())
    cx = mapsize * 0.5
    wpx = (px - cx) * WORLD_SCALE
    wpz = (pz - cx) * WORLD_SCALE
    # мировая высота растения — по отметке ближайшего региона (грубо, но одинаково)
    from scipy.spatial import cKDTree
    tree = cKDTree(np.stack([rx, rz], 1))
    _, ri = tree.query(np.stack([px, pz], 1), k=1)
    wpy = np.power(np.maximum(rel[ri], 0.01), 1.15) * HEIGHT_SCALE

    # высота растения в мире
    hworld = np.array([TARGET_H[k] for k in kind]) * scale

    print(f"{'точка':<12}{'деревья':>9}{'кусты':>7}{'трава':>7}{'мох':>6}{'цветы':>7}{'камни':>7}"
          f"{'>10px всего':>13}")
    print("-" * 68)

    for bcode, label in BIOME.items():
        sel = np.where(rb == bcode)[0]
        if len(sel) == 0:
            continue
        # берём медианный по отметке регион биома — не край и не аномалия
        pick = sel[np.argsort(rel[sel])[len(sel) // 2]]
        ex = (rx[pick] - cx) * WORLD_SCALE
        ez = (rz[pick] - cx) * WORLD_SCALE
        ey = math.pow(max(rel[pick], 0.01), 1.15) * HEIGHT_SCALE + 1.7 / MPU

        dist = np.sqrt((wpx - ex) ** 2 + (wpy - ey) ** 2 + (wpz - ez) ** 2)
        near = np.zeros(len(dist), bool)
        cov = np.isin(kind, list(COVER))
        near[~cov & (dist <= IMP_ENTER)] = True
        near[cov & (dist <= COVER_HIDE)] = True

        scr = hworld / np.maximum(dist, 0.01) * px_per_rad
        big = scr > 10

        def cnt(ks, mask=near):
            return int(np.isin(kind, ks)[mask].sum())

        row = [cnt([0, 1, 2]), cnt([3]), cnt([6]), cnt([7]), cnt([4]), cnt([8])]
        big_total = int((big & near).sum())
        print(f"{label:<12}{row[0]:>9}{row[1]:>7}{row[2]:>7}{row[3]:>6}{row[4]:>7}{row[5]:>7}"
              f"{big_total:>13}")

    print("\nПорог: экземпляры в ближних корзинах (деревья до 16 ед., покрытия до "
          f"{COVER_HIDE:.0f}). «>10px» — сколько из них различимы на экране.")


if __name__ == "__main__":
    main()
