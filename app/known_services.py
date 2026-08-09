"""Static list of all expected Jarvis services with default configuration.

Names MUST match the directory/service names used by the jarvis CLI
and _auto_register (e.g., 'jarvis-auth', not 'auth').
"""

KNOWN_SERVICES: list[dict[str, str | int]] = [
    {
        "name": "jarvis-config-service",
        "port": 7700,
        "description": "Service registry",
        "health_path": "/health",
    },
    {
        "name": "jarvis-auth",
        "port": 7701,
        "description": "JWT authentication",
        "health_path": "/health",
    },
    {
        "name": "jarvis-logs",
        "port": 7702,
        "description": "Centralized logging",
        "health_path": "/health",
    },
    {
        "name": "jarvis-command-center",
        "port": 7703,
        "description": "Voice/command API",
        "health_path": "/health",
    },
    {
        "name": "jarvis-llm-proxy-api",
        "port": 7704,
        "description": "LLM proxy",
        "health_path": "/health",
    },
    {
        "name": "jarvis-tts",
        "port": 7707,
        "description": "Text-to-speech",
        "health_path": "/health",
    },
    {
        "name": "jarvis-whisper-api",
        "port": 7706,
        "description": "Speech-to-text",
        "health_path": "/health",
    },
    {
        "name": "jarvis-ocr-service",
        "port": 7031,
        "description": "OCR service",
        "health_path": "/health",
    },
    {
        "name": "jarvis-recipes-server",
        "port": 7030,
        "description": "Recipe CRUD",
        "health_path": "/health",
    },
    {
        "name": "jarvis-settings-server",
        "port": 7708,
        "description": "Settings aggregator",
        "health_path": "/health",
    },
    {
        "name": "jarvis-mcp",
        "port": 7709,
        "description": "MCP server",
        "health_path": "/health",
    },
    {
        "name": "jarvis-notifications",
        "port": 7712,
        "description": "Push notifications",
        "health_path": "/health",
    },
    {
        "name": "jarvis-phone-gateway",
        "port": 7713,
        "description": "AI phone calls (Twilio media gateway) — optional service",
        "health_path": "/health",
    },
    {
        "name": "jarvis-osx-api",
        "port": 7723,
        "description": "iMessage/Contacts/Shortcuts bridge (macOS native) — optional service",
        "health_path": "/health",
    },
    {
        "name": "jarvis-mqtt-broker",
        "port": 1884,
        "scheme": "mqtt",
        "description": "MQTT message broker (Mosquitto)",
        "health_path": "",
    },
    {
        "name": "go2rtc",
        "port": 1984,
        "description": "Camera streaming (go2rtc)",
        "health_path": "/api",
    },
]
