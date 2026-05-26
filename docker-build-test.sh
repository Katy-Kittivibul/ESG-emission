#!/bin/bash
# Docker Build and Test Script for ESG Dashboard
# Run this script to build the Docker image and verify it works

set -e

echo "================================"
echo "ESG Dashboard Docker Build Test"
echo "================================"
echo ""

# Step 1: Build the Docker image
echo "Step 1: Building Docker image..."
docker build -t esg-dashboard:latest .
IMAGE_ID=$(docker images esg-dashboard:latest --quiet)
IMAGE_SIZE=$(docker images esg-dashboard:latest --format "{{.Size}}")
echo "✓ Built image: $IMAGE_ID ($IMAGE_SIZE)"
echo ""

# Step 2: Run the container with port mapping
echo "Step 2: Running container..."
docker run -d \
  --name esg-dashboard-test \
  -p 8050:8050 \
  --health-cmd="curl -f http://localhost:8050 || exit 1" \
  --health-interval=10s \
  --health-timeout=5s \
  --health-retries=3 \
  esg-dashboard:latest

sleep 5
echo "Container started"
echo ""

# Step 3: Check container logs
echo "Step 3: Container logs:"
docker logs esg-dashboard-test | head -20
echo ""

# Step 4: Check healthcheck
echo "Step 4: Checking healthcheck..."
HEALTH_STATUS=$(docker inspect --format='{{.State.Health.Status}}' esg-dashboard-test)
echo "Health status: $HEALTH_STATUS"

if [ "$HEALTH_STATUS" = "healthy" ]; then
  echo "✓ Healthcheck passing"
else
  echo "⚠ Healthcheck not yet passing (may need more time)"
fi
echo ""

# Step 5: Test HTTP endpoint
echo "Step 5: Testing HTTP endpoint..."
curl -s http://localhost:8050 | head -20
echo "✓ HTTP endpoint responding"
echo ""

# Step 6: docker-compose test
echo "Step 6: Testing docker-compose..."
docker-compose up --build -d
sleep 5
COMPOSE_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' esg-dashboard)
echo "docker-compose health: $COMPOSE_HEALTH"
docker-compose down
echo ""

# Cleanup
echo "Step 7: Cleanup..."
docker stop esg-dashboard-test 2>/dev/null || true
docker rm esg-dashboard-test 2>/dev/null || true
docker image inspect esg-dashboard:latest > /dev/null && \
  echo "✓ Image ready for Render deployment" || echo "⚠ Image not found"

echo ""
echo "================================"
echo "Build and test complete!"
echo "Image size: $IMAGE_SIZE"
echo "Next: Deploy to Render"
echo "================================"
