#!/usr/bin/env python3
"""캡컷 초안을 '수정 가능한' 형태로 만드는 도우미.

편집팀 스킬이 초안을 만들 때 이 파일의 함수만 쓴다. 지키는 원칙 세 가지:
1. 영상은 원본 파일을 그대로 참조하고 쓸 구간만 source_timerange 로 지정한다.
   → 캡컷에서 클립 앞뒤를 끌어서 늘릴 수 있다. (ffmpeg 로 잘라 만든 새 파일을 쓰면 못 늘린다)
2. 영상 소리는 지우지 않는다(volume=1.0). 별도 오디오를 깔더라도 원본 소리는 남긴다.
3. 글자가 들어가는 그래픽(자막·훅·키워드·숫자·챕터·행동 유도)은 이미지가 아니라
   캡컷 텍스트로 넣는다 → 캡컷에서 더블클릭해 글자·색·폰트를 바로 고칠 수 있다.
   (글자 없는 그래픽 — 동그라미 강조, 진행 바 — 만 mg.py 의 .mov 를 쓴다)

필요: ~/.pycapcut 의 pycapcut.  실행: ~/.pycapcut/bin/python
색은 ~/릴스스타일/brand.json 을 따른다 (mg.py 와 같은 파일).

예)
  from capcut_build import Draft
  d = Draft("릴스_러프컷", vertical=True)
  d.add_cuts("~/Desktop/촬영본/촬영본.mp4", [(1.2, 4.8), (6.0, 11.5)], zoom_every_other=1.12)
  d.subtitle("이거 모르면 손해", 0.0, 1.8)
  d.hook("월 300 버는 법", 0.0, 1.6, sub="딱 3가지")
  d.keyword("반전", 3.1, 1.0)
  d.counter(87, 5.0, 1.5, suffix="%")
  d.cta("팔로우하고 다음 편 보기", 9.0, 3.0)
  d.save()

자체 점검: ~/.pycapcut/bin/python capcut_build.py --selftest <영상파일> [초안폴더]
"""
import json
import os
import subprocess
import sys

import pycapcut as cc
from pycapcut import (ClipSettings, TextBackground, TextBorder, TextIntro, TextLoopAnim,
                      TextOutro, TextSegment, TextShadow, TextStyle, TrackType, VideoMaterial,
                      VideoSegment, trange)

DRAFT_ROOT = os.path.expanduser("~/Movies/CapCut/User Data/Projects/com.lveditor.draft")
BRAND_PATH = os.path.expanduser("~/릴스스타일/brand.json")
BRAND = {"text": "#FFFFFF", "accent": "#FFD400", "accent_text": "#111111", "stroke": "#000000"}


def _brand():
    b = dict(BRAND)
    if os.path.exists(BRAND_PATH):
        with open(BRAND_PATH, encoding="utf-8") as f:
            b.update({k: v for k, v in json.load(f).items() if k in BRAND})
    return b


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _y(frac):
    """화면 위에서부터의 비율(0=맨 위, 1=맨 아래) → 캡컷 세로 위치."""
    return 1 - 2 * frac


def _probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return float(out.strip())


class Draft:
    def __init__(self, name, vertical=True, root=DRAFT_ROOT, replace=True):
        w, h = (1080, 1920) if vertical else (1920, 1080)
        self.vertical = vertical
        self.brand = _brand()
        self.folder = cc.DraftFolder(root)
        self.script = self.folder.create_draft(name, w, h, allow_replace=replace)
        self.tracks = set()
        self.cursor = 0.0  # 메인 영상 트랙이 끝나는 시간(초)

    # ---------- 트랙 ----------
    def _track(self, kind, name):
        if name not in self.tracks:
            self.script.add_track(kind, name)
            self.tracks.add(name)
        return name

    # ---------- 영상 ----------
    def add_cuts(self, path, keep, track="영상", volume=1.0, zoom_every_other=None):
        """원본 영상에서 keep=[(시작초, 끝초), ...] 구간만 순서대로 이어 붙인다.

        원본 파일을 그대로 참조하므로 캡컷에서 각 클립의 앞뒤를 늘릴 수 있고, 소리도 그대로 남는다.
        zoom_every_other=1.12 를 주면 짝수 번째 컷을 112% 로 키워 점프컷 줌을 만든다.
        반환: 각 컷이 타임라인에서 시작하는 시간 목록(초).
        """
        path = os.path.expanduser(path)
        material = VideoMaterial(path)
        self._track(TrackType.video, track)
        starts = []
        for i, (s, e) in enumerate(keep):
            dur = e - s
            settings = None
            if zoom_every_other and i % 2 == 1:
                settings = ClipSettings(scale_x=zoom_every_other, scale_y=zoom_every_other)
            seg = VideoSegment(material, trange(f"{self.cursor}s", f"{dur}s"),
                               source_timerange=trange(f"{s}s", f"{dur}s"),
                               volume=volume, clip_settings=settings)
            self.script.add_segment(seg, track)
            starts.append(self.cursor)
            self.cursor += dur
        return starts

    def add_overlay_video(self, path, start, duration=None, track="모션그래픽", y=None, scale=1.0):
        """글자 없는 그래픽(.mov)·자료 화면을 위 트랙에 올린다. 소리는 끈다."""
        path = os.path.expanduser(path)
        duration = duration or _probe_duration(path)
        self._track(TrackType.video, track)
        settings = ClipSettings(scale_x=scale, scale_y=scale,
                                transform_y=_y(y) if y is not None else 0.0)
        self.script.add_segment(VideoSegment(VideoMaterial(path), trange(f"{start}s", f"{duration}s"),
                                             volume=0.0, clip_settings=settings), track)

    # ---------- 텍스트 (모두 캡컷에서 바로 수정 가능) ----------
    def _text(self, text, start, dur, track, *, size, color, y, x=0.0, bold=True, border=True,
              bg=None, intro=None, outro=None, loop=None, rotation=0.0, shadow=True):
        self._track(TrackType.text, track)
        seg = TextSegment(
            text, trange(f"{start}s", f"{dur}s"),
            style=TextStyle(size=size, bold=bold, color=_rgb(color), align=1,
                            auto_wrapping=True, max_line_width=0.86),
            border=TextBorder(color=_rgb(self.brand["stroke"]), width=40.0) if border else None,
            background=TextBackground(color=bg, style=1, round_radius=0.4, height=0.2, width=0.2) if bg else None,
            shadow=TextShadow(alpha=0.45, distance=4.0) if shadow else None,
            clip_settings=ClipSettings(transform_x=x, transform_y=_y(y), rotation=rotation))
        if intro:
            seg.add_animation(intro, min(0.4, dur / 3))
        if outro:
            seg.add_animation(outro, min(0.25, dur / 4))
        if loop:
            seg.add_animation(loop)
        self.script.add_segment(seg, track)
        return seg

    def subtitle(self, text, start, dur, highlight=False, y=None):
        """자막 한 줄. highlight=True 면 강조색."""
        y = y if y is not None else (0.72 if self.vertical else 0.86)
        color = self.brand["accent"] if highlight else self.brand["text"]
        return self._text(text, start, dur, "자막", size=9.0 if self.vertical else 7.0, color=color, y=y)

    def hook(self, text, start, dur, sub=None, y=0.25):
        """첫 화면 글자 훅 (+ 아래 강조 알약 한 줄)."""
        self._text(text, start, dur, "훅", size=15.0, color=self.brand["text"], y=y,
                   intro=TextIntro.弹出, outro=TextOutro.渐隐)
        if sub:
            self._text(sub, start + 0.15, max(0.3, dur - 0.15), "훅_서브", size=8.5,
                       color=self.brand["accent_text"], y=y + 0.07, border=False, shadow=False,
                       bg=self.brand["accent"], intro=TextIntro.弹出, outro=TextOutro.渐隐)

    def keyword(self, text, start, dur=1.2, y=0.6, x=0.0, angle=-4.0):
        """핵심 단어 스티커 (강조색 박스, 살짝 기울임)."""
        return self._text(text, start, dur, "키워드", size=11.0, color=self.brand["accent_text"], y=y, x=x,
                          border=False, shadow=False, bg=self.brand["accent"], rotation=angle,
                          intro=TextIntro.弹出, outro=TextOutro.缩小)

    def counter(self, value, start, dur=1.8, suffix="", prefix="", steps=8, y=0.4, decimals=0):
        """숫자 카운트업: 짧은 텍스트 조각을 이어서 0→value 로 올라가게 한다(각 조각도 수정 가능)."""
        count_t = min(0.8, dur * 0.5)
        step = count_t / steps
        for i in range(1, steps + 1):
            p = 1 - (1 - i / steps) ** 3
            last = i == steps
            v = value if last else value * p
            txt = f"{prefix}{v:,.{decimals}f}{suffix}"
            t0 = start + (i - 1) * step
            self._text(txt, t0, (dur - count_t + step) if last else step, "숫자", size=17.0,
                       color=self.brand["accent"] if last else self.brand["text"], y=y,
                       intro=TextIntro.放大 if last else None, outro=TextOutro.渐隐 if last else None)

    def chapter(self, num, title, start, dur=3.0):
        """롱폼 챕터 카드 (왼쪽 아래)."""
        y = 0.82
        self._text(f"{int(num):02d}", start, dur, "챕터", size=9.0, color=self.brand["accent_text"],
                   y=y, x=-0.78, border=False, shadow=False, bg=self.brand["accent"],
                   intro=TextIntro.向右滑动, outro=TextOutro.向左滑动)
        self._text(title, start + 0.1, dur - 0.1, "챕터_제목", size=8.0, color=self.brand["text"],
                   y=y, x=-0.45, border=False, bg="#111111", intro=TextIntro.向右滑动, outro=TextOutro.向左滑动)

    def cta(self, text, start, dur=3.0, y=0.8):
        """마지막 행동 유도 버튼 (통통 튀는 반복 애니메이션)."""
        return self._text(text, start, dur, "행동유도", size=9.5, color=self.brand["accent_text"], y=y,
                          border=False, shadow=False, bg=self.brand["accent"],
                          intro=TextIntro.向上弹入, loop=TextLoopAnim.调皮)

    def save(self):
        self.script.save()
        return self.script


def _selftest(video, root):
    os.makedirs(root, exist_ok=True)
    d = Draft("수정가능_테스트", vertical=True, root=root)
    total = _probe_duration(video)
    keep = [(0.2, min(1.4, total)), (min(1.8, total - 0.5), min(3.2, total))]
    d.add_cuts(video, keep, zoom_every_other=1.12)
    d.hook("월 300 버는 법", 0.0, 1.5, sub="딱 3가지")
    d.subtitle("이거 모르면 손해", 0.0, 1.2)
    d.keyword("반전", 1.3, 0.9)
    d.counter(87, 1.0, 1.5, suffix="%")
    d.cta("팔로우하고 다음 편 보기", 1.5, 1.0)
    d.save()

    path = os.path.join(root, "수정가능_테스트", "draft_content.json")
    data = json.load(open(path, encoding="utf-8"))
    texts = data["materials"]["texts"]
    segs = [s for t in data["tracks"] if t["type"] == "video" for s in t["segments"]]
    ok_text = len(texts) > 0 and all(t.get("content") for t in texts)
    ok_src = all(s["source_timerange"]["start"] > 0 or i == 0 for i, s in enumerate(segs))
    ok_audio = all(s.get("volume", 1.0) > 0 for s in segs)
    print(f"텍스트 {len(texts)}개(수정 가능): {'OK' if ok_text else '실패'}")
    print(f"영상 {len(segs)}컷, 원본 참조·앞뒤 늘리기 가능: {'OK' if ok_src else '실패'}")
    print(f"영상 소리 켜짐: {'OK' if ok_audio else '실패'}")
    return ok_text and ok_src and ok_audio


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        root = sys.argv[3] if len(sys.argv) > 3 else DRAFT_ROOT
        sys.exit(0 if _selftest(os.path.expanduser(sys.argv[2]), os.path.expanduser(root)) else 1)
    print(__doc__)
