"""Usage tracking for documentation analytics."""

import json
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional
from collections import defaultdict


@dataclass
class PageView:
    """Single page view event."""
    doc_path: str
    timestamp: str
    duration_seconds: float
    scroll_depth: float  # 0-1
    search_query: Optional[str] = None
    referrer: Optional[str] = None


@dataclass
class UsageStats:
    """Aggregated usage statistics for a doc."""
    doc_path: str
    total_views: int = 0
    avg_duration: float = 0.0
    avg_scroll_depth: float = 0.0
    bounce_rate: float = 0.0  # Left quickly without scrolling
    common_searches: list[str] = field(default_factory=list)
    last_viewed: Optional[str] = None


class UsageTracker:
    """Track and analyze documentation usage patterns."""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = data_dir / 'events.jsonl'
        self.stats_file = data_dir / 'stats.json'
    
    def record_view(self, view: PageView):
        """Record a page view event."""
        with open(self.events_file, 'a') as f:
            f.write(json.dumps(asdict(view)) + '\n')
    
    def get_events(self, since: Optional[datetime] = None) -> list[PageView]:
        """Load events, optionally filtered by date."""
        events = []
        
        if not self.events_file.exists():
            return events
        
        with open(self.events_file) as f:
            for line in f:
                try:
                    data = json.loads(line)
                    event = PageView(**data)
                    
                    if since:
                        event_time = datetime.fromisoformat(event.timestamp)
                        if event_time < since:
                            continue
                    
                    events.append(event)
                except (json.JSONDecodeError, TypeError):
                    continue
        
        return events
    
    def compute_stats(self, days: int = 30) -> dict[str, UsageStats]:
        """Compute usage statistics for each doc."""
        since = datetime.now() - timedelta(days=days)
        events = self.get_events(since)
        
        # Group by doc
        by_doc = defaultdict(list)
        for event in events:
            by_doc[event.doc_path].append(event)
        
        stats = {}
        for doc_path, doc_events in by_doc.items():
            total = len(doc_events)
            
            # Calculate averages
            avg_duration = sum(e.duration_seconds for e in doc_events) / total
            avg_scroll = sum(e.scroll_depth for e in doc_events) / total
            
            # Bounce rate (< 10s and < 0.1 scroll)
            bounces = sum(1 for e in doc_events if e.duration_seconds < 10 and e.scroll_depth < 0.1)
            bounce_rate = bounces / total
            
            # Common searches
            searches = [e.search_query for e in doc_events if e.search_query]
            search_counts = defaultdict(int)
            for q in searches:
                search_counts[q] += 1
            common_searches = sorted(search_counts.keys(), key=lambda q: -search_counts[q])[:5]
            
            # Last viewed
            last = max(doc_events, key=lambda e: e.timestamp)
            
            stats[doc_path] = UsageStats(
                doc_path=doc_path,
                total_views=total,
                avg_duration=avg_duration,
                avg_scroll_depth=avg_scroll,
                bounce_rate=bounce_rate,
                common_searches=common_searches,
                last_viewed=last.timestamp
            )
        
        return stats
    
    def save_stats(self, stats: dict[str, UsageStats]):
        """Save computed stats to file."""
        data = {path: asdict(stat) for path, stat in stats.items()}
        with open(self.stats_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_stats(self) -> dict[str, UsageStats]:
        """Load saved stats from file."""
        if not self.stats_file.exists():
            return {}
        
        with open(self.stats_file) as f:
            data = json.load(f)
        
        return {path: UsageStats(**stat) for path, stat in data.items()}
    
    def get_insights(self, stats: dict[str, UsageStats]) -> list[str]:
        """Generate actionable insights from usage data."""
        insights = []
        
        if not stats:
            return ["No usage data available yet."]
        
        # Most viewed
        by_views = sorted(stats.values(), key=lambda s: -s.total_views)
        if by_views:
            top = by_views[0]
            insights.append(f"📈 Most viewed: {top.doc_path} ({top.total_views} views)")
        
        # High bounce rate
        high_bounce = [s for s in stats.values() if s.bounce_rate > 0.7 and s.total_views > 5]
        if high_bounce:
            for stat in high_bounce[:3]:
                insights.append(
                    f"⚠️ High bounce rate ({stat.bounce_rate*100:.0f}%): {stat.doc_path} - "
                    "Consider improving introduction or restructuring"
                )
        
        # Low scroll depth
        low_scroll = [s for s in stats.values() if s.avg_scroll_depth < 0.3 and s.total_views > 5]
        if low_scroll:
            for stat in low_scroll[:3]:
                insights.append(
                    f"📊 Low engagement: {stat.doc_path} - "
                    "Users don't scroll far, content may need restructuring"
                )
        
        # Common searches with no matching doc
        all_searches = []
        for stat in stats.values():
            all_searches.extend(stat.common_searches)
        if all_searches:
            insights.append(f"🔍 Common searches: {', '.join(set(all_searches)[:5])}")
        
        return insights


def generate_tracking_script() -> str:
    """Generate JavaScript tracking snippet for docs."""
    return """
<!-- Living Docs Usage Tracking -->
<script>
(function() {
  var startTime = Date.now();
  var maxScroll = 0;
  var docPath = window.location.pathname;
  var searchQuery = new URLSearchParams(window.location.search).get('q');
  
  // Track scroll depth
  window.addEventListener('scroll', function() {
    var scrolled = window.scrollY + window.innerHeight;
    var total = document.documentElement.scrollHeight;
    maxScroll = Math.max(maxScroll, scrolled / total);
  });
  
  // Send on unload
  window.addEventListener('beforeunload', function() {
    var duration = (Date.now() - startTime) / 1000;
    
    navigator.sendBeacon('/api/docs/track', JSON.stringify({
      doc_path: docPath,
      timestamp: new Date().toISOString(),
      duration_seconds: duration,
      scroll_depth: maxScroll,
      search_query: searchQuery,
      referrer: document.referrer
    }));
  });
})();
</script>
"""
