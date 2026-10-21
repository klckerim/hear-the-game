"""OpenTelemetry for the deployed demo: Application Insights traces and metrics, no-op everywhere else.

`setup()` does nothing unless APPLICATIONINSIGHTS_CONNECTION_STRING is set. The API objects below are safe to use before or without it
(the OpenTelemetry API is a no-op until a provider is configured), and exporters batch in the background, so nothing here blocks the replay.
"""
from __future__ import annotations

import os

from opentelemetry import metrics, trace

tracer = trace.get_tracer("htg")
_meter = metrics.get_meter("htg")
sessions_active = _meter.create_up_down_counter("htg.sessions.active", description="Open listener sessions")
speech_resolved = _meter.create_counter("htg.speech.resolved", description="Speech messages resolved, by source and language")
resolve_ms = _meter.create_histogram("htg.speech.resolve_ms", unit="ms", description="Time to resolve one speech message")
dropped_stale = _meter.create_counter("htg.speech.dropped_stale", description="Non-goal speech dropped because it resolved too late")


def setup() -> bool:
    """Send traces, metrics and OpenAI-call spans to Application Insights. Returns whether telemetry was switched on."""
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return False
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

        configure_azure_monitor()
        OpenAIInstrumentor().instrument()
    except Exception as e:  # telemetry must never keep the demo from starting
        print(f"Telemetry unavailable ({type(e).__name__}: {e}); continuing without it.")
        return False
    print("Telemetry on: Application Insights")
    return True
