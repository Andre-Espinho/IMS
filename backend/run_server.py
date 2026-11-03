"""Entry point for the backend. The packaged app runs this frozen by PyInstaller.

Environment variables (all optional):
  IMS_PORT      port to listen on (default 8000)
  IMS_DATA_DIR  folder for the database and sign-in cache (default: backend/../data)
  IMS_WEB_DIR   folder with the built UI to serve at /
"""

import os

import uvicorn

from ims.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("IMS_PORT", "8000")), log_level="info")
