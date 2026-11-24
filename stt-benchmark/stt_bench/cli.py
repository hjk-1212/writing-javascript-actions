"""STT 엔진 비교 실행기.

사용 예:
    python -m stt_bench --data data --engines whisper,rtzr,clova,manual:clovanote

data/ 안에 같은 이름의 오디오와 정답 텍스트를 둔다.
    data/회의01.m4a   data/회의01.txt
앱에서 내보낸 결과는 manual/<이름>/<파일명>.txt 에 둔다.
    manual/clovanote/회의01.txt
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .engines import build_engine
from .metrics import cer, cp_cer, normalize
from .reference import load_reference, parse_clovanote_txt, parse_plain_txt
from .report import Row, write_reports
from .types import Transcript

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".mp4", ".flac", ".ogg", ".aac"}

# 시간당 원화(부가세 별도). rtzr는 공식 요금표 1구간(월 1,000시간 이하) 기준.
DEFAULT_PRICE_PER_HOUR = {"rtzr": 1000.0, "whisper": 0.0}


def audio_duration(path: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def load_manual(engine: str, stem: str, manual_dir: Path) -> Transcript | None:
    label = engine.split(":", 1)[1]
    path = manual_dir / label / f"{stem}.txt"
    if not path.exists():
        return None
    t = parse_clovanote_txt(path, engine=engine)
    return t if t.segments else parse_plain_txt(path, engine=engine)


def run_engine(spec: str, engine_obj, audio: Path, cache_dir: Path, force: bool) -> Transcript:
    """결과를 캐시에 저장해, 다시 돌릴 때 유료 API를 또 호출하지 않는다."""
    cache = cache_dir / spec.replace(":", "_") / f"{audio.stem}.json"
    if cache.exists() and not force:
        return Transcript.from_dict(json.loads(cache.read_text(encoding="utf-8")))
    t0 = time.time()
    t = engine_obj.transcribe(audio)
    t.engine = spec
    t.elapsed_sec = time.time() - t0
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(t.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    return t


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="한국어 STT 엔진 비교(CER, 화자 구분, 속도, 비용)")
    ap.add_argument("--data", type=Path, default=Path("data"), help="오디오와 정답(.txt) 폴더")
    ap.add_argument("--engines", default="whisper,rtzr,clova",
                    help="쉼표 구분: whisper[:모델], rtzr, clova, manual:<이름>")
    ap.add_argument("--manual-dir", type=Path, default=Path("manual"))
    ap.add_argument("--out", type=Path, default=Path("results"))
    ap.add_argument("--keywords", type=Path, help="사용자 사전(한 줄에 한 단어)")
    ap.add_argument("--num-speakers", type=int, help="화자 수를 알면 지정")
    ap.add_argument("--price", action="append", default=[], metavar="엔진=원/시간",
                    help="시간당 요금 지정. 예: --price clova=1200")
    ap.add_argument("--monthly-hours", type=float, default=20.0, help="월 비용 추정에 쓸 월 사용 시간")
    ap.add_argument("--force", action="store_true", help="캐시를 무시하고 다시 변환")
    args = ap.parse_args(argv)

    prices = dict(DEFAULT_PRICE_PER_HOUR)
    for p in args.price:
        k, _, v = p.partition("=")
        prices[k.strip()] = float(v)

    keywords = []
    if args.keywords:
        keywords = [w.strip() for w in args.keywords.read_text(encoding="utf-8").splitlines() if w.strip()]

    audios = sorted(p for p in args.data.iterdir() if p.suffix.lower() in AUDIO_EXT)
    pairs = [(a, a.with_suffix(".txt")) for a in audios if a.with_suffix(".txt").exists()]
    for a in audios:
        if not a.with_suffix(".txt").exists():
            print(f"[건너뜀] 정답 파일 없음: {a.with_suffix('.txt').name}")
    if not pairs:
        print(f"{args.data}에 '오디오 + 같은 이름의 .txt 정답' 쌍이 없습니다.", file=sys.stderr)
        return 1

    specs = [s.strip() for s in args.engines.split(",") if s.strip()]
    rows: list[Row] = []
    for spec in specs:
        print(f"== {spec}")
        try:
            engine = None if spec.startswith("manual:") else build_engine(spec, keywords, args.num_speakers)
        except Exception as e:  # 키 누락, 라이브러리 미설치 등
            print(f"  [건너뜀] {e}")
            continue
        for audio, ref_path in pairs:
            ref = load_reference(ref_path)
            dur = audio_duration(audio)
            try:
                if engine is None:
                    t = load_manual(spec, audio.stem, args.manual_dir)
                    if t is None:
                        print(f"  [건너뜀] {audio.stem}: {args.manual_dir}/{spec[7:]}/{audio.stem}.txt 없음")
                        continue
                else:
                    t = run_engine(spec, engine, audio, args.out / "cache", args.force)
            except Exception as e:
                print(f"  [실패] {audio.name}: {e}")
                continue

            dur = dur or t.audio_sec or max((s.end for s in t.segments), default=0) or None
            hyp_by_spk: dict[str, str] = {}
            for s in t.segments:
                hyp_by_spk.setdefault(s.speaker or "?", "")
                hyp_by_spk[s.speaker or "?"] += " " + s.text
            row = Row(
                file=audio.name, engine=spec,
                ref_chars=len(normalize(ref.text)),
                cer=cer(ref.text, t.text),
                cpcer=cp_cer(ref.by_speaker, hyp_by_spk) if ref.by_speaker and t.speakers else None,
                ref_speakers=len(ref.by_speaker) if ref.by_speaker else None,
                hyp_speakers=len(t.speakers) or None,
                audio_sec=dur, elapsed_sec=t.elapsed_sec,
            )
            rows.append(row)
            print(f"  {audio.name}: CER {row.cer:.2%}"
                  + (f", cpCER {row.cpcer:.2%}" if row.cpcer is not None else "")
                  + (f", 화자 {row.hyp_speakers or '-'}/{row.ref_speakers}" if row.ref_speakers else ""))

    if not rows:
        print("결과가 없습니다.", file=sys.stderr)
        return 1
    md, csv_path = write_reports(rows, args.out, prices, args.monthly_hours)
    print(f"\n보고서: {md}\nCSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
