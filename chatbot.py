# --- 환경 변수 로드 ---
import os
from dotenv import load_dotenv
# Load environment variables from .env (if present)
load_dotenv()
# Respect existing settings; only set a default if missing
if not os.environ.get("LANGCHAIN_PROJECT"):
    os.environ["LANGCHAIN_PROJECT"] = "fomc-local"

# --- 라이브러리 임포트 ---
from typing import List, Dict
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from utils.rag_index import build_or_load_index, FAISS_DB_PATH_DEFAULT

# --- FAISS 인덱스 경로 ---
FAISS_DB_PATH = os.environ.get("FAISS_DB_PATH", FAISS_DB_PATH_DEFAULT)

# --- 벡터 스토어 생성/로드 ---
def setup_vector_store():
    # Basic sanity check for API key presence (LangChain will also validate)
    if not os.environ.get("OPENAI_API_KEY"):
        print("[WARN] OPENAI_API_KEY is not set. Please configure it in your .env.")
    try:
        max_docs = int(os.environ.get("FOMC_RAG_MAX_DOCS", "200"))
    except Exception:
        max_docs = 200
    return build_or_load_index(FAISS_DB_PATH, None, max_docs)

# --- RAG 체인 생성 ---
# 전역 변수로 체인 관리 (애플리케이션 컨텍스트 사용 권장)
retriever, prompt, llm = None, None, None

def get_rag_chain():
    global retriever, prompt, llm
    if not all([retriever, prompt, llm]):
        retriever, prompt, llm = create_rag_chain()
    return retriever, prompt, llm

def create_rag_chain():
    vectorstore = setup_vector_store()
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    template = """다음 문맥을 바탕으로 질문에 간단히 답하세요:

{context}

질문: {question}
"""
    prompt = ChatPromptTemplate.from_template(template)
    llm = ChatOpenAI(model="gpt-3.5-turbo-0125", max_tokens=200)

    return retriever, prompt, llm

# --- 질문 처리 ---
def answer_question(question: str, max_preview_chars: int = 200) -> Dict:
    retriever, prompt, llm = get_rag_chain()
    # 최신 방식: retriever.invoke
    docs = retriever.invoke(question)

    # context 합치기
    context_text = "\n\n".join([doc.page_content for doc in docs])
    input_prompt = prompt.format(context=context_text, question=question)

    # 최신 방식: llm.invoke
    answer_obj = llm.invoke(input_prompt)
    answer_text = getattr(answer_obj, 'content', None) or (answer_obj if isinstance(answer_obj, str) else str(answer_obj))

    documents_info = []
    for doc in docs:
        content_preview = doc.page_content[:max_preview_chars].replace("\n", " ")
        documents_info.append({
            "source": doc.metadata.get('source', "출처 정보 없음"),
            "content_preview": content_preview
        })

    return {"answer": answer_text, "documents": documents_info}

# --- 메인 실행 ---
if __name__ == "__main__":
    # 메인 실행 로직은 app.py로 이전하거나, 테스트용으로 유지
    questions = [
        "2011년 1월 보고서에 따르면 제조업 동향은 어땠나요?",
        "주택 시장은 어떻게 변했나요?"
    ]

    for q in questions:
        result = answer_question(q)
        print("=====================================================")
        print("질문:", q)
        print("-----------------------------------------------------")
        print("답변:", result["answer"])
        print("-----------------------------------------------------")
        print("출처:")
        for doc in result["documents"]:
            print(f" - {doc['source']}")
    print("=====================================================")