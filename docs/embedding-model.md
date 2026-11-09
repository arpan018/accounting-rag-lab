# Local embedding model selection

## Current T10a choice

- Ollama model: `embeddinggemma-2:270m`
- Ollama runtime observed: `0.40.15`
- Project endpoint: `http://127.0.0.1:11434/api/embed`
- Live output: two input strings produced two finite vectors, each 768 values long; Ollama reported 30 prompt tokens for that batch.
- `ollama show embeddinggemma-2:270m` reported architecture `gemma-embedding2`, 271M parameters, 262144 context length, Q8_0 quantization, and an embedding length of 512.

The model metadata and live endpoint disagree about vector length (512 vs. 768). I recorded 768 as the observed API output in `config.yaml`; T10b must validate the runtime response length and fail clearly if it changes. The Chroma collection must use the actual supplied vector dimensions, not a guessed value.

I will send the text batch to Ollama's local `/api/embed` endpoint, keep the returned vectors explicit, and pass them to Chroma. The official [Ollama embedding endpoint documentation](https://docs.ollama.com/api/embed) accepts a text or text array and documents `truncate` (default `true`) and optional `dimensions` request fields. The project should set truncation behavior explicitly so source text is not silently shortened.

The chat/CLI context setting of 4096 is separate from this embedding call. I do not need to raise it for T10a or embedding generation. I will revisit generation context only if later RAG prompts exceed the current budget or lose required evidence.
