from abc import ABC, abstractmethod


class AIProvider(ABC):
    """
    Base class for AI providers (Ollama for dev, Gemini for prod).
    Implementations must handle both text generation and embedding.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        context: list[str],
        history: list[dict] | None = None,
    ) -> str:
        """
        Generate a response given a user prompt, relevant context chunks,
        and optional chat history.

        Args:
            prompt: The user's question or request.
            context: List of relevant text chunks retrieved via vector search.
            history: Previous messages in the conversation [{"role": ..., "content": ...}].

        Returns:
            The generated response text.
        """

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embedding vectors for a batch of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (each a list of floats).
        """

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        context: list[str],
    ) -> str:
        """
        Generate a response that should be valid JSON. Used for flashcards,
        summaries, and other structured outputs.

        The caller is responsible for parsing the JSON — this method just
        returns the raw string, since different providers handle structured
        output differently.
        """

    def _build_rag_prompt(self, question: str, context: list[str]) -> str:
        """Build the standard RAG prompt with context chunks."""
        context_block = "\n\n---\n\n".join(context) if context else "No relevant context found."
        return (
            "You are a helpful study assistant. Answer the user's question based "
            "ONLY on the provided context from their study notes. If the context "
            "doesn't contain enough information to answer, say so honestly. "
            "Cite specific parts of the notes when possible.\n\n"
            f"## Context from study notes:\n\n{context_block}\n\n"
            f"## Question:\n\n{question}"
        )
