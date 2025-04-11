# Kubernetes Metrics API

A streamlined API for extracting, transforming, and storing Kubernetes metrics from observability platforms (DataDog, New Relic) into a local database.

## Overview

This project demonstrates a Python Backend Engineering solution that:

1. Queries observability platform APIs (New Relic, DataDog)
2. Extracts Kubernetes cluster metrics (CPU, memory, pod count, namespace usage)
3. Transforms and stores data in a custom PostgreSQL format
4. Provides namespace cost analysis

## Architecture

- **REST API**: Built with FastAPI for querying and returning metrics
- **Database**: PostgreSQL for processed metrics storage
- **Cost Analysis**: Script for calculating approximate costs and generating reports

## Core Features

### Metric Endpoints

- `/nr/kubernetes`: Extracts Kubernetes metrics from New Relic (CPU, memory, pod count)
- `/nr/cpu`: Detailed CPU data
- `/nr/memory`: Detailed memory data
- `/nr/dashboard`: Main metrics dashboard
- `/fetch-datadog-metrics`: Fetches DataDog metrics (kubernetes.cpu.usage.total)

### Data Model

- `kubernetes_metrics` table: Stores Kubernetes-specific metrics with custom schema
- `metrics` table: Stores generic metrics

### Cost Analysis

The `kubernetes_cost_analysis.py` script provides:

- Approximate cost calculations based on CPU and memory usage
- Namespace and pod-level reports
- Cost visualization charts
- Usage and cost trends over time

## Installation

1. Clone the repository:
```bash
git clone https://github.com/your-username/metrics-api.git
cd metrics-api
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables in `.env`:

4. Run database migrations:
```bash
alembic upgrade head
```

5. Start the application:
```bash
uvicorn main:app --reload
```

## New Relic Setup

### 1. API Key Configuration

Configure the `.env` file with:
```bash
NEWRELIC_API_KEY=your_etl_key  # INGEST - LICENSE type key
NEWRELIC_ACCOUNT_ID=your_account_id
```

### 2. Kubernetes Installation

```bash
# Remove previous installation (if exists)
helm uninstall newrelic-bundle -n newrelic
kubectl delete namespace newrelic

# Create namespace
kubectl create namespace newrelic

# Install New Relic
helm install newrelic-bundle newrelic/nri-bundle \
  --set global.licenseKey=your_license_key \
  --set global.cluster=minikube-cluster \
  --namespace newrelic \
  --set global.lowDataMode=true \
  --set newrelic-infrastructure.privileged=true \
  --set newrelic-infrastructure.kubernetesCrds.enabled=true \
  --set newrelic-infrastructure.kubernetesMetrics.enabled=true \
  --set kube-state-metrics.enabled=true \
  --set kubeEvents.enabled=true \
  --set prometheus.enabled=true \
  --set logging.enabled=true
```

### 3. Installation Verification

```bash
# Verify running pods
kubectl get pods -n newrelic
```

## Traffic Generation and Metric Collection

### 1. Nginx Port Forward

In one terminal:
```bash
kubectl port-forward svc/nginx-test 8080:80
```

### 2. Traffic Generator

In another terminal:
```bash
python traffic-generator.py
```

### 3. ETL Execution

After a few minutes of traffic generation:
```bash
python etl_newrelic.py
```

### Workflow

1. Ensure New Relic is installed and running
2. Start Nginx port-forward
3. Run traffic generator
4. Wait 3-5 minutes for New Relic to collect data
5. Run ETL to process metrics

### Data Verification

To verify data collection:

1. Check New Relic pods:
```bash
kubectl get pods -n newrelic
```

2. Check ETL logs:
```bash
python etl_newrelic.py
```

3. Query metrics via API:
```bash
curl http://localhost:8000/nr/kubernetes
```

## Usage Examples

### New Relic Query Example

```python
import requests

headers = {
    "Accept": "application/json",
    "Api-Key": "NEWRELIC_API_KEY",
    "Content-Type": "application/json"
}

response = requests.get("http://localhost:8000/nr/kubernetes")
data = response.json()
print(data)
```

### Cost Analysis Example

```python
import asyncio
from kubernetes_cost_analysis import calculate_kubernetes_costs, generate_cost_charts

async def analyze():
    # Calculate costs for the last 24 hours
    costs = await calculate_kubernetes_costs(hours=24)
    print(f"Total cost: ${costs['total_cost']}")
    
    # Generate charts
    await generate_cost_charts(hours=24, output_dir="./reports")

if __name__ == "__main__":
    asyncio.run(analyze())
```

## Cost Reports & Visualizations

The system generates detailed cost analysis reports and visualizations to help understand resource usage and costs across your Kubernetes clusters.

### Generated Reports

#### 1. Cost Distribution by Namespace
<div align="center">
  <img src="reports/cost_distribution_24h.png" alt="Cost Distribution" width="600"/>
  <br>
  <em>Pie chart showing the percentage of total costs per namespace</em>
</div>

**Features:**
- Clear visualization of cost allocation
- Helps identify resource-heavy namespaces
- Shows cost percentage distribution

#### 2. Total Cost by Namespace
<div align="center">
  <img src="reports/cost_by_namespace_24h.png" alt="Total Cost" width="600"/>
  <br>
  <em>Bar chart displaying absolute cost values per namespace</em>
</div>

**Features:**
- Absolute cost values in dollars
- Easy comparison between namespaces
- Clear cost breakdown

### Report Features

<table>
  <tr>
    <th>Report Type</th>
    <th>Description</th>
    <th>Update Frequency</th>
  </tr>
  <tr>
    <td>Cost Distribution</td>
    <td>Percentage-based pie chart showing relative cost distribution</td>
    <td>Every 24 hours</td>
  </tr>
  <tr>
    <td>Total Cost</td>
    <td>Bar chart showing absolute cost values</td>
    <td>Every 24 hours</td>
  </tr>
  <tr>
    <td>Trend Analysis</td>
    <td>Line graph showing cost trends over time</td>
    <td>Hourly</td>
  </tr>
  <tr>
    <td>Resource Usage</td>
    <td>Combined CPU/Memory usage patterns</td>
    <td>Real-time</td>
  </tr>
</table>

### Sample Report Output

```json
{
  "report_timestamp": "2024-04-10T23:18:13.539",
  "total_cost": "$2.39",
  "namespace_distribution": {
    "default": {
      "cost": "$2.22",
      "percentage": "92.9%"
    },
    "kube-system": {
      "cost": "$0.12",
      "percentage": "5.0%"
    },
    "newrelic": {
      "cost": "$0.05",
      "percentage": "2.1%"
    }
  }
}
```

### Report Generation Commands

```bash
# Generate all reports
python kubernetes_cost_analysis.py --report-type=all

# Generate specific reports
python kubernetes_cost_analysis.py --report-type=distribution
python kubernetes_cost_analysis.py --report-type=total-cost

# Customization options
python kubernetes_cost_analysis.py \
  --report-type=all \
  --hours=48 \
  --format=png \
  --theme=dark \
  --output-dir=./reports
```

### Report Storage & Integration

📊 **Storage**
- Reports saved in `./reports` directory
- Organized by date and type
- Configurable retention period

🔗 **Integrations**
- Slack notifications
- Email reports
- S3 backup
- Custom webhooks

⚡ **Alerts**
```yaml
alerts:
  namespace_cost:
    threshold: 100  # Dollars
    period: 24h     # Time window
    actions:
      - slack
      - email
```
## Requirements

- Python 3.8+
- PostgreSQL
- New Relic API Key
- DataDog API Key (optional)

## Future Enhancements

- Support for additional observability platforms
- Cost-based alerting implementation
- Web dashboard development
- Resource optimization recommendations

## Technologies

- Python
- FastAPI
- PostgreSQL
- New Relic
- Kubernetes

