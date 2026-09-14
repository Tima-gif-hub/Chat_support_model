from support_runtime.metrics import RuntimeMetrics


def test_runtime_metrics_expose_health_and_outcomes() -> None:
    metrics = RuntimeMetrics()
    metrics.readiness(True)
    metrics.complaint("confirmation_required")
    metrics.complaint("submitted")
    metrics.citation_failure()

    output = metrics.prometheus()

    assert "support_runtime_ready 1" in output
    assert 'support_runtime_complaints_total{outcome="confirmation_required"} 1' in output
    assert 'support_runtime_complaints_total{outcome="submitted"} 1' in output
    assert 'support_runtime_complaints_total{outcome="failed"} 0' in output
    assert "support_runtime_citation_failures_total 1" in output
