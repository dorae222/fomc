# FOMC 성명문이 주식시장(S&P 500)에 미친 영향 분석 가이드

> 마지막 업데이트: 2025-08-15

이 문서는 **1994년 이후 FOMC 성명문(Statement)** 발표가 **S&P 500** 일간 수익률과 변동성에 미친 영향을
재현 가능한 코드로 분석하는 방법을 설명합니다.  
데이터는 사용자가 직접 제공하거나(권장), 스크립트가 자동으로 내려받도록 구성되어 있습니다.

---

## 핵심 아이디어

- **제도 변화 포인트**  
  - **1994년 2월**: 회의 직후 **즉시 성명문 공표** 도입 → 발표 시점 전후 가격 반응 확대
  - **2000년 1월**: **모든 정례회의 후 성명문 정례화** → 주식시장 발표일 트리거가 구조화
- **분석 목표**  
  - FOMC **발표 전일(-1), 발표일(0), 익일(+1)**의 S&P 500 **평균 수익률** 및 **절대수익률(변동성 proxy)** 비교
  - **레짐(시기) 별** 차이: 1994–1999 / 2000–2007 / 2008–2012 / 2013–2019 / 2020–현재
  - FOMC **발표일 vs 비발표일**의 통계적 차이(간단 t-통계) 확인

> 본 분석은 **일간 데이터** 기준이며, 성명문 발표 시각(ET 2:00/2:15)과 같은 **초단기(분/시간) 효과**는 다루지 않습니다.
> 초단기 반응까지 보려면 분봉 데이터가 필요합니다.

---

## 필요한 것

1. **Python 3.9+**  
2. 패키지: `pandas`, `numpy`, `matplotlib`, `yfinance`(선택), `beautifulsoup4`(선택), `requests`(선택)  
3. **S&P 500 일일 종가 데이터**  
   - 자동: `yfinance` 로 `^GSPC` 다운로드  
   - 수동: CSV 제공(열 이름 예: `Date,Open,High,Low,Close,Adj Close,Volume`), Date는 YYYY-MM-DD
4. **FOMC 회의/성명문 날짜 CSV** (권장)  
   - 템플릿: [`fomc_dates_template.csv`](sandbox:/mnt/data/fomc_dates_template.csv)를 다운로드하여 채운 뒤 사용
   - 열: `date`(YYYY-MM-DD), `type`(예: regular/emergency)

> 자동 스크래핑은 보조 수단입니다. **가장 신뢰할 수 있는 방법은 공식 일정으로 CSV를 직접 만드는 것**입니다.

---

## 실행 방법

### 1) 기본 실행 (yfinance로 지수 다운로드 + 사용자 CSV)
```bash
python fomc_impact_analysis.py   --sp-source yfinance   --fomc-csv /path/to/your_fomc_dates.csv   --start 1990-01-01   --end 2025-12-31   --output-dir ./output
```

### 2) 모두 수동 파일로 실행 (오프라인 환경)
```bash
python fomc_impact_analysis.py   --sp-source csv   --sp-csv /path/to/sp500_daily.csv   --fomc-csv /path/to/your_fomc_dates.csv   --start 1990-01-01   --end 2025-12-31   --output-dir ./output
```

### 3) (선택) 자동 스크래핑으로 FOMC 날짜 추출 시도
```bash
python fomc_impact_analysis.py   --sp-source yfinance   --auto-scrape-fomc   --start 1990-01-01   --end 2025-12-31   --output-dir ./output
```
> 스크래핑은 연준 사이트 구조 변경에 취약하므로, 실패 시 **CSV를 직접 제공**하세요.

---

## 분석 산출물

- `output/fomc_event_windows.csv` — 각 FOMC 발표일 기준 **-1, 0, +1** 일 수익률/절대수익률
- `output/summary_by_regime.csv` — 레짐별 평균(수익률/절대수익률), 관측치, 표준편차, t-통계
- `output/mean_returns_by_regime_window.png` — 레짐×창(-1/0/+1) **평균 수익률** 바차트
- `output/mean_abs_returns_by_regime_window.png` — 레짐×창 **평균 절대수익률** 바차트
- `output/cumulative_excess_return_fomc_only.png` — FOMC(0일)만 연결한 **누적 수익률 곡선**

---

## 레짐(시기) 정의

- **Regime A**: 1994-01-01 ~ 1999-12-31 — 즉시성명 도입 초기
- **Regime B**: 2000-01-01 ~ 2007-12-31 — 정례화 확립(위기 전)
- **Regime C**: 2008-01-01 ~ 2012-12-31 — 금융위기/초저금리 전개
- **Regime D**: 2013-01-01 ~ 2019-12-31 — 정상화/포워드가이던스 고도화
- **Regime E**: 2020-01-01 ~ 현재 — 팬데믹/고금리 전환기

필요시 날짜 경계를 자유롭게 바꿔 실험하세요.

---

## 결과 해석 팁

- **발표일(0일) 평균 수익률**이 비발표일 대비 **유의미하게 크거나 작다면**, 성명문 공개가 직접적으로 가격 재평가를 촉발했을 가능성.
- **절대수익률(=변동성 proxy)**이 0일에 상대적으로 크면, 발표 자체가 **정보 이벤트**로 기능한다는 신호.
- **-1일 효과**(pre-FOMC drift)에 주의: 문헌상 1994년 이후 -1일 수익이 높은 경향이 보고됨.
- 시기별 차이는 **커뮤니케이션 제도 변화**(1994, 2000), **거시 환경**(2008, 2020) 등의 구조적 요인을 시사.

---

## 한계와 확장

- 본 스크립트는 **일별 종가 기준**으로, intraday(분/틱) 반응은 포착하지 못함.
- 개별 섹터/스타일(빅테크 vs 가치, 소형주 등), 채권/FX와의 동시반응, 옵션 IV(변동성 스마일) 등으로 확장 가능.
- 발표시각(ET 2:00/2:15) 반영을 원하면 고빈도 데이터로 교체하고 창을 재정의하세요.

---

## 참고(문헌 가이드)

- **Lucca, D. O., & Moench, E. (2015)**, *The Pre-FOMC Announcement Drift*, Journal of Finance.  
- **Cieslak, A., Morse, A., & Vissing-Jorgensen, A. (2019)**, *Stock Returns over the FOMC Cycle*, Journal of Finance.  
- 연준: FOMC 역사 자료, 회의 일정 및 성명문/의사록 페이지.

---

### CSV 템플릿(필수 컬럼)

- `date`: `YYYY-MM-DD` (예: 1994-02-04)  
- `type`: `regular` / `emergency` 등(임의 라벨)

템플릿 파일: [`fomc_dates_template.csv`](sandbox:/mnt/data/fomc_dates_template.csv)

