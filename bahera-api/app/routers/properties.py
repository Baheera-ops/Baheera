"""
Properties router: CRUD for property listings + document upload for RAG knowledge base.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agency_id
from app.models.models import Document, DocumentStatus, KnowledgeBaseEmbedding, Property

router = APIRouter(prefix="/properties", tags=["Properties"])


# ── Schemas ──────────────────────────────────────────────────────────

class PropertyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    location: str = Field(min_length=2, max_length=255)
    property_type: str
    bedrooms_min: int | None = None
    bedrooms_max: int | None = None
    price_from: float
    price_to: float | None = None
    currency: str = "AED"
    payment_plan: str | None = None
    handover_date: str | None = None
    amenities: list[str] = []
    developer_id: UUID | None = None

class PropertyUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    price_from: float | None = None
    price_to: float | None = None
    payment_plan: str | None = None
    is_active: bool | None = None
    amenities: list[str] | None = None

class PropertyResponse(BaseModel):
    id: UUID
    agency_id: UUID
    name: str
    location: str
    property_type: str
    bedrooms_min: int | None
    bedrooms_max: int | None
    price_from: float
    price_to: float | None
    currency: str
    payment_plan: str | None
    amenities: list | dict
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class DocumentResponse(BaseModel):
    id: UUID
    file_name: str
    file_type: str
    processing_status: str
    chunk_count: int
    uploaded_at: datetime

    class Config:
        from_attributes = True


# ── Property CRUD ────────────────────────────────────────────────────

@router.get("", response_model=list[PropertyResponse])
async def list_properties(
    is_active: bool = Query(True),
    property_type: str = Query(None),
    location: str = Query(None),
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    query = select(Property).where(Property.agency_id == agency_id)
    if is_active is not None:
        query = query.where(Property.is_active == is_active)
    if property_type:
        query = query.where(Property.property_type == property_type)
    if location:
        query = query.where(Property.location.ilike(f"%{location}%"))
    query = query.order_by(Property.created_at.desc())

    result = await db.execute(query)
    return [PropertyResponse.model_validate(p) for p in result.scalars().all()]


@router.post("", response_model=PropertyResponse, status_code=201)
async def create_property(
    body: PropertyCreate,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    prop = Property(
        agency_id=agency_id,
        **body.model_dump(exclude={"handover_date"}),
    )
    db.add(prop)
    await db.flush()
    return PropertyResponse.model_validate(prop)


@router.patch("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: UUID,
    body: PropertyUpdate,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Property).where(Property.id == property_id, Property.agency_id == agency_id)
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    await db.flush()
    return PropertyResponse.model_validate(prop)


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: UUID,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Property).where(Property.id == property_id, Property.agency_id == agency_id)
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return PropertyResponse.model_validate(prop)


# ── Document Upload (Knowledge Base) ─────────────────────────────────

@router.post("/{property_id}/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    property_id: UUID,
    file: UploadFile = File(...),
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a PDF/document for the property knowledge base.
    The file is stored, then processed asynchronously:
      1. Text extraction (PyPDF2)
      2. Chunking (500 tokens, 50 overlap)
      3. Embedding (text-embedding-3-small)
      4. Storage in knowledge_base_embeddings

    For MVP, processing happens inline. In production, push to a task queue.
    """
    # Validate property exists
    result = await db.execute(
        select(Property).where(Property.id == property_id, Property.agency_id == agency_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Property not found")

    # Validate file type
    allowed_types = {"application/pdf", "text/plain", "text/csv"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"File type not supported. Allowed: {allowed_types}")

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Determine file type
    extension = file.filename.rsplit(".", 1)[-1].lower() if file.filename else "pdf"

    # Store document record (file goes to Supabase Storage in production)
    storage_path = f"documents/{agency_id}/{property_id}/{file.filename}"

    doc = Document(
        agency_id=agency_id,
        property_id=property_id,
        file_name=file.filename or "uploaded_file",
        file_type=extension,
        storage_path=storage_path,
        file_size_bytes=file_size,
        processing_status=DocumentStatus.UPLOADED,
    )
    db.add(doc)
    await db.flush()

    # TODO: In production, trigger async processing via task queue:
    #   - Extract text from PDF
    #   - Chunk into 500-token segments
    #   - Generate embeddings via OpenAI
    #   - Store in knowledge_base_embeddings table
    #
    # For MVP, this can be done inline with a background task:
    # background_tasks.add_task(process_document, doc.id, content)

    return DocumentResponse.model_validate(doc)


@router.get("/{property_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    property_id: UUID,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """List all uploaded documents for a property."""
    result = await db.execute(
        select(Document)
        .where(Document.property_id == property_id, Document.agency_id == agency_id)
        .order_by(Document.uploaded_at.desc())
    )
    return [DocumentResponse.model_validate(d) for d in result.scalars().all()]


@router.delete("/{property_id}/documents/{document_id}", status_code=204)
async def delete_document(
    property_id: UUID,
    document_id: UUID,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and its embeddings."""
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.property_id == property_id,
            Document.agency_id == agency_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.delete(doc)  # Cascades to embeddings via FK


# ── Knowledge Base Search (used by chatbot) ──────────────────────────

@router.post("/search")
async def search_knowledge_base(
    query: str = Query(..., min_length=2),
    property_id: UUID = Query(None),
    limit: int = Query(5, ge=1, le=10),
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Vector similarity search across the knowledge base.
    Used by the chatbot when answering property questions.
    """
    from openai import AsyncOpenAI
    from app.config import get_settings

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    # Generate query embedding
    embedding_resp = await client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=query,
    )
    query_embedding = embedding_resp.data[0].embedding

    # Search via pgvector cosine similarity
    from sqlalchemy import text as sql_text

    sql = sql_text("""
        SELECT
            kbe.id,
            kbe.content_text,
            kbe.chunk_metadata,
            kbe.property_id,
            p.name AS property_name,
            p.location,
            1 - (kbe.embedding <=> :embedding::vector) AS similarity
        FROM knowledge_base_embeddings kbe
        JOIN properties p ON p.id = kbe.property_id
        WHERE kbe.agency_id = :agency_id
          AND (:property_id IS NULL OR kbe.property_id = :property_id)
          AND 1 - (kbe.embedding <=> :embedding::vector) > 0.65
        ORDER BY kbe.embedding <=> :embedding::vector
        LIMIT :limit
    """)

    result = await db.execute(sql, {
        "agency_id": agency_id,
        "property_id": str(property_id) if property_id else None,
        "embedding": str(query_embedding),
        "limit": limit,
    })

    rows = result.mappings().all()
    return [
        {
            "content": row["content_text"],
            "property_name": row["property_name"],
            "location": row["location"],
            "similarity": round(float(row["similarity"]), 3),
            "metadata": row["chunk_metadata"],
        }
        for row in rows
    ]
