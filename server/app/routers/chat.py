import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.core.security import current_active_user
from app.models.user import User
from app.models.chat import Conversation, Message, MessageRole
from app.models.document import Document, DocumentStatus
from app.schemas.chat import (
    ConversationCreate,
    ConversationOut,
    MessageOut,
    ChatRequest,
    ChatResponse,
    SourceChunk,
)
from app.services.retrieval import search_similar_chunks
from app.routers.documents import get_ai_provider

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ConversationOut)
async def create_conversation(
    data: ConversationCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Start a new chat conversation, optionally linked to a document."""
    # if a document is specified, verify it exists and belongs to the user
    if data.document_id:
        stmt = select(Document).where(
            Document.id == data.document_id,
            Document.user_id == user.id,
            Document.status == DocumentStatus.READY,
        )
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Document not found or not ready")

    conversation = Conversation(
        user_id=user.id,
        document_id=data.document_id,
        title=data.title,
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


@router.get("/", response_model=list[ConversationOut])
async def list_conversations(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """List all conversations for the current user."""
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def get_messages(
    conversation_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get all messages in a conversation."""
    # verify ownership
    conv = await _get_user_conversation(conversation_id, user.id, session)

    stmt = (
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("/{conversation_id}/message", response_model=ChatResponse)
async def send_message(
    conversation_id: uuid.UUID,
    data: ChatRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Send a message and get an AI response.
    Uses RAG: retrieves relevant chunks from the user's documents,
    then sends them along with the question to the AI for a grounded answer.
    """
    conv = await _get_user_conversation(conversation_id, user.id, session)
    provider = get_ai_provider()

    # save the user's message
    user_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.USER,
        content=data.message,
    )
    session.add(user_msg)
    await session.flush()

    # retrieve relevant chunks
    chunks = await search_similar_chunks(
        query=data.message,
        ai_provider=provider,
        session=session,
        user_id=user.id,
        document_id=conv.document_id,
        top_k=5,
    )

    context_texts = [c.content for c in chunks]

    # build chat history for context
    history_stmt = (
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
    )
    history_result = await session.execute(history_stmt)
    history = [
        {"role": m.role.value, "content": m.content}
        for m in history_result.scalars().all()
    ]

    # generate the AI response
    answer = await provider.generate(
        prompt=data.message,
        context=context_texts,
        history=history[:-1],  # exclude the message we just added
    )

    # save the assistant's response
    assistant_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.ASSISTANT,
        content=answer,
    )
    session.add(assistant_msg)

    # update conversation title from the first message
    if len(history) <= 1:
        conv.title = data.message[:100]

    await session.commit()

    return ChatResponse(
        answer=answer,
        sources=[
            SourceChunk(content=c.content, chunk_index=c.chunk_index)
            for c in chunks
        ],
    )


@router.post("/{conversation_id}/stream")
async def stream_message(
    conversation_id: uuid.UUID,
    data: ChatRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Stream an AI response back to the client.
    """
    conv = await _get_user_conversation(conversation_id, user.id, session)
    provider = get_ai_provider()

    user_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.USER,
        content=data.message,
    )
    session.add(user_msg)
    await session.flush()

    chunks = await search_similar_chunks(
        query=data.message,
        ai_provider=provider,
        session=session,
        user_id=user.id,
        document_id=conv.document_id,
        top_k=5,
    )
    context_texts = [c.content for c in chunks]

    history_stmt = (
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
    )
    history_result = await session.execute(history_stmt)
    history = [
        {"role": m.role.value, "content": m.content}
        for m in history_result.scalars().all()
    ]

    async def stream_generator():
        full_answer = ""
        async for chunk in provider.generate_stream(
            prompt=data.message,
            context=context_texts,
            history=history[:-1],
        ):
            full_answer += chunk
            yield chunk

        # Save to DB after streaming completes
        assistant_msg = Message(
            conversation_id=conv.id,
            role=MessageRole.ASSISTANT,
            content=full_answer,
        )
        session.add(assistant_msg)

        if len(history) <= 1:
            conv.title = data.message[:100]

        await session.commit()

    return StreamingResponse(stream_generator(), media_type="text/plain")


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a conversation and all its messages."""
    conv = await _get_user_conversation(conversation_id, user.id, session)
    await session.delete(conv)
    await session.commit()
    return {"message": "Conversation deleted"}


async def _get_user_conversation(
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession,
) -> Conversation:
    """Helper to fetch a conversation and verify it belongs to the user."""
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    )
    result = await session.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv
