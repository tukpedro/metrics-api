import datetime

from sqlalchemy import (Column, DateTime, Float, Integer, MetaData, String,
                        Table, Text)

metadata = MetaData()

metrics = Table(
    "metrics",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("platform", String, index=True),
    Column("metric_name", String, index=True),
    Column("value", Float),
)

kubernetes_metrics = Table(
    "kubernetes_metrics",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("timestamp", DateTime, default=datetime.datetime.utcnow),
    Column("cluster_name", String, index=True),
    Column("namespace", String, index=True),
    Column("pod_name", String, index=True),
    Column("container_name", String),
    Column("metric_type", String, index=True),  # cpu, memory, disk, etc
    Column("metric_name", String, index=True),
    Column("value", Float),
    Column("unit", String),
    Column("metadata", Text),  # JSON data for additional info
)
