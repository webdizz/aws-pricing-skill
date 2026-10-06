# AWS Pricing Skill

Retrieve real AWS on-demand pricing for 13 services in eu-west-1 using the official AWS Bulk Pricing API. Built for cost estimation in RFPs, infrastructure planning, and pricing comparisons.

## Features

- **13 AWS Services**: EC2, RDS, S3, Lambda, EKS, Fargate, ElastiCache, SQS, SNS, EventBridge, API Gateway, ALB/NLB, VPC
- **Zero Dependencies**: Pure Python 3.11+ with stdlib only
- **Smart Caching**: 2-week TTL with automatic refresh and manual override
- **Dual Interface**: CLI for quick lookups, Python API for programmatic access
- **Structured Guidance**: "Ask Before Calculate" prompts prevent dangerous assumptions
- **Monthly Formulas**: Ready-to-use cost calculation formulas included

## Quick Start

### CLI Usage

```bash
# EC2 pricing
uv run aws_pricing.py ec2 t3.medium
uv run aws_pricing.py ec2 m5.xlarge --os Linux

# RDS with options
uv run aws_pricing.py rds db.r5.large --engine PostgreSQL --deployment Multi-AZ

# Serverless services
uv run aws_pricing.py lambda
uv run aws_pricing.py sqs --queue-type FIFO
uv run aws_pricing.py sns
uv run aws_pricing.py eventbridge

# Networking
uv run aws_pricing.py apigw
uv run aws_pricing.py alb
uv run aws_pricing.py nlb
uv run aws_pricing.py vpc
```

## Service Coverage

| Category | Services |
|----------|----------|
| **Compute** | EC2, EKS, Fargate |
| **Database** | RDS |
| **Storage** | S3 |
| **Serverless** | Lambda |
| **Messaging** | SQS, SNS, EventBridge |
| **Networking** | API Gateway, ALB, NLB, VPC |
| **Cache** | ElastiCache |

## Key Capabilities

### EC2

```bash
uv run aws_pricing.py ec2 t3.medium                    # Default: Linux, Shared tenancy
uv run aws_pricing.py ec2 c5.2xlarge --os Windows      # Windows OS
uv run aws_pricing.py ec2 m5.large --tenancy Dedicated # Dedicated instance
```

### RDS

```bash
uv run aws_pricing.py rds db.t3.medium                                    # Default: MySQL, Single-AZ
uv run aws_pricing.py rds db.r5.large --engine PostgreSQL --deployment Multi-AZ
uv run aws_pricing.py rds db.r5.xlarge --engine "Aurora PostgreSQL"
```

### S3

```bash
uv run aws_pricing.py s3                              # General Purpose (default)
uv run aws_pricing.py s3 --storage-class "Archive"    # Archive storage
```

### Lambda
Returns both `price_usd_per_gb_second` and `price_usd_per_request`.

### SQS / SNS / EventBridge
Returns **prices per million requests** (USD). Queue types for SQS: `Standard` (default), `FIFO`, `Fair` (high-throughput FIFO).

### API Gateway
```bash
uv run aws_pricing.py apigw
```
Returns REST ($3.50/M), HTTP ($1.11/M, ~68% cheaper), WebSocket, and connection-minute rates.

### Networking (VPC)
NAT Gateway, VPN, Transit Gateway, VPC Endpoints, Peering, Elastic IPs — hourly and data-transfer pricing.

## Before You Calculate

> **Always ask before assuming defaults**, especially for:
> - **Storage**: What storage class? How often accessed?
> - **Databases**: Single-AZ or Multi-AZ? Engine type?
> - **Compute**: Instance type and OS?
> - **Data transfer**: Same AZ, cross-AZ, or egress?

Never hard-code instance sizes or storage volumes without confirming with stakeholders.


## Caching & Refresh

```bash
# Check cache status and TTL
uv run aws_pricing.py cache-status

# Force refresh a service
uv run aws_pricing.py refresh AmazonEC2
uv run aws_pricing.py refresh AmazonRDS

# List all available services
uv run aws_pricing.py list-services
```

Cache files stored in `.pricing_cache/` with 2-week TTL. AWS pricing is stable enough for this interval; refresh manually if needed.

## Advanced: Generic Search

For services or filters not exposed by the main commands:

```bash
uv run aws_pricing.py search AmazonEC2 '{"instanceType":"c5.xlarge","operatingSystem":"Linux"}'

# Substring matching with contains:
uv run aws_pricing.py search AmazonEKS '{"usagetype":"contains:Fargate-vCPU"}' --limit 3

# Custom region
uv run aws_pricing.py search AmazonRDS '{"instanceType":"db.r5.large"}' --region us-east-1
```

## Monthly Cost Formulas

| Resource | Formula |
|----------|---------|
| EC2 / RDS / ElastiCache | `hourly_price × 730` |
| EKS cluster | `0.1 × 730 = $73/month` |
| Fargate | `(vcpu_count × vcpu_price + gb_ram × gb_price) × 730` |
| Lambda compute | `invocations × avg_duration_sec × gb_ram × gb_sec_price` |
| Lambda requests | `invocations × request_price` |
| S3 | `gb_stored × gb_month_price` |
| NAT Gateway | `(hourly_price × 730) + (gb_processed × gb_price)` |
| ALB | `(hourly_rate × 730) + (lcu_count × lcu_price × 730)` |

## Limitations

- **Default region**: eu-west-1 (use `--region` flag for others, less tested)
- **Pricing type**: On-demand only (Reserved Instances and Spot pricing are Phase 2)
- **No credentials**: Uses public AWS pricing API; cached data is at most 2 weeks old

## Architecture

Single-file, zero-dependency design:

1. **Cache Manager** — Fetches and stores AWS pricing JSON files with TTL
2. **Service Loader** — Lazy-loads region-specific pricing indexes
3. **Query Engine** — Filters and returns structured pricing data
4. **CLI Layer** — Exposes all services via simple, memorable commands
5. **Python API** — Direct import for programmatic access (zero subprocess overhead)

## Why This Approach

- **No external dependencies** → works offline after first fetch
- **Small region-specific files** → 50KB indexes vs. GB-scale full datasets
- **2-week cache** → AWS pricing changes slowly; minimal stale data risk
- **Type hints throughout** → IDE autocomplete, runtime safety
- **Structured guidance** → prevents common RFP estimation mistakes