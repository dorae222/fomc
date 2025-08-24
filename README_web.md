# `generate_comparisons.py` Documentation

This script automates the generation of a web-based interface to analyze and compare FOMC statement (`mone`) and press conference (`pres`) sentiment analysis results. It compares consecutive statements, generates individual pages for press conferences, and critically, annotates market reaction plots based on a set of rules.

## Purpose

The primary goal is to visually correlate the change in FOMC sentiment with the market's reaction. The script creates a static website that presents:
1.  Side-by-side comparisons of FOMC statements (`mone` files) between two consecutive dates.
2.  Individual analysis pages for each press conference (`pres` files).
3.  Annotated charts that quickly show whether the market's movement aligned with the script's sentiment-based prediction.

## File Structure (Inputs)

The script requires a specific directory structure and input files to function correctly.

-   **Sentiment Predictions (`predicted/`)**:
    -   `predicted/txt_pred/`: A primary directory for prediction CSVs (e.g., `pred_20240731_mone.csv`).
    -   `predicted/statement_txt/`: Optional, dedicated directory for statement (`mone`) predictions.
    -   `predicted/blocks_pres_txt/`: Optional, dedicated directory for press conference (`pres`) predictions.
    -   `predicted/csv/`: Optional, for 1-hour market data CSVs.
    -   Each prediction CSV should contain at a minimum a column for the predicted label (`pred_label`) and the prediction probability (`max_prob`).

-   **Market Data (`results/csv/`)**:
    -   Contains 1-hour (1h) market data files in CSV format (e.g., `QQQ_1h_2023-09-20_ET.csv`).
    -   These files are crucial for the plot annotation logic. The script robustly finds the 'Close' price, even with varying column names.

-   **Plot Images (`results/plots/`)**:
    -   Contains the original, non-annotated plot images (e.g., `QQQ_1h_2024-07-31_with_sentiment.png`).

## Execution

To run the script, simply execute it from the project's root directory:

```bash
python3 generate_comparisons.py
```

The script will automatically scan the input directories, process the files, and generate the web output.

## Output

The script generates a self-contained website in the `web/` directory.

-   **`web/index.html`**: The main entry point, linking to all comparison and press conference pages.
-   **`web/style.css`**: Basic styling for the generated pages.
-   **`web/comparisons/`**: Contains HTML files comparing two `mone` statements (e.g., `compare_20240612_to_20240731_mone.html`).
-   **`web/pres/`**: Contains HTML files for each `pres` conference (e.g., `pres_20240731.html`).
-   **`web/plots/`**: The script copies the original plots from `results/plots/` here and then **overlays annotations** on them.

## Plot Annotation Logic

This is the core analytical feature of the script. For each press conference, the script performs the following steps:

1.  **Calculate Hawk-Share**: It computes a probability-weighted "hawk-share" for both the statement (`mone`) and the press conference (`pres`) using the `max_prob` values from the prediction CSVs.
    -   `hawk_share = sum(max_prob for hawkish predictions) / sum(max_prob for all predictions)`

2.  **Analyze Market Movement**: It reads the corresponding 1-hour market data CSV and finds the closing price for the last two hours of the session.

3.  **Apply Rules and Annotate**: It applies a coloring rule based on the comparison between sentiment change and market reaction:
    -   **GREEN (Correct Prediction)**:
        -   If the press conference was **more hawkish** than the statement (`press_score > stmt_score`) AND the market **went down** (`change < 0`).
        -   OR
        -   If the press conference was **less hawkish** than the statement (`press_score < stmt_score`) AND the market **went up** (`change > 0`).
    -   **RED (Incorrect Prediction)**: All other cases.

The script then uses the Pillow library to draw a colored band and a line on the plot image in `web/plots/` to visually represent this outcome, providing an at-a-glance summary of the model's predictive success for that date.


---

# `generate_comparisons.py` 문서

이 스크립트는 FOMC 성명서(`mone`)와 기자회견(`pres`)의 감성 분석 결과를 분석하고 비교하는 웹 기반 인터페이스 생성을 자동화합니다. 연속적인 성명서를 비교하고, 기자회견별 개별 페이지를 생성하며, 규칙에 따라 시장 반응 플롯에 주석을 추가하는 중요한 기능을 수행합니다.

## 목적

주요 목표는 FOMC 감성 변화와 시장 반응을 시각적으로 연관시키는 것입니다. 이 스크립트는 다음을 제공하는 정적 웹사이트를 생성합니다:
1.  두 연속 날짜 사이의 FOMC 성명서(`mone` 파일) 비교.
2.  각 기자회견(`pres` 파일)에 대한 개별 분석 페이지.
3.  스크립트의 감성 기반 예측과 시장 움직임이 일치했는지를 빠르게 보여주는 주석이 달린 차트.

## 파일 구조 (입력)

스크립트가 올바르게 작동하려면 특정 디렉토리 구조와 입력 파일이 필요합니다.

-   **감성 예측 (`predicted/`)**:
    -   `predicted/txt_pred/`: 예측 CSV를 위한 기본 디렉토리 (예: `pred_20240731_mone.csv`).
    -   `predicted/statement_txt/`: 성명서(`mone`) 예측을 위한 선택적 전용 디렉토리.
    -   `predicted/blocks_pres_txt/`: 기자회견(`pres`) 예측을 위한 선택적 전용 디렉토리.
    -   `predicted/csv/`: 1시간 단위 시장 데이터 CSV를 위한 선택적 디렉토리.
    -   각 예측 CSV에는 최소한 예측된 레이블(`pred_label`)과 예측 확률(`max_prob`) 열이 포함되어야 합니다.

-   **시장 데이터 (`results/csv/`)**:
    -   1시간(1h) 시장 데이터 CSV 파일 포함 (예: `QQQ_1h_2023-09-20_ET.csv`).
    -   이 파일들은 플롯 주석 로직에 매우 중요합니다. 스크립트는 다양한 열 이름에도 불구하고 'Close' 가격을 안정적으로 찾아냅니다.

-   **플롯 이미지 (`results/plots/`)**:
    -   원본, 주석 없는 플롯 이미지 포함 (예: `QQQ_1h_2024-07-31_with_sentiment.png`).

## 실행

스크립트를 실행하려면 프로젝트의 루트 디렉토리에서 다음을 실행하십시오:

```bash
python3 generate_comparisons.py
```

스크립트는 자동으로 입력 디렉토리를 스캔하고, 파일을 처리하며, 웹 결과물을 생성합니다.

## 출력

스크립트는 `web/` 디렉토리에 독립적인 웹사이트를 생성합니다.

-   **`web/index.html`**: 모든 비교 및 기자회견 페이지로 연결되는 기본 진입점.
-   **`web/style.css`**: 생성된 페이지를 위한 기본 스타일링.
-   **`web/comparisons/`**: 두 `mone` 성명서를 비교하는 HTML 파일 포함 (예: `compare_20240612_to_20240731_mone.html`).
-   **`web/pres/`**: 각 `pres` 기자회견용 HTML 파일 포함 (예: `pres_20240731.html`).
-   **`web/plots/`**: 스크립트는 `results/plots/`의 원본 플롯을 여기에 복사한 다음 그 위에 **주석을 오버레이합니다**.

## 플롯 주석 로직

이것은 스크립트의 핵심 분석 기능입니다. 각 기자회견에 대해 스크립트는 다음 단계를 수행합니다:

1.  **Hawk-Share 계산**: 예측 CSV의 `max_prob` 값을 사용하여 성명서(`mone`)와 기자회견(`pres`) 모두에 대해 확률 가중 "hawk-share"를 계산합니다.
    -   `hawk_share = 매파적 예측의 max_prob 합계 / 모든 예측의 max_prob 합계`

2.  **시장 움직임 분석**: 해당 1시간 시장 데이터 CSV를 읽고 세션의 마지막 2시간 동안의 종가를 찾습니다.

3.  **규칙 적용 및 주석**: 감성 변화와 시장 반응 간의 비교를 기반으로 색상 규칙을 적용합니다:
    -   **GREEN (예측 성공)**:
        -   기자회견이 성명서보다 **더 매파적**(`press_score > stmt_score`)이고 시장이 **하락**(`change < 0`)한 경우.
        -   또는
        -   기자회견이 성명서보다 **덜 매파적**(`press_score < stmt_score`)이고 시장이 **상승**(`change > 0`)한 경우.
    -   **RED (예측 실패)**: 그 외 모든 경우.

그런 다음 스크립트는 Pillow 라이브러리를 사용하여 `web/plots/`의 플롯 이미지에 색상 밴드와 선을 그려 이 결과를 시각적으로 나타내고, 해당 날짜에 대한 모델의 예측 성공 여부를 한눈에 요약하여 보여줍니다.