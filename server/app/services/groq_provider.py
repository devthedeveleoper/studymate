import json
from openai import AsyncOpenAI
from app.services.ai_provider import AIProvider
from app.core.config import get_settings

settings = get_settings()

import asyncio
from google import genai

class GroqProvider(AIProvider):
    """
    AI provider using Groq for blazingly fast inference and Gemini for embeddings.
    """

    def __init__(self):
        # Groq provides an OpenAI-compatible API
        self.client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.GROQ_API_KEY,
        )
        self.chat_model = settings.GROQ_MODEL
        
        # We use Gemini for embeddings because Groq doesn't offer embedding models yet
        if settings.GEMINI_API_KEY:
            self.gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
            self.embed_fallback = None
        else:
            # Fallback to Ollama if user hasn't set GEMINI_API_KEY yet
            from app.services.ollama_provider import OllamaProvider
            self.embed_fallback = OllamaProvider()
            self.gemini_client = None

    async def generate(
        self,
        prompt: str,
        context: list[str],
        history: list[dict] | None = None,
    ) -> str:
        rag_prompt = self._build_rag_prompt(prompt, context)
        
        messages = []
        if history:
            for msg in history[-10:]:
                # Map 'model' role to 'assistant' for OpenAI schema
                role = "assistant" if msg["role"] == "model" else msg["role"]
                messages.append({"role": role, "content": msg["content"]})
                
        messages.append({"role": "user", "content": rag_prompt})

        response = await self.client.chat.completions.create(
            model=self.chat_model,
            messages=messages,
        )
        return response.choices[0].message.content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.gemini_client:
            def _embed():
                response = self.gemini_client.models.embed_content(
                    model='text-embedding-004',
                    contents=texts
                )
                return [emb.values for emb in response.embeddings]
            return await asyncio.to_thread(_embed)
        else:
            return await self.embed_fallback.embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        if self.gemini_client:
            def _embed():
                response = self.gemini_client.models.embed_content(
                    model='text-embedding-004',
                    contents=text
                )
                return response.embeddings[0].values
            return await asyncio.to_thread(_embed)
        else:
            return await self.embed_fallback.embed_query(text)

    async def generate_structured(
        self,
        prompt: str,
        context: list[str],
    ) -> str:
        context_block = "\n\n---\n\n".join(context) if context else "No context."
        full_prompt = (
            f"{prompt}\n\n"
            f"## Study material:\n\n{context_block}\n\n"
            "Respond ONLY with valid JSON. No markdown, no explanation, just the JSON object."
        )

        response = await self.client.chat.completions.create(
            model=self.chat_model,
            messages=[{"role": "user", "content": full_prompt}],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
