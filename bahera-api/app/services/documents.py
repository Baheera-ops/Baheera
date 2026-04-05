"""
Document processing pipeline for the RAG knowledge base.
Extracts text from PDFs, chunks it, generates embeddings, stores in pgvector.

Pipeline: Upload → Extract → Chunk → Embed → Store
"""

import logging
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.models import Document, DocumentStatus, KnowledgeBaseEmbedding

logger = logging.getLogger("bahera.documents")
settings = get_settings()


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF using pypdf."""
    import io
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())
    return "\n\n".join(pages)


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[dict]:
    """
    Split text into overlapping chunks for embedding.
    
    Strategy:
    - Split on paragraph boundaries first (double newline)
    - If a paragraph exceeds chunk_size tokens, split on sentences
    - Maintain overlap for context continuity across chunks
    
    Returns list of {"text": str, "index": int, "char_count": int}
    """
    import tiktoken

    encoder = tiktoken.encoding_for_model("gpt-4o-mini")

    # Split into paragraphs
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current_chunk = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = len(encoder.encode(para))

        if current_tokens + para_tokens > chunk_size and current_chunk:
            # Flush current chunk
            chunk_text_str = "\n\n".join(current_chunk)
            chunks.append({
                "text": chunk_text_str,
                "index": len(chunks),
                "char_count": len(chunk_text_str),
            })

            # Keep overlap: take the last paragraph as the start of the next chunk
            if chunk_overlap > 0 and current_chunk:
                last = current_chunk[-1]
                last_tokens = len(encoder.encode(last))
                if last_tokens <= chunk_overlap:
                    current_chunk = [last]
                    current_tokens = last_tokens
                else:
                    current_chunk = []
                    current_tokens = 0
            else:
                current_chunk = []
                current_tokens = 0

        # Handle paragraphs that are themselves too large
        if para_tokens > chunk_size:
            sentences = para.replace(". ", ".\n").split("\n")
            for sentence in sentences:
                s_tokens = len(encoder.encode(sentence))
                if current_tokens + s_tokens > chunk_size and current_chunk:
                    chunk_text_str = "\n\n".join(current_chunk)
                    chunks.append({
                        "text": chunk_text_str,
                        "index": len(chunks),
                        "char_count": len(chunk_text_str),
                    })
                    current_chunk = []
                    current_tokens = 0
                current_chunk.append(sentence)
                current_tokens += s_tokens
        else:
            current_chunk.append(para)
            current_tokens += para_tokens

    # Flush remaining
    if current_chunk:
        chunk_text_str = "\n\n".join(current_chunk)
        chunks.append({
            "text": chunk_text_str,
            "index": len(chunks),
            "char_count": len(chunk_text_str),
        })

    return chunks


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of text chunks using OpenAI."""
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    # OpenAI embedding API supports batching (up to 2048 inputs)
    response = await client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=texts,
    )

    return [item.embedding for item in response.data]


async def process_document(
    db: AsyncSession,
    document_id: UUID,
    pdf_bytes: bytes,
) -> int:
    """
    Full pipeline: extract → chunk → embed → store.
    Returns the number of chunks created.
    
    Call this from a background task or task queue.
    """
    # Load the document record
    from sqlalchemy import select
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        logger.error(f"Document {document_id} not found")
        return 0

    try:
        # Step 1: Update status to processing
        doc.processing_status = DocumentStatus.PROCESSING
        await db.flush()

        # Step 2: Extract text
        logger.info(f"Extracting text from {doc.file_name}")
        text = extract_text_from_pdf(pdf_bytes)
        if not text:
            doc.processing_status = DocumentStatus.FAILED
            await db.flush()
            return 0

        doc.extracted_text = text

        # Step 3: Chunk
        logger.info(f"Chunking {len(text)} chars into segments")
        chunks = chunk_text(text, chunk_size=500, chunk_overlap=50)
        logger.info(f"Created {len(chunks)} chunks")

        # Step 4: Generate embeddings
        doc.processing_status = DocumentStatus.EMBEDDING
        await db.flush()

        chunk_texts = [c["text"] for c in chunks]

        # Process in batches of 100 to avoid API limits
        all_embeddings = []
        batch_size = 100
        for i in range(0, len(chunk_texts), batch_size):
            batch = chunk_texts[i:i + batch_size]
            embeddings = await generate_embeddings(batch)
            all_embeddings.extend(embeddings)

        # Step 5: Store in knowledge_base_embeddings
        for chunk, embedding in zip(chunks, all_embeddings):
            kbe = KnowledgeBaseEmbedding(
                document_id=doc.id,
                property_id=doc.property_id,
                agency_id=doc.agency_id,
                chunk_index=chunk["index"],
                content_text=chunk["text"],
                content_length=chunk["char_count"],
                embedding=embedding,
                chunk_metadata={
                    "source_file": doc.file_name,
                    "chunk_of": len(chunks),
                },
            )
            db.add(kbe)

        # Step 6: Mark complete
        doc.processing_status = DocumentStatus.COMPLETED
        doc.chunk_count = len(chunks)
        from datetime import datetime
        doc.processed_at = datetime.utcnow()
        await db.flush()

        logger.info(f"Document {doc.file_name}: {len(chunks)} chunks embedded successfully")
        return len(chunks)

    except Exception as e:
        logger.exception(f"Document processing failed: {e}")
        doc.processing_status = DocumentStatus.FAILED
        await db.flush()
        return 0
