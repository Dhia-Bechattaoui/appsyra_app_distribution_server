# Vercel serverless function entry point
from app_distribution_server.app import app

# Export the FastAPI app as 'app' for Vercel
# This file tells Vercel how to handle the FastAPI application
