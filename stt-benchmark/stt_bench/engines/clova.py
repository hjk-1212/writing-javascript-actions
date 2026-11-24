"""네이버 CLOVA Speech 장문 인식 API(로컬 파일 업로드, 동기 방식).

클로바노트 앱에는 외부 API가 없으므로, 같은 네이버 엔진 계열인 CLOVA Speech로 비교한다.
문서: https://api.ncloud-docs.com/docs/ai-application-service-clovaspeech-longsentence-local
환경변수: CLOVA_SPEECH_INVOKE_URL (콘솔 > 빌더 > 설정 > 연동 정보), CLOVA_SPEECH_SECRET
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from ..types import Segment, Transcript


class ClovaSpeechEngine:
    name = "clova"

    def __init__(self, keywords: list[str] | None = None, timeout_sec: int = 3600,
                 session: requests.Session | None = None):
        self.invoke_url = (os.environ.get("CLOVA_SPEECH_INVOKE_URL") or "").rstrip("/")
        self.secret = os.environ.get("CLOVA_SPEECH_SECRET")
        if not (self.invoke_url and self.secret):
            raise RuntimeError("CLOVA_SPEECH_INVOKE_URL / CLOVA_SPEECH_SECRET 환경변수를 설정하세요.")
        self.keywords = keywords or []
        self.timeout_sec = timeout_sec
        self.http = session or requests.Session()

    def transcribe(self, audio: Path) -> Transcript:
        params: dict = {
            "language": "ko-KR",
            "completion": "sync",
            "wordAlignment": False,
            "fullText": True,
            "diarization": {"enable": True},
        }
        if self.keywords:
            params["boostings"] = [{"words": ",".join(self.keywords)}]
        with audio.open("rb") as f:
            r = self.http.post(
                f"{self.invoke_url}/recognizer/upload",
                headers={"X-CLOVASPEECH-API-KEY": self.secret},
                files={"media": (audio.name, f)},
                data={"params": json.dumps(params, ensure_ascii=False), "type": "application/json"},
                timeout=self.timeout_sec,
            )
        r.raise_for_status()
        body = r.json()
        if body.get("result") not in ("COMPLETED", "SUCCEEDED"):
            raise RuntimeError(f"CLOVA Speech 실패: {body.get('result')} {body.get('message')}")

        segs = [
            Segment(start=s["start"] / 1000, end=s["end"] / 1000, text=s["text"],
                    speaker=(s.get("speaker") or {}).get("label"))
            for s in body.get("segments", [])
        ]
        return Transcript(engine=self.name, segments=segs, raw=body)
