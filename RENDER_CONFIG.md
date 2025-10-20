# Render Configuration Guide

## 🚨 CRITICAL: Manual Dashboard Configuration Required

Render is **NOT** reading the `render.yaml` automatically. You **MUST** configure these settings in the Render dashboard.

## Step-by-Step Configuration

### 1. Go to Render Dashboard
- Navigate to https://dashboard.render.com
- Select your service (backend)

### 2. Configure Build & Deploy Settings

Click on "Settings" tab, then update:

**Build Command:**
```bash
./build.sh
```

**Start Command:**
```bash
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

**Python Version:**
- Either let it auto-detect from `runtime.txt` (3.12.7)
- Or set manually to: `3.12.7`

### 3. Add Environment Variables

Go to "Environment" tab and add these variables:

```
MONGODB_URI=mongodb+srv://brianmayoga_db_user:QzjQdMkFcMUqtvtE@spotterai.mef7kkd.mongodb.net/?retryWrites=true&w=majority&appName=spotterai

MONGODB_DB_NAME=spotterai

AZURE_MAPS_SUBSCRIPTION_KEY=<your-azure-maps-key-from-env-file>

DEBUG=False
```

For `SECRET_KEY`, generate a new random key:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

For `ALLOWED_HOSTS`, use your Render domain:
```
ALLOWED_HOSTS=your-service-name.onrender.com
```

Example: If your URL is `https://spotterai-backend.onrender.com`, use:
```
ALLOWED_HOSTS=spotterai-backend.onrender.com
```

### 4. Make build.sh Executable (if needed)

If build fails with "permission denied", you may need to:

**Option A - Add to build command in Render:**
```bash
chmod +x build.sh && ./build.sh
```

**Option B - Commit executable permission (recommended):**
```bash
git update-index --chmod=+x build.sh
git commit -m "Make build.sh executable"
git push
```

### 5. Manual Deploy

After configuring:
1. Click "Manual Deploy" button
2. Select "Deploy latest commit"
3. Watch the logs

### 6. Verify Deployment

Check logs for:
- ✅ `Successfully installed` (all packages)
- ✅ `0 static files copied` (or number of static files)
- ✅ `Operations to perform: ...` (migrations)
- ✅ `Build successful 🎉`
- ✅ `Starting gunicorn` (with correct module path)

## 🐛 Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'app'"
**Cause:** Start command is wrong (using `gunicorn app:app`)
**Fix:** Change start command in dashboard to:
```bash
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

### Issue: "Permission denied: ./build.sh"
**Cause:** build.sh is not executable
**Fix:** Use chmod option above

### Issue: "Static files not found"
**Cause:** STATIC_ROOT not configured or collectstatic failed
**Check:** 
- Verify build logs show "Collecting static files"
- Ensure WhiteNoise is in MIDDLEWARE (already added)

### Issue: "ALLOWED_HOSTS error"
**Cause:** Your Render domain not in ALLOWED_HOSTS
**Fix:** Add environment variable with your full domain

### Issue: Django admin shows no CSS
**Cause:** Static files not collected or WhiteNoise not configured
**Fix:** Already configured - just ensure build.sh runs successfully

## ✅ Success Indicators

Your deployment is successful when you see:

1. **Build logs:**
```
==> Installing Python dependencies
Successfully installed Django-4.2.7 Pillow-11.0.0 ...
==> Collecting static files
0 static files copied to '/opt/render/project/src/staticfiles'
==> Running migrations
Operations to perform: ...
==> Build successful 🎉
```

2. **Deploy logs:**
```
==> Deploying...
==> Running 'gunicorn config.wsgi:application --bind 0.0.0.0:$PORT'
[INFO] Starting gunicorn 23.0.0
[INFO] Listening at: http://0.0.0.0:10000
```

3. **Test endpoints:**
```bash
# Should return 404 JSON (not HTML error)
curl https://your-domain.onrender.com/

# Should return empty array or trips
curl https://your-domain.onrender.com/api/trips/list/
```

## 📝 Alternative: Use Procfile Only

If render.yaml continues to be ignored, Render should auto-detect and use the Procfile.

Current Procfile content:
```
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

This should work automatically if:
1. File is named exactly `Procfile` (no extension)
2. Located in repository root
3. Build command is: `pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate`

## 🎯 Quick Fix Checklist

- [ ] Start Command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
- [ ] Build Command: `chmod +x build.sh && ./build.sh`
- [ ] Environment: Add all 5 required variables
- [ ] ALLOWED_HOSTS: Set to your Render domain
- [ ] Manual Deploy: Trigger new deployment
- [ ] Test: Visit API endpoints

## 📞 Still Having Issues?

1. Screenshot your Render settings (Build Command, Start Command)
2. Share the full deployment logs
3. Verify all environment variables are set
4. Check that repository has latest commits

---

**Last Updated:** October 20, 2025
**Issue:** Render ignoring render.yaml, using default `gunicorn app:app`
**Solution:** Manual dashboard configuration required
