import os

import uvicorn

if __name__ == "__main__":
    from app.cli import migrate

    migrate()
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), proxy_headers=True)
