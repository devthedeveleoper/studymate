import uuid
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.core.security import current_active_user
from app.models.user import User
from app.models.document import Document, DocumentStatus
from app.models.chunk import DocumentChunk
from app.schemas.study import FlashcardResponse, SummaryResponse, Flashcard
from app.routers.documents import get_ai_provider
from app.core.valkey import get_cache, set_cache

router = APIRouter(prefix="/study", tags=["study"])

FLASHCARD_PROMPT = """Generate flashcards from the following study material.
Create between 5 and 15 flashcards depending on the amount of content.
Each flashcard should have a clear question and a concise but complete answer.

Return your response as a JSON object with this exact structure:
{
    "flashcards": [
        {"question": "...", "answer": "..."},
        {"question": "...", "answer": "..."}
    ]
}"""

SUMMARY_PROMPT = """Summarize the following study material.
Write a comprehensive summary that covers the main topics and concepts.
Also extract 3-7 key points that are most important to remember.

Return your response as a JSON object with this exact structure:
{
    "summary": "Your comprehensive summary here...",
    "key_points": [
        "First key point",
        "Second key point"
    ]
}"""


@router.post("/{document_id}/flashcards", response_model=FlashcardResponse)
async def generate_flashcards(
    document_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Generate flashcards from a document's content.
    Uses the AI provider to create Q&A pairs based on the document's chunks.
    """
    chunks = await _get_document_chunks(document_id, user.id, session)
    # Check cache first
    cache_key = f"flashcards:{document_id}"
    cached_data = await get_cache(cache_key)
    if cached_data:
        flashcards = [Flashcard(**fc) for fc in cached_data]
        return FlashcardResponse(
            flashcards=flashcards,
            document_id=str(document_id),
        )

    provider = get_ai_provider()
    chunk_texts = [c.content for c in chunks]
    
    # TRUNCATION: Prevent massive documents from exceeding free tier TPM limits (e.g., Groq's 12k TPM limit)
    # We'll limit the input to roughly 25,000 characters (~6,000 tokens) to be safe.
    combined_text = "\n\n".join(chunk_texts)
    if len(combined_text) > 25000:
        combined_text = combined_text[:25000] + "\n\n...[Document truncated due to size limits]..."
        
    raw = await provider.generate_structured(FLASHCARD_PROMPT, [combined_text])

    try:
        data = json.loads(raw)
        flashcards = [Flashcard(**fc) for fc in data.get("flashcards", [])]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse AI response into flashcards: {e}",
        )

    # Save to cache (24 hours expiration)
    await set_cache(cache_key, [fc.model_dump() for fc in flashcards], expire_seconds=86400)

    return FlashcardResponse(
        flashcards=flashcards,
        document_id=str(document_id),
    )


@router.post("/{document_id}/summary", response_model=SummaryResponse)
async def generate_summary(
    document_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Generate a summary of a document's content.
    Returns a comprehensive summary and a list of key points.
    """
    chunks = await _get_document_chunks(document_id, user.id, session)
    # Check cache first
    cache_key = f"summary:{document_id}"
    cached_data = await get_cache(cache_key)
    if cached_data:
        return SummaryResponse(
            summary=cached_data.get("summary", ""),
            key_points=cached_data.get("key_points", []),
            document_id=str(document_id),
        )

    provider = get_ai_provider()
    chunk_texts = [c.content for c in chunks]
    
    # TRUNCATION: Prevent massive documents from exceeding free tier TPM limits (e.g., Groq's 12k TPM limit)
    combined_text = "\n\n".join(chunk_texts)
    if len(combined_text) > 25000:
        combined_text = combined_text[:25000] + "\n\n...[Document truncated due to size limits]..."
        
    raw = await provider.generate_structured(SUMMARY_PROMPT, [combined_text])

    try:
        data = json.loads(raw)
        summary = data.get("summary", "")
        key_points = data.get("key_points", [])
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse AI response into summary: {e}",
        )

    # Save to cache (24 hours expiration)
    await set_cache(
        cache_key, 
        {"summary": summary, "key_points": key_points}, 
        expire_seconds=86400
    )

    return SummaryResponse(
        summary=summary,
        key_points=key_points,
        document_id=str(document_id),
    )


async def _get_document_chunks(
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession,
) -> list[DocumentChunk]:
    """Fetch all chunks for a document, verifying ownership and readiness."""
    # verify document exists, belongs to user, and is ready
    doc_stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == user_id,
    )
    doc_result = await session.execute(doc_stmt)
    doc = doc_result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.status != DocumentStatus.READY:
        raise HTTPException(status_code=400, detail="Document is still processing")

    # get all chunks ordered by index
    chunk_stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
    )
    result = await session.execute(chunk_stmt)
    chunks = list(result.scalars().all())

    if not chunks:
        raise HTTPException(status_code=400, detail="No content found for this document")

    return chunks
