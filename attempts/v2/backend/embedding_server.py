from fastapi import FastAPI
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

app = FastAPI()
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
class Batch(BaseModel):
    texts: list[str] = Field(max_length=64)

@app.get('/health')
def health():
    return {'model': 'all-MiniLM-L6-v2', 'dimensions': 384}

@app.post('/encode')
def encode(batch: Batch):
    # Explicit token-aware truncation; corpus chunking uses overlapping short windows.
    tokenizer = model.tokenizer
    bounded = [tokenizer.decode(tokenizer.encode(t, truncation=True, max_length=250), skip_special_tokens=True) for t in batch.texts]
    vectors = model.encode(bounded, normalize_embeddings=True, batch_size=32)
    return {'embeddings': vectors.tolist(), 'dimensions': 384}
