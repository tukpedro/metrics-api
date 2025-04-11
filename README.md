# Metrics API para Kubernetes

Uma API simplificada para extrair métricas de plataformas de observabilidade (DataDog, New Relic) sobre clusters Kubernetes, transformar os dados e armazená-los localmente.

## Objetivo

Este projeto foi desenvolvido como demonstração para uma vaga de Python Backend Engineer, focando na criação de um serviço que:

1. Consulta APIs de plataformas de observabilidade (New Relic, DataDog)
2. Extrai métricas relacionadas a clusters Kubernetes (CPU, memória, contagem de pods, uso por namespace)
3. Transforma e armazena estes dados em formato customizado no PostgreSQL
4. Fornece análise de custos por namespace

## Arquitetura

- **API REST**: Desenvolvida com FastAPI para consultar e retornar métricas
- **Banco de Dados**: PostgreSQL para armazenamento das métricas processadas
- **Análise de Custos**: Script para calcular custos aproximados e gerar relatórios

## Principais Funcionalidades

### Endpoints de Métricas

- `/nr/kubernetes`: Extrai métricas de Kubernetes do New Relic (CPU, memória, contagem de pods)
- `/nr/cpu`: Dados detalhados de CPU
- `/nr/memory`: Dados detalhados de memória
- `/nr/dashboard`: Dashboard com métricas principais
- `/fetch-datadog-metrics`: Busca métricas do DataDog (kubernetes.cpu.usage.total)

### Modelo de Dados

- Tabela `kubernetes_metrics`: Armazena métricas específicas de Kubernetes com schema customizado
- Tabela `metrics`: Armazena métricas genéricas

### Análise de Custos

O script `kubernetes_cost_analysis.py` fornece:

- Cálculo de custos aproximados baseados em uso de CPU e memória
- Relatórios por namespace e pod
- Gráficos para visualização de custos
- Tendências de uso e custo ao longo do tempo

## Instalação

1. Clone o repositório:
```bash
git clone https://github.com/seu-usuario/metrics-api.git
cd metrics-api
```

2. Instale as dependências:
```bash
pip install -r requirements.txt
```

3. Configure as variáveis de ambiente no arquivo `.env`:
```
DATABASE_URL=postgresql+psycopg2://usuario:senha@localhost/nome_do_banco
NEWRELIC_API_KEY=sua_chave_api_newrelic
NEWRELIC_ACCOUNT_ID=seu_id_conta_newrelic
DATADOG_API_KEY=sua_chave_api_datadog
DATADOG_APP_KEY=sua_chave_app_datadog
```

4. Execute as migrações do banco de dados:
```bash
alembic upgrade head
```

5. Inicie a aplicação:
```bash
uvicorn main:app --reload
```

## Uso

### Consultar Métricas de Kubernetes

```bash
curl http://localhost:8000/nr/kubernetes
```

### Gerar Relatório de Custos

```bash
python kubernetes_cost_analysis.py
```

## Requisitos

- Python 3.8+
- PostgreSQL
- New Relic API Key
- DataDog API Key (opcional)

## Exemplos de Integração

### Exemplo de Consulta ao New Relic

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

### Exemplo de Análise de Custos

```python
import asyncio
from kubernetes_cost_analysis import calculate_kubernetes_costs, generate_cost_charts

async def analyze():
    # Calcular custos das últimas 24 horas
    costs = await calculate_kubernetes_costs(hours=24)
    print(f"Custo total: ${costs['total_cost']}")
    
    # Gerar gráficos
    await generate_cost_charts(hours=24, output_dir="./reports")

if __name__ == "__main__":
    asyncio.run(analyze())
```

## Próximos Passos

- Adicionar suporte para mais plataformas de observabilidade
- Implementar alertas baseados em custos
- Desenvolver dashboard web para visualização
- Adicionar recomendações de otimização de recursos

## Tecnologias

- Python
- FastAPI
- SQLite

## Instalação inicial

Crie o ambiente virtual e instale as dependências:

```bash
python -m venv venv
source venv/bin/activate
pip install fastapi uvicorn requests python-dotenv sqlalchemy databases
