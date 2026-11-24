"""결과 표(report.md, report.csv) 만들기."""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Row:
    file: str
    engine: str
    ref_chars: int
    cer: float
    cpcer: float | None
    ref_speakers: int | None
    hyp_speakers: int | None
    audio_sec: float | None
    elapsed_sec: float | None


def _pct(v: float | None) -> str:
    return "-" if v is None else f"{v:.2%}"


def _num(v: float | None, fmt: str = "{:.1f}") -> str:
    return "-" if v is None else fmt.format(v)


def _price_key(engine: str) -> str:
    return engine.split(":", 1)[0] if not engine.startswith("manual:") else engine


def summarize(rows: list[Row], prices: dict[str, float], monthly_hours: float) -> list[dict]:
    by_engine: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_engine[r.engine].append(r)
    out = []
    for engine, rs in by_engine.items():
        chars = sum(r.ref_chars for r in rs)
        # 글자 수 가중 CER: 긴 파일이 더 큰 비중을 갖는다.
        w_cer = sum(r.cer * r.ref_chars for r in rs) / chars if chars else None
        cps = [r.cpcer for r in rs if r.cpcer is not None]
        spk_err = [abs(r.hyp_speakers - r.ref_speakers) for r in rs
                   if r.hyp_speakers is not None and r.ref_speakers is not None]
        timed = [r for r in rs if r.elapsed_sec is not None and r.audio_sec]
        rtf = (sum(r.elapsed_sec for r in timed) / sum(r.audio_sec for r in timed)) if timed else None
        price = prices.get(_price_key(engine))
        out.append({
            "engine": engine,
            "files": len(rs),
            "cer": w_cer,
            "cpcer": sum(cps) / len(cps) if cps else None,
            "spk_err": sum(spk_err) / len(spk_err) if spk_err else None,
            "rtf": rtf,
            "min_per_hour": rtf * 60 if rtf is not None else None,
            "price_per_hour": price,
            "monthly_cost": price * monthly_hours if price is not None else None,
        })
    out.sort(key=lambda d: (d["cer"] is None, d["cer"]))
    return out


def write_reports(rows: list[Row], out_dir: Path, prices: dict[str, float], monthly_hours: float):
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "report.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:  # 엑셀 한글 깨짐 방지
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))

    summary = summarize(rows, prices, monthly_hours)
    lines = [
        "# STT 엔진 비교 결과",
        "",
        f"- 파일 수: {len({r.file for r in rows})}개",
        f"- 월 비용 추정 기준: 월 {monthly_hours:g}시간",
        "",
        "## 엔진별 요약 (CER 낮은 순)",
        "",
        "| 엔진 | 파일 | CER | cpCER(화자 포함) | 화자 수 오차 | 1시간 처리 시간(분) | 시간당 요금(원) | 월 비용(원) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in summary:
        lines.append(
            f"| {s['engine']} | {s['files']} | {_pct(s['cer'])} | {_pct(s['cpcer'])} | {_num(s['spk_err'])} "
            f"| {_num(s['min_per_hour'])} | {_num(s['price_per_hour'], '{:,.0f}')} "
            f"| {_num(s['monthly_cost'], '{:,.0f}')} |"
        )
    lines += [
        "",
        "## 파일별 결과",
        "",
        "| 파일 | 엔진 | 정답 글자 수 | CER | cpCER | 화자(인식/정답) | 오디오(분) | 처리(초) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda r: (r.file, r.cer)):
        spk = f"{r.hyp_speakers or '-'}/{r.ref_speakers or '-'}"
        lines.append(
            f"| {r.file} | {r.engine} | {r.ref_chars:,} | {_pct(r.cer)} | {_pct(r.cpcer)} | {spk} "
            f"| {_num(r.audio_sec / 60 if r.audio_sec else None)} | {_num(r.elapsed_sec)} |"
        )
    lines += [
        "",
        "## 지표 설명",
        "",
        "- **CER**: 공백·문장부호를 뺀 글자 단위 오류율. 낮을수록 좋음.",
        "- **cpCER**: 화자별로 나눈 텍스트를 정답 화자와 가장 잘 맞게 짝지은 뒤의 CER. "
        "화자 구분이 틀리면 CER보다 커진다. 정답 파일에 화자 라벨이 있을 때만 계산.",
        "- **1시간 처리 시간**: 1시간 녹음을 처리하는 데 걸린 시간(분). API는 대기열 시간 포함. "
        "manual(앱 내보내기)은 측정 안 됨.",
        "- **요금**: 사용자가 지정한 시간당 단가 기준 추정치. 부가세·무료 제공량 미반영.",
    ]
    md_path = out_dir / "report.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, csv_path
