"""
Centralised logging + LlamaIndex observability setup.

Call setup_logging() once at application startup.
Afterwards every module can do:

    import logging
    logger = logging.getLogger(__name__)

LlamaIndex internals are captured via LlamaDebugHandler and forwarded to
the "llama_index" Python logger so they appear in the same stream as the
rest of the application.
"""
import logging
import logging.config
import sys
from typing import Any

from llama_index.core import Settings as LlamaSettings
from llama_index.core.callbacks import CallbackManager, LlamaDebugHandler
from llama_index.core.callbacks.base_handler import BaseCallbackHandler
from llama_index.core.callbacks.schema import CBEventType, EventPayload


# ---------------------------------------------------------------------------
# Custom handler: forwards LlamaIndex callback events to Python logging
# ---------------------------------------------------------------------------

class _PythonLogBridge(BaseCallbackHandler):
    """
    Bridges LlamaIndex callback events into Python's logging system.
    Each event type maps to a log level and a short message so you can
    follow the RAG pipeline step by step in your log output.
    """

    _LEVEL_MAP: dict[CBEventType, int] = {
        CBEventType.LLM: logging.INFO,
        CBEventType.EMBEDDING: logging.DEBUG,
        CBEventType.RETRIEVE: logging.INFO,
        CBEventType.QUERY: logging.INFO,
        CBEventType.CHUNKING: logging.DEBUG,
        CBEventType.NODE_PARSING: logging.DEBUG,
        CBEventType.RERANKING: logging.INFO,
        CBEventType.SYNTHESIZE: logging.INFO,
        CBEventType.TEMPLATING: logging.DEBUG,
        CBEventType.FUNCTION_CALL: logging.INFO,
        CBEventType.EXCEPTION: logging.ERROR,
    }

    def __init__(self) -> None:
        super().__init__(event_starts_to_ignore=[], event_ends_to_ignore=[])
        self._log = logging.getLogger("llama_index.events")

    def on_event_start(
        self,
        event_type: CBEventType,
        payload: dict[str, Any] | None = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> str:
        level = self._LEVEL_MAP.get(event_type, logging.DEBUG)
        msg = self._summarise(event_type, payload, start=True)
        self._log.log(level, "[START] %s  id=%s  %s", event_type.value, event_id[:8], msg)
        return event_id

    def on_event_end(
        self,
        event_type: CBEventType,
        payload: dict[str, Any] | None = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        level = self._LEVEL_MAP.get(event_type, logging.DEBUG)
        msg = self._summarise(event_type, payload, start=False)
        self._log.log(level, "[END]   %s  id=%s  %s", event_type.value, event_id[:8], msg)

    def start_trace(self, trace_id: str | None = None) -> None:
        self._log.debug("─── LlamaIndex trace START  id=%s ───", trace_id)

    def end_trace(
        self,
        trace_id: str | None = None,
        trace_map: dict[str, list[str]] | None = None,
    ) -> None:
        self._log.debug("─── LlamaIndex trace END    id=%s ───", trace_id)

    # ------------------------------------------------------------------
    @staticmethod
    def _summarise(
        event_type: CBEventType,
        payload: dict[str, Any] | None,
        start: bool,
    ) -> str:
        if not payload:
            return ""
        parts: list[str] = []

        if event_type == CBEventType.LLM:
            if start:
                messages = payload.get(EventPayload.MESSAGES, [])
                parts.append(f"messages={len(messages)}")
                model = payload.get(EventPayload.SERIALIZED, {}).get("model", "")
                if model:
                    parts.append(f"model={model}")
            else:
                response = payload.get(EventPayload.RESPONSE)
                if response:
                    usage = getattr(getattr(response, "raw", None), "usage", None)
                    if usage:
                        parts.append(
                            f"prompt_tokens={getattr(usage, 'prompt_tokens', '?')} "
                            f"completion_tokens={getattr(usage, 'completion_tokens', '?')}"
                        )

        elif event_type == CBEventType.EMBEDDING:
            chunks = payload.get(EventPayload.CHUNKS, [])
            parts.append(f"chunks={len(chunks)}")

        elif event_type == CBEventType.RETRIEVE:
            if not start:
                nodes = payload.get(EventPayload.NODES, [])
                parts.append(f"retrieved={len(nodes)}")

        elif event_type == CBEventType.CHUNKING:
            chunks = payload.get(EventPayload.CHUNKS, [])
            parts.append(f"chunks={len(chunks)}")

        elif event_type == CBEventType.RERANKING:
            if not start:
                nodes = payload.get(EventPayload.NODES, [])
                parts.append(f"reranked={len(nodes)}")

        elif event_type == CBEventType.EXCEPTION:
            exc = payload.get(EventPayload.EXCEPTION)
            parts.append(str(exc))

        return "  ".join(parts)


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s  %(levelname)-8s  %(name)-40s  %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "%(levelname)-8s  %(name)s  %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "default",
        },
    },
    "loggers": {
        # Application namespaces — INFO and above
        "app": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
        "main": {"level": "INFO", "handlers": ["console"], "propagate": False},

        # LlamaIndex internals — DEBUG so callback bridge events show up
        "llama_index": {"level": "DEBUG", "handlers": ["console"], "propagate": False},

        # OpenAI HTTP client — WARNING to suppress verbose request logs
        "openai": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "httpx": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "httpcore": {"level": "WARNING", "handlers": ["console"], "propagate": False},

        # MongoDB driver
        "motor": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "pymongo": {"level": "WARNING", "handlers": ["console"], "propagate": False},

        # Root — catch anything else at WARNING
        "root": {"level": "WARNING", "handlers": ["console"]},
    },
}


def setup_logging() -> CallbackManager:
    """
    Configure Python logging and wire up LlamaIndex's callback manager.
    Returns the CallbackManager so it can be stored on LlamaSettings.
    """
    logging.config.dictConfig(LOGGING_CONFIG)

    debug_handler = LlamaDebugHandler(print_trace_on_end=False)
    bridge_handler = _PythonLogBridge()
    callback_manager = CallbackManager(handlers=[debug_handler, bridge_handler])

    # Attach to LlamaIndex global settings so every index/query/pipeline
    # created anywhere in the app automatically uses this manager.
    LlamaSettings.callback_manager = callback_manager

    logging.getLogger("app").info(
        "Logging initialised — LlamaIndex CallbackManager active "
        "(LlamaDebugHandler + Python log bridge)"
    )
    return callback_manager
