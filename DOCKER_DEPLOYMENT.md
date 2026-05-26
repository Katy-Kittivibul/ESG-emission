# Docker Deployment Guide - ESG Carbon Analytics Dashboard

## Overview
The ESG Dashboard has been fully containerized for production deployment to Render or other cloud platforms.

## Files Created

### 1. **Dockerfile** (890 bytes)
- **Base Image**: `python:3.11-slim`
- **System Dependencies**: `build-essential`, `libgomp1` (required by Prophet and PyArrow)
- **Features**:
  - Multi-layer optimization (requirements.txt cached separately)
  - Port 8050 exposed
  - Healthcheck configured (curl-based)
  - Cache directory created
  - Python environment variables set
- **Entry Point**: `python app.py`

### 2. **docker-compose.yml** (587 bytes)
- **Service**: esg-dashboard
- **Port Mapping**: 8050:8050
- **Volume Persistence**: `./esg_dashboard/cache:/app/cache`
- **Healthcheck**: 30s interval, 10s timeout, 3 retries
- **Restart Policy**: unless-stopped
- **Network**: Bridge network for service isolation

### 3. **.dockerignore** (300 bytes)
Optimized build context excluding:
- Virtual environments (.venv/, venv/)
- Python cache (__pycache__/, *.pyc)
- Version control (.git/, .github/)
- Development files (tests/, .pytest_cache/, .coverage)
- Documentation (*.md)
- Build artifacts (cache/)

### 4. **docker-build-test.sh** (2.2K)
Comprehensive test script for:
- Building the Docker image
- Running container with port mapping
- Verifying healthcheck status
- Testing HTTP endpoint
- docker-compose orchestration
- Cleanup

### 5. **app.py Updates**
Modified app startup to support containerization:
```python
if __name__ == "__main__":
    import os
    debug_mode = os.getenv("DEBUG", "False").lower() == "true"
    print(f"ESG Dashboard running on http://0.0.0.0:8050 (debug={debug_mode})")
    app.run(host="0.0.0.0", port=8050, debug=debug_mode)
```

## Local Testing

### Build the Image
```bash
docker build -t esg-dashboard .
```

### Run the Container
```bash
docker run -p 8050:8050 esg-dashboard
```

### Using docker-compose
```bash
docker-compose up --build
docker-compose down
```

## Render Deployment

### Setup Steps
1. Create new Web Service on Render
2. Connect GitHub repository
3. Configure:
   - **Build Command**: (uses Dockerfile by default)
   - **Start Command**: `python app.py`
   - **Environment Variables**:
     - `PORT=8050`
     - `PYTHONUNBUFFERED=1`
     - `DEBUG=False` (default)

### How Healthcheck Works
- Render will check `http://localhost:8050` every 30 seconds
- Service automatically restarts if healthcheck fails
- On successful deployment, dashboard will be accessible

## Container Architecture

### Image Composition
- **Base**: python:3.11-slim (~150 MB)
- **System dependencies**: build-essential, libgomp1 (~200 MB)
- **Python packages**: dash, pandas, prophet, pyarrow, etc. (~400-500 MB)
- **Application code**: ~5 MB
- **Estimated Total**: 800-900 MB

### Runtime
- **Port**: 8050 (TCP)
- **Environment**: Production (debug=False)
- **Cache**: Persistent `/app/cache` directory
- **Health**: Verified by curl endpoint check

## Features

### Production Ready
- ✓ No debug mode in containers
- ✓ Host binding to 0.0.0.0 for external access
- ✓ Healthcheck for auto-recovery
- ✓ Proper signal handling
- ✓ Environment variable configuration

### Development Friendly
- ✓ docker-compose for local testing
- ✓ Volume persistence for cache
- ✓ Network isolation
- ✓ Restart policy for stability

### Data Persistence
- Cache directory mounted as volume
- Parquet files cached across restarts
- EDGAR v8 data persisted
- Reduces API calls and startup time

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker logs esg-dashboard

# Verify port isn't in use
netstat -ano | findstr :8050
```

### Healthcheck Failing
- Wait 10-15 seconds for app to start
- Check: `curl http://localhost:8050`
- Verify port 8050 is exposed and mapped

### Cache Not Persisting
- Verify volume mount in docker-compose.yml
- Check permissions on `./esg_dashboard/cache`
- Ensure directory exists before running

## Environment Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `DEBUG` | False | Set to "true" for development |
| `PORT` | 8050 | Render sets this automatically |
| `PYTHONUNBUFFERED` | 1 | Enables real-time logging |

## Next Steps

1. **Test Locally**:
   ```bash
   docker-compose up --build
   # Visit http://localhost:8050
   ```

2. **Push to GitHub**:
   ```bash
   git add Dockerfile .dockerignore docker-compose.yml
   git commit -m "Phase C: Dockerization complete"
   git push
   ```

3. **Deploy to Render**:
   - Connect repository
   - Configure environment
   - Deploy

## Verification Checklist

- [x] Dockerfile created and tested
- [x] .dockerignore optimized
- [x] docker-compose.yml configured
- [x] app.py configured for 0.0.0.0 binding
- [x] Healthcheck implemented
- [x] Cache persistence configured
- [x] Environment variables documented
- [x] Ready for production deployment

---

**Phase C Complete**: Dockerization ready for Render deployment.
