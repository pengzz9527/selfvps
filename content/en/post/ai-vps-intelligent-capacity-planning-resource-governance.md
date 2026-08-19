---
title: "AI-Driven VPS Intelligent Capacity Planning & Resource Governance"
description: "Traditional VPS capacity planning relies on manual experience, often lagging behind business growth. This article introduces how to build an AI-driven VPS intelligent capacity planning and resource governance system, achieving the transition from reactive to proactive planning."
date: 2026-08-19T21:00:00+08:00
lastmod: 2026-08-19T21:00:00+08:00
slug: "ai-vps-intelligent-capacity-planning-resource-governance"
tags: ["AI", "VPS", "capacity planning", "resource governance", "predictive analytics", "Auto Scaling", "cost optimization", "Docker", "Prometheus"]
categories: ["AI+VPS"]
draft: false
image: /images/posts/ai-vps-intelligent-capacity-planning-resource-governance/featured.png
---

## Introduction

Capacity planning has always been a core challenge in VPS operations. The traditional approach relies on the administrator's experience—reserving 30%~50% buffer resources based on historical traffic peaks. This approach has two fundamental flaws: **resource waste** (excess resources sit idle during off-peak hours) and **capacity shortage** (insufficient response when business surges).

The maturity of AI technology is changing this landscape. **AI-driven VPS intelligent capacity planning and resource governance** systems continuously learn business patterns, predict future demands, and dynamically optimize resource allocation—achieving a transformation from "reactive firefighting" to "proactive planning."

This article systematically introduces how to build a complete AI capacity planning and resource governance system.

---

## 1. Core Challenges of AI Capacity Planning

### 1.1 Three Pain Points of Traditional Planning

| Pain Point | Traditional Approach | Consequence |
|-----------|---------------------|-------------|
| Capacity Estimation | Historical peak + fixed ratio | 20%~40% waste during off-peak, still insufficient during peaks |
| Scaling Decision | Manual judgment, reactive | Response delay, degraded user experience |
| Resource Allocation | Static allocation, long-term fixed | Cannot adapt to business fluctuations and growth |

### 1.2 Unique Value of AI Solutions

The core value of AI capacity planning systems lies in three dimensions:

- **Prediction Accuracy**: Time series models learn seasonality, trends, and cyclical patterns, achieving over 90% prediction accuracy
- **Global Optimization**: Achieve globally optimal resource allocation across multi-tenant, multi-service scenarios
- **Continuous Evolution**: The system accumulates data over time, continuously enhancing its prediction capabilities

---

## 2. System Architecture Design

### 2.1 Overall Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                  AI Capacity Planning & Resource Governance System   │
├──────────────────┬───────────────────┬──────────────────┬────────────┤
│  Data Collection │    AI Analysis    │  Decision &      │  Execution │
│      Layer       │      Layer        │  Governance Layer│   Layer    │
├──────────────────┼───────────────────┼──────────────────┼────────────┤
│ • Prometheus     │ • Time series     │ • Capacity       │ • Resource │
│ • Node Exporter  │   forecasting     │   planning       │   allocation │
│ • Container      │ • Business        │ • Cost optimizer │ • Auto       │
│   metrics        │   pattern         │ • Governance     │   scaling    │
│ • Business API   │   recognition     │   policy engine  │ • Config     │
│                  │ • Anomaly         │ • Budget control │   update     │
│                  │   detection       │                  │ • Alert      │
├──────────────────┴───────────────────┴──────────────────┴────────────┤
│                          Data Storage Layer                          │
│  • Prometheus TSDB (short-term) • TimescaleDB (long-term) • Redis   │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
[Metric Collection] → [Feature Engineering] → [Model Inference] → [Decision Generation] → [Execution Feedback] → [Model Update]
    ↑                                                                           │
    └───────────────────── Closed-loop Learning ←───────────────────────────────┘
```

---

## 3. Data Collection & Feature Engineering

### 3.1 Monitoring Stack Setup

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

volumes:
  prometheus-data:
  timescale-data:
```

### 3.2 Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  scrape_timeout: 10s

rule_files:
  - rules/capacity_rules.yml

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']

  - job_name: 'cadvisor'
    static_configs:
      - targets: ['cadvisor:8080']

  - job_name: 'application'
    static_configs:
      - targets: ['app-exporter:9101']
```

### 3.3 Feature Engineering

Careful feature construction is essential for AI models:

```python
# features.py
"""Capacity planning feature engineering module"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import requests

class CapacityFeatures:
    """Capacity planning feature extractor"""

    def __init__(self, prometheus_url="http://localhost:9090"):
        self.prom_url = prometheus_url

    def extract_cpu_features(self, hours=24, step='5m') -> dict:
        """Extract CPU-related features"""
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

        now = datetime.now()
        features['hour_of_day'] = [now.hour]
        features['day_of_week'] = [now.weekday()]
        features['is_weekend'] = [1 if now.weekday() >= 5 else 0]
        features['is_business_hours'] = [1 if 9 <= now.hour <= 18 and now.weekday() < 5 else 0]

        return features

    def build_feature_vector(self, target_hours_ahead: int = 24) -> dict:
        """Build complete feature vector"""
        features = self.extract_cpu_features()
        features.update(self.extract_memory_features())
        features.update(self.extract_business_features())
        features['forecast_horizon_hours'] = target_hours_ahead
        return features

    def extract_memory_features(self, hours=24) -> dict:
        """Extract memory usage features"""
        return {
            'mem_mean': [0.0],
            'mem_std': [0.0],
            'mem_p95': [0.0],
            'mem_max': [0.0],
        }

    def extract_business_features(self) -> dict:
        """Extract business-related features"""
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
            print(f"Business metrics fetch failed: {e}")
        return business_features
```

---

## 4. AI Prediction Models

### 4.1 Model Selection Strategy

For VPS capacity planning, we adopt a **multi-level prediction strategy**:

| Prediction Granularity | Model | Use Case |
|----------------------|-------|----------|
| Short-term (within 1h) | ARIMA / Prophet | Real-time monitoring and emergency scaling |
| Medium-term (1~7 days) | LSTM / GRU | Daily capacity planning |
| Long-term (1 week+) | Prophet + trend decomposition | Resource procurement decisions |

### 4.2 Prophet Time Series Forecasting

```python
# prophet_forecaster.py
"""Capacity forecasting model based on Prophet"""
from prophet import Prophet
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests

class CapacityProphetForecaster:
    """Capacity forecasting using Prophet"""

    def __init__(self, history_days=30, growth_factor=1.0):
        self.history_days = history_days
        self.growth_factor = growth_factor
        self.models = {}
        self.metrics_history = {}

    def train_cpu_model(self, prometheus_url="http://localhost:9090"):
        """Train CPU usage prediction model"""
        start = datetime.now() - timedelta(days=self.history_days)
        df = self._fetch_from_prometheus(prometheus_url, start, datetime.now())

        if df.empty or len(df) < 48:
            raise ValueError("Insufficient historical data, need at least 48 data points")

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=True,
            interval_width=0.95,
        )
        model.add_regressor('is_weekend', mode='additive')
        model.add_regressor('is_business_hours', mode='additive')
        model.add_regressor('growth_trend', mode='additive')

        train_df = df[['ds', 'y', 'is_weekend', 'is_business_hours', 'growth_trend']].copy()
        model.fit(train_df)

        self.models['cpu'] = model
        self.metrics_history['cpu'] = df
        return model

    def predict(self, metric='cpu', hours_ahead=24):
        """Execute prediction"""
        if metric not in self.models:
            raise ValueError(f"Model {metric} not trained, call train_{metric}_model() first")

        model = self.models[metric]
        future = model.make_future_dataframe(periods=hours_ahead * 4)

        future['is_weekend'] = future['ds'].dt.dayofweek.isin([5, 6]).astype(int)
        future['is_business_hours'] = (
            (future['ds'].dt.hour.between(9, 18)) &
            (~future['ds'].dt.dayofweek.isin([5, 6]))
        ).astype(int)
        future['growth_trend'] = np.linspace(0, self.growth_factor, len(future))

        forecast = model.predict(future)
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
        """Fetch metrics from Prometheus and convert to Prophet format"""
        query = ('100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)')
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

        values = []
        for ts_str, val_str in data[0]['values']:
            values.append({'ds': pd.Timestamp(ts_str), 'y': float(val_str)})

        df = pd.DataFrame(values)
        if df.empty:
            return df

        df = df.set_index('ds').resample('15T').mean().interpolate().reset_index()
        return df
```

### 4.3 Anomaly Detection

```python
# anomaly_detector.py
"""Statistical and ML-based capacity anomaly detection"""
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import pandas as pd

class CapacityAnomalyDetector:
    """Capacity anomaly detector"""

    def __init__(self, contamination=0.05, window_size=24):
        self.contamination = contamination
        self.scaler = StandardScaler()
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100
        )
        self.baseline = None

    def fit_baseline(self, historical_data: pd.DataFrame):
        """Build baseline using historical data"""
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
        print(f"✓ Baseline model established with {len(historical_data)} historical records")

    def detect(self, current_features: dict) -> dict:
        """Detect if current state is anomalous"""
        if self.baseline is None:
            return {'is_anomaly': False, 'confidence': 0, 'reason': 'no_baseline'}

        feature_cols = self.baseline['features']
        X = np.array([[current_features.get(f, 0) for f in feature_cols]])
        X_scaled = self.scaler.transform(X)

        prediction = self.model.predict(X_scaled)[0]
        score = self.model.score_samples(X_scaled)[0]

        anomalies = []
        if prediction == -1:
            for i, col in enumerate(feature_cols):
                if current_features.get(col, 0) > self.baseline['scaler_mean'][i] + 2 * self.baseline['scaler_scale'][i]:
                    anomalies.append(col)

        return {
            'is_anomaly': prediction == -1,
            'anomaly_score': float(-score),
            'confidence': min(abs(score) * 2, 1.0),
            'anomalies': anomalies,
            'recommendation': self._get_recommendation(anomalies)
        }

    def _get_recommendation(self, anomalies: list) -> str:
        recommendations = {
            'cpu_mean': 'CPU usage abnormally high, check load sources and consider scaling',
            'mem_mean': 'Memory usage abnormal, possible memory leak, monitor and scale',
            'disk_io_mean': 'Disk I/O abnormal, check I/O bottlenecks',
            'network_rx_mean': 'Network traffic abnormal, possible traffic spike or attack'
        }
        return '; '.join(recommendations.get(a, a) for a in anomalies) if anomalies else 'System operating normally'
```

---

## 5. Capacity Planning Engine

### 5.1 Core Planning Logic

```python
# capacity_planner.py
"""AI capacity planning engine"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import numpy as np

logger = logging.getLogger(__name__)

class CapacityPlanner:
    """Capacity planning engine"""

    def __init__(self, config: dict):
        self.config = config
        self.safety_margin = config.get('safety_margin', 0.2)
        self.min_headroom = config.get('min_headroom', 0.15)
        self.max_concurrent_changes = config.get('max_concurrent_changes', 2)

    def plan(self, forecasts: Dict[str, dict], current_capacity: dict) -> dict:
        """Execute capacity planning"""
        plan = {
            'timestamp': datetime.now().isoformat(),
            'actions': [],
            'warnings': [],
            'summary': {}
        }

        cpu_forecast = forecasts.get('cpu', {})
        cpu_plan = self._plan_cpu(cpu_forecast, current_capacity)
        plan['actions'].extend(cpu_plan['actions'])
        plan['warnings'].extend(cpu_plan['warnings'])

        mem_forecast = forecasts.get('memory', {})
        mem_plan = self._plan_memory(mem_forecast, current_capacity)
        plan['actions'].extend(mem_plan['actions'])
        plan['warnings'].extend(mem_plan['warnings'])

        plan['summary'] = self._summarize(plan)
        return plan

    def _plan_cpu(self, forecast: dict, capacity: dict) -> dict:
        """CPU capacity planning"""
        result = {'actions': [], 'warnings': []}

        current_cpu = forecast.get('current_value', 0)
        peak_cpu = forecast.get('peak_predicted', current_cpu)
        peak_time = forecast.get('peak_time', 'unknown')
        current_capacity_units = capacity.get('cpu_cores', 4)

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
                'reason': f'Predicted peak CPU {peak_cpu:.1f}%, need {required_capacity} cores',
                'peak_at': peak_time,
                'urgency': 'high' if increase >= 2 else 'medium'
            })
        elif current_cpu > 80:
            result['warnings'].append({
                'type': 'high_utilization',
                'resource': 'cpu',
                'current': current_cpu,
                'message': f'Current CPU usage {current_cpu:.1f}% is high, consider scaling up'
            })

        return result

    def _plan_memory(self, forecast: dict, capacity: dict) -> dict:
        """Memory capacity planning"""
        result = {'actions': [], 'warnings': []}

        current_mem = forecast.get('current_value', 0)
        peak_mem = forecast.get('peak_predicted', current_mem)
        current_capacity_gb = capacity.get('memory_gb', 8)

        required_gb = peak_mem / (100 * (1 - self.safety_margin)) * current_capacity_gb
        required_gb = max(required_gb, current_capacity_gb * (1 + self.min_headroom))
        required_gb = int(np.ceil(required_gb))

        standard_sizes = [2, 4, 8, 16, 32, 64]
        next_size = next((s for s in standard_sizes if s >= required_gb), standard_sizes[-1] * 2)

        if next_size > current_capacity_gb:
            result['actions'].append({
                'type': 'scale_up',
                'resource': 'memory',
                'from': current_capacity_gb,
                'to': next_size,
                'increase_by_gb': next_size - current_capacity_gb,
                'reason': f'Predicted peak memory {peak_mem:.1f}%, need {next_size}GB',
                'urgency': 'high' if next_size > current_capacity_gb * 2 else 'medium'
            })

        return result

    def _summarize(self, plan: dict) -> dict:
        """Generate planning summary"""
        actions = plan.get('actions', [])
        scale_ups = [a for a in actions if a.get('type') == 'scale_up']
        high_urgency = [a for a in scale_ups if a.get('urgency') == 'high']

        return {
            'total_actions': len(actions),
            'scale_ups_required': len(scale_ups),
            'high_urgency_actions': len(high_urgency),
            'status': 'critical' if high_urgency else ('warning' if scale_ups else 'normal')
        }
```

### 5.2 Resource Governance Strategy

```python
# resource_governor.py
"""Resource governance policy engine"""
import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)

class ResourceGovernor:
    """Resource governance policy engine"""

    def __init__(self, policy_config: dict):
        self.policies = policy_config.get('policies', [])
        self.effective_policies = self._parse_policies(policy_config)
        self.quota_manager = QuotaManager(policy_config.get('quotas', {}))
        self.cost_tracker = CostTracker(policy_config.get('budget', {}))

    def _parse_policies(self, config: dict) -> List[dict]:
        """Parse governance policies"""
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
        """Evaluate system state and execute governance policies"""
        decisions = []
        for policy in self.effective_policies:
            if not policy['active']:
                continue

            if self._evaluate_condition(policy['condition'], system_state):
                decision = self._apply_action(policy['action'], system_state)
                decisions.append(decision)
                logger.info(f"Governance policy: {policy['name']} -> {decision}")

        return {
            'timestamp': datetime.now().isoformat(),
            'decisions': decisions,
            'quota_status': self.quota_manager.get_status(),
            'budget_status': self.cost_tracker.get_status()
        }

    def _evaluate_condition(self, condition: dict, state: dict) -> bool:
        """Evaluate policy condition"""
        metric = condition.get('metric')
        operator = condition.get('operator', 'gt')
        threshold = condition.get('threshold')

        if metric not in state:
            return False

        current_value = state[metric]
        operators = {'gt': lambda a, b: a > b, 'lt': lambda a, b: a < b,
                     'gte': lambda a, b: a >= b, 'lte': lambda a, b: a <= b}
        return operators.get(operator, operators['gt'])(current_value, threshold)

    def _apply_action(self, action: dict, state: dict) -> dict:
        """Apply governance action"""
        action_type = action.get('type')
        result = {'action_type': action_type, 'triggered_at': datetime.now().isoformat()}

        if action_type == 'notify':
            result['message'] = action.get('message', 'System notification')
            result['channel'] = action.get('channel', 'webhook')
        elif action_type == 'throttle':
            result['throttle_percent'] = action.get('percent', 50)
            result['message'] = f"Traffic throttled to {action.get('percent', 50)}%"
        elif action_type == 'auto_scale':
            result['direction'] = action.get('direction', 'up')
            result['scale_factor'] = action.get('factor', 1.5)
        elif action_type == 'cost_alert':
            result['current_spend'] = state.get('current_spend', 0)
            result['budget_limit'] = action.get('budget_limit')

        return result


class QuotaManager:
    """Quota manager"""

    def __init__(self, quotas: dict):
        self.quotas = quotas
        self.usage = {}

    def get_status(self) -> dict:
        """Get quota status"""
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
    """Cost tracker"""

    def __init__(self, budget_config: dict):
        self.budget = budget_config.get('monthly_limit', 1000)
        self.currency = budget_config.get('currency', 'USD')
        self.daily_spend = budget_config.get('daily_spend', 0)

    def get_status(self) -> dict:
        """Get budget status"""
        now = datetime.now()
        days_in_month = now.days_in_month if hasattr(now, 'days_in_month') else 30
        projected_spend = self.daily_spend * days_in_month

        return {
            'budget_limit': self.budget,
            'projected_spend': round(projected_spend, 2),
            'daily_spend': self.daily_spend,
            'remaining': max(0, self.budget - projected_spend),
            'utilization_percent': round((projected_spend / self.budget) * 100, 1) if self.budget > 0 else 0,
            'currency': self.currency,
            'at_risk': projected_spend > self.budget * 0.8
        }
```

---

## 6. Automated Execution & Closed Loop

### 6.1 Main Control Loop

```python
# capacity_controller.py
"""Capacity planning main controller"""
import time
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List
import requests

from prophet_forecaster import CapacityProphetForecaster
from anomaly_detector import CapacityAnomalyDetector
from capacity_planner import CapacityPlanner
from resource_governor import ResourceGovernor

logger = logging.getLogger(__name__)

class CapacityController:
    """Capacity planning main controller"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.forecaster = CapacityProphetForecaster(
            history_days=self.config.get('forecast', {}).get('history_days', 30)
        )
        self.anomaly_detector = CapacityAnomalyDetector()
        self.planner = CapacityPlanner(self.config.get('planner', {}))
        self.governor = ResourceGovernor(self.config.get('governor', {}))
        self.last_scale_time = 0
        self.scaling_cooldown = self.config.get('planner', {}).get('cooldown_seconds', 300)
        self._init_baseline()

    def run_cycle(self) -> Dict:
        """Execute a complete capacity planning cycle"""
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
            # 1. Forecast
            logger.info("Starting capacity forecasting...")
            cpu_forecast = self.forecaster.predict('cpu', hours_ahead=24)
            mem_forecast = self.forecaster.predict('memory', hours_ahead=24)
            result['forecast'] = {
                'cpu': {'peak': cpu_forecast['peak_predicted'], 'time': str(cpu_forecast['peak_time'])},
                'memory': {'peak': mem_forecast['peak_predicted'], 'time': str(mem_forecast['peak_time'])}
            }

            # 2. Anomaly detection
            anomaly_result = self.anomaly_detector.detect({
                'cpu_mean': cpu_forecast.get('current_value', 50),
                'cpu_std': 0, 'mem_mean': 0, 'mem_max': 0,
                'disk_io_mean': 0, 'network_rx_mean': 0
            })
            result['anomaly_check'] = anomaly_result

            # 3. Capacity planning
            current_capacity = {
                'cpu_cores': self._get_current_cpu_cores(),
                'memory_gb': self._get_current_memory_gb()
            }
            plan = self.planner.plan({'cpu': cpu_forecast, 'memory': mem_forecast}, current_capacity)
            result['plan'] = plan

            # 4. Resource governance
            system_state = {
                'cpu_mean': anomaly_result.get('anomaly_score', 0.5) * 100,
                'current_spend': self._get_current_spend(),
                'budget_limit': 1000
            }
            governance_result = self.governor.evaluate(system_state)
            result['governance'] = governance_result

            # 5. Execute decisions
            actions_taken = self._execute_decisions(plan, governance_result)
            result['actions_taken'] = actions_taken

            cycle_time = time.time() - cycle_start
            result['cycle_duration_seconds'] = round(cycle_time, 2)
            logger.info(f"Capacity planning cycle completed in {cycle_time:.2f}s")

        except Exception as e:
            logger.error(f"Capacity planning cycle error: {e}", exc_info=True)
            result['error'] = str(e)

        return result

    def _execute_decisions(self, plan: dict, governance: dict) -> List[dict]:
        """Execute planning decisions"""
        actions = []
        now = time.time()

        for action in plan.get('actions', []):
            if action.get('type') == 'scale_up':
                if now - self.last_scale_time < self.scaling_cooldown:
                    logger.warning(f"Skipping scale-up: cooldown period active")
                    continue

                if self._can_auto_execute(action):
                    action_result = self._execute_scale_up(action)
                    if action_result:
                        actions.append(action_result)
                        self.last_scale_time = now
                else:
                    actions.append({
                        'action': action,
                        'status': 'pending_approval',
                        'reason': 'Requires manual confirmation'
                    })

        for decision in governance.get('decisions', []):
            if decision.get('action_type') in ['notify', 'cost_alert']:
                self._send_notification(decision)
                actions.append({'action': decision, 'status': 'executed'})

        return actions

    def _execute_scale_up(self, action: dict) -> Optional[dict]:
        """Execute scale-up operation"""
        resource = action.get('resource')
        target = action.get('to')
        logger.info(f"Executing scale-up: {resource} -> {target}")

        return {
            'action': action,
            'status': 'executed',
            'executed_at': datetime.now().isoformat(),
            'note': 'In production, this calls cloud provider API'
        }

    def _send_notification(self, notification: dict):
        """Send notification"""
        webhook_url = self.config.get('notifications', {}).get('webhook_url')
        if not webhook_url:
            logger.warning("No notification webhook configured")
            return
        try:
            requests.post(webhook_url, json={
                'type': 'capacity_alert',
                'timestamp': datetime.now().isoformat(),
                'data': notification
            }, timeout=10)
        except Exception as e:
            logger.error(f"Notification failed: {e}")

    def _get_current_cpu_cores(self) -> int:
        try:
            with open('/proc/cpuinfo', 'r') as f:
                return sum(1 for line in f if line.startswith('processor'))
        except Exception:
            return 4

    def _get_current_memory_gb(self) -> int:
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal'):
                        return max(1, int(line.split()[1]) // 1048576)
        except Exception:
            return 8

    def _get_current_spend(self) -> float:
        return 50.0

    def run_daemon(self, interval: int = 300):
        """Run as daemon"""
        logger.info(f"Capacity planning daemon started, interval {interval}s")
        while True:
            try:
                result = self.run_cycle()
                with open(f"/var/log/capacity-plan-{datetime.now().strftime('%Y%m%d')}.json", 'w') as f:
                    json.dump(result, f, indent=2, default=str)
            except Exception as e:
                logger.error(f"Cycle execution error: {e}", exc_info=True)
            time.sleep(interval)


if __name__ == '__main__':
    import argparse
    import sys
    parser = argparse.ArgumentParser(description='AI Capacity Planning Controller')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--interval', type=int, default=300)
    args = parser.parse_args()

    controller = CapacityController(args.config)
    if args.once:
        result = controller.run_cycle()
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0)
    else:
        controller.run_daemon(args.interval)
```

### 6.2 Configuration

```yaml
# config.yaml
forecast:
  history_days: 30
  prediction_hours: 24
  retrain_days: 7

anomaly:
  contamination: 0.05

planner:
  safety_margin: 0.2
  min_headroom: 0.15
  cooldown_seconds: 300
  max_concurrent_changes: 2

notifications:
  webhook_url: "https://hooks.example.com/capacity-alerts"

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
        message: "CPU usage exceeds 85%, consider scaling up"
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
      priority: 3
      active: true

  budget:
    monthly_limit: 1000
    currency: "USD"
    daily_spend: 35.0
```

---

## 7. Full Docker Deployment

```yaml
# docker-compose.full.yaml
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    container_name: ai-capacity-prometheus
    ports: ["9090:9090"]
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./rules:/etc/prometheus/rules
      - prom-data:/prometheus
    restart: unless-stopped

  node-exporter:
    image: prom/node-exporter:latest
    container_name: ai-capacity-node-exporter
    ports: ["9100:9100"]
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    restart: unless-stopped

  cadvisor:
    image: gcr.io/cadvisor/cadvisor:latest
    container_name: ai-capacity-cadvisor
    ports: ["8080:8080"]
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:ro
      - /sys:/sys:ro
      - /var/lib/docker/:/var/lib/docker:ro
    restart: unless-stopped

  grafana:
    image: grafana/grafana-oss:latest
    container_name: ai-capacity-grafana
    ports: ["3000:3000"]
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
    volumes:
      - grafana-data:/var/lib/grafana
      - ./dashboards:/etc/grafana/provisioning/dashboards
    depends_on: [prometheus]
    restart: unless-stopped

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
    depends_on: [prometheus]
    restart: unless-stopped

  timescaledb:
    image: timescale/timescaledb:latest-pg16
    container_name: ai-capacity-timescaledb
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD:-capacity_secure_pass}
      POSTGRES_DB: capacity_planning
    volumes:
      - tsdata:/var/lib/postgresql/data
    ports: ["5432:5432"]
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
RUN apt-get update && apt-get install -y gcc g++ && rm -rf /var/lib/apt/lists/*
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
```

---

## 8. Key Metrics & Best Practices

### 8.1 Key Performance Indicators

| Metric | Target | Description |
|--------|--------|-------------|
| Prediction Accuracy | > 85% | Deviation between actual and predicted values within 15% |
| Scaling Response Time | < 5 min | Time from identifying need to resource readiness |
| Resource Idle Rate | < 15% | Proportion of unused resources |
| False Positive Rate | < 10% | Rate of incorrect scaling/alert triggers |
| Cost Savings | 15%~30% | Cost reduction compared to traditional planning |

### 8.2 Operational Best Practices

1. **Data Quality First**: Ensure completeness and accuracy of monitoring data collection—this is the foundation of AI capability
2. **Gradual Deployment**: Start in read-only mode, validate prediction accuracy before enabling automatic execution
3. **Regular Retraining**: Retrain models every 1~2 weeks to adapt to business changes
4. **Human Review Mechanism**: Retain manual confirmation for high-risk operations (e.g., significant scaling)
5. **Baseline Backup**: Preserve at least 30 days of historical data for model training and retrospective analysis
6. **Cost Accounting**: Establish real-time cost tracking to ensure AI optimization gains are not offset by overspending

---

## Summary

The AI-driven VPS intelligent capacity planning and resource governance system, through the coordinated work of **prediction models**, **governance policies**, and **automated execution** across three layers, achieves a fundamental transformation from "reactive firefighting" to "proactive planning." Key takeaways:

1. **Collection**: Comprehensive monitoring data is the foundation of AI capability
2. **Prediction**: Multi-level models (Prophet, etc.) cover planning needs across different time scales
3. **Decision**: Intelligent capacity planning and resource governance strategies based on predictions
4. **Execution**: Safe and controllable automatic execution combined with human review
5. **Closed Loop**: Continuous learning mechanism makes the system smarter over time

This system not only saves operational manpower but, more importantly, significantly reduces infrastructure costs through precise resource planning while ensuring stable business operations.
