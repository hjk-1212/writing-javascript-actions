"""엔진 생성기. 엔진 이름 → 객체.

- whisper[:모델]   자체 Whisper (예: whisper, whisper:medium)
- rtzr            리턴제로 API
- clova           CLOVA Speech API
- manual:<이름>    앱에서 내보낸 텍스트를 읽음 (예: manual:clovanote)
"""
from __future__ import annotations


def build_engine(spec: str, keywords: list[str], num_speakers: int | None):
    kind, _, arg = spec.partition(":")
    if kind == "whisper":
        from .whisper_local import WhisperEngine

        return WhisperEngine(model=arg or "large-v3", keywords=keywords, num_speakers=num_speakers)
    if kind == "rtzr":
        from .rtzr import RtzrEngine

        return RtzrEngine(keywords=keywords, spk_count=num_speakers or 0)
    if kind == "clova":
        from .clova import ClovaSpeechEngine

        return ClovaSpeechEngine(keywords=keywords)
    if kind == "manual":
        if not arg:
            raise ValueError("manual 엔진은 이름이 필요합니다. 예: manual:clovanote")
        return None  # 수동 엔진은 cli에서 파일을 직접 읽는다.
    raise ValueError(f"알 수 없는 엔진: {spec}")
