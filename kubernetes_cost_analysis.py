import asyncio
import datetime
import json
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sqlalchemy
from databases import Database
from dotenv import load_dotenv
from sqlalchemy.sql import desc, func, select, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
database = Database(DATABASE_URL)


async def connect_to_db():
    await database.connect()
    print("Connected to PostgreSQL database!")


async def disconnect_from_db():
    await database.disconnect()
    print("Disconnected from database!")


async def get_kubernetes_metrics(hours=24, metric_type=None):
    """
    Gets Kubernetes metrics from the database
    
    Parameters:
    - hours: Data period in hours
    - metric_type: Filter by metric type (cpu, memory, kubernetes)
    """
    query = """
    SELECT * FROM kubernetes_metrics 
    WHERE timestamp >= NOW() - INTERVAL '1 hour' * :hours
    """
    
    if metric_type:
        query += " AND metric_type = :metric_type"
    
    query += " ORDER BY timestamp DESC"
    
    result = await database.fetch_all(
        query=query,
        values={
            "hours": hours,
            "metric_type": metric_type
        }
    )
    return result


async def calculate_kubernetes_costs(hours=24):
    """
    Calculates approximate costs based on Kubernetes metrics
    
    Parameters:
    - hours: Data period in hours
    """
    print("\nStarting cost calculation...")
    
    
    costs = {
        "cpu_core_hour": 0.031,  
        "memory_gb_hour": 0.0042,  
    }
    
    print("\nFetching memory data...")
    
    memory_data = await database.fetch_all(
        """
        SELECT 
            cluster_name, 
            namespace,
            pod_name,
            AVG(value) as avg_memory_mb,
            COUNT(*) as sample_count
        FROM kubernetes_metrics
        WHERE 
            metric_type = 'memory' AND
            metric_name = 'used_mb' AND
            timestamp >= NOW() - INTERVAL '1 hour' * :hours
        GROUP BY cluster_name, namespace, pod_name
        """,
        values={"hours": hours}
    )
    
    print(f"Memory records found: {len(memory_data) if memory_data else 0}")
    
    
    if not memory_data:
        print("\nNo memory data found. Trying to calculate costs with CPU only...")
        cpu_only_data = await database.fetch_all(
            """
            SELECT 
                cluster_name,
                namespace,
                pod_name,
                AVG(value) as avg_cpu_cores,
                COUNT(*) as sample_count
            FROM kubernetes_metrics
            WHERE 
                metric_type = 'cpu' AND
                metric_name = 'used_cores' AND
                timestamp >= NOW() - INTERVAL '1 hour' * :hours
            GROUP BY cluster_name, namespace, pod_name
            """,
            values={"hours": hours}
        )
        
        print(f"CPU records found: {len(cpu_only_data) if cpu_only_data else 0}")
        
        if not cpu_only_data:
            print("No CPU data found either.")
            return {
                "timestamp": datetime.datetime.now().isoformat(),
                "period_hours": hours,
                "pod_details": [],
                "namespace_summary": [],
                "total_cost": 0
            }
            
        
        results = []
        total_cost = 0
        namespace_costs = {}
        
        for cpu_row in cpu_only_data:
            avg_cpu_cores = cpu_row['avg_cpu_cores'] or 0
            
            
            cpu_cost = avg_cpu_cores * costs["cpu_core_hour"] * hours
            total_pod_cost = cpu_cost
            
            
            pod_result = {
                "cluster_name": cpu_row['cluster_name'],
                "namespace": cpu_row['namespace'],
                "pod_name": cpu_row['pod_name'],
                "resources": {
                    "cpu_cores": avg_cpu_cores,
                    "memory_gb": 0  
                },
                "costs": {
                    "cpu_cost": round(cpu_cost, 2),
                    "memory_cost": 0,  
                    "total_cost": round(total_pod_cost, 2)
                }
            }
            results.append(pod_result)
            
            
            total_cost += total_pod_cost
            
            
            namespace = cpu_row['namespace']
            if namespace not in namespace_costs:
                namespace_costs[namespace] = {
                    "cpu_cost": 0,
                    "memory_cost": 0,
                    "total_cost": 0
                }
            
            namespace_costs[namespace]["cpu_cost"] += cpu_cost
            namespace_costs[namespace]["total_cost"] += total_pod_cost
        
        
        namespace_summary = []
        for namespace, costs_data in namespace_costs.items():
            namespace_summary.append({
                "namespace": namespace,
                "cpu_cost": round(costs_data["cpu_cost"], 2),
                "memory_cost": 0,  
                "total_cost": round(costs_data["total_cost"], 2),
                "percentage": round((costs_data["total_cost"] / total_cost) * 100, 2) if total_cost > 0 else 0
            })
        
        
        namespace_summary = sorted(namespace_summary, key=lambda x: x["total_cost"], reverse=True)
        
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "period_hours": hours,
            "pod_details": results,
            "namespace_summary": namespace_summary,
            "total_cost": round(total_cost, 2)
        }
    
    
    print("\nCalculating costs with CPU and memory...")
    results = []
    total_cost = 0
    namespace_costs = {}
    
    for memory_row in memory_data:
        print(f"\nProcessing pod: {memory_row['pod_name']}")
        
        cpu_data = await database.fetch_all(
            """
            SELECT 
                AVG(value) as avg_cpu_cores
            FROM kubernetes_metrics
            WHERE 
                metric_type = 'cpu' AND
                metric_name = 'used_cores' AND
                cluster_name = :cluster_name AND
                namespace = :namespace AND
                pod_name = :pod_name AND
                timestamp >= NOW() - INTERVAL '1 hour' * :hours
            GROUP BY cluster_name, namespace, pod_name
            """,
            values={
                "cluster_name": memory_row['cluster_name'],
                "namespace": memory_row['namespace'],
                "pod_name": memory_row['pod_name'],
                "hours": hours
            }
        )
        
        avg_memory_gb = memory_row['avg_memory_mb'] / 1024  
        print(f"Average Memory: {avg_memory_gb:.2f} GB")
        
        avg_cpu_cores = 0
        if cpu_data:
            avg_cpu_cores = cpu_data[0]['avg_cpu_cores']
        print(f"Average CPU: {avg_cpu_cores:.2f} cores")
        
        
        cpu_cost = avg_cpu_cores * costs["cpu_core_hour"] * hours
        memory_cost = avg_memory_gb * costs["memory_gb_hour"] * hours
        total_pod_cost = cpu_cost + memory_cost
        
        print(f"CPU Cost: ${cpu_cost:.2f}")
        print(f"Memory Cost: ${memory_cost:.2f}")
        print(f"Total Pod Cost: ${total_pod_cost:.2f}")
        
        
        pod_result = {
            "cluster_name": memory_row['cluster_name'],
            "namespace": memory_row['namespace'],
            "pod_name": memory_row['pod_name'],
            "resources": {
                "cpu_cores": avg_cpu_cores,
                "memory_gb": avg_memory_gb
            },
            "costs": {
                "cpu_cost": round(cpu_cost, 2),
                "memory_cost": round(memory_cost, 2),
                "total_cost": round(total_pod_cost, 2)
            }
        }
        results.append(pod_result)
        
        
        total_cost += total_pod_cost
        
        
        namespace = memory_row['namespace']
        if namespace not in namespace_costs:
            namespace_costs[namespace] = {
                "cpu_cost": 0,
                "memory_cost": 0,
                "total_cost": 0
            }
        
        namespace_costs[namespace]["cpu_cost"] += cpu_cost
        namespace_costs[namespace]["memory_cost"] += memory_cost
        namespace_costs[namespace]["total_cost"] += total_pod_cost
    
    
    namespace_summary = []
    for namespace, costs_data in namespace_costs.items():
        namespace_summary.append({
            "namespace": namespace,
            "cpu_cost": round(costs_data["cpu_cost"], 2),
            "memory_cost": round(costs_data["memory_cost"], 2),
            "total_cost": round(costs_data["total_cost"], 2),
            "percentage": round((costs_data["total_cost"] / total_cost) * 100, 2) if total_cost > 0 else 0
        })
    
    
    namespace_summary = sorted(namespace_summary, key=lambda x: x["total_cost"], reverse=True)
    
    print(f"\nCalculation finished. Total cost: ${round(total_cost, 2)}")
    
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "period_hours": hours,
        "pod_details": results,
        "namespace_summary": namespace_summary,
        "total_cost": round(total_cost, 2)
    }


async def generate_cost_charts(hours=24, output_dir="./reports"):
    """
    Generates cost charts by namespace
    
    Parameters:
    - hours: Data period in hours
    - output_dir: Directory to save the charts
    """
    print("\nGenerating cost charts...")
    
    
    output_dir = os.path.abspath(output_dir)
    
    
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Output directory: {output_dir}")
    
    
    cost_data = await calculate_kubernetes_costs(hours)
    
    if not cost_data:
        print("No cost data available")
        return None
        
    if not cost_data.get("namespace_summary"):
        print("No namespace data available")
        return None
    
    print(f"Found cost data for {len(cost_data['namespace_summary'])} namespaces")
    
    
    df = pd.DataFrame(cost_data["namespace_summary"])
    
    try:
        print("\nGenerating total cost bar chart by namespace...")
        
        plt.style.use('default')  
        
        
        plt.rcParams.update({
            'font.size': 12,
            'font.family': 'sans-serif',
            'axes.labelsize': 14,
            'axes.titlesize': 16,
            'figure.titlesize': 18,
            'legend.fontsize': 12,
            'figure.figsize': (12, 8),
            'figure.dpi': 100
        })
        
        
        plt.figure(figsize=(12, 8))
        
        
        colors = ['#2E86C1', '#28B463', '#F1C40F', '#E67E22', '#CB4335', '#7D3C98']
        
        
        total = df["total_cost"].sum()
        
        
        labels = [
            f"{label}\n${value:.2f}\n{value/total*100:.1f}%"
            for label, value in zip(df["namespace"], df["total_cost"])
        ]
        
        
        patches, texts, autotexts = plt.pie(
            df["total_cost"],
            labels=labels,
            colors=colors,
            autopct='%1.1f%%',
            shadow=False,
            startangle=90,
            textprops={'fontsize': 10},
            wedgeprops={'linewidth': 2, 'edgecolor': 'white'},
            pctdistance=0.85,
            labeldistance=1.1
        )
        
        
        plt.axis('equal')
        
        
        bbox_props = dict(boxstyle="round,pad=0.3", fc="w", ec="gray", alpha=0.9)
        
        
        angles = []
        start_angle = 90
        for value in df["total_cost"]:
            angle = value / total * 360
            center_angle = start_angle - angle / 2
            angles.append(np.radians(center_angle))
            start_angle -= angle
        
        
        for i, (text, angle) in enumerate(zip(texts, angles)):
            
            value = df["total_cost"].iloc[i]
            percentage = value / total
            namespace = df["namespace"].iloc[i]
            
            
            if percentage > 0.5:  
                radius = 0.8
            elif namespace == "newrelic":  
                radius = 1.5
                angle = np.radians(45)  
            elif percentage > 0.1:  
                radius = 1.4
            else:  
                radius = 1.2
            
            
            x = np.cos(angle) * radius
            y = np.sin(angle) * radius
            
            
            if x < 0:
                text.set_horizontalalignment('right')
            else:
                text.set_horizontalalignment('left')
            
            
            if abs(y) < 0.2 and namespace != "newrelic":  
                y += 0.2 * (1 if y >= 0 else -1)
            
            text.set_position((x, y))
            text.set_bbox(bbox_props)
        
        
        for autotext in autotexts:
            autotext.set_visible(False)
        
        plt.title(
            f"Cost Distribution by Namespace\n(last {hours} hours)",
            pad=20,
            fontweight='bold'
        )
        
        
        chart1_path = os.path.join(output_dir, f"cost_distribution_{hours}h.png")
        plt.savefig(chart1_path, bbox_inches='tight', dpi=100)
        plt.close()
        
        
        plt.figure()
        bars = plt.bar(
            range(len(df["namespace"])),
            df["total_cost"],
            color=colors[:len(df["namespace"])],
            width=0.7
        )
        
        
        for bar in bars:
            height = bar.get_height()
            plt.text(
                bar.get_x() + bar.get_width()/2.,
                height,
                f'${height:.2f}',
                ha='center',
                va='bottom',
                fontsize=12,
                fontweight='bold'
            )
        
        plt.xticks(
            range(len(df["namespace"])),
            df["namespace"],
            rotation=45,
            ha='right',
            fontweight='bold'
        )
        
        plt.title(
            f"Total Cost by Namespace\n(last {hours} hours)",
            pad=20,
            fontweight='bold'
        )
        plt.xlabel("Namespace", labelpad=10, fontweight='bold')
        plt.ylabel("Cost ($)", labelpad=10, fontweight='bold')
        plt.grid(True, linestyle='--', alpha=0.7)
        
        
        chart2_path = os.path.join(output_dir, f"cost_by_namespace_{hours}h.png")
        plt.savefig(chart2_path, bbox_inches='tight', dpi=100)
        plt.close()
        
        charts_generated = [chart1_path, chart2_path]
        print(f"\nCharts saved successfully:")
        print(f"- Cost Distribution: {chart1_path}")
        print(f"- Total Cost: {chart2_path}")
        
        return {
            "charts_generated": charts_generated,
            "data": cost_data
        }
    
    except Exception as e:
        print(f"Error generating charts: {str(e)}")
        return None
    finally:
        plt.close('all')  


async def main():
    try:
        
        await connect_to_db()
        
        print("Calculating Kubernetes costs...")
        costs = await calculate_kubernetes_costs(hours=24)
        
        print("\nCost Summary by Namespace:")
        for ns in costs["namespace_summary"]:
            print(f"- {ns['namespace']}: ${ns['total_cost']} ({ns['percentage']}%)")
        
        print(f"\nTotal Cost: ${costs['total_cost']}")
        
        print("\nGenerating graphs...")
        await generate_cost_charts(hours=24)
        
        print("\nAnalysis complete!")
    
    finally:
        
        await disconnect_from_db()


if __name__ == "__main__":
    asyncio.run(main()) 