# --- 환경 변수 로드 ---
import os
from dotenv import load_dotenv
# load_dotenv()
os.environ["LANGCHAIN_PROJECT"] = "RAG TUTORIAL"

# --- 라이브러리 임포트 ---
from typing import List, Dict
from langchain_community.document_loaders import DirectoryLoader, UnstructuredMarkdownLoader
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from tqdm import tqdm

# --- FAISS 인덱스 경로 ---
FAISS_DB_PATH = "fomc_faiss_index"

# --- 벡터 스토어 생성/로드 ---
def setup_vector_store():
    embeddings = OpenAIEmbeddings()

    if os.path.exists(FAISS_DB_PATH):
        print("[INFO] FAISS 인덱스 파일이 이미 존재합니다. 불러옵니다...")
        vectorstore = FAISS.load_local(FAISS_DB_PATH, embeddings, allow_dangerous_deserialization=True)
    else:
        print("[INFO] FAISS 인덱스 파일이 존재하지 않습니다. 새로 구축합니다...")
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        DATA_DIR = os.path.join(BASE_DIR, "fomc_files")

        loader = DirectoryLoader(
            DATA_DIR,
            glob="**/*.md",
            loader_cls=UnstructuredMarkdownLoader
        )
        docs = list(tqdm(loader.load(), desc="문서 로딩 중"))

        # 테스트용: 일부 문서만 사용
        # docs = docs[:20]

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=100
        )
        splits = list(tqdm(text_splitter.split_documents(docs), desc="문서 분할 중"))

        vectorstore = FAISS.from_documents(splits, embeddings)
        vectorstore.save_local(FAISS_DB_PATH)
        print("[INFO] FAISS 인덱스 파일이 성공적으로 저장되었습니다.")

    return vectorstore

# --- RAG 체인 생성 ---
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
def answer_question(question: str, retriever, prompt, llm, max_preview_chars: int = 200) -> Dict:
    # 최신 방식: retriever.invoke
    docs = retriever.invoke(question)

    # context 합치기
    context_text = "\n\n".join([doc.page_content for doc in docs])
    input_prompt = prompt.format(context=context_text, question=question)

    # 최신 방식: llm.invoke
    answer = llm.invoke(input_prompt)

    documents_info = []
    for doc in docs:
        content_preview = doc.page_content[:max_preview_chars].replace("\n", " ")
        documents_info.append({
            "source": doc.metadata.get('source', "출처 정보 없음"),
            "content_preview": content_preview
        })

    return {"answer": answer, "documents": documents_info}

# --- 메인 실행 ---
if __name__ == "__main__":
    retriever, prompt, llm = create_rag_chain()

    questions = [
        "2011년 1월 보고서에 따르면 제조업 동향은 어땠나요?",
        "주택 시장은 어떻게 변했나요?"
    ]

    for q in questions:
        result = answer_question(q, retriever, prompt, llm)
        print("=====================================================")
        print("질문:", q)
        print("-----------------------------------------------------")
        print("답변:", result["answer"])
        print("-----------------------------------------------------")
        print("출처:")
        for doc in result["documents"]:
            print(f" - {doc['source']}")
    print("=====================================================")
