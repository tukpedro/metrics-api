import datetime
import json
import os
from contextlib import asynccontextmanager

import requests
from databases import Database
from dotenv import load_dotenv
from fastapi import FastAPI

from models import kubernetes_metrics, metrics

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
DATADOG_API_KEY = os.getenv("DATADOG_API_KEY")
DATADOG_APP_KEY = os.getenv("DATADOG_APP_KEY")
NEWRELIC_API_KEY = os.getenv("NEWRELIC_API_KEY")
NEWRELIC_ACCOUNT_ID = "6593256"  # Usando o valor do seu comando de instalação

database = Database(DATABASE_URL)

# Constante com o GUID correto do host
TUKSTATION_ENTITY_GUID = "NjU5MzI1NnxJTkZSQXxOQXwzNTE5MDI0NDc4NjQxMzMzNzMx"

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()
    yield
    await database.disconnect()

app = FastAPI(
    lifespan=lifespan,
    title="Metrics API",
    description="API para coletar e armazenar métricas de sistemas de monitoramento como New Relic e DataDog",
    version="1.0.0"
)

@app.get("/")
async def root():
    """
    Página principal que lista todos os endpoints disponíveis.
    """
    # URL base para acessar a API
    base_url = "http://localhost:8000"
    
    endpoints = {
        "DataDog": [
            {
                "path": "/fetch-datadog-metrics",
                "url": f"{base_url}/fetch-datadog-metrics",
                "description": "Busca métricas do DataDog (kubernetes.cpu.usage.total)"
            }
        ],
        "New Relic": [
            {
                "path": "/test-newrelic-connection",
                "url": f"{base_url}/test-newrelic-connection",
                "description": "Testa a conexão com a API do New Relic"
            },
            {
                "path": "/test-newrelic-agent",
                "url": f"{base_url}/test-newrelic-agent",
                "description": "Verifica o status do agente New Relic e metadados do host"
            },
            {
                "path": "/list-newrelic-hosts",
                "url": f"{base_url}/list-newrelic-hosts",
                "description": "Lista todos os hosts disponíveis no New Relic"
            },
            {
                "path": "/fetch-newrelic-basic",
                "url": f"{base_url}/fetch-newrelic-basic",
                "description": "Endpoint simplificado que busca apenas métricas básicas de CPU e memória"
            },
            {
                "path": "/discover-newrelic-data",
                "url": f"{base_url}/discover-newrelic-data",
                "description": "Ferramenta de diagnóstico para descobrir tipos de eventos e métricas disponíveis"
            }
        ],
        "New Relic Detalhado (nr/)": [
            {
                "path": "/nr/cpu",
                "url": f"{base_url}/nr/cpu",
                "description": "Dados detalhados de CPU (atual e histórico)"
            },
            {
                "path": "/nr/memory",
                "url": f"{base_url}/nr/memory",
                "description": "Dados detalhados de memória (atual e histórico)"
            },
            {
                "path": "/nr/disk",
                "url": f"{base_url}/nr/disk",
                "description": "Dados detalhados dos discos por dispositivo"
            },
            {
                "path": "/nr/network",
                "url": f"{base_url}/nr/network",
                "description": "Dados detalhados de rede por interface"
            },
            {
                "path": "/nr/processes",
                "url": f"{base_url}/nr/processes",
                "description": "Informações sobre processos em execução, ordenados por CPU e memória"
            },
            {
                "path": "/nr/dashboard",
                "url": f"{base_url}/nr/dashboard",
                "description": "Dashboard resumido com métricas atuais principais"
            },
            {
                "path": "/nr/complete",
                "url": f"{base_url}/nr/complete?hours=6",
                "description": "Dashboard completo com métricas atuais e históricas (parâmetro hours controla período)"
            }
        ]
    }
    
    # Informações do servidor
    server_info = {
        "api_version": "1.0.0",
        "datadog_configured": bool(DATADOG_API_KEY),
        "newrelic_configured": bool(NEWRELIC_API_KEY),
        "newrelic_account_id": NEWRELIC_ACCOUNT_ID,
        "tukstation_entity_guid": TUKSTATION_ENTITY_GUID,
        "database_url": DATABASE_URL.replace("postgresql+psycopg2://", "postgres://").split("@")[1] if "@" in DATABASE_URL else None
    }
    
    return {
        "title": "Metrics API",
        "description": "API para coleta de métricas de New Relic e DataDog",
        "server_info": server_info,
        "endpoints": endpoints,
        "docs_url": f"{base_url}/docs"
    }

@app.get("/fetch-datadog-metrics")
async def fetch_datadog_metrics():
    try:
        headers = {
            "Accept": "application/json",
            "DD-API-KEY": DATADOG_API_KEY,
            # "DD-APPLICATION-KEY": DATADOG_APP_KEY,
        }

        params = {
            "from": int(__import__("time").time()) - 3600,
            "to": int(__import__("time").time()),
            "query": "avg:kubernetes.cpu.usage.total{*}",
        }

        response = requests.get(
            "https://api.datadoghq.com/api/v1/validate", headers=headers
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("series"):
            return {
                "error": "Nenhum dado encontrado",
                "status_code": response.status_code,
                "response": data
            }

        value = data["series"][0]["pointlist"][-1][1] if data["series"][0].get("pointlist") else 0.0

        query = metrics.insert().values(
            platform="DataDog", metric_name="kubernetes.cpu.usage.total", value=value
        )

        await database.execute(query)
        return {
            "platform": "DataDog",
            "metric": "kubernetes.cpu.usage.total",
            "value": value,
        }

    except requests.exceptions.RequestException as e:
        return {
            "error": f"Erro na requisição ao Datadog: {str(e)}",
            "status_code": getattr(e.response, 'status_code', None)
        }
    except Exception as e:
        return {
            "error": f"Erro inesperado: {str(e)}"
        }


    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }

        # Usando GraphQL para consultar métricas de memória
        graphql_query = """
        {
          actor {
            account(id: 6593256) {
              nrql(query: "SELECT average(memoryUsedPercent) FROM Metric WHERE entityGuid = 'MzM4MjQxN3xJTkZSQXxOQXwyMzUxOTk0NzMzMTM5MTU5MTY4' SINCE 1 hour ago") {
                results
              }
            }
          }
        }
        """
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": graphql_query}
        )
        response.raise_for_status()
        data = response.json()

        # Extraindo o valor da métrica da resposta GraphQL
        value = 0.0
        if "data" in data and "actor" in data["data"] and "account" in data["data"]["actor"]:
            results = data["data"]["actor"]["account"]["nrql"]["results"]
            if len(results) > 0 and "average.host.memoryUsedPercent" in results[0]:
                value = results[0]["average.host.memoryUsedPercent"]

        # Inserindo na base de dados
        query = metrics.insert().values(
            platform="NewRelic", metric_name="host.memoryUsedPercent", value=value
        )

        await database.execute(query)
        return {
            "platform": "NewRelic",
            "metric": "host.memoryUsedPercent",
            "value": value,
        }

    except requests.exceptions.RequestException as e:
        return {
            "error": f"Erro na requisição ao New Relic: {str(e)}",
            "status_code": getattr(e.response, 'status_code', None),
            "response": getattr(e, 'response', {}).text if hasattr(e, 'response') else None
        }
    except Exception as e:
        return {
            "error": f"Erro inesperado: {str(e)}"
        }

@app.get("/fetch-newrelic-all")
async def fetch_newrelic_all(hostname: str = "TUKSTATION"):
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }

        # NRQL que especifica o hostname exato
        account_query = """
        {
          actor {
            account(id: 6593256) {
              system: nrql(query: "SELECT latest(timestamp), latest(cpuPercent) as cpu, latest(memoryPercent) as memory, latest(diskFreePercent) as diskFree FROM SystemSample WHERE hostname = '%s' SINCE 10 minutes ago LIMIT 1") {
                results
              }
              network: nrql(query: "SELECT latest(timestamp), sum(transmitBytesPerSecond) as network_tx, sum(receiveBytesPerSecond) as network_rx FROM NetworkSample WHERE hostname = '%s' SINCE 10 minutes ago LIMIT 1") {
                results
              }
              processes: nrql(query: "SELECT latest(timestamp), count(*) as processCount FROM ProcessSample WHERE hostname = '%s' SINCE 10 minutes ago LIMIT 1") {
                results
              }
              diskDetails: nrql(query: "SELECT latest(timestamp), deviceName, diskUsedPercent FROM DiskSample WHERE hostname = '%s' SINCE 10 minutes ago LIMIT 100") {
                results
              }
              topProcesses: nrql(query: "SELECT latest(timestamp), processDisplayName, cpuPercent, memoryResidentSizeBytes FROM ProcessSample WHERE hostname = '%s' ORDER BY cpuPercent DESC LIMIT 5") {
                results
              }
            }
          }
        }
        """ % (hostname, hostname, hostname, hostname, hostname)
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": account_query}
        )
        response.raise_for_status()
        data = response.json()
        
        # Verificar se a estrutura da resposta está completa
        if not data or "data" not in data:
            return {
                "error": "Resposta da API inválida",
                "response": data
            }
            
        if "actor" not in data.get("data", {}) or "account" not in data.get("data", {}).get("actor", {}):
            return {
                "error": "Estrutura de resposta inválida",
                "response": data
            }
            
        account_data = data.get("data", {}).get("actor", {}).get("account", {})
        
        # Criar estrutura de resultado
        result = {
            "platform": "NewRelic",
            "hostname": hostname,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "metrics": {
                "system": {},
                "network": {},
                "processes": {},
                "disks": [],
                "top_processes": []
            }
        }
        
        # Processar métricas do sistema com verificações de segurança
        system_results = []
        if account_data.get("system") and isinstance(account_data.get("system"), dict):
            system_results = account_data.get("system", {}).get("results", [])
            
        if system_results and len(system_results) > 0:
            for metric_name, key in [
                ("system.cpuPercent", "cpu"),
                ("system.memoryPercent", "memory"),
                ("system.diskFreePercent", "diskFree")
            ]:
                if key in system_results[0]:
                    value = system_results[0].get(key)
                    # Registrar no banco de dados se o valor não for None
                    if value is not None:
                        try:
                            await database.execute(
                                metrics.insert().values(
                                    platform="NewRelic", 
                                    metric_name=metric_name, 
                                    value=float(value)
                                )
                            )
                            result["metrics"]["system"][key] = value
                        except Exception as e:
                            result["metrics"]["system"][key] = f"Erro: {str(e)}"

        # Processar métricas de rede com verificações de segurança
        network_results = []
        if account_data.get("network") and isinstance(account_data.get("network"), dict):
            network_results = account_data.get("network", {}).get("results", [])
            
        if network_results and len(network_results) > 0:
            for metric_name, key in [
                ("network.transmitBytesPerSecond", "network_tx"),
                ("network.receiveBytesPerSecond", "network_rx")
            ]:
                if key in network_results[0]:
                    value = network_results[0].get(key)
                    # Registrar no banco de dados se o valor não for None
                    if value is not None:
                        try:
                            await database.execute(
                                metrics.insert().values(
                                    platform="NewRelic", 
                                    metric_name=metric_name, 
                                    value=float(value)
                                )
                            )
                            result["metrics"]["network"][key.replace("network_", "")] = value
                        except Exception as e:
                            result["metrics"]["network"][key.replace("network_", "")] = f"Erro: {str(e)}"
        
        # Processar contagem de processos com verificações de segurança
        processes_results = []
        if account_data.get("processes") and isinstance(account_data.get("processes"), dict):
            processes_results = account_data.get("processes", {}).get("results", [])
            
        if processes_results and len(processes_results) > 0:
            if "processCount" in processes_results[0]:
                value = processes_results[0].get("processCount")
                if value is not None:
                    try:
                        await database.execute(
                            metrics.insert().values(
                                platform="NewRelic", 
                                metric_name="system.processCount", 
                                value=float(value)
                            )
                        )
                        result["metrics"]["processes"]["count"] = value
                    except Exception as e:
                        result["metrics"]["processes"]["count"] = f"Erro: {str(e)}"
                    
        # Processar detalhes dos discos com verificações de segurança
        disk_results = []
        if account_data.get("diskDetails") and isinstance(account_data.get("diskDetails"), dict):
            disk_results = account_data.get("diskDetails", {}).get("results", [])
            
        if disk_results:
            for disk in disk_results:
                if isinstance(disk, dict) and "deviceName" in disk and "diskUsedPercent" in disk:
                    try:
                        result["metrics"]["disks"].append({
                            "device": disk.get("deviceName"),
                            "usedPercent": disk.get("diskUsedPercent")
                        })
                    except Exception as e:
                        # Apenas continue se houver um erro com um disco específico
                        pass
                    
        # Processar top processos com verificações de segurança
        top_processes = []
        if account_data.get("topProcesses") and isinstance(account_data.get("topProcesses"), dict):
            top_processes = account_data.get("topProcesses", {}).get("results", [])
            
        if top_processes:
            for proc in top_processes:
                if isinstance(proc, dict) and "processDisplayName" in proc:
                    try:
                        memory_mb = 0
                        if "memoryResidentSizeBytes" in proc and proc.get("memoryResidentSizeBytes") is not None:
                            memory_mb = proc.get("memoryResidentSizeBytes", 0) / 1024 / 1024
                            
                        result["metrics"]["top_processes"].append({
                            "name": proc.get("processDisplayName"),
                            "cpu": proc.get("cpuPercent", 0),
                            "memory_mb": memory_mb
                        })
                    except Exception as e:
                        # Apenas continue se houver um erro com um processo específico
                        pass

        # Verificar se temos algum dado
        if (not result["metrics"]["system"] and 
            not result["metrics"]["network"] and 
            not result["metrics"]["disks"] and 
            not result["metrics"]["top_processes"]):
            # Se não temos dados, vamos tentar uma query mais simples
            simple_query = """
            {
              actor {
                account(id: 6593256) {
                  systemData: nrql(query: "SELECT latest(cpuPercent) as cpu FROM SystemSample WHERE hostname = '%s' SINCE 1 hour ago") {
                    results
                  }
                }
              }
            }
            """ % hostname
            
            simple_response = requests.post(
                "https://api.newrelic.com/graphql",
                headers=headers,
                json={"query": simple_query}
            )
            
            if simple_response.status_code == 200:
                simple_data = simple_response.json()
                result["debug_info"] = {
                    "simple_query_response": simple_data
                }
            
            result["message"] = "Não foi possível encontrar dados para o host especificado"

        return result

    except requests.exceptions.RequestException as e:
        return {
            "error": f"Erro na requisição ao New Relic: {str(e)}",
            "status_code": getattr(e.response, 'status_code', None),
            "response": getattr(e, 'response', {}).text if hasattr(e, 'response') else None
        }
    except Exception as e:
        return {
            "error": f"Erro inesperado: {str(e)}",
            "details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/test-newrelic-connection")
async def test_newrelic_connection():
    """
    Testa a conexão com a API do New Relic.
    Este endpoint verifica se as credenciais do New Relic estão configuradas corretamente.
    """
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }
        
        # Uma consulta GraphQL simples para testar a conexão
        graphql_query = """
        {
          actor {
            user {
              name
              email
            }
          }
        }
        """
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": graphql_query}
        )
        
        # Verificar resposta
        if response.status_code == 200:
            data = response.json()
            if "data" in data and "actor" in data["data"] and "user" in data["data"]["actor"]:
                user_info = data["data"]["actor"]["user"]
                return {
                    "status": "success",
                    "message": "Conexão com o New Relic estabelecida com sucesso",
                    "user": user_info,
                    "api_key_configured": bool(NEWRELIC_API_KEY) and len(NEWRELIC_API_KEY) > 10,
                    "account_id": NEWRELIC_ACCOUNT_ID
                }
            else:
                return {
                    "status": "warning",
                    "message": "Resposta recebida, mas formato inesperado",
                    "api_key_configured": bool(NEWRELIC_API_KEY),
                    "account_id": NEWRELIC_ACCOUNT_ID,
                    "response": data
                }
        else:
            return {
                "status": "error",
                "message": f"Erro na conexão com o New Relic: {response.status_code}",
                "status_code": response.status_code,
                "response": response.text,
                "api_key_configured": bool(NEWRELIC_API_KEY) and len(NEWRELIC_API_KEY) > 10,
                "account_id": NEWRELIC_ACCOUNT_ID
            }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro inesperado: {str(e)}",
            "api_key_configured": bool(NEWRELIC_API_KEY),
            "account_id": NEWRELIC_ACCOUNT_ID,
            "error_details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/test-newrelic-agent")
async def test_newrelic_agent():
    """
    Verifica o status do agente New Relic e metadados do host.
    Retorna informações detalhadas sobre o host monitorado pelo New Relic.
    """
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }
        
        # Consulta GraphQL para verificar o host
        graphql_query = """
        {
          actor {
            account(id: %s) {
              system: nrql(query: "SELECT entityName, fullHostname, operatingSystem, windowsVersion, kernelVersion, agentVersion, agentName FROM SystemSample WHERE entityGuid = '%s' LIMIT 1") {
                results
              }
            }
          }
        }
        """ % (NEWRELIC_ACCOUNT_ID, TUKSTATION_ENTITY_GUID)
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": graphql_query}
        )
        
        if response.status_code != 200:
            return {
                "status": "error",
                "message": f"Erro na consulta ao New Relic: {response.status_code}",
                "response": response.text
            }
            
        data = response.json()
        
        # Verificar se temos dados do host
        host_data = {}
        if ("data" in data and "actor" in data["data"] and 
            "account" in data["data"]["actor"] and "system" in data["data"]["actor"]["account"] and 
            "results" in data["data"]["actor"]["account"]["system"]):
            
            results = data["data"]["actor"]["account"]["system"]["results"]
            if results and len(results) > 0:
                host_data = results[0]
        
        if not host_data:
            # Se não encontrou pelo GUID, tenta buscar usando o nome do host
            backup_query = """
            {
              actor {
                account(id: %s) {
                  system: nrql(query: "SELECT entityName, fullHostname, operatingSystem, windowsVersion, kernelVersion, agentVersion, agentName FROM SystemSample LIMIT 1") {
                    results
                  }
                }
              }
            }
            """ % NEWRELIC_ACCOUNT_ID
            
            backup_response = requests.post(
                "https://api.newrelic.com/graphql",
                headers=headers,
                json={"query": backup_query}
            )
            
            if backup_response.status_code == 200:
                backup_data = backup_response.json()
                if ("data" in backup_data and "actor" in backup_data["data"] and 
                    "account" in backup_data["data"]["actor"] and "system" in backup_data["data"]["actor"]["account"] and 
                    "results" in backup_data["data"]["actor"]["account"]["system"]):
                    
                    results = backup_data["data"]["actor"]["account"]["system"]["results"]
                    if results and len(results) > 0:
                        host_data = results[0]
        
        # Verificar status da API e do agente
        if host_data:
            return {
                "status": "success",
                "message": "Agente New Relic encontrado e funcionando corretamente",
                "entity_guid": TUKSTATION_ENTITY_GUID,
                "account_id": NEWRELIC_ACCOUNT_ID,
                "api_key_configured": bool(NEWRELIC_API_KEY) and len(NEWRELIC_API_KEY) > 10,
                "agent_info": {
                    "name": host_data.get("agentName"),
                    "version": host_data.get("agentVersion")
                },
                "host_info": {
                    "name": host_data.get("entityName"),
                    "full_hostname": host_data.get("fullHostname"),
                    "operating_system": host_data.get("operatingSystem"),
                    "windows_version": host_data.get("windowsVersion"),
                    "kernel_version": host_data.get("kernelVersion")
                }
            }
        else:
            return {
                "status": "warning",
                "message": "Não foi possível encontrar dados do agente New Relic",
                "entity_guid": TUKSTATION_ENTITY_GUID,
                "account_id": NEWRELIC_ACCOUNT_ID,
                "api_key_configured": bool(NEWRELIC_API_KEY) and len(NEWRELIC_API_KEY) > 10,
                "troubleshooting": [
                    "Verifique se o agente New Relic está instalado corretamente",
                    "Confirme se o GUID da entidade está correto",
                    "Confirme se o ID da conta está correto",
                    "Verifique os logs do agente para possíveis erros"
                ]
            }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro inesperado: {str(e)}",
            "entity_guid": TUKSTATION_ENTITY_GUID,
            "account_id": NEWRELIC_ACCOUNT_ID,
            "api_key_configured": bool(NEWRELIC_API_KEY) and len(NEWRELIC_API_KEY) > 10,
            "error_details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/nr/cpu")
async def get_newrelic_cpu():
    """
    Retorna dados detalhados de CPU do host no New Relic.
    """
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }

        # Query para dados de CPU usando entityGuid fornecido
        query = """
        {
          actor {
            account(id: 6593256) {
              current: nrql(query: "SELECT latest(cpuPercent) AS 'current_cpu' FROM SystemSample WHERE entityGuid = '%s' SINCE 5 minutes ago") {
                results
              }
              history: nrql(query: "SELECT average(cpuPercent) AS 'cpu_used' FROM SystemSample WHERE entityGuid = '%s' TIMESERIES AUTO SINCE 30 minutes ago") {
                results
              }
              cores: nrql(query: "SELECT latest(coreCount) FROM SystemSample WHERE entityGuid = '%s' SINCE 5 minutes ago") {
                results
              }
              loadAverage: nrql(query: "SELECT average(loadAverageOneMinute) AS '1min', average(loadAverageFiveMinute) AS '5min', average(loadAverageFifteenMinute) AS '15min' FROM SystemSample WHERE entityGuid = '%s' TIMESERIES AUTO SINCE 30 minutes ago") {
                results
              }
            }
          }
        }
        """ % (TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID)
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": query}
        )
        
        if response.status_code != 200:
            return {
                "error": "Erro na requisição",
                "status_code": response.status_code,
                "response": response.text
            }
            
        data = response.json()
        
        # Processar os resultados
        result = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "entity_guid": TUKSTATION_ENTITY_GUID,
            "cpu": {
                "current": None,
                "history": [],
                "cores": None,
                "load_average": {
                    "history": []
                }
            }
        }
        
        # Extrair CPU atual
        if "data" in data and "actor" in data["data"]:
            account = data["data"]["actor"]["account"]
            
            # Valor atual de CPU
            if "current" in account and "results" in account["current"]:
                current_results = account["current"]["results"]
                if current_results and len(current_results) > 0:
                    result["cpu"]["current"] = current_results[0].get("current_cpu")
                    
                    # Salvar no banco de dados
                    if result["cpu"]["current"] is not None:
                        try:
                            await database.execute(
                                metrics.insert().values(
                                    platform="NewRelic", 
                                    metric_name="system.cpuPercent", 
                                    value=float(result["cpu"]["current"])
                                )
                            )
                        except Exception as e:
                            result["db_error"] = str(e)
            
            # Número de cores
            if "cores" in account and "results" in account["cores"]:
                cores_results = account["cores"]["results"]
                if cores_results and len(cores_results) > 0:
                    result["cpu"]["cores"] = cores_results[0].get("latest.coreCount")
            
            # Histórico de CPU
            if "history" in account and "results" in account["history"]:
                history_results = account["history"]["results"]
                result["cpu"]["history"] = [
                    {
                        "timestamp": point.get("beginTimeSeconds"),
                        "value": point.get("cpu_used")
                    }
                    for point in history_results
                    if "beginTimeSeconds" in point and "cpu_used" in point
                ]
                
                # Calcular estatísticas
                if result["cpu"]["history"]:
                    values = [point["value"] for point in result["cpu"]["history"] if point["value"] is not None]
                    if values:
                        result["cpu"]["stats"] = {
                            "avg": sum(values) / len(values),
                            "min": min(values),
                            "max": max(values)
                        }
            
            # Histórico de carga média
            if "loadAverage" in account and "results" in account["loadAverage"]:
                load_results = account["loadAverage"]["results"]
                for point in load_results:
                    if "beginTimeSeconds" in point:
                        result["cpu"]["load_average"]["history"].append({
                            "timestamp": point.get("beginTimeSeconds"),
                            "1min": point.get("1min"),
                            "5min": point.get("5min"),
                            "15min": point.get("15min")
                        })
        
        return result
    
    except Exception as e:
        return {
            "error": "Erro inesperado",
            "details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/nr/memory")
async def get_newrelic_memory():
    """
    Retorna dados detalhados de memória do host no New Relic.
    """
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }

        # Query para dados de memória usando entityGuid fornecido
        query = """
        {
          actor {
            account(id: 6593256) {
              current: nrql(query: "SELECT latest(memoryUsedPercent) AS 'current_memory', latest(memoryTotalBytes)/1024/1024/1024 AS 'total_gb', latest(memoryFreeBytes)/1024/1024/1024 AS 'free_gb' FROM SystemSample WHERE entityGuid = '%s' SINCE 5 minutes ago") {
                results
              }
              history: nrql(query: "SELECT average(memoryUsedPercent) AS 'memory_used' FROM SystemSample WHERE entityGuid = '%s' TIMESERIES AUTO SINCE 30 minutes ago") {
                results
              }
            }
          }
        }
        """ % (TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID)
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": query}
        )
        
        if response.status_code != 200:
            return {
                "error": "Erro na requisição",
                "status_code": response.status_code,
                "response": response.text
            }
            
        data = response.json()
        
        # Processar os resultados
        result = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "entity_guid": TUKSTATION_ENTITY_GUID,
            "memory": {
                "current_percent": None,
                "total_gb": None,
                "free_gb": None,
                "history": []
            }
        }
        
        # Extrair dados de memória
        if "data" in data and "actor" in data["data"]:
            account = data["data"]["actor"]["account"]
            
            # Valores atuais de memória
            if "current" in account and "results" in account["current"]:
                current_results = account["current"]["results"]
                if current_results and len(current_results) > 0:
                    result["memory"]["current_percent"] = current_results[0].get("current_memory")
                    result["memory"]["total_gb"] = current_results[0].get("total_gb")
                    result["memory"]["free_gb"] = current_results[0].get("free_gb")
                    
                    # Calcular memória usada em GB
                    if result["memory"]["total_gb"] is not None and result["memory"]["free_gb"] is not None:
                        result["memory"]["used_gb"] = result["memory"]["total_gb"] - result["memory"]["free_gb"]
                    
                    # Salvar no banco de dados
                    if result["memory"]["current_percent"] is not None:
                        try:
                            await database.execute(
                                metrics.insert().values(
                                    platform="NewRelic", 
                                    metric_name="system.memoryUsedPercent", 
                                    value=float(result["memory"]["current_percent"])
                                )
                            )
                        except Exception as e:
                            result["db_error"] = str(e)
            
            # Histórico de memória
            if "history" in account and "results" in account["history"]:
                history_results = account["history"]["results"]
                result["memory"]["history"] = [
                    {
                        "timestamp": point.get("beginTimeSeconds"),
                        "value": point.get("memory_used")
                    }
                    for point in history_results
                    if "beginTimeSeconds" in point and "memory_used" in point
                ]
                
                # Calcular estatísticas
                if result["memory"]["history"]:
                    values = [point["value"] for point in result["memory"]["history"] if point["value"] is not None]
                    if values:
                        result["memory"]["stats"] = {
                            "avg": sum(values) / len(values),
                            "min": min(values),
                            "max": max(values)
                        }
        
        return result
    
    except Exception as e:
        return {
            "error": "Erro inesperado",
            "details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/nr/disk")
async def get_newrelic_disk():
    """
    Retorna dados detalhados dos discos do host no New Relic.
    Inclui fallbacks para garantir que os discos sejam detectados mesmo quando o agente não reporta dados.
    """
    try:
        # Importar bibliotecas necessárias
        import os
        import platform
        import string
        import subprocess
        
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }

        # Query aprimorada para dados de disco usando entityGuid fornecido
        query = """
        {
          actor {
            account(id: %s) {
              current: nrql(query: "SELECT latest(diskUsedPercent) AS 'used_percent', mountPoint FROM StorageSample WHERE entityGuid = '%s' FACET device LIMIT MAX SINCE 5 minutes ago") {
                results
                facets
              }
              all_devices: nrql(query: "SELECT uniques(device), uniques(mountPoint) FROM StorageSample WHERE entityGuid = '%s' LIMIT MAX SINCE 30 minutes ago") {
                results
              }
              details: nrql(query: "SELECT latest(diskTotalBytes)/1024/1024/1024 AS 'total_gb', latest(diskFreeBytes)/1024/1024/1024 AS 'free_gb', latest(diskUsedBytes)/1024/1024/1024 AS 'used_gb', mountPoint FROM StorageSample WHERE entityGuid = '%s' FACET device LIMIT MAX SINCE 5 minutes ago") {
                results
                facets
              }
              system_disks: nrql(query: "SELECT latest(diskFreeBytes)/1024/1024/1024 as free_gb, latest(diskTotalBytes)/1024/1024/1024 as total_gb, mountPoint FROM SystemSample WHERE entityGuid = '%s' FACET mountPoint LIMIT MAX SINCE 5 minutes ago") {
                results
                facets
              }
              windows_disks: nrql(query: "FROM Metric SELECT latest(windows.storage.freeBytes)/1024/1024/1024 as free_gb, latest(windows.storage.usedBytes)/1024/1024/1024 as used_gb WHERE entity.guid = '%s' FACET mountPoint LIMIT MAX SINCE 5 minutes ago") {
                results
                facets
              }
              io: nrql(query: "SELECT latest(ioUtilizationPercent) AS 'io_percent', latest(readBytesPerSecond)/1024/1024 AS 'read_mbps', latest(writeBytesPerSecond)/1024/1024 AS 'write_mbps' FROM StorageSample WHERE entityGuid = '%s' FACET device LIMIT MAX SINCE 5 minutes ago") {
                results
                facets
              }
              history: nrql(query: "SELECT average(diskUsedPercent) AS 'disk_used' FROM StorageSample WHERE entityGuid = '%s' TIMESERIES AUTO SINCE 30 minutes ago") {
                results
              }
            }
          }
        }
        """ % (NEWRELIC_ACCOUNT_ID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, 
               TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID,
               TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID)
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": query}
        )
        
        if response.status_code != 200:
            return {
                "status": "error",
                "message": f"Erro na consulta ao New Relic: {response.status_code}",
                "response": response.text
            }
            
        data = response.json()
        
        # Processar os resultados
        result = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "entity_guid": TUKSTATION_ENTITY_GUID,
            "disks": [],
            "history": {
                "overall": [],
                "io": []
            },
            "status": "success"
        }
        
        # Flag para rastrear se conseguimos obter dados de disco
        has_disk_data = False
        
        # Extrair dados de disco
        if "data" in data and "actor" in data["data"] and "account" in data["data"]["actor"]:
            account = data["data"]["actor"]["account"]
            
            # Lista de unidades/dispositivos
            devices_set = set()
            mount_points = set()
            
            # Verificar lista de dispositivos disponíveis
            if "all_devices" in account and "results" in account["all_devices"]:
                device_results = account["all_devices"]["results"]
                if device_results and len(device_results) > 0:
                    if "uniques.device" in device_results[0]:
                        devices_list = device_results[0].get("uniques.device", [])
                        if isinstance(devices_list, list):
                            devices_set.update(devices_list)
                    
                    if "uniques.mountPoint" in device_results[0]:
                        mounts_list = device_results[0].get("uniques.mountPoint", [])
                        if isinstance(mounts_list, list):
                            mount_points.update(mounts_list)
            
            # Buscar dados de uso atual por dispositivo
            if "current" in account and "results" in account["current"] and "facets" in account["current"]:
                current_results = account["current"]["results"]
                facets = account["current"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(current_results):
                        device = facet[0]
                        devices_set.add(device)
                        
                        mount_point = current_results[i].get("mountPoint")
                        if mount_point:
                            mount_points.add(mount_point)
                        
                        disk_info = {
                            "device": device,
                            "mount_point": mount_point,
                            "used_percent": current_results[i].get("used_percent")
                        }
                        result["disks"].append(disk_info)
                        has_disk_data = True
                        
                        # Salvar no banco de dados
                        if disk_info["used_percent"] is not None:
                            try:
                                await database.execute(
                                    metrics.insert().values(
                                        platform="NewRelic", 
                                        metric_name=f"disk.{device}.usedPercent", 
                                        value=float(disk_info["used_percent"])
                                    )
                                )
                            except Exception as e:
                                pass  # Ignorar erros de BD para múltiplos discos
            
            # Adicionar detalhes por dispositivo (total, usado, livre)
            if "details" in account and "results" in account["details"] and "facets" in account["details"]:
                details_results = account["details"]["results"]
                facets = account["details"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(details_results):
                        device = facet[0]
                        devices_set.add(device)
                        
                        mount_point = details_results[i].get("mountPoint")
                        if mount_point:
                            mount_points.add(mount_point)
                        
                        # Encontrar o disco na lista ou criar um novo
                        disk_info = next((d for d in result["disks"] if d["device"] == device), None)
                        if disk_info is None:
                            disk_info = {
                                "device": device,
                                "mount_point": mount_point
                            }
                            result["disks"].append(disk_info)
                            has_disk_data = True
                        elif not disk_info.get("mount_point") and mount_point:
                            disk_info["mount_point"] = mount_point
                        
                        # Adicionar detalhes
                        disk_info["total_gb"] = details_results[i].get("total_gb")
                        disk_info["free_gb"] = details_results[i].get("free_gb") 
                        disk_info["used_gb"] = details_results[i].get("used_gb")
                        
                        # Calcular porcentagem se não estiver disponível
                        if disk_info.get("used_percent") is None and disk_info.get("total_gb") and disk_info.get("used_gb"):
                            disk_info["used_percent"] = (disk_info["used_gb"] / disk_info["total_gb"]) * 100
            
            # Adicionar dados de I/O
            if "io" in account and "results" in account["io"] and "facets" in account["io"]:
                io_results = account["io"]["results"]
                facets = account["io"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(io_results):
                        device = facet[0]
                        devices_set.add(device)
                        
                        # Encontrar o disco na lista ou criar um novo
                        disk_info = next((d for d in result["disks"] if d["device"] == device), None)
                        if disk_info is None:
                            disk_info = {"device": device}
                            result["disks"].append(disk_info)
                            has_disk_data = True
                        
                        # Adicionar dados de I/O
                        disk_info["io_percent"] = io_results[i].get("io_percent")
                        disk_info["read_mbps"] = io_results[i].get("read_mbps")
                        disk_info["write_mbps"] = io_results[i].get("write_mbps")
            
            # Fallback 1: Tentar dados do SystemSample se não tivermos StorageSample
            if not has_disk_data and "system_disks" in account and "results" in account["system_disks"] and "facets" in account["system_disks"]:
                system_results = account["system_disks"]["results"]
                facets = account["system_disks"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(system_results):
                        mount_point = facet[0]
                        mount_points.add(mount_point)
                        
                        # Extrair letra de unidade para Windows (C:, D:, etc.)
                        device = mount_point
                        if mount_point and ":" in mount_point:
                            device = mount_point.split(":")[0] + ":"
                        
                        devices_set.add(device)
                        
                        total_gb = system_results[i].get("total_gb")
                        free_gb = system_results[i].get("free_gb")
                        
                        disk_info = {
                            "device": device,
                            "mount_point": mount_point,
                            "total_gb": total_gb,
                            "free_gb": free_gb
                        }
                        
                        # Calcular espaço usado e porcentagem
                        if total_gb is not None and free_gb is not None:
                            used_gb = total_gb - free_gb
                            disk_info["used_gb"] = used_gb
                            disk_info["used_percent"] = (used_gb / total_gb) * 100 if total_gb > 0 else None
                        
                        result["disks"].append(disk_info)
                        has_disk_data = True
            
            # Fallback 2: Tentar métricas específicas do Windows se ainda não tivermos dados
            if not has_disk_data and "windows_disks" in account and "results" in account["windows_disks"] and "facets" in account["windows_disks"]:
                windows_results = account["windows_disks"]["results"]
                facets = account["windows_disks"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(windows_results):
                        mount_point = facet[0]
                        mount_points.add(mount_point)
                        
                        # Extrair letra de unidade para Windows (C:, D:, etc.)
                        device = mount_point
                        if mount_point and ":" in mount_point:
                            device = mount_point.split(":")[0] + ":"
                        
                        devices_set.add(device)
                        
                        free_gb = windows_results[i].get("free_gb")
                        used_gb = windows_results[i].get("used_gb")
                        
                        disk_info = {
                            "device": device,
                            "mount_point": mount_point,
                            "free_gb": free_gb,
                            "used_gb": used_gb
                        }
                        
                        # Calcular espaço total e porcentagem
                        if free_gb is not None and used_gb is not None:
                            total_gb = free_gb + used_gb
                            disk_info["total_gb"] = total_gb
                            disk_info["used_percent"] = (used_gb / total_gb) * 100 if total_gb > 0 else None
                        
                        result["disks"].append(disk_info)
                        has_disk_data = True
            
            # Histórico de uso geral de disco
            if "history" in account and "results" in account["history"]:
                history_results = account["history"]["results"]
                result["history"]["overall"] = [
                    {
                        "timestamp": point.get("beginTimeSeconds"),
                        "value": point.get("disk_used")
                    }
                    for point in history_results
                    if "beginTimeSeconds" in point and "disk_used" in point
                ]
            
            # Adicionar dispositivos e pontos de montagem detectados
            if not has_disk_data and devices_set:
                for device in devices_set:
                    result["disks"].append({
                        "device": device,
                        "status": "dispositivo detectado, mas sem dados completos"
                    })
                    has_disk_data = True
            
            if not has_disk_data and mount_points:
                for mount in mount_points:
                    # Extrair letra de unidade para Windows (C:, D:, etc.)
                    device = mount
                    if mount and ":" in mount:
                        device = mount.split(":")[0] + ":"
                    
                    result["disks"].append({
                        "device": device,
                        "mount_point": mount,
                        "status": "ponto de montagem detectado, mas sem dados completos"
                    })
                    has_disk_data = True
        
        # Fallback 3: Se ainda não temos dados, usar uma abordagem direta do sistema operacional
        if not has_disk_data:
            # Para Windows
            if platform.system() == "Windows":
                try:
                    # Usar letra de unidades para Windows
                    drives = []
                    for letter in string.ascii_uppercase:
                        drive_path = f"{letter}:"
                        try:
                            if os.path.exists(f"{drive_path}\\"):
                                total, used, free = __import__("shutil").disk_usage(drive_path)
                                drives.append({
                                    "device": drive_path,
                                    "mount_point": f"{drive_path}\\",
                                    "total_gb": total / (1024**3),
                                    "free_gb": free / (1024**3),
                                    "used_gb": used / (1024**3),
                                    "used_percent": (used / total) * 100 if total > 0 else None,
                                    "source": "os_module"
                                })
                        except:
                            pass
                    
                    # Se isso não funcionar, tentar wmic
                    if not drives:
                        try:
                            output = subprocess.check_output("wmic logicaldisk get deviceid, freespace, size", shell=True).decode()
                            lines = output.strip().split('\n')[1:]
                            for line in lines:
                                parts = line.split()
                                if len(parts) >= 3:
                                    try:
                                        device = parts[0]
                                        free_bytes = int(parts[1])
                                        total_bytes = int(parts[2])
                                        used_bytes = total_bytes - free_bytes
                                        
                                        drives.append({
                                            "device": device,
                                            "mount_point": f"{device}\\",
                                            "total_gb": total_bytes / (1024**3),
                                            "free_gb": free_bytes / (1024**3),
                                            "used_gb": used_bytes / (1024**3),
                                            "used_percent": (used_bytes / total_bytes) * 100 if total_bytes > 0 else None,
                                            "source": "wmic"
                                        })
                                    except:
                                        pass
                        except:
                            pass
                    
                    if drives:
                        result["disks"] = drives
                        has_disk_data = True
                        result["message"] = "Dados obtidos diretamente do sistema operacional Windows"
                except Exception as e:
                    result["windows_error"] = str(e)
            
            # Para Linux
            elif platform.system() == "Linux":
                try:
                    # Usar df para verificar partições
                    output = subprocess.check_output("df -h", shell=True).decode()
                    lines = output.strip().split('\n')[1:]
                    drives = []
                    
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 6:
                            try:
                                device = parts[0]
                                mount_point = parts[5]
                                
                                # Ignorar sistemas de arquivos virtuais
                                if device.startswith("/dev/") or device.startswith("/dev/mapper/"):
                                    # Usar shutil para dados precisos
                                    try:
                                        total, used, free = __import__("shutil").disk_usage(mount_point)
                                        drives.append({
                                            "device": device,
                                            "mount_point": mount_point,
                                            "total_gb": total / (1024**3),
                                            "free_gb": free / (1024**3),
                                            "used_gb": used / (1024**3),
                                            "used_percent": (used / total) * 100 if total > 0 else None,
                                            "source": "os_module"
                                        })
                                    except:
                                        # Fallback para parse de df se shutil falhar
                                        size = parts[1]
                                        used = parts[2]
                                        avail = parts[3]
                                        used_percent = parts[4].replace("%", "")
                                        
                                        # Converter para bytes removendo sufixos como G, M, T
                                        def parse_size(size_str):
                                            if not size_str:
                                                return None
                                            multipliers = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
                                            size_str = size_str.upper()
                                            if size_str[-1] in multipliers:
                                                return float(size_str[:-1]) * multipliers[size_str[-1]] / (1024**3)  # Convert to GB
                                            return float(size_str) / (1024**3)
                                        
                                        drives.append({
                                            "device": device,
                                            "mount_point": mount_point,
                                            "total_gb": parse_size(size),
                                            "free_gb": parse_size(avail),
                                            "used_gb": parse_size(used),
                                            "used_percent": float(used_percent) if used_percent else None,
                                            "source": "df_command"
                                        })
                            except:
                                pass
                    
                    if drives:
                        result["disks"] = drives
                        has_disk_data = True
                        result["message"] = "Dados obtidos diretamente do sistema operacional Linux"
                except Exception as e:
                    result["linux_error"] = str(e)
        
        # Incluir estatísticas agregadas se temos dados de disco
        if result["disks"]:
            try:
                total_space_gb = 0
                free_space_gb = 0
                used_space_gb = 0
                
                for disk in result["disks"]:
                    if disk.get("total_gb") is not None:
                        total_space_gb += disk["total_gb"]
                    
                    if disk.get("free_gb") is not None:
                        free_space_gb += disk["free_gb"]
                    
                    if disk.get("used_gb") is not None:
                        used_space_gb += disk["used_gb"]
                
                if total_space_gb > 0:
                    result["summary"] = {
                        "total_storage_gb": total_space_gb,
                        "free_storage_gb": free_space_gb,
                        "used_storage_gb": used_space_gb,
                        "overall_used_percent": (used_space_gb / total_space_gb) * 100 if total_space_gb > 0 else None,
                        "disk_count": len(result["disks"])
                    }
            except Exception as e:
                result["summary_error"] = str(e)
        
        if not has_disk_data:
            result["status"] = "warning"
            result["message"] = "Não foi possível obter dados de disco via New Relic ou sistema operacional"
        
        return result
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro inesperado: {str(e)}",
            "error_details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/nr/network")
async def get_newrelic_network():
    """
    Retorna dados detalhados de rede do host no New Relic.
    """
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }

        # Query para dados de rede usando entityGuid fornecido
        query = """
        {
          actor {
            account(id: %s) {
              current: nrql(query: "SELECT latest(transmitBytesPerSecond) AS 'tx_bps', latest(receiveBytesPerSecond) AS 'rx_bps' FROM NetworkSample WHERE entityGuid = '%s' FACET interfaceName SINCE 5 minutes ago") {
                results
                facets
              }
              history: nrql(query: "SELECT average(transmitBytesPerSecond) AS 'tx_bps', average(receiveBytesPerSecond) AS 'rx_bps' FROM NetworkSample WHERE entityGuid = '%s' TIMESERIES AUTO SINCE 30 minutes ago") {
                results
              }
              details: nrql(query: "SELECT latest(transmitDroppedPacketsPerSecond) AS 'tx_drops', latest(receiveDroppedPacketsPerSecond) AS 'rx_drops', latest(transmitErrorsPerSecond) AS 'tx_errors', latest(receiveErrorsPerSecond) AS 'rx_errors' FROM NetworkSample WHERE entityGuid = '%s' FACET interfaceName SINCE 5 minutes ago") {
                results
                facets
              }
              system_overview: nrql(query: "SELECT sum(transmitBytesPerSecond)/1024/1024 as 'tx_mbps', sum(receiveBytesPerSecond)/1024/1024 as 'rx_mbps' FROM NetworkSample WHERE entityGuid = '%s' SINCE 5 minutes ago") {
                results
              }
            }
          }
        }
        """ % (NEWRELIC_ACCOUNT_ID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID)
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": query}
        )
        
        if response.status_code != 200:
            return {
                "status": "error",
                "message": f"Erro na requisição: {response.status_code}",
                "response": response.text
            }
            
        data = response.json()
        
        # Processar os resultados
        result = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "entity_guid": TUKSTATION_ENTITY_GUID,
            "interfaces": [],
            "history": [],
            "status": "success"
        }
        
        # Extrair dados de rede
        if "data" in data and "actor" in data["data"] and "account" in data["data"]["actor"]:
            account = data["data"]["actor"]["account"]
            
            # Verificar se temos dados de sistema gerais
            if "system_overview" in account and "results" in account["system_overview"]:
                overview_results = account["system_overview"]["results"]
                if overview_results and len(overview_results) > 0:
                    result["network_overview"] = {
                        "total_tx_mbps": overview_results[0].get("tx_mbps"),
                        "total_rx_mbps": overview_results[0].get("rx_mbps")
                    }
            
            # Tráfego atual por interface
            if "current" in account and "results" in account["current"] and "facets" in account["current"]:
                current_results = account["current"]["results"]
                facets = account["current"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(current_results):
                        interface_name = facet[0]
                        interface_info = {
                            "name": interface_name,
                            "tx_bps": current_results[i].get("tx_bps"),
                            "rx_bps": current_results[i].get("rx_bps")
                        }
                        
                        # Calcular taxa em MB/s para facilitar leitura
                        if interface_info["tx_bps"] is not None:
                            interface_info["tx_mbps"] = interface_info["tx_bps"] / 1024 / 1024
                        if interface_info["rx_bps"] is not None:
                            interface_info["rx_mbps"] = interface_info["rx_bps"] / 1024 / 1024
                        
                        result["interfaces"].append(interface_info)
                        
                        # Salvar no banco de dados
                        if interface_info["tx_bps"] is not None:
                            try:
                                await database.execute(
                                    metrics.insert().values(
                                        platform="NewRelic", 
                                        metric_name=f"network.{interface_name}.tx", 
                                        value=float(interface_info["tx_bps"])
                                    )
                                )
                            except Exception as e:
                                pass
                        
                        if interface_info["rx_bps"] is not None:
                            try:
                                await database.execute(
                                    metrics.insert().values(
                                        platform="NewRelic", 
                                        metric_name=f"network.{interface_name}.rx", 
                                        value=float(interface_info["rx_bps"])
                                    )
                                )
                            except Exception as e:
                                pass
            
            # Detalhes adicionais por interface (erros, pacotes)
            if "details" in account and "results" in account["details"] and "facets" in account["details"]:
                details_results = account["details"]["results"]
                facets = account["details"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(details_results):
                        interface_name = facet[0]
                        
                        # Encontrar a interface na lista ou criar uma nova
                        interface_info = next((intf for intf in result["interfaces"] if intf["name"] == interface_name), None)
                        if interface_info is None:
                            interface_info = {"name": interface_name}
                            result["interfaces"].append(interface_info)
                        
                        # Adicionar detalhes
                        interface_info["tx_drops"] = details_results[i].get("tx_drops")
                        interface_info["rx_drops"] = details_results[i].get("rx_drops")
                        interface_info["tx_errors"] = details_results[i].get("tx_errors")
                        interface_info["rx_errors"] = details_results[i].get("rx_errors")
            
            # Histórico de tráfego
            if "history" in account and "results" in account["history"]:
                history_results = account["history"]["results"]
                result["history"] = [
                    {
                        "timestamp": point.get("beginTimeSeconds"),
                        "tx_bps": point.get("tx_bps"),
                        "rx_bps": point.get("rx_bps")
                    }
                    for point in history_results
                    if "beginTimeSeconds" in point
                ]
                
                # Adicionar versão em MB/s para facilitar leitura
                for point in result["history"]:
                    if point["tx_bps"] is not None:
                        point["tx_mbps"] = point["tx_bps"] / 1024 / 1024
                    if point["rx_bps"] is not None:
                        point["rx_mbps"] = point["rx_bps"] / 1024 / 1024
        
        # Se não temos interfaces, adicione uma mensagem explicativa
        if not result["interfaces"]:
            result["status"] = "warning"
            result["message"] = "Nenhuma interface de rede encontrada. O agente New Relic pode não estar configurado para coletar métricas de rede."
            
            # Adicionar diagnóstico manual para Windows
            import platform
            if platform.system() == "Windows":
                try:
                    import subprocess

                    # Tentar obter informações básicas de rede do sistema
                    network_info = subprocess.check_output("ipconfig", shell=True).decode('utf-8', errors='ignore')
                    if network_info:
                        result["system_network_info"] = {
                            "message": "Informações de rede obtidas diretamente do sistema",
                            "details": "Dados disponíveis, mas não processados em formato JSON"
                        }
                except:
                    pass
        
        return result
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro inesperado: {str(e)}",
            "error_details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/nr/processes")
async def get_newrelic_processes():
    """
    Retorna informações sobre os processos em execução no host.
    """
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }

        # Query para dados de processos usando entityGuid fornecido
        query = """
        {
          actor {
            account(id: 6593256) {
              top_cpu: nrql(query: "SELECT latest(cpuPercent) AS 'cpu', latest(threadCount) AS 'threads', latest(memoryResidentSizeBytes)/1024/1024 AS 'memory_mb' FROM ProcessSample WHERE entityGuid = '%s' FACET processId, processDisplayName ORDER BY latest(cpuPercent) DESC LIMIT 20 SINCE 5 minutes ago") {
                results
                facets
              }
              top_memory: nrql(query: "SELECT latest(memoryResidentSizeBytes)/1024/1024 AS 'memory_mb', latest(cpuPercent) AS 'cpu', latest(threadCount) AS 'threads' FROM ProcessSample WHERE entityGuid = '%s' FACET processId, processDisplayName ORDER BY latest(memoryResidentSizeBytes) DESC LIMIT 20 SINCE 5 minutes ago") {
                results
                facets
              }
              summary: nrql(query: "SELECT uniqueCount(processId) AS 'process_count', uniqueCount(processDisplayName) AS 'unique_processes' FROM ProcessSample WHERE entityGuid = '%s' SINCE 5 minutes ago") {
                results
              }
            }
          }
        }
        """ % (TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID)
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": query}
        )
        
        if response.status_code != 200:
            return {
                "error": "Erro na requisição",
                "status_code": response.status_code,
                "response": response.text
            }
            
        data = response.json()
        
        # Processar os resultados
        result = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "entity_guid": TUKSTATION_ENTITY_GUID,
            "summary": {
                "total_processes": None,
                "unique_processes": None
            },
            "top_by_cpu": [],
            "top_by_memory": []
        }
        
        # Extrair dados de processos
        if "data" in data and "actor" in data["data"]:
            account = data["data"]["actor"]["account"]
            
            # Resumo de processos
            if "summary" in account and "results" in account["summary"]:
                summary_results = account["summary"]["results"]
                if summary_results and len(summary_results) > 0:
                    result["summary"]["total_processes"] = summary_results[0].get("process_count")
                    result["summary"]["unique_processes"] = summary_results[0].get("unique_processes")
            
            # Top processos por CPU
            if "top_cpu" in account and "results" in account["top_cpu"] and "facets" in account["top_cpu"]:
                cpu_results = account["top_cpu"]["results"]
                facets = account["top_cpu"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(cpu_results):
                        process_id = facet[0]
                        process_name = facet[1]
                        
                        process_info = {
                            "id": process_id,
                            "name": process_name,
                            "cpu_percent": cpu_results[i].get("cpu"),
                            "threads": cpu_results[i].get("threads"),
                            "memory_mb": cpu_results[i].get("memory_mb")
                        }
                        
                        result["top_by_cpu"].append(process_info)
            
            # Top processos por memória
            if "top_memory" in account and "results" in account["top_memory"] and "facets" in account["top_memory"]:
                memory_results = account["top_memory"]["results"]
                facets = account["top_memory"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(memory_results):
                        process_id = facet[0]
                        process_name = facet[1]
                        
                        process_info = {
                            "id": process_id,
                            "name": process_name,
                            "memory_mb": memory_results[i].get("memory_mb"),
                            "cpu_percent": memory_results[i].get("cpu"),
                            "threads": memory_results[i].get("threads")
                        }
                        
                        result["top_by_memory"].append(process_info)
            
            # Salvar dados resumidos no banco
            try:
                if result["summary"]["total_processes"] is not None:
                    await database.execute(
                        metrics.insert().values(
                            platform="NewRelic", 
                            metric_name="system.processCount", 
                            value=float(result["summary"]["total_processes"])
                        )
                    )
                
                # Salvar top processo por CPU
                if result["top_by_cpu"] and len(result["top_by_cpu"]) > 0 and result["top_by_cpu"][0]["cpu_percent"] is not None:
                    await database.execute(
                        metrics.insert().values(
                            platform="NewRelic", 
                            metric_name="process.topCpu", 
                            value=float(result["top_by_cpu"][0]["cpu_percent"])
                        )
                    )
            except Exception as e:
                result["db_error"] = str(e)
        
        return result
    
    except Exception as e:
        return {
            "error": "Erro inesperado",
            "details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/nr/dashboard")
async def get_newrelic_dashboard():
    """
    Retorna um dashboard completo com todas as métricas principais em uma única chamada.
    """
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }

        # Query completa para dashboard usando entityGuid fornecido
        query = """
        {
          actor {
            account(id: 6593256) {
              host: nrql(query: "SELECT latest(timestamp) as last_report, entityName, fullHostname, operatingSystem, windowsVersion FROM SystemSample WHERE entityGuid = '%s' LIMIT 1") {
                results
              }
              cpu: nrql(query: "SELECT latest(cpuPercent) as cpu, latest(coreCount) as cores FROM SystemSample WHERE entityGuid = '%s' SINCE 5 minutes ago") {
                results
              }
              memory: nrql(query: "SELECT latest(memoryUsedPercent) as memory, latest(memoryTotalBytes)/1024/1024/1024 as total_gb FROM SystemSample WHERE entityGuid = '%s' SINCE 5 minutes ago") {
                results
              }
              disk: nrql(query: "SELECT latest(diskUsedPercent) as used_percent FROM StorageSample WHERE entityGuid = '%s' FACET device LIMIT MAX SINCE 5 minutes ago") {
                results
                facets
              }
              network: nrql(query: "SELECT latest(transmitBytesPerSecond)/1024/1024 as tx_mbps, latest(receiveBytesPerSecond)/1024/1024 as rx_mbps FROM NetworkSample WHERE entityGuid = '%s' SINCE 5 minutes ago") {
                results
              }
              processes: nrql(query: "SELECT uniqueCount(processId) as count FROM ProcessSample WHERE entityGuid = '%s' SINCE 5 minutes ago") {
                results
              }
              top_processes: nrql(query: "SELECT latest(cpuPercent) as cpu, latest(memoryResidentSizeBytes)/1024/1024 as memory_mb FROM ProcessSample WHERE entityGuid = '%s' FACET processDisplayName ORDER BY latest(cpuPercent) DESC LIMIT 5 SINCE 5 minutes ago") {
                results
                facets
              }
            }
          }
        }
        """ % (TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, 
               TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID)
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": query}
        )
        
        if response.status_code != 200:
            return {
                "error": "Erro na requisição",
                "status_code": response.status_code,
                "response": response.text
            }
            
        data = response.json()
        
        # Processar os resultados
        result = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "entity_guid": TUKSTATION_ENTITY_GUID,
            "host_info": {},
            "metrics": {
                "cpu": {},
                "memory": {},
                "disk": [],
                "network": {},
                "processes": {
                    "count": None,
                    "top": []
                }
            }
        }
        
        # Extrair todos os dados
        if "data" in data and "actor" in data["data"]:
            account = data["data"]["actor"]["account"]
            
            # Informações do host
            if "host" in account and "results" in account["host"]:
                host_results = account["host"]["results"]
                if host_results and len(host_results) > 0:
                    result["host_info"] = {
                        "name": host_results[0].get("entityName"),
                        "full_hostname": host_results[0].get("fullHostname"),
                        "os": host_results[0].get("operatingSystem"),
                        "windows_version": host_results[0].get("windowsVersion"),
                        "last_report": host_results[0].get("last_report")
                    }
            
            # CPU
            if "cpu" in account and "results" in account["cpu"]:
                cpu_results = account["cpu"]["results"]
                if cpu_results and len(cpu_results) > 0:
                    result["metrics"]["cpu"] = {
                        "percent": cpu_results[0].get("cpu"),
                        "cores": cpu_results[0].get("cores")
                    }
            
            # Memória
            if "memory" in account and "results" in account["memory"]:
                memory_results = account["memory"]["results"]
                if memory_results and len(memory_results) > 0:
                    result["metrics"]["memory"] = {
                        "percent": memory_results[0].get("memory"),
                        "total_gb": memory_results[0].get("total_gb")
                    }
                    
                    # Calcular usado/livre em GB
                    if result["metrics"]["memory"]["total_gb"] is not None and result["metrics"]["memory"]["percent"] is not None:
                        total_gb = result["metrics"]["memory"]["total_gb"]
                        percent = result["metrics"]["memory"]["percent"] / 100
                        result["metrics"]["memory"]["used_gb"] = total_gb * percent
                        result["metrics"]["memory"]["free_gb"] = total_gb - (total_gb * percent)
            
            # Disco
            if "disk" in account and "results" in account["disk"] and "facets" in account["disk"]:
                disk_results = account["disk"]["results"]
                facets = account["disk"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(disk_results):
                        result["metrics"]["disk"].append({
                            "device": facet[0],
                            "used_percent": disk_results[i].get("used_percent")
                        })
            
            # Rede
            if "network" in account and "results" in account["network"]:
                network_results = account["network"]["results"]
                if network_results and len(network_results) > 0:
                    result["metrics"]["network"] = {
                        "tx_mbps": network_results[0].get("tx_mbps"),
                        "rx_mbps": network_results[0].get("rx_mbps")
                    }
            
            # Processos
            if "processes" in account and "results" in account["processes"]:
                process_results = account["processes"]["results"]
                if process_results and len(process_results) > 0:
                    result["metrics"]["processes"]["count"] = process_results[0].get("count")
            
            # Top processos
            if "top_processes" in account and "results" in account["top_processes"] and "facets" in account["top_processes"]:
                top_results = account["top_processes"]["results"]
                facets = account["top_processes"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(top_results):
                        result["metrics"]["processes"]["top"].append({
                            "name": facet[0],
                            "cpu_percent": top_results[i].get("cpu"),
                            "memory_mb": top_results[i].get("memory_mb")
                        })
            
            # Salvar métricas principais no banco de dados
            try:
                # CPU
                if result["metrics"]["cpu"].get("percent") is not None:
                    await database.execute(
                        metrics.insert().values(
                            platform="NewRelic", 
                            metric_name="system.cpuPercent", 
                            value=float(result["metrics"]["cpu"]["percent"])
                        )
                    )
                
                # Memória
                if result["metrics"]["memory"].get("percent") is not None:
                    await database.execute(
                        metrics.insert().values(
                            platform="NewRelic", 
                            metric_name="system.memoryUsedPercent", 
                            value=float(result["metrics"]["memory"]["percent"])
                        )
                    )
                
                # Processos
                if result["metrics"]["processes"].get("count") is not None:
                    await database.execute(
                        metrics.insert().values(
                            platform="NewRelic", 
                            metric_name="system.processCount", 
                            value=float(result["metrics"]["processes"]["count"])
                        )
                    )
                
                # Rede
                if result["metrics"]["network"].get("tx_mbps") is not None:
                    await database.execute(
                        metrics.insert().values(
                            platform="NewRelic", 
                            metric_name="network.transmitMbps", 
                            value=float(result["metrics"]["network"]["tx_mbps"])
                        )
                    )
                
                if result["metrics"]["network"].get("rx_mbps") is not None:
                    await database.execute(
                        metrics.insert().values(
                            platform="NewRelic", 
                            metric_name="network.receiveMbps", 
                            value=float(result["metrics"]["network"]["rx_mbps"])
                        )
                    )
            except Exception as e:
                result["db_error"] = str(e)
        
        return result
    
    except Exception as e:
        return {
            "error": "Erro inesperado",
            "details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/nr/complete")
async def get_newrelic_complete(hours: int = 3):
    """
    Retorna um dashboard completo com todas as métricas atuais e históricas em uma única chamada.
    Este é o endpoint mais completo que fornece uma visão detalhada do sistema.
    
    Parâmetros:
    - hours: Número de horas para buscar dados históricos (padrão: 3)
    """
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }

        # Query para dados atuais
        current_query = """
        {
          actor {
            account(id: 6593256) {
              host: nrql(query: "SELECT latest(timestamp) as last_report, entityName, fullHostname, operatingSystem, windowsVersion, kernelVersion FROM SystemSample WHERE entityGuid = '%s' LIMIT 1") {
                results
              }
              system: nrql(query: "SELECT latest(cpuPercent) as cpu, latest(memoryUsedPercent) as memory, latest(coreCount) as cores, latest(memoryTotalBytes)/1024/1024/1024 as memory_total_gb, latest(uptime)/60/60/24 as uptime_days FROM SystemSample WHERE entityGuid = '%s' SINCE 5 minutes ago") {
                results
              }
              disk: nrql(query: "SELECT latest(diskUsedPercent) as used_percent, latest(diskTotalBytes)/1024/1024/1024 as total_gb, deviceName FROM StorageSample WHERE entityGuid = '%s' FACET device LIMIT MAX SINCE 5 minutes ago") {
                results
                facets
              }
              network: nrql(query: "SELECT latest(transmitBytesPerSecond)/1024/1024 as tx_mbps, latest(receiveBytesPerSecond)/1024/1024 as rx_mbps, interfaceName FROM NetworkSample WHERE entityGuid = '%s' FACET interfaceName SINCE 5 minutes ago") {
                results
                facets
              }
              processes: nrql(query: "SELECT uniqueCount(processId) as count, uniqueCount(processDisplayName) as unique_count FROM ProcessSample WHERE entityGuid = '%s' SINCE 5 minutes ago") {
                results
              }
              top_cpu: nrql(query: "SELECT latest(cpuPercent) as cpu, latest(memoryResidentSizeBytes)/1024/1024 as memory_mb FROM ProcessSample WHERE entityGuid = '%s' FACET processDisplayName ORDER BY latest(cpuPercent) DESC LIMIT 10 SINCE 5 minutes ago") {
                results
                facets
              }
              top_memory: nrql(query: "SELECT latest(memoryResidentSizeBytes)/1024/1024 as memory_mb, latest(cpuPercent) as cpu FROM ProcessSample WHERE entityGuid = '%s' FACET processDisplayName ORDER BY latest(memoryResidentSizeBytes) DESC LIMIT 10 SINCE 5 minutes ago") {
                results
                facets
              }
            }
          }
        }
        """ % (TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, 
               TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID)
        
        # Query para dados históricos
        historical_query = """
        {
          actor {
            account(id: 6593256) {
              cpu_history: nrql(query: "SELECT average(cpuPercent) as cpu FROM SystemSample WHERE entityGuid = '%s' TIMESERIES AUTO SINCE %d hours ago") {
                results
              }
              memory_history: nrql(query: "SELECT average(memoryUsedPercent) as memory FROM SystemSample WHERE entityGuid = '%s' TIMESERIES AUTO SINCE %d hours ago") {
                results
              }
              disk_history: nrql(query: "SELECT average(diskUsedPercent) as disk FROM StorageSample WHERE entityGuid = '%s' TIMESERIES AUTO SINCE %d hours ago") {
                results
              }
              network_history: nrql(query: "SELECT average(transmitBytesPerSecond)/1024/1024 as tx_mbps, average(receiveBytesPerSecond)/1024/1024 as rx_mbps FROM NetworkSample WHERE entityGuid = '%s' TIMESERIES AUTO SINCE %d hours ago") {
                results
              }
              load_history: nrql(query: "SELECT average(loadAverageOneMinute) as load_1min FROM SystemSample WHERE entityGuid = '%s' TIMESERIES AUTO SINCE %d hours ago") {
                results
              }
            }
          }
        }
        """ % (TUKSTATION_ENTITY_GUID, hours, TUKSTATION_ENTITY_GUID, hours, 
               TUKSTATION_ENTITY_GUID, hours, TUKSTATION_ENTITY_GUID, hours,
               TUKSTATION_ENTITY_GUID, hours)
        
        # Executar as queries em paralelo
        current_response_future = __import__("asyncio").create_task(
            __import__("asyncio").to_thread(
                requests.post,
                "https://api.newrelic.com/graphql",
                headers=headers,
                json={"query": current_query}
            )
        )
        
        historical_response_future = __import__("asyncio").create_task(
            __import__("asyncio").to_thread(
                requests.post,
                "https://api.newrelic.com/graphql",
                headers=headers,
                json={"query": historical_query}
            )
        )
        
        # Esperar as duas respostas
        current_response, historical_response = await __import__("asyncio").gather(
            current_response_future,
            historical_response_future
        )
        
        # Verificar respostas
        if current_response.status_code != 200 or historical_response.status_code != 200:
            return {
                "error": "Erro em uma ou mais requisições",
                "current_status": current_response.status_code,
                "historical_status": historical_response.status_code
            }
            
        current_data = current_response.json()
        historical_data = historical_response.json()
        
        # Criar estrutura de resultado
        result = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "entity_guid": TUKSTATION_ENTITY_GUID,
            "host_info": {},
            "current": {
                "system": {},
                "disk": [],
                "network": [],
                "processes": {
                    "count": None,
                    "unique_count": None,
                    "top_by_cpu": [],
                    "top_by_memory": []
                }
            },
            "historical": {
                "cpu": [],
                "memory": [],
                "disk": [],
                "network": [],
                "load": []
            }
        }
        
        # Processar dados atuais
        if "data" in current_data and "actor" in current_data["data"]:
            account = current_data["data"]["actor"]["account"]
            
            # Informações do host
            if "host" in account and "results" in account["host"]:
                host_results = account["host"]["results"]
                if host_results and len(host_results) > 0:
                    result["host_info"] = {
                        "name": host_results[0].get("entityName"),
                        "full_hostname": host_results[0].get("fullHostname"),
                        "os": host_results[0].get("operatingSystem"),
                        "windows_version": host_results[0].get("windowsVersion"),
                        "kernel_version": host_results[0].get("kernelVersion"),
                        "last_report": host_results[0].get("last_report")
                    }
            
            # Sistema
            if "system" in account and "results" in account["system"]:
                system_results = account["system"]["results"]
                if system_results and len(system_results) > 0:
                    result["current"]["system"] = {
                        "cpu_percent": system_results[0].get("cpu"),
                        "memory_percent": system_results[0].get("memory"),
                        "cores": system_results[0].get("cores"),
                        "memory_total_gb": system_results[0].get("memory_total_gb"),
                        "uptime_days": system_results[0].get("uptime_days")
                    }
                    
                    # Calcular memória utilizada/livre
                    if result["current"]["system"].get("memory_total_gb") is not None and result["current"]["system"].get("memory_percent") is not None:
                        total_gb = result["current"]["system"]["memory_total_gb"]
                        percent = result["current"]["system"]["memory_percent"] / 100
                        result["current"]["system"]["memory_used_gb"] = total_gb * percent
                        result["current"]["system"]["memory_free_gb"] = total_gb - (total_gb * percent)
            
            # Disco
            if "disk" in account and "results" in account["disk"] and "facets" in account["disk"]:
                disk_results = account["disk"]["results"]
                facets = account["disk"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(disk_results):
                        disk_info = {
                            "device": facet[0],
                            "used_percent": disk_results[i].get("used_percent"),
                            "total_gb": disk_results[i].get("total_gb")
                        }
                        
                        # Calcular espaço utilizado/livre
                        if disk_info.get("total_gb") is not None and disk_info.get("used_percent") is not None:
                            total_gb = disk_info["total_gb"]
                            percent = disk_info["used_percent"] / 100
                            disk_info["used_gb"] = total_gb * percent
                            disk_info["free_gb"] = total_gb - (total_gb * percent)
                        
                        result["current"]["disk"].append(disk_info)
            
            # Rede
            if "network" in account and "results" in account["network"] and "facets" in account["network"]:
                network_results = account["network"]["results"]
                facets = account["network"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(network_results):
                        result["current"]["network"].append({
                            "interface": facet[0],
                            "tx_mbps": network_results[i].get("tx_mbps"),
                            "rx_mbps": network_results[i].get("rx_mbps")
                        })
            
            # Processos
            if "processes" in account and "results" in account["processes"]:
                process_results = account["processes"]["results"]
                if process_results and len(process_results) > 0:
                    result["current"]["processes"]["count"] = process_results[0].get("count")
                    result["current"]["processes"]["unique_count"] = process_results[0].get("unique_count")
            
            # Top processos por CPU
            if "top_cpu" in account and "results" in account["top_cpu"] and "facets" in account["top_cpu"]:
                top_results = account["top_cpu"]["results"]
                facets = account["top_cpu"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(top_results):
                        result["current"]["processes"]["top_by_cpu"].append({
                            "name": facet[0],
                            "cpu_percent": top_results[i].get("cpu"),
                            "memory_mb": top_results[i].get("memory_mb")
                        })
            
            # Top processos por memória
            if "top_memory" in account and "results" in account["top_memory"] and "facets" in account["top_memory"]:
                top_results = account["top_memory"]["results"]
                facets = account["top_memory"]["facets"]
                
                for i, facet in enumerate(facets):
                    if i < len(top_results):
                        result["current"]["processes"]["top_by_memory"].append({
                            "name": facet[0],
                            "memory_mb": top_results[i].get("memory_mb"),
                            "cpu_percent": top_results[i].get("cpu")
                        })
        
        # Processar dados históricos
        if "data" in historical_data and "actor" in historical_data["data"]:
            account = historical_data["data"]["actor"]["account"]
            
            # Histórico de CPU
            if "cpu_history" in account and "results" in account["cpu_history"]:
                cpu_results = account["cpu_history"]["results"]
                result["historical"]["cpu"] = [
                    {
                        "timestamp": point.get("beginTimeSeconds"),
                        "value": point.get("cpu")
                    }
                    for point in cpu_results
                    if "beginTimeSeconds" in point and "cpu" in point
                ]
                
                # Calcular estatísticas
                if result["historical"]["cpu"]:
                    values = [point["value"] for point in result["historical"]["cpu"] if point["value"] is not None]
                    if values:
                        result["historical"]["cpu_stats"] = {
                            "avg": sum(values) / len(values),
                            "min": min(values),
                            "max": max(values)
                        }
            
            # Histórico de memória
            if "memory_history" in account and "results" in account["memory_history"]:
                memory_results = account["memory_history"]["results"]
                result["historical"]["memory"] = [
                    {
                        "timestamp": point.get("beginTimeSeconds"),
                        "value": point.get("memory")
                    }
                    for point in memory_results
                    if "beginTimeSeconds" in point and "memory" in point
                ]
                
                # Calcular estatísticas
                if result["historical"]["memory"]:
                    values = [point["value"] for point in result["historical"]["memory"] if point["value"] is not None]
                    if values:
                        result["historical"]["memory_stats"] = {
                            "avg": sum(values) / len(values),
                            "min": min(values),
                            "max": max(values)
                        }
            
            # Histórico de disco
            if "disk_history" in account and "results" in account["disk_history"]:
                disk_results = account["disk_history"]["results"]
                result["historical"]["disk"] = [
                    {
                        "timestamp": point.get("beginTimeSeconds"),
                        "value": point.get("disk")
                    }
                    for point in disk_results
                    if "beginTimeSeconds" in point and "disk" in point
                ]
            
            # Histórico de rede
            if "network_history" in account and "results" in account["network_history"]:
                network_results = account["network_history"]["results"]
                result["historical"]["network"] = [
                    {
                        "timestamp": point.get("beginTimeSeconds"),
                        "tx_mbps": point.get("tx_mbps"),
                        "rx_mbps": point.get("rx_mbps")
                    }
                    for point in network_results
                    if "beginTimeSeconds" in point
                ]
            
            # Histórico de carga
            if "load_history" in account and "results" in account["load_history"]:
                load_results = account["load_history"]["results"]
                result["historical"]["load"] = [
                    {
                        "timestamp": point.get("beginTimeSeconds"),
                        "value": point.get("load_1min")
                    }
                    for point in load_results
                    if "beginTimeSeconds" in point and "load_1min" in point
                ]
        
        # Salvar métricas principais no banco de dados
        try:
            # CPU
            if result["current"]["system"].get("cpu_percent") is not None:
                await database.execute(
                    metrics.insert().values(
                        platform="NewRelic", 
                        metric_name="system.cpuPercent", 
                        value=float(result["current"]["system"]["cpu_percent"])
                    )
                )
            
            # Memória
            if result["current"]["system"].get("memory_percent") is not None:
                await database.execute(
                    metrics.insert().values(
                        platform="NewRelic", 
                        metric_name="system.memoryUsedPercent", 
                        value=float(result["current"]["system"]["memory_percent"])
                    )
                )
            
            # Processos
            if result["current"]["processes"].get("count") is not None:
                await database.execute(
                    metrics.insert().values(
                        platform="NewRelic", 
                        metric_name="system.processCount", 
                        value=float(result["current"]["processes"]["count"])
                    )
                )
        except Exception as e:
            result["db_error"] = str(e)
        
        return result
    
    except Exception as e:
        return {
            "error": "Erro inesperado",
            "details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/list-newrelic-hosts")
async def list_newrelic_hosts():
    """
    Lista todos os hosts disponíveis no New Relic.
    Útil para descobrir hosts e seus respectivos GUIDs.
    """
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }
        
        # Consulta GraphQL para listar todos os hosts
        graphql_query = """
        {
          actor {
            account(id: %s) {
              hosts: nrql(query: "SELECT entityName, entityGuid, fullHostname, operatingSystem, windowsVersion FROM SystemSample LIMIT MAX") {
                results
              }
              infra_hosts: nrql(query: "FROM SystemSample SELECT uniques(hostname), uniques(entityGuid), uniques(fullHostname) LIMIT MAX") {
                results
              }
            }
          }
        }
        """ % NEWRELIC_ACCOUNT_ID
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": graphql_query}
        )
        
        if response.status_code != 200:
            return {
                "status": "error",
                "message": f"Erro na consulta ao New Relic: {response.status_code}",
                "response": response.text
            }
            
        data = response.json()
        
        # Extrair dados dos hosts
        hosts = []
        host_guids = set()  # Para evitar duplicatas
        
        if ("data" in data and "actor" in data["data"] and 
            "account" in data["data"]["actor"] and "hosts" in data["data"]["actor"]["account"] and 
            "results" in data["data"]["actor"]["account"]["hosts"]):
            
            results = data["data"]["actor"]["account"]["hosts"]["results"]
            for host in results:
                if "entityGuid" in host and host["entityGuid"] not in host_guids:
                    host_guids.add(host["entityGuid"])
                    hosts.append({
                        "name": host.get("entityName"),
                        "guid": host.get("entityGuid"),
                        "hostname": host.get("fullHostname"),
                        "os": host.get("operatingSystem"),
                        "windows_version": host.get("windowsVersion")
                    })
        
        # Se não encontrou hosts, tenta buscar usando o modo alternativo
        if not hosts and "infra_hosts" in data["data"]["actor"]["account"]:
            infra_results = data["data"]["actor"]["account"]["infra_hosts"]["results"]
            if infra_results and len(infra_results) > 0:
                hostnames = infra_results[0].get("uniques.hostname", [])
                guids = infra_results[0].get("uniques.entityGuid", [])
                fullhostnames = infra_results[0].get("uniques.fullHostname", [])
                
                # Tenta mapear hostnames com GUIDs (caso os arrays tenham o mesmo tamanho)
                if len(hostnames) == len(guids):
                    for i in range(len(hostnames)):
                        full_hostname = fullhostnames[i] if i < len(fullhostnames) else None
                        hosts.append({
                            "name": hostnames[i],
                            "guid": guids[i],
                            "hostname": full_hostname,
                            "os": None,  # Informação não disponível neste formato
                            "windows_version": None  # Informação não disponível neste formato
                        })
                else:
                    # Caso contrário, separa as informações
                    for hostname in hostnames:
                        hosts.append({
                            "name": hostname,
                            "guid": None,
                            "hostname": None,
                            "os": None,
                            "windows_version": None
                        })
                    
                    for guid in guids:
                        hosts.append({
                            "name": None,
                            "guid": guid,
                            "hostname": None,
                            "os": None,
                            "windows_version": None
                        })
        
        # Se ainda não temos hosts, fazemos uma última tentativa buscando apenas GUIDs
        if not hosts:
            last_attempt_query = """
            {
              actor {
                entitySearch {
                  results {
                    entities {
                      guid
                      name
                      type
                    }
                  }
                }
              }
            }
            """
            
            last_response = requests.post(
                "https://api.newrelic.com/graphql",
                headers=headers,
                json={"query": last_attempt_query}
            )
            
            if last_response.status_code == 200:
                last_data = last_response.json()
                if ("data" in last_data and "actor" in last_data["data"] and 
                    "entitySearch" in last_data["data"]["actor"] and 
                    "results" in last_data["data"]["actor"]["entitySearch"] and 
                    "entities" in last_data["data"]["actor"]["entitySearch"]["results"]):
                    
                    entities = last_data["data"]["actor"]["entitySearch"]["results"]["entities"]
                    for entity in entities:
                        if entity.get("type") == "HOST" and entity.get("guid") not in host_guids:
                            host_guids.add(entity.get("guid"))
                            hosts.append({
                                "name": entity.get("name"),
                                "guid": entity.get("guid"),
                                "hostname": entity.get("name"),
                                "type": entity.get("type"),
                                "os": None,
                                "windows_version": None
                            })
        
        return {
            "status": "success",
            "account_id": NEWRELIC_ACCOUNT_ID,
            "current_guid": TUKSTATION_ENTITY_GUID,
            "host_count": len(hosts),
            "hosts": hosts
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro inesperado: {str(e)}",
            "error_details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/fetch-newrelic-basic")
async def fetch_newrelic_basic():
    """
    Endpoint simplificado que busca apenas métricas básicas de CPU e memória.
    Este endpoint sempre deve funcionar, mesmo quando outros mais específicos falham.
    """
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }
        
        # Consulta GraphQL simples para obter métricas básicas
        graphql_query = """
        {
          actor {
            account(id: %s) {
              cpu: nrql(query: "SELECT latest(cpuPercent) as cpu FROM SystemSample WHERE entityGuid = '%s' SINCE 5 minutes ago LIMIT 1") {
                results
              }
              memory: nrql(query: "SELECT latest(memoryUsedPercent) as memory FROM SystemSample WHERE entityGuid = '%s' SINCE 5 minutes ago LIMIT 1") {
                results
              }
              host: nrql(query: "SELECT entityName FROM SystemSample WHERE entityGuid = '%s' SINCE 5 minutes ago LIMIT 1") {
                results
              }
              fallback: nrql(query: "SELECT latest(cpuPercent) as cpu, latest(memoryUsedPercent) as memory FROM SystemSample LIMIT 1") {
                results
              }
            }
          }
        }
        """ % (NEWRELIC_ACCOUNT_ID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID)
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": graphql_query}
        )
        
        if response.status_code != 200:
            return {
                "status": "error",
                "message": f"Erro na consulta ao New Relic: {response.status_code}",
                "response": response.text
            }
            
        data = response.json()
        
        result = {
            "status": "success",
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "entity_guid": TUKSTATION_ENTITY_GUID,
            "metrics": {
                "cpu": None,
                "memory": None
            },
            "host": None
        }
        
        # Tentar extrair dados do host específico
        has_data = False
        
        if "data" in data and "actor" in data["data"] and "account" in data["data"]["actor"]:
            account = data["data"]["actor"]["account"]
            
            # Nome do host
            if "host" in account and "results" in account["host"] and account["host"]["results"]:
                host_results = account["host"]["results"]
                if host_results and len(host_results) > 0:
                    result["host"] = host_results[0].get("entityName")
            
            # CPU
            if "cpu" in account and "results" in account["cpu"] and account["cpu"]["results"]:
                cpu_results = account["cpu"]["results"]
                if cpu_results and len(cpu_results) > 0 and "cpu" in cpu_results[0]:
                    result["metrics"]["cpu"] = cpu_results[0]["cpu"]
                    has_data = True
            
            # Memória
            if "memory" in account and "results" in account["memory"] and account["memory"]["results"]:
                memory_results = account["memory"]["results"]
                if memory_results and len(memory_results) > 0 and "memory" in memory_results[0]:
                    result["metrics"]["memory"] = memory_results[0]["memory"]
                    has_data = True
            
            # Se não temos dados do host específico, usar fallback
            if not has_data and "fallback" in account and "results" in account["fallback"]:
                fallback_results = account["fallback"]["results"]
                if fallback_results and len(fallback_results) > 0:
                    result["metrics"]["cpu"] = fallback_results[0].get("cpu")
                    result["metrics"]["memory"] = fallback_results[0].get("memory")
                    result["message"] = "Usando dados de fallback (não específicos para o host solicitado)"
                    has_data = True
        
        # Se ainda não temos dados, tentar uma última consulta mais simples
        if not has_data:
            simple_query = """
            {
              actor {
                account(id: %s) {
                  data: nrql(query: "SELECT latest(cpuPercent) as cpu, latest(memoryUsedPercent) as memory FROM SystemSample LIMIT 1") {
                    results
                  }
                }
              }
            }
            """ % NEWRELIC_ACCOUNT_ID
            
            simple_response = requests.post(
                "https://api.newrelic.com/graphql",
                headers=headers,
                json={"query": simple_query}
            )
            
            if simple_response.status_code == 200:
                simple_data = simple_response.json()
                
                if ("data" in simple_data and 
                    "actor" in simple_data["data"] and 
                    "account" in simple_data["data"]["actor"] and 
                    "data" in simple_data["data"]["actor"]["account"] and 
                    "results" in simple_data["data"]["actor"]["account"]["data"]):
                    
                    simple_results = simple_data["data"]["actor"]["account"]["data"]["results"]
                    if simple_results and len(simple_results) > 0:
                        result["metrics"]["cpu"] = simple_results[0].get("cpu")
                        result["metrics"]["memory"] = simple_results[0].get("memory")
                        result["message"] = "Usando dados de fallback final (qualquer host disponível)"
                        has_data = True
        
        # Salvar métricas no banco de dados se disponíveis
        if result["metrics"]["cpu"] is not None:
            try:
                await database.execute(
                    metrics.insert().values(
                        platform="NewRelic", 
                        metric_name="system.cpuPercent", 
                        value=float(result["metrics"]["cpu"])
                    )
                )
            except Exception as e:
                result["db_error_cpu"] = str(e)
        
        if result["metrics"]["memory"] is not None:
            try:
                await database.execute(
                    metrics.insert().values(
                        platform="NewRelic", 
                        metric_name="system.memoryUsedPercent", 
                        value=float(result["metrics"]["memory"])
                    )
                )
            except Exception as e:
                result["db_error_memory"] = str(e)
        
        return result
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro inesperado: {str(e)}",
            "error_details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/discover-newrelic-data")
async def discover_newrelic_data():
    """
    Ferramenta de diagnóstico para descobrir tipos de eventos e métricas disponíveis no New Relic.
    Auxilia na exploração dos dados disponíveis para consulta.
    """
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }
        
        # Consulta GraphQL para descobrir tipos de eventos
        event_types_query = """
        {
          actor {
            account(id: %s) {
              eventTypes: nrql(query: "SHOW EVENT TYPES") {
                results
              }
              metrics: nrql(query: "SHOW METRICS WHERE entityGuid = '%s'") {
                results
              }
              host_metadata: nrql(query: "SELECT * FROM SystemSample WHERE entityGuid = '%s' LIMIT 1") {
                metadata {
                  facets
                  eventTypes
                  attributes
                }
                results
              }
              network_metadata: nrql(query: "SELECT * FROM NetworkSample WHERE entityGuid = '%s' LIMIT 1") {
                metadata {
                  attributes
                }
                results
              }
              storage_metadata: nrql(query: "SELECT * FROM StorageSample WHERE entityGuid = '%s' LIMIT 1") {
                metadata {
                  attributes
                }
                results
              }
              process_metadata: nrql(query: "SELECT * FROM ProcessSample WHERE entityGuid = '%s' LIMIT 1") {
                metadata {
                  attributes
                }
                results
              }
            }
          }
        }
        """ % (NEWRELIC_ACCOUNT_ID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, 
               TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID)
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": event_types_query}
        )
        
        if response.status_code != 200:
            return {
                "status": "error",
                "message": f"Erro na consulta ao New Relic: {response.status_code}",
                "response": response.text
            }
            
        data = response.json()
        
        result = {
            "status": "success",
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "entity_guid": TUKSTATION_ENTITY_GUID,
            "account_id": NEWRELIC_ACCOUNT_ID,
            "discovery": {
                "event_types": [],
                "metrics": [],
                "system_attributes": [],
                "network_attributes": [],
                "storage_attributes": [],
                "process_attributes": []
            }
        }
        
        # Extrair tipos de eventos e métricas
        account = None
        if "data" in data and "actor" in data["data"] and "account" in data["data"]["actor"]:
            account = data["data"]["actor"]["account"]
            
            # Tipos de eventos
            if "eventTypes" in account and "results" in account["eventTypes"]:
                event_results = account["eventTypes"]["results"]
                for event in event_results:
                    if "eventType" in event:
                        result["discovery"]["event_types"].append(event["eventType"])
            
            # Métricas
            if "metrics" in account and "results" in account["metrics"]:
                metric_results = account["metrics"]["results"]
                for metric in metric_results:
                    if "metric" in metric:
                        result["discovery"]["metrics"].append(metric["metric"])
            
            # Atributos do SystemSample
            if ("host_metadata" in account and "metadata" in account["host_metadata"] and 
                "attributes" in account["host_metadata"]["metadata"]):
                
                attributes = account["host_metadata"]["metadata"]["attributes"]
                if isinstance(attributes, list):
                    result["discovery"]["system_attributes"] = attributes
            
            # Atributos do NetworkSample
            if ("network_metadata" in account and "metadata" in account["network_metadata"] and 
                "attributes" in account["network_metadata"]["metadata"]):
                
                attributes = account["network_metadata"]["metadata"]["attributes"]
                if isinstance(attributes, list):
                    result["discovery"]["network_attributes"] = attributes
            
            # Atributos do StorageSample
            if ("storage_metadata" in account and "metadata" in account["storage_metadata"] and 
                "attributes" in account["storage_metadata"]["metadata"]):
                
                attributes = account["storage_metadata"]["metadata"]["attributes"]
                if isinstance(attributes, list):
                    result["discovery"]["storage_attributes"] = attributes
            
            # Atributos do ProcessSample
            if ("process_metadata" in account and "metadata" in account["process_metadata"] and 
                "attributes" in account["process_metadata"]["metadata"]):
                
                attributes = account["process_metadata"]["metadata"]["attributes"]
                if isinstance(attributes, list):
                    result["discovery"]["process_attributes"] = attributes
        
        # Criar exemplos de NRQL
        result["nrql_examples"] = [
            {
                "description": "Uso de CPU ao longo do tempo",
                "query": f"SELECT average(cpuPercent) FROM SystemSample WHERE entityGuid = '{TUKSTATION_ENTITY_GUID}' TIMESERIES AUTO SINCE 1 hour ago"
            },
            {
                "description": "Uso de memória",
                "query": f"SELECT latest(memoryUsedPercent) FROM SystemSample WHERE entityGuid = '{TUKSTATION_ENTITY_GUID}' SINCE 5 minutes ago"
            },
            {
                "description": "Uso de disco por dispositivo",
                "query": f"SELECT latest(diskUsedPercent) FROM StorageSample WHERE entityGuid = '{TUKSTATION_ENTITY_GUID}' FACET device LIMIT MAX SINCE 5 minutes ago"
            },
            {
                "description": "Top processos por CPU",
                "query": f"SELECT latest(cpuPercent) FROM ProcessSample WHERE entityGuid = '{TUKSTATION_ENTITY_GUID}' FACET processDisplayName ORDER BY latest(cpuPercent) DESC LIMIT 10 SINCE 5 minutes ago"
            },
            {
                "description": "Tráfego de rede",
                "query": f"SELECT sum(transmitBytesPerSecond)/1024/1024 as 'TX MB/s', sum(receiveBytesPerSecond)/1024/1024 as 'RX MB/s' FROM NetworkSample WHERE entityGuid = '{TUKSTATION_ENTITY_GUID}' TIMESERIES AUTO SINCE 30 minutes ago"
            }
        ]
        
        # Adicionar links úteis de documentação
        result["useful_links"] = {
            "nrql_docs": "https://docs.newrelic.com/docs/query-your-data/nrql-new-relic-query-language/get-started/introduction-nrql-new-relics-query-language/",
            "metric_types": "https://docs.newrelic.com/docs/data-apis/understand-data/metric-data/metric-data-type/",
            "graphql_api": "https://docs.newrelic.com/docs/apis/nerdgraph/get-started/introduction-new-relic-nerdgraph/"
        }
        
        # Adicionar exemplos de dados apenas se account foi devidamente definido
        if account:
            # Exemplo de dados
            examples = {}
            
            if "host_metadata" in account and "results" in account["host_metadata"]:
                host_results = account["host_metadata"]["results"]
                if host_results and len(host_results) > 0:
                    examples["system_sample"] = host_results[0]
                    
                    # Adicionar exemplo usando hostname se disponível
                    host_name = host_results[0].get("entityName")
                    if host_name:
                        result["nrql_examples"].append({
                            "description": "Filtrar por nome do host",
                            "query": f"SELECT latest(cpuPercent) FROM SystemSample WHERE hostname = '{host_name}' SINCE 5 minutes ago"
                        })
            
            if "network_metadata" in account and "results" in account["network_metadata"]:
                network_results = account["network_metadata"]["results"]
                if network_results and len(network_results) > 0:
                    examples["network_sample"] = network_results[0]
            
            if "storage_metadata" in account and "results" in account["storage_metadata"]:
                storage_results = account["storage_metadata"]["results"]
                if storage_results and len(storage_results) > 0:
                    examples["storage_sample"] = storage_results[0]
            
            if "process_metadata" in account and "results" in account["process_metadata"]:
                process_results = account["process_metadata"]["results"]
                if process_results and len(process_results) > 0:
                    examples["process_sample"] = process_results[0]
            
            if examples:
                result["discovery"]["examples"] = examples
        
        return result
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro inesperado: {str(e)}",
            "error_details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/nr/logs")
async def get_newrelic_logs(minutes: int = 30, limit: int = 100):
    """
    Retorna logs do sistema (events, errors, alerts) do host no New Relic.
    
    Parâmetros:
    - minutes: Número de minutos para buscar dados (padrão: 30)
    - limit: Número máximo de logs a serem retornados (padrão: 100)
    """
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }

        # Query para logs usando entityGuid fornecido
        query = """
        {
          actor {
            account(id: %s) {
              logs: nrql(query: "SELECT `level`,`message`,`timestamp` FROM Log WHERE `entity.guid` = '%s' OR `entity.guids` LIKE '%%%s%%' OR `host.name` = 'TUKSTATION' OR `hostname` = 'TUKSTATION' OR `host` = 'TUKSTATION' SINCE %d minutes ago LIMIT %d") {
                results
              }
              error_logs: nrql(query: "SELECT `level`,`message`,`timestamp` FROM Log WHERE (`level` = 'ERROR' OR `level` = 'CRITICAL' OR `level` = 'FATAL') AND (`entity.guid` = '%s' OR `entity.guids` LIKE '%%%s%%' OR `host.name` = 'TUKSTATION' OR `hostname` = 'TUKSTATION' OR `host` = 'TUKSTATION') SINCE %d minutes ago LIMIT %d") {
                results
              }
              warnings: nrql(query: "SELECT `level`,`message`,`timestamp` FROM Log WHERE `level` = 'WARNING' AND (`entity.guid` = '%s' OR `entity.guids` LIKE '%%%s%%' OR `host.name` = 'TUKSTATION' OR `hostname` = 'TUKSTATION' OR `host` = 'TUKSTATION') SINCE %d minutes ago LIMIT %d") {
                results
              }
              event_types: nrql(query: "SELECT count(*) FROM Log WHERE (`entity.guid` = '%s' OR `entity.guids` LIKE '%%%s%%' OR `host.name` = 'TUKSTATION' OR `hostname` = 'TUKSTATION' OR `host` = 'TUKSTATION') FACET `event.type`, `level` SINCE %d minutes ago LIMIT %d") {
                results
                facets
              }
            }
          }
        }
        """ % (
            NEWRELIC_ACCOUNT_ID, TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, minutes, limit,
            TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, minutes, limit,
            TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, minutes, limit,
            TUKSTATION_ENTITY_GUID, TUKSTATION_ENTITY_GUID, minutes, limit
        )
        
        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": query}
        )
        
        if response.status_code != 200:
            return {
                "status": "error",
                "message": f"Erro na consulta ao New Relic: {response.status_code}",
                "response": response.text
            }
            
        data = response.json()
        
        # Processar os resultados
        result = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "entity_guid": TUKSTATION_ENTITY_GUID,
            "logs": [],
            "errors": [],
            "warnings": [],
            "log_summary": {},
            "status": "success",
            "query_period_minutes": minutes
        }
        
        # Extrair logs
        if "data" in data and "actor" in data["data"] and "account" in data["data"]["actor"]:
            account = data["data"]["actor"]["account"]
            
            # Logs gerais
            if "logs" in account and "results" in account["logs"]:
                log_results = account["logs"]["results"]
                result["logs"] = log_results
                result["log_count"] = len(log_results)
            
            # Logs de erro
            if "error_logs" in account and "results" in account["error_logs"]:
                error_results = account["error_logs"]["results"]
                result["errors"] = error_results
                result["error_count"] = len(error_results)
            
            # Logs de aviso
            if "warnings" in account and "results" in account["warnings"]:
                warning_results = account["warnings"]["results"]
                result["warnings"] = warning_results
                result["warning_count"] = len(warning_results)
            
            # Resumo de tipos de eventos
            if "event_types" in account and "results" in account["event_types"] and "facets" in account["event_types"]:
                event_results = account["event_types"]["results"]
                facets = account["event_types"]["facets"]
                
                event_summary = {}
                for i, facet in enumerate(facets):
                    if i < len(event_results) and len(facet) >= 2:
                        event_type = facet[0]
                        level = facet[1]
                        count = event_results[i].get("count") if "count" in event_results[i] else 0
                        
                        if event_type not in event_summary:
                            event_summary[event_type] = {}
                        
                        event_summary[event_type][level] = count
                
                result["log_summary"] = event_summary
        
        # Verificar se temos dados
        if not result["logs"] and not result["errors"] and not result["warnings"]:
            result["status"] = "warning"
            result["message"] = f"Nenhum log encontrado para o período de {minutes} minutos"
            
            # Tentar buscar com um período maior se não encontramos logs
            if minutes < 360:  # Não vamos tentar mais de 6 horas
                result["suggestion"] = f"Tente aumentar o período de busca: /nr/logs?minutes={minutes*2}"
        else:
            result["message"] = f"Encontrados {result.get('log_count', 0)} logs, incluindo {result.get('error_count', 0)} erros e {result.get('warning_count', 0)} avisos"
        
        return result
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro inesperado: {str(e)}",
            "error_details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

@app.get("/nr/kubernetes")
async def get_kubernetes_metrics(namespace: str = None, hours: int = 1):
    """
    Retorna métricas relacionadas ao Kubernetes do New Relic e salva em formato customizado.
    Parâmetros opcionais:
    - namespace: Filtrar por namespace específico
    - hours: Período de dados em horas (padrão: 1)
    """
    try:
        headers = {
            "Accept": "application/json",
            "Api-Key": NEWRELIC_API_KEY,
            "Content-Type": "application/json"
        }

        # Construir a condição de namespace se fornecida
        namespace_condition = f"AND kubernetes.namespaceName = '{namespace}'" if namespace else ""
        
        # Query para buscar dados de utilização de CPU e memória por pod/container
        query = """
        {
          actor {
            account(id: %s) {
              cpu: nrql(query: "SELECT average(cpuUsedCores) AS 'cpu_used', average(cpuRequestedCores) AS 'cpu_requested', 
                                       average(cpuLimitCores) AS 'cpu_limit', latest(cpuUsedCoresUtilization) AS 'cpu_utilization' 
                                FROM K8sContainerSample 
                                WHERE kubernetes.clusterName IS NOT NULL %s
                                FACET kubernetes.clusterName, kubernetes.namespaceName, kubernetes.podName, containerName 
                                SINCE %d hours ago LIMIT 1000") {
                results
              }
              memory: nrql(query: "SELECT average(memoryUsedBytes)/1024/1024 AS 'memory_used_mb', average(memoryRequestedBytes)/1024/1024 AS 'memory_requested_mb', 
                                         average(memoryLimitBytes)/1024/1024 AS 'memory_limit_mb', latest(memoryUsedUtilization) AS 'memory_utilization' 
                                FROM K8sContainerSample 
                                WHERE kubernetes.clusterName IS NOT NULL %s
                                FACET kubernetes.clusterName, kubernetes.namespaceName, kubernetes.podName, containerName 
                                SINCE %d hours ago LIMIT 1000") {
                results
              }
              pods: nrql(query: "SELECT uniqueCount(kubernetes.podName) AS 'pod_count' 
                               FROM K8sContainerSample 
                               WHERE kubernetes.clusterName IS NOT NULL %s
                               FACET kubernetes.clusterName, kubernetes.namespaceName 
                               SINCE %d hours ago") {
                results
              }
              containers: nrql(query: "SELECT uniqueCount(containerName) AS 'container_count' 
                                    FROM K8sContainerSample 
                                    WHERE kubernetes.clusterName IS NOT NULL %s
                                    FACET kubernetes.clusterName, kubernetes.namespaceName 
                                    SINCE %d hours ago") {
                results
              }
            }
          }
        }
        """ % (NEWRELIC_ACCOUNT_ID, namespace_condition, hours, namespace_condition, hours, namespace_condition, hours, namespace_condition, hours)

        response = requests.post(
            "https://api.newrelic.com/graphql",
            headers=headers,
            json={"query": query}
        )
        
        if response.status_code != 200:
            return {
                "error": "Erro na requisição",
                "status_code": response.status_code,
                "response": response.text
            }
            
        data = response.json()
        
        if "data" not in data or "actor" not in data["data"] or "account" not in data["data"]["actor"]:
            return {
                "error": "Estrutura de resposta inesperada",
                "data": data
            }
            
        account = data["data"]["actor"]["account"]
        result = {
            "timestamp": datetime.datetime.now().isoformat(),
            "cpu_metrics": [],
            "memory_metrics": [],
            "pod_counts": [],
            "container_counts": [],
            "saved_records": 0
        }
        
        # Processar métricas de CPU por container
        if "cpu" in account and "results" in account["cpu"]:
            for item in account["cpu"]["results"]:
                cluster = item.get("facet")[0] if len(item.get("facet", [])) > 0 else "unknown"
                namespace = item.get("facet")[1] if len(item.get("facet", [])) > 1 else "unknown"
                pod_name = item.get("facet")[2] if len(item.get("facet", [])) > 2 else "unknown"
                container = item.get("facet")[3] if len(item.get("facet", [])) > 3 else "unknown"
                
                cpu_item = {
                    "cluster_name": cluster,
                    "namespace": namespace,
                    "pod_name": pod_name,
                    "container_name": container,
                    "cpu_used": item.get("cpu_used"),
                    "cpu_requested": item.get("cpu_requested"),
                    "cpu_limit": item.get("cpu_limit"),
                    "cpu_utilization": item.get("cpu_utilization")
                }
                result["cpu_metrics"].append(cpu_item)
                
                # Salvar no banco de dados
                try:
                    await database.execute(
                        kubernetes_metrics.insert().values(
                            timestamp=datetime.datetime.now(),
                            cluster_name=cluster,
                            namespace=namespace,
                            pod_name=pod_name,
                            container_name=container,
                            metric_type="cpu",
                            metric_name="used_cores",
                            value=item.get("cpu_used"),
                            unit="cores",
                            metadata=json.dumps({
                                "requested": item.get("cpu_requested"),
                                "limit": item.get("cpu_limit"),
                                "utilization": item.get("cpu_utilization")
                            })
                        )
                    )
                    result["saved_records"] += 1
                except Exception as e:
                    if "db_errors" not in result:
                        result["db_errors"] = []
                    result["db_errors"].append(str(e))
        
        # Processar métricas de memória por container
        if "memory" in account and "results" in account["memory"]:
            for item in account["memory"]["results"]:
                cluster = item.get("facet")[0] if len(item.get("facet", [])) > 0 else "unknown"
                namespace = item.get("facet")[1] if len(item.get("facet", [])) > 1 else "unknown"
                pod_name = item.get("facet")[2] if len(item.get("facet", [])) > 2 else "unknown"
                container = item.get("facet")[3] if len(item.get("facet", [])) > 3 else "unknown"
                
                memory_item = {
                    "cluster_name": cluster,
                    "namespace": namespace,
                    "pod_name": pod_name,
                    "container_name": container,
                    "memory_used_mb": item.get("memory_used_mb"),
                    "memory_requested_mb": item.get("memory_requested_mb"),
                    "memory_limit_mb": item.get("memory_limit_mb"),
                    "memory_utilization": item.get("memory_utilization")
                }
                result["memory_metrics"].append(memory_item)
                
                # Salvar no banco de dados
                try:
                    await database.execute(
                        kubernetes_metrics.insert().values(
                            timestamp=datetime.datetime.now(),
                            cluster_name=cluster,
                            namespace=namespace,
                            pod_name=pod_name,
                            container_name=container,
                            metric_type="memory",
                            metric_name="used_mb",
                            value=item.get("memory_used_mb"),
                            unit="MB",
                            metadata=json.dumps({
                                "requested_mb": item.get("memory_requested_mb"),
                                "limit_mb": item.get("memory_limit_mb"),
                                "utilization": item.get("memory_utilization")
                            })
                        )
                    )
                    result["saved_records"] += 1
                except Exception as e:
                    if "db_errors" not in result:
                        result["db_errors"] = []
                    result["db_errors"].append(str(e))
        
        # Processar contagem de pods por namespace
        if "pods" in account and "results" in account["pods"]:
            for item in account["pods"]["results"]:
                cluster = item.get("facet")[0] if len(item.get("facet", [])) > 0 else "unknown"
                namespace = item.get("facet")[1] if len(item.get("facet", [])) > 1 else "unknown"
                
                pod_count = {
                    "cluster_name": cluster,
                    "namespace": namespace,
                    "pod_count": item.get("pod_count")
                }
                result["pod_counts"].append(pod_count)
                
                # Salvar no banco de dados
                try:
                    await database.execute(
                        kubernetes_metrics.insert().values(
                            timestamp=datetime.datetime.now(),
                            cluster_name=cluster,
                            namespace=namespace,
                            pod_name="aggregate",
                            container_name="aggregate",
                            metric_type="kubernetes",
                            metric_name="pod_count",
                            value=item.get("pod_count"),
                            unit="count",
                            metadata=json.dumps({})
                        )
                    )
                    result["saved_records"] += 1
                except Exception as e:
                    if "db_errors" not in result:
                        result["db_errors"] = []
                    result["db_errors"].append(str(e))
        
        # Processar contagem de containers por namespace
        if "containers" in account and "results" in account["containers"]:
            for item in account["containers"]["results"]:
                cluster = item.get("facet")[0] if len(item.get("facet", [])) > 0 else "unknown"
                namespace = item.get("facet")[1] if len(item.get("facet", [])) > 1 else "unknown"
                
                container_count = {
                    "cluster_name": cluster,
                    "namespace": namespace,
                    "container_count": item.get("container_count")
                }
                result["container_counts"].append(container_count)
                
                # Salvar no banco de dados
                try:
                    await database.execute(
                        kubernetes_metrics.insert().values(
                            timestamp=datetime.datetime.now(),
                            cluster_name=cluster,
                            namespace=namespace,
                            pod_name="aggregate",
                            container_name="aggregate",
                            metric_type="kubernetes",
                            metric_name="container_count",
                            value=item.get("container_count"),
                            unit="count",
                            metadata=json.dumps({})
                        )
                    )
                    result["saved_records"] += 1
                except Exception as e:
                    if "db_errors" not in result:
                        result["db_errors"] = []
                    result["db_errors"].append(str(e))
        
        # Adicionar estatísticas agregadas
        if result["cpu_metrics"]:
            cpu_values = [item.get("cpu_used") for item in result["cpu_metrics"] if item.get("cpu_used") is not None]
            if cpu_values:
                result["stats"] = {
                    "cpu": {
                        "total": sum(cpu_values),
                        "avg": sum(cpu_values) / len(cpu_values),
                        "min": min(cpu_values),
                        "max": max(cpu_values)
                    }
                }
        
        if result["memory_metrics"]:
            memory_values = [item.get("memory_used_mb") for item in result["memory_metrics"] if item.get("memory_used_mb") is not None]
            if memory_values:
                if "stats" not in result:
                    result["stats"] = {}
                result["stats"]["memory"] = {
                    "total_mb": sum(memory_values),
                    "avg_mb": sum(memory_values) / len(memory_values),
                    "min_mb": min(memory_values),
                    "max_mb": max(memory_values)
                }
        
        return result
    
    except Exception as e:
        return {
            "error": "Erro inesperado",
            "details": str(e),
            "traceback": __import__('traceback').format_exc()
        }

