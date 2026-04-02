import os

# We use Langfuse directly for app-level tracing. Disabling Haystack auto tracing
# avoids OpenTelemetry auto-loader side effects and circular import edge cases.
os.environ.setdefault("HAYSTACK_AUTO_TRACE_ENABLED", "false")
