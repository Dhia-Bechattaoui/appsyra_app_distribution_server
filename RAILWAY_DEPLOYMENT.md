# Railway Deployment Guide

This guide explains how to deploy Appsyra to Railway with PostgreSQL database and persistent storage.

## Quick Deploy

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template/bGnCo1)

## Manual Deployment

### 1. Prerequisites

- A Railway account ([sign up here](https://railway.app))
- Git repository with this code

### 2. Create Railway Project

1. Go to [Railway](https://railway.app)
2. Click "Start a New Project"
3. Choose "Deploy from GitHub repo"
4. Select your repository
5. Railway will automatically detect the Dockerfile and start building

### 3. Add PostgreSQL Database

1. In your Railway project dashboard, click **"+ New"**
2. Select **"Database"** → **"PostgreSQL"**
3. Railway will create a PostgreSQL database and provide `DATABASE_URL`

### 4. Configure Environment Variables

In your Railway project dashboard, go to the "Variables" tab and add:

#### Required Variables:
- `UPLOADS_SECRET_AUTH_TOKEN`: A secure secret token for app uploads
- `APP_BASE_URL`: Your Railway app URL (e.g., `https://your-app-name.up.railway.app`)
- `DATABASE_URL`: Auto-provided by Railway PostgreSQL service

#### Cloudflare R2 Variables (Optional, for persistent file storage):
- `STORAGE_URL`: `s3://your-bucket-name`
- `AWS_ACCESS_KEY_ID`: Your Cloudflare R2 API token
- `AWS_SECRET_ACCESS_KEY`: Your Cloudflare R2 API token (same as above)
- `AWS_ENDPOINT_URL`: Your R2 endpoint URL
- `AWS_DEFAULT_REGION`: `auto`

#### Optional Variables:
- `LOGO_URL`: Custom logo URL (default: `/static/logo.png`)
- `APP_VERSION`: App version (default: `0.0.1-development`)

### 5. Domain Setup

1. In Railway dashboard, go to "Settings" tab
2. In the "Domains" section, you can:
   - Use the provided Railway domain (e.g., `your-app-name.up.railway.app`)
   - Add a custom domain

### 6. Deploy

Railway will automatically deploy your app when you push to your connected Git branch.

## File Structure for Railway

The following files have been configured for Railway deployment:

- `Procfile`: Defines the web process command
- `railway.toml`: Railway-specific configuration
- `Dockerfile`: Updated to use Railway's PORT environment variable

## Important Notes

1. **Database**: PostgreSQL database provides persistent storage for users, reviews, settings, and app metadata

2. **File Storage**: 
   - **With Cloudflare R2**: Files persist across deployments (recommended)
   - **Without R2**: Files stored in container filesystem (lost on restart)

3. **Security**: Make sure to set a strong `UPLOADS_SECRET_AUTH_TOKEN` in your environment variables

4. **Domain**: Update `APP_BASE_URL` to match your actual Railway domain

5. **Health Check**: The app includes a `/health` endpoint for Railway's health checks

6. **Data Persistence**: With PostgreSQL + R2, your app data survives restarts and deployments

## Troubleshooting

- Check Railway logs in the "Deployments" tab if the app fails to start
- Ensure all required environment variables are set
- Verify the `APP_BASE_URL` matches your actual domain

## Local Development

To run locally with the same configuration:

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export UPLOADS_SECRET_AUTH_TOKEN=your-secret-token
export APP_BASE_URL=http://localhost:8000

# Run the app
uvicorn app_distribution_server.app:app --host 0.0.0.0 --port 8000
```
