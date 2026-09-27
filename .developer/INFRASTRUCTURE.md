# Infrastructure & Containerization Standards

## Purpose

Define standards for containerizing the Bard application and managing infrastructure as code. This ensures consistent, reproducible deployments across environments.

---

## Containerization Strategy

### Current State

| Component | Status |
|-----------|--------|
| Application Dockerfile | ✅ Exists (`Dockerfile`) |
| Database docker-compose | ✅ Exists (`docker-compose.yml`) |
| Multi-stage build | ❌ Not implemented |
| Health checks | ❌ Minimal |
| Non-root user | ❌ Not implemented |
| Build args for versioning | ❌ Not implemented |

### Target State

```dockerfile
# Multi-stage build
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim AS runtime
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN useradd --no-create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Standards

1. **Multi-stage builds** — Separate build and runtime stages
2. **Non-root user** — Run as `appuser` (UID 1000)
3. **Health checks** — HTTP endpoint + process check
4. **Version labels** — `org.opencontainers.image.version`, `org.opencontainers.image.source`
5. **No secrets in images** — Use build-time args only for public metadata
5. **Layer caching** — Copy dependency files first, then source
6. **Distroless/slim base** — Prefer `python:3.12-slim` over full image

---

## Docker Compose Standards

### Development (`docker-compose.yml`)

- Database only (current approach)
- App runs locally via `uvicorn --reload`
- Port mapping: host 5433 → container 5432

### Production (`docker-compose.prod.yml`)

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    image: bard-dm-assistant:${VERSION}
    environment:
      - APP_ENV=production
      - DATABASE_URL=postgresql+psycopg://${DB_USER}:${DB_PASS}@db:5432/${DB_NAME}
      - OIDC_ISSUER_URL=${OIDC_ISSUER_URL}
      - OIDC_AUDIENCE=${OIDC_AUDIENCE}
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'

  db:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_DB=${DB_NAME}
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASS}
    volumes:
      - bard_postgres:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  bard_postgres:
```

### Environment Files

| File | Purpose |
|------|---------|
| `.env.example` | Template with all required variables |
| `.env.development` | Local development overrides (gitignored) |
| `.env.production` | Production values (never committed) |

---

## Terraform Standards

### Module Structure

```
infrastructure/
├── main.tf                 # Root module
├── variables.tf            # Input variables
├── outputs.tf              # Output values
├── providers.tf            # Provider configuration
├── backend.tf              # State backend (S3 + DynamoDB)
├── modules/
│   ├── vpc/               # VPC, subnets, NAT gateways
│   ├── rds/               # PostgreSQL + pgvector (RDS or Cloud SQL)
│   ├── ecs/               # ECS Fargate service + task definition
│   ├── alb/               # Application Load Balancer
│   ├── acm/               # SSL certificate
│   ├── route53/           # DNS records
│   ├── secrets/           # Secrets Manager for DB creds, OIDC
│   └── monitoring/        # CloudWatch logs, metrics, alarms
├── environments/
│   ├── development/
│   │   ├── main.tf
│   │   └── terraform.tfvars
│   ├── staging/
│   │   ├── main.tf
│   │   └── terraform.tfvars
│   └── production/
│       ├── main.tf
│       └── terraform.tfvars
└── .github/workflows/
    └── terraform.yml       # CI/CD pipeline
```

### Provider Standards

```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
  backend "s3" {
    bucket         = "bard-terraform-state"
    key            = "infrastructure/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "bard-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "bard"
      Environment = var.environment
      ManagedBy   = "terraform"
      Repository  = "github.com/MRBrown91/bard"
    }
  }
}
```

### Variable Standards

```hcl
variable "environment" {
  description = "Deployment environment"
  type        = string
  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be development, staging, or production."
  }
}

variable "app_version" {
  description = "Application version to deploy"
  type        = string
  default     = "latest"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}
```

### Security Standards

1. **No hardcoded secrets** — Use AWS Secrets Manager + IAM roles
2. **Private subnets** — App and DB in private subnets only
3. **Security groups** — Least privilege (ALB → App → DB)
4. **Encryption** — At rest (RDS, S3, EBS) and in transit (TLS 1.2+)
5. **IAM least privilege** — Task execution roles with minimal permissions
6. **VPC flow logs** — Enabled for audit

---

## CI/CD Pipeline Standards

### GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -e '.[dev]'
      - name: Run linter
        run: ruff check .
      - name: Run type checker
        run: mypy app/
      - name: Run tests
        run: pytest --tb=short

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy-staging:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Deploy to staging
        run: ./scripts/deploy.sh staging

  deploy-production:
    needs: build
    if: github.event_name == 'release' && github.event.action == 'published'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Deploy to production
        run: ./scripts/deploy.sh production
```

---

## Deployment Strategy

### Environments

| Environment | Purpose | Trigger | Approval |
|-------------|---------|---------|----------|
| Development | Local only | Manual | None |
| Staging | Integration testing | Push to `main` | Auto |
| Production | Live traffic | GitHub Release | Manual |

### Rollout Strategy

- **Blue/Green** for production (ALB target group swap)
- **Rolling** for staging (ECS rolling update)
- **Health checks** must pass before traffic switch
- **Rollback** on health check failure (< 5 min)

---

## Monitoring & Observability

### Required Metrics

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Request latency (p95) | ALB / App | > 2s |
| Error rate (5xx) | ALB / App | > 1% |
| DB CPU / Memory | RDS | > 80% |
| DB connections | RDS | > 80% max |
| App memory / CPU | ECS | > 80% |
| Container restarts | ECS | > 0 in 5m |

### Logging

- **Structured JSON logs** — stdout/stderr captured by CloudWatch
- **Correlation IDs** — Request ID propagated through all services
- **Log levels** — DEBUG (dev), INFO (staging), WARN (prod)
- **Retention** — 30 days (staging), 1 year (prod)

---

## Disaster Recovery

| Component | RPO | RTO | Strategy |
|-----------|-----|-----|----------|
| PostgreSQL | < 1 min | < 15 min | Automated backups + point-in-time recovery |
| Application | 0 | < 5 min | Blue/Green deploy, container image rollback |
| Secrets | 0 | < 5 min | Secrets Manager replication |

---

## Cost Optimization

1. **Right-size instances** — Start small, scale based on metrics
2. **Spot instances** — For non-critical batch workloads (future)
3. **Auto-scaling** — ECS service auto-scaling on CPU/memory
4. **DB instance scheduling** — Stop dev/staging DBs nights/weekends
5. **Cleanup** — TTL on ECR images, CloudWatch logs retention

---

## Documentation Requirements

Every infrastructure change must update:

1. `INFRASTRUCTURE.md` — If standards change
2. `DECISIONS.md` — ADR for major architectural choices
3. `HISTORY.md` — Milestone entry
4. Module README — For each Terraform module

---

## Phased Implementation Plan

### Phase 1: Containerize (Week 1)

- [ ] Multi-stage Dockerfile
- [ ] Health check endpoint enhancement
- [ ] `docker-compose.prod.yml`
- [ ] GitHub Actions CI pipeline

### Phase 2: Terraform Foundation (Week 2)

- [ ] VPC module
- [ ] RDS module (pgvector)
- [ ] Secrets Manager setup
- [ ] State backend (S3 + DynamoDB)

### Phase 3: Deploy Pipeline (Week 3)

- [ ] ECS Fargate module
- [ ] ALB + ACM module
- [ ] GitHub Actions deploy workflow
- [ ] Staging environment

### Phase 4: Production Hardening (Week 4)

- [ ] Production environment
- [ ] Monitoring/alerting
- [ ] Blue/Green deployment
- [ ] Runbook documentation

---

## Decision Log

| Decision | ADR | Status |
|----------|-----|--------|
| Multi-stage Docker builds | — | Planned |
| ECS Fargate for compute | — | Planned |
| RDS PostgreSQL + pgvector | — | Planned |
| GitHub Actions for CI/CD | — | Planned |
| Terraform state in S3 | — | Planned |