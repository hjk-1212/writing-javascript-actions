# 한국어 STT 엔진 비교 도구

실제 회의 녹음으로 STT 엔진의 **정확도(CER), 화자 구분, 처리 속도, 비용**을 한 번에 비교합니다.

| 엔진 이름 | 대상 | 필요한 것 |
|---|---|---|
| `whisper[:모델]` | 자체 호스팅 Whisper(faster-whisper). 기본 `large-v3` | `pip install faster-whisper "av<14"`. 화자 구분은 `pyannote.audio`와 `HF_TOKEN` |
| `rtzr` | 리턴제로 파일 STT API | `RTZR_CLIENT_ID`, `RTZR_CLIENT_SECRET` |
| `clova` | 네이버 CLOVA Speech 장문 인식 API | `CLOVA_SPEECH_INVOKE_URL`, `CLOVA_SPEECH_SECRET` |
| `manual:<이름>` | 앱에서 내보낸 텍스트(클로바노트 등) | `manual/<이름>/<파일명>.txt` |

> 클로바노트 앱에는 외부 API가 없습니다. 앱 자체를 비교하려면 `manual:clovanote`를 쓰고,
> 네이버 엔진을 우리 앱에 붙일 때의 성능은 `clova`(CLOVA Speech API)로 확인합니다.

## 1. 준비

```bash
cd stt-benchmark
pip install -r requirements.txt
```

## 2. 데이터 넣기

```
stt-benchmark/
├─ data/
│  ├─ 주간회의_1105.m4a      ← 녹음
│  └─ 주간회의_1105.txt      ← 사람이 받아쓴 정답(같은 파일명)
└─ manual/
   └─ clovanote/
      └─ 주간회의_1105.txt   ← 클로바노트 앱 > 텍스트로 내보내기
```

**정답 파일 형식**
- 화자 구분까지 평가하려면 모든 줄을 `화자: 내용` 형식으로 씁니다.
  ```
  김팀장: 오늘 주간 회의를 시작하겠습니다.
  이연구원: 네, 지난주 시험 주행을 마쳤습니다.
  ```
- 화자 라벨이 없으면 글자 정확도(CER)만 계산합니다.
- 들리는 그대로 씁니다. "음", "어" 같은 군말은 넣든 빼든 **모든 파일에서 같은 기준**으로 통일합니다.

**권장 표본**: 실제 업무 회의 3~5건, 건당 10~30분. 조용한 회의실, 잡음 많은 현장, 화상회의를 섞으면 좋습니다.

**보안**: `data/`, `manual/`, `results/`는 `.gitignore`에 들어 있어 저장소에 올라가지 않습니다.
유료 API(rtzr, clova)에 올리면 녹음이 해당 회사 서버로 전송되니, 보안 등급이 높은 회의는 `whisper`로만 시험하세요.

## 3. 실행

```bash
export RTZR_CLIENT_ID=... RTZR_CLIENT_SECRET=...
export CLOVA_SPEECH_INVOKE_URL=... CLOVA_SPEECH_SECRET=...

python -m stt_bench \
  --engines whisper,rtzr,clova,manual:clovanote \
  --keywords keywords.example.txt \
  --price clova=<콘솔에서 확인한 시간당 원화> \
  --monthly-hours 20
```

| 옵션 | 설명 |
|---|---|
| `--keywords` | 사용자 사전(한 줄에 한 단어). rtzr는 `keywords`, clova는 `boostings`, whisper는 `initial_prompt`로 전달 |
| `--num-speakers` | 화자 수를 알면 지정(rtzr, whisper) |
| `--price 엔진=원` | 시간당 요금. rtzr는 공식 요금표 기본값(1,000원/시간, 월 1,000시간 이하) 내장. clova는 공개 단가를 확인하지 못해 직접 입력 |
| `--monthly-hours` | 월 비용 추정 기준 시간(기본 20) |
| `--force` | 캐시를 무시하고 다시 변환. 기본은 `results/cache/`의 결과를 재사용해 **유료 API를 두 번 부르지 않음** |

키가 없는 엔진은 건너뛰고 나머지만 비교합니다.

## 4. 결과

`results/report.md`(요약표)와 `results/report.csv`(엑셀용)가 만들어집니다.

| 지표 | 뜻 |
|---|---|
| CER | 공백·문장부호를 뺀 글자 오류율. 낮을수록 좋음 |
| cpCER | 화자별로 나눈 텍스트를 정답 화자와 가장 잘 맞게 짝지은 뒤의 CER. 화자 구분이 틀리면 커짐 |
| 화자 수 오차 | 인식한 화자 수와 실제 화자 수의 차이 |
| 1시간 처리 시간 | 1시간 녹음을 처리하는 데 걸린 분. API는 대기열 시간 포함 |
| 월 비용 | 시간당 단가 × 월 사용 시간. 부가세·무료 제공량 미반영 |

## 5. 테스트

```bash
python -m pytest -q
```

API 호출은 가짜 응답으로 시험합니다(실제 과금 없음).
