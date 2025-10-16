#!/usr/bin/env python
"""
Passenger WSGI entry point for hosting services (cPanel, Plesk, etc.)
This file allows the FastAPI app to run on shared hosting with Passenger
"""

import sys
import os
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Add the app directory to Python path
app_dir = backend_dir / 'app'
sys.path.insert(0, str(app_dir))

# Import the FastAPI application
try:
    from app.api.web_optimizer import app as application
except ImportError:
    # Alternative import if structure is different
    from api.web_optimizer import app as application

# For debugging (remove in production)
import logging
logging.basicConfig(level=logging.INFO)

# Passenger requires 'application' variable
# FastAPI apps work with Passenger through ASGI
if __name__ == "__main__":
    # This allows testing locally
    import uvicorn
    uvicorn.run(application, host="0.0.0.0", port=8001)