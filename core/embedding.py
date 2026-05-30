# core/embedding.py
import numpy as np
import os
# 强制走国内镜像
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["TRANSFORMERS_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"

_model = None

def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(
            "moka-ai/m3e-small",
            local_files_only=True
        )
    return _model

def get_embedding(text: str) -> list[float]:
    model = _load_model()
    return model.encode(text, normalize_embeddings=True).tolist()