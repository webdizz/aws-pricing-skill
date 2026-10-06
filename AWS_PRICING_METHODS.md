# Agent/LLM-Friendly AWS Pricing Methods

## Executive Summary

This document provides a comprehensive guide to programmatic AWS pricing methods that are suitable for automation and agent-based Infrastructure as Code (IaC) cost estimation during RFP processes. The AWS Pricing Calculator UI is interactive and not agent-friendly, but there are several API-based approaches.

---

## 1. AWS Pricing API (Boto3)

### Overview
The AWS Pricing API is a centralized query service that provides access to services, products, and pricing information using standardized product attributes.

### Key Capabilities
- **GetServices**: Retrieve list of AWS services with pricing data
- **GetProducts**: Query products and their pricing dimensions
- **GetAttributeValues**: Get valid values for specific attributes (e.g., instance types, regions)
- **DescribeServices**: Get detailed service information

### Usage Pattern
```python
import boto3

pricing = boto3.client('pricing', region_name='us-east-1')

# Get services
services = pricing.describe_services()

# Query EC2 products
response = pricing.get_products(
    ServiceCode='AmazonEC2',
    Filters=[
        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': 'US East (N. Virginia)'},
        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': 't3.micro'},
    ]
)
```

### Pros
- Official AWS API
- No account required (public endpoint)
- Programmatic access to raw pricing data
- Supports filtering by attributes

### Cons
- Complex filtering syntax
- Returns raw SKU-level data requiring interpretation
- No built-in cost calculation logic
- Pagination required for large result sets
- Limited to pricing data without calculator logic

---

## 2. AWS Bulk Pricing Tool

### Overview
AWS provides a bulk pricing download mechanism for getting all pricing data locally.

### Key Capabilities
- Download complete pricing datasets
- JSON and CSV formats
- Covers all AWS services
- Can be cached locally for fast queries

### Data URL Format
```
https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{service_code}/current/index.json
```

### Usage Pattern
```bash
# Download EC2 pricing
curl -o ec2-pricing.json \
  https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/index.json

# Download all services list
curl -o services.json \
  https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json
```

### Python Processing Example
```python
import json

# Load and parse pricing data
with open('ec2-pricing.json') as f:
    data = json.load(f)

# Extract on-demand pricing for specific instance
for sku, product in data['products'].items():
    if product.get('attributes', {}).get('instanceType') == 't3.micro':
        on_demand = data['terms']['OnDemand'].get(sku, {})
        price_dimensions = on_demand.get(list(on_demand.keys())[0], {}).get('priceDimensions', {})
        for dim_key, dim in price_dimensions.items():
            print(f"{product['attributes']['location']}: ${dim['pricePerUnit']['USD']} per hour")
```

### Pros
- Complete dataset for offline processing
- Fast lookups once downloaded
- No API rate limits
- Can build local pricing database

### Cons
- Large file sizes (hundreds of MB)
- Data freshness issues
- Complex parsing logic required
- Not real-time pricing

---

## 3. AWS Cost Explorer API

### Overview
The AWS Cost Explorer API provides access to historical cost and usage data from your AWS account.

### Key Capabilities
- GetCostAndUsage: Retrieve cost and usage data
- GetReservationCoverage: EC2 Reserved Instance coverage
- GetSavingsPlansCoverage: Savings Plans coverage data
- GetRightsizingRecommendation: Rightsizing recommendations

### Usage Pattern
```python
import boto3

ce = boto3.client('ce')

# Get historical costs
response = ce.get_cost_and_usage(
    TimePeriod={
        'Start': '2024-01-01',
        'End': '2024-01-31'
    },
    Granularity='MONTHLY',
    Metrics=['BlendedCost'],
    GroupBy=[
        {'Type': 'DIMENSION', 'Key': 'SERVICE'}
    ]
)
```

### Pros
- Historical data (your actual costs)
- Integrated with your AWS account
- Supports forecasting
- Native AWS authentication

### Cons
- Requires AWS account and IAM permissions
- Only shows historical data, not estimates
- Not suitable for RFP pre-planning

---

## 4. AWS Pricing Calculator API (Experimental)

### Overview
AWS has been developing a REST API for the Pricing Calculator that allows programmatic estimate creation.

### Known Endpoint Patterns
```
POST https://pricing-calculator.amazonaws.com/api/estimates
```

### Usage Pattern (Conceptual)
```python
import requests
import json

# Create estimate payload
estimate = {
    "estimateName": "RFP Infrastructure",
    "currencyCode": "USD",
    "services": [
        {
            "serviceName": "AmazonEC2",
            "region": "us-east-1",
            "instanceType": "t3.micro",
            "operatingSystem": "Linux",
            "term": "OnDemand",
            "quantity": 5
        }
    ]
}

# Note: This API may require special access or be in preview
response = requests.post(
    "https://pricing-calculator.amazonaws.com/api/estimates",
    json=estimate,
    headers={"Content-Type": "application/json"}
)
```

### Pros
- Direct programmatic access to calculator logic
- Handles pricing calculations
- Returns formatted estimates
- Can create and manage estimates

### Cons
- May still be in preview or limited access
- Documentation may be limited
- Subject to API changes

---

## 5. Third-Party Libraries

### 5.1 Infracost

#### Overview
Infracost is a popular open-source tool that estimates cloud costs from Terraform, CloudFormation, and other IaC templates.

#### Key Capabilities
- Terraform plan parsing
- CloudFormation template analysis
- CI/CD integration
- Cost breakdown by resource

#### Installation & Usage
```bash
# Install
brew install infracost

# Register for API key (free tier available)
infracost auth login

# Estimate from Terraform
infracost breakdown --path ./terraform

# Estimate from CloudFormation
cat template.yaml | infracost breakdown --path /dev/stdin --format json

# JSON output for programmatic use
infracost breakdown --path ./terraform --format json > estimate.json
```

#### Python Integration
```python
import subprocess
import json

result = subprocess.run(
    ['infracost', 'breakdown', '--path', './terraform', '--format', 'json'],
    capture_output=True,
    text=True
)

estimate = json.loads(result.stdout)
monthly_cost = estimate['totalMonthlyCost']
```

#### Pros
- Purpose-built for IaC cost estimation
- Supports multiple IaC formats
- Mature and well-documented
- JSON output for programmatic processing
- Free tier available
- GitHub Actions integration

#### Cons
- Requires external tool installation
- Free tier has limits on API calls
- Paid plan for higher usage
- Not pure AWS API

### 5.2 Terraform Cost Estimation (built-in)

#### Overview
Terraform has experimental cost estimation integration with cloud providers.

#### Usage
```bash
terraform plan -out=tfplan
terraform show -json tfplan | jq '.resource_changes'
# Requires additional tooling for price lookups
```

#### Pros
- Native to Terraform workflows
- No external dependencies for basic analysis

#### Cons
- Experimental feature
- Limited pricing data
- Requires significant additional tooling

### 5.3 CloudFormation Template Analysis

#### Custom Solution Approach
```python
import yaml
import json
import boto3

# Parse CloudFormation template
with open('template.yaml') as f:
    template = yaml.safe_load(f)

# Extract resources by type
resources = template.get('Resources', {})
ec2_instances = [
    name for name, config in resources.items()
    if config.get('Type') == 'AWS::EC2::Instance'
]

# Query pricing for each instance type found
pricing = boto3.client('pricing')
# ... query logic based on extracted instance types
```

---

## 6. Custom Agent-Friendly Solutions

### 6.1 Pricing Data Cache + Query Layer

#### Architecture
```
AWS Bulk Pricing API → Local Cache (SQLite/JSON) → Agent Query Interface
```

#### Implementation Pattern
```python
import sqlite3
import json
import requests
from typing import Dict, List, Optional

class AWSPricingCache:
    def __init__(self, db_path: str = "pricing.db"):
        self.conn = sqlite3.connect(db_path)
        self._init_tables()
    
    def _init_tables(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS pricing (
                sku TEXT PRIMARY KEY,
                service_code TEXT,
                region TEXT,
                instance_type TEXT,
                price_per_unit REAL,
                unit TEXT,
                json_data TEXT
            )
        ''')
    
    def load_bulk_pricing(self, service_code: str):
        """Download and cache pricing from AWS Bulk API"""
        url = f"https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{service_code}/current/index.json"
        response = requests.get(url)
        data = response.json()
        
        for sku, product in data['products'].items():
            # Insert into database
            pass  # Implementation details
    
    def query_price(self, service: str, region: str, instance_type: str) -> Optional[float]:
        """Query cached pricing data"""
        cursor = self.conn.execute('''
            SELECT price_per_unit FROM pricing 
            WHERE service_code = ? AND region = ? AND instance_type = ?
        ''', (service, region, instance_type))
        result = cursor.fetchone()
        return result[0] if result else None
```

### 6.2 LLM-Friendly Cost Estimation Service

#### REST API Wrapper
```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class CostEstimateRequest(BaseModel):
    service: str
    region: str
    instance_type: Optional[str]
    quantity: int = 1
    hours_per_month: int = 730

class CostEstimateResponse(BaseModel):
    monthly_cost: float
    hourly_rate: float
    currency: str = "USD"
    service: str
    region: str

@app.post("/estimate")
async def estimate_cost(request: CostEstimateRequest) -> CostEstimateResponse:
    # Query pricing cache or AWS API
    hourly_rate = pricing_cache.query_price(
        request.service,
        request.region,
        request.instance_type
    )
    monthly = hourly_rate * request.hours_per_month * request.quantity
    
    return CostEstimateResponse(
        monthly_cost=monthly,
        hourly_rate=hourly_rate,
        service=request.service,
        region=request.region
    )
```

### 6.3 Agent Tool Integration

#### For pi-like agents
```python
from typing import Dict, Any

def estimate_aws_cost(
    service: str,
    region: str,
    instance_type: str = None,
    quantity: int = 1,
    storage_gb: int = None,
    data_transfer_gb: int = None
) -> Dict[str, Any]:
    """
    Estimate AWS infrastructure cost.
    
    Args:
        service: AWS service (EC2, RDS, S3, etc.)
        region: AWS region (us-east-1, eu-west-1, etc.)
        instance_type: Instance/DB instance type
        quantity: Number of instances
        storage_gb: Storage size in GB
        data_transfer_gb: Data transfer in GB
    
    Returns:
        Dictionary with monthly cost breakdown
    """
    # Implementation using pricing cache
    pass

# Register as agent tool
tools = {
    "estimate_aws_cost": estimate_aws_cost
}
```

---

## 7. Comparison Matrix

| Method | Account Required | Latency | Complexity | Coverage | LLM-Friendly |
|--------|-----------------|---------|------------|----------|--------------|
| AWS Pricing API | No | Medium | High | Full | ⭐⭐ |
| Bulk Pricing Download | No | Low* | Medium | Full | ⭐⭐⭐ |
| Cost Explorer API | Yes | Medium | Medium | Historical | ⭐⭐ |
| Pricing Calculator API | No | Low | Low | Calculated | ⭐⭐⭐⭐⭐ |
| Infracost | No | Low | Low | IaC-focused | ⭐⭐⭐⭐⭐ |
| Custom Cache | No | Very Low | Medium | Configurable | ⭐⭐⭐⭐ |

*Low after initial download

---

## 8. Recommended Architecture for RFP Use

### Phase 1: Quick Estimation (MVP)
```
→ Use Infracost with CloudFormation/Terraform templates
→ Generate JSON estimates programmatically
→ Agent parses and presents results
```

### Phase 2: Enhanced Accuracy
```
→ Build local pricing cache from Bulk Pricing API
→ Implement custom query layer
→ Support more AWS services and configurations
```

### Phase 3: Full Integration
```
→ REST API service for cost estimation
→ Agent calls REST API for real-time estimates
→ Support for Savings Plans and Reserved Instances
```

---

## 9. Sample Implementation: Complete Agent Integration

```python
#!/usr/bin/env python3
"""AWS Cost Estimation Agent Tool

Usage for agents:
  1. Download and cache pricing data: estimate.setup_cache()
  2. Estimate single resource: estimate.estimate_ec2(region="us-east-1", instance_type="t3.micro")
  3. Estimate from template: estimate.from_cloudformation("template.yaml")
"""

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Dict, Optional, List
import requests

class AWSCostEstimator:
    def __init__(self, cache_dir: str = ".pricing_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.db_path = self.cache_dir / "pricing.db"
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ec2_pricing (
                sku TEXT PRIMARY KEY,
                region TEXT,
                instance_type TEXT,
                os TEXT,
                tenancy TEXT,
                price_per_hour REAL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    def download_pricing(self, service: str = "AmazonEC2"):
        """Download latest pricing from AWS Bulk API"""
        url = f"https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{service}/current/index.json"
        print(f"Downloading pricing data from {url}...")
        
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # Process in chunks to handle large files
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Clear existing data
        cursor.execute("DELETE FROM ec2_pricing")
        
        # Parse and insert (simplified - actual implementation would stream)
        data = response.json()
        
        for sku, product in data.get('products', {}).items():
            attrs = product.get('attributes', {})
            if attrs.get('servicecode') == 'AmazonEC2':
                # Extract pricing
                on_demand = data.get('terms', {}).get('OnDemand', {}).get(sku, {})
                for term in on_demand.values():
                    for dim in term.get('priceDimensions', {}).values():
                        price = float(dim['pricePerUnit']['USD'])
                        cursor.execute('''
                            INSERT INTO ec2_pricing (sku, region, instance_type, os, tenancy, price_per_hour)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (
                            sku,
                            attrs.get('location', ''),
                            attrs.get('instanceType', ''),
                            attrs.get('operatingsystem', ''),
                            attrs.get('tenancy', ''),
                            price
                        ))
        
        conn.commit()
        conn.close()
        print("Pricing data cached successfully")
    
    def estimate_ec2(self, region: str, instance_type: str, 
                     os: str = "Linux", tenancy: str = "Shared",
                     quantity: int = 1, hours_per_month: int = 730) -> Dict:
        """Get EC2 cost estimate from cache"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute('''
            SELECT price_per_hour FROM ec2_pricing
            WHERE region LIKE ? AND instance_type = ? AND os LIKE ? AND tenancy = ?
            LIMIT 1
        ''', (f'%{region}%', instance_type, f'%{os}%', tenancy))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return {"error": f"No pricing found for {instance_type} in {region}"}
        
        hourly_price = result[0]
        monthly_price = hourly_price * hours_per_month * quantity
        
        return {
            "service": "EC2",
            "region": region,
            "instance_type": instance_type,
            "operating_system": os,
            "hourly_rate": round(hourly_price, 4),
            "monthly_cost": round(monthly_price, 2),
            "annual_cost": round(monthly_price * 12, 2),
            "currency": "USD",
            "assumptions": {
                "hours_per_month": hours_per_month,
                "quantity": quantity
            }
        }
    
    def estimate_infracost(self, template_path: str) -> Optional[Dict]:
        """Use Infracost for CloudFormation/Terraform templates"""
        try:
            result = subprocess.run(
                ['infracost', 'breakdown', '--path', template_path, '--format', 'json'],
                capture_output=True,
                text=True
            )
            return json.loads(result.stdout)
        except FileNotFoundError:
            return {"error": "Infracost not installed. Run: brew install infracost"}
        except Exception as e:
            return {"error": str(e)}


# === Agent-Friendly Interface ===

def estimate_single_resource(service: str, **kwargs) -> str:
    """Estimate cost for a single AWS resource (agent-friendly wrapper)"""
    estimator = AWSCostEstimator()
    
    if service == "EC2":
        result = estimator.estimate_ec2(**kwargs)
    else:
        return f"Service {service} not yet supported in basic estimator. Try using Infracost."
    
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    # Demo usage
    estimator = AWSCostEstimator()
    estimator.download_pricing()
    
    result = estimator.estimate_ec2(
        region="US East (N. Virginia)",
        instance_type="t3.micro",
        quantity=5
    )
    print(json.dumps(result, indent=2))
```

---

## 10. Next Steps

1. **Immediate**: Set up Infracost for IaC-based estimation
2. **Short-term**: Build pricing cache for common services (EC2, RDS, S3, ELB)
3. **Medium-term**: Create REST API wrapper for cost estimation
4. **Long-term**: Full integration with agent tools ecosystem

---

## References

- [AWS Pricing API Documentation](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/Welcome.html)
- [AWS Bulk Pricing API](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json)
- [Boto3 Pricing Client](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/pricing.html)
- [Infracost Documentation](https://www.infracost.io/docs/)
- [AWS Cost Explorer API](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostAndUsage.html)
