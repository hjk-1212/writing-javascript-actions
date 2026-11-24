"""엔진 공통 결과 형식."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Segment:
    start: float  # 초
    end: float  # 초
    text: str
    speaker: str | None = None


@dataclass
class Transcript:
    engine: str
    segments: list[Segment] = field(default_factory=list)
    elapsed_sec: float | None = None  # 엔진 처리에 걸린 시간(벽시계)
    audio_sec: float | None = None  # 오디오 길이
    raw: dict | None = None  # 엔진 원본 응답(디버깅용)

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments if s.text.strip())

    @property
    def speakers(self) -> set[str]:
        return {s.speaker for s in self.segments if s.speaker is not None}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Transcript":
        segs = [Segment(**s) for s in d.get("segments", [])]
        return cls(
            engine=d["engine"],
            segments=segs,
            elapsed_sec=d.get("elapsed_sec"),
            audio_sec=d.get("audio_sec"),
            raw=d.get("raw"),
        )
