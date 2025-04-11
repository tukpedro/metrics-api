import asyncio
import datetime
import json
import os
from time import sleep

import requests
from databases import Database
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
NEWRELIC_API_KEY = os.getenv("NEWRELIC_API_KEY")
NEWRELIC_ACCOUNT_ID = os.getenv("NEWRELIC_ACCOUNT_ID", "6593256")  # Default value if not found in .env

# Add this check after loading environment variables
if not all([DATABASE_URL, NEWRELIC_API_KEY, NEWRELIC_ACCOUNT_ID]):
    print("Error: Environment variables not properly configured")
    print(f"DATABASE_URL: {'Configured' if DATABASE_URL else 'Not configured'}")
    print(f"NEWRELIC_API_KEY: {'Configured' if NEWRELIC_API_KEY else 'Not configured'}")
    print(f"NEWRELIC_ACCOUNT_ID: {'Configured' if NEWRELIC_ACCOUNT_ID else 'Not configured'}")
    exit(1)

database = Database(DATABASE_URL)

async def extract_kubernetes_metrics(hours_ago=6):
    """Extracts Kubernetes metrics from New Relic"""
    headers = {
        "Accept": "application/json",
        "Api-Key": NEWRELIC_API_KEY,
        "Content-Type": "application/json"
    }
    
    # Converter horas para minutos
    minutes_ago = int(hours_ago * 60)
    minutes_interval = minutes_ago - 10  # 10 minutes before
    
    # Two separate queries for CPU and memory
    query = """
    {
      actor {
        account(id: %d) {
          cpu: nrql(query: "SELECT latest(cpuUsedCores) as 'value', latest(status) as 'status' FROM K8sContainerSample WHERE clusterName IS NOT NULL FACET clusterName, namespaceName, podName, containerName SINCE %d minutes ago UNTIL %d minutes ago LIMIT 1000") {
            results
          }
          memory: nrql(query: "SELECT latest(memoryUsedBytes)/1024/1024 as 'value', latest(status) as 'status' FROM K8sContainerSample WHERE clusterName IS NOT NULL FACET clusterName, namespaceName, podName, containerName SINCE %d minutes ago UNTIL %d minutes ago LIMIT 1000") {
            results
          }
        }
      }
    }
    """ % (
        int(NEWRELIC_ACCOUNT_ID), 
        minutes_ago, minutes_interval,
        minutes_ago, minutes_interval
    )
    
    try:
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": query}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nQuerying data from {minutes_ago} to {minutes_interval} minutes ago")
            
            if "errors" in data:
                print("Error in API response:")
                for error in data["errors"]:
                    print(f"- {error['message']}")
                return None
                
            return data
        else:
            print(f"Request error: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"Error extracting data: {str(e)}")
        return None

async def transform_metrics(data):
    """Transforms data from New Relic format to our format"""
    if not data or 'data' not in data:
        return []
    
    metrics = []
    timestamp = datetime.datetime.now()
    
    # At the beginning of transform_metrics function
    print(f"Received data: {json.dumps(data, indent=2)}")
    
    # Process CPU metrics
    cpu_results = data['data']['actor']['account']['cpu']['results']
    for result in cpu_results:
        facets = result.get('facet', [])
        if len(facets) >= 4:
            cluster, namespace, pod, container = facets[:4]
            
            if result.get('value') is not None:
                metrics.append({
                    "timestamp": timestamp,
                    "cluster_name": cluster,
                    "namespace": namespace,
                    "pod_name": pod,
                    "container_name": container,
                    "metric_type": "cpu",
                    "metric_name": "used_cores",
                    "value": float(result['value']),
                    "unit": "cores",
                    "metadata": json.dumps({
                        "status": result.get('status', 'unknown')
                    })
                })
    
    # Before processing memory
    print(f"Memory results: {json.dumps(data['data']['actor']['account']['memory']['results'], indent=2)}")
    
    # Process memory metrics
    memory_results = data['data']['actor']['account']['memory']['results']
    for result in memory_results:
        facets = result.get('facet', [])
        if len(facets) >= 4:
            cluster, namespace, pod, container = facets[:4]
            
            if result.get('value') is not None:
                metrics.append({
                    "timestamp": timestamp,
                    "cluster_name": cluster,
                    "namespace": namespace,
                    "pod_name": pod,
                    "container_name": container,
                    "metric_type": "memory",
                    "metric_name": "used_mb",
                    "value": float(result['value']),
                    "unit": "MB",
                    "metadata": json.dumps({
                        "status": result.get('status', 'unknown')
                    })
                })
    
    return metrics

async def load_metrics(metrics):
    """Loads metrics into the database"""
    if not metrics:
        return 0
    
    try:
        # Inserir em lote
        query = """
        INSERT INTO kubernetes_metrics (
            timestamp, cluster_name, namespace, pod_name, container_name,
            metric_type, metric_name, value, unit, metadata
        ) VALUES (
            :timestamp, :cluster_name, :namespace, :pod_name, :container_name,
            :metric_type, :metric_name, :value, :unit, :metadata
        )
        """
        
        await database.execute_many(query=query, values=metrics)
        return len(metrics)
    
    except Exception as e:
        print(f"Error loading data: {str(e)}")
        return 0

async def etl_process(hours_ago=24):
    """Executes the complete ETL process"""
    print(f"\nStarting ETL for data from {hours_ago} hours ago...")
    
    # Extract
    print("Extracting data from New Relic...")
    data = await extract_kubernetes_metrics(hours_ago)
    
    if not data:
        print("No data to transform")
        return 0
    
    # Transform
    print("Transforming data...")
    metrics = await transform_metrics(data)
    
    if not metrics:
        print("Nenhum dado para transformar")
        return 0
    
    print(f"Transformed data: {len(metrics)} metrics")
    
    # Load
    print("Loading data into database...")
    inserted = await load_metrics(metrics)
    
    print(f"Loaded data: {inserted} records")
    return inserted

async def main():
    print("=== New Relic Kubernetes Metrics ETL ===")
    
    try:
        # Conectar ao banco
        await database.connect()
        print("Connected to database")
        
        # Coletar dados em intervalos de 10 minutos para 6 horas
        total_inserted = 0
        intervals = 6 * 6  # 6 hours * 6 (10 minutes intervals) = 36 intervals
        
        for interval in range(intervals, 0, -1):
            # Converter intervalo para horas
            hours = interval / 6  # Converte intervalo de 10min para horas
            inserted = await etl_process(hours_ago=hours)
            total_inserted += inserted
            
            current_time = datetime.datetime.now() - datetime.timedelta(minutes=interval*10)
            print(f"Progress: {intervals-interval}/{intervals} intervals processed")
            print(f"Period: {current_time.strftime('%Y-%m-%d %H:%M')}")
            
            # Small pause to not overload the API
            sleep(0.5)
        
        print(f"\nTotal records inserted: {total_inserted}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
    
    finally:
        await database.disconnect()
        print("Disconnected from database")

if __name__ == "__main__":
    asyncio.run(main())
