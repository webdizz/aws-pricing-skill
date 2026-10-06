---
name: aws-pricing
description: >
  Retrieve real AWS prices for eu-west-1 using the official
  AWS Bulk Pricing API. Use this skill whenever you need to estimate, quote, or
  compare AWS service costs, build RFP pricing tables, size infrastructure
  budgets, or answer any question involving AWS prices. Covers EC2, RDS, S3,
  Lambda, EKS, Fargate, ElastiCache, SQS, SNS, EventBridge, API Gateway, ALB/NLB,
  and VPC. 
---

# AWS Pricing Skill

Provides instant on-demand pricing for AWS services in **eu-west-1 (Ireland)**.
Data comes from the official AWS Bulk Pricing API, cached locally for 2 weeks.
No AWS account or credentials required.

## ⚠️ Before You Calculate: Ask Clarifying Questions

**Do NOT make assumptions about infrastructure sizing, configuration, or usage patterns.**
Before retrieving prices or building estimates, **ask the user:**

### Storage (S3, EBS, etc.)
- Storage class: Standard, Infrequent Access, Archive, Intelligent-Tiering?
- Volume: How much data (GB, TB)?
- Access pattern: Frequent, occasional, rare?

### Databases (RDS, Aurora, ElastiCache)
- Instance type/size? (e.g., `db.t3.medium`, `db.r5.xlarge`)
- Engine? (MySQL, PostgreSQL, Aurora, etc.)
- Deployment: Single-AZ, Multi-AZ, or Aurora (HA built-in)?
- Workload pattern: OLTP, reporting, read-heavy, write-heavy?
- Backup/retention: Default 7 days, extended?

### Compute (EC2, EKS, Lambda)
- Instance type/size? (e.g., `t3.medium`, `m5.large`)
- Operating system? (Linux, Windows)
- Expected utilization? (hours/day, days/month)
- For Lambda: invocation count, average duration, memory?
- For EKS: managed node groups, Fargate, or both?

### Messaging & Eventing (SQS, SNS, EventBridge)
- Queue type? (Standard, FIFO, Fair/high-throughput)
- Expected volume? (messages/sec, requests/month)
- Delivery pattern? (publish-subscribe, fan-out, async)
- SNS delivery endpoints? (SQS, HTTP, email, Lambda, mobile)

### Networking (API Gateway, ALB, NLB, VPC)
- API type? (REST, HTTP, WebSocket)
- Expected request volume per month?
- Load balancer type? (ALB for HTTP/HTTPS, NLB for extreme throughput)
- Data transfer: intra-region, cross-region, inter-AZ?
- NAT Gateway data volume (GB/month)?

**Propose options and recommendations**, but do **NOT** select one unless explicitly asked. Always let the user decide based on their requirements and constraints.

## Setup

The wrapper script lives at:
```
~/.agents/skills/aws-pricing/aws_pricing.py
```

Run it with `uv run` — no installation needed:
```bash
uv run ~/.agents/skills/aws-pricing/aws_pricing.py <command> [options]
```

## Quick-reference: all commands

| Command | What it returns |
|---|---|
| `ec2 <type>` | On-demand hourly price (USD) |
| `rds <type>` | On-demand hourly price (USD) |
| `s3` | Storage price per GB-month |
| `lambda` | Compute (GB-sec) + request price |
| `eks` | Cluster-hour + Fargate prices |
| `fargate` | vCPU-hour + GB-hour prices |
| `elasticache <type>` | On-demand hourly price (USD) |
| `sqs` | Price per million requests |
| `sns` | API requests + delivery prices per million |
| `eventbridge` | Custom events, scheduler, archive prices |
| `apigw` | REST, HTTP, WebSocket API prices |
| `alb` | ALB hourly + LCU prices |
| `nlb` | NLB hourly + NLCU prices |
| `vpc` | NAT GW, VPN, TGW, Endpoints, Peering, EIP |
| `search <service> '<json>'` | Raw product search with filters |
| `list-services` | All available AWS service codes |
| `cache-status` | Show cached files & expiry dates |
| `refresh <service>` | Force-refresh a service's cache |

All commands accept `--region` (default: `eu-west-1`).

---

## Service-by-service usage

### EC2
```bash
uv run aws_pricing.py ec2 t3.medium
uv run aws_pricing.py ec2 m5.xlarge --os Linux
uv run aws_pricing.py ec2 c5.2xlarge --os Windows
uv run aws_pricing.py ec2 m5.large --tenancy Dedicated
```
**Key `--os` values:** `Linux`, `Windows`, `RHEL`, `SUSE`  
**Key `--tenancy` values:** `Shared` (default), `Dedicated`, `Host`

### RDS
```bash
uv run aws_pricing.py rds db.t3.medium
uv run aws_pricing.py rds db.r5.large --engine PostgreSQL --deployment Multi-AZ
uv run aws_pricing.py rds db.r5.xlarge --engine "Aurora PostgreSQL"
uv run aws_pricing.py rds db.m5.large --engine MySQL --deployment Single-AZ
```
**Engine strings:** `MySQL`, `PostgreSQL`, `Oracle`, `SQL Server`,
`Aurora MySQL`, `Aurora PostgreSQL`  
**Deployment:** `Single-AZ` (default), `Multi-AZ`  
> Aurora only has `Single-AZ` — it manages high-availability internally.

### S3
```bash
uv run aws_pricing.py s3
uv run aws_pricing.py s3 --storage-class "Infrequent Access"
uv run aws_pricing.py s3 --storage-class "Archive"
uv run aws_pricing.py s3 --storage-class "Intelligent-Tiering"
```
**Storage class strings:** `General Purpose`, `Infrequent Access`, `Archive`,
`Archive Instant Retrieval`, `Intelligent-Tiering`

### Lambda
```bash
uv run aws_pricing.py lambda
```
Returns both `price_usd_per_gb_second` and `price_usd_per_request`.

### SQS
```bash
uv run aws_pricing.py sqs                       # Standard queue
uv run aws_pricing.py sqs --queue-type FIFO     # FIFO queue
uv run aws_pricing.py sqs --queue-type Fair     # High-throughput FIFO
```
Returns **price per million requests** (USD).

Queue types: `Standard` (default), `FIFO`, `Fair` (high-throughput FIFO)

### SNS
```bash
uv run aws_pricing.py sns
```
Returns prices per million for: API requests, HTTP/HTTPS, email, SQS delivery (free), Lambda delivery (free), mobile push (GCM/APNS).

### EventBridge
```bash
uv run aws_pricing.py eventbridge
```
Returns: custom event publishing, Scheduler invocations, cross-account events, API Destination invocations, archive storage (per GB-month).

### API Gateway
```bash
uv run aws_pricing.py apigw
```
Returns per-million prices for: REST API requests, HTTP API requests (cheaper), WebSocket messages, WebSocket connection-minutes.

**Choose REST vs HTTP API:**
- REST: `$3.50/M` — full features, WAF, API keys, usage plans
- HTTP: `$1.11/M` — simpler, lower latency, ~68% cheaper

### ALB / NLB
```bash
uv run aws_pricing.py alb    # Application Load Balancer
uv run aws_pricing.py nlb    # Network Load Balancer
```
Returns hourly rate + capacity unit (LCU/NLCU) rate per hour.

**Monthly estimate:** `(0.0252 × 730) + (lcu_count × lcu_price × 730)`

### VPC
```bash
uv run aws_pricing.py vpc
```
Returns:
| Field | Description |
|---|---|
| `nat_gateway_price_usd_per_hour` | NAT Gateway — hourly |
| `nat_gateway_price_usd_per_gb` | NAT Gateway — data processed |
| `vpn_connection_price_usd_per_hour` | Site-to-Site VPN connection |
| `transit_gateway_price_usd_per_hour` | Transit Gateway attachment |
| `transit_gateway_price_usd_per_gb` | Transit Gateway data processing |
| `vpc_endpoint_price_usd_per_hour` | Interface Endpoint per AZ |
| `vpc_peering_price_usd_per_gb` | Cross-AZ VPC Peering data |
| `eip_idle_price_usd_per_hour` | Idle public IPv4 address |
| `eip_inuse_price_usd_per_hour` | In-use public IPv4 address |

### EKS + Fargate
```bash
uv run aws_pricing.py eks      # cluster-hour + Fargate bundle
uv run aws_pricing.py fargate  # vCPU-hour + GB-hour
```

### ElastiCache
```bash
uv run aws_pricing.py elasticache cache.t3.medium
uv run aws_pricing.py elasticache cache.r6g.large --engine Redis
uv run aws_pricing.py elasticache cache.m6g.xlarge --engine Memcached
```

### Generic search (advanced)
```bash
uv run aws_pricing.py search AmazonEC2 '{"instanceType":"c5.xlarge","operatingSystem":"Linux","tenancy":"Shared","capacitystatus":"Used","preInstalledSw":"NA"}'
uv run aws_pricing.py search AmazonRDS '{"instanceType":"db.r5.large"}' --limit 5
```
Filter values prefixed with `contains:` do substring matching:
```bash
uv run aws_pricing.py search AmazonEKS '{"usagetype":"contains:Fargate-vCPU"}' --limit 3
```

---

## Using the Python API directly

When building RFP tables or multi-service estimates, import and call directly:

```python
import subprocess, json, sys

SCRIPT = "/Users/webdizz/.agents/skills/aws-pricing/aws_pricing.py"

def aws_price(*args):
    result = subprocess.run(
        ["uv", "run", SCRIPT, *args],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)

# Examples
ec2   = aws_price("ec2", "m5.xlarge")["price_usd_per_hour"]
rds   = aws_price("rds", "db.r5.large", "--engine", "PostgreSQL", "--deployment", "Multi-AZ")["price_usd_per_hour"]
s3    = aws_price("s3")["price_usd_per_gb_month"]
lamb  = aws_price("lambda")
eks   = aws_price("eks")
cache = aws_price("elasticache", "cache.r6g.large")["price_usd_per_hour"]
```

Or import the module for zero-overhead repeated queries (cache already loaded):

```python
sys.path.insert(0, "/Users/webdizz/.agents/skills/aws-pricing")
from aws_pricing import AWSPricing

p = AWSPricing()  # region defaults to eu-west-1
print(p.get_ec2_price("m5.xlarge"))           # 0.214
print(p.get_rds_price("db.r5.large", engine="PostgreSQL", deployment="Multi-AZ"))
print(p.get_s3_price("Infrequent Access"))    # 0.0125
print(p.get_lambda_price())                   # 1.66667e-05
print(p.get_eks_price())                      # 0.1
print(p.get_fargate_price())                  # {vcpu, gb}
print(p.get_elasticache_price("cache.r6g.large"))
```

---

## Monthly cost formulas

Use these to convert hourly/unit prices to monthly estimates:

| Resource | Formula |
|---|---|
| EC2 / RDS / ElastiCache | `hourly_price × 730` |
| EKS cluster | `0.1 × 730 = $73/month` per cluster |
| Fargate | `(vcpu_count × vcpu_price + gb_ram × gb_price) × 730` |
| Lambda compute | `invocations × avg_duration_sec × gb_ram × gb_sec_price` |
| Lambda requests | `invocations × request_price` |
| S3 | `gb_stored × gb_month_price` |

---

## Cache behaviour

- Cache lives in `~/.agents/skills/aws-pricing/.pricing_cache/`  
  (or `.pricing_cache/` relative to script location when run directly)
- First fetch per service downloads the region-specific JSON (~5–300 MB depending on service)
- Subsequent calls are instant — no network, no rate limits
- TTL is **14 days**; stale files are re-downloaded automatically
- Check status: `uv run aws_pricing.py cache-status`
- Force refresh: `uv run aws_pricing.py refresh AmazonEC2`

---

## Reference: eu-west-1 sample prices (as of cache date)

### Compute
| Service | Config | Price |
|---|---|---|
| EC2 t3.medium | Linux, Shared | $0.0456/hr |
| EC2 m5.xlarge | Linux, Shared | $0.214/hr |
| EC2 c5.2xlarge | Windows | $0.384/hr |
| EKS cluster | Control plane | $0.100/hr |
| Fargate | Per vCPU | $0.04048/hr |
| Fargate | Per GB RAM | $0.004445/hr |
| Lambda compute | Per GB-second | $0.0000167 |
| Lambda requests | Per request | $0.0000002 |

### Databases & Caching
| Service | Config | Price |
|---|---|---|
| RDS db.t3.medium | PostgreSQL, Single-AZ | $0.078/hr |
| RDS db.r5.large | PostgreSQL, Multi-AZ | $0.560/hr |
| RDS db.r5.xlarge | Aurora PostgreSQL | $0.832/hr |
| ElastiCache cache.t3.medium | Redis | $0.058/hr |
| ElastiCache cache.r6g.large | Redis | $0.366/hr |

### Storage
| Service | Config | Price |
|---|---|---|
| S3 Standard | Per GB-month | $0.023 |
| S3 Infrequent Access | Per GB-month | $0.0125 |
| S3 Archive | Per GB-month | $0.021 |

### Messaging & Eventing
| Service | Config | Price |
|---|---|---|
| SQS Standard | Per million requests | $0.40 |
| SQS FIFO | Per million requests | $0.50 |
| SQS Fair (HT FIFO) | Per million requests | $0.10 |
| SNS API requests | Per million | $0.50 |
| SNS HTTP delivery | Per million | $0.60 |
| SNS email delivery | Per million | $20.00 |
| SNS mobile push | Per million | $0.50 |
| EventBridge custom | Per million events | $1.00 |
| EventBridge cross-acct | Per million events | $0.05 |
| EventBridge API Dest | Per million invocations | $0.20 |
| EventBridge archive | Per GB-month | $0.023 |

### Networking
| Service | Config | Price |
|---|---|---|
| API Gateway REST | Per million requests | $3.50 |
| API Gateway HTTP | Per million requests | $1.11 |
| API Gateway WS | Per million messages | $1.14 |
| ALB | Per hour | $0.0252 |
| ALB | Per LCU-hour | $0.008 |
| NLB | Per hour | $0.0252 |
| NLB | Per NLCU-hour | $0.006 |
| NAT Gateway | Per hour | $0.048 |
| NAT Gateway | Per GB processed | $0.048 |
| Transit Gateway | Per attachment-hour | $0.050 |
| Transit Gateway | Per GB processed | $0.020 |
| VPC Endpoint | Per AZ-hour | $0.011 |
| VPC Peering | Per GB cross-AZ | $0.010 |
| EIP (idle) | Per hour | $0.005 |
| EIP (in-use) | Per hour | $0.005 |
| Site-to-Site VPN | Per connection-hour | $0.010 |

> These are **on-demand** prices. Reserved instances and Savings Plans offer significant discounts (typically 30–60%).

---

## Troubleshooting

**`null` price returned** — the filter combination has no match. Use `search` to inspect what attribute values are actually present, then adjust filters accordingly.

**Slow first query** — EC2 pricing JSON is ~280 MB for eu-west-1. Subsequent calls load from cache instantly.

**Stale/corrupt cache** — run `uv run aws_pricing.py refresh <ServiceCode>` or delete `.pricing_cache/<service>_eu-west-1.json`.

**Unknown service** — run `uv run aws_pricing.py list-services` for the full list of valid service codes.
