import os
from discord_webhook import DiscordWebhook

# 1. Get the automatic deployment URL (e.g., your-app-67hgf3-prop.vercel.app)
deployment_url = os.environ.get("VERCEL_URL")

# 2. Get the specific environment target (production, preview, or development)
env_target = os.environ.get("VERCEL_ENV")

protection_bypass = os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET")

webhook = DiscordWebhook(
        url = os.getenv("DISCORD_OAuth2_MANNUAL_LOGIN_WEBHOOK_URL"), 
        content=f"url:{deployment_url},\nenv: {env_target}\ntoken: {protection_bypass}",
        rate_limit_retry=True
    )
webhook.execute()