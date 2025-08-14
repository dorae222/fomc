# FOMC

팀 토이 프로젝트 **FOMC** 저장소입니다.  
웹 서비스, 데이터 크롤러, 머신러닝 모델링을 **모노레포(Monorepo)** 구조로 관리합니다.

---

## 📌 프로젝트 개요
- **Web (webapp/)**  
  사용자 인터페이스 및 백엔드 API  

- **Crawler (crawler/)**  
  데이터 수집기 (웹 크롤링, API 수집 등)  

- **Model (model/)**  
  데이터 전처리, 머신러닝/딥러닝 모델 학습 및 실험  

---

## 📂 디렉터리 구조
```

fomc/
├─ webapp/          # 프론트엔드/백엔드 코드
├─ crawler/         # 크롤러 코드
├─ model/           # 모델 학습/평가 코드, 노트북
├─ data/            # 로컬 데이터 (gitignore 처리됨)
├─ .github/         # GitHub Actions, 이슈/PR 템플릿
└─ README.md

````

---

## 🌱 브랜치 전략
- **main**  
  배포 및 안정화된 코드만 유지  

- **develop**  
  기능 통합 및 테스트  

- **web / crawler / model**  
  역할별 장기 브랜치  

- **기능 브랜치 규칙**  
  - `web/feature-login-ui`  
  - `crawler/feature-news-crawl`  
  - `model/experiment-baseline`  

---

## 🔄 협업 워크플로우
1. 역할별 브랜치에서 최신 코드 가져오기  
   ```bash
   git checkout web
   git pull
   git checkout -b web/feature-xxx
   ```

2. 기능 개발 → 커밋 & 푸시

   ```bash
   git add .
   git commit -m "web: add login UI"
   git push -u origin web/feature-xxx
   ```
3. GitHub Pull Request 생성 → 리뷰 & CI 통과
4. 역할 브랜치 → develop → main 순서로 병합

---

## ⚙️ 개발 환경

### 공통

* **Git** (Windows: Git for Windows)
* **VS Code** (권장)
* **환경 변수 관리**: 각 폴더의 `.env` 파일 사용

  > `.env`는 `.gitignore`에 포함되어 있으므로 GitHub에 올라가지 않습니다.

---

### 🔵 Web (webapp/)

* **필수**: Node.js 20 LTS, npm
* **초기 설정**

  ```bash
  cd webapp
  npm install   # 의존성 설치
  ```
* **개발 서버 실행**

  ```bash
  npm run dev
  ```
* **빌드**

  ```bash
  npm run build
  ```
* **테스트**

  ```bash
  npm test
  ```

---

### 🟢 Crawler (crawler/)

* **필수**: Python 3.11
* **가상환경 생성 (Windows PowerShell)**

  ```powershell
  cd crawler
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```
* **실행 예시**

  ```powershell
  python src/news_crawler.py --date 2025-01-01
  ```

---

### 🟣 Model (model/)

* **필수**: Python 3.11, Jupyter Notebook (또는 VS Code Jupyter)
* **환경 설정**

  ```powershell
  cd model
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```
* **노트북 실행**

  ```powershell
  jupyter notebook
  ```
* **테스트 실행 (pytest 사용 시)**

  ```powershell
  pytest src/tests/
  ```

---

## 🚀 실행 예시 (빠른 시작)

```powershell
# 1. 레포 클론
git clone git@github.com:<org-or-user>/fomc.git
cd fomc

# 2. web 서버 실행
cd webapp
npm install
npm run dev

# 3. crawler 실행
cd ../crawler
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src/news_crawler.py

# 4. model 학습 실행
cd ../model
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
jupyter notebook
```

---

## 🛠️ 기여 가이드

* 모든 PR은 최소 1명 리뷰 후 머지
* 커밋 메시지 규칙:

  * `web: ...`, `crawler: ...`, `model: ...`
* CI 통과 필수 (`.github/workflows/ci.yml`)

