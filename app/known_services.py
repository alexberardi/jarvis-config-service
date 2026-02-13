"""Static list of all expected Jarvis services with default configuration."""

KNOWN_SERVICES: list[dict[str, str | int]] = [
    {
        "name": "auth",
        "port": 8007,
        "description": "JWT authentication",
        "health_path": "/health",
    },
    {
        "name": "command-center",
        "port": 8002,
        "description": "Voice/command API",
        "health_path": "/health",
    },
    {
        "name": "whisper",
        "port": 8012,
        "description": "Speech-to-text",
        "health_path": "/health",
    },
    {
        "name": "ocr",
        "port": 5009,
        "description": "OCR service",
        "health_path": "/health",
    },
    {
        "name": "recipes",
        "port": 8001,
        "description": "Recipe CRUD",
        "health_path": "/health",
    },
    {
        "name": "llm-proxy",
        "port": 8000,
        "description": "LLM proxy",
        "health_path": "/health",
    },
    {
        "name": "tts",
        "port": 8009,
        "description": "Text-to-speech",
        "health_path": "/health",
    },
    {
        "name": "logs",
        "port": 8006,
        "description": "Centralized logging",
        "health_path": "/health",
    },
    {
        "name": "mcp",
        "port": 8011,
        "description": "MCP server",
        "health_path": "/health",
    },
    {
        "name": "config-service",
        "port": 8013,
        "description": "Service registry",
        "health_path": "/health",
    },
]
