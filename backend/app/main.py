from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, chores, members, onboarding, push, rooms, sessions
from app.routers import settings as settings_router
from app.routers import supplies, tasks

app = FastAPI(title="Tada API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(push.router)
app.include_router(rooms.router)
app.include_router(tasks.router)
app.include_router(sessions.router)
app.include_router(settings_router.router)
app.include_router(onboarding.router)
app.include_router(chores.router)
app.include_router(members.router)
app.include_router(supplies.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
