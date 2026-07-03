import json
from openai import AsyncOpenAI
from app.services.ai_provider import AIProvider
from app.core.config import get_settings

settings = get_settings()

import asyncio
from huggingface_hub import AsyncInferenceClient

class GroqProvider(AIProvider):
    """
    AI provider using Groq for blazingly fast inference and HuggingFace for embeddings.
    """

    def __init__(self):
        # Groq provides an OpenAI-compatible API
        self.client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.GROQ_API_KEY,
        )
        self.chat_model = settings.GROQ_MODEL
        
        # We use HuggingFace for embeddings because Groq doesn't offer embedding models yet
        if settings.HUGGINGFACE_API_KEY:
            self.hf_client = AsyncInferenceClient(token=settings.HUGGINGFACE_API_KEY)
            self.embed_fallback = None
        else:
            # Fallback to Ollama if user hasn't set HUGGINGFACE_API_KEY yet
            from app.services.ollama_provider import OllamaProvider
            self.embed_fallback = OllamaProvider()
            self.hf_client = None

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

    async def generate_stream(
        self,
        prompt: str,
        context: list[str],
        history: list[dict] | None = None,
    ):
        rag_prompt = self._build_rag_prompt(prompt, context)
        
        messages = []
        if history:
            for msg in history[-10:]:
                role = "assistant" if msg["role"] == "model" else msg["role"]
                messages.append({"role": role, "content": msg["content"]})
                
        messages.append({"role": "user", "content": rag_prompt})

        response = await self.client.chat.completions.create(
            model=self.chat_model,
            messages=messages,
            stream=True,
        )
        
        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.hf_client:
            # We must use list comprehension because the API sometimes returns a flat list if texts has only 1 element,
            # but usually a 2D list for multiple elements. HuggingFace feature_extraction returns ndarray-like lists.
            res = await self.hf_client.feature_extraction(
                texts,
                model="BAAI/bge-small-en-v1.5"
            )
            import numpy as np
            # Convert to standard Python lists
            return np.array(res).tolist()
        else:
            return await self.embed_fallback.embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        if self.hf_client:
            res = await self.hf_client.feature_extraction(
                text,
                model="BAAI/bge-small-en-v1.5"
            )
            import numpy as np
            # Squeeze to 1D array if needed, then tolist
            arr = np.array(res)
            if arr.ndim > 1:
                arr = arr.squeeze()
            return arr.tolist()
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
