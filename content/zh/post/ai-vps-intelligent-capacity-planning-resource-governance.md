---
title: "AI驱动的VPS智能容量规划与资源治理：从被动应对到主动预测"
description: "传统VPS容量规划依赖人工经验，面对业务增长往往滞后。本文介绍如何构建AI驱动的VPS智能容量规划与资源治理系统，实现从被动应对到主动预测的转变，包括预测模型、资源分配策略和治理框架的完整实现。"
date: 2026-08-19T21:00:00+08:00
lastmod: 2026-08-19T21:00:00+08:00
slug: "ai-vps-intelligent-capacity-planning-resource-governance"
tags: ["AI", "VPS", "容量规划", "资源治理", "预测分析", "Auto Scaling", "成本优化", "Docker", "Prometheus"]
categories: ["AI+VPS"]
draft: false
image: /images/posts/ai-vps-intelligent-capacity-planning-resource-governance/featured.png
---

## 引言

在VPS运维中，容量规划始终是一个核心难题。传统做法依赖管理员的经验判断——根据历史流量高峰预留30%~50%的缓冲资源。这种方式有两个根本性缺陷：**资源浪费**（高峰预留导致平时大量资源闲置）和**容量不足**（业务突增时反应滞后）。

AI技术的成熟正在改变这一局面。**AI驱动的VPS智能容量规划与资源治理**系统通过持续学习业务模式、预测未来需求、动态优化资源配置，实现了从"被动救火"到"主动规划"的转变。

本文将系统性地介绍如何构建这样一个完整的AI容量规划与资源治理体系。

---

## 一、AI容量规划的核心挑战

### 1.1 传统规划的三大痛点

| 痛点 | 传统做法 | 后果 |
|------|---------|------|
| 容量估算 | 基于历史峰值加固定比例 | 平时浪费20%~40%，高峰仍可能不足 |
| 扩容决策 | 人工判断，事后补救 | 响应延迟，用户体验受损 |
| 资源分配 | 静态分配，长期固定 | 无法适应业务波动和增长 |

### 1.2 AI方案的独特价值

AI容量规划系统的核心价值体现在三个维度：

- **预测精度**：通过时序模型学习季节性、趋势性和周期性模式，预测准确率可达90%以上
- **全局优化**：在多租户、多业务场景下实现资源的全局最优分配
- **持续进化**：系统随运行时间不断积累数据，预测能力持续增强

---

## 二、系统架构设计

### 2.1 整体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                     AI 容量规划与资源治理系统                          │
├──────────────────┬───────────────────┬──────────────────┬────────────┤
│   数据采集层      │     AI分析层       │   决策治理层      │   执行层    │
├──────────────────┼───────────────────┼──────────────────┼────────────┤
│ • Prometheus     │ • 时序预测模型     │ • 容量规划引擎    │ • 资源分配  │
│ • Node Exporter  │ • 业务模式识别     │ • 成本优化器      │ • 弹性伸缩  │
│ • 应用指标       │ • 异常检测         │ • 治理策略引擎    │ • 配置更新  │
│ • 业务API数据    │ • 增长趋势分析     │ • 预算管控        │ • 告警通知  │
├──────────────────┴───────────────────┴──────────────────┴────────────┤
│                          数据存储层                                  │
│  • Prometheus TSDB (短期指标) • TimescaleDB (长期趋势) • Redis (缓存)  │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
[指标采集] → [特征工程] → [模型推理] → [决策生成] → [执行反馈] → [模型更新]
    ↑                                                              │
    └────────────────────── 闭环学习 ←──────────────────────────────┘
```

---

## 三、数据采集与特征工程

### 3.1 监控体系搭建

```yaml
# docker-compose.capacity.yaml
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    container_name: capacity-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
      - ./rules:/etc/prometheus/rules
    restart: unless-stopped

  node-exporter:
    image: prom/node-exporter:latest
    container_name: capacity-node-exporter
    ports:
      - "9100:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)'
    restart: unless-stopped

  cadvisor:
    image: gcr.io/cadvisor/cadvisor:latest
    container_name: capacity-cadvisor
    ports:
      - "8080:8080"
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:ro
      - /sys:/sys:ro
      - /var/lib/docker/:/var/lib/docker:ro
    restart: unless-stopped

  timescaledb:
    image: timescale/timescaledb:latest-pg16
    container_name: capacity-timescaledb
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD:-capacity_pass}
      POSTGRES_DB: capacity_planning
    volumes:
      - timescale-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped

  prom2tsdb:
    image: prom2tsdb:v1
    container_name: capacity-prom2tsdb
    command:
      - '--source=http://prometheus:9090'
      - '--destination=postgres://postgres:capacity_pass@timescaledb:5432/capacity_planning'
      - '--retention=720h'
      - '--interval=5m'
    depends_on:
      - prometheus
      - timescaledb
    restart: unless-stopped

volumes:
  prometheus-data:
  timescale-data:
```

### 3.2 Prometheus配置

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  scrape_timeout: 10s

rule_files:
  - rules/capacity_rules.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']
    metrics_path: /metrics
    params:
      mount_namespace[1000]: []

  - job_name: 'cadvisor'
    static_configs:
      - targets: ['cadvisor:8080']
    metrics_path: /metrics
    relabel_configs:
      - source_labels: [__meta_consul_service_metadata_project]
        target_label: project

  - job_name: 'application'
    static_configs:
      - targets: ['app-exporter:9101']
    metrics_path: /metrics

  # 自定义业务指标
  - job_name: 'business'
    metrics_path: /metrics
    static_configs:
      - targets: ['business-metrics:8888']
```

### 3.3 特征工程

AI模型的输入特征需要精心构造：

```python
# features.py
"""容量规划特征工程模块"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import requests

class CapacityFeatures:
    """容量规划特征提取器"""

    def __init__(self, prometheus_url="http://localhost:9090"):
        self.prom_url = prometheus_url

    def fetch_metrics(self, query, start=None, end=None, step="60s"):
        """从Prometheus获取指标数据"""
        params = {
            'query': query,
            'start': (start or datetime.now() - timedelta(hours=24)).isoformat(),
            'end': (end or datetime.now()).isoformat(),
            'step': step
        }
        resp = requests.get(f"{self.prom_url}/api/v1/query_range", params=params)
        return resp.json()['data']['result']

    def extract_cpu_features(self, hours=24, step='5m') -> dict:
        """提取CPU相关特征"""
        # 基础指标
        cpu_idle = self.fetch_metrics(
            '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
        )

        features = {
            'cpu_mean': [],
            'cpu_std': [],
            'cpu_p95': [],
            'cpu_p99': [],
            'cpu_max': [],
            'cpu_min': [],
            # 时间特征
            'hour_of_day': [],
            'day_of_week': [],
            'is_weekend': [],
            'is_business_hours': [],
        }

        for series in cpu_idle[0].get('values', []):
            ts, value = series
            features['cpu_mean'].append(100 - float(value))

        if features['cpu_mean']:
            arr = np.array(features['cpu_mean'])
            features.update({
                'cpu_mean': [float(arr.mean())],
                'cpu_std': [float(arr.std())],
                'cpu_p95': [float(np.percentile(arr, 95))],
                'cpu_p99': [float(np.percentile(arr, 99))],
                'cpu_max': [float(arr.max())],
                'cpu_min': [float(arr.min())],
            })

        # 时间特征
        now = datetime.now()
        features['hour_of_day'] = [now.hour]
        features['day_of_week'] = [now.weekday()]
        features['is_weekend'] = [1 if now.weekday() >= 5 else 0]
        features['is_business_hours'] = [1 if 9 <= now.hour <= 18 and now.weekday() < 5 else 0]

        return features

    def extract_memory_features(self, hours=24) -> dict:
        """提取内存使用特征"""
        mem_features = {
            'mem_mean': [],
            'mem_std': [],
            'mem_p95': [],
            'mem_max': [],
        }
        # 类似CPU的特征提取逻辑...
        return mem_features

    def extract_business_features(self) -> dict:
        """提取业务相关特征"""
        # 调用业务API获取实时业务指标
        business_features = {}
        try:
            resp = requests.get('http://business-metrics:8888/summary', timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                business_features.update({
                    'active_users': data.get('active_users', 0),
                    'requests_per_minute': data.get('rpm', 0),
                    'error_rate': data.get('error_rate', 0),
                    'avg_response_time_ms': data.get('avg_response_time_ms', 0),
                })
        except Exception as e:
            print(f"获取业务指标失败: {e}")
        return business_features

    def build_feature_vector(self, target_hours_ahead: int = 24) -> dict:
        """构建完整的特征向量"""
        features = self.extract_cpu_features()
        features.update(self.extract_memory_features())
        features.update(self.extract_business_features())
        features['forecast_horizon_hours'] = target_hours_ahead
        return features
```

---

## 四、AI预测模型

### 4.1 预测模型选择

针对VPS容量规划，我们采用**多层级预测策略**：

| 预测粒度 | 模型选择 | 适用场景 |
|---------|---------|---------|
| 短期（1h内）| ARIMA / Prophet | 实时监控和紧急扩容 |
| 中期（1~7天）| LSTM / GRU | 日常容量规划 |
| 长期（1周+）| Prophet + 趋势分解 | 资源采购决策 |

### 4.2 Prophet时序预测

```python
# prophet_forecaster.py
"""基于Prophet的容量预测模型"""
from prophet import Prophet
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

class CapacityProphetForecaster:
    """使用Prophet进行容量预测"""

    def __init__(self, history_days=30, growth_factor=1.0):
        self.history_days = history_days
        self.growth_factor = growth_factor
        self.models = {}
        self.metrics_history = {}

    def train_cpu_model(self, prometheus_url="http://localhost:9090"):
        """训练CPU使用率预测模型"""
        # 获取历史数据
        start = datetime.now() - timedelta(days=self.history_days)
        end = datetime.now()
        df = self._fetch_from_prometheus(prometheus_url, start, end)

        if df.empty or len(df) < 48:
            raise ValueError("历史数据不足，至少需要48个数据点")

        # 模型训练
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=True,
            interval_width=0.95,
        )
        model.add_regressor('is_weekend', mode='additive')
        model.add_regressor('is_business_hours', mode='additive')
        model.add_regressor('growth_trend', mode='additive')

        # 准备训练数据
        train_df = df[['ds', 'y', 'is_weekend', 'is_business_hours', 'growth_trend']].copy()
        model.fit(train_df)

        # 保存模型和训练数据
        self.models['cpu'] = model
        self.metrics_history['cpu'] = df

        return model

    def train_memory_model(self, prometheus_url="http://localhost:9090"):
        """训练内存使用率预测模型"""
        start = datetime.now() - timedelta(days=self.history_days)
        df = self._fetch_from_prometheus(prometheus_url, start, datetime.now())

        if df.empty or len(df) < 48:
            raise ValueError("历史数据不足")

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            interval_width=0.95,
        )
        model.fit(df)
        self.models['memory'] = model
        self.metrics_history['memory'] = df
        return model

    def predict(self, metric='cpu', hours_ahead=24):
        """执行预测"""
        if metric not in self.models:
            raise ValueError(f"未训练 {metric} 模型，请先调用 train_{metric}_model()")

        model = self.models[metric]
        future = model.make_future_dataframe(periods=hours_ahead * 4)  # 15分钟粒度

        # 添加外部回归量
        future['is_weekend'] = future['ds'].dt.dayofweek.isin([5, 6]).astype(int)
        future['is_business_hours'] = (
            (future['ds'].dt.hour.between(9, 18)) &
            (~future['ds'].dt.dayofweek.isin([5, 6]))
        ).astype(int)
        future['growth_trend'] = np.linspace(0, self.growth_factor, len(future))

        forecast = model.predict(future)

        # 提取预测结果
        result = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(hours_ahead * 4)
        return {
            'predictions': result,
            'current_value': self.metrics_history[metric]['y'].iloc[-1] if metric in self.metrics_history else None,
            'peak_predicted': float(result['yhat'].max()),
            'peak_time': result.loc[result['yhat'].idxmax(), 'ds'],
            'confidence_interval': {
                'lower': float(result['yhat_lower'].min()),
                'upper': float(result['yhat_upper'].max())
            }
        }

    def _fetch_from_prometheus(self, url, start, end):
        """从Prometheus获取指标数据并转为Prophet格式"""
        import requests
        query = (
            '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
        )
        params = {
            'query': query,
            'start': start.isoformat(),
            'end': end.isoformat(),
            'step': '60s'
        }
        resp = requests.get(f"{url}/api/v1/query_range", params=params)
        data = resp.json()['data']['result']

        if not data:
            return pd.DataFrame(columns=['ds', 'y'])

        # 取第一个序列的平均值
        values = []
        for ts_str, val_str in data[0]['values']:
            values.append({
                'ds': pd.Timestamp(ts_str),
                'y': float(val_str)
            })

        df = pd.DataFrame(values)
        if df.empty:
            return df

        # 填充缺失值
        df = df.set_index('ds').resample('15T').mean().interpolate().reset_index()
        return df
```

### 4.3 异常检测

```python
# anomaly_detector.py
"""基于统计和ML的容量异常检测"""
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import pandas as pd

class CapacityAnomalyDetector:
    """容量异常检测器"""

    def __init__(self, contamination=0.05, window_size=24):
        self.contamination = contamination
        self.window_size = window_size
        self.scaler = StandardScaler()
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100
        )
        self.baseline = None

    def fit_baseline(self, historical_data: pd.DataFrame):
        """使用历史数据建立基线"""
        feature_cols = ['cpu_mean', 'cpu_std', 'mem_mean', 'mem_max',
                        'disk_io_mean', 'network_rx_mean']
        X = historical_data[feature_cols].values
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)
        self.baseline = {
            'features': feature_cols,
            'scaler_mean': self.scaler.mean_,
            'scaler_scale': self.scaler.scale_
        }
        print(f"✓ 基线模型已建立，使用 {len(historical_data)} 条历史记录")

    def detect(self, current_features: dict) -> dict:
        """检测当前状态是否异常"""
        if self.baseline is None:
            return {'is_anomaly': False, 'confidence': 0, 'reason': 'no_baseline'}

        feature_cols = self.baseline['features']
        X = np.array([[current_features.get(f, 0) for f in feature_cols]])
        X_scaled = self.scaler.transform(X)

        prediction = self.model.predict(X_scaled)[0]
        score = self.model.score_samples(X_scaled)[0]

        anomalies = []
        if prediction == -1:  # 异常
            # 分析具体哪个指标异常
            for i, col in enumerate(feature_cols):
                if current_features.get(col, 0) > self.baseline['scaler_mean'][i] + 2 * self.baseline['scaler_scale'][i]:
                    anomalies.append(col)

        return {
            'is_anomaly': prediction == -1,
            'anomaly_score': float(-score),  # 分数越高越异常
            'confidence': min(abs(score) * 2, 1.0),
            'anomalies': anomalies,
            'recommendation': self._get_recommendation(anomalies)
        }

    def _get_recommendation(self, anomalies: list) -> str:
        """根据异常类型给出建议"""
        recommendations = {
            'cpu_mean': 'CPU使用率异常升高，建议检查负载来源并考虑扩容',
            'mem_mean': '内存使用率异常，可能存在内存泄漏，建议监控并扩容',
            'disk_io_mean': '磁盘I/O异常，建议检查I/O瓶颈',
            'network_rx_mean': '网络流量异常，可能存在突发流量或攻击'
        }
        return '; '.join(recommendations.get(a, a) for a in anomalies) if anomalies else '系统运行正常'
```

---

## 五、容量规划引擎

### 5.1 核心规划逻辑

```python
# capacity_planner.py
"""AI容量规划引擎"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

class CapacityPlanner:
    """容量规划引擎"""

    def __init__(self, config: dict):
        self.config = config
        self.safety_margin = config.get('safety_margin', 0.2)  # 安全边际20%
        self.min_headroom = config.get('min_headroom', 0.15)   # 最小预留15%
        self.max_concurrent_changes = config.get('max_concurrent_changes', 2)
        self.cooldown_seconds = config.get('cooldown_seconds', 300)

    def plan(self, forecasts: Dict[str, dict], current_capacity: dict) -> dict:
        """执行容量规划"""
        plan = {
            'timestamp': datetime.now().isoformat(),
            'actions': [],
            'warnings': [],
            'summary': {}
        }

        # 分析CPU需求
        cpu_forecast = forecasts.get('cpu', {})
        cpu_plan = self._plan_cpu(cpu_forecast, current_capacity)
        plan['actions'].extend(cpu_plan['actions'])
        plan['warnings'].extend(cpu_plan['warnings'])

        # 分析内存需求
        mem_forecast = forecasts.get('memory', {})
        mem_plan = self._plan_memory(mem_forecast, current_capacity)
        plan['actions'].extend(mem_plan['actions'])
        plan['warnings'].extend(mem_plan['warnings'])

        # 综合分析
        plan['summary'] = self._summarize(plan)

        return plan

    def _plan_cpu(self, forecast: dict, capacity: dict) -> dict:
        """CPU容量规划"""
        result = {'actions': [], 'warnings': []}

        current_cpu = forecast.get('current_value', 0)
        peak_cpu = forecast.get('peak_predicted', current_cpu)
        peak_time = forecast.get('peak_time', 'unknown')
        current_capacity_units = capacity.get('cpu_cores', 4)

        # 计算所需容量
        required_capacity = peak_cpu / (100 * (1 - self.safety_margin)) * current_capacity_units
        required_capacity = max(required_capacity, current_capacity_units * (1 + self.min_headroom))
        required_capacity = int(np.ceil(required_capacity))

        if required_capacity > current_capacity_units:
            increase = required_capacity - current_capacity_units
            result['actions'].append({
                'type': 'scale_up',
                'resource': 'cpu',
                'from': current_capacity_units,
                'to': required_capacity,
                'increase_by': increase,
                'reason': f'预测峰值CPU {peak_cpu:.1f}%，需要 {required_capacity} 核',
                'peak_at': peak_time,
                'urgency': 'high' if increase >= 2 else 'medium',
                'estimated_cost_impact': self._estimate_cost_increase('cpu', increase)
            })
        elif current_cpu > 80:
            result['warnings'].append({
                'type': 'high_utilization',
                'resource': 'cpu',
                'current': current_cpu,
                'message': f'当前CPU使用率 {current_cpu:.1f}% 偏高，建议考虑扩容'
            })

        return result

    def _plan_memory(self, forecast: dict, capacity: dict) -> dict:
        """内存容量规划"""
        result = {'actions': [], 'warnings': []}

        current_mem = forecast.get('current_value', 0)
        peak_mem = forecast.get('peak_predicted', current_mem)
        current_capacity_gb = capacity.get('memory_gb', 8)

        required_gb = peak_mem / (100 * (1 - self.safety_margin)) * current_capacity_gb
        required_gb = max(required_gb, current_capacity_gb * (1 + self.min_headroom))
        required_gb = int(np.ceil(required_gb))

        # 标准内存规格
        standard_sizes = [2, 4, 8, 16, 32, 64]
        next_size = next((s for s in standard_sizes if s >= required_gb), standard_sizes[-1] * 2)

        if next_size > current_capacity_gb:
            result['actions'].append({
                'type': 'scale_up',
                'resource': 'memory',
                'from': current_capacity_gb,
                'to': next_size,
                'increase_by_gb': next_size - current_capacity_gb,
                'reason': f'预测峰值内存 {peak_mem:.1f}%，需要 {next_size}GB',
                'urgency': 'high' if next_size > current_capacity_gb * 2 else 'medium'
            })

        return result

    def _estimate_cost_increase(self, resource: str, increase: int) -> dict:
        """估算成本影响"""
        # 简化估算，实际应对接云厂商API
        pricing = {
            'cpu': {'per_core_month': 15.0, 'currency': 'USD'},
            'memory': {'per_gb_month': 2.0, 'currency': 'USD'}
        }
        if resource in pricing:
            p = pricing[resource]
            return {
                'additional_monthly_cost': increase * p['per_core_month'],
                'currency': p['currency'],
                'note': '估算值，实际价格请参考云厂商定价'
            }
        return {}

    def _summarize(self, plan: dict) -> dict:
        """生成规划摘要"""
        actions = plan.get('actions', [])
        scale_ups = [a for a in actions if a.get('type') == 'scale_up']
        high_urgency = [a for a in scale_ups if a.get('urgency') == 'high']

        return {
            'total_actions': len(actions),
            'scale_ups_required': len(scale_ups),
            'high_urgency_actions': len(high_urgency),
            'estimated_cost_increase': sum(
                a.get('estimated_cost_impact', {}).get('additional_monthly_cost', 0)
                for a in scale_ups
                if 'estimated_cost_impact' in a
            ),
            'status': 'critical' if high_urgency else ('warning' if scale_ups else 'normal')
        }
```

### 5.2 资源治理策略

```python
# resource_governor.py
"""资源治理策略引擎"""
import json
import time
from datetime import datetime
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class ResourceGovernor:
    """资源治理策略引擎"""

    def __init__(self, policy_config: dict):
        self.policies = policy_config.get('policies', [])
        self.effective_policies = self._parse_policies(policy_config)
        self.quota_manager = QuotaManager(policy_config.get('quotas', {}))
        self.cost_tracker = CostTracker(policy_config.get('budget', {}))

    def _parse_policies(self, config: dict) -> List[dict]:
        """解析治理策略"""
        policies = []
        for policy in config.get('policies', []):
            policies.append({
                'name': policy.get('name'),
                'condition': policy.get('condition'),
                'action': policy.get('action'),
                'priority': policy.get('priority', 0),
                'active': policy.get('active', True)
            })
        policies.sort(key=lambda x: x['priority'], reverse=True)
        return policies

    def evaluate(self, system_state: dict) -> dict:
        """评估当前系统状态并执行治理策略"""
        decisions = []
        for policy in self.effective_policies:
            if not policy['active']:
                continue

            if self._evaluate_condition(policy['condition'], system_state):
                decision = self._apply_action(policy['action'], system_state)
                decisions.append(decision)
                logger.info(f"治理策略执行: {policy['name']} -> {decision}")

        return {
            'timestamp': datetime.now().isoformat(),
            'decisions': decisions,
            'quota_status': self.quota_manager.get_status(),
            'budget_status': self.cost_tracker.get_status()
        }

    def _evaluate_condition(self, condition: dict, state: dict) -> bool:
        """评估策略条件"""
        metric = condition.get('metric')
        operator = condition.get('operator', 'gt')
        threshold = condition.get('threshold')

        if metric not in state:
            return False

        current_value = state[metric]
        if operator == 'gt':
            return current_value > threshold
        elif operator == 'lt':
            return current_value < threshold
        elif operator == 'gte':
            return current_value >= threshold
        elif operator == 'lte':
            return current_value <= threshold
        return False

    def _apply_action(self, action: dict, state: dict) -> dict:
        """执行治理动作"""
        action_type = action.get('type')
        result = {
            'action_type': action_type,
            'triggered_at': datetime.now().isoformat()
        }

        if action_type == 'notify':
            result['message'] = action.get('message', '系统通知')
            result['channel'] = action.get('channel', 'webhook')

        elif action_type == 'throttle':
            result['throttle_percent'] = action.get('percent', 50)
            result['message'] = f"已启用流量限速，限制 {action.get('percent', 50)}%"

        elif action_type == 'auto_scale':
            result['direction'] = action.get('direction', 'up')
            result['scale_factor'] = action.get('factor', 1.5)
            result['message'] = f"已触发自动扩容，缩放因子 {action.get('factor', 1.5)}"

        elif action_type == 'cost_alert':
            result['current_spend'] = state.get('current_spend', 0)
            result['budget_limit'] = action.get('budget_limit')
            result['message'] = f"成本预警: 当前花费 ${result['current_spend']:.2f}，预算上限 ${action.get('budget_limit', 0):.2f}"

        return result


class QuotaManager:
    """配额管理器"""

    def __init__(self, quotas: dict):
        self.quotas = quotas
        self.usage = {}

    def check_quota(self, resource: str, requested: float) -> dict:
        """检查配额是否充足"""
        if resource not in self.quotas:
            return {'allowed': True, 'reason': 'no_quota_configured'}

        quota = self.quotas[resource]
        current_usage = self.usage.get(resource, 0)
        remaining = quota['limit'] - current_usage

        allowed = requested <= remaining
        return {
            'allowed': allowed,
            'requested': requested,
            'remaining': remaining,
            'limit': quota['limit'],
            'usage_percent': (current_usage / quota['limit']) * 100 if quota['limit'] > 0 else 0
        }

    def get_status(self) -> dict:
        """获取配额状态"""
        status = {}
        for resource, quota in self.quotas.items():
            usage = self.usage.get(resource, 0)
            status[resource] = {
                'used': usage,
                'limit': quota['limit'],
                'remaining': quota['limit'] - usage,
                'utilization_percent': (usage / quota['limit']) * 100 if quota['limit'] > 0 else 0
            }
        return status


class CostTracker:
    """成本跟踪器"""

    def __init__(self, budget_config: dict):
        self.budget = budget_config.get('monthly_limit', 1000)
        self.currency = budget_config.get('currency', 'USD')
        self.daily_spend = budget_config.get('daily_spend', 0)
        self.budget_date = budget_config.get('budget_date', datetime.now().day)

    def get_status(self) -> dict:
        """获取预算状态"""
        now = datetime.now()
        days_in_month = now.days_in_month if hasattr(now, 'days_in_month') else 30
        days_elapsed = now.day
        projected_spend = self.daily_spend * days_in_month

        return {
            'budget_limit': self.budget,
            'projected_spend': round(projected_spend, 2),
            'daily_spend': self.daily_spend,
            'remaining': max(0, self.budget - projected_spend),
            'utilization_percent': round((projected_spend / self.budget) * 100, 1) if self.budget > 0 else 0,
            'currency': self.currency,
            'alert_threshold': self.budget * 0.8,
            'at_risk': projected_spend > self.budget * 0.8
        }

    def record_spend(self, amount: float):
        """记录支出"""
        self.daily_spend += amount / 30  # 分摊到每日
```

---

## 六、自动执行与闭环

### 6.1 主控制循环

```python
# capacity_controller.py
"""容量规划主控制器"""
import time
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Optional
import requests

from prophet_forecaster import CapacityProphetForecaster
from anomaly_detector import CapacityAnomalyDetector
from capacity_planner import CapacityPlanner
from resource_governor import ResourceGovernor

logger = logging.getLogger(__name__)

class CapacityController:
    """容量规划主控制器"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.forecaster = CapacityProphetForecaster(
            history_days=self.config.get('forecast', {}).get('history_days', 30)
        )
        self.anomaly_detector = CapacityAnomalyDetector(
            contamination=self.config.get('anomaly', {}).get('contamination', 0.05)
        )
        self.planner = CapacityPlanner(self.config.get('planner', {}))
        self.governor = ResourceGovernor(self.config.get('governor', {}))

        self.last_scale_time = 0
        self.scaling_cooldown = self.config.get('planner', {}).get('cooldown_seconds', 300)

        # 初始化基线
        self._init_baseline()

    def _load_config(self, path: str) -> dict:
        """加载配置"""
        try:
            with open(path, 'r') as f:
                import yaml
                return yaml.safe_load(f)
        except Exception:
            # 默认配置
            return {
                'forecast': {'history_days': 30},
                'anomaly': {'contamination': 0.05},
                'planner': {'safety_margin': 0.2, 'min_headroom': 0.15, 'cooldown_seconds': 300},
                'governor': {
                    'policies': [],
                    'quotas': {},
                    'budget': {'monthly_limit': 1000, 'currency': 'USD'}
                }
            }

    def _init_baseline(self):
        """初始化异常检测基线"""
        try:
            # 加载历史数据建立基线
            start = datetime.now() - timedelta(days=30)
            df = self.forecaster._fetch_from_prometheus("http://localhost:9090", start, datetime.now())
            if not df.empty:
                feature_df = pd.DataFrame({
                    'cpu_mean': df['y'].rolling(window=12, min_periods=1).mean().values,
                    'cpu_std': df['y'].rolling(window=12, min_periods=1).std().values,
                    'mem_mean': [0.0] * len(df),  # 需要从Prometheus获取内存数据
                    'mem_max': [0.0] * len(df),
                })
                self.anomaly_detector.fit_baseline(feature_df)
        except Exception as e:
            logger.warning(f"初始化基线失败: {e}")

    def run_cycle(self) -> Dict:
        """执行一次完整的容量规划周期"""
        cycle_start = time.time()
        result = {
            'cycle_time': datetime.now().isoformat(),
            'forecast': {},
            'anomaly_check': {},
            'plan': {},
            'governance': {},
            'actions_taken': []
        }

        try:
            # 1. 预测
            logger.info("开始容量预测...")
            cpu_forecast = self.forecaster.predict('cpu', hours_ahead=24)
            mem_forecast = self.forecaster.predict('memory', hours_ahead=24)
            result['forecast'] = {
                'cpu': {'peak': cpu_forecast['peak_predicted'], 'time': str(cpu_forecast['peak_time'])},
                'memory': {'peak': mem_forecast['peak_predicted'], 'time': str(mem_forecast['peak_time'])}
            }

            # 2. 异常检测
            current_features = self.forecaster._fetch_from_prometheus(
                "http://localhost:9090",
                datetime.now() - timedelta(hours=1),
                datetime.now()
            )
            # 构建当前特征向量
            import pandas as pd
            if current_features and current_features[0].get('values'):
                latest = current_features[0]['values'][-1]
                current_cpu = float(latest[1])
                anomaly_result = self.anomaly_detector.detect({
                    'cpu_mean': current_cpu,
                    'cpu_std': 0,
                    'mem_mean': 0,
                    'mem_max': 0,
                    'disk_io_mean': 0,
                    'network_rx_mean': 0
                })
                result['anomaly_check'] = anomaly_result

            # 3. 容量规划
            current_capacity = {
                'cpu_cores': self._get_current_cpu_cores(),
                'memory_gb': self._get_current_memory_gb()
            }
            forecast_dict = {'cpu': cpu_forecast, 'memory': mem_forecast}
            plan = self.planner.plan(forecast_dict, current_capacity)
            result['plan'] = plan

            # 4. 资源治理
            system_state = {
                'cpu_mean': current_cpu,
                'current_spend': self._get_current_spend(),
                'budget_limit': 1000
            }
            governance_result = self.governor.evaluate(system_state)
            result['governance'] = governance_result

            # 5. 执行决策
            actions_taken = self._execute_decisions(plan, governance_result)
            result['actions_taken'] = actions_taken

            # 6. 记录结果
            cycle_time = time.time() - cycle_start
            result['cycle_duration_seconds'] = round(cycle_time, 2)
            logger.info(f"容量规划周期完成，耗时 {cycle_time:.2f}s")

        except Exception as e:
            logger.error(f"容量规划周期出错: {e}", exc_info=True)
            result['error'] = str(e)

        return result

    def _execute_decisions(self, plan: dict, governance: dict) -> List[dict]:
        """执行规划决策"""
        actions = []
        now = time.time()

        for action in plan.get('actions', []):
            if action.get('type') == 'scale_up':
                # 检查冷却时间
                if now - self.last_scale_time < self.scaling_cooldown:
                    logger.warning(f"跳过扩容: 冷却期未结束 ({self.scaling_cooldown}s)")
                    continue

                if action.get('urgency') == 'high' or self._can_auto_execute(action):
                    action_result = self._execute_scale_up(action)
                    if action_result:
                        actions.append(action_result)
                        self.last_scale_time = now
                else:
                    actions.append({
                        'action': action,
                        'status': 'pending_approval',
                        'reason': '需要人工确认'
                    })
            elif action.get('type') == 'notify':
                self._send_notification(action)
                actions.append({'action': action, 'status': 'executed'})

        # 处理治理决策
        for decision in governance.get('decisions', []):
            if decision.get('action_type') in ['notify', 'cost_alert']:
                self._send_notification(decision)
                actions.append({'action': decision, 'status': 'executed'})

        return actions

    def _can_auto_execute(self, action: dict) -> bool:
        """判断是否可自动执行"""
        # 低风险操作可自动执行
        return action.get('urgency') != 'high' and action.get('type') == 'scale_up'

    def _execute_scale_up(self, action: dict) -> Optional[dict]:
        """执行扩容操作"""
        resource = action.get('resource')
        target = action.get('to')
        logger.info(f"执行扩容: {resource} -> {target}")

        try:
            # 在实际环境中，这里会调用云厂商API或K8s API
            # 演示：记录执行结果
            return {
                'action': action,
                'status': 'executed',
                'executed_at': datetime.now().isoformat(),
                'note': '实际部署需对接云厂商API'
            }
        except Exception as e:
            logger.error(f"扩容执行失败: {e}")
            return {
                'action': action,
                'status': 'failed',
                'error': str(e)
            }

    def _send_notification(self, notification: dict):
        """发送通知"""
        webhook_url = self.config.get('notifications', {}).get('webhook_url')
        if not webhook_url:
            logger.warning("未配置通知webhook，跳过发送")
            return

        try:
            payload = {
                'type': 'capacity_alert',
                'timestamp': datetime.now().isoformat(),
                'data': notification
            }
            requests.post(webhook_url, json=payload, timeout=10)
            logger.info("通知发送成功")
        except Exception as e:
            logger.error(f"通知发送失败: {e}")

    def _get_current_cpu_cores(self) -> int:
        """获取当前CPU核数"""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                content = f.read()
                return content.count('processor')
        except Exception:
            return 4  # 默认值

    def _get_current_memory_gb(self) -> int:
        """获取当前内存大小"""
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal'):
                        kb = int(line.split()[1])
                        return max(1, kb // 1048576)
        except Exception:
            return 8  # 默认值

    def _get_current_spend(self) -> float:
        """获取当前支出"""
        # 实际应用中需要从账单API获取
        return 50.0

    def run_daemon(self, interval: int = 300):
        """以守护进程方式运行"""
        logger.info(f"容量规划守护进程启动，间隔 {interval}秒")
        while True:
            try:
                result = self.run_cycle()
                # 保存结果
                with open(f"/var/log/capacity-plan-{datetime.now().strftime('%Y%m%d')}.json", 'w') as f:
                    json.dump(result, f, indent=2, default=str)
            except Exception as e:
                logger.error(f"周期执行出错: {e}", exc_info=True)
            time.sleep(interval)


if __name__ == '__main__':
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='AI容量规划控制器')
    parser.add_argument('--config', default='config.yaml', help='配置文件路径')
    parser.add_argument('--once', action='store_true', help='执行一次后退出')
    parser.add_argument('--interval', type=int, default=300, help='运行间隔（秒）')
    args = parser.parse_args()

    controller = CapacityController(args.config)

    if args.once:
        result = controller.run_cycle()
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0)
    else:
        controller.run_daemon(args.interval)
```

### 6.2 配置文件

```yaml
# config.yaml
forecast:
  history_days: 30
  prediction_hours: 24
  retrain_days: 7

anomaly:
  contamination: 0.05
  window_size: 24

planner:
  safety_margin: 0.2
  min_headroom: 0.15
  cooldown_seconds: 300
  max_concurrent_changes: 2
  auto_execute_safe: true

notifications:
  webhook_url: "https://hooks.example.com/capacity-alerts"
  channels:
    - slack
    - webhook

quotas:
  cpu:
    limit: 64
    unit: "cores"
  memory:
    limit: 128
    unit: "GB"

governor:
  policies:
    - name: "cost_budget_alert"
      condition:
        metric: "current_spend"
        operator: "gt"
        threshold: 800
      action:
        type: "cost_alert"
        budget_limit: 1000
      priority: 1
      active: true
    - name: "cpu_high_warning"
      condition:
        metric: "cpu_mean"
        operator: "gt"
        threshold: 85
      action:
        type: "notify"
        message: "CPU使用率超过85%，建议扩容"
        channel: "webhook"
      priority: 2
      active: true
    - name: "traffic_throttle"
      condition:
        metric: "cpu_mean"
        operator: "gt"
        threshold: 95
      action:
        type: "throttle"
        percent: 50
        message: "CPU严重过载，启用50%流量限速"
      priority: 3
      active: true

  budget:
    monthly_limit: 1000
    currency: "USD"
    daily_spend: 35.0
```

---

## 七、集成部署

### 7.1 完整Docker部署

```yaml
# docker-compose.full.yaml
version: '3.8'
services:
  # 监控层
  prometheus:
    image: prom/prometheus:latest
    container_name: ai-capacity-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./rules:/etc/prometheus/rules
      - prom-data:/prometheus
    restart: unless-stopped

  node-exporter:
    image: prom/node-exporter:latest
    container_name: ai-capacity-node-exporter
    ports:
      - "9100:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command: ['--path.procfs=/host/proc', '--path.sysfs=/host/sys']
    restart: unless-stopped

  cadvisor:
    image: gcr.io/cadvisor/cadvisor:latest
    container_name: ai-capacity-cadvisor
    ports:
      - "8080:8080"
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:ro
      - /sys:/sys:ro
      - /var/lib/docker/:/var/lib/docker:ro
    restart: unless-stopped

  grafana:
    image: grafana/grafana-oss:latest
    container_name: ai-capacity-grafana
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
      GF_INSTALL_PLUGINS: grafana-clock-panel
    volumes:
      - grafana-data:/var/lib/grafana
      - ./dashboards:/etc/grafana/provisioning/dashboards
    depends_on:
      - prometheus
    restart: unless-stopped

  # AI分析层
  capacity-planner:
    build:
      context: .
      dockerfile: Dockerfile.planner
    container_name: ai-capacity-planner
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./prophet_models:/app/models
      - /var/log:/var/log
    environment:
      - PROMETHEUS_URL=http://prometheus:9090
      - WEBHOOK_URL=${WEBHOOK_URL:-}
    depends_on:
      - prometheus
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  # 长期存储
  timescaledb:
    image: timescale/timescaledb:latest-pg16
    container_name: ai-capacity-timescaledb
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD:-capacity_secure_pass}
      POSTGRES_DB: capacity_planning
    volumes:
      - tsdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped

volumes:
  prom-data:
  grafana-data:
  tsdata:
```

```dockerfile
# Dockerfile.planner
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.planner.txt .
RUN pip install --no-cache-dir -r requirements.planner.txt

COPY . .

RUN mkdir -p /app/models /var/log

CMD ["python", "capacity_controller.py", "--config", "config.yaml", "--interval", "300"]
```

```txt
# requirements.planner.txt
prophet>=1.1.5
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
requests>=2.31.0
pyyaml>=6.0
prometheus-api-client>=0.5.0
```

---

## 八、实战效果与运维建议

### 8.1 关键指标

部署AI容量规划系统后，建议关注以下核心指标：

| 指标 | 目标值 | 说明 |
|------|-------|------|
| 预测准确率 | > 85% | 实际值与预测值的偏差在15%以内 |
| 扩容响应时间 | < 5分钟 | 从识别需求到资源就绪的时间 |
| 资源闲置率 | < 15% | 未被有效利用的资源比例 |
| 误报率 | < 10% | 错误触发扩容/告警的比例 |
| 成本节省 | 15%~30% | 相比传统规划方式的成本降低 |

### 8.2 运维最佳实践

1. **数据质量优先**：确保监控数据采集的完整性和准确性，这是AI模型的基础
2. **渐进式部署**：先从只读模式开始，验证预测准确性后再开启自动执行
3. **定期重训练**：每1~2周重新训练模型，适应业务变化
4. **人工审核机制**：高风险操作（如大幅扩容）保留人工确认环节
5. **备份基线**：保留至少30天的历史数据用于模型训练和回溯分析
6. **成本核算**：建立实时成本跟踪，确保AI优化带来的收益不被超额支出抵消

---

## 总结

AI驱动的VPS智能容量规划与资源治理系统，通过**预测模型**、**治理策略**和**自动执行**三层的协同工作，实现了从"被动救火"到"主动规划"的根本转变。核心要点：

1. **采集**：全面的监控数据是AI能力的基础
2. **预测**：Prophet等多层级模型覆盖不同时间尺度的规划需求
3. **决策**：基于预测结果的智能容量规划和资源治理策略
4. **执行**：安全可控的自动执行与人工审核相结合
5. **闭环**：持续学习机制让系统越用越智能

这套系统不仅节省了运维人力，更重要的是通过精准的资源规划，显著降低了基础设施成本，同时保障了业务的稳定运行。
