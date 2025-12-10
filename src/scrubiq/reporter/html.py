"""HTML report generation for scrubIQ scan results."""

from pathlib import Path
from datetime import datetime
from typing import Optional
from ..scanner.results import ScanResult

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>scrubIQ Scan Report</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .header h1 {{ font-size: 24px; margin-bottom: 10px; }}
        .header .meta {{ opacity: 0.9; font-size: 14px; }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .stat {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .stat .value {{ font-size: 32px; font-weight: bold; color: #667eea; }}
        .stat .label {{ font-size: 14px; color: #666; }}
        .stat.warning .value {{ color: #dc2626; }}
        .entity-chart {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .entity-chart h3 {{
            font-size: 16px;
            margin-bottom: 15px;
            color: #333;
        }}
        .entity-bar {{
            display: flex;
            align-items: center;
            margin-bottom: 8px;
        }}
        .entity-bar .label {{
            width: 150px;
            font-size: 13px;
            color: #555;
        }}
        .entity-bar .bar {{
            flex: 1;
            height: 20px;
            background: #e5e7eb;
            border-radius: 4px;
            overflow: hidden;
            margin: 0 10px;
        }}
        .entity-bar .fill {{
            height: 100%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 4px;
        }}
        .entity-bar .count {{
            width: 50px;
            font-size: 13px;
            font-weight: 500;
            text-align: right;
        }}
        .files {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .file {{
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
        }}
        .file:last-child {{ border-bottom: none; }}
        .file-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
        }}
        .file-header:hover {{
            background: #f9fafb;
            margin: -15px -20px;
            padding: 15px 20px;
        }}
        .file-path {{ 
            font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
            font-size: 13px;
            word-break: break-all;
            flex: 1;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
            margin-left: 10px;
            white-space: nowrap;
        }}
        .badge.high {{ background: #fee2e2; color: #991b1b; }}
        .badge.medium {{ background: #fef3c7; color: #92400e; }}
        .badge.low {{ background: #e0f2fe; color: #075985; }}
        .matches {{
            margin-top: 10px;
            padding-left: 20px;
            border-left: 2px solid #e5e7eb;
        }}
        .match {{
            font-size: 13px;
            padding: 5px 0;
            color: #555;
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .match-type {{ 
            font-weight: 500;
            color: #667eea;
            min-width: 120px;
        }}
        .match-value {{ 
            font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
            background: #f1f5f9;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 12px;
        }}
        .confidence {{
            color: #888;
            font-size: 12px;
        }}
        .filter-bar {{
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}
        .filter-bar input {{
            padding: 10px 14px;
            border: 1px solid #ddd;
            border-radius: 6px;
            flex: 1;
            min-width: 200px;
            font-size: 14px;
        }}
        .filter-bar input:focus {{
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }}
        .filter-bar select {{
            padding: 10px 14px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
            background: white;
        }}
        .empty {{ 
            text-align: center;
            padding: 60px 20px;
            color: #888;
        }}
        .empty .icon {{
            font-size: 48px;
            margin-bottom: 15px;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #888;
            font-size: 12px;
        }}
        .toggle-btn {{
            background: none;
            border: none;
            color: #667eea;
            cursor: pointer;
            font-size: 12px;
            padding: 0;
        }}
        .toggle-btn:hover {{
            text-decoration: underline;
        }}
        .hidden {{ display: none; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>&#128269; scrubIQ Scan Report</h1>
        <div class="meta">
            <div>Path: {source_path}</div>
            <div>Scanned: {scan_time}</div>
            <div>Scan ID: {scan_id}</div>
        </div>
    </div>
    
    <div class="stats">
        <div class="stat">
            <div class="value">{total_files}</div>
            <div class="label">Files Scanned</div>
        </div>
        <div class="stat{matches_warning}">
            <div class="value">{files_with_matches}</div>
            <div class="label">Files with Matches</div>
        </div>
        <div class="stat{matches_warning}">
            <div class="value">{total_matches}</div>
            <div class="label">Total Matches</div>
        </div>
        <div class="stat">
            <div class="value">{files_errored}</div>
            <div class="label">Errors</div>
        </div>
    </div>
    
    {entity_chart}
    
    <div class="filter-bar">
        <input type="text" id="search" placeholder="Filter by filename..." onkeyup="filterFiles()">
        <select id="labelFilter" onchange="filterFiles()">
            <option value="">All Labels</option>
            <option value="highly_confidential">Highly Confidential</option>
            <option value="confidential">Confidential</option>
            <option value="internal">Internal</option>
        </select>
        <select id="entityFilter" onchange="filterFiles()">
            <option value="">All Entity Types</option>
            {entity_options}
        </select>
    </div>
    
    <div class="files" id="fileList">
        {file_rows}
    </div>
    
    <div class="footer">
        Generated by scrubIQ &bull; {generation_time}
    </div>
    
    <script>
        function filterFiles() {{
            const search = document.getElementById('search').value.toLowerCase();
            const label = document.getElementById('labelFilter').value;
            const entity = document.getElementById('entityFilter').value;
            const files = document.querySelectorAll('.file');
            
            files.forEach(file => {{
                const path = file.dataset.path.toLowerCase();
                const fileLabel = file.dataset.label;
                const fileEntities = file.dataset.entities || '';
                
                const matchesSearch = path.includes(search);
                const matchesLabel = !label || fileLabel === label;
                const matchesEntity = !entity || fileEntities.includes(entity);
                
                file.style.display = matchesSearch && matchesLabel && matchesEntity ? 'block' : 'none';
            }});
        }}
        
        function toggleMatches(id) {{
            const el = document.getElementById(id);
            if (el) {{
                el.classList.toggle('hidden');
            }}
        }}
    </script>
</body>
</html>"""

FILE_ROW_TEMPLATE = """
<div class="file" data-path="{path}" data-label="{label}" data-entities="{entities}">
    <div class="file-header" onclick="toggleMatches('matches-{file_id}')">
        <span class="file-path">{path_display}</span>
        <span>
            <span class="badge {badge_class}">{label_display}</span>
            <button class="toggle-btn">{match_count} match{match_plural}</button>
        </span>
    </div>
    <div class="matches" id="matches-{file_id}">
        {match_rows}
    </div>
</div>
"""

MATCH_ROW_TEMPLATE = """
<div class="match">
    <span class="match-type">{entity_type}</span>
    <span class="match-value">{value}</span>
    <span class="confidence">{confidence}% confidence</span>
</div>
"""

ENTITY_CHART_TEMPLATE = """
<div class="entity-chart">
    <h3>Entities Found by Type</h3>
    {bars}
</div>
"""

ENTITY_BAR_TEMPLATE = """
<div class="entity-bar">
    <span class="label">{entity_type}</span>
    <div class="bar">
        <div class="fill" style="width: {percent}%"></div>
    </div>
    <span class="count">{count}</span>
</div>
"""


def generate_html_report(
    result: ScanResult,
    output_path: Path,
    title: Optional[str] = None,
) -> Path:
    """
    Generate an HTML report from scan results.

    Args:
        result: ScanResult from Scanner
        output_path: Where to write the HTML file
        title: Optional custom title

    Returns:
        Path to the generated report
    """
    # Calculate entity counts for chart
    entity_counts: dict[str, int] = {}
    for f in result.files:
        for m in f.real_matches:
            entity_type = m.entity_type.value
            entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1

    # Build entity chart
    entity_chart = ""
    if entity_counts:
        max_count = max(entity_counts.values())
        bars = []
        for entity_type, count in sorted(entity_counts.items(), key=lambda x: -x[1]):
            percent = (count / max_count) * 100 if max_count > 0 else 0
            bars.append(
                ENTITY_BAR_TEMPLATE.format(
                    entity_type=entity_type.replace("_", " ").title(),
                    count=count,
                    percent=percent,
                )
            )
        entity_chart = ENTITY_CHART_TEMPLATE.format(bars="\n".join(bars))

    # Build entity filter options
    entity_options = "\n".join(
        f'<option value="{e}">{e.replace("_", " ").title()}</option>'
        for e in sorted(entity_counts.keys())
    )

    # Build file rows
    file_rows = []
    file_id = 0

    for f in result.files:
        if not f.has_sensitive_data:
            continue

        file_id += 1

        # Build match rows
        match_rows = []
        for m in f.real_matches:
            match_rows.append(
                MATCH_ROW_TEMPLATE.format(
                    entity_type=m.entity_type.value.replace("_", " ").title(),
                    value=m.redacted_value,
                    confidence=int(m.confidence * 100),
                )
            )

        # Determine badge class
        label = f.label_recommendation.value if f.label_recommendation else "none"
        if "highly" in label:
            badge_class = "high"
        elif "confidential" in label:
            badge_class = "high"
        elif label == "internal":
            badge_class = "medium"
        else:
            badge_class = "low"

        label_display = label.replace("_", " ").title()

        # Get entity types in this file
        file_entities = ",".join(set(m.entity_type.value for m in f.real_matches))

        # Truncate path display
        path_str = str(f.path)
        path_display = path_str if len(path_str) <= 80 else "..." + path_str[-77:]

        match_count = len(f.real_matches)

        file_rows.append(
            FILE_ROW_TEMPLATE.format(
                path=path_str,
                path_display=path_display,
                label=label,
                badge_class=badge_class,
                label_display=label_display,
                match_rows="\n".join(match_rows),
                entities=file_entities,
                file_id=file_id,
                match_count=match_count,
                match_plural="" if match_count == 1 else "es",
            )
        )

    if not file_rows:
        file_rows = [
            """
<div class="empty">
    <div class="icon">&#127881;</div>
    <div>No sensitive data found!</div>
</div>
"""
        ]

    # Warning class for stats when matches found
    matches_warning = " warning" if result.files_with_matches > 0 else ""

    # Build full HTML
    html = HTML_TEMPLATE.format(
        source_path=result.source_path,
        scan_time=result.started_at.strftime("%Y-%m-%d %H:%M:%S") if result.started_at else "N/A",
        scan_id=result.scan_id,
        total_files=result.total_files,
        files_with_matches=result.files_with_matches,
        total_matches=result.total_matches,
        files_errored=result.files_errored,
        file_rows="\n".join(file_rows),
        entity_chart=entity_chart,
        entity_options=entity_options,
        matches_warning=matches_warning,
        generation_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    output_path = Path(output_path)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def generate_summary_report(
    results: list[ScanResult],
    output_path: Path,
    title: str = "scrubIQ Summary Report",
) -> Path:
    """
    Generate a summary HTML report from multiple scan results.

    Useful for comparing scans over time or across different directories.

    Args:
        results: List of ScanResult objects
        output_path: Where to write the HTML file
        title: Report title

    Returns:
        Path to the generated report
    """
    # For now, just generate a report from the most recent scan
    # Full implementation would show trends across scans
    if results:
        return generate_html_report(results[-1], output_path, title)

    # Empty report
    output_path = Path(output_path)
    output_path.write_text(
        """<!DOCTYPE html>
<html>
<head><title>No Scans</title></head>
<body><h1>No scan results available</h1></body>
</html>"""
    )
    return output_path
