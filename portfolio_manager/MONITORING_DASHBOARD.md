# Monitoring Dashboard Documentation

**Date:** November 29, 2025  
**Status:** Production Ready  
**Purpose:** Comprehensive guide for monitoring the High Availability (HA) trading system

---

## Table of Contents

1. [Overview](#overview)
2. [Available Metrics](#available-metrics)
3. [Alert Thresholds](#alert-thresholds)
4. [Grafana Dashboard Examples](#grafana-dashboard-examples)
5. [Prometheus Alert Rules](#prometheus-alert-rules)
6. [Visualization Best Practices](#visualization-best-practices)
7. [Integration Guide](#integration-guide)

---

## Overview

This document provides comprehensive guidance for monitoring the HA trading system using Grafana and Prometheus. The system exposes metrics via the `get_metrics()` method on `RedisCoordinator`, which returns a comprehensive dictionary of metrics and alert statuses.

**Critical Context for Trading Systems:**
- ₹50L capital at risk
- 5-15 signals/year (low frequency, high value)
- 2% risk per trade (₹1L per position)
- **Zero tolerance for duplicate signals** (2x financial risk)
- **Zero tolerance for missed signals** (lost trading opportunities)

---

## Available Metrics

### Metrics Endpoint

The `RedisCoordinator.get_metrics()` method returns a dictionary with the following structure:

```python
{
    # DB Sync Metrics
    'db_sync_success': int,              # Count of successful syncs
    'db_sync_failure': int,              # Count of failed syncs
    'db_sync_total': int,                # Total sync attempts
    'db_sync_failure_rate': float,       # Failure rate (0.0-1.0)
    'db_sync_avg_latency_ms': float,     # Average latency (rolling window)
    'db_sync_min_latency_ms': float,     # Minimum latency in window
    'db_sync_max_latency_ms': float,     # Maximum latency in window
    'db_sync_p50_latency_ms': float,     # Median latency (50th percentile)
    'db_sync_p95_latency_ms': float,     # 95th percentile latency
    'db_sync_p99_latency_ms': float,     # 99th percentile latency
    'db_sync_latency_samples': int,       # Number of samples in rolling window
    
    # Leadership Metrics
    'leadership_changes': int,            # Total leadership transitions
    'current_leader_redis': str,          # Current leader from Redis (or None)
    'current_leader_db': str,             # Current leader from DB (or None)
    'this_instance': str,                 # This instance's ID (UUID-PID format)
    'is_leader': bool,                    # Whether this instance is leader
    'heartbeat_running': bool,            # Whether heartbeat thread is running
    'fallback_mode': bool,                # Whether in DB-only fallback mode
    'last_heartbeat': str,                # ISO timestamp of last heartbeat (or None)
    
    # Alert Status
    'alerts': {
        'db_sync_failure_rate': {
            'status': 'OK' | 'WARNING' | 'CRITICAL',
            'value': float,
            'threshold_warning': float,
            'threshold_critical': float,
            'message': str
        },
        'leadership_changes': {
            'status': 'OK' | 'WARNING' | 'CRITICAL',
            'value': float,  # Changes per hour
            'threshold_warning': float,
            'threshold_critical': float,
            'message': str
        },
        'heartbeat_staleness': {
            'status': 'OK' | 'WARNING' | 'CRITICAL',
            'value': float | None,  # Seconds since last heartbeat
            'threshold_warning': float,
            'threshold_critical': float,
            'message': str
        },
        'overall_status': 'OK' | 'WARNING' | 'CRITICAL'
    },
    'overall_alert_status': 'OK' | 'WARNING' | 'CRITICAL'
}
```

### Metric Significance

#### DB Sync Metrics

**Purpose:** Monitor database synchronization health between Redis and PostgreSQL.

- **`db_sync_failure_rate`**: Critical for detecting split-brain scenarios
  - **>5%**: WARNING - Degraded DB connectivity, potential split-brain risk
  - **>10%**: CRITICAL - Serious DB issues, split-brain likely
  - **Financial Impact**: High failure rate → Split-brain → Duplicate signals → 2x financial risk

- **`db_sync_latency_ms` (p50, p95, p99)**: Performance monitoring
  - **p95 > 100ms**: Investigate DB performance
  - **p99 > 500ms**: Critical performance issue
  - **Financial Impact**: High latency → Delayed leadership updates → Race conditions

#### Leadership Metrics

**Purpose:** Monitor leader election and failover health.

- **`leadership_changes`**: Detects leadership flapping
  - **>3/hour**: WARNING - Leadership instability
  - **>10/hour**: CRITICAL - Severe instability, system may be unusable
  - **Financial Impact**: Flapping → Signal processing interruptions → Missed signals

- **`is_leader`**: Current leadership status
  - **False on all instances**: No leader → Background tasks not running
  - **True on multiple instances**: Split-brain → Duplicate signals

- **`current_leader_redis` vs `current_leader_db`**: Split-brain detection
  - **Mismatch**: Split-brain detected → Auto-demotion should trigger
  - **Financial Impact**: Split-brain → Duplicate signals → 2x financial risk

#### Heartbeat Metrics

**Purpose:** Monitor instance health and detect crashes.

- **`last_heartbeat`**: Instance health indicator
  - **>30s stale**: WARNING - Instance may be down
  - **>60s stale**: CRITICAL - Instance likely down
  - **Financial Impact**: Stale heartbeat → Stale leader → Missed signals

#### Crash Recovery Metrics

**Purpose:** Monitor database recovery performance and reliability.

- **`recovery_time_ms`**: Time to restore state from database
  - **<100ms**: Normal (1-10 positions)
  - **>500ms**: WARNING - Large position count or slow DB
  - **>2000ms**: CRITICAL - Database performance issue
  - **Financial Impact**: Slow recovery → Delayed signal processing → Missed entries

- **`recovery_success_count`**: Total successful recoveries
  - Increments on each successful startup recovery
  - Track recovery frequency (restarts/crashes)

- **`recovery_failure_count`**: Total failed recoveries
  - **>0**: Indicates persistent issues
  - Check error code distribution

- **`recovery_error_code`**: Last recovery error
  - **DB_UNAVAILABLE**: Database connection failed
  - **DATA_CORRUPT**: Invalid position data in DB
  - **VALIDATION_FAILED**: Risk/margin mismatch (>0.01₹)
  - **Financial Impact**: Failed recovery → Manual intervention → Trading halted

- **`positions_recovered`**: Number of positions restored
  - Tracks portfolio size at recovery
  - Expected: 0-50 positions (performance validated)

---

## Alert Thresholds

### Threshold Configuration

Alert thresholds are defined in `CoordinatorMetrics` class constants:

```python
DB_SYNC_FAILURE_RATE_WARNING = 0.05      # 5%
DB_SYNC_FAILURE_RATE_CRITICAL = 0.10     # 10%
LEADERSHIP_CHANGES_WARNING_PER_HOUR = 3
LEADERSHIP_CHANGES_CRITICAL_PER_HOUR = 10
HEARTBEAT_STALE_WARNING_SECONDS = 30
HEARTBEAT_STALE_CRITICAL_SECONDS = 60
```

### Alert Status Levels

- **OK**: Metric within normal range
- **WARNING**: Metric exceeds warning threshold (investigate)
- **CRITICAL**: Metric exceeds critical threshold (immediate action required)

### Alert Priority for Trading Systems

**CRITICAL Alerts (Immediate Action Required):**
1. `db_sync_failure_rate` > 10% → Split-brain risk → Duplicate signals
2. `leadership_changes` > 10/hour → System instability → Missed signals
3. `heartbeat_staleness` > 60s → Instance down → Missed signals
4. `overall_alert_status` = 'CRITICAL' → Any critical metric triggered

**WARNING Alerts (Investigate):**
1. `db_sync_failure_rate` > 5% → Degraded connectivity
2. `leadership_changes` > 3/hour → Leadership flapping
3. `heartbeat_staleness` > 30s → Instance may be down

---

## Grafana Dashboard Examples

### Dashboard Layout

**Recommended Panel Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│  HA Trading System - Leader Election & Coordination         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Overall      │  │ Current      │  │ Instance     │      │
│  │ Alert Status │  │ Leader       │  │ Status       │      │
│  │ (Stat)       │  │ (Stat)       │  │ (Stat)       │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ DB Sync Failure Rate (%)                              │  │
│  │ (Time Series - Line Graph)                            │  │
│  │ Threshold lines: 5% (WARNING), 10% (CRITICAL)        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ DB Sync Latency (ms) - p50, p95, p99                 │  │
│  │ (Time Series - Multi-line Graph)                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Leadership Changes per Hour                           │  │
│  │ (Time Series - Bar Chart)                             │  │
│  │ Threshold lines: 3/hour (WARNING), 10/hour (CRITICAL)│  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Heartbeat Staleness (seconds)                         │  │
│  │ (Time Series - Line Graph)                            │  │
│  │ Threshold lines: 30s (WARNING), 60s (CRITICAL)        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Leader Status Comparison (Redis vs DB)                 │  │
│  │ (Table)                                                │  │
│  │ Columns: Instance ID, Redis Leader, DB Leader, Match  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Instance Health Status                                │  │
│  │ (Table)                                                │  │
│  │ Columns: Instance ID, Is Leader, Heartbeat Running,   │  │
│  │          Last Heartbeat, Fallback Mode                │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Grafana Dashboard JSON

```json
{
  "dashboard": {
    "title": "HA Trading System - Leader Election & Coordination",
    "tags": ["trading", "ha", "redis", "postgresql"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "Overall Alert Status",
        "type": "stat",
        "targets": [
          {
            "expr": "portfolio_manager_overall_alert_status",
            "legendFormat": "{{instance}}"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "mappings": [
              {
                "options": {
                  "0": {
                    "text": "OK",
                    "color": "green"
                  },
                  "1": {
                    "text": "WARNING",
                    "color": "yellow"
                  },
                  "2": {
                    "text": "CRITICAL",
                    "color": "red"
                  }
                }
              }
            ],
            "thresholds": {
              "mode": "absolute",
              "steps": [
                { "value": 0, "color": "green" },
                { "value": 1, "color": "yellow" },
                { "value": 2, "color": "red" }
              ]
            }
          }
        },
        "gridPos": { "h": 4, "w": 6, "x": 0, "y": 0 }
      },
      {
        "id": 2,
        "title": "DB Sync Failure Rate (%)",
        "type": "timeseries",
        "targets": [
          {
            "expr": "portfolio_manager_db_sync_failure_rate * 100",
            "legendFormat": "{{instance}}"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "thresholds": {
              "mode": "absolute",
              "steps": [
                { "value": 0, "color": "green" },
                { "value": 5, "color": "yellow" },
                { "value": 10, "color": "red" }
              ]
            }
          }
        },
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 4 }
      },
      {
        "id": 3,
        "title": "DB Sync Latency (ms) - p50, p95, p99",
        "type": "timeseries",
        "targets": [
          {
            "expr": "portfolio_manager_db_sync_p50_latency_ms",
            "legendFormat": "p50 - {{instance}}"
          },
          {
            "expr": "portfolio_manager_db_sync_p95_latency_ms",
            "legendFormat": "p95 - {{instance}}"
          },
          {
            "expr": "portfolio_manager_db_sync_p99_latency_ms",
            "legendFormat": "p99 - {{instance}}"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "ms",
            "thresholds": {
              "mode": "absolute",
              "steps": [
                { "value": 0, "color": "green" },
                { "value": 100, "color": "yellow" },
                { "value": 500, "color": "red" }
              ]
            }
          }
        },
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 4 }
      },
      {
        "id": 4,
        "title": "Leadership Changes per Hour",
        "type": "timeseries",
        "targets": [
          {
            "expr": "rate(portfolio_manager_leadership_changes[1h]) * 3600",
            "legendFormat": "{{instance}}"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "short",
            "thresholds": {
              "mode": "absolute",
              "steps": [
                { "value": 0, "color": "green" },
                { "value": 3, "color": "yellow" },
                { "value": 10, "color": "red" }
              ]
            }
          }
        },
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 12 }
      },
      {
        "id": 5,
        "title": "Heartbeat Staleness (seconds)",
        "type": "timeseries",
        "targets": [
          {
            "expr": "time() - portfolio_manager_last_heartbeat_timestamp",
            "legendFormat": "{{instance}}"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "s",
            "thresholds": {
              "mode": "absolute",
              "steps": [
                { "value": 0, "color": "green" },
                { "value": 30, "color": "yellow" },
                { "value": 60, "color": "red" }
              ]
            }
          }
        },
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 12 }
      }
    ],
    "refresh": "10s",
    "time": {
      "from": "now-1h",
      "to": "now"
    }
  }
}
```

### Key Panels Explained

1. **Overall Alert Status (Stat Panel)**
   - Shows worst alert status across all metrics
   - Color-coded: Green (OK), Yellow (WARNING), Red (CRITICAL)
   - **Action**: Red = Immediate investigation required

2. **DB Sync Failure Rate (Time Series)**
   - Line graph showing failure rate over time
   - Threshold lines at 5% (WARNING) and 10% (CRITICAL)
   - **Action**: Spikes above 10% = Check DB connectivity, investigate split-brain

3. **DB Sync Latency (Time Series)**
   - Multi-line graph showing p50, p95, p99 percentiles
   - **Action**: p95 > 100ms = Investigate DB performance

4. **Leadership Changes per Hour (Time Series)**
   - Bar chart showing leadership change frequency
   - Threshold lines at 3/hour (WARNING) and 10/hour (CRITICAL)
   - **Action**: Spikes above 10/hour = System instability, investigate root cause

5. **Heartbeat Staleness (Time Series)**
   - Line graph showing seconds since last heartbeat
   - Threshold lines at 30s (WARNING) and 60s (CRITICAL)
   - **Action**: Staleness > 60s = Instance likely down, check instance health

---

## Prometheus Alert Rules

### Alert Rule Configuration

Create a file `portfolio_manager_alerts.yml`:

```yaml
groups:
  - name: portfolio_manager_ha
    interval: 30s
    rules:
      # CRITICAL: DB Sync Failure Rate > 10%
      - alert: HighDBSyncFailureRate
        expr: portfolio_manager_db_sync_failure_rate > 0.10
        for: 2m
        labels:
          severity: critical
          component: ha_coordination
        annotations:
          summary: "DB sync failure rate is {{ $value | humanizePercentage }}"
          description: |
            Instance {{ $labels.instance }} has DB sync failure rate of {{ $value | humanizePercentage }}.
            This indicates serious DB connectivity issues and potential split-brain scenarios.
            Financial Impact: Split-brain → Duplicate signals → 2x financial risk (₹1L per duplicate).
          runbook_url: "https://your-wiki/runbooks/high-db-sync-failure-rate"

      # WARNING: DB Sync Failure Rate > 5%
      - alert: ElevatedDBSyncFailureRate
        expr: portfolio_manager_db_sync_failure_rate > 0.05
        for: 5m
        labels:
          severity: warning
          component: ha_coordination
        annotations:
          summary: "DB sync failure rate is {{ $value | humanizePercentage }}"
          description: |
            Instance {{ $labels.instance }} has elevated DB sync failure rate of {{ $value | humanizePercentage }}.
            This indicates degraded DB connectivity. Investigate before it becomes critical.

      # CRITICAL: Leadership Changes > 10/hour
      - alert: ExcessiveLeadershipFlapping
        expr: rate(portfolio_manager_leadership_changes[1h]) * 3600 > 10
        for: 5m
        labels:
          severity: critical
          component: ha_coordination
        annotations:
          summary: "Leadership changed {{ $value | humanize }} times in the last hour"
          description: |
            Leadership is flapping excessively ({{ $value | humanize }} changes/hour).
            This indicates severe system instability.
            Financial Impact: Flapping → Signal processing interruptions → Missed signals.
          runbook_url: "https://your-wiki/runbooks/excessive-leadership-flapping"

      # WARNING: Leadership Changes > 3/hour
      - alert: LeadershipFlapping
        expr: rate(portfolio_manager_leadership_changes[1h]) * 3600 > 3
        for: 10m
        labels:
          severity: warning
          component: ha_coordination
        annotations:
          summary: "Leadership changed {{ $value | humanize }} times in the last hour"
          description: |
            Leadership is flapping ({{ $value | humanize }} changes/hour).
            This indicates system instability. Monitor closely.

      # CRITICAL: Heartbeat Staleness > 60s
      - alert: StaleHeartbeat
        expr: (time() - portfolio_manager_last_heartbeat_timestamp) > 60
        for: 1m
        labels:
          severity: critical
          component: ha_coordination
        annotations:
          summary: "Instance {{ $labels.instance }} heartbeat is {{ $value | humanizeDuration }} stale"
          description: |
            Instance {{ $labels.instance }} has not sent a heartbeat for {{ $value | humanizeDuration }}.
            The instance is likely down or network-partitioned.
            Financial Impact: Stale heartbeat → Stale leader → Missed signals.
          runbook_url: "https://your-wiki/runbooks/stale-heartbeat"

      # WARNING: Heartbeat Staleness > 30s
      - alert: DelayedHeartbeat
        expr: (time() - portfolio_manager_last_heartbeat_timestamp) > 30
        for: 2m
        labels:
          severity: warning
          component: ha_coordination
        annotations:
          summary: "Instance {{ $labels.instance }} heartbeat is {{ $value | humanizeDuration }} stale"
          description: |
            Instance {{ $labels.instance }} has not sent a heartbeat for {{ $value | humanizeDuration }}.
            The instance may be experiencing issues.

      # CRITICAL: Split-Brain Detected (Redis Leader != DB Leader)
      - alert: SplitBrainDetected
        expr: |
          portfolio_manager_current_leader_redis != portfolio_manager_current_leader_db
          and portfolio_manager_current_leader_redis != ""
          and portfolio_manager_current_leader_db != ""
        for: 1m
        labels:
          severity: critical
          component: ha_coordination
        annotations:
          summary: "Split-brain detected: Redis leader ({{ $labels.redis_leader }}) != DB leader ({{ $labels.db_leader }})"
          description: |
            Split-brain detected! Redis reports {{ $labels.redis_leader }} as leader,
            but PostgreSQL reports {{ $labels.db_leader }} as leader.
            Auto-demotion should trigger, but manual intervention may be required.
            Financial Impact: Split-brain → Duplicate signals → 2x financial risk (₹1L per duplicate).
          runbook_url: "https://your-wiki/runbooks/split-brain-detection"

      # CRITICAL: No Leader (All instances report no leader)
      - alert: NoLeader
        expr: |
          count(portfolio_manager_is_leader == 1) == 0
        for: 2m
        labels:
          severity: critical
          component: ha_coordination
        annotations:
          summary: "No leader instance detected"
          description: |
            No instance is currently the leader. Background tasks (rollover, cleanup) are not running.
            Financial Impact: No leader → Background tasks not running → Missed rollovers, stale data.
          runbook_url: "https://your-wiki/runbooks/no-leader"

      # WARNING: Multiple Leaders (Split-brain)
      - alert: MultipleLeaders
        expr: |
          count(portfolio_manager_is_leader == 1) > 1
        for: 1m
        labels:
          severity: critical
          component: ha_coordination
        annotations:
          summary: "Multiple leaders detected: {{ $value }} instances claim leadership"
          description: |
            {{ $value }} instances are reporting themselves as leader. This is a split-brain scenario.
            Auto-demotion should trigger, but manual intervention may be required.
            Financial Impact: Split-brain → Duplicate signals → 2x financial risk (₹1L per duplicate).
          runbook_url: "https://your-wiki/runbooks/multiple-leaders"

      # CRITICAL: Recovery Failed (DB_UNAVAILABLE)
      - alert: RecoveryFailed
        expr: |
          portfolio_manager_recovery_failure_count > 0
          and portfolio_manager_recovery_error_code == 1  # DB_UNAVAILABLE
        for: 30s
        labels:
          severity: critical
          component: crash_recovery
        annotations:
          summary: "Instance {{ $labels.instance }} recovery failed: DB_UNAVAILABLE"
          description: |
            Instance {{ $labels.instance }} cannot recover from database (DB_UNAVAILABLE).
            Trading is halted on this instance until database connectivity is restored.
            Financial Impact: Failed recovery → Trading halted → Missed signals.
          runbook_url: "https://your-wiki/runbooks/recovery-db-unavailable"

      # CRITICAL: Recovery Validation Failed
      - alert: RecoveryValidationFailed
        expr: |
          portfolio_manager_recovery_failure_count > 0
          and portfolio_manager_recovery_error_code == 3  # VALIDATION_FAILED
        for: 1m
        labels:
          severity: critical
          component: crash_recovery
        annotations:
          summary: "Instance {{ $labels.instance }} recovery validation failed"
          description: |
            Instance {{ $labels.instance }} recovered from database but validation failed (risk/margin mismatch).
            This indicates data inconsistency. Manual intervention required.
            Financial Impact: Validation failure → Trading halted → Manual investigation needed.
          runbook_url: "https://your-wiki/runbooks/recovery-validation-failed"

      # WARNING: Slow Recovery
      - alert: SlowRecovery
        expr: portfolio_manager_recovery_time_ms > 500
        for: 1m
        labels:
          severity: warning
          component: crash_recovery
        annotations:
          summary: "Instance {{ $labels.instance }} slow recovery: {{ $value }}ms"
          description: |
            Instance {{ $labels.instance }} took {{ $value }}ms to recover from database.
            Expected <100ms for normal position counts. Investigate database performance.
```

### Alert Severity Levels

**CRITICAL (Immediate Action Required):**
- High DB sync failure rate (>10%)
- Excessive leadership flapping (>10/hour)
- Stale heartbeat (>60s)
- Split-brain detected
- No leader
- Multiple leaders

**WARNING (Investigate):**
- Elevated DB sync failure rate (>5%)
- Leadership flapping (>3/hour)
- Delayed heartbeat (>30s)

### AlertManager Configuration

Configure AlertManager to route alerts to appropriate channels:

**Create `alertmanager.yml`:**

```yaml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'severity', 'component']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'team-trading'
  routes:
    # Critical alerts → PagerDuty (immediate response)
    - match:
        severity: critical
      receiver: 'pagerduty-critical'
      continue: true  # Also send to Slack

    # Critical alerts → Slack (visibility)
    - match:
        severity: critical
      receiver: 'slack-critical'

    # Warning alerts → Slack (investigation)
    - match:
        severity: warning
      receiver: 'slack-warnings'

receivers:
  # PagerDuty for CRITICAL alerts (24/7 on-call)
  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: '<your_pagerduty_service_key>'
        description: '{{ .GroupLabels.alertname }}: {{ .CommonAnnotations.summary }}'
        details:
          firing: '{{ .Alerts.Firing | len }}'
          resolved: '{{ .Alerts.Resolved | len }}'
          num_firing: '{{ .Alerts.Firing | len }}'
          num_resolved: '{{ .Alerts.Resolved | len }}'

  # Slack for CRITICAL alerts (team visibility)
  - name: 'slack-critical'
    slack_configs:
      - api_url: '<your_slack_webhook_url>'
        channel: '#trading-alerts-critical'
        title: '🚨 CRITICAL: {{ .GroupLabels.alertname }}'
        text: |
          {{ range .Alerts }}
          *Alert:* {{ .Labels.alertname }}
          *Summary:* {{ .Annotations.summary }}
          *Description:* {{ .Annotations.description }}
          *Runbook:* {{ .Annotations.runbook_url }}
          {{ end }}
        send_resolved: true

  # Slack for WARNING alerts
  - name: 'slack-warnings'
    slack_configs:
      - api_url: '<your_slack_webhook_url>'
        channel: '#trading-alerts-warnings'
        title: '⚠️ WARNING: {{ .GroupLabels.alertname }}'
        text: |
          {{ range .Alerts }}
          *Alert:* {{ .Labels.alertname }}
          *Summary:* {{ .Annotations.summary }}
          {{ end }}
        send_resolved: true

  # Default receiver (fallback)
  - name: 'team-trading'
    email_configs:
      - to: 'trading-team@your-company.com'
        headers:
          Subject: 'Portfolio Manager Alert: {{ .GroupLabels.alertname }}'

inhibit_rules:
  # Suppress WARNING if CRITICAL is firing for same metric
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'instance']
```

**Testing AlertManager Configuration:**

```bash
# Validate configuration
amtool check-config alertmanager.yml

# Test alert routing
amtool config routes test --config.file=alertmanager.yml \
  --tree \
  alertname=HighDBSyncFailureRate severity=critical
```

---

## Visualization Best Practices

### For Trading Systems

1. **Color Coding**
   - **Green**: Normal operation, no action needed
   - **Yellow**: Warning condition, investigate within 1 hour
   - **Red**: Critical condition, immediate action required

2. **Threshold Visualization**
   - Always show threshold lines on graphs (WARNING and CRITICAL)
   - Use shaded regions to indicate alert zones
   - Make thresholds clearly visible and labeled

3. **Time Windows**
   - **Short-term view**: Last 1 hour (for immediate issues)
   - **Medium-term view**: Last 24 hours (for trend analysis)
   - **Long-term view**: Last 7 days (for capacity planning)

4. **Financial Impact Indicators**
   - Add annotations showing financial impact of alerts
   - Example: "CRITICAL: Split-brain → Duplicate signals → ₹1L risk per duplicate"

5. **Instance Comparison**
   - Use tables to compare all instances side-by-side
   - Highlight discrepancies (e.g., Redis leader != DB leader)
   - Show instance health at a glance

6. **Alert Summary Panel**
   - Top-level panel showing overall system health
   - Color-coded by worst alert status
   - Click-through to detailed metrics

### Dashboard Refresh Rates

- **Real-time panels**: 10s refresh (for critical metrics)
- **Standard panels**: 30s refresh (for general monitoring)
- **Historical panels**: 1m refresh (for trend analysis)

### Panel Sizing

- **Critical metrics**: Large panels (12 columns wide)
- **Status indicators**: Small panels (4-6 columns wide)
- **Tables**: Full-width panels (24 columns wide)

---

## Integration Guide

### Step 1: Expose Metrics Endpoint

Add a metrics endpoint to your Flask application:

```python
from flask import Flask, jsonify
from core.redis_coordinator import RedisCoordinator

app = Flask(__name__)
coordinator = None  # Initialize in your app startup

@app.route('/coordinator/metrics', methods=['GET'])
def get_coordinator_metrics():
    """Expose coordinator metrics for Prometheus scraping"""
    if coordinator is None:
        return jsonify({'error': 'Coordinator not initialized'}), 503
    
    metrics = coordinator.get_metrics()
    return jsonify(metrics)
```

### Step 2: Prometheus Scraping Configuration

Add to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'portfolio_manager'
    scrape_interval: 30s
    metrics_path: '/coordinator/metrics'
    static_configs:
      - targets:
        - 'instance1:5000'
        - 'instance2:5000'
        - 'instance3:5000'
    relabel_configs:
      - source_labels: [__address__]
        target_label: instance
        regex: '([^:]+):.*'
        replacement: '${1}'
```

### Step 3: Prometheus Metrics Export

Convert JSON metrics to Prometheus format:

```python
from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Define Prometheus metrics
db_sync_failure_rate = Gauge(
    'portfolio_manager_db_sync_failure_rate',
    'DB sync failure rate (0.0-1.0)',
    ['instance']
)

db_sync_latency_p95 = Gauge(
    'portfolio_manager_db_sync_p95_latency_ms',
    'DB sync latency 95th percentile (ms)',
    ['instance']
)

leadership_changes = Counter(
    'portfolio_manager_leadership_changes',
    'Total leadership changes',
    ['instance']
)

overall_alert_status = Gauge(
    'portfolio_manager_overall_alert_status',
    'Overall alert status (0=OK, 1=WARNING, 2=CRITICAL)',
    ['instance']
)

@app.route('/metrics', methods=['GET'])
def prometheus_metrics():
    """Prometheus metrics endpoint"""
    if coordinator is None:
        return '', 503
    
    metrics = coordinator.get_metrics()
    instance_id = metrics['this_instance']
    
    # Update Prometheus metrics
    db_sync_failure_rate.labels(instance=instance_id).set(
        metrics['db_sync_failure_rate']
    )
    db_sync_latency_p95.labels(instance=instance_id).set(
        metrics['db_sync_p95_latency_ms']
    )
    overall_alert_status.labels(instance=instance_id).set(
        0 if metrics['overall_alert_status'] == 'OK' else
        1 if metrics['overall_alert_status'] == 'WARNING' else 2
    )
    
    return generate_latest()
```

### Step 4: Grafana Data Source

**Configure Prometheus as a data source in Grafana:**

1. **Navigate to Data Sources:**
   - In Grafana web UI, click the gear icon (⚙️) in the left sidebar
   - Select "Data sources"
   - Or navigate directly to: `http://your-grafana:3000/datasources`

2. **Add New Data Source:**
   - Click the blue "Add data source" button
   - Search for "Prometheus" in the search box
   - Click "Prometheus" from the list of data source types

3. **Configure Prometheus Connection:**

   **Basic Settings:**
   - **Name:** `Prometheus` (or `Portfolio-Manager-Prometheus`)
   - **Default:** Toggle ON (if this is your primary data source)

   **HTTP Settings:**
   - **URL:** `http://prometheus:9090`
     - If Prometheus is on a different host: `http://<prometheus-host>:9090`
     - If using SSL: `https://<prometheus-host>:9090`
   - **Access:** `Server (default)`
     - This means Grafana server accesses Prometheus directly
     - Use "Browser" only if Prometheus is accessible from user's browser

   **Auth Settings (Optional):**
   - Leave all auth toggles OFF if Prometheus has no authentication
   - If using basic auth:
     - Toggle "Basic auth" ON
     - Enter username and password

   **Scrape Interval:**
   - **Scrape interval:** `30s` (must match `prometheus.yml` scrape_interval)
   - **Query timeout:** `60s` (default is usually fine)

   **HTTP Method:**
   - **HTTP Method:** `POST` (recommended for complex queries)

4. **Save & Test:**
   - Scroll to the bottom of the page
   - Click "Save & test" button
   - **Expected Result:** Green checkmark with message:
     ```
     ✓ Data source is working
     ```

   **If Test Fails:**
   - **Error: "Post http://prometheus:9090/api/v1/query: dial tcp: lookup prometheus"**
     - **Fix:** Prometheus hostname is incorrect. Verify hostname/IP.

   - **Error: "Post http://prometheus:9090/api/v1/query: connect: connection refused"**
     - **Fix:** Prometheus is not running or port 9090 is not accessible.
     - Verify: `curl http://prometheus:9090/api/v1/query?query=up`

   - **Error: "Post http://prometheus:9090/api/v1/query: context deadline exceeded"**
     - **Fix:** Network latency too high or Prometheus overloaded.
     - Increase query timeout or check Prometheus health.

5. **Verify Metrics Availability:**
   - After successful connection, test that portfolio manager metrics are available
   - Click "Explore" (compass icon in left sidebar)
   - Select your Prometheus data source
   - In the query builder, start typing: `portfolio_manager_`
   - **Expected:** Autocomplete should show metrics like:
     - `portfolio_manager_db_sync_failure_rate`
     - `portfolio_manager_leadership_changes`
     - `portfolio_manager_is_leader`

   **If No Metrics Appear:**
   - Verify Prometheus is scraping your portfolio manager instances
   - Check Prometheus targets: `http://prometheus:9090/targets`
   - Verify your `/metrics` endpoint is working: `curl http://instance1:5000/metrics`

### Step 5: Import Dashboard

**Import the HA Trading System dashboard into Grafana:**

1. **Copy Dashboard JSON:**
   - Scroll up to the "Grafana Dashboard JSON" section (line 229-395)
   - Copy the entire JSON object (from `{` to `}`)
   - **Tip:** Use your editor's "copy code block" feature if available

2. **Navigate to Dashboard Import:**
   - In Grafana web UI, click the "+" icon in the left sidebar
   - Select "Import"
   - Or navigate directly to: `http://your-grafana:3000/dashboard/import`

3. **Import Dashboard:**
   - **Option A: Paste JSON**
     1. Paste the copied JSON into the "Import via panel json" text area
     2. Click "Load"

   - **Option B: Upload JSON File**
     1. Save the JSON to a file (e.g., `ha_trading_dashboard.json`)
     2. Click "Upload JSON file" button
     3. Select the file from your computer

4. **Configure Dashboard Settings:**
   - **Name:** `HA Trading System - Leader Election & Coordination` (default from JSON)
     - **Tip:** You can modify the name if needed (e.g., add environment prefix like "PROD - ...")

   - **Folder:** Select a folder to organize the dashboard
     - **Recommended:** Create a "Trading System" folder if it doesn't exist
     - Or use "General" for simple setups

   - **UID:** Auto-generated (leave as-is unless you have conflicts)

   - **Prometheus Data Source:** Select your Prometheus data source from the dropdown
     - This should be the data source you configured in Step 4
     - **IMPORTANT:** All panels will use this data source

5. **Import & Verify:**
   - Click the green "Import" button
   - **Expected Result:** Dashboard loads with all panels displaying data

   **Verification Checklist:**
   - [ ] "Overall Alert Status" panel shows OK/WARNING/CRITICAL status
   - [ ] "DB Sync Failure Rate (%)" graph shows time series data
   - [ ] "DB Sync Latency (ms)" graph shows p50, p95, p99 lines
   - [ ] "Leadership Changes per Hour" graph shows data
   - [ ] "Heartbeat Staleness (seconds)" graph shows data
   - [ ] All panels show data (not "No data")

   **If Panels Show "No Data":**
   - **Cause 1: No metrics available yet**
     - **Fix:** Wait for Prometheus to scrape metrics (30s interval)
     - Verify: `curl http://instance1:5000/metrics` returns data

   - **Cause 2: Wrong data source selected**
     - **Fix:** Click panel title → Edit → Query tab → Change data source

   - **Cause 3: Metrics not exposed**
     - **Fix:** Verify `/metrics` endpoint is implemented (see Step 3)
     - Check Prometheus targets are UP: `http://prometheus:9090/targets`

6. **Customize Dashboard (Optional):**
   - **Time Range:** Default is "Last 1 hour"
     - Change to "Last 24 hours" for trend analysis
     - Or use "Last 5 minutes" for real-time debugging

   - **Refresh Interval:** Default is "10s"
     - Change to "30s" for less frequent updates
     - Or "5s" for critical issue debugging

   - **Variables:** Add dashboard variables for multi-instance filtering
     - Click dashboard settings (gear icon in top-right)
     - Go to "Variables" tab
     - Add variable: `instance` with query: `label_values(portfolio_manager_is_leader, instance)`
     - Use in panels: Replace `instance` label with `$instance`

7. **Save Dashboard:**
   - Click the save icon (💾) in the top-right corner
   - Add a note describing the import (e.g., "Initial import - HA monitoring v1.0")
   - Click "Save"

8. **Set as Default (Optional):**
   - Click the star icon (⭐) next to the dashboard title to favorite it
   - Or set as home dashboard:
     - User menu → Preferences → Home Dashboard → Select this dashboard

### Step 6: Configure Alerting

1. In Prometheus: Add alert rules file to `prometheus.yml`:
   ```yaml
   rule_files:
     - 'portfolio_manager_alerts.yml'
   ```
2. Configure alertmanager for notifications (PagerDuty, Slack, etc.)
3. Test alerts by triggering conditions

---

## Example Queries

### Prometheus Queries

**DB Sync Failure Rate:**
```promql
portfolio_manager_db_sync_failure_rate
```

**DB Sync Latency p95:**
```promql
portfolio_manager_db_sync_p95_latency_ms
```

**Leadership Changes per Hour:**
```promql
rate(portfolio_manager_leadership_changes[1h]) * 3600
```

**Heartbeat Staleness:**
```promql
time() - portfolio_manager_last_heartbeat_timestamp
```

**Split-Brain Detection:**
```promql
portfolio_manager_current_leader_redis != portfolio_manager_current_leader_db
```

**No Leader:**
```promql
count(portfolio_manager_is_leader == 1) == 0
```

**Multiple Leaders:**
```promql
count(portfolio_manager_is_leader == 1) > 1
```

---

## Runbooks

### Runbook: High DB Sync Failure Rate

**Symptoms:**
- `db_sync_failure_rate` > 10%
- Alert: `HighDBSyncFailureRate`

**Impact:**
- Split-brain risk → Duplicate signals → 2x financial risk (₹1L per duplicate)

**Actions:**
1. Check PostgreSQL connectivity from all instances
2. Check network latency between instances and DB
3. Review PostgreSQL logs for connection errors
4. Verify database is not overloaded
5. Check for network partitions
6. If split-brain detected, verify auto-demotion is working

**Resolution:**
- Fix DB connectivity issues
- Verify split-brain detection and auto-demotion
- Monitor metrics until failure rate drops below 5%

### Runbook: Excessive Leadership Flapping

**Symptoms:**
- `leadership_changes` > 10/hour
- Alert: `ExcessiveLeadershipFlapping`

**Impact:**
- System instability → Signal processing interruptions → Missed signals

**Actions:**
1. Check Redis connectivity and latency
2. Check instance health (CPU, memory, network)
3. Review leader election logs
4. Check for network partitions
5. Verify heartbeat mechanism is working
6. Check for resource contention

**Resolution:**
- Fix root cause (network, resource, or configuration issue)
- Monitor metrics until flapping stops
- Consider increasing `LEADER_TTL` if network is slow

### Runbook: Split-Brain Detected

**Symptoms:**
- `current_leader_redis` != `current_leader_db`
- Alert: `SplitBrainDetected`

**Impact:**
- Duplicate signals → 2x financial risk (₹1L per duplicate)

**Actions:**
1. Verify auto-demotion is working (check logs for "Self-demoting due to split-brain")
2. Manually demote instances if auto-demotion failed
3. Check Redis and PostgreSQL connectivity
4. Verify network connectivity between instances
5. Review leadership history in database

**Resolution:**
- Auto-demotion should resolve automatically
- If not, manually release leadership on conflicting instances
- Monitor until split-brain is resolved
- Investigate root cause (network partition, DB sync failure)

---

## Best Practices Summary

1. **Monitor Continuously**: Set up 24/7 monitoring with alerting
2. **Set Appropriate Thresholds**: Use defined thresholds (5% WARNING, 10% CRITICAL)
3. **Visualize Trends**: Use time series graphs to identify patterns
4. **Compare Instances**: Use tables to compare all instances side-by-side
5. **Financial Impact Awareness**: Always consider financial impact of alerts
6. **Automated Response**: Rely on auto-demotion for split-brain scenarios
7. **Documentation**: Keep runbooks updated with actual resolution steps

---

## References

- **Implementation Plan**: `TASK22_3_ISSUEFIXPLAN.md`
- **Alert Thresholds**: Task 22.9 - Define Alert Thresholds for Metrics
- **Metrics Implementation**: Task 22.8 - Enhance Metrics Aggregation with Detailed Calculations
- **Grafana Documentation**: https://grafana.com/docs/
- **Prometheus Documentation**: https://prometheus.io/docs/

---

**Last Updated:** November 29, 2025  
**Version:** 1.0  
**Status:** Production Ready

