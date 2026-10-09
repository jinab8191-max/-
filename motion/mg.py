#!/usr/bin/env python3
"""릴스/롱폼용 모션그래픽 오버레이 생성기.

투명 배경 .mov(ProRes 4444) 를 만들어 캡컷 위 트랙에 그대로 올려 쓴다.
투명이 안 보이는 환경이면 --green 으로 초록 배경을 만들고 캡컷 '크로마키'로 뺀다.

필요: python3 + Pillow, ffmpeg
  ~/.pycapcut/bin/pip install pillow

예)
  python3 mg.py hook "월 300 버는 법" --sub "딱 3가지" -o hook.mov
  python3 mg.py keyword "핵심" -o kw.mov
  python3 mg.py counter 1000 --suffix "만원" -o num.mov
  python3 mg.py chapter "자막 넣는 법" --num 2 --size 1920x1080 -o ch2.mov
  python3 mg.py cta "팔로우하고 다음 편 보기" -o cta.mov
  python3 mg.py progress --duration 32 -o bar.mov
  python3 mg.py batch spec.json            # 여러 개 한 번에
  python3 mg.py preview                     # 전부 샘플로 만들어 보기

색·폰트는 ~/릴스스타일/brand.json 이 있으면 거기서 읽는다:
  {"font": "/경로/폰트.ttf", "text": "#FFFFFF", "accent": "#FFD400",
   "accent_text": "#111111", "stroke": "#000000"}
"""
import argparse
import json
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

FPS = 30
BRAND_PATH = os.path.expanduser("~/릴스스타일/brand.json")
DEFAULT_BRAND = {
    "font": None,
    "text": "#FFFFFF",
    "accent": "#FFD400",
    "accent_text": "#111111",
    "stroke": "#000000",
}
FONT_CANDIDATES = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/NanumGothicExtraBold.ttf",
    "/Library/Fonts/NanumSquareEB.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
BOLD_STYLES = ("Heavy", "ExtraBold", "Black", "Bold", "SemiBold")
_font_cache = {}


# ---------- 공통 ----------

def load_brand():
    brand = dict(DEFAULT_BRAND)
    if os.path.exists(BRAND_PATH):
        with open(BRAND_PATH, encoding="utf-8") as f:
            brand.update(json.load(f))
    return brand


def hex_rgba(h, a=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def _boldest_index(path):
    """ttc 묶음 안에서 가장 굵은 글꼴 번호를 이름으로 찾는다."""
    styles = {}
    for i in range(32):
        try:
            styles[ImageFont.truetype(path, 10, index=i).getname()[1]] = i
        except OSError:
            break
    for want in BOLD_STYLES:
        if want in styles:
            return styles[want]
    return 0


def font(brand, size):
    if brand.get("font"):
        return ImageFont.truetype(os.path.expanduser(brand["font"]), size)
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            if path not in _font_cache:
                _font_cache[path] = _boldest_index(path)
            return ImageFont.truetype(path, size, index=_font_cache[path])
    sys.exit("한글 폰트를 찾지 못했어요. brand.json 의 font 에 .ttf 경로를 넣어주세요.")


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def ease_out_cubic(t):
    return 1 - (1 - clamp(t)) ** 3


def ease_out_back(t, s=1.9):
    t = clamp(t) - 1
    return t * t * ((s + 1) * t + s) + 1


def ease_in_cubic(t):
    return clamp(t) ** 3


def text_size(draw, text, f, stroke=0):
    box = draw.textbbox((0, 0), text, font=f, stroke_width=stroke)
    return box[2] - box[0], box[3] - box[1], box[1]


def paste_scaled(canvas, layer, cx, cy, scale, alpha=1.0, angle=0.0):
    """layer 를 (cx, cy) 중심에 scale·투명도·회전을 줘서 합친다."""
    if scale <= 0.01 or alpha <= 0.01:
        return
    w, h = layer.size
    img = layer.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    if angle:
        img = img.rotate(angle, resample=Image.BICUBIC, expand=True)
    if alpha < 1.0:
        a = img.getchannel("A").point(lambda v: int(v * alpha))
        img.putalpha(a)
    canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


def pill(text, f, fill, color, pad_x, pad_y, radius=None, stroke=0, stroke_fill=None):
    """둥근 박스 안에 글자를 넣은 레이어."""
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw, th, top = text_size(tmp, text, f, stroke)
    w, h = tw + pad_x * 2, th + pad_y * 2
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius if radius is not None else h // 2, fill=fill)
    d.text((pad_x, pad_y - top), text, font=f, fill=color, stroke_width=stroke, stroke_fill=stroke_fill)
    return layer


def outlined_text(text, f, color, stroke, stroke_fill, shadow=True):
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw, th, top = text_size(tmp, text, f, stroke)
    off = stroke + 12
    layer = Image.new("RGBA", (tw + off * 2, th + off * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if shadow:
        d.text((off + 6, off - top + 8), text, font=f, fill=(0, 0, 0, 110), stroke_width=stroke, stroke_fill=(0, 0, 0, 110))
    d.text((off, off - top), text, font=f, fill=color, stroke_width=stroke, stroke_fill=stroke_fill)
    return layer


def fit_font(brand, text, max_w, start):
    size = start
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    while size > 20:
        f = font(brand, size)
        if text_size(tmp, text, f, size // 12)[0] <= max_w:
            return f, size
        size -= 4
    return font(brand, size), size


def env(t, dur, t_in=0.25, t_out=0.18):
    """등장(0→1)과 퇴장(1→0) 진행도."""
    return clamp(t / t_in), clamp((dur - t) / t_out)


# ---------- 템플릿 ----------
# 각 함수는 (W, H, brand, opts) 를 받아 frame(t) -> RGBA Image 함수를 돌려준다.

def tpl_hook(W, H, brand, o):
    """첫 1초 화면 글자 훅: 큰 글씨 + 강조색 밑줄 박스, 튀어나오듯 등장."""
    main, _ = fit_font(brand, o["text"], int(W * 0.86), int(W * 0.12))
    stroke = max(4, main.size // 12)
    title = outlined_text(o["text"], main, hex_rgba(brand["text"]), stroke, hex_rgba(brand["stroke"]))
    sub = None
    if o.get("sub"):
        sf, _ = fit_font(brand, o["sub"], int(W * 0.7), int(W * 0.07))
        sub = pill(o["sub"], sf, hex_rgba(brand["accent"]), hex_rgba(brand["accent_text"]),
                   int(sf.size * 0.6), int(sf.size * 0.3))
    cy = H * o.get("y", 0.28)

    def frame(t):
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        a_in, a_out = env(t, o["duration"])
        s = ease_out_back(a_in) * (1 - 0.15 * (1 - a_out))
        paste_scaled(c, title, W / 2, cy, s, a_out)
        if sub is not None:
            b_in = clamp((t - 0.18) / 0.25)
            paste_scaled(c, sub, W / 2, cy + title.height * 0.62 + sub.height / 2,
                         ease_out_back(b_in), min(b_in * 3, 1) * a_out, angle=-3 * (1 - ease_out_cubic(b_in)))
        return c
    return frame


def tpl_keyword(W, H, brand, o):
    """핵심 단어 스티커: 강조색 알약이 살짝 기울어져 튀어나옴."""
    f, _ = fit_font(brand, o["text"], int(W * 0.7), int(W * 0.085))
    layer = pill(o["text"], f, hex_rgba(brand["accent"]), hex_rgba(brand["accent_text"]),
                 int(f.size * 0.55), int(f.size * 0.28))
    cx, cy = W * o.get("x", 0.5), H * o.get("y", 0.62)
    tilt = o.get("angle", -4)

    def frame(t):
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        a_in, a_out = env(t, o["duration"], 0.22, 0.15)
        wobble = math.sin(t * 9) * 1.2 * (1 - clamp(t / 0.8))
        paste_scaled(c, layer, cx, cy, ease_out_back(a_in, 2.4) * (0.85 + 0.15 * a_out), a_out, tilt + wobble)
        return c
    return frame


def tpl_counter(W, H, brand, o):
    """숫자 카운트업: 0 → 목표값, 끝에 한 번 통 튐."""
    target = float(o["text"])
    decimals = int(o.get("decimals", 0))
    suffix, prefix = o.get("suffix", ""), o.get("prefix", "")
    sample = f"{prefix}{target:,.{decimals}f}{suffix}"
    f, _ = fit_font(brand, sample, int(W * 0.86), int(W * 0.16))
    stroke = max(4, f.size // 12)
    cy = H * o.get("y", 0.4)
    count_t = min(1.0, o["duration"] * 0.55)

    def frame(t):
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        a_in, a_out = env(t, o["duration"], 0.15, 0.18)
        p = ease_out_cubic(t / count_t)
        val = target * p
        txt = f"{prefix}{val:,.{decimals}f}{suffix}"
        color = hex_rgba(brand["accent"]) if p >= 1 else hex_rgba(brand["text"])
        layer = outlined_text(txt, f, color, stroke, hex_rgba(brand["stroke"]))
        pop = 1 + 0.12 * math.sin(clamp((t - count_t) / 0.2) * math.pi)
        paste_scaled(c, layer, W / 2, cy, ease_out_back(a_in) * pop, a_out)
        return c
    return frame


def tpl_chapter(W, H, brand, o):
    """롱폼 챕터 카드: 왼쪽 아래에서 번호 + 제목 바가 미끄러져 들어옴."""
    num = f"{int(o.get('num', 1)):02d}"
    nf = font(brand, int(H * 0.075))
    tf, _ = fit_font(brand, o["text"], int(W * 0.5), int(H * 0.06))
    num_l = pill(num, nf, hex_rgba(brand["accent"]), hex_rgba(brand["accent_text"]),
                 int(nf.size * 0.4), int(nf.size * 0.2), radius=10)
    title_l = pill(o["text"], tf, (17, 17, 17, 230), hex_rgba(brand["text"]),
                   int(tf.size * 0.6), int((num_l.height - tf.size) / 2 + tf.size * 0.05), radius=10)
    x0, y0 = int(W * 0.06), int(H * o.get("y", 0.78))

    def frame(t):
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        a_in, a_out = env(t, o["duration"], 0.35, 0.3)
        slide = (1 - ease_out_cubic(a_in)) + ease_in_cubic(1 - a_out)
        nx = x0 - slide * (W * 0.4)
        c.alpha_composite(num_l, (int(nx), y0))
        b_in = clamp((t - 0.12) / 0.35)
        tx = nx + num_l.width + 12 - (1 - ease_out_cubic(b_in)) * 60
        if b_in > 0:
            tl = title_l.copy()
            tl.putalpha(tl.getchannel("A").point(lambda v: int(v * b_in * a_out)))
            c.alpha_composite(tl, (int(tx), y0 + (num_l.height - title_l.height) // 2))
        return c
    return frame


def tpl_cta(W, H, brand, o):
    """마지막 행동 유도: 아래쪽 알약 버튼이 통통 튀고 화살표가 깜빡임."""
    f, _ = fit_font(brand, o["text"], int(W * 0.8), int(W * 0.06))
    btn = pill(o["text"], f, hex_rgba(brand["accent"]), hex_rgba(brand["accent_text"]),
               int(f.size * 0.8), int(f.size * 0.45))
    af = font(brand, int(f.size * 1.3))
    arrow = outlined_text("▼", af, hex_rgba(brand["text"]), 3, hex_rgba(brand["stroke"]), shadow=False)
    cy = H * o.get("y", 0.8)

    def frame(t):
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        a_in, a_out = env(t, o["duration"], 0.3, 0.2)
        bounce = abs(math.sin(t * 4.5)) * 18 * clamp((t - 0.3) / 0.2)
        paste_scaled(c, btn, W / 2, cy - bounce, ease_out_back(a_in), a_out)
        blink = 0.5 + 0.5 * math.sin(t * 8)
        paste_scaled(c, arrow, W / 2, cy + btn.height * 0.95 + bounce * 0.5, 0.8, blink * a_out * clamp(t / 0.4))
        return c
    return frame


def tpl_progress(W, H, brand, o):
    """영상 길이만큼 위쪽에 차오르는 진행 바 (끝까지 보게 만드는 장치)."""
    bar_h = max(8, int(H * 0.006))
    y = int(H * o.get("y", 0.0)) or 0
    color = hex_rgba(brand["accent"])

    def frame(t):
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(c)
        d.rectangle((0, y, W, y + bar_h), fill=(255, 255, 255, 70))
        d.rectangle((0, y, int(W * clamp(t / o["duration"])), y + bar_h), fill=color)
        return c
    return frame


def tpl_highlight(W, H, brand, o):
    """화면 속 특정 위치를 동그라미로 그려서 강조 (자료 화면 위에)."""
    cx, cy = W * o.get("x", 0.5), H * o.get("y", 0.3)
    rx, ry = W * o.get("rx", 0.22), H * o.get("ry", 0.05)
    width = max(8, int(W * 0.01))
    color = hex_rgba(brand["accent"])

    def frame(t):
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        _, a_out = env(t, o["duration"], 0.4, 0.2)
        p = ease_out_cubic(t / 0.45)
        if p > 0:
            d = ImageDraw.Draw(c)
            d.arc((cx - rx, cy - ry, cx + rx, cy + ry), start=-100, end=-100 + 370 * p,
                  fill=color[:3] + (int(255 * a_out),), width=width)
        return c
    return frame


TEMPLATES = {
    "hook": (tpl_hook, 1.8),
    "keyword": (tpl_keyword, 1.2),
    "counter": (tpl_counter, 2.0),
    "chapter": (tpl_chapter, 3.0),
    "cta": (tpl_cta, 3.0),
    "progress": (tpl_progress, 30.0),
    "highlight": (tpl_highlight, 1.5),
}


# ---------- 렌더 ----------

def render(kind, opts, out, size="1080x1920", green=False, brand=None):
    brand = brand or load_brand()
    W, H = (int(v) for v in size.lower().split("x"))
    tpl, default_dur = TEMPLATES[kind]
    opts = dict(opts)
    opts.setdefault("duration", default_dur)
    opts.setdefault("text", "")
    frame = tpl(W, H, brand, opts)
    n = max(1, int(round(opts["duration"] * FPS)))

    if out.lower().endswith(".png"):
        frame(opts.get("at", min(0.6, opts["duration"] / 2))).save(out)
        return out

    if green:
        args = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16"]
    else:
        args = ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-vendor", "apl0"]
    proc = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", *args, out],
        stdin=subprocess.PIPE)
    bg = Image.new("RGBA", (W, H), (0, 255, 0, 255)) if green else None
    for i in range(n):
        img = frame(i / FPS)
        if bg is not None:
            img = Image.alpha_composite(bg, img)
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit(f"ffmpeg 렌더 실패: {out}")
    return out


def main():
    p = argparse.ArgumentParser(description="모션그래픽 오버레이 생성기")
    p.add_argument("kind", choices=[*TEMPLATES, "batch", "preview"])
    p.add_argument("text", nargs="?", default="", help="표시할 글자 (counter 는 목표 숫자, batch 는 spec.json 경로)")
    p.add_argument("-o", "--out", help="출력 파일 (.mov, 미리보기는 .png)")
    p.add_argument("--sub", help="hook 아래 작은 글자")
    p.add_argument("--num", type=int, help="chapter 번호")
    p.add_argument("--suffix", default="", help="counter 뒤 단위 (예: 만원, %%)")
    p.add_argument("--prefix", default="", help="counter 앞 글자")
    p.add_argument("--decimals", type=int, default=0)
    p.add_argument("--duration", type=float)
    p.add_argument("--x", type=float, help="가로 위치 0~1")
    p.add_argument("--y", type=float, help="세로 위치 0~1")
    p.add_argument("--size", default="1080x1920", help="1080x1920(숏폼) 또는 1920x1080(롱폼)")
    p.add_argument("--green", action="store_true", help="투명 대신 초록 배경(캡컷 크로마키용)")
    a = p.parse_args()

    if a.kind == "batch":
        with open(a.text, encoding="utf-8") as f:
            spec = json.load(f)
        size = spec.get("size", a.size)
        green = spec.get("green", a.green)
        out_dir = os.path.expanduser(spec.get("out_dir", "."))
        os.makedirs(out_dir, exist_ok=True)
        for i, item in enumerate(spec["items"], 1):
            item = dict(item)
            kind = item.pop("type")
            out = os.path.join(out_dir, item.pop("out", f"{i:02d}_{kind}.mov"))
            render(kind, item, out, size, green)
            print(out)
        return

    if a.kind == "preview":
        out_dir = a.out or "mg_preview"
        os.makedirs(out_dir, exist_ok=True)
        samples = [
            ("hook", {"text": "월 300 버는 법", "sub": "딱 3가지만 하세요"}, "1080x1920"),
            ("keyword", {"text": "핵심은 이거"}, "1080x1920"),
            ("counter", {"text": "1000", "suffix": "만원"}, "1080x1920"),
            ("cta", {"text": "팔로우하고 다음 편 보기"}, "1080x1920"),
            ("progress", {"duration": 4, "at": 2.5}, "1080x1920"),
            ("highlight", {"at": 1.0}, "1080x1920"),
            ("chapter", {"text": "자막 넣는 법", "num": 2, "at": 1.2}, "1920x1080"),
        ]
        for kind, opts, size in samples:
            for ext in ("png", "mov"):
                print(render(kind, opts, os.path.join(out_dir, f"{kind}.{ext}"), size, a.green))
        return

    opts = {k: v for k, v in {
        "text": a.text, "sub": a.sub, "num": a.num, "suffix": a.suffix, "prefix": a.prefix,
        "decimals": a.decimals, "duration": a.duration, "x": a.x, "y": a.y,
    }.items() if v not in (None, "")}
    out = a.out or f"{a.kind}.mov"
    print(render(a.kind, opts, out, a.size, a.green))


if __name__ == "__main__":
    main()
