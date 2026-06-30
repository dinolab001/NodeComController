from fastapi import FastAPI, HTTPException, Header, Depends
from discord_webhook import DiscordWebhook
import os
import httpx
import json

app = FastAPI()

DATA : dict = {"message": "hello world from NodeCom controller 1","version":1}

# Vercel KV details (Upstash Redis)
KV_REST_API_URL = os.getenv("KV_REST_API_URL")
KV_REST_API_TOKEN = os.getenv("KV_REST_API_TOKEN")

# Primary Backend URL
PRIMARY_BACKEND_URL = os.getenv("PRIMARY_BACKEND_URL", "http://localhost:8001")

# Controller API Key to protect endpoints
CONTROLLER_API_KEY = os.getenv("CONTROLLER_API_KEY")


def save_to_kv(key: str, value: str):
    if not KV_REST_API_URL or not KV_REST_API_TOKEN:
        print(f"Mock KV Save: {key}")
        return
        
    url = f"{KV_REST_API_URL}/set/{key}"
    headers = {"Authorization": f"Bearer {KV_REST_API_TOKEN}"}
    
    with httpx.Client() as client:
        response = client.post(url, headers=headers, json=value)
        response.raise_for_status()

def verify_api_key(x_api_key: str = Header(None)):
    if not CONTROLLER_API_KEY:
        # If no API key configured, we allow it (for dev)
        return True
    if not x_api_key or x_api_key != CONTROLLER_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return True


@app.get("/")
def read_root():
    global DATA
    return DATA

@app.get("/ping")
def pingDiscord():
    webhook_url = os.getenv("DISCORD_OAuth2_MANNUAL_LOGIN_WEBHOOK_URL")
    if not webhook_url:
        return {"status": 500, "detail": "Webhook URL not set"}
        
    webhook = DiscordWebhook(
        url=webhook_url, 
        content="hello world from NodeCom controller!",
        rate_limit_retry=True
    )
    return {"status": webhook.execute().status_code}

@app.post("/admin/fetch-auth")
async def fetch_auth(valid: bool = Depends(verify_api_key)):
    """
    Fetches Drive authentication details from the Primary Backend
    and stores them in this controller's Vercel KV.
    """
    try:
        if not CONTROLLER_API_KEY:
            raise HTTPException(status_code=500, detail="CONTROLLER_API_KEY not configured. Cannot authenticate with Primary Backend.")
            
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{PRIMARY_BACKEND_URL}/api/controllers/auth",
                headers={"X-Controller-API-Key": CONTROLLER_API_KEY},
                timeout=10.0
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"Failed to fetch from primary: {response.text}")
                
            data = response.json()
            if data.get("status") != "success":
                raise HTTPException(status_code=500, detail="Unsuccessful response from primary backend")
                
            credentials = data.get("credentials", {})
            for key, value in credentials.items():
                # Save each file content into our KV
                save_to_kv(key, value)
                
            return {"status": "success", "message": f"Successfully fetched and saved {len(credentials)} credential files."}
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
