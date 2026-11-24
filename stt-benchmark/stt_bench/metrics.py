"""정확도 지표.

- CER: 글자 오류율. 공백·문장부호를 지우고 글자 단위 편집거리 / 정답 글자 수.
- cpCER: 화자별로 텍스트를 이어 붙인 뒤, 정답 화자와 인식 화자를 가장 잘 맞는
  짝으로 연결했을 때의 CER. 화자 구분이 틀리면 값이 올라간다.
"""
from __future__ import annotations

import itertools
import re
import unicodedata

from rapidfuzz.distance import Levenshtein

# 한글·영문·숫자만 남긴다. 공백과 문장부호는 엔진마다 넣는 방식이 달라 비교에서 뺀다.
_KEEP = re.compile(r"[^0-9A-Za-zㄱ-ㆎ가-힣]")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    return _KEEP.sub("", text)


def edit_distance(ref: str, hyp: str) -> int:
    return Levenshtein.distance(ref, hyp)


def cer(ref: str, hyp: str) -> float:
    r, h = normalize(ref), normalize(hyp)
    if not r:
        return 0.0 if not h else 1.0
    return edit_distance(r, h) / len(r)


def cp_cer(ref_by_spk: dict[str, str], hyp_by_spk: dict[str, str]) -> float:
    """화자 순열을 고려한 CER(concatenated minimum-permutation CER)."""
    refs = [normalize(t) for t in ref_by_spk.values()]
    hyps = [normalize(t) for t in hyp_by_spk.values()]
    total = sum(len(r) for r in refs)
    if total == 0:
        return 0.0
    # 개수가 다르면 빈 화자를 채워 정방행렬로 만든다(남는 화자의 글자는 전부 오류).
    n = max(len(refs), len(hyps))
    refs += [""] * (n - len(refs))
    hyps += [""] * (n - len(hyps))
    cost = [[edit_distance(r, h) for h in hyps] for r in refs]
    return _min_assignment(cost) / total


def _min_assignment(cost: list[list[int]]) -> int:
    n = len(cost)
    try:
        from scipy.optimize import linear_sum_assignment

        rows, cols = linear_sum_assignment(cost)
        return int(sum(cost[r][c] for r, c in zip(rows, cols)))
    except ImportError:
        if n > 8:
            raise RuntimeError("화자가 9명 이상이면 scipy가 필요합니다: pip install scipy")
        return min(
            sum(cost[i][p[i]] for i in range(n)) for p in itertools.permutations(range(n))
        )
