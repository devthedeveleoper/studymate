import ollama
from app.services.ai_provider import AIProvider
from app.core.config import get_settings

settings = get_settings()


class OllamaProvider(AIProvider):
    """
    AI provider using locally-running Ollama.
    Expects Ollama to be running and the models to be pulled:
      ollama pull qwen3:4b
      ollama pull nomic-embed-text
    """

    def __init__(self):
        self.client = ollama.AsyncClient(host=settings.OLLAMA_BASE_URL)
        self.chat_model = settings.OLLAMA_CHAT_MODEL
        self.embed_model = settings.OLLAMA_EMBED_MODEL

    async def generate(
        self,
        prompt: str,
        context: list[str],
        history: list[dict] | None = None,
    ) -> str:
        rag_prompt = self._build_rag_prompt(prompt, context)

        messages = []
        # add chat history if available
        if history:
            for msg in history[-10:]:  # keep last 10 messages to stay within context
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": rag_prompt})

        response = await self.client.chat(
            model=self.chat_model,
            messages=messages,
        )
        return response["message"]["content"]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # nomic-embed-text works best with task-specific prefixes
        prefixed = [f"search_document: {t}" for t in texts]

        response = await self.client.embed(
            model=self.embed_model,
            input=prefixed,
        )
        return response["embeddings"]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query (uses the search_query prefix)."""
        response = await self.client.embed(
            model=self.embed_model,
            input=[f"search_query: {text}"],
        )
        return response["embeddings"][0]

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

        response = await self.client.chat(
            model=self.chat_model,
            messages=[{"role": "user", "content": full_prompt}],
            format="json",
        )
        return response["message"]["content"]
