"""OpenTelemetry 스팬 — 설치·설정돼 있지 않으면 no-op."""

from __future__ import annotations

from contextlib import contextmanager

try:
    from opentelemetry import trace

    _tracer = trace.get_tracer("kinetic-action")
except Exception:  # pragma: no cover - 선택 의존성
    _tracer = None


@contextmanager
def span(name: str, **attrs):
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as s:
        for k, v in attrs.items():
            if v is not None:
                s.set_attribute(f"kinetic.{k}", str(v))
        yield s
