class RecursiveCharacterSplitter:
    """
    Splits text into chunks using a hierarchy of separators.
    Falls through to the next separator when chunks are still too large.
    Similar to LangChain's RecursiveCharacterTextSplitter but without the dependency.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: list[str] | None = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " "]

    def split(self, text: str) -> list[str]:
        """Split text into overlapping chunks."""
        if not text or not text.strip():
            return []

        chunks = self._split_recursive(text, self.separators)
        # merge small chunks and apply overlap
        return self._merge_with_overlap(chunks)

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text using the separator hierarchy."""
        if len(text) <= self.chunk_size:
            return [text.strip()] if text.strip() else []

        # find the best separator (first one that actually appears in the text)
        separator = ""
        remaining_separators = []
        for i, sep in enumerate(separators):
            if sep in text:
                separator = sep
                remaining_separators = separators[i + 1:]
                break

        # if no separator works, just force-split by chunk_size
        if not separator:
            return self._force_split(text)

        parts = text.split(separator)
        result = []
        current = ""

        for part in parts:
            candidate = f"{current}{separator}{part}" if current else part

            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                # save what we have so far
                if current.strip():
                    result.append(current.strip())

                # if this single part is too long, split it further
                if len(part) > self.chunk_size and remaining_separators:
                    sub_chunks = self._split_recursive(part, remaining_separators)
                    result.extend(sub_chunks)
                    current = ""
                else:
                    current = part

        if current.strip():
            result.append(current.strip())

        return result

    def _force_split(self, text: str) -> list[str]:
        """Last resort: split into fixed-size pieces."""
        chunks = []
        for i in range(0, len(text), self.chunk_size):
            chunk = text[i : i + self.chunk_size].strip()
            if chunk:
                chunks.append(chunk)
        return chunks

    def _merge_with_overlap(self, chunks: list[str]) -> list[str]:
        """Apply overlap between consecutive chunks."""
        if len(chunks) <= 1:
            return chunks

        result = []
        for i, chunk in enumerate(chunks):
            if i == 0:
                result.append(chunk)
                continue

            # grab the tail of the previous chunk as overlap
            prev = chunks[i - 1]
            overlap = prev[-self.chunk_overlap:] if len(prev) > self.chunk_overlap else prev

            # prepend overlap to current chunk
            merged = f"{overlap} {chunk}"

            # trim if it got too long
            if len(merged) > self.chunk_size + self.chunk_overlap:
                merged = merged[:self.chunk_size + self.chunk_overlap]

            result.append(merged.strip())

        return result
