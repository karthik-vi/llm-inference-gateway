import numpy as np

from perfmodel.model import HW, Params, predict
from perfmodel.planner import simulate


def test_decode_scales_inversely_with_weight_bytes() -> None:
    hw = HW(triad_gbps=10, gemm_gflops=200, cores=4)
    _, tg_small = predict(hw, Params(), "qwen2.5-0.5b-instruct-q4_k_m", 5e8, 2)
    _, tg_big = predict(hw, Params(), "qwen2.5-0.5b-instruct-q4_k_m", 1e9, 2)
    assert abs(tg_small / tg_big - 2.0) < 1e-9


def test_more_threads_never_slower() -> None:
    hw = HW(10, 200, 4)
    a = predict(hw, Params(alpha_c=0.7, alpha_b=0.7), "qwen2.5-1.5b-instruct-q8_0", 1.6e9, 1)
    b = predict(hw, Params(alpha_c=0.7, alpha_b=0.7), "qwen2.5-1.5b-instruct-q8_0", 1.6e9, 4)
    assert b[0] > a[0] and b[1] > a[1]


def test_simulation_more_replicas_lower_ttft_and_overload_blows_up() -> None:
    pre, out = np.full(100, 80), np.full(100, 30)
    low = simulate(0.2, 2, pp=100, tg=25, pre=pre, out=out, n=3000)
    one = simulate(1.5, 1, pp=100, tg=25, pre=pre, out=out, n=3000)
    two = simulate(1.5, 4, pp=100, tg=25, pre=pre, out=out, n=3000)
    assert low["ttft_p95"] < 1.0           # light load: just the prefill time (0.8 s)
    assert one["ttft_p95"] > 10 * two["ttft_p95"]
