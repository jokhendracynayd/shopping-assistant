# 🛍️ Shopping Assistant

An AI-powered shopping assistant built with LangChain, LangGraph, and FastAPI, featuring streaming responses and vector search capabilities.

## ✨ Features

- **AI-Powered Responses**: Built with Groq, OpenAI, and Anthropic LLMs
- **Streaming API**: Real-time streaming responses using Server-Sent Events (SSE)
- **Vector Search**: Multiple vector database support (Weaviate, FAISS, ChromaDB, pgvector)
- **RAG Pipeline**: Advanced retrieval-augmented generation
- **FastAPI Backend**: Modern, fast web framework with automatic API documentation
- **Docker Support**: Containerized deployment for easy scaling
- **Health Checks**: Comprehensive health monitoring and readiness probes
- **Rate Limiting**: Built-in request throttling and security
- **Input Sanitization**: Security-focused input validation and cleaning

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   FastAPI App   │    │   LangGraph      │    │   Vector DB     │
│   (API Layer)   │◄──►│   (Orchestration)│◄──►│   (Weaviate)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Redis Cache   │    │   LLM Clients    │    │   Document      │
│   (Session)     │    │   (Groq/OpenAI)  │    │   Storage      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- Docker and Docker Compose
- Groq API key (required)
- Optional: OpenAI, Anthropic API keys

### Local Development

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd shopping-assistant
   ```

2. **Set up environment variables**
   ```bash
   cp env.example .env
   # Edit .env with your API keys
   ```

3. **Deploy locally with Docker Compose**
   ```bash
   chmod +x deploy-local.sh
   ./deploy-local.sh
   ```

4. **Access the application**
   - API: http://localhost:8000
   - Documentation: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health

### Manual Local Setup

1. **Install dependencies**
   ```bash
   pip install uv
   uv sync
   ```

2. **Start services**
   ```bash
   docker-compose up -d redis weaviate
   ```

3. **Run the application**
   ```bash
   python main.py
   ```

## ☁️ AWS ECS Deployment

### Prerequisites

- AWS CLI configured with appropriate permissions
- Terraform installed
- Docker installed

### Step 1: Set up AWS Secrets

```bash
cd aws
chmod +x setup-secrets.sh
./setup-secrets.sh
```

This will create the following secrets in AWS Secrets Manager:
- `shopping-assistant/groq-api-key`
- `shopping-assistant/weaviate-url`
- `shopping-assistant/redis-url`
- Optional: OpenAI, Anthropic, Weaviate API keys

### Step 2: Deploy Infrastructure with Terraform

```bash
cd aws/terraform
chmod +x deploy.sh
./deploy.sh
```

This will create:
- VPC with public/private subnets
- ECS cluster and service
- Application Load Balancer
- ECR repository
- CloudWatch log groups
- IAM roles and security groups

### Step 3: Deploy Application to ECS

```bash
cd aws
chmod +x deploy-ecs.sh
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
./deploy-ecs.sh
```

### Alternative: Manual ECS Deployment

1. **Build and push Docker image**
   ```bash
   docker build -t shopping-assistant .
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
   docker tag shopping-assistant:latest $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/shopping-assistant:latest
   docker push $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/shopping-assistant:latest
   ```

2. **Update ECS service**
   ```bash
   aws ecs update-service --cluster shopping-assistant-cluster --service shopping-assistant-service --force-new-deployment
   ```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `GROQ_API_KEY` | Groq API key for LLM access | - | ✅ |
| `OPENAI_API_KEY` | OpenAI API key (optional) | - | ❌ |
| `ANTHROPIC_API_KEY` | Anthropic API key (optional) | - | ❌ |
| `WEAVIATE_URL` | Weaviate vector database URL | - | ✅ |
| `WEAVIATE_API_KEY` | Weaviate API key (optional) | - | ❌ |
| `REDIS_URL` | Redis cache URL | `redis://localhost:6379/0` | ❌ |
| `LOG_LEVEL` | Logging level | `INFO` | ❌ |
| `DEFAULT_TEMPERATURE` | LLM temperature | `0.0` | ❌ |
| `LLM_TIMEOUT_SECONDS` | LLM request timeout | `30` | ❌ |
| `RATE_LIMITING_ENABLED` | Enable rate limiting | `true` | ❌ |

### Docker Compose Services

- **shopping-assistant**: Main application
- **redis**: Cache and session storage
- **weaviate**: Vector database
- **postgres**: Optional PostgreSQL with pgvector
- **chroma**: Optional ChromaDB vector database

## 📡 API Endpoints

### Health Checks
- `GET /health` - Basic health check
- `GET /health/ready` - Readiness probe
- `GET /health/live` - Liveness probe

### Shopping Assistant
- `POST /api/v1/shopping/query` - Regular query endpoint
- `POST /api/v1/shopping/query/stream` - Streaming query endpoint
- `POST /api/v1/shopping/add-documents` - Add documents to vector store

### Streaming Response Format

The streaming endpoint returns Server-Sent Events (SSE) with JSON payloads:

```json
{"chunk_type": "intent", "intent": "FAQ"}
{"chunk_type": "metadata", "context_count": 3, "retrieval_quality": "high"}
{"chunk_type": "content", "content": "Based on our return policy...", "is_final": false}
{"chunk_type": "final", "confidence": "high", "quality_metrics": {...}}
{"chunk_type": "complete"}
```

## 🧪 Testing

### Test the API

```bash
# Health check
curl http://localhost:8000/health

# Regular query
curl -X POST http://localhost:8000/api/v1/shopping/query \
  -H "Content-Type: application/json" \
  -d '{"q": "What is your return policy?"}'

# Streaming query
curl -X POST http://localhost:8000/api/v1/shopping/query/stream \
  -H "Content-Type: application/json" \
  -d '{"q": "What is your return policy?"}' \
  --no-buffer

# Add documents
curl -X POST http://localhost:8000/api/v1/shopping/add-documents \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {
        "id": "doc1",
        "text": "Our return policy allows returns within 30 days.",
        "metadata": {"category": "policy", "title": "Return Policy"}
      }
    ]
  }'
```

## 📊 Monitoring

### CloudWatch Metrics (AWS)

- ECS service metrics (CPU, memory, network)
- Application Load Balancer metrics
- Custom application metrics

### Local Monitoring

- Docker container logs: `docker-compose logs -f shopping-assistant`
- Application logs: `tail -f logs/app.log`
- Health check endpoint: `/health/ready`

## 🔒 Security

- Input sanitization and validation
- Rate limiting and request size limits
- CORS configuration
- Non-root Docker containers
- AWS IAM roles and security groups
- Secrets management via AWS Secrets Manager

## 📈 Scaling

### Local Scaling

```bash
# Scale the application
docker-compose up --scale shopping-assistant=3 -d

# Scale Redis
docker-compose up --scale redis=3 -d
```

### AWS Scaling

- **Auto-scaling**: CPU-based auto-scaling (70% threshold)
- **Manual scaling**: Update desired count
- **Load balancer**: Distributes traffic across instances

```bash
# Scale ECS service
aws ecs update-service \
  --cluster shopping-assistant-cluster \
  --service shopping-assistant-service \
  --desired-count 5
```

## 🛠️ Development

### Project Structure

```
shopping-assistant/
├── app/                    # Application code
│   ├── api/               # API endpoints
│   ├── agents/            # AI agents
│   ├── config/            # Configuration
│   ├── core/              # Core functionality
│   ├── database/          # Database clients
│   ├── graphs/            # LangGraph workflows
│   ├── llm/               # LLM clients
│   ├── models/            # Data models
│   ├── prompts/           # Prompt templates
│   ├── retrievers/        # Vector store retrievers
│   ├── services/          # Business logic
│   └── utils/             # Utilities
├── aws/                   # AWS deployment files
│   ├── terraform/         # Infrastructure as Code
│   ├── deploy-ecs.sh      # ECS deployment script
│   └── setup-secrets.sh   # Secrets setup script
├── docs/                  # Documentation
├── tests/                 # Test suite
├── Dockerfile             # Docker image
├── docker-compose.yml     # Local services
├── deploy-local.sh        # Local deployment script
└── pyproject.toml         # Python project config
```

### Adding New Features

1. **New LLM Provider**: Extend `app/llm/base.py`
2. **New Vector Store**: Extend `app/retrievers/base.py`
3. **New API Endpoint**: Add to `app/api/v1/shopping.py`
4. **New Graph Node**: Add to `app/graphs/shopping_graph.py`

### Code Quality

```bash
# Run pre-commit hooks
pre-commit run --all-files

# Format code
black app/ tests/

# Lint code
ruff check app/ tests/

# Type checking
mypy app/

# Run tests
pytest tests/
```

## 🚨 Troubleshooting

### Common Issues

1. **Weaviate Connection Failed**
   - Check if Weaviate container is running
   - Verify network connectivity
   - Check Weaviate logs: `docker-compose logs weaviate`

2. **LLM API Errors**
   - Verify API keys in `.env` or AWS Secrets Manager
   - Check API rate limits
   - Verify network connectivity

3. **ECS Service Not Starting**
   - Check CloudWatch logs
   - Verify IAM permissions
   - Check security group rules

4. **Health Check Failures**
   - Check application logs
   - Verify dependencies are healthy
   - Check resource constraints

### Debug Commands

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f [service-name]

# Execute commands in container
docker-compose exec shopping-assistant bash

# Check network connectivity
docker-compose exec shopping-assistant ping weaviate

# Monitor resources
docker stats
```

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [LangChain Documentation](https://python.langchain.com/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Weaviate Documentation](https://weaviate.io/developers/weaviate)
- [AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)
- [Terraform Documentation](https://www.terraform.io/docs)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run pre-commit hooks
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Check the troubleshooting section
- Review the API documentation at `/docs`
- Check the application logs

---

**Happy Shopping! 🛍️✨**
