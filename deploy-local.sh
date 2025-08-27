#!/bin/bash

# Local Development Deployment Script for Shopping Assistant
set -e

echo "🚀 Deploying Shopping Assistant locally..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp env.example .env
    echo "📝 Please edit .env file with your API keys and settings, then run this script again."
    exit 1
fi

# Load environment variables
source .env

# Check required API keys
if [ -z "$GROQ_API_KEY" ] || [ "$GROQ_API_KEY" = "your_groq_api_key_here" ]; then
    echo "❌ GROQ_API_KEY not set in .env file. Please add your Groq API key."
    exit 1
fi

echo "✅ Environment configuration loaded"

# Stop existing containers
echo "🛑 Stopping existing containers..."
docker-compose down --remove-orphans

# Build and start services
echo "🔨 Building and starting services..."
docker-compose up --build -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Health check loop
echo "🔍 Running health checks..."
max_attempts=30
attempt=1

while [ $attempt -le $max_attempts ]; do
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Application health check passed!"
        break
    fi

    echo "⏳ Attempt $attempt/$max_attempts - waiting for application to be ready..."
    sleep 5
    attempt=$((attempt + 1))
done

if [ $attempt -gt $max_attempts ]; then
    echo "❌ Health check failed after $max_attempts attempts"
    echo "📋 Checking service logs..."
    docker-compose logs shopping-assistant
    exit 1
fi

# Check Weaviate
echo "🔍 Checking Weaviate..."
if curl -f http://localhost:8080/v1/meta > /dev/null 2>&1; then
    echo "✅ Weaviate is running"
else
    echo "⚠️  Weaviate health check failed"
fi

# Check Redis
echo "🔍 Checking Redis..."
if docker-compose exec redis redis-cli ping | grep -q "PONG"; then
    echo "✅ Redis is running"
else
    echo "⚠️  Redis health check failed"
fi

# Final status
echo ""
echo "🎉 Deployment successful!"
echo "🌐 Application: http://localhost:8000"
echo "📚 API Docs: http://localhost:8000/docs"
echo "🔍 Health Check: http://localhost:8000/health"
echo "🧠 Weaviate: http://localhost:8080"
echo "📊 Redis: localhost:6379"
echo ""
echo "📋 Useful commands:"
echo "  View logs: docker-compose logs -f shopping-assistant"
echo "  Stop services: docker-compose down"
echo "  Restart: docker-compose restart"
echo "  Rebuild: docker-compose up --build -d"
echo ""
echo "🧪 Test the API:"
echo "  curl http://localhost:8000/health"
echo "  curl -X POST http://localhost:8000/api/v1/shopping/query \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"q\": \"What is your return policy?\"}'"
