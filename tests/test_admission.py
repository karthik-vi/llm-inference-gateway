from gateway.admission import AdmissionController


def test_admits_under_light_load_and_rejects_when_queue_long() -> None:
    a = AdmissionController(slo_ttft_s=2.0, slots=4, init_ttft_s=0.7, init_service_s=2.0)
    assert a.decide({"r0": 1, "r1": 0}).admit
    d = a.decide({"r0": 12, "r1": 11})  # queue 8 -> 0.7 + 8*2/4 = 4.7 s
    assert not d.admit and d.retry_after_s >= 1 and a.rejected == 1


def test_uses_least_loaded_replica() -> None:
    a = AdmissionController(slo_ttft_s=2.0, slots=4)
    assert a.decide({"r0": 50, "r1": 2}).admit


def test_observe_updates_ewma() -> None:
    a = AdmissionController(slo_ttft_s=2.0, slots=4, init_service_s=2.0, alpha=0.5)
    a.observe(0.3, 1.0, inflight_at_start=0)
    assert a.service == 1.5 and abs(a.ttft_base - 0.5) < 1e-9
    a.observe(5.0, 3.0, inflight_at_start=9)  # loaded: ttft_base unchanged
    assert abs(a.ttft_base - 0.5) < 1e-9
