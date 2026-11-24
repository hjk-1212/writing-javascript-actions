"""정답 전사(사람이 받아쓴 텍스트)와 클로바노트 내보내기 파일 읽기."""
from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from .types import Segment, Transcript

# "화자명: 내용" 또는 "화자명<TAB>내용"
_SPK_LINE = re.compile(r"^\s*([^\t:：]{1,20}?)\s*(?:[:：]|\t)\s*(.+)$")
# 클로바노트 텍스트 내보내기의 발화 머리줄: "참석자 1 00:15" / "홍길동 01:02:03"
_CLOVANOTE_HEAD = re.compile(r"^\s*(.+?)\s+((?:\d{1,2}:)?\d{1,2}:\d{2})\s*$")


@dataclass
class Reference:
    text: str
    by_speaker: dict[str, str] | None  # 화자 라벨이 없으면 None


def load_reference(path: Path) -> Reference:
    """정답 파일을 읽는다.

    모든 내용 줄이 '화자: 내용' 형식이면 화자별 정답으로 쓰고,
    하나라도 아니면 화자 정보 없는 일반 텍스트로 본다.
    """
    lines = [ln for ln in path.read_text(encoding="utf-8-sig").splitlines() if ln.strip()]
    matches = [_SPK_LINE.match(ln) for ln in lines]
    if lines and all(matches):
        by_spk: dict[str, list[str]] = OrderedDict()
        for m in matches:
            by_spk.setdefault(m.group(1).strip(), []).append(m.group(2).strip())
        joined = {k: " ".join(v) for k, v in by_spk.items()}
        return Reference(text=" ".join(m.group(2) for m in matches), by_speaker=joined)
    return Reference(text=" ".join(lines), by_speaker=None)


def _to_sec(ts: str) -> float:
    parts = [int(p) for p in ts.split(":")]
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return float(sec)


def parse_clovanote_txt(path: Path, engine: str = "clovanote") -> Transcript:
    """클로바노트 앱에서 '텍스트(.txt)로 내보내기'한 파일을 Transcript로 바꾼다.

    머리줄("참석자 1 00:15") 앞의 제목·날짜 줄은 무시한다.
    """
    segments: list[Segment] = []
    cur_spk: str | None = None
    cur_start = 0.0
    buf: list[str] = []

    def flush():
        if cur_spk is not None and buf:
            segments.append(Segment(start=cur_start, end=cur_start, text=" ".join(buf), speaker=cur_spk))

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = _CLOVANOTE_HEAD.match(line)
        if m:
            flush()
            cur_spk, cur_start, buf = m.group(1).strip(), _to_sec(m.group(2)), []
        elif line.strip() and cur_spk is not None:
            buf.append(line.strip())
    flush()

    # 다음 발화 시작 시각을 끝 시각으로 채운다.
    for a, b in zip(segments, segments[1:]):
        a.end = b.start
    return Transcript(engine=engine, segments=segments)


def parse_plain_txt(path: Path, engine: str) -> Transcript:
    """다른 앱에서 내보낸 일반 텍스트. '화자: 내용' 형식이면 화자도 살린다."""
    ref = load_reference(path)
    if ref.by_speaker:
        segs = [Segment(0.0, 0.0, t, s) for s, t in ref.by_speaker.items()]
    else:
        segs = [Segment(0.0, 0.0, ref.text, None)]
    return Transcript(engine=engine, segments=segs)
