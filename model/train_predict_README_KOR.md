# FinBERT FOMC 기조 분석: 모델 학습 및 예측

이 문서는 커스텀 학습된 FinBERT 모델을 사용하여 FOMC 문서를 분석하는 2단계 프로세스를 설명합니다:
1.  **`train_fomc.py`**: 사전 학습된 FinBERT 모델을 FOMC 특화 데이터로 미세조정하여 전문 분류기를 생성합니다.
2.  **`predict.py`**: 새로 학습된 분류기를 사용하여 새로운 FOMC 문서의 기조(비둘기파, 중립, 매파)를 예측합니다.

---

## 1단계: 모델 학습 (`train_fomc.py`)

이 스크립트는 모델 미세조정의 전체 과정을 처리합니다. Hugging Face Hub에서 기반 언어 모델(`FinBERT2-base`)과 금융 벤치마크 데이터셋(`TheFinAI/finben-fomc`)을 다운로드하고, 이 데이터셋으로 모델을 학습시킨 후, 결과물인 특화 분류기를 로컬에 저장합니다.

### 사전 준비사항

필요한 라이브러리가 설치되어 있는지 확인하세요:

```bash
pip install transformers datasets evaluate torch
```

### 실행 방법

학습 과정을 시작하려면, 프로젝트 루트 디렉토리에서 다음 스크립트를 실행하기만 하면 됩니다. 이 스크립트는 미리 정의된 소스를 사용하므로 별도의 실행 인자가 필요 없습니다.

```bash
python model/train_fomc.py
```

**참고:** 모델 학습은 상당한 시간이 소요될 수 있으며, 최적의 성능을 위해 GPU가 장착된 환경이 권장됩니다.

### 결과물

학습이 성공적으로 완료되면, 프로젝트 루트에 `finbert2-fomc-classifier`라는 이름의 새 디렉토리가 생성됩니다. 이 디렉토리에는 미세조정된 모델과 토크나이저 파일이 포함되며, 이는 다음 예측 단계에서 필수적으로 사용됩니다.

---

## 2단계: 학습된 모델로 예측 (`predict.py`)

커스텀 모델 학습을 완료한 후, 이 스크립트를 사용하여 모든 FOMC 관련 PDF 문서를 분석할 수 있습니다.

### 사전 준비사항

예측에 필요한 라이브러리들을 설치했는지 확인하세요:

```bash
pip install torch transformers pandas pdfplumber
# (권장) 문장 분리기로 spaCy를 설치하세요:
pip install spacy
python -m spacy download en_core_web_sm
```

### 실행 방법

프로젝트 루트 디렉토리에서 스크립트를 실행하며, 분석하고자 하는 PDF 파일의 경로를 지정합니다. 스크립트는 1단계에서 생성된 모델을 자동으로 사용합니다.

**실행 예시:**

```bash
python model/predict.py --pdf path/to/your/fomc_document.pdf --output results/predictions.csv
```

# FOMC20250730
python model/predict.py --pdf data/FOMCpresconf20250730.pdf --output results/pred_20250730pres.csv

python model/predict.py --pdf data/monetary20250730a1.pdf --output results/pred_20250730mone.csv

python model/predict.py --pdf data/FOMCpresconf20250618.pdf --output results/pred_20250618pres.csv

python model/predict.py --pdf data/monetary20250618a1.pdf --output results/pred_20250618pres.csv

### 주요 실행 인자

*   `--pdf` (필수): 분석하고자 하는 입력 PDF 파일의 경로.
*   `--output`: 상세 예측 결과가 담긴 CSV 파일을 저장할 경로. (기본값: `predictions.csv`)
*   `--model_dir`: 학습된 모델이 위치한 디렉토리. (기본값: `./finbert2-fomc-classifier`)
*   `--mode`: PDF 텍스트를 분석을 위해 작은 단위로 나누는 방법. (기본값: `sentence_spacy`)
    *   `sentence_spacy`: (권장) spaCy 라이브러리를 사용하여 텍스트를 문장 단위로 정확하게 분리합니다.
    *   `chunk_slide`: 텍스트를 더 크고 겹치는 청크 단위로 분리합니다. 문장 구분이 명확하지 않은 긴 문단에 유용합니다.
*   `--threshold`: 예측 결과의 신뢰도를 판단하는 임계값. 예측 확률이 이 값보다 낮으면 '불확실(uncertain)'로 표시됩니다. (기본값: `0.6`)

### 결과물

1.  **콘솔 요약**: 스크립트는 문서에서 발견된 비둘기파, 중립, 매파적 발언의 비율을 보여주는 요약 정보를 콘솔에 출력합니다.
2.  **CSV 파일**: 지정된 출력 경로에 상세 결과 CSV 파일이 저장됩니다. 파일의 각 행은 문서의 한 문장(또는 청크)에 해당하며, 예측된 레이블, 예측 확률, 원본 텍스트 등의 정보를 포함합니다.
