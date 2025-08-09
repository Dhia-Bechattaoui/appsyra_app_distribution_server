# Deployment Guide for Appsyra

This app is configured for production deployment with **persistent data storage**. Choose your hosting platform:

## 🚀 Option 1: Render.com (Recommended)

**Why Render?** Best free tier for Python apps, supports custom domains, includes PostgreSQL database, 750 hours/month free.

### Deploy Steps:
1. **Fork this repository** to your GitHub account
2. **Set up Cloudflare R2** (optional but recommended):
   - Create R2 bucket (e.g., `appsyra-files`)
   - Generate API token with R2 Storage access
   - Copy bucket endpoint URL
3. **Go to [Render.com](https://render.com)** and create account
4. **Connect GitHub** and select your forked repository
5. **Render auto-detects** `render.yaml` and creates:
   - ✅ Web service
   - ✅ PostgreSQL database (automatically)
6. **Add R2 Environment Variables** (if using Cloudflare R2):
   - Go to your service → Environment tab
   - Update the R2 variables with your actual values
7. **Deploy automatically starts!**

### ✅ What You Get (Completely Free):
- ✅ **Web Service** (750 hours/month) 
- ✅ **PostgreSQL Database** (500MB) - auto-created
- ✅ **Persistent Data Storage** (no data loss on restart)
- ✅ **Custom Domain Support**
- ✅ **SSL Certificate** (automatic)
- ✅ **Cloudflare R2 Storage** (10GB free) - for app files

### Custom Domain Setup:
1. In Render dashboard, go to your service settings
2. Add custom domain: `appsyra.bechattaoui.dev`
3. Render will provide CNAME record
4. **Add to Netlify DNS**:
   - Type: `CNAME`
   - Name: `appsyra`
   - Value: `your-app.onrender.com` (Render provides this)

---

## 🔥 Option 2: Vercel (Serverless)

**Why Vercel?** Excellent for serverless, fast deployments, great for APIs.

### Deploy Steps:
1. **Install Vercel CLI**:
   ```bash
   npm install -g vercel
   ```

2. **Deploy**:
   ```bash
   vercel --prod
   ```

3. **Set Environment Variables** in Vercel dashboard:
   - `UPLOADS_SECRET_AUTH_TOKEN`: Your secret token
   - `APP_BASE_URL`: `https://appsyra.bechattaoui.dev`

### Custom Domain Setup:
1. In Vercel dashboard, go to project settings → Domains
2. Add `appsyra.bechattaoui.dev`
3. **Add to Netlify DNS**:
   - Type: `CNAME`
   - Name: `appsyra`
   - Value: `cname.vercel-dns.com`

---

## ✈️ Option 3: Fly.io

**Why Fly.io?** Global edge deployment, generous free tier.

### Deploy Steps:
1. **Install Fly CLI**:
   ```bash
   # Windows
   iwr https://fly.io/install.ps1 -useb | iex
   ```

2. **Login and Deploy**:
   ```bash
   fly auth login
   fly launch --no-deploy
   fly deploy
   ```

### Custom Domain Setup:
1. **Add domain to Fly**:
   ```bash
   fly domains add appsyra.bechattaoui.dev
   ```
2. **Add to Netlify DNS**:
   - Type: `CNAME`
   - Name: `appsyra`
   - Value: (Fly will provide the value)

---

## 🌐 DNS Configuration in Netlify

For any option you choose, you'll need to add a CNAME record in your Netlify DNS:

1. **Go to Netlify Dashboard**
2. **Select your `bechattaoui.dev` site**
3. **Go to Site Settings → Domain Management → DNS Records**
4. **Add Record**:
   - Type: `CNAME`
   - Name: `appsyra`
   - Value: (depends on hosting provider - see above)

---

## 📋 Quick Comparison

| Platform | Free Tier | Custom Domain | Database | Best For |
|----------|-----------|---------------|----------|----------|
| **Render** | 750 hrs/month | ✅ Free | ✅ PostgreSQL | Full apps, persistent data |
| **Vercel** | Unlimited | ✅ Free | ❌ No database | APIs, serverless |
| **Fly.io** | 3 VMs, 160GB | ✅ Free | ✅ Add-on | Global deployment |

## 🔧 Environment Variables to Set

For any platform you choose, set these environment variables:

### Required:
- `UPLOADS_SECRET_AUTH_TOKEN`: A strong secret password
- `APP_BASE_URL`: `https://appsyra.bechattaoui.dev`
- `DATABASE_URL`: PostgreSQL connection (auto-provided by hosting platforms)

### Cloudflare R2 Configuration (for persistent file storage):
Replace these values in your Render service environment variables:

```bash
STORAGE_URL=s3://your-bucket-name              # Your R2 bucket name
AWS_ACCESS_KEY_ID=your-r2-api-token            # From Cloudflare API token
AWS_SECRET_ACCESS_KEY=your-r2-api-token        # Same as access key
AWS_ENDPOINT_URL=https://abc123.r2.cloudflarestorage.com  # Your R2 endpoint
AWS_DEFAULT_REGION=auto                         # Always 'auto' for R2
```

### Without R2 (Local Storage Only):
If you skip R2 setup, files will be stored locally and **lost on restart**. Database data will still persist.

## 🚦 Next Steps

1. **Choose a platform** (I recommend Render for simplicity)
2. **Deploy using the steps above**
3. **Configure DNS in Netlify**
4. **Test your app at https://appsyra.bechattaoui.dev**

Need help with any specific platform? Let me know!
