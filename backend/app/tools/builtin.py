"""Built-in domain tools for BoetClaw agent."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from langchain_core.tools import tool

from app.core.config import settings
from app.core.observability import EventType, emit_event
from app.core.run_context import write_artifact_meta


def _infer_well_id(rows: list[Any]) -> str:
    for row in rows:
        if isinstance(row, dict):
            value = row.get("well_id") or row.get("well_ref") or row.get("well")
            if value:
                return str(value)
    return ""


@tool
def review_text(content: str, doc_type: str = "general") -> str:
    """审查文本内容的合规性、完整性与专业性。

    Args:
        content: 待审查的文本内容
        doc_type: 文档类型 (drilling_report/safety/general)
    """
    emit_event(EventType.TOOL_CALL, {"tool": "review_text", "doc_type": doc_type})

    issues: list[str] = []
    suggestions: list[str] = []

    if len(content.strip()) < 50:
        issues.append("内容过短，可能缺少关键信息")

    required_keywords = {
        "drilling_report": ["井深", "钻压", "转速", "排量"],
        "safety": ["安全", "风险", "措施"],
    }
    for kw in required_keywords.get(doc_type, []):
        if kw not in content:
            issues.append(f"缺少关键字段/术语: {kw}")

    if "。" not in content and "." not in content:
        suggestions.append("建议添加完整标点，提升可读性")

    paragraphs = [p for p in content.split("\n") if p.strip()]
    if len(paragraphs) < 2:
        suggestions.append("建议分段组织内容，增加结构层次")

    score = max(0, 100 - len(issues) * 15 - len(suggestions) * 5)
    result = {
        "score": score,
        "doc_type": doc_type,
        "issues": issues,
        "suggestions": suggestions,
        "word_count": len(content),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    emit_event(EventType.TOOL_RESULT, {"tool": "review_text", "score": score})
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool
def generate_text(
    topic: str,
    doc_type: str = "drilling_report",
    context: str = "",
) -> str:
    """生成专业文本内容（钻井报告、方案、总结等）。

    Args:
        topic: 主题或标题
        doc_type: 文档类型
        context: 额外上下文信息
    """
    emit_event(EventType.TOOL_CALL, {"tool": "generate_text", "topic": topic})

    templates = {
        "drilling_report": """# {topic} - 钻井日报

**日期**: {date}
**井号**: [待填写]

## 一、钻井参数
| 参数 | 数值 | 单位 |
|------|------|------|
| 井深 | - | m |
| 钻压 (WOB) | - | kN |
| 转速 (RPM) | - | r/min |
| 排量 | - | L/s |
| 泵压 | - | MPa |

## 二、进尺情况
- 日进尺: - m
- 累计进尺: - m
- 机械钻速 (ROP): - m/h

## 三、井况描述
{context}

## 四、下步计划
- 目标层位: -
- 预计进尺: - m
""",
        "summary": """# {topic}

## 概述
{context}

## 主要成果
1. 
2. 
3. 

## 存在问题
- 

## 建议措施
- 
""",
    }

    template = templates.get(doc_type, templates["drilling_report"])
    text = template.format(
        topic=topic,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        context=context or "（请补充具体井况信息）",
    )
    emit_event(EventType.TOOL_RESULT, {"tool": "generate_text", "length": len(text)})
    return text


@tool
def generate_chart(
    data_json: str,
    chart_type: str = "line",
    title: str = "钻井数据图表",
    x_field: str = "x",
    y_fields: str = "y",
) -> str:
    """生成数据可视化图表并保存为 PNG 文件。

    Args:
        data_json: JSON 数组格式的数据
        chart_type: 图表类型 (line/bar/scatter)
        title: 图表标题
        x_field: X 轴字段名
        y_fields: Y 轴字段名，多个用逗号分隔
    """
    emit_event(EventType.TOOL_CALL, {"tool": "generate_chart", "chart_type": chart_type})

    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = settings.workspace_dir / "charts"
    charts_dir.mkdir(exist_ok=True)

    data = json.loads(data_json)
    df = pd.DataFrame(data)
    y_cols = [c.strip() for c in y_fields.split(",")]

    fig, ax = plt.subplots(figsize=(10, 6))

    if chart_type == "bar":
        df.plot(kind="bar", x=x_field, y=y_cols, ax=ax)
    elif chart_type == "scatter":
        for col in y_cols:
            ax.scatter(df[x_field], df[col], label=col, alpha=0.7)
        ax.legend()
    else:
        for col in y_cols:
            ax.plot(df[x_field], df[col], marker="o", label=col)
        ax.legend()

    ax.set_title(title)
    ax.set_xlabel(x_field)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    filename = f"chart_{uuid.uuid4().hex[:8]}.png"
    filepath = charts_dir / filename
    fig.savefig(filepath, dpi=150)
    plt.close(fig)
    write_artifact_meta(
        "chart",
        filename,
        well_id=_infer_well_id(data if isinstance(data, list) else []),
        extra={"title": title, "chart_type": chart_type},
    )

    result = {
        "status": "success",
        "chart_type": chart_type,
        "title": title,
        "file_path": str(filepath),
        "url": f"/api/v1/files/{filename}",
        "data_points": len(data),
    }
    emit_event(EventType.TOOL_RESULT, {"tool": "generate_chart", "file": filename})
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool
def generate_code(
    description: str,
    language: str = "python",
    framework: str = "",
) -> str:
    """生成代码片段或完整脚本。

    Args:
        description: 代码功能描述
        language: 编程语言 (python/javascript/sql)
        framework: 使用的框架或库
    """
    emit_event(EventType.TOOL_CALL, {"tool": "generate_code", "language": language})

    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    code_dir = settings.workspace_dir / "code"
    code_dir.mkdir(exist_ok=True)

    ext_map = {"python": "py", "javascript": "js", "typescript": "ts", "sql": "sql"}
    ext = ext_map.get(language, "txt")
    filename = f"code_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = code_dir / filename

    templates: dict[str, str] = {
        "python": f'''"""{description}

Framework: {framework or "standard library"}
Generated by BoetClaw Agent
"""

import pandas as pd
import numpy as np


def main():
    """Main entry point."""
    # TODO: Implement {description}
    pass


if __name__ == "__main__":
    main()
''',
        "javascript": f"""/**
 * {description}
 * Framework: {framework or "Node.js"}
 * Generated by BoetClaw Agent
 */

async function main() {{
  // TODO: Implement {description}
}}

main().catch(console.error);
""",
        "sql": f"""-- {description}
-- Generated by BoetClaw Agent

SELECT *
FROM drilling_data
WHERE well_id = :well_id
ORDER BY depth;
""",
    }

    code = templates.get(language, f"# {description}\n# Language: {language}\n")
    filepath.write_text(code, encoding="utf-8")
    write_artifact_meta(
        "code",
        filename,
        extra={"description": description, "language": language, "framework": framework},
    )

    result = {
        "status": "success",
        "language": language,
        "description": description,
        "file_path": str(filepath),
        "url": f"/api/v1/files/code/{filename}",
        "code_preview": code[:500],
    }
    emit_event(EventType.TOOL_RESULT, {"tool": "generate_code", "file": filename})
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool
def query_drilling_params(well_id: str, depth_range: str = "0-3000") -> str:
    """查询钻井参数数据，优先读取领域参数库，无数据时回退模拟数据。

    Args:
        well_id: 井号
        depth_range: 深度范围，格式 "start-end"
    """
    emit_event(EventType.TOOL_CALL, {"tool": "query_drilling_params", "well_id": well_id})

    try:
        start, end = [float(x.strip()) for x in depth_range.split("-", 1)]
    except Exception:
        start, end = 0.0, 3000.0

    try:
        from app.domain.store import domain_store

        wells = domain_store.list("wells")
        matched_well = next((w for w in wells if w.get("id") == well_id or w.get("name") == well_id), None)
        lookup_id = matched_well["id"] if matched_well else well_id
        domain_records = []
        for row in domain_store.list("params", lookup_id):
            depth = float(row.get("measured_depth", 0))
            if start <= depth <= end:
                domain_records.append(
                    {
                        "well_id": matched_well.get("name", lookup_id) if matched_well else lookup_id,
                        "well_ref": lookup_id,
                        "depth": depth,
                        "wob": row.get("wob"),
                        "rpm": row.get("rpm"),
                        "rop": row.get("rop"),
                        "torque": row.get("torque"),
                        "pump_pressure": row.get("pump_pressure"),
                        "flow_rate": row.get("flow_rate"),
                        "timestamp": row.get("timestamp", ""),
                        "source": row.get("source", "domain"),
                    }
                )
        if domain_records:
            domain_records.sort(key=lambda r: r["depth"])
            result = {
                "well_id": well_id,
                "depth_range": depth_range,
                "source": "domain",
                "records": domain_records,
            }
            emit_event(EventType.TOOL_RESULT, {"tool": "query_drilling_params", "count": len(domain_records)})
            return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception:
        # Domain data is optional; keep the original mock behavior as a safe fallback.
        pass

    records = _mock_drilling_params(well_id, start, end)
    result = {"well_id": well_id, "depth_range": depth_range, "source": "mock", "records": records}
    emit_event(EventType.TOOL_RESULT, {"tool": "query_drilling_params", "count": len(records)})
    return json.dumps(result, ensure_ascii=False, indent=2)


def _mock_drilling_params(well_id: str, start: float, end: float) -> list[dict[str, Any]]:
    start_i, end_i = int(start), int(end)
    step = max(10, (end - start) // 20)
    records = []
    for depth in range(start_i, end_i + 1, int(step)):
        records.append(
            {
                "well_id": well_id,
                "depth": depth,
                "wob": round(80 + (depth % 100) * 0.5, 1),
                "rpm": round(60 + (depth % 50) * 0.3, 1),
                "rop": round(5 + (depth % 30) * 0.1, 2),
                "flow_rate": round(30 + (depth % 20) * 0.2, 1),
                "source": "mock",
            }
        )
    return records


def get_builtin_tools() -> list:
    return [
        review_text,
        generate_text,
        generate_chart,
        generate_code,
        query_drilling_params,
    ]
