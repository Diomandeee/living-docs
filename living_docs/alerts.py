#!/usr/bin/env python3
"""Staleness Alerts System — Living Docs Enhancement

Provides configurable alerting for stale documentation:
- Email notifications
- Slack/Discord webhooks  
- GitHub Issues
- Console alerts
- Scheduled digest reports
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from enum import Enum

from .freshness import FreshnessReport, FreshnessGrade, grade_to_emoji


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertChannel(Enum):
    """Available alert channels."""
    CONSOLE = "console"
    FILE = "file"
    WEBHOOK = "webhook"
    EMAIL = "email"
    GITHUB_ISSUE = "github_issue"


@dataclass
class Alert:
    """A documentation staleness alert."""
    severity: AlertSeverity
    title: str
    message: str
    doc_path: str
    freshness_score: float
    grade: FreshnessGrade
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "doc_path": self.doc_path,
            "freshness_score": round(self.freshness_score, 3),
            "grade": self.grade.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
    
    def to_markdown(self) -> str:
        emoji = grade_to_emoji(self.grade)
        return f"""### {emoji} {self.title}

**Document:** `{self.doc_path}`  
**Freshness:** {self.freshness_score:.1%} ({self.grade.value})  
**Severity:** {self.severity.value}  

{self.message}
"""

    def to_slack_block(self) -> dict:
        """Format alert for Slack Block Kit."""
        emoji_map = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.ERROR: "🔴",
            AlertSeverity.CRITICAL: "🔥",
        }
        
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji_map[self.severity]} *{self.title}*\n"
                        f"Document: `{self.doc_path}`\n"
                        f"Freshness: {self.freshness_score:.1%} ({self.grade.value})\n"
                        f"{self.message}"
            }
        }


@dataclass
class AlertConfig:
    """Configuration for the alerting system."""
    enabled: bool = True
    channels: list[AlertChannel] = field(default_factory=lambda: [AlertChannel.CONSOLE])
    min_severity: AlertSeverity = AlertSeverity.WARNING
    webhook_url: Optional[str] = None
    email_recipients: list[str] = field(default_factory=list)
    github_repo: Optional[str] = None
    github_token: Optional[str] = None
    digest_schedule: Optional[str] = None  # cron expression
    cooldown_hours: int = 24  # Don't re-alert for same doc within this period
    
    # Thresholds for severity mapping
    critical_threshold: float = 0.3
    error_threshold: float = 0.5
    warning_threshold: float = 0.7
    
    @classmethod
    def from_dict(cls, data: dict) -> "AlertConfig":
        return cls(
            enabled=data.get("enabled", True),
            channels=[AlertChannel(c) for c in data.get("channels", ["console"])],
            min_severity=AlertSeverity(data.get("min_severity", "warning")),
            webhook_url=data.get("webhook_url"),
            email_recipients=data.get("email_recipients", []),
            github_repo=data.get("github_repo"),
            github_token=data.get("github_token"),
            digest_schedule=data.get("digest_schedule"),
            cooldown_hours=data.get("cooldown_hours", 24),
            critical_threshold=data.get("critical_threshold", 0.3),
            error_threshold=data.get("error_threshold", 0.5),
            warning_threshold=data.get("warning_threshold", 0.7),
        )


class AlertSender(ABC):
    """Abstract base class for alert senders."""
    
    @abstractmethod
    def send(self, alerts: list[Alert]) -> bool:
        """Send alerts. Returns True on success."""
        pass


class ConsoleAlertSender(AlertSender):
    """Send alerts to console."""
    
    def send(self, alerts: list[Alert]) -> bool:
        for alert in alerts:
            emoji = grade_to_emoji(alert.grade)
            severity_colors = {
                AlertSeverity.INFO: "\033[94m",
                AlertSeverity.WARNING: "\033[93m",
                AlertSeverity.ERROR: "\033[91m",
                AlertSeverity.CRITICAL: "\033[91m\033[1m",
            }
            reset = "\033[0m"
            color = severity_colors.get(alert.severity, "")
            
            print(f"{color}{emoji} [{alert.severity.value.upper()}] {alert.title}{reset}")
            print(f"   Document: {alert.doc_path}")
            print(f"   Freshness: {alert.freshness_score:.1%}")
            print(f"   {alert.message}")
            print()
        
        return True


class FileAlertSender(AlertSender):
    """Send alerts to a log file."""
    
    def __init__(self, log_path: Path):
        self.log_path = log_path
    
    def send(self, alerts: list[Alert]) -> bool:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.log_path, "a") as f:
                for alert in alerts:
                    f.write(json.dumps(alert.to_dict()) + "\n")
            
            return True
        except Exception as e:
            print(f"Failed to write alerts to file: {e}")
            return False


class WebhookAlertSender(AlertSender):
    """Send alerts to a webhook (Slack, Discord, etc.)."""
    
    def __init__(self, webhook_url: str, format: str = "slack"):
        self.webhook_url = webhook_url
        self.format = format
    
    def send(self, alerts: list[Alert]) -> bool:
        if not self.webhook_url:
            return False
        
        try:
            if self.format == "slack":
                payload = self._format_slack(alerts)
            elif self.format == "discord":
                payload = self._format_discord(alerts)
            else:
                payload = {"alerts": [a.to_dict() for a in alerts]}
            
            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status == 200
        except Exception as e:
            print(f"Failed to send webhook: {e}")
            return False
    
    def _format_slack(self, alerts: list[Alert]) -> dict:
        """Format alerts for Slack."""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📚 Documentation Staleness Alert ({len(alerts)} issues)",
                }
            },
            {"type": "divider"},
        ]
        
        for alert in alerts[:10]:  # Limit to 10
            blocks.append(alert.to_slack_block())
        
        if len(alerts) > 10:
            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": f"_...and {len(alerts) - 10} more alerts_"
                }]
            })
        
        return {"blocks": blocks}
    
    def _format_discord(self, alerts: list[Alert]) -> dict:
        """Format alerts for Discord."""
        embeds = []
        
        for alert in alerts[:10]:
            embeds.append({
                "title": alert.title,
                "description": alert.message,
                "color": {
                    AlertSeverity.INFO: 0x3498db,
                    AlertSeverity.WARNING: 0xf39c12,
                    AlertSeverity.ERROR: 0xe74c3c,
                    AlertSeverity.CRITICAL: 0x992d22,
                }.get(alert.severity, 0x95a5a6),
                "fields": [
                    {"name": "Document", "value": alert.doc_path, "inline": True},
                    {"name": "Freshness", "value": f"{alert.freshness_score:.1%}", "inline": True},
                ],
            })
        
        return {"embeds": embeds}


class GitHubIssueSender(AlertSender):
    """Create GitHub issues for critical documentation alerts."""
    
    def __init__(self, repo: str, token: str):
        self.repo = repo
        self.token = token
    
    def send(self, alerts: list[Alert]) -> bool:
        if not self.repo or not self.token:
            return False
        
        # Only create issues for critical alerts
        critical_alerts = [a for a in alerts if a.severity == AlertSeverity.CRITICAL]
        
        if not critical_alerts:
            return True
        
        try:
            url = f"https://api.github.com/repos/{self.repo}/issues"
            
            for alert in critical_alerts[:3]:  # Limit to 3 issues
                issue_body = alert.to_markdown()
                issue_body += f"\n\n---\n_Created automatically by Living Docs at {alert.timestamp.isoformat()}_"
                
                payload = {
                    "title": f"[Docs] {alert.title}",
                    "body": issue_body,
                    "labels": ["documentation", "stale-docs"],
                }
                
                data = json.dumps(payload).encode("utf-8")
                request = urllib.request.Request(
                    url,
                    data=data,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"token {self.token}",
                        "Accept": "application/vnd.github.v3+json",
                    }
                )
                
                with urllib.request.urlopen(request, timeout=10) as response:
                    if response.status not in (200, 201):
                        return False
            
            return True
        except Exception as e:
            print(f"Failed to create GitHub issue: {e}")
            return False


class AlertManager:
    """Manages documentation staleness alerts."""
    
    def __init__(self, config: AlertConfig, state_dir: Optional[Path] = None):
        self.config = config
        self.state_dir = state_dir or Path(".living-docs")
        self.state_file = self.state_dir / "alert_state.json"
        self.alert_log = self.state_dir / "alerts.log"
        
        self.senders: list[AlertSender] = []
        self._init_senders()
        
        self._alert_history: dict[str, datetime] = self._load_state()
    
    def _init_senders(self) -> None:
        """Initialize alert senders based on config."""
        for channel in self.config.channels:
            if channel == AlertChannel.CONSOLE:
                self.senders.append(ConsoleAlertSender())
            elif channel == AlertChannel.FILE:
                self.senders.append(FileAlertSender(self.alert_log))
            elif channel == AlertChannel.WEBHOOK and self.config.webhook_url:
                # Detect webhook type
                if "discord" in self.config.webhook_url.lower():
                    self.senders.append(WebhookAlertSender(self.config.webhook_url, "discord"))
                else:
                    self.senders.append(WebhookAlertSender(self.config.webhook_url, "slack"))
            elif channel == AlertChannel.GITHUB_ISSUE:
                if self.config.github_repo and self.config.github_token:
                    self.senders.append(GitHubIssueSender(
                        self.config.github_repo,
                        self.config.github_token
                    ))
    
    def _load_state(self) -> dict[str, datetime]:
        """Load alert history state."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                    return {
                        k: datetime.fromisoformat(v) 
                        for k, v in data.items()
                    }
            except Exception:
                pass
        return {}
    
    def _save_state(self) -> None:
        """Save alert history state."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(
                {k: v.isoformat() for k, v in self._alert_history.items()},
                f, indent=2
            )
    
    def _should_alert(self, doc_path: str) -> bool:
        """Check if we should alert for this doc (cooldown check)."""
        if doc_path not in self._alert_history:
            return True
        
        last_alert = self._alert_history[doc_path]
        cooldown = timedelta(hours=self.config.cooldown_hours)
        
        return datetime.now() - last_alert > cooldown
    
    def _severity_from_score(self, score: float) -> AlertSeverity:
        """Determine alert severity from freshness score."""
        if score < self.config.critical_threshold:
            return AlertSeverity.CRITICAL
        elif score < self.config.error_threshold:
            return AlertSeverity.ERROR
        elif score < self.config.warning_threshold:
            return AlertSeverity.WARNING
        else:
            return AlertSeverity.INFO
    
    def check_and_alert(self, reports: list[FreshnessReport]) -> list[Alert]:
        """Check freshness reports and send appropriate alerts."""
        if not self.config.enabled:
            return []
        
        alerts = []
        
        for report in reports:
            severity = self._severity_from_score(report.score)
            
            # Skip if below minimum severity
            if severity.value > self.config.min_severity.value:
                continue
            
            # Skip if in cooldown
            if not self._should_alert(report.doc_path):
                continue
            
            # Create alert
            alert = Alert(
                severity=severity,
                title=f"Documentation for {Path(report.doc_path).name} is {report.grade.value}",
                message="; ".join(report.issues) if report.issues else "Documentation needs review",
                doc_path=report.doc_path,
                freshness_score=report.score,
                grade=report.grade,
                metadata={
                    "factors": report.factors.to_dict(),
                    "recommendations": report.recommendations,
                },
            )
            alerts.append(alert)
            
            # Update history
            self._alert_history[report.doc_path] = datetime.now()
        
        # Send alerts
        if alerts:
            for sender in self.senders:
                sender.send(alerts)
            
            self._save_state()
        
        return alerts
    
    def send_digest(self, reports: list[FreshnessReport]) -> bool:
        """Send a digest summary of all documentation health."""
        if not self.config.enabled:
            return False
        
        total = len(reports)
        if total == 0:
            return True
        
        # Calculate summary stats
        excellent = sum(1 for r in reports if r.grade == FreshnessGrade.EXCELLENT)
        good = sum(1 for r in reports if r.grade == FreshnessGrade.GOOD)
        fair = sum(1 for r in reports if r.grade == FreshnessGrade.FAIR)
        stale = sum(1 for r in reports if r.grade == FreshnessGrade.STALE)
        critical = sum(1 for r in reports if r.grade == FreshnessGrade.CRITICAL)
        
        avg_score = sum(r.score for r in reports) / total
        
        # Create digest alert
        digest = Alert(
            severity=AlertSeverity.INFO if avg_score > 0.7 else AlertSeverity.WARNING,
            title="Documentation Health Digest",
            message=f"Average freshness: {avg_score:.1%}\n"
                    f"🟢 Excellent: {excellent} | 🟡 Good: {good} | 🟠 Fair: {fair} | "
                    f"🔴 Stale: {stale} | 🔥 Critical: {critical}",
            doc_path="(all)",
            freshness_score=avg_score,
            grade=FreshnessGrade.EXCELLENT if avg_score > 0.9 else 
                  FreshnessGrade.GOOD if avg_score > 0.7 else
                  FreshnessGrade.FAIR if avg_score > 0.5 else
                  FreshnessGrade.STALE,
            metadata={
                "total_docs": total,
                "by_grade": {
                    "excellent": excellent,
                    "good": good,
                    "fair": fair,
                    "stale": stale,
                    "critical": critical,
                },
            },
        )
        
        for sender in self.senders:
            sender.send([digest])
        
        return True


def setup_alerts_from_config(config: dict, project_root: Path) -> AlertManager:
    """Set up alert manager from project config."""
    alert_config = AlertConfig.from_dict(config.get("alerts", {}))
    return AlertManager(alert_config, project_root / ".living-docs")
