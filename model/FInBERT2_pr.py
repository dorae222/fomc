import pdfplumber
from transformers import BertTokenizer, BertForSequenceClassification
import torch
import re

# 모델 불러오기
from transformers import AutoTokenizer, AutoModelForSequenceClassification

model_name = "valuesimplex-ai-lab/FinBERT2-base"
tokenizer = AutoTokenizer.from_pretrained(model_name)

model = AutoModelForSequenceClassification.from_pretrained(
    model_name,
    num_labels=3  # 비둘기/중립/매파
)

# PDF 파일 열기
pdf_path = "data/FOMCpresconf20250730.pdf"  # 확장자 .pdf 두 번 안 붙이기
with pdfplumber.open(pdf_path) as pdf:
    text = ""
    for page in pdf.pages:
        text += page.extract_text() + "\n"

# 줄 단위로 분리
lines = text.splitlines()

# 이름 패턴 (간단 예시: 대문자로 시작하는 두 단어 이상)
name_pattern = re.compile(r"[A-Z][a-z]+\s[A-Z][a-z]+")

split_index = None
for i, line in enumerate(lines):
    if name_pattern.search(line):
        split_index = i
        break

if split_index is None:
    raise ValueError("사람 이름을 찾을 수 없음")

# 성명 부분 / 질의응답 부분 분리
statement_text = "\n".join(lines[:split_index])
qa_text = "\n".join(lines[split_index:])

print("성명 부분 미리보기:", statement_text[:300], "...")
print("Q&A 부분 미리보기:", qa_text[:300], "...")

# 긴 문장을 BERT 입력 크기(512 토큰)로 분할하는 함수
def chunk_text(text, tokenizer, max_length=512):
    tokens = tokenizer.encode(text, add_special_tokens=True)
    chunks = []
    for i in range(0, len(tokens), max_length-2):  # CLS/SEP 고려
        chunk = tokens[i:i+max_length-2]
        chunk = [tokenizer.cls_token_id] + chunk + [tokenizer.sep_token_id]
        chunks.append(chunk)
    return chunks

# 성명과 Q&A 각각 분할
statement_chunks = chunk_text(statement_text, tokenizer)
qa_chunks = chunk_text(qa_text, tokenizer)

print(f"성명 부분 chunk 개수: {len(statement_chunks)}")
print(f"Q&A 부분 chunk 개수: {len(qa_chunks)}")

# 각 chunk를 모델에 넣어 추론
def predict_chunks(chunks, tokenizer, model):
    preds = []
    for chunk in chunks:
        inputs = {
            "input_ids": torch.tensor([chunk]),
            "attention_mask": torch.tensor([[1]*len(chunk)])
        }
        with torch.no_grad():
            outputs = model(**inputs)
        logits = outputs.logits
        print("Logits:", logits)  # 모델 raw 출력
        print("Softmax probabilities:", torch.nn.functional.softmax(logits, dim=-1))  # 확률 분포 확인

        pred = torch.argmax(logits, dim=1).item()
        preds.append(pred)
    return preds

statement_preds = predict_chunks(statement_chunks, tokenizer, model)
qa_preds = predict_chunks(qa_chunks, tokenizer, model)

print("성명 부분 예측 결과:", statement_preds)
print("Q&A 부분 예측 결과:", qa_preds)
