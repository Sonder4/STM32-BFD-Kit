#!/usr/bin/env python3
"""
Error Exporter Module
Exports error records to JSON and CSV formats.
"""

import json
import csv
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import asdict
import zipfile
import tempfile


class ErrorExporter:
    def __init__(self, error_records: List[Any] = None):
        self.error_records = error_records or []
    
    def set_records(self, records: List[Any]):
        self.error_records = records
    
    def export_json(
        self,
        filepath: str,
        include_metadata: bool = True,
        pretty_print: bool = True
    ) -> bool:
        try:
            export_data = {
                "export_time": datetime.now().isoformat(),
                "total_errors": len(self.error_records),
                "errors": []
            }
            
            for record in self.error_records:
                if hasattr(record, '__dataclass_fields__'):
                    error_dict = asdict(record)
                elif hasattr(record, 'to_dict'):
                    error_dict = record.to_dict()
                elif isinstance(record, dict):
                    error_dict = record
                else:
                    error_dict = dict(record)
                
                export_data["errors"].append(error_dict)
            
            if not include_metadata:
                export_data = {"errors": export_data["errors"]}
            
            with open(filepath, 'w', encoding='utf-8') as f:
                if pretty_print:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(export_data, f, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            print(f"Export to JSON failed: {e}")
            return False
    
    def export_csv(
        self,
        filepath: str,
        include_headers: bool = True,
        columns: Optional[List[str]] = None
    ) -> bool:
        try:
            default_columns = [
                "id", "timestamp", "fault_type", "severity",
                "source", "description", "PC", "LR"
            ]
            
            export_columns = columns or default_columns
            
            rows = []
            for record in self.error_records:
                if hasattr(record, '__dataclass_fields__'):
                    record_dict = asdict(record)
                elif hasattr(record, 'to_dict'):
                    record_dict = record.to_dict()
                elif isinstance(record, dict):
                    record_dict = record
                else:
                    record_dict = dict(record)
                
                row = {}
                for col in export_columns:
                    if col in record_dict:
                        row[col] = record_dict[col]
                    elif col == "PC":
                        row[col] = record_dict.get("registers", {}).get("PC", "")
                    elif col == "LR":
                        row[col] = record_dict.get("registers", {}).get("LR", "")
                    else:
                        row[col] = ""
                
                rows.append(row)
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=export_columns)
                
                if include_headers:
                    writer.writeheader()
                
                writer.writerows(rows)
            
            return True
            
        except Exception as e:
            print(f"Export to CSV failed: {e}")
            return False
    
    def export_html(
        self,
        filepath: str,
        title: str = "Hardware Error Report",
        include_summary: bool = True
    ) -> bool:
        try:
            html_content = self._generate_html_report(title, include_summary)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return True
            
        except Exception as e:
            print(f"Export to HTML failed: {e}")
            return False
    
    def _generate_html_report(self, title: str, include_summary: bool) -> str:
        severity_colors = {
            "Critical": "#dc3545",
            "High": "#fd7e14",
            "Medium": "#ffc107",
            "Low": "#28a745",
            "Info": "#17a2b8"
        }
        
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }}
        .summary {{
            background: #e9ecef;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }}
        .summary-item {{
            display: inline-block;
            margin-right: 30px;
        }}
        .error-card {{
            border: 1px solid #ddd;
            border-radius: 4px;
            margin-bottom: 15px;
            overflow: hidden;
        }}
        .error-header {{
            padding: 10px 15px;
            color: white;
            font-weight: bold;
        }}
        .error-body {{
            padding: 15px;
        }}
        .register-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        .register-table td {{
            padding: 5px 10px;
            border: 1px solid #ddd;
        }}
        .register-table td:first-child {{
            font-weight: bold;
            width: 80px;
            background: #f8f9fa;
        }}
        .stack-trace {{
            background: #f8f9fa;
            padding: 10px;
            font-family: monospace;
            border-radius: 4px;
            margin-top: 10px;
        }}
        .footer {{
            margin-top: 20px;
            padding-top: 10px;
            border-top: 1px solid #ddd;
            color: #666;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
"""
        
        if include_summary:
            severity_counts = {}
            source_counts = {}
            
            for record in self.error_records:
                if hasattr(record, '__dataclass_fields__'):
                    record_dict = asdict(record)
                elif isinstance(record, dict):
                    record_dict = record
                else:
                    record_dict = dict(record)
                
                severity = record_dict.get("severity", "Unknown")
                source = record_dict.get("source", "Unknown")
                
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
                source_counts[source] = source_counts.get(source, 0) + 1
            
            html += """
        <div class="summary">
            <h3>Summary</h3>
            <div class="summary-item"><strong>Total Errors:</strong> {total}</div>
""".format(total=len(self.error_records))
            
            for sev, count in severity_counts.items():
                html += f'            <div class="summary-item"><strong>{sev}:</strong> {count}</div>\n'
            
            html += """
        </div>
"""
        
        html += """
        <h2>Error Details</h2>
"""
        
        for record in self.error_records:
            if hasattr(record, '__dataclass_fields__'):
                record_dict = asdict(record)
            elif isinstance(record, dict):
                record_dict = record
            else:
                record_dict = dict(record)
            
            severity = record_dict.get("severity", "Low")
            color = severity_colors.get(severity, "#6c757d")
            
            html += f"""
        <div class="error-card">
            <div class="error-header" style="background-color: {color};">
                [{record_dict.get('id', 'N/A')}] {record_dict.get('fault_type', 'Unknown')} - {severity}
            </div>
            <div class="error-body">
                <p><strong>Time:</strong> {record_dict.get('timestamp', 'N/A')}</p>
                <p><strong>Source:</strong> {record_dict.get('source', 'N/A')}</p>
                <p><strong>Description:</strong> {record_dict.get('description', 'N/A')}</p>
"""
            
            registers = record_dict.get("registers", {})
            if registers:
                html += """
                <table class="register-table">
"""
                for reg, val in list(registers.items())[:8]:
                    html += f"""                    <tr><td>{reg}</td><td>{val}</td></tr>
"""
                html += """                </table>
"""
            
            stack_trace = record_dict.get("stack_trace", [])
            if stack_trace:
                html += f"""
                <div class="stack-trace">
                    <strong>Stack Trace:</strong><br>
                    {'<br>'.join(stack_trace[:10])}
                </div>
"""
            
            html += """
            </div>
        </div>
"""
        
        html += f"""
        <div class="footer">
            Generated: {datetime.now().isoformat()} | Hardware Error Logger
        </div>
    </div>
</body>
</html>
"""
        
        return html
    
    def export_markdown(
        self,
        filepath: str,
        title: str = "Hardware Error Report"
    ) -> bool:
        try:
            md_content = self._generate_markdown_report(title)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(md_content)
            
            return True
            
        except Exception as e:
            print(f"Export to Markdown failed: {e}")
            return False
    
    def _generate_markdown_report(self, title: str) -> str:
        md = f"# {title}\n\n"
        md += f"**Generated:** {datetime.now().isoformat()}\n\n"
        md += f"**Total Errors:** {len(self.error_records)}\n\n"
        
        md += "## Summary\n\n"
        
        severity_counts = {}
        for record in self.error_records:
            if hasattr(record, '__dataclass_fields__'):
                record_dict = asdict(record)
            elif isinstance(record, dict):
                record_dict = record
            else:
                record_dict = dict(record)
            
            severity = record_dict.get("severity", "Unknown")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        md += "| Severity | Count |\n"
        md += "|----------|-------|\n"
        for sev, count in severity_counts.items():
            md += f"| {sev} | {count} |\n"
        
        md += "\n## Error Details\n\n"
        
        for i, record in enumerate(self.error_records, 1):
            if hasattr(record, '__dataclass_fields__'):
                record_dict = asdict(record)
            elif isinstance(record, dict):
                record_dict = record
            else:
                record_dict = dict(record)
            
            md += f"### {i}. {record_dict.get('id', 'N/A')} - {record_dict.get('fault_type', 'Unknown')}\n\n"
            md += f"- **Severity:** {record_dict.get('severity', 'N/A')}\n"
            md += f"- **Source:** {record_dict.get('source', 'N/A')}\n"
            md += f"- **Time:** {record_dict.get('timestamp', 'N/A')}\n"
            md += f"- **Description:** {record_dict.get('description', 'N/A')}\n\n"
            
            registers = record_dict.get("registers", {})
            if registers:
                md += "**Registers:**\n\n"
                for reg, val in list(registers.items())[:6]:
                    md += f"- `{reg}`: `{val}`\n"
                md += "\n"
            
            stack_trace = record_dict.get("stack_trace", [])
            if stack_trace:
                md += "**Stack Trace:**\n\n```\n"
                for addr in stack_trace[:5]:
                    md += f"{addr}\n"
                md += "```\n\n"
        
        return md
    
    def export_all(
        self,
        output_dir: str,
        base_name: str = "error_report"
    ) -> Dict[str, bool]:
        results = {}
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        results["json"] = self.export_json(
            os.path.join(output_dir, f"{base_name}.json")
        )
        results["csv"] = self.export_csv(
            os.path.join(output_dir, f"{base_name}.csv")
        )
        results["html"] = self.export_html(
            os.path.join(output_dir, f"{base_name}.html")
        )
        results["md"] = self.export_markdown(
            os.path.join(output_dir, f"{base_name}.md")
        )
        
        return results
    
    def export_archive(
        self,
        filepath: str,
        formats: List[str] = None
    ) -> bool:
        formats = formats or ["json", "csv", "html"]
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                files_to_zip = []
                
                if "json" in formats:
                    json_path = os.path.join(temp_dir, "error_report.json")
                    self.export_json(json_path)
                    files_to_zip.append(("error_report.json", json_path))
                
                if "csv" in formats:
                    csv_path = os.path.join(temp_dir, "error_report.csv")
                    self.export_csv(csv_path)
                    files_to_zip.append(("error_report.csv", csv_path))
                
                if "html" in formats:
                    html_path = os.path.join(temp_dir, "error_report.html")
                    self.export_html(html_path)
                    files_to_zip.append(("error_report.html", html_path))
                
                with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for name, path in files_to_zip:
                        zf.write(path, name)
            
            return True
            
        except Exception as e:
            print(f"Export archive failed: {e}")
            return False


if __name__ == "__main__":
    from dataclasses import dataclass
    
    @dataclass
    class TestRecord:
        id: str
        timestamp: str
        fault_type: str
        severity: str
        source: str
        description: str
        registers: dict
        stack_trace: list
    
    test_records = [
        TestRecord(
            id="ERR_001",
            timestamp="2024-01-20T10:30:00",
            fault_type="HardFault",
            severity="Critical",
            source="CPU",
            description="Invalid memory access",
            registers={"PC": "0x08004567", "LR": "0x08002345"},
            stack_trace=["0x08004567", "0x08002345"]
        )
    ]
    
    exporter = ErrorExporter(test_records)
    exporter.export_json("test_report.json")
    exporter.export_csv("test_report.csv")
    print("Export completed")
