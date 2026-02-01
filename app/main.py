from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routes import services_router
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown: nothing to clean up


app = FastAPI(
    title="Jarvis Config Service",
    description="Central service registry for the Jarvis ecosystem",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - allow all origins for internal service communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(services_router)


@app.get("/health")
def health():
    """Health check for the config service itself."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
