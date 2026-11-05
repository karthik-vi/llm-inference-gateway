"""Single source of settings: config.yaml (override path with GATEWAY_CONFIG)."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class GatewayCfg(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080
    upstream_timeout_s: float = 120.0
    routing: str = "round_robin"


class Replica(BaseModel):
    name: str
    url: str


class LlamaCfg(BaseModel):
    server_bin: str
    model_small: str
    model_large: str
    threads_per_replica: int = 2
    parallel_slots: int = 4
    ctx_per_slot: int = 1024
    model: str = "small"


class DataCfg(BaseModel):
    bitext_csv: str = "data/bitext.csv"
    trace_path: str = "data/trace.jsonl"


class Settings(BaseModel):
    gateway: GatewayCfg = GatewayCfg()
    replicas: list[Replica]
    llama: LlamaCfg
    data: DataCfg = DataCfg()


def load_settings(path: str | None = None) -> Settings:
    p = Path(path or os.environ.get("GATEWAY_CONFIG", "config.yaml"))
    return Settings.model_validate(yaml.safe_load(p.read_text()))
