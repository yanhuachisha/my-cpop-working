from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


QWEN_MODEL = os.getenv("QWEN_MODEL", "Qwen/Qwen3-0.6B")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")


class IntentRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4_000)
    recent_messages: list[dict[str, str]] = Field(default_factory=list, max_length=12)


class EmbeddingRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=64)


class MemoryRequest(BaseModel):
    messages: list[dict[str, str]] = Field(min_length=1, max_length=24)


class SummaryRequest(BaseModel):
    previous: str = ""
    messages: list[dict[str, str]] = Field(min_length=1, max_length=256)


class TokenizeRequest(BaseModel):
    text: str


class ModelRuntime:
    def __init__(self) -> None:
        self.tokenizer = None
        self.qwen = None
        self.embedder = None
        self.device = "unloaded"
        self.errors: list[str] = []
        self.lock = Lock()

    def load(self) -> None:
        with self.lock:
            if self.tokenizer is not None and self.embedder is not None:
                return
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer

                self.device = "cuda" if torch.cuda.is_available() else "cpu"
                self.tokenizer = AutoTokenizer.from_pretrained(QWEN_MODEL)
                self.qwen = AutoModelForCausalLM.from_pretrained(
                    QWEN_MODEL,
                    torch_dtype="auto",
                    device_map="auto" if self.device == "cuda" else None,
                )
                if self.device == "cpu":
                    self.qwen.to("cpu")
            except Exception as error:
                self.errors.append(f"qwen:{type(error).__name__}")
            try:
                from FlagEmbedding import BGEM3FlagModel

                self.embedder = BGEM3FlagModel(
                    EMBEDDING_MODEL,
                    use_fp16=self.device == "cuda",
                )
            except Exception as error:
                self.errors.append(f"bge-m3:{type(error).__name__}")

    def generate_json(self, system: str, payload: dict[str, Any], max_new_tokens: int = 320) -> dict[str, Any]:
        if self.qwen is None or self.tokenizer is None:
            raise RuntimeError("Qwen3-0.6B is not loaded")
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        try:
            rendered = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            rendered = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer([rendered], return_tensors="pt").to(self.qwen.device)
        output = self.qwen.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        generated = output[0][inputs.input_ids.shape[1]:]
        text = self.tokenizer.decode(generated, skip_special_tokens=True)
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("model did not return JSON")
        return json.loads(match.group(0))

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.embedder is None:
            raise RuntimeError("BGE-M3 is not loaded")
        encoded = self.embedder.encode(texts, batch_size=min(16, len(texts)), max_length=8192)
        dense = encoded["dense_vecs"]
        vectors = [item.tolist() if hasattr(item, "tolist") else list(item) for item in dense]
        if any(len(item) != 1024 for item in vectors):
            raise ValueError("BGE-M3 must return 1024-dimensional dense vectors")
        return vectors


runtime = ModelRuntime()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("MODEL_PRELOAD", "true").casefold() in {"1", "true", "yes"}:
        runtime.load()
    yield


app = FastAPI(title="Agent Model Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok" if runtime.qwen is not None and runtime.embedder is not None else "degraded",
        "qwen_model": QWEN_MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": 1024,
        "device": runtime.device,
        "errors": runtime.errors,
    }


@app.get("/ready")
def ready():
    if runtime.qwen is None or runtime.embedder is None:
        raise HTTPException(status_code=503, detail=health())
    return health()


@app.post("/v1/intent/classify")
def classify_intent(request: IntentRequest):
    system = (
        "你是业务Agent意图分类器，只输出JSON。intent只能是chat、music_search、recommendation、"
        "listening_history、preference_query、rag_qa、business_write、memory_update、unsafe_request。"
        "同时输出confidence、entities、slots、needs_rag、needs_memory、needs_tool、memory_worthy、risk_level。"
    )
    return runtime.generate_json(system, request.model_dump())


@app.post("/v1/embeddings")
def embeddings(request: EmbeddingRequest):
    vectors = runtime.embed(request.texts)
    return {
        "model": EMBEDDING_MODEL,
        "dimensions": 1024,
        "data": [{"index": index, "embedding": vector} for index, vector in enumerate(vectors)],
    }


@app.post("/v1/memory/extract")
def extract_memory(request: MemoryRequest):
    system = (
        "从对话中抽取用户明确表达或已被工具验证的稳定业务事实，只输出JSON对象memories。"
        "每项包含subject、predicate、object、memory_type、confidence、entities、source_message_ids、"
        "valid_from、expires_at。不要抽取密钥、身份号码、推测或助手自己生成的内容。"
    )
    return runtime.generate_json(system, request.model_dump(), max_new_tokens=512)


@app.post("/v1/summarize")
def summarize(request: SummaryRequest):
    system = (
        "生成去重的增量会话摘要，只保留用户目标、已确认事实、未完成事项和必要实体。"
        "不要复述最近对话之外的内容，只输出JSON对象，字段为summary。"
    )
    return runtime.generate_json(system, request.model_dump(), max_new_tokens=384)


@app.post("/v1/tokenize")
def tokenize(request: TokenizeRequest):
    if runtime.tokenizer is None:
        raise HTTPException(status_code=503, detail="Qwen tokenizer is not loaded")
    return {"tokens": len(runtime.tokenizer.encode(request.text, add_special_tokens=False))}
