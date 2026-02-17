"""Static list of all expected Jarvis services with default configuration.

Names MUST match the directory/service names used by the jarvis CLI
and _auto_register (e.g., 'jarvis-auth', not 'auth').
"""

KNOWN_SERVICES: list[dict[str, str | int]] = [
    {
        "name": "jarvis-config-service",
        "port": 8013,
        "description": "Service registry",
        "health_path": "/health",
    },
    {
        "name": "jarvis-auth",
        "port": 8007,
        "description": "JWT authentication",
        "health_path": "/health",
    },
    {
        "name": "jarvis-logs",
        "port": 8006,
        "description": "Centralized logging",
        "health_path": "/health",
    },
    {
        "name": "jarvis-command-center",
        "port": 8002,
        "description": "Voice/command API",
        "health_path": "/health",
    },
    {
        "name": "jarvis-llm-proxy-api",
        "port": 8000,
        "description": "LLM proxy",
        "health_path": "/health",
    },
    {
        "name": "jarvis-tts",
        "port": 8009,
        "description": "Text-to-speech",
        "health_path": "/health",
    },
    {
        "name": "jarvis-whisper-api",
        "port": 8012,
        "description": "Speech-to-text",
        "health_path": "/health",
    },
    {
        "name": "jarvis-ocr-service",
        "port": 5009,
        "description": "OCR service",
        "health_path": "/health",
    },
    {
        "name": "jarvis-recipes-server",
        "port": 8001,
        "description": "Recipe CRUD",
        "health_path": "/health",
    },
    {
        "name": "jarvis-settings-server",
        "port": 8014,
        "description": "Settings aggregator",
        "health_path": "/health",
    },
    {
        "name": "jarvis-mcp",
        "port": 8011,
        "description": "MCP server",
        "health_path": "/health",
    },
]
