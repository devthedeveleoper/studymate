import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.chunk import DocumentChunk
from app.services.ai_provider import AIProvider


async def search_similar_chunks(
    query: str,
    ai_provider: AIProvider,
    session: AsyncSession,
    user_id: uuid.UUID,
    document_id: uuid.UUID | None = None,
    top_k: int = 5,
) -> list[DocumentChunk]:
    """
    Embed the query and find the most similar document chunks via pgvector.

    Can optionally scope the search to a specific document, or search
    across all of a user's documents.
    """
    # embed the query
    query_embedding = await ai_provider.embed_query(query)

    # build the similarity search query
    # using cosine distance operator <=> from pgvector
    stmt = (
        select(DocumentChunk)
        .join(DocumentChunk.document)
        .where(DocumentChunk.document.has(user_id=user_id))
    )

    if document_id:
        stmt = stmt.where(DocumentChunk.document_id == document_id)

    # order by cosine distance (lower = more similar)
    stmt = stmt.order_by(
        DocumentChunk.embedding.cosine_distance(query_embedding)
    ).limit(top_k)

    result = await session.execute(stmt)
    return list(result.scalars().all())
