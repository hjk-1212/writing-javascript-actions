"""자체 호스팅 Whisper(faster-whisper) + 선택적 화자 구분(pyannote).

설치: pip install faster-whisper  (화자 구분까지: pip install pyannote.audio, HF_TOKEN 필요)
GPU가 있으면 자동으로 cuda를 쓰고, 없으면 CPU int8로 돈다.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..types import Segment, Transcript


class WhisperEngine:
    def __init__(self, model: str = "large-v3", diarize: bool = True, keywords: list[str] | None = None,
                 num_speakers: int | None = None):
        from faster_whisper import WhisperModel

        device = "cuda" if _has_cuda() else "cpu"
        compute = "float16" if device == "cuda" else "int8"
        self.name = f"whisper-{model}"
        self.model = WhisperModel(model, device=device, compute_type=compute)
        self.keywords = keywords or []
        self.num_speakers = num_speakers
        self.diarizer = _load_diarizer(device) if diarize else None

    def transcribe(self, audio: Path) -> Transcript:
        # 사용자 사전은 initial_prompt로 넣어 고유명사 인식을 돕는다.
        prompt = ", ".join(self.keywords) if self.keywords else None
        it, info = self.model.transcribe(str(audio), language="ko", vad_filter=True,
                                         initial_prompt=prompt, beam_size=5)
        segs = [Segment(start=s.start, end=s.end, text=s.text.strip()) for s in it]

        if self.diarizer is not None:
            kwargs = {"num_speakers": self.num_speakers} if self.num_speakers else {}
            diar = self.diarizer(str(audio), **kwargs)
            turns = [(t.start, t.end, spk) for t, _, spk in diar.itertracks(yield_label=True)]
            for s in segs:
                s.speaker = _best_speaker(s.start, s.end, turns)
        return Transcript(engine=self.name, segments=segs, audio_sec=info.duration)


def _has_cuda() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _load_diarizer(device: str):
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("  [whisper] HF_TOKEN이 없어 화자 구분을 건너뜁니다.")
        return None
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        print("  [whisper] pyannote.audio가 없어 화자 구분을 건너뜁니다.")
        return None
    pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=token)
    if device == "cuda":
        import torch

        pipe.to(torch.device("cuda"))
    return pipe


def _best_speaker(start: float, end: float, turns: list[tuple[float, float, str]]) -> str | None:
    """구간과 가장 많이 겹치는 화자를 고른다."""
    best, best_overlap = None, 0.0
    for ts, te, spk in turns:
        overlap = min(end, te) - max(start, ts)
        if overlap > best_overlap:
            best, best_overlap = spk, overlap
    return best
