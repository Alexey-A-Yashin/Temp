#!/usr/bin/env python3
"""Взгляд ИГРОКА, а не карта.

Пускает лучи из точки на высоте глаз и марширует по высотному полю, собранному
из пяти колец: в каждой точке берётся самое мелкое кольцо, которое её накрывает.
Нужен ровно для одного вопроса — заметит ли игрок разницу со своего места.
"""
import struct
import sys

import numpy as np
from PIL import Image

EYE_M = 1.7
MPU = 10.0                      # метров в мировой единице


def load(tag):
    """Пять колец: (шаг в мировых, полуширина, сетка высот)."""
    rings = []
    for r in range(5):
        b = open(f"/home/claude/work/r{r}_{tag}.bin", "rb").read()
        side, = struct.unpack_from("<i", b, 0)
        step, = struct.unpack_from("<f", b, 4)
        h = np.frombuffer(b, "<f4", side * side, 8).reshape(side, side)
        rings.append((step, (side - 1) * step * 0.5, h))
    return rings


def height(rings, x, z):
    """Высота в мировых точках; вне области — уровень внешнего кольца."""
    out = np.zeros_like(x)
    filled = np.zeros(x.shape, bool)
    for step, half, h in rings:                       # от мелкого к грубому
        n = h.shape[0] - 1
        inside = (np.abs(x) < half) & (np.abs(z) < half) & ~filled
        if not inside.any():
            continue
        gx = np.clip((x[inside] + half) / step, 0, n - 1e-4)
        gz = np.clip((z[inside] + half) / step, 0, n - 1e-4)
        i0 = gx.astype(int); j0 = gz.astype(int)
        tx = gx - i0; tz = gz - j0
        a = h[j0, i0]; b = h[j0, i0 + 1]
        c = h[j0 + 1, i0]; d = h[j0 + 1, i0 + 1]
        out[inside] = (a * (1 - tx) + b * tx) * (1 - tz) + (c * (1 - tx) + d * tx) * tz
        filled |= inside
    return out


def render(rings, eye_xz, yaw_deg, pitch_deg=-2.0, w=560, h=315, fov=65.0, up_m=0.0):
    ex, ez = eye_xz
    ground = height(rings, np.array([ex]), np.array([ez]))[0]
    ey = ground + (EYE_M + up_m) / MPU

    yaw = np.radians(yaw_deg); pitch = np.radians(pitch_deg)
    aspect = w / h
    px = (np.arange(w) + 0.5) / w * 2 - 1
    py = 1 - (np.arange(h) + 0.5) / h * 2
    tanh_ = np.tan(np.radians(fov) / 2)
    PX, PY = np.meshgrid(px * tanh_ * aspect, py * tanh_)
    dx = np.sin(yaw) + 0 * PX
    dz = np.cos(yaw) + 0 * PX
    # базис камеры
    rx, rz = np.cos(yaw), -np.sin(yaw)
    dirx = rx * PX + dx * 1.0
    dirz = rz * PX + dz * 1.0
    diry = PY + np.tan(pitch)
    ln = np.sqrt(dirx**2 + diry**2 + dirz**2)
    dirx /= ln; diry /= ln; dirz /= ln

    t = np.full(PX.shape, 0.5)
    hit = np.zeros(PX.shape, bool)
    hx = np.zeros(PX.shape); hz = np.zeros(PX.shape); ht = np.zeros(PX.shape)
    far = 2880.0                                   # полуширина внешнего кольца
    for _ in range(600):
        live = ~hit & (t < far)
        if not live.any():
            break
        x = ex + dirx * t; z = ez + dirz * t; y = ey + diry * t
        g = height(rings, x, z)
        below = live & (y <= g)
        hit |= below
        hx[below] = x[below]; hz[below] = z[below]; ht[below] = t[below]
        # шаг растёт с расстоянием: вдали подробность всё равно не видна
        t = np.where(live & ~below, t + np.maximum(0.35, t * 0.012), t)

    # затенение по нормали
    eps = 0.6
    n_dx = (height(rings, hx + eps, hz) - height(rings, hx - eps, hz)) / (2 * eps)
    n_dz = (height(rings, hx, hz + eps) - height(rings, hx, hz - eps)) / (2 * eps)
    nx, ny, nz = -n_dx, np.ones_like(n_dx), -n_dz
    nl = np.sqrt(nx**2 + ny**2 + nz**2); nx /= nl; ny /= nl; nz /= nl
    L = np.array([0.42, 0.62, 0.66]); L /= np.linalg.norm(L)
    lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)

    hgt = height(rings, hx, hz) * MPU
    lo, hi = np.percentile(hgt[hit], 2), np.percentile(hgt[hit], 98)
    v = np.clip((hgt - lo) / max(hi - lo, 1), 0, 1)
    col = np.dstack([0.26 + 0.62 * v, 0.40 + 0.48 * v, 0.30 + 0.52 * v])
    img = col * (0.28 + 0.85 * lam)[..., None]
    # воздушная дымка с расстоянием
    fog = np.clip(ht / 1400.0, 0, 1)[..., None]
    sky = np.array([0.72, 0.80, 0.88])
    img = img * (1 - fog) + sky * fog
    img[~hit] = sky
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))


if __name__ == "__main__":
    yaw = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    up = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    pitch = -2.0 if up < 100 else -14.0
    tiles = []
    for tag, name in (("cur", "как сейчас"), ("new", "с эрозией")):
        rings = load(tag)
        tiles.append((name, render(rings, (0.0, 0.0), yaw, pitch_deg=pitch, up_m=up)))
    W, H = tiles[0][1].size
    out = Image.new("RGB", (W, H * 2 + 6), (18, 18, 18))
    for i, (_, im) in enumerate(tiles):
        out.paste(im, (0, i * (H + 6)))
    out.save(f"/home/claude/work/eye_{int(yaw)}_{int(up)}.png")
    print(f"eye_{int(yaw)}_{int(up)}.png — сверху «как сейчас», снизу «с эрозией»")
