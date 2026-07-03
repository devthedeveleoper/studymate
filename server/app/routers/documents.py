import uuid
import os
import shutil
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_async_session, async_session_maker
from app.core.security import current_active_user
from app.models.user import User
from app.models.document import Document, DocumentStatus
from app.models.chunk import DocumentChunk
from app.schemas.document import DocumentOut, DocumentUploadResponse
from app.services.pdf import extract_text_from_pdf
from app.services.chunker import RecursiveCharacterSplitter
from app.services.ai_provider import AIProvider
from app.services.ollama_provider import OllamaProvider

settings = get_settings()
router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


from app.services.ollama_provider import OllamaProvider
from app.services.groq_provider import GroqProvider

def get_ai_provider() -> AIProvider:
    """Factory that returns the configured AI provider."""
    if settings.AI_PROVIDER == "groq":
        return GroqProvider()
    return OllamaProvider()


async def process_document(document_id: uuid.UUID, file_path: str):
    """
    Background task: extract text from PDF, chunk it, generate embeddings,
    and store everything in the database.
    """
    provider = get_ai_provider()
    splitter = RecursiveCharacterSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )

    async with async_session_maker() as session:
        try:
            # extract text
            full_text, page_count = extract_text_from_pdf(file_path)

            if not full_text.strip():
                raise ValueError("No text could be extracted from the PDF")

            # chunk the text
            chunks = splitter.split(full_text)

            # generate embeddings in batches
            batch_size = 10
            all_embeddings = []
            
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i : i + batch_size]
                embeddings = await provider.embed(batch)
                all_embeddings.extend(embeddings)

            # store chunks with embeddings
            for idx, (chunk_text, embedding) in enumerate(zip(chunks, all_embeddings)):
                chunk = DocumentChunk(
                    document_id=document_id,
                    content=chunk_text,
                    chunk_index=idx,
                    embedding=embedding,
                )
                session.add(chunk)

            # update document status
            doc = await session.get(Document, document_id)
            if doc:
                doc.status = DocumentStatus.READY
                doc.page_count = page_count

            await session.commit()
            print(f"Document {document_id} processed: {len(chunks)} chunks created")

        except Exception as e:
            print(f"Failed to process document {document_id}: {e}")
            doc = await session.get(Document, document_id)
            if doc:
                doc.status = DocumentStatus.FAILED
            await session.commit()

        finally:
            # clean up the uploaded file
            if os.path.exists(file_path):
                os.remove(file_path)


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Upload a PDF document for processing.
    The document will be chunked and embedded in the background.
    """
    # validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # validate file size
    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.MAX_UPLOAD_MB}MB",
        )

    # save to disk temporarily
    file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
    with open(file_path, "wb") as f:
        f.write(contents)

    # create document record
    document = Document(
        user_id=user.id,
        filename=file.filename,
        status=DocumentStatus.PROCESSING,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)

    # kick off background processing
    background_tasks.add_task(process_document, document.id, file_path)

    return DocumentUploadResponse(
        id=document.id,
        filename=document.filename,
        status=document.status,
        message="Document uploaded. Processing will begin shortly.",
    )


@router.get("/", response_model=list[DocumentOut])
async def list_documents(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """List all documents belonging to the current user."""
    stmt = (
        select(Document)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get details of a specific document."""
    stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == user.id,
    )
    result = await session.execute(stmt)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a document and all its chunks."""
    stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == user.id,
    )
    result = await session.execute(stmt)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await session.delete(doc)
    await session.commit()
    return {"message": "Document deleted"}
