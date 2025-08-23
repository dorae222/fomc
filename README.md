# FOMC

FOMC 텍스트/시계열 데이터를 수집·가공하고, Flask 기반 대시보드로 시각화하는 프로젝트입니다.

## 📚 문서 (docs/)
- docs/FOMC_Statement_Impact_Study.md — 성명서 영향 분석 정리
- docs/stance_explain.md — 스탠스 분류 기준 설명

## 📂 디렉터리 개요
```
app.py             # Flask 앱 엔트리포인트
config.py          # 환경/경로 설정
crawler/           # FOMC 원문/지표 수집 스크립트
database/          # DB 모델/초기화 코드
model/             # 분석/모델링 스크립트
static/            # CSS/JS/이미지
templates/         # Jinja 템플릿
utils/             # 데이터 처리/시각화/전처리 유틸
docs/              # 프로젝트 문서 모음
requirements.txt   # Python 의존성
run.sh             # 서버 실행 헬퍼 스크립트(옵션)
README.md          # 이 문서
```

## 🚀 빠른 시작 (Anaconda/conda, macOS)
Python 3.10+ 권장. 기본 실행은 `run.sh` 스크립트를 사용합니다.

```bash
# 1) conda 가상환경 생성 및 활성화
conda create -n fomc python=3.10 -y
conda activate fomc

# 2) 의존성 설치
pip install -U pip
pip install -r requirements.txt

# 3) .env 설정 (Chatbot 사용시 필수)
cp -n .env.example .env 2>/dev/null || cp .env.example .env
echo "OPENAI_API_KEY=<여기에_키_입력>" >> .env  # 이미 존재 시 이 줄은 무시하세요

# 4) 실행 (권장)
chmod +x run.sh  # 최초 1회만 필요할 수 있음
./run.sh

# 옵션
./run.sh --reset-db        # DB 초기화 후 실행
./run.sh --skip-quality    # 데이터 품질 검사 생략
./run.sh --skip-precompute # 프리컴퓨트 생략
./run.sh --host 0.0.0.0 --port 8000

# 서버 주소
open http://127.0.0.1:5000
```

수동 실행이 필요한 경우:

```bash
python setup_db.py   # (선택) 초기화
python app.py        # Flask 직접 실행
```

### 🤖 Chatbot 탭 사용 방법
- 네비게이션의 Chatbot 탭에서 질문을 입력하면, `crawler/fomc_files/**/*.md` 코퍼스를 기반으로 답변합니다.
- 최초 실행 시 임베딩 인덱스를 로컬(Chroma)로 생성/저장합니다. 시간이 조금 걸릴 수 있습니다.
- 환경변수 `OPENAI_API_KEY`가 필요합니다. `.env` 파일에 값을 넣어주세요.

## 🔐 환경 변수 및 OpenAI 키 관리 (.env)
이 프로젝트는 `python-dotenv`로 `.env` 파일을 자동 로드합니다. Chatbot 기능을 사용하려면 OpenAI API 키가 필요합니다.

1) 패키지 설치: `requirements.txt`에 포함되어 있으므로 별도 설치 없이 일괄 설치하면 됩니다.
2) `.env` 파일 생성:
	- 템플릿 복사: `.env.example` → `.env`
	- 값 채우기: `OPENAI_API_KEY=sk-...`
3) 서버 재시작 후 Chatbot 탭에서 질문을 입력하면 동작합니다.

참고: `.env`는 gitignore로 제외되어 저장소에 노출되지 않습니다.

참고:
- conda 환경에서 `sqlite` 패키지가 필요하면 `conda install -c conda-forge sqlite`로 설치할 수 있습니다.
- `./run.sh` 실행 시 권한 오류가 나면 `chmod +x run.sh` 실행 후 다시 시도하세요.

## 🚀 빠른 시작 (Windows, PowerShell)
Windows 기본 셸에서는 `run.sh` 대신 아래 수동 실행 절차를 사용하세요. (WSL/Ubuntu 환경에서는 `./run.sh` 사용 가능)

```powershell
# 1) conda 가상환경
conda create -n fomc python=3.10 -y
conda activate fomc

# 2) 의존성 설치
python -m pip install -U pip
# requirements.txt 설치 (sqlite3 줄에서 오류 발생 시 해당 줄을 삭제 후 다시 시도)
pip install -r requirements.txt

# 3) (선택) DB 초기화/적재
python setup_db.py

# 4) 서버 실행
python app.py

# 브라우저에서 열기
start "" http://localhost:5000
```

팁:
- `conda init powershell`로 PowerShell에 conda를 등록할 수 있습니다.

## 🚀 빠른 시작 (Linux)

```bash
# 1) conda 가상환경
conda create -n fomc python=3.10 -y
conda activate fomc

# 2) 의존성 설치 (sqlite3 제외 권장)
pip install -U pip
grep -v '^sqlite3' requirements.txt | pip install -r /dev/stdin

# 3) 실행 방법 A: run.sh (권장)
chmod +x run.sh
./run.sh --host 0.0.0.0 --port 5000

# 실행 방법 B: 수동 실행
python setup_db.py   # (선택)
python app.py

# 브라우저에서 열기
xdg-open http://127.0.0.1:5000 || true
```

참고:
- conda를 셸에 등록하려면 `conda init bash` 후 터미널을 재시작하세요.
- 일부 배포판에서 `./run.sh` 실행 시 `env: zsh: No such file or directory` 오류가 나면, 수동 실행 방법을 사용하세요.

## 주요 기능
- 대시보드: 요약 지표, 차트, 타임라인, 회의 간 비교
- API: `/api/summary`, `/api/overview`, `/api/meeting/<date>`, `/api/compare` 등
- 사전 계산: 앱 시작 시 감성 집계 및 최근 비교 페어 프리컴퓨트

## 개발 메모
- 환경변수는 `.env`(옵션) 또는 `config.py`로 관리
- 장기 계산은 백그라운드 스레드로 처리 (앱 최초 요청 시 트리거)
- OneDrive 경로 사용 시 대용량 파일 동기화 지연에 유의

## 기여
- PR 1인 이상 리뷰 후 머지
- 커밋 메시지 접두어 권장: `app: ...`, `crawler: ...`, `model: ...`

