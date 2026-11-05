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
    routing: str = "round_robin"   # round_robin | prefix
    max_inflight_per_replica: int = 6
    admission: bool = False        # SLO-aware admission control (env GATEWAY_ADMISSION=1)
    slo_ttft_s: float = 2.0
    slots_per_replica: int = 4
    admission_margin: float = 1.0
    admission_seed: str = "none"   # none | perfmodel: seed EWMAs from the Phase 3 service-time model
    breaker: bool = False          # passive circuit breaker on connect errors (env GATEWAY_BREAKER=1)
    breaker_cooldown_s: float = 3.0
    semcache: bool = False         # semantic cache (env GATEWAY_SEMCACHE=1)
    semcache_threshold: float = 0.92
    cascade: str = "off"          # off | rule | llm (env GATEWAY_CASCADE)


class Replica(BaseModel):
    name: str
    url: str
    tier: str | None = None   # small | large; default = llama.model


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
    s = Settings.model_validate(yaml.safe_load(p.read_text()))
    if os.environ.get("GATEWAY_ROUTING"):
        s.gateway.routing = os.environ["GATEWAY_ROUTING"]
    if os.environ.get("GATEWAY_CASCADE"):
        s.gateway.cascade = os.environ["GATEWAY_CASCADE"]
    for r in s.replicas:
        r.tier = r.tier or s.llama.model
    if os.environ.get("GATEWAY_BREAKER"):
        s.gateway.breaker = os.environ["GATEWAY_BREAKER"] == "1"
    if os.environ.get("GATEWAY_SEMCACHE"):
        s.gateway.semcache = os.environ["GATEWAY_SEMCACHE"] == "1"
    if os.environ.get("GATEWAY_ADMISSION"):
        s.gateway.admission = os.environ["GATEWAY_ADMISSION"] == "1"
    return s
