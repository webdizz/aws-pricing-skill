#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
AWS Pricing Wrapper
-------------------
Downloads and caches AWS bulk pricing JSON files (2-week TTL).
Provides a simple query API suitable for use in pi skills.

Usage:
    from aws_pricing import AWSPricing

    pricing = AWSPricing()

    # EC2
    price = pricing.get_ec2_price("t3.medium", tenancy="Shared", os="Linux")

    # RDS
    price = pricing.get_rds_price("db.t3.medium", engine="MySQL", deployment="Single-AZ")

    # S3
    price = pricing.get_s3_price(storage_class="Standard")

    # Lambda
    price = pricing.get_lambda_price()

    # Generic search
    results = pricing.search("AmazonEC2", {"instanceType": "t3.medium", "operatingSystem": "Linux"})

CLI:
    python aws_pricing.py sqs
    python aws_pricing.py sqs --queue-type FIFO
    python aws_pricing.py sns
    python aws_pricing.py eventbridge
    python aws_pricing.py apigw
    python aws_pricing.py alb
    python aws_pricing.py nlb
    python aws_pricing.py vpc
    python aws_pricing.py ec2 t3.medium
    python aws_pricing.py rds db.t3.medium --engine MySQL
    python aws_pricing.py s3
    python aws_pricing.py lambda
    python aws_pricing.py search AmazonEC2 '{"instanceType":"t3.medium"}'
    python aws_pricing.py list-services
    python aws_pricing.py cache-status
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CACHE_DIR = Path(__file__).parent / ".pricing_cache"
CACHE_TTL_DAYS = 14

# AWS Bulk Pricing base URL (always us-east-1 endpoint, regardless of target region)
PRICING_BASE = "https://pricing.us-east-1.amazonaws.com"
INDEX_URL = f"{PRICING_BASE}/offers/v1.0/aws/index.json"

# Region string used in AWS product location field
REGION_DISPLAY_NAMES = {
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "eu-central-1": "EU (Frankfurt)",
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
}

DEFAULT_REGION = "eu-west-1"


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(service_code: str, region: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{service_code}_{region}.json"


def _index_cache_path() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / "index.json"


def _is_stale(path: Path, ttl_days: int = CACHE_TTL_DAYS) -> bool:
    if not path.exists():
        return True
    age = time.time() - path.stat().st_mtime
    return age > ttl_days * 86400


def _download(url: str, dest: Path, label: str = "") -> dict:
    label = label or url
    # Only allow https:// URLs to the AWS pricing endpoint
    if not url.startswith("https://"):
        raise ValueError(f"Refusing non-HTTPS URL: {url}")
    print(f"[aws_pricing] Downloading {label} ...", file=sys.stderr)
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc
    dest.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"[aws_pricing] Saved to {dest}", file=sys.stderr)
    return data


# ---------------------------------------------------------------------------
# Service index
# ---------------------------------------------------------------------------

def _load_index() -> dict:
    path = _index_cache_path()
    if _is_stale(path):
        return _download(INDEX_URL, path, "AWS service index")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _download(INDEX_URL, path, "AWS service index")


def _region_index_cache_path(service_code: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{service_code}_region_index.json"


def _get_service_url(service_code: str, region: str = DEFAULT_REGION) -> str:
    """
    Return the pricing URL for a service, preferring the region-specific file
    (orders of magnitude smaller than the global file) when available.
    """
    index = _load_index()
    offers = index.get("offers", {})
    if service_code not in offers:
        available = sorted(offers.keys())
        raise ValueError(
            f"Unknown service '{service_code}'. Available: {available[:20]}..."
        )

    offer = offers[service_code]

    # Try region-specific index first (much smaller download)
    region_index_path_key = offer.get("currentRegionIndexUrl")
    if region_index_path_key:
        ri_cache = _region_index_cache_path(service_code)
        if _is_stale(ri_cache):
            ri_url = f"{PRICING_BASE}{region_index_path_key}"
            try:
                ri_data = _download(ri_url, ri_cache, f"{service_code} region index")
            except RuntimeError:
                ri_data = None
        else:
            try:
                ri_data = json.loads(ri_cache.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                ri_data = None

        if ri_data:
            region_entry = ri_data.get("regions", {}).get(region)
            if region_entry:
                return f"{PRICING_BASE}{region_entry['currentVersionUrl']}"

    # Fall back to the global file
    return f"{PRICING_BASE}{offer['currentVersionUrl']}"


# ---------------------------------------------------------------------------
# Per-service bulk data loader
# ---------------------------------------------------------------------------

def _load_service(service_code: str, region: str = DEFAULT_REGION) -> dict:
    path = _cache_path(service_code, region)
    if not _is_stale(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            path.unlink(missing_ok=True)  # discard corrupt file and re-download
    url = _get_service_url(service_code, region)
    return _download(url, path, f"{service_code} pricing ({region})")


# ---------------------------------------------------------------------------
# Low-level product search
# ---------------------------------------------------------------------------

def _iter_products(service_code: str, filters: dict[str, str | None], region: str = DEFAULT_REGION):
    """
    Yield (product_attrs, on_demand_price_usd) tuples matching all filters.

    filters: dict of attribute -> value
      - Exact match (case-insensitive) by default.
      - Prefix value with "contains:" for substring match, e.g.
        {"usagetype": "contains:perCluster"}
    """
    location = REGION_DISPLAY_NAMES.get(region, region)
    data = _load_service(service_code, region)
    products = data.get("products", {})
    terms = data.get("terms", {}).get("OnDemand", {})

    # Normalise filter values for comparison
    normalised_filters: dict[str, tuple[str, str]] = {}  # key -> (mode, value)
    opted_out: set[str] = set()  # keys explicitly set to None by caller
    for k, v in filters.items():
        if v is None:
            opted_out.add(k)  # caller opts out of this key (e.g. location guard)
            continue
        if v.startswith("contains:"):
            normalised_filters[k] = ("contains", v[len("contains:"):].lower())
        else:
            normalised_filters[k] = ("exact", v.lower())
    # Always restrict to target region — unless caller already set it or opted out
    if "location" not in opted_out:
        normalised_filters.setdefault("location", ("exact", location.lower()))

    def _matches(attrs: dict) -> bool:
        for key, (mode, val) in normalised_filters.items():
            attr_val = attrs.get(key, "").lower()
            if mode == "contains":
                if val not in attr_val:
                    return False
            else:
                if attr_val != val:
                    return False
        return True

    for sku, product in products.items():
        attrs = product.get("attributes", {})
        if _matches(attrs):
            # Extract on-demand price
            sku_terms = terms.get(sku, {})
            for offer in sku_terms.values():
                for pd in offer.get("priceDimensions", {}).values():
                    usd = pd.get("pricePerUnit", {}).get("USD", "0")
                    try:
                        price = float(usd)
                    except ValueError:
                        price = 0.0
                    yield attrs, price


def _first_price(service_code: str, filters: dict[str, str | None], region: str = DEFAULT_REGION) -> float | None:
    for _, price in _iter_products(service_code, filters, region):
        return price
    return None


# ---------------------------------------------------------------------------
# High-level query methods
# ---------------------------------------------------------------------------

class AWSPricing:
    """
    High-level AWS pricing query interface.

    All prices are on-demand USD per unit per hour (or as noted).
    Region defaults to eu-west-1.
    """

    def __init__(self, region: str = DEFAULT_REGION):
        self.region = region

    # ---- EC2 ----------------------------------------------------------------

    def get_ec2_price(
        self,
        instance_type: str,
        os: str = "Linux",
        tenancy: str = "Shared",
        capacity_status: str = "Used",
    ) -> float | None:
        """
        Returns on-demand hourly price (USD) for an EC2 instance.

        Args:
            instance_type: e.g. "t3.medium", "m5.xlarge"
            os: "Linux", "Windows", "RHEL", "SUSE", etc.
            tenancy: "Shared", "Dedicated", "Host"
            capacity_status: "Used" (default) or "AllocatedCapacityReservation"
        """
        return _first_price("AmazonEC2", {
            "instanceType": instance_type,
            "operatingSystem": os,
            "tenancy": tenancy,
            "capacitystatus": capacity_status,
            "preInstalledSw": "NA",
        }, self.region)

    def search_ec2(self, instance_type: str, **extra_filters) -> list[dict]:
        """Return all matching EC2 products with prices for an instance type."""
        filters = {"instanceType": instance_type, **extra_filters}
        return [
            {"attributes": attrs, "price_usd_per_hour": price}
            for attrs, price in _iter_products("AmazonEC2", filters, self.region)
        ]

    # ---- RDS ----------------------------------------------------------------

    def get_rds_price(
        self,
        instance_type: str,
        engine: str = "MySQL",
        deployment: str = "Single-AZ",
    ) -> float | None:
        """
        Returns on-demand hourly price (USD) for an RDS instance.

        Args:
            instance_type: e.g. "db.t3.medium", "db.r5.xlarge"
            engine: "MySQL", "PostgreSQL", "Oracle", "SQL Server", "Aurora MySQL", etc.
            deployment: "Single-AZ" or "Multi-AZ"
        """
        return _first_price("AmazonRDS", {
            "instanceType": instance_type,
            "databaseEngine": engine,
            "deploymentOption": deployment,
        }, self.region)

    # ---- S3 -----------------------------------------------------------------

    def get_s3_price(
        self,
        storage_class: str = "General Purpose",
    ) -> float | None:
        """
        Returns S3 storage price (USD per GB-month) for the first tier.

        Args:
            storage_class: One of:
              "General Purpose", "Infrequent Access", "Archive",
              "Archive Instant Retrieval", "Intelligent-Tiering", etc.
        """
        return _first_price("AmazonS3", {
            "storageClass": storage_class,
        }, self.region)

    # ---- Lambda -------------------------------------------------------------

    def get_lambda_price(self, group: str = "AWS-Lambda-Duration") -> float | None:
        """
        Returns Lambda compute price (USD per GB-second).

        Args:
            group: "AWS-Lambda-Duration" (compute) or "AWS-Lambda-Requests"
        """
        return _first_price("AWSLambda", {
            "group": group,
        }, self.region)

    def get_lambda_request_price(self) -> float | None:
        """Returns Lambda request price (USD per request)."""
        return self.get_lambda_price(group="AWS-Lambda-Requests")

    # ---- EKS / ECS ----------------------------------------------------------

    def get_eks_price(self) -> float | None:
        """Returns EKS cluster control-plane price (USD per cluster-hour)."""
        return _first_price("AmazonEKS", {
            "usagetype": "contains:perCluster",
            "operation": "CreateOperation",
        }, self.region)

    def get_fargate_price(self) -> dict[str, float | None]:
        """
        Returns Fargate pricing for eu-west-1.

        Returns dict with:
            price_usd_per_vcpu_hour  – per vCPU per hour
            price_usd_per_gb_hour    – per GB memory per hour
        """
        vcpu = _first_price("AmazonEKS", {
            "usagetype": "contains:Fargate-vCPU-Hours",
        }, self.region)
        mem = _first_price("AmazonEKS", {
            "usagetype": "contains:Fargate-GB-Hours",
        }, self.region)
        return {
            "price_usd_per_vcpu_hour": vcpu,
            "price_usd_per_gb_hour": mem,
        }

    # ---- ElastiCache --------------------------------------------------------

    def get_elasticache_price(
        self,
        instance_type: str,
        cache_engine: str = "Redis",
    ) -> float | None:
        """
        Returns ElastiCache on-demand hourly price (USD).

        Args:
            instance_type: e.g. "cache.t3.medium", "cache.r6g.large"
            cache_engine: "Redis" or "Memcached"
        """
        return _first_price("AmazonElastiCache", {
            "instanceType": instance_type,
            "cacheEngine": cache_engine,
        }, self.region)

    # ---- SQS ----------------------------------------------------------------

    def get_sqs_price(self, queue_type: str = "Standard") -> float | None:
        """
        Returns SQS price per 1 million requests (USD).

        Args:
            queue_type: "Standard", "FIFO", or "Fair" (high-throughput FIFO)
        """
        _map = {
            "standard": "Standard",
            "fifo": "FIFO (first-in, first-out)",
            "fair": "Fair",
        }
        normalized = _map.get(queue_type.lower(), queue_type)
        price = _first_price("AWSQueueService", {
            "queueType": normalized,
            "usagetype": "contains:Requests-",
        }, self.region)
        # prices are per-request; return per million for readability
        return round(price * 1_000_000, 6) if price is not None else None

    # ---- SNS ----------------------------------------------------------------

    def get_sns_price(self) -> dict[str, float | None]:
        """
        Returns SNS pricing for eu-west-1.

        Returns dict with:
            price_usd_per_million_api_requests  – publish API calls (paid tier)
            price_usd_per_million_http           – HTTP/HTTPS deliveries (paid tier)
            price_usd_per_million_email          – email deliveries (paid tier)
            price_usd_per_million_sqs            – SQS deliveries (free)
            price_usd_per_million_lambda         – Lambda deliveries (free)
            price_usd_per_million_mobile_push    – mobile push (GCM/APNS etc.)
        """
        def paid_per_m(usagetype_contains: str) -> float | None:
            """Return the non-zero (paid tier) price per million, skipping free-tier SKUs."""
            for _, price in _iter_products(
                "AmazonSNS", {"usagetype": f"contains:{usagetype_contains}"}, self.region
            ):
                if price > 0:
                    return round(price * 1_000_000, 6)
            return 0.0  # free for this endpoint type

        return {
            "price_usd_per_million_api_requests": paid_per_m("Requests-Tier1"),
            "price_usd_per_million_http": paid_per_m("DeliveryAttempts-HTTP"),
            "price_usd_per_million_email": paid_per_m("DeliveryAttempts-SMTP"),
            "price_usd_per_million_sqs": 0.0,    # always free
            "price_usd_per_million_lambda": 0.0,  # always free
            "price_usd_per_million_mobile_push": paid_per_m("DeliveryAttempts-GCM"),
        }

    # ---- EventBridge --------------------------------------------------------

    def get_eventbridge_price(self) -> dict[str, float | None]:
        """
        Returns EventBridge pricing for eu-west-1.

        Returns dict with:
            price_usd_per_million_custom_events   – events published to custom buses
            price_usd_per_million_scheduled       – Scheduler invocations
            price_usd_per_million_cross_account   – cross-account event delivery
            price_usd_per_million_api_destination – API Destination invocations
            price_usd_per_gb_month_archive        – archive storage
        """
        def per_m(event_type: str) -> float | None:
            p = _first_price("AWSEvents", {"eventType": event_type}, self.region)
            return round(p * 1_000_000, 6) if p is not None else None

        archive_storage = _first_price("AWSEvents", {"eventType": "Event Storage"}, self.region)

        return {
            "price_usd_per_million_custom_events": per_m("Custom Event"),
            "price_usd_per_million_scheduled": _first_price(
                "AWSEvents", {"usagetype": "contains:ScheduledInvocation"}, self.region
            ),
            "price_usd_per_million_cross_account": per_m("Cross-Account Custom Event"),
            "price_usd_per_million_api_destination": per_m("APIDestination"),
            "price_usd_per_gb_month_archive": archive_storage,
        }

    # ---- API Gateway --------------------------------------------------------

    def get_api_gateway_price(self) -> dict[str, float | None]:
        """
        Returns API Gateway pricing for eu-west-1.

        Returns dict with:
            rest_price_usd_per_million_requests  – REST API (ApiGatewayRequest)
            http_price_usd_per_million_requests  – HTTP API (cheaper, ApiGatewayHttpApi)
            websocket_price_usd_per_million_msgs – WebSocket messages
            websocket_price_usd_per_million_mins – WebSocket connection-minutes
        """
        def per_m(op: str, usagetype_contains: str) -> float | None:
            p = _first_price("AmazonApiGateway",
                             {"operation": op, "usagetype": f"contains:{usagetype_contains}"},
                             self.region)
            return round(p * 1_000_000, 6) if p is not None else None

        ws_min = _first_price("AmazonApiGateway",
                              {"operation": "ApiGatewayWebSocket",
                               "usagetype": "contains:Minute"},
                              self.region)

        return {
            "rest_price_usd_per_million_requests": per_m("ApiGatewayRequest", "ApiGatewayRequest"),
            "http_price_usd_per_million_requests": per_m("ApiGatewayHttpApi", "ApiGatewayHttpRequest"),
            "websocket_price_usd_per_million_msgs": per_m("ApiGatewayWebSocket", "ApiGatewayMessage"),
            "websocket_price_usd_per_million_mins": round(ws_min * 1_000_000, 6) if ws_min else None,
        }

    # ---- ALB / NLB ----------------------------------------------------------

    def get_alb_price(self) -> dict[str, float | None]:
        """
        Returns Application Load Balancer pricing for eu-west-1.

        Returns dict with:
            price_usd_per_hour    – ALB hourly charge
            price_usd_per_lcu_hour – LCU (Load Balancer Capacity Unit) per hour
        """
        hourly = _first_price("AWSELB",
                              {"operation": "LoadBalancing:Application",
                               "usagetype": "EU-LoadBalancerUsage"},
                              self.region)
        lcu = _first_price("AWSELB",
                           {"operation": "LoadBalancing:Application",
                            "usagetype": "EU-LCUUsage"},
                           self.region)
        return {
            "price_usd_per_hour": hourly,
            "price_usd_per_lcu_hour": lcu,
        }

    def get_nlb_price(self) -> dict[str, float | None]:
        """
        Returns Network Load Balancer pricing for eu-west-1.

        Returns dict with:
            price_usd_per_hour     – NLB hourly charge
            price_usd_per_lcu_hour – NLCU per hour
        """
        hourly = _first_price("AWSELB",
                              {"operation": "LoadBalancing:Network",
                               "usagetype": "EU-LoadBalancerUsage"},
                              self.region)
        lcu = _first_price("AWSELB",
                           {"operation": "LoadBalancing:Network",
                            "usagetype": "EU-LCUUsage"},
                           self.region)
        return {
            "price_usd_per_hour": hourly,
            "price_usd_per_lcu_hour": lcu,
        }

    # ---- VPC ----------------------------------------------------------------

    def get_vpc_price(self) -> dict[str, float | None]:
        """
        Returns common VPC networking pricing for eu-west-1.

        Returns dict with:
            nat_gateway_price_usd_per_hour        – NAT Gateway hourly charge (billed via EC2)
            nat_gateway_price_usd_per_gb           – NAT Gateway data processing per GB
            vpn_connection_price_usd_per_hour      – Site-to-Site VPN connection
            transit_gateway_price_usd_per_hour     – Transit Gateway attachment
            transit_gateway_price_usd_per_gb       – Transit Gateway data processing
            vpc_endpoint_price_usd_per_hour        – Interface VPC Endpoint per AZ-hour
            vpc_peering_price_usd_per_gb           – VPC Peering cross-AZ data transfer
            eip_idle_price_usd_per_hour            – Idle public IPv4 address
            eip_inuse_price_usd_per_hour           – In-use public IPv4 address
        """
        return {
            # NAT Gateway is billed through AmazonEC2 service
            "nat_gateway_price_usd_per_hour": _first_price(
                "AmazonEC2", {"usagetype": "EU-NatGateway-Hours"}, self.region),
            "nat_gateway_price_usd_per_gb": _first_price(
                "AmazonEC2", {"usagetype": "EU-NatGateway-Bytes"}, self.region),
            # VPN, Transit Gateway, Endpoints — under AmazonVPC
            "vpn_connection_price_usd_per_hour": _first_price(
                "AmazonVPC", {"usagetype": "contains:VPN-concentrator-site-Usage-Hours"}, self.region),
            "transit_gateway_price_usd_per_hour": _first_price(
                "AmazonVPC", {"usagetype": "EU-TransitGateway-Hours"}, self.region),
            "transit_gateway_price_usd_per_gb": _first_price(
                "AmazonVPC", {"usagetype": "EU-TransitGateway-Bytes"}, self.region),
            "vpc_endpoint_price_usd_per_hour": _first_price(
                "AmazonVPC", {"usagetype": "EU-VpcEndpoint-Hours"}, self.region),
            "vpc_peering_price_usd_per_gb": _first_price(
                "AmazonVPC",
                {"usagetype": "EU-VpcPeering-In-Bytes", "location": None},
                self.region),
            # Public IPv4 addresses — billed through AmazonVPC
            "eip_idle_price_usd_per_hour": _first_price(
                "AmazonVPC", {"usagetype": "EU-PublicIPv4:IdleAddress"}, self.region),
            "eip_inuse_price_usd_per_hour": _first_price(
                "AmazonVPC", {"usagetype": "EU-PublicIPv4:InUseAddress"}, self.region),
        }

    # ---- Generic search -----------------------------------------------------

    def search(self, service_code: str, filters: dict[str, str | None]) -> list[dict]:
        """
        Generic product search against any AWS service.

        Returns list of {"attributes": {...}, "price_usd": float}
        """
        return [
            {"attributes": attrs, "price_usd": price}
            for attrs, price in _iter_products(service_code, filters, self.region)
        ]

    # ---- Utility ------------------------------------------------------------

    def list_services(self) -> list[str]:
        """Return all available AWS service codes."""
        index = _load_index()
        return sorted(index.get("offers", {}).keys())

    def cache_status(self) -> list[dict]:
        """Return info about cached files."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        results = []
        for f in sorted(CACHE_DIR.glob("*.json")):
            mtime = f.stat().st_mtime
            age_days = (time.time() - mtime) / 86400
            expires = datetime.fromtimestamp(mtime) + timedelta(days=CACHE_TTL_DAYS)
            results.append({
                "file": f.name,
                "size_mb": round(f.stat().st_size / 1_048_576, 1),
                "age_days": round(age_days, 1),
                "expires": expires.strftime("%Y-%m-%d"),
                "stale": _is_stale(f),
            })
        return results

    def refresh(self, service_code: str):
        """Force-refresh cache for a service (ignores TTL)."""
        _cache_path(service_code, self.region).unlink(missing_ok=True)
        _region_index_cache_path(service_code).unlink(missing_ok=True)
        _load_service(service_code, self.region)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_json(obj):
    print(json.dumps(obj, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="AWS Pricing CLI (eu-west-1, cached)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS region (default: eu-west-1)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    # ec2
    p_ec2 = sub.add_parser("ec2", help="Get EC2 on-demand hourly price")
    p_ec2.add_argument("instance_type", help="e.g. t3.medium")
    p_ec2.add_argument("--os", default="Linux", help="OS (default: Linux)")
    p_ec2.add_argument("--tenancy", default="Shared")

    # rds
    p_rds = sub.add_parser("rds", help="Get RDS on-demand hourly price")
    p_rds.add_argument("instance_type", help="e.g. db.t3.medium")
    p_rds.add_argument("--engine", default="MySQL")
    p_rds.add_argument("--deployment", default="Single-AZ")

    # s3
    p_s3 = sub.add_parser("s3", help="Get S3 storage price per GB-month")
    p_s3.add_argument("--storage-class", default="General Purpose",
                      help="e.g. 'General Purpose', 'Infrequent Access', 'Archive'")

    # lambda
    sub.add_parser("lambda", help="Get Lambda compute and request prices")

    # elasticache
    p_ec = sub.add_parser("elasticache", help="Get ElastiCache on-demand hourly price")
    p_ec.add_argument("instance_type", help="e.g. cache.t3.medium")
    p_ec.add_argument("--engine", default="Redis")

    # sqs
    p_sqs = sub.add_parser("sqs", help="Get SQS price per million requests")
    p_sqs.add_argument("--queue-type", default="Standard",
                       help="Standard (default), FIFO, Fair (high-throughput FIFO)")

    # sns
    sub.add_parser("sns", help="Get SNS pricing (requests, deliveries)")

    # eventbridge
    sub.add_parser("eventbridge", help="Get EventBridge pricing (events, scheduler, archive)")

    # apigw
    sub.add_parser("apigw", help="Get API Gateway pricing (REST, HTTP, WebSocket)")

    # alb
    sub.add_parser("alb", help="Get Application Load Balancer pricing")

    # nlb
    sub.add_parser("nlb", help="Get Network Load Balancer pricing")

    # vpc
    sub.add_parser("vpc", help="Get VPC pricing (NAT GW, VPN, Transit GW, Endpoints, Peering)")

    # eks
    sub.add_parser("eks", help="Get EKS cluster and Fargate prices")

    # fargate
    sub.add_parser("fargate", help="Get Fargate vCPU and memory prices")

    # search
    p_search = sub.add_parser("search", help="Generic product search")
    p_search.add_argument("service_code", help="e.g. AmazonEC2")
    p_search.add_argument("filters_json", help='JSON string, e.g. \'{"instanceType":"t3.medium"}\'')
    p_search.add_argument("--limit", type=int, default=10)

    # list-services
    sub.add_parser("list-services", help="List available AWS service codes")

    # cache-status
    sub.add_parser("cache-status", help="Show cached files and their age")

    # refresh
    p_refresh = sub.add_parser("refresh", help="Force-refresh cache for a service")
    p_refresh.add_argument("service_code")

    args = parser.parse_args()
    pricing = AWSPricing(region=args.region)

    if args.cmd == "ec2":
        price = pricing.get_ec2_price(args.instance_type, os=args.os, tenancy=args.tenancy)
        _print_json({
            "service": "EC2",
            "instance_type": args.instance_type,
            "os": args.os,
            "tenancy": args.tenancy,
            "region": args.region,
            "price_usd_per_hour": price,
        })

    elif args.cmd == "rds":
        price = pricing.get_rds_price(args.instance_type, engine=args.engine, deployment=args.deployment)
        _print_json({
            "service": "RDS",
            "instance_type": args.instance_type,
            "engine": args.engine,
            "deployment": args.deployment,
            "region": args.region,
            "price_usd_per_hour": price,
        })

    elif args.cmd == "s3":
        price = pricing.get_s3_price(storage_class=args.storage_class)
        _print_json({
            "service": "S3",
            "storage_class": args.storage_class,
            "region": args.region,
            "price_usd_per_gb_month": price,
        })

    elif args.cmd == "lambda":
        compute = pricing.get_lambda_price()
        requests_ = pricing.get_lambda_request_price()
        _print_json({
            "service": "Lambda",
            "region": args.region,
            "price_usd_per_gb_second": compute,
            "price_usd_per_request": requests_,
        })

    elif args.cmd == "elasticache":
        price = pricing.get_elasticache_price(args.instance_type, cache_engine=args.engine)
        _print_json({
            "service": "ElastiCache",
            "instance_type": args.instance_type,
            "engine": args.engine,
            "region": args.region,
            "price_usd_per_hour": price,
        })

    elif args.cmd == "sqs":
        price = pricing.get_sqs_price(queue_type=args.queue_type)
        _print_json({
            "service": "SQS",
            "queue_type": args.queue_type,
            "region": args.region,
            "price_usd_per_million_requests": price,
        })

    elif args.cmd == "sns":
        _print_json({"service": "SNS", "region": args.region, **pricing.get_sns_price()})

    elif args.cmd == "eventbridge":
        _print_json({"service": "EventBridge", "region": args.region, **pricing.get_eventbridge_price()})

    elif args.cmd == "apigw":
        _print_json({"service": "API Gateway", "region": args.region, **pricing.get_api_gateway_price()})

    elif args.cmd == "alb":
        _print_json({"service": "ALB", "region": args.region, **pricing.get_alb_price()})

    elif args.cmd == "nlb":
        _print_json({"service": "NLB", "region": args.region, **pricing.get_nlb_price()})

    elif args.cmd == "vpc":
        _print_json({"service": "VPC", "region": args.region, **pricing.get_vpc_price()})

    elif args.cmd == "eks":
        cluster = pricing.get_eks_price()
        fargate = pricing.get_fargate_price()
        _print_json({
            "service": "EKS",
            "region": args.region,
            "price_usd_per_cluster_hour": cluster,
            "fargate": fargate,
        })

    elif args.cmd == "fargate":
        fargate = pricing.get_fargate_price()
        _print_json({"service": "Fargate", "region": args.region, **fargate})

    elif args.cmd == "search":
        try:
            filters = json.loads(args.filters_json)
        except json.JSONDecodeError as exc:
            print(f"Error: filters_json is not valid JSON: {exc}", file=sys.stderr)
            sys.exit(1)
        results = pricing.search(args.service_code, filters)
        _print_json(results[:args.limit])

    elif args.cmd == "list-services":
        services = pricing.list_services()
        for s in services:
            print(s)

    elif args.cmd == "cache-status":
        _print_json(pricing.cache_status())

    elif args.cmd == "refresh":
        pricing.refresh(args.service_code)
        print(f"Refreshed {args.service_code} cache.")


if __name__ == "__main__":
    main()
