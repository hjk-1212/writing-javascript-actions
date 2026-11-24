"""리턴제로(RTZR, 구 VITO) 파일 STT API.

문서: https://developers.rtzr.ai/docs/stt-file/
환경변수: RTZR_CLIENT_ID, RTZR_CLIENT_SECRET
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from ..types import Segment, Transcript

BASE = "https://openapi.vito.ai"
POLL_SEC = 5  # 문서 권장 간격. 더 짧으면 429(A0003)


class RtzrEngine:
    name = "rtzr"

    def __init__(self, keywords: list[str] | None = None, spk_count: int = 0, model: str = "sommers",
                 timeout_sec: int = 3 * 3600, session: requests.Session | None = None):
        self.client_id = os.environ.get("RTZR_CLIENT_ID")
        self.client_secret = os.environ.get("RTZR_CLIENT_SECRET")
        if not (self.client_id and self.client_secret):
            raise RuntimeError("RTZR_CLIENT_ID / RTZR_CLIENT_SECRET 환경변수를 설정하세요.")
        self.keywords = keywords or []
        self.spk_count = spk_count  # 0이면 화자 수 자동 추정
        self.model = model
        self.timeout_sec = timeout_sec
        self.http = session or requests.Session()
        self._token: str | None = None
        self._token_exp = 0.0

    def _auth(self) -> dict:
        # 토큰은 6시간 유효. 만료 30분 전에 갱신한다.
        if self._token is None or self._token_exp < time.time() + 1800:
            r = self.http.post(f"{BASE}/v1/authenticate",
                               data={"client_id": self.client_id, "client_secret": self.client_secret}, timeout=30)
            r.raise_for_status()
            body = r.json()
            self._token, self._token_exp = body["access_token"], float(body.get("expire_at", 0))
        return {"Authorization": f"Bearer {self._token}"}

    def transcribe(self, audio: Path) -> Transcript:
        config = {
            "model_name": self.model,
            "language": "ko",
            "use_diarization": True,
            "diarization": {"spk_count": self.spk_count},
            "use_itn": True,
            "use_disfluency_filter": False,  # 정답 전사와 맞추기 위해 간투사를 지우지 않음
            "use_paragraph_splitter": False,
        }
        if self.keywords:
            config["keywords"] = self.keywords
        with audio.open("rb") as f:
            r = self.http.post(f"{BASE}/v1/transcribe", headers=self._auth(),
                               files={"file": (audio.name, f)}, data={"config": json.dumps(config)}, timeout=600)
        r.raise_for_status()
        job_id = r.json()["id"]

        deadline = time.time() + self.timeout_sec
        while True:
            r = self.http.get(f"{BASE}/v1/transcribe/{job_id}", headers=self._auth(), timeout=30)
            if r.status_code == 429:
                time.sleep(POLL_SEC * 2)
                continue
            r.raise_for_status()
            body = r.json()
            status = body.get("status")
            if status == "completed":
                break
            if status == "failed":
                raise RuntimeError(f"RTZR 변환 실패: {body.get('error')}")
            if time.time() > deadline:
                raise TimeoutError(f"RTZR 작업 {job_id} 시간 초과")
            time.sleep(POLL_SEC)

        segs = [
            Segment(start=u["start_at"] / 1000, end=(u["start_at"] + u["duration"]) / 1000,
                    text=u["msg"], speaker=str(u.get("spk")) if u.get("spk") is not None else None)
            for u in body["results"]["utterances"]
        ]
        return Transcript(engine=self.name, segments=segs, raw=body)
