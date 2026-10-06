# AWS Pricing Skill - Implementation Summary

## What was delivered

A complete **AWS pricing lookup skill** for pi, with support for **13 AWS services** in eu-west-1.

### Services covered

1. **EC2** — compute instances (on-demand hourly)
2. **RDS** — managed databases (on-demand hourly)
3. **S3** — object storage (per GB-month by storage class)
4. **Lambda** — serverless compute (per GB-sec + per request)
5. **EKS** — managed Kubernetes (cluster + Fargate pricing)
6. **Fargate** — container compute (per vCPU-hour + per GB-hour)
7. **ElastiCache** — managed cache (on-demand hourly)
8. **SQS** — message queue (per million requests by queue type)
9. **SNS** — pub/sub messaging (per million by delivery endpoint)
10. **EventBridge** — event routing (per million events + archive storage)
11. **API Gateway** — API hosting (per million by API type: REST/HTTP/WebSocket)
12. **ALB/NLB** — load balancing (hourly + capacity unit pricing)
13. **VPC** — networking (NAT GW, VPN, Transit GW, Endpoints, Peering, EIP)

---

## Key features

### ✅ Smart caching
- **Region-specific downloads** — fetches only eu-west-1 JSON slices (~5–15 MB per service vs. 200 MB global files)
- **2-week TTL** — automatic refresh, graceful re-download on corruption
- **No network on repeat queries** — all subsequent calls are instant

### ✅ Zero friction
- **`uv run` ready** — inline script metadata, no pip/venv needed
- **No AWS credentials required** — uses public AWS Bulk Pricing API
- **Single file + symlink** — `~/.agents/skills/aws-pricing/aws_pricing.py`

### ✅ Rich query capabilities
- **Exact-match filters** — case-insensitive attribute matching (default)
- **Substring filters** — `contains:` prefix for partial matches (e.g., EKS/Fargate usagetypes)
- **Opt-out location guard** — `location: None` to skip auto-region filtering (VPC Peering)
- **Multi-tier pricing** — returns highest non-zero tier price (skips free tiers for SNS)

### ✅ Skill-ready integration
- **SKILL.md with prominent warning section** — mandatory clarifying questions before any calculation
- **Structured guidance per service** — what to ask users about sizing, config, usage patterns
- **Python API** — direct import for programmatic access without subprocess overhead

---

## Usage: CLI

### Basic queries (instant from cache)
```bash
uv run ~/.agents/skills/aws-pricing/aws_pricing.py ec2 t3.medium
uv run ~/.agents/skills/aws-pricing/aws_pricing.py rds db.r5.large --engine PostgreSQL --deployment Multi-AZ
uv run ~/.agents/skills/aws-pricing/aws_pricing.py s3 --storage-class "Infrequent Access"
uv run ~/.agents/skills/aws-pricing/aws_pricing.py lambda
uv run ~/.agents/skills/aws-pricing/aws_pricing.py eks
uv run ~/.agents/skills/aws-pricing/aws_pricing.py elasticache cache.r6g.large

# NEW services
uv run ~/.agents/skills/aws-pricing/aws_pricing.py sqs --queue-type FIFO
uv run ~/.agents/skills/aws-pricing/aws_pricing.py sns
uv run ~/.agents/skills/aws-pricing/aws_pricing.py eventbridge
uv run ~/.agents/skills/aws-pricing/aws_pricing.py apigw
uv run ~/.agents/skills/aws-pricing/aws_pricing.py alb
uv run ~/.agents/skills/aws-pricing/aws_pricing.py nlb
uv run ~/.agents/skills/aws-pricing/aws_pricing.py vpc
```

### Output format (JSON)
```json
{
  "service": "EC2",
  "instance_type": "t3.medium",
  "os": "Linux",
  "tenancy": "Shared",
  "region": "eu-west-1",
  "price_usd_per_hour": 0.0456
}
```

---

## Usage: Python API

### Direct import (zero subprocess overhead)
```python
sys.path.insert(0, "~/.agents/skills/aws-pricing")
from aws_pricing import AWSPricing

p = AWSPricing()  # region defaults to eu-west-1
ec2_price = p.get_ec2_price("m5.xlarge")
rds_price = p.get_rds_price("db.r5.large", engine="PostgreSQL", deployment="Multi-AZ")
s3_price = p.get_s3_price("Infrequent Access")
lambda_info = p.get_lambda_price()  # (gb_sec, requests)
sqs_price = p.get_sqs_price("FIFO")
sns_prices = p.get_sns_price()  # dict of all endpoints
apigw_prices = p.get_api_gateway_price()
alb_prices = p.get_alb_price()
vpc_prices = p.get_vpc_price()  # dict of 9 networking line items
```

---

## Skill behavior: clarifying questions requirement

The SKILL.md now includes a prominent **⚠️ "Before You Calculate"** section that mandates:

1. **ASK before calculating** — Never assume sizing or defaults
2. **Per-service guidance** — Structured questions for Storage, Databases, Compute, Messaging, Networking
3. **Propose, don't assume** — Offer options and let the user decide

Example questions the skill should ask:
- **S3:** Storage class? Volume (GB/TB)? Access pattern?
- **RDS:** Instance type? Engine? Single-AZ vs Multi-AZ? Workload pattern?
- **EC2:** Instance size? Linux or Windows? Expected uptime?
- **SQS:** Standard, FIFO, or Fair? Expected volume?
- **API Gateway:** REST (full features) or HTTP (cheaper)? WebSocket?
- **NAT Gateway:** Expected data processing (GB/month)?

---

## File locations

| Location | Purpose |
|---|---|
| `~/.agents/skills/aws-pricing/aws_pricing.py` | Main script (uv-ready) |
| `~/.agents/skills/aws-pricing/SKILL.md` | Skill definition + documentation |
| `~/.pi/agent/skills/aws-pricing` | Symlink (for pi auto-discovery) |

---

## Sample prices (eu-west-1, as of cache date)

| Service | Config | Price |
|---|---|---|
| EC2 t3.medium | Linux | $0.0456/hr |
| RDS db.r5.large | PostgreSQL, Multi-AZ | $0.560/hr |
| S3 Standard | Per GB-month | $0.023 |
| Lambda compute | Per GB-sec | $1.67e-05 |
| SQS Standard | Per M requests | $0.40 |
| SNS API requests | Per M | $0.50 |
| API Gateway REST | Per M requests | $3.50 |
| API Gateway HTTP | Per M requests | $1.11 |
| ALB | Per hour | $0.0252 |
| NAT Gateway | Per hour | $0.048 |
| NAT Gateway | Per GB data | $0.048 |
| VPC Endpoint | Per AZ-hour | $0.011 |

---

## Technical notes

### Filter engine enhancements
- **`contains:` prefix** — substring matching on attributes (used for EKS, Fargate, NAT Gateway)
- **`location: None` opt-out** — skip auto-region guard for products using different location schemas (VPC Peering)
- **Paid-tier filtering** — SNS returns highest non-zero price per endpoint type (skips free tiers)

### Architecture
- **`_iter_products()`** — core product matching engine with flexible filters
- **`_first_price()`** — returns first matching on-demand price, or None
- **`_load_service()`** — lazy-load + cache service pricing JSON
- **`_get_service_url()`** — prefer region-specific index over global file
- **Class methods** — `AWSPricing` wraps CLI functions for direct API access

### Data sources
- **Index:** `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json`
- **Region index:** `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{ServiceCode}/current/region_index.json`
- **Service pricing:** `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{ServiceCode}/current/{region}/index.json`

All endpoints HTTPS-only; URL validation enforced.

---

## Next steps (optional)

1. **Add CLI piping** — chain multiple queries into a CSV RFP template
2. **Reserved Instance calculator** — apply savings plan multipliers (typically 30–60% discount)
3. **Data transfer cost matrix** — cross-region, inter-AZ, egress pricing
4. **Spot pricing** — fetch current spot market rates (requires EC2 API call)
5. **Per-region CLI flag** — `--region us-east-1` to query other regions
6. **Monthly calculator** — `--hours-per-month`, `--data-gb`, etc. to output total bill
