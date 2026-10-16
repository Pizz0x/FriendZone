"""Sharper illustrations of the guide Lumi, without the light halo of the old cut-out.

The PNGs of the team's demo are small (about 260 x 420 px) and carry a light
fringe from the original background. This script spreads the colours of the
opaque pixels into the soft edge, tightens the alpha a little, enlarges 4x with
Real-ESRGAN (RealESRGAN_x4plus_anime_6B, BSD-3-Clause) and scales down to the
wanted factor. Not part of the pipeline: run it only to regenerate the assets.

    pip install torch pillow numpy   # CPU build is enough
    curl -LO https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth
    python tools/upscale_mascots.py <png folder> frontend/assets/lumi 3
"""
import sys, glob, os
import numpy as np, torch, torch.nn as nn, torch.nn.functional as F
from PIL import Image, ImageFilter

class RDB(nn.Module):
    def __init__(s, nf=64, gc=32):
        super().__init__()
        s.conv1 = nn.Conv2d(nf, gc, 3, 1, 1); s.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1)
        s.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1); s.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1)
        s.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1); s.lrelu = nn.LeakyReLU(0.2, True)
    def forward(s, x):
        x1 = s.lrelu(s.conv1(x)); x2 = s.lrelu(s.conv2(torch.cat((x, x1), 1)))
        x3 = s.lrelu(s.conv3(torch.cat((x, x1, x2), 1))); x4 = s.lrelu(s.conv4(torch.cat((x, x1, x2, x3), 1)))
        return s.conv5(torch.cat((x, x1, x2, x3, x4), 1)) * 0.2 + x
class RRDB(nn.Module):
    def __init__(s, nf, gc=32):
        super().__init__(); s.rdb1 = RDB(nf, gc); s.rdb2 = RDB(nf, gc); s.rdb3 = RDB(nf, gc)
    def forward(s, x): return s.rdb3(s.rdb2(s.rdb1(x))) * 0.2 + x
class RRDBNet(nn.Module):
    def __init__(s, nb=6, nf=64, gc=32):
        super().__init__()
        s.conv_first = nn.Conv2d(3, nf, 3, 1, 1); s.body = nn.Sequential(*[RRDB(nf, gc) for _ in range(nb)])
        s.conv_body = nn.Conv2d(nf, nf, 3, 1, 1); s.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1); s.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1)
        s.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1); s.conv_last = nn.Conv2d(nf, 3, 3, 1, 1); s.lrelu = nn.LeakyReLU(0.2, True)
    def forward(s, x):
        f = s.conv_first(x); f = f + s.conv_body(s.body(f))
        f = s.lrelu(s.conv_up1(F.interpolate(f, scale_factor=2, mode="nearest")))
        f = s.lrelu(s.conv_up2(F.interpolate(f, scale_factor=2, mode="nearest")))
        return s.conv_last(s.lrelu(s.conv_hr(f)))

net = RRDBNet(); sd = torch.load("RealESRGAN_x4plus_anime_6B.pth", map_location="cpu"); sd = sd.get("params_ema", sd.get("params", sd))
net.load_state_dict(sd, strict=True); net.eval()

def sr(rgb):  # HxWx3 float 0..1 -> 4x
    with torch.no_grad():
        t = torch.from_numpy(rgb.transpose(2, 0, 1)).float()[None]
        return net(t)[0].clamp(0, 1).numpy().transpose(1, 2, 0)

def bleed(rgba, iters=12):
    """Spread the colours of opaque pixels into semi-transparent and transparent ones (removes the light fringe)."""
    rgb = rgba[..., :3].astype(float); a = rgba[..., 3].astype(float) / 255
    known = a >= 0.98
    out = rgb.copy()
    for _ in range(iters):
        acc = np.zeros_like(out); cnt = np.zeros(out.shape[:2])
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == dx == 0: continue
                k = np.roll(np.roll(known, dy, 0), dx, 1); c = np.roll(np.roll(out, dy, 0), dx, 1)
                acc += c * k[..., None]; cnt += k
        grow = (~known) & (cnt > 0)
        out[grow] = acc[grow] / cnt[grow][:, None]
        known = known | grow
    return out

src, dst, scale = sys.argv[1], sys.argv[2], float(sys.argv[3])
os.makedirs(dst, exist_ok=True)
for f in sorted(glob.glob(src + "/*.png")):
    im = np.asarray(Image.open(f).convert("RGBA"))
    pad = 8
    im = np.pad(im, ((pad, pad), (pad, pad), (0, 0)))
    rgb = bleed(im) / 255
    a = im[..., 3].astype(float) / 255
    # tighten the soft rim a little: the old matte lives in the faint outer pixels
    a = np.clip((a - 0.12) / 0.88, 0, 1)
    up = sr(rgb)
    ua = sr(np.repeat(a[..., None], 3, 2)).mean(2)
    ua = np.clip((ua - 0.04) / 0.92, 0, 1)
    h, w = up.shape[:2]
    out = np.dstack([up * 255, ua * 255]).round().astype(np.uint8)
    img = Image.fromarray(out, "RGBA")
    # 4x -> wanted scale with a high-quality filter, then crop the padding
    W, H = round(w / 4 * scale), round(h / 4 * scale)
    img = img.resize((W, H), Image.LANCZOS)
    p = round(pad * scale); img = img.crop((p, p, W - p, H - p))
    name = os.path.basename(f).replace(".png", ".webp")
    img.save(os.path.join(dst, name), "WEBP", quality=88, method=6, alpha_quality=100)
    print(name, img.size, os.path.getsize(os.path.join(dst, name)) // 1024, "KB")
