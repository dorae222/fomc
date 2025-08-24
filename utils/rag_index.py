import os
import sys
import argparse
import logging
from typing import List, Optional, Sequence, Tuple

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover - tqdm is optional at runtime
    def tqdm(x, **kwargs):
        return x


FAISS_DB_PATH_DEFAULT = "fomc_faiss_index"


def get_data_dir(base: Optional[str] = None) -> str:
    """Best-effort discovery of the repository's FOMC text directory."""
    base_dir = base or os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(base_dir)
    candidates = [
        os.path.join(repo_root, "crawler", "fomc_files"),
        os.path.join(os.path.dirname(repo_root), "crawler", "fomc_files"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


def _load_docs(data_dir: str, patterns: Sequence[str], quiet: bool = False) -> List:
    docs: List = []
    for pat in patterns:
        try:
            loader = DirectoryLoader(data_dir, glob=pat, loader_cls=TextLoader)
            docs.extend(loader.load())
        except Exception as e:
            logging.getLogger(__name__).debug(f"Skip pattern {pat}: {e}")
    return list(tqdm(docs, desc="문서 로딩 중", disable=quiet))


def build_or_load_index(
    faiss_path: str = FAISS_DB_PATH_DEFAULT,
    data_dir: Optional[str] = None,
    max_docs: int = 0,  # 0 for unlimited
    chunk_size: int = 500,
    chunk_overlap: int = 100,
    patterns: Sequence[str] = ("**/*.md", "**/*.txt"),
    quiet: bool = False,
    rebuild: bool = False,
):
    """Build or load a FAISS index for the FOMC RAG corpus.

    Parameters
    - faiss_path: Directory for FAISS index.
    - data_dir: Root directory for documents; auto-discovered if None.
    - max_docs: Cap number of documents for initial index build (0 to disable).
    - chunk_size / chunk_overlap: Text splitter settings.
    - patterns: Glob patterns to include.
    - quiet: Disable progress bars/log noise.
    - rebuild: Force rebuild even if index exists.
    """
    log = logging.getLogger(__name__)

    # Ensure API key presence before embedding
    if not os.environ.get("OPENAI_API_KEY"):
        log.error("OPENAI_API_KEY not set. Please set it in your environment or .env file.")
        raise RuntimeError("OPENAI_API_KEY not set.")

    if os.path.exists(faiss_path) and not rebuild:
        if not quiet:
            log.info(f"Loading existing FAISS index from: {faiss_path}")
        try:
            return FAISS.load_local(faiss_path, OpenAIEmbeddings(), allow_dangerous_deserialization=True)
        except Exception as e:
            log.warning(f"Failed to load index, will rebuild: {e}")

    data_dir = data_dir or get_data_dir()
    log.info(f"Building FAISS index at {faiss_path} from {data_dir}")

    docs = _load_docs(data_dir, patterns, quiet=quiet)
    if not docs:
        log.warning("No documents found. Creating an empty placeholder index.")
        # Create and save an empty index
        placeholder_vs = FAISS.from_texts(["Knowledge base is empty."], OpenAIEmbeddings())
        placeholder_vs.save_local(faiss_path)
        return placeholder_vs

    if max_docs > 0:
        docs = docs[:max_docs]
    log.info(f"Loaded {len(docs)} documents (cap={'all' if max_docs == 0 else max_docs})")

    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    splits = list(tqdm(splitter.split_documents(docs), desc="Splitting documents", disable=quiet))
    log.info(f"Split into {len(splits)} chunks (chunk_size={chunk_size}, overlap={chunk_overlap})")

    log.info("Embedding documents and building FAISS index...")
    vs = FAISS.from_documents(splits, OpenAIEmbeddings())
    
    log.info(f"Saving FAISS index to {faiss_path}...")
    vs.save_local(faiss_path)
    log.info("FAISS index saved successfully.")
    return vs


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prebuild or load FAISS index for FOMC RAG")
    p.add_argument("--faiss-path", default=os.environ.get("FAISS_DB_PATH", FAISS_DB_PATH_DEFAULT), help="Path to FAISS index dir")
    p.add_argument("--data-dir", default=os.environ.get("FOMC_RAG_DATA_DIR"), help="Root dir for documents (auto if omitted)")
    p.add_argument("--max-docs", type=int, default=int(os.environ.get("FOMC_RAG_MAX_DOCS", "0")), help="Max documents to index (0=all)")
    p.add_argument("--chunk-size", type=int, default=500, help="Chunk size for splitting")
    p.add_argument("--chunk-overlap", type=int, default=100, help="Chunk overlap for splitting")
    p.add_argument("--patterns", default="**/*.md,**/*.txt", help="Comma-separated globs for files")
    p.add_argument("--rebuild", action="store_true", help="Force rebuild even if index exists")
    p.add_argument("--quiet", action="store_true", help="Reduce output and hide progress bars")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    from dotenv import load_dotenv
    load_dotenv()

    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO if not args.quiet else logging.WARNING, format="%(levelname)s:%(name)s:%(message)s")
    patterns: Tuple[str, ...] = tuple([p.strip() for p in args.patterns.split(',') if p.strip()])

    try:
        build_or_load_index(
            faiss_path=args.faiss_path,
            data_dir=args.data_dir,
            max_docs=args.max_docs,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            patterns=patterns,
            quiet=args.quiet,
            rebuild=args.rebuild,
        )
        return 0
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to build/load index: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
