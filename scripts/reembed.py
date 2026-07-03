"""
Re-embed all document chunks when switching AI providers.

Usage:
    uv run python scripts/reembed.py --provider gemini
    uv run python scripts/reembed.py --provider ollama

This script re-generates embeddings for ALL chunks in the database
using the specified provider. Needed when switching between Ollama
and Gemini since their embedding spaces are incompatible.
"""

import asyncio
import argparse
import sys
import os

# add the server directory to the path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from sqlalchemy import select
from app.core.database import async_session_maker, engine
from app.models.chunk import DocumentChunk
from app.services.ollama_provider import OllamaProvider
from app.services.gemini_provider import GeminiProvider


async def reembed_all(provider_name: str):
    if provider_name == "ollama":
        provider = OllamaProvider()
    elif provider_name == "gemini":
        provider = GeminiProvider()
    else:
        print(f"Unknown provider: {provider_name}")
        return

    print(f"Re-embedding all chunks with {provider_name}...")

    async with async_session_maker() as session:
        result = await session.execute(
            select(DocumentChunk).order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        )
        chunks = list(result.scalars().all())

        if not chunks:
            print("No chunks found in the database.")
            return

        print(f"Found {len(chunks)} chunks to re-embed.")

        # process in batches
        batch_size = 50
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.content for c in batch]

            embeddings = await provider.embed(texts)

            for chunk, embedding in zip(batch, embeddings):
                chunk.embedding = embedding

            await session.commit()
            print(f"  Processed {min(i + batch_size, len(chunks))}/{len(chunks)} chunks")

    await engine.dispose()
    print("Done! All chunks have been re-embedded.")


def main():
    parser = argparse.ArgumentParser(description="Re-embed all document chunks")
    parser.add_argument(
        "--provider",
        choices=["ollama", "gemini"],
        required=True,
        help="Which AI provider to use for generating new embeddings",
    )
    args = parser.parse_args()
    asyncio.run(reembed_all(args.provider))


if __name__ == "__main__":
    main()
