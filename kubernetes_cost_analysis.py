import asyncio
import datetime
import json
import os

import matplotlib.pyplot as plt
import pandas as pd
import sqlalchemy
from databases import Database
from dotenv import load_dotenv
from sqlalchemy.sql import desc, func, select, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
database = Database(DATABASE_URL)

# Function to connect to the database
async def connect_to_db():
    await database.connect()
    print("Connected to PostgreSQL database!")

# Function to disconnect from the database
async def disconnect_from_db():
    await database.disconnect()
    print("Disconnected from database!")

# Function to get Kubernetes metrics from the database
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

# Function to calculate approximate cost based on metrics
async def calculate_kubernetes_costs(hours=24):
    """
    Calculates approximate costs based on Kubernetes metrics
    
    Parameters:
    - hours: Data period in hours
    """
    print("\nIniciando cálculo de custos...")
    
    # Cost definition per unit (fictional example)
    costs = {
        "cpu_core_hour": 0.031,  # $0.031 per core/hour (based on GKE/EKS prices)
        "memory_gb_hour": 0.0042,  # $0.0042 per GB/hour (based on GKE/EKS prices)
    }
    
    print("\nBuscando dados de memória...")
    # Get memory data
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
    
    print(f"Registros de memória encontrados: {len(memory_data) if memory_data else 0}")
    
    # Se não houver dados de memória, tentar usar apenas dados de CPU
    if not memory_data:
        print("\nNenhum dado de memória encontrado. Tentando calcular custos apenas com CPU...")
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
        
        print(f"Registros de CPU encontrados: {len(cpu_only_data) if cpu_only_data else 0}")
        
        if not cpu_only_data:
            print("Nenhum dado de CPU encontrado também.")
            return {
                "timestamp": datetime.datetime.now().isoformat(),
                "period_hours": hours,
                "pod_details": [],
                "namespace_summary": [],
                "total_cost": 0
            }
            
        # Calcular custos apenas com CPU
        results = []
        total_cost = 0
        namespace_costs = {}
        
        for cpu_row in cpu_only_data:
            avg_cpu_cores = cpu_row['avg_cpu_cores'] or 0
            
            # Calculate cost
            cpu_cost = avg_cpu_cores * costs["cpu_core_hour"] * hours
            total_pod_cost = cpu_cost
            
            # Add to results
            pod_result = {
                "cluster_name": cpu_row['cluster_name'],
                "namespace": cpu_row['namespace'],
                "pod_name": cpu_row['pod_name'],
                "resources": {
                    "cpu_cores": avg_cpu_cores,
                    "memory_gb": 0  # Não temos dados de memória
                },
                "costs": {
                    "cpu_cost": round(cpu_cost, 2),
                    "memory_cost": 0,  # Não temos dados de memória
                    "total_cost": round(total_pod_cost, 2)
                }
            }
            results.append(pod_result)
            
            # Update total cost
            total_cost += total_pod_cost
            
            # Update costs by namespace
            namespace = cpu_row['namespace']
            if namespace not in namespace_costs:
                namespace_costs[namespace] = {
                    "cpu_cost": 0,
                    "memory_cost": 0,
                    "total_cost": 0
                }
            
            namespace_costs[namespace]["cpu_cost"] += cpu_cost
            namespace_costs[namespace]["total_cost"] += total_pod_cost
        
        # Format costs by namespace
        namespace_summary = []
        for namespace, costs_data in namespace_costs.items():
            namespace_summary.append({
                "namespace": namespace,
                "cpu_cost": round(costs_data["cpu_cost"], 2),
                "memory_cost": 0,  # Não temos dados de memória
                "total_cost": round(costs_data["total_cost"], 2),
                "percentage": round((costs_data["total_cost"] / total_cost) * 100, 2) if total_cost > 0 else 0
            })
        
        # Ordenar por custo total
        namespace_summary = sorted(namespace_summary, key=lambda x: x["total_cost"], reverse=True)
        
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "period_hours": hours,
            "pod_details": results,
            "namespace_summary": namespace_summary,
            "total_cost": round(total_cost, 2)
        }
    
    # Se temos dados de memória, continuar com o cálculo normal
    print("\nCalculando custos com CPU e memória...")
    results = []
    total_cost = 0
    namespace_costs = {}
    
    for memory_row in memory_data:
        print(f"\nProcessando pod: {memory_row['pod_name']}")
        # Find corresponding CPU data
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
        
        avg_memory_gb = memory_row['avg_memory_mb'] / 1024  # Convert MB to GB
        print(f"Memória média: {avg_memory_gb:.2f} GB")
        
        avg_cpu_cores = 0
        if cpu_data:
            avg_cpu_cores = cpu_data[0]['avg_cpu_cores']
        print(f"CPU média: {avg_cpu_cores:.2f} cores")
        
        # Calculate cost
        cpu_cost = avg_cpu_cores * costs["cpu_core_hour"] * hours
        memory_cost = avg_memory_gb * costs["memory_gb_hour"] * hours
        total_pod_cost = cpu_cost + memory_cost
        
        print(f"Custo CPU: ${cpu_cost:.2f}")
        print(f"Custo Memória: ${memory_cost:.2f}")
        print(f"Custo Total do Pod: ${total_pod_cost:.2f}")
        
        # Add to results
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
        
        # Update total cost
        total_cost += total_pod_cost
        
        # Update costs by namespace
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
    
    # Format costs by namespace
    namespace_summary = []
    for namespace, costs_data in namespace_costs.items():
        namespace_summary.append({
            "namespace": namespace,
            "cpu_cost": round(costs_data["cpu_cost"], 2),
            "memory_cost": round(costs_data["memory_cost"], 2),
            "total_cost": round(costs_data["total_cost"], 2),
            "percentage": round((costs_data["total_cost"] / total_cost) * 100, 2) if total_cost > 0 else 0
        })
    
    # Ordenar por custo total
    namespace_summary = sorted(namespace_summary, key=lambda x: x["total_cost"], reverse=True)
    
    print(f"\nCálculo finalizado. Custo total: ${round(total_cost, 2)}")
    
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "period_hours": hours,
        "pod_details": results,
        "namespace_summary": namespace_summary,
        "total_cost": round(total_cost, 2)
    }

# Function to generate cost charts by namespace
async def generate_cost_charts(hours=24, output_dir="./reports"):
    """
    Generates cost charts by namespace
    
    Parameters:
    - hours: Data period in hours
    - output_dir: Directory to save the charts
    """
    print("\nGerando gráficos de custos...")
    
    # Create absolute path for output directory
    output_dir = os.path.abspath(output_dir)
    
    # Create directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Diretório de saída: {output_dir}")
    
    # Get cost data
    cost_data = await calculate_kubernetes_costs(hours)
    
    if not cost_data:
        print("Nenhum dado de custo disponível")
        return None
        
    if not cost_data.get("namespace_summary"):
        print("Nenhum dado de namespace disponível")
        return None
    
    print(f"Encontrados dados de custo para {len(cost_data['namespace_summary'])} namespaces")
    
    # Create DataFrame for charts
    df = pd.DataFrame(cost_data["namespace_summary"])
    
    try:
        print("\nGerando gráfico de barras de custo total por namespace...")
        # Chart configuration
        plt.figure(figsize=(12, 8))
        
        # Bar chart for total cost by namespace
        ax = df.sort_values("total_cost", ascending=False).plot(
            x="namespace", 
            y="total_cost", 
            kind="bar", 
            color="steelblue",
            title=f"Custo Total por Namespace (últimas {hours} horas)"
        )
        
        # Add values to bars
        for i, v in enumerate(df.sort_values("total_cost", ascending=False)["total_cost"]):
            ax.text(i, v + 0.1, f"${v}", ha="center")
        
        plt.xlabel("Namespace")
        plt.ylabel("Custo ($)")
        plt.tight_layout()
        
        chart1_path = os.path.join(output_dir, f"cost_by_namespace_{hours}h.png")
        plt.savefig(chart1_path)
        print(f"Gráfico salvo: {chart1_path}")
        
        print("\nGerando gráfico de pizza de distribuição de custos...")
        # Pie chart for cost distribution
        plt.figure(figsize=(10, 10))
        
        # Show only top 5 namespaces, group the rest as "Others"
        if len(df) > 5:
            top_df = df.sort_values("total_cost", ascending=False).head(5)
            other_cost = df.sort_values("total_cost", ascending=False).iloc[5:]["total_cost"].sum()
            
            data = top_df["total_cost"].tolist() + [other_cost]
            labels = top_df["namespace"].tolist() + ["Outros"]
        else:
            data = df["total_cost"].tolist()
            labels = df["namespace"].tolist()
        
        # Add percentages to labels
        total = sum(data)
        labels = [f"{label} (${value:.2f}, {value/total*100:.1f}%)" for label, value in zip(labels, data)]
        
        # Pie chart
        plt.pie(data, labels=labels, autopct="%1.1f%%", shadow=True, startangle=90)
        plt.axis("equal")
        plt.title(f"Distribuição de Custos por Namespace (últimas {hours} horas)")
        
        chart2_path = os.path.join(output_dir, f"cost_distribution_{hours}h.png")
        plt.savefig(chart2_path)
        print(f"Gráfico salvo: {chart2_path}")
        
        # Only generate CPU vs Memory comparison if we have memory data
        if any(df["memory_cost"] > 0):
            print("\nGerando gráfico de comparação CPU vs Memória...")
            # CPU vs Memory comparison chart
            plt.figure(figsize=(12, 8))
            
            # Create data for the chart
            cpu_costs = df.sort_values("total_cost", ascending=False).head(10)["cpu_cost"]
            memory_costs = df.sort_values("total_cost", ascending=False).head(10)["memory_cost"]
            namespaces = df.sort_values("total_cost", ascending=False).head(10)["namespace"]
            
            x = range(len(namespaces))
            width = 0.35
            
            fig, ax = plt.subplots(figsize=(12, 8))
            rects1 = ax.bar([i - width/2 for i in x], cpu_costs, width, label="CPU")
            rects2 = ax.bar([i + width/2 for i in x], memory_costs, width, label="Memória")
            
            ax.set_xlabel("Namespace")
            ax.set_ylabel("Custo ($)")
            ax.set_title(f"Comparação de Custos CPU vs Memória por Namespace (últimas {hours} horas)")
            ax.set_xticks(x)
            ax.set_xticklabels(namespaces, rotation=45, ha="right")
            ax.legend()
            
            plt.tight_layout()
            
            chart3_path = os.path.join(output_dir, f"cpu_vs_memory_{hours}h.png")
            plt.savefig(chart3_path)
            print(f"Gráfico salvo: {chart3_path}")
            
            charts_generated = [chart1_path, chart2_path, chart3_path]
        else:
            print("\nDados de memória não disponíveis, pulando gráfico de comparação CPU vs Memória")
            charts_generated = [chart1_path, chart2_path]
        
        print(f"\nTodos os gráficos foram salvos no diretório: {output_dir}")
        return {
            "charts_generated": charts_generated,
            "data": cost_data
        }
    
    except Exception as e:
        print(f"Erro ao gerar gráficos: {str(e)}")
        return None
    finally:
        plt.close('all')  # Clean up all plots

# Main function to run the analysis
async def main():
    try:
        # Connect to database
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
        # Disconnect from database
        await disconnect_from_db()

# Run script
if __name__ == "__main__":
    asyncio.run(main()) 