from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import json
from app.api.routes import router as api_router
from app.core.config import settings
from app.services.kv_storage import StorageService

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Fetching Supabase credentials from Primary Backend...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.PRIMARY_BACKEND_URL}/api/controllers/credentials/supabase",
                headers={"Authorization": f"Bearer {settings.CONTROLLER_API_KEY}"}
            )
            response.raise_for_status()
            creds = response.json()
            StorageService.save_data("supabase_creds", json.dumps(creds))
            print("Successfully fetched and saved Supabase credentials.")
    except Exception as e:
        print(f"Failed to fetch Supabase credentials: {e}")
    yield

app = FastAPI(title="NodeCom Controller", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
