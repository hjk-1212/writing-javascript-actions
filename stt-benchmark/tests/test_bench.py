import json
from pathlib import Path

import pytest

from stt_bench.cli import main
from stt_bench.metrics import cer, cp_cer, normalize
from stt_bench.reference import load_reference, parse_clovanote_txt


def test_normalize_drops_spaces_and_punct():
    assert normalize("안녕하세요, 여러분! ITS 2026.") == "안녕하세요여러분its2026"


def test_cer_basic():
    assert cer("오늘 회의를 시작합니다", "오늘 회의를 시작합니다.") == 0.0
    # 10글자 중 1글자 틀림
    assert cer("오늘회의를시작합니다", "오늘회이를시작합니다") == pytest.approx(0.1)


def test_cp_cer_handles_label_permutation():
    ref = {"김": "안건을 보고드리겠습니다", "이": "질문이 있습니다"}
    hyp = {"0": "질문이 있습니다", "1": "안건을 보고드리겠습니다"}
    assert cp_cer(ref, hyp) == 0.0


def test_cp_cer_penalizes_wrong_speaker():
    ref = {"김": "가나다라", "이": "마바사아"}
    hyp_merged = {"0": "가나다라마바사아"}  # 화자를 하나로 합쳐버림
    assert cp_cer(ref, hyp_merged) > cer("가나다라 마바사아", "가나다라마바사아")


def test_load_reference_with_and_without_speakers(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("김과장: 시작하겠습니다.\n이대리: 네.\n김과장: 첫 안건입니다.\n", encoding="utf-8")
    ref = load_reference(p)
    assert ref.by_speaker == {"김과장": "시작하겠습니다. 첫 안건입니다.", "이대리": "네."}

    p.write_text("그냥 받아쓴 문장입니다.\n두 번째 줄.\n", encoding="utf-8")
    assert load_reference(p).by_speaker is None


def test_parse_clovanote_export(tmp_path: Path):
    p = tmp_path / "c.txt"
    p.write_text(
        "주간 회의\n2026.11.24 화 오후 2:00 ・ 12분 3초\n\n"
        "참석자 1 00:00\n시작하겠습니다.\n\n참석자 2 00:05\n네 좋습니다.\n다음 안건은요.\n\n"
        "참석자 1 01:02:03\n마치겠습니다.\n",
        encoding="utf-8",
    )
    t = parse_clovanote_txt(p)
    assert [s.speaker for s in t.segments] == ["참석자 1", "참석자 2", "참석자 1"]
    assert t.segments[1].text == "네 좋습니다. 다음 안건은요."
    assert t.segments[2].start == 3723.0
    assert t.segments[0].end == 5.0


class FakeResp:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, posts, gets=()):
        self.posts, self.gets, self.calls = list(posts), list(gets), []

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self.posts.pop(0)

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self.gets.pop(0)


def test_rtzr_engine(monkeypatch, tmp_path: Path):
    import stt_bench.engines.rtzr as rtzr

    monkeypatch.setenv("RTZR_CLIENT_ID", "id")
    monkeypatch.setenv("RTZR_CLIENT_SECRET", "secret")
    monkeypatch.setattr(rtzr.time, "sleep", lambda s: None)
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    sess = FakeSession(
        posts=[FakeResp({"access_token": "tok", "expire_at": 9e12}), FakeResp({"id": "job1"})],
        gets=[
            FakeResp({"id": "job1", "status": "transcribing"}),
            FakeResp({"id": "job1", "status": "completed", "results": {"utterances": [
                {"start_at": 1000, "duration": 2500, "msg": "안녕하세요.", "spk": 0, "lang": "ko"},
                {"start_at": 4000, "duration": 1000, "msg": "네.", "spk": 1, "lang": "ko"},
            ]}}),
        ],
    )
    t = rtzr.RtzrEngine(keywords=["C-ITS"], spk_count=2, session=sess).transcribe(audio)
    assert t.text == "안녕하세요. 네."
    assert t.segments[0].end == 3.5 and t.speakers == {"0", "1"}
    config = json.loads(sess.calls[1][2]["data"]["config"])
    assert config["diarization"] == {"spk_count": 2} and config["keywords"] == ["C-ITS"]
    assert sess.calls[1][2]["headers"]["Authorization"] == "Bearer tok"


def test_clova_engine(monkeypatch, tmp_path: Path):
    import stt_bench.engines.clova as clova

    monkeypatch.setenv("CLOVA_SPEECH_INVOKE_URL", "https://example.invalid/external/v1/123/abc/")
    monkeypatch.setenv("CLOVA_SPEECH_SECRET", "sec")
    audio = tmp_path / "a.m4a"
    audio.write_bytes(b"x")
    sess = FakeSession(posts=[FakeResp({
        "result": "COMPLETED", "message": "Succeeded", "text": "안녕하세요 네",
        "segments": [
            {"start": 0, "end": 1500, "text": "안녕하세요", "speaker": {"label": "1", "name": "A"}},
            {"start": 1600, "end": 2000, "text": "네", "speaker": {"label": "2", "name": "B"}},
        ],
    })])
    t = clova.ClovaSpeechEngine(session=sess).transcribe(audio)
    _, url, kw = sess.calls[0]
    assert url == "https://example.invalid/external/v1/123/abc/recognizer/upload"
    assert kw["headers"]["X-CLOVASPEECH-API-KEY"] == "sec"
    assert json.loads(kw["data"]["params"])["completion"] == "sync"
    assert t.speakers == {"1", "2"} and t.segments[1].start == 1.6


def test_cli_end_to_end_with_manual_engine(tmp_path: Path, monkeypatch):
    data, manual, out = tmp_path / "data", tmp_path / "manual" / "clovanote", tmp_path / "results"
    data.mkdir()
    manual.mkdir(parents=True)
    (data / "m1.m4a").write_bytes(b"x")
    (data / "m1.txt").write_text("김: 오늘 회의를 시작합니다\n이: 네 좋습니다\n", encoding="utf-8")
    (manual / "m1.txt").write_text(
        "참석자 1 00:00\n오늘 회의를 시작합니다\n\n참석자 2 00:03\n네 좋슴니다\n", encoding="utf-8")
    monkeypatch.delenv("RTZR_CLIENT_ID", raising=False)

    rc = main(["--data", str(data), "--manual-dir", str(tmp_path / "manual"), "--out", str(out),
               "--engines", "manual:clovanote,rtzr", "--price", "manual:clovanote=0"])
    assert rc == 0
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "manual:clovanote" in md and "rtzr" not in md.split("## 파일별 결과")[1]
    assert (out / "report.csv").exists()
