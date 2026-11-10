"""Create downloadable Excel, PDF and chart artifacts for each analysis."""
from __future__ import annotations

import json
import re
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)


def _safe_cell(value):
    if pd.isna(value):
        return ""
    text = str(value)
    # Prevent spreadsheet formula execution from untrusted customer text.
    if text.startswith(("=", "+", "-", "@")):
        text = "'" + text
    return text


def _make_chart(findings: list[dict], chart_path: Path) -> None:
    plot_items = findings[:10]
    labels = [item["theme"] for item in reversed(plot_items)]
    values = [item["mention_count"] for item in reversed(plot_items)]
    height = max(4.2, 0.48 * len(labels) + 1.5)
    fig, ax = plt.subplots(figsize=(9, height))
    ax.barh(labels, values)
    ax.set_xlabel("Customer feedback mentions")
    ax.set_title("Most frequently reported customer themes")
    ax.grid(axis="x", alpha=0.2)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(chart_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def _make_excel(result: dict, output_path: Path) -> None:
    classified: pd.DataFrame = result["classified_records"]
    findings = result["findings"]
    ai = result.get("ai_breakdown", {})
    overview = pd.DataFrame([
        {"Metric": "Valid feedback records", "Value": result["dataset"]["total_valid_records"]},
        {"Metric": "Exact duplicate mentions retained", "Value": result["dataset"]["exact_duplicate_mentions"]},
        {"Metric": "Unique normalized feedback", "Value": result["dataset"]["unique_normalized_feedback"]},
        {"Metric": "Themes identified", "Value": result["summary"]["themes_identified"]},
        {"Metric": "Classified by Qwen3", "Value": ai.get("qwen3_records", "Not recorded")},
        {"Metric": "Classified by keyword fallback", "Value": ai.get("fallback_records", "Not recorded")},
        {"Metric": "Unreported classification method", "Value": ai.get("unreported_records", "Not recorded")},
        {"Metric": "Qwen3 share of valid records (%)", "Value": ai.get("qwen3_percentage", "Not recorded")},
        {"Metric": "High urgency language signals", "Value": result["summary"].get("high_urgency_records", 0)},
        {"Metric": "Emotion language signals", "Value": json.dumps(result["summary"].get("emotion_breakdown", {}), ensure_ascii=False)},
        {"Metric": "Urgency language signals", "Value": json.dumps(result["summary"].get("urgency_breakdown", {}), ensure_ascii=False)},
        {"Metric": "Ranking method", "Value": result["summary"]["priority_method"]},
    ])
    theme_rows = []
    evidence_rows = []
    for item in findings:
        theme_rows.append({
            "Rank": item["priority_rank"],
            "Theme": item["theme"],
            "Mentions": item["mention_count"],
            "Unique feedback": item["unique_normalized_feedback_count"],
            "Exact duplicate mentions": item["duplicate_mention_count"],
            "Prevalence (%)": item["prevalence_pct"],
            "Distinct wording patterns": item["unique_normalized_feedback_count"],
            "Evidence breadth (not confidence)": item.get("investigation", {}).get("evidence_breadth", "Not assessed"),
            "Sentiment mix": json.dumps(item.get("sentiment_breakdown", {}), ensure_ascii=False),
            "Emotion signals": json.dumps(item.get("emotion_breakdown", {}), ensure_ascii=False),
            "Urgency signals": json.dumps(item.get("urgency_breakdown", {}), ensure_ascii=False),
            "Suggested next step (validate)": item["suggested_next_step"],
        })
        for row_id in item["record_ids"]:
            match = classified.loc[classified["record_id"] == row_id].iloc[0]
            evidence_rows.append({
                "Finding ID": item["finding_id"],
                "Theme": item["theme"],
                "Record ID": row_id,
                "Source ID": _safe_cell(match.get("source_id", "")),
                "Source type": _safe_cell(match.get("source_type", "file_upload")),
                "Source row": int(match["source_row"]),
                "Source reference": _safe_cell(match.get("source_reference", "")),
                "Source page": _safe_cell(match.get("source_page", "")),
                "Duplicate": bool(match["is_duplicate"]),
                "Original feedback": _safe_cell(match["original_feedback"]),
                "Classification method": match["classification_method"],
                "Emotion": _safe_cell(match.get("emotion", "unknown")),
                "Urgency": _safe_cell(match.get("urgency", "unknown")),
            })

    investigation_rows = []
    for item in findings:
        card = item.get("investigation", {})
        investigation_rows.append({
            "Finding ID": item["finding_id"],
            "Theme": item["theme"],
            "Status": card.get("status", "Needs investigation"),
            "What customers report": card.get("what_customers_report", ""),
            "Evidence breadth": card.get("evidence_breadth", "Not assessed"),
            "Evidence breadth note": card.get("evidence_breadth_note", ""),
            "Mixed experience signals": card.get("mixed_experience_signals", False),
            "What is not established": "\n".join(card.get("what_is_not_established", [])),
            "Investigation checks": "\n".join(card.get("investigation_checks", [])),
            "Suggested next step": card.get("recommended_next_step", ""),
        })

    trend = result.get("trend_analysis", {"available": False, "reason": "Not generated."})
    if trend.get("available"):
        trend_rows = [{
            "Date column": trend.get("date_column", ""),
            "Previous period": f"{trend['previous_period']['start']} to {trend['previous_period']['end']}",
            "Recent period": f"{trend['recent_period']['start']} to {trend['recent_period']['end']}",
            **row,
        } for row in trend.get("trends", [])]
    else:
        trend_rows = [{"Trend analysis": "Unavailable", "Reason": trend.get("reason", "Not generated.")}]

    cluster_result = result.get("problem_clusters", {})
    cluster_rows = []
    for cluster in cluster_result.get("clusters", []):
        cluster_rows.append({
            "Cluster ID": cluster.get("cluster_id"), "Theme": cluster.get("theme"),
            "Representative wording": cluster.get("label"), "Mentions": cluster.get("mention_count"),
            "Distinct customers": cluster.get("unique_customers"),
            "Record IDs": ", ".join(cluster.get("record_ids", [])),
            "Similarity method": cluster.get("similarity_basis"),
        })
    if not cluster_rows:
        cluster_rows = [{"Clustering": "Unavailable", "Reason": cluster_result.get("reason", "No multi-record clusters found.") }]

    segment_result = result.get("segment_analysis", {})
    segment_rows = []
    for dimension in segment_result.get("dimensions", []):
        for segment in dimension.get("segments", []):
            segment_rows.append({
                "Dimension": dimension.get("column"), "Segment": segment.get("segment"),
                "Feedback records": segment.get("feedback_records"),
                "Distinct customers": segment.get("unique_customers"),
                "Top themes": json.dumps(segment.get("top_themes", []), ensure_ascii=False),
            })
    if not segment_rows:
        segment_rows = [{"Segmentation": "Unavailable", "Reason": segment_result.get("reason", "No suitable segment columns found.") }]

    decision_pack = result.get("decision_pack", {})
    decision_rows = []
    for card in decision_pack.get("prioritised_decision_cards", []):
        decision_rows.append({
            "Finding ID": card.get("finding_id"), "Theme": card.get("theme"),
            "Triage score (heuristic)": card.get("triage_score"),
            "Score components": json.dumps(card.get("triage_score_components", {}), ensure_ascii=False),
            "Problem statement": card.get("problem_statement"),
            "Unverified hypotheses": "\n".join(item.get("hypothesis", "") for item in card.get("root_cause_hypotheses", [])),
            "Evidence record IDs": ", ".join(card.get("evidence_record_ids", [])),
            "Decision status": card.get("decision_status"),
        })
    if not decision_rows:
        decision_rows = [{"Decision pack": "Unavailable", "Reason": decision_pack.get("limitations", "No generated decisions.")}]

    columns = [
        "record_id", "source_id", "source_type", "source_row", "original_feedback", "theme",
        "sentiment", "emotion", "urgency", "classification_method", "source_reference", "source_page", "is_duplicate", "duplicate_of_record_id",
    ]
    feedback_export = classified[[column for column in columns if column in classified.columns]].copy()
    for column in feedback_export.columns:
        feedback_export[column] = feedback_export[column].map(_safe_cell)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        overview.to_excel(writer, sheet_name="Overview", index=False)
        pd.DataFrame(theme_rows).to_excel(writer, sheet_name="Theme Findings", index=False)
        pd.DataFrame(evidence_rows).to_excel(writer, sheet_name="Evidence Register", index=False)
        pd.DataFrame(investigation_rows).to_excel(writer, sheet_name="Investigation Cards", index=False)
        pd.DataFrame(trend_rows).to_excel(writer, sheet_name="Trend Analysis", index=False)
        pd.DataFrame(cluster_rows).to_excel(writer, sheet_name="Problem Clusters", index=False)
        pd.DataFrame(segment_rows).to_excel(writer, sheet_name="Customer Segments", index=False)
        pd.DataFrame(decision_rows).to_excel(writer, sheet_name="Decision Pack", index=False)
        feedback_export.to_excel(writer, sheet_name="Processed Feedback", index=False)
        header_fill = PatternFill("solid", fgColor="16324F")
        header_font = Font(name="Aptos", color="FFFFFF", bold=True, size=10)
        body_font = Font(name="Aptos", color="1F2937", size=10)
        header_border = Border(bottom=Side(style="medium", color="2F6B9A"))
        fixed_widths = {
            "Overview": {"A": 36, "B": 76},
            "Theme Findings": {"A": 8, "B": 30, "C": 12, "D": 16, "E": 22, "F": 14, "G": 22, "H": 28, "I": 28, "J": 28, "K": 68},
            "Evidence Register": {"A": 14, "B": 28, "C": 14, "D": 16, "E": 12, "F": 12, "G": 24, "H": 12, "I": 72, "J": 22, "K": 16, "L": 12},
            "Processed Feedback": {"A": 14, "B": 16, "C": 16, "D": 12, "E": 72, "F": 30, "G": 14, "H": 18, "I": 12, "J": 22, "K": 14, "L": 20},
            "Investigation Cards": {"A": 14, "B": 28, "C": 22, "D": 68, "E": 20, "F": 58, "G": 20, "H": 68, "I": 76, "J": 72},
            "Trend Analysis": {"A": 20, "B": 28, "C": 28, "D": 28, "E": 16, "F": 16, "G": 18, "H": 24},
            "Problem Clusters": {"A": 14, "B": 28, "C": 72, "D": 12, "E": 18, "F": 75, "G": 34},
            "Customer Segments": {"A": 22, "B": 28, "C": 18, "D": 18, "E": 80},
            "Decision Pack": {"A": 14, "B": 28, "C": 20, "D": 48, "E": 75, "F": 80, "G": 75, "H": 30},
        }
        for sheet in writer.book.worksheets:
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            sheet.sheet_view.showGridLines = False
            sheet.row_dimensions[1].height = 30
            sheet.sheet_properties.pageSetUpPr.fitToPage = True
            for cell in sheet[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                cell.border = header_border
            for row in sheet.iter_rows(min_row=2):
                for cell in row:
                    cell.font = body_font
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
                # Explicit heights make wrapped evidence legible in common spreadsheet viewers.
                sheet.row_dimensions[row[0].row].height = 42 if sheet.title != "Overview" else 32
            for letter, width in fixed_widths.get(sheet.title, {}).items():
                sheet.column_dimensions[letter].width = width

        # A compact bar chart on the Overview sheet makes the workbook self-contained.
        overview_sheet = writer.book["Overview"]
        theme_sheet = writer.book["Theme Findings"]
        if len(theme_rows) > 0:
            chart = BarChart()
            chart.type = "bar"
            chart.style = 10
            chart.title = "Most frequent customer themes"
            chart.y_axis.title = "Theme"
            chart.x_axis.title = "Mentions"
            chart.height = 8
            chart.width = 17
            chart.legend = None
            data = Reference(theme_sheet, min_col=3, min_row=1, max_row=min(len(theme_rows), 10) + 1)
            categories = Reference(theme_sheet, min_col=2, min_row=2, max_row=min(len(theme_rows), 10) + 1)
            chart.add_data(data, titles_from_data=True)
            chart.set_categories(categories)
            overview_sheet.add_chart(chart, "D2")


def _make_pdf(result: dict, chart_path: Path, output_path: Path) -> None:
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SmallCell", parent=styles["BodyText"], fontSize=7, leading=9))
    styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#16324F")))
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
    )
    story = [
        Paragraph("SIGNALDESK", styles["CoverTitle"]),
        Paragraph("Evidence-First Customer Research Brief", styles["Heading2"]),
        Paragraph(f"Source file: {result['dataset']['filename']}", styles["BodyText"]),
        Spacer(1, 5 * mm),
    ]
    ai = result.get("ai_breakdown", {})
    metrics = [
        ["Valid records", str(result["dataset"]["total_valid_records"])],
        ["Exact duplicate mentions retained", str(result["dataset"]["exact_duplicate_mentions"])],
        ["Themes identified", str(result["summary"]["themes_identified"])],
        ["Classified by Qwen3", str(ai.get("qwen3_records", "Not recorded"))],
        ["Classified by keyword fallback", str(ai.get("fallback_records", "Not recorded"))],
        ["Unreported classification method", str(ai.get("unreported_records", "Not recorded"))],
        ["Qwen3 share of valid records", f"{ai.get('qwen3_percentage', 'Not recorded')}%" if "qwen3_percentage" in ai else "Not recorded"],
        ["High urgency language signals", str(result["summary"].get("high_urgency_records", 0))],
        ["Emotion language signals", json.dumps(result["summary"].get("emotion_breakdown", {}), ensure_ascii=False)],
    ]
    table = Table([["Measure", "Result"]] + metrics, colWidths=[85 * mm, 75 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16324F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [table, Spacer(1, 5 * mm), Paragraph("Priority themes by observed frequency", styles["Heading2"])]
    story.append(Image(str(chart_path), width=170 * mm, height=90 * mm, kind="proportional"))
    story += [Paragraph("Key findings", styles["Heading2"])]
    for item in result["findings"][:10]:
        story.append(KeepTogether([
            Paragraph(
                f"<b>{item['priority_rank']}. {item['theme']}</b> — {item['mention_count']} mentions "
                f"({item['prevalence_pct']}% of valid records)", styles["BodyText"]
            ),
            Paragraph(item["priority_basis"], styles["SmallCell"]),
            Paragraph(f"<b>Suggested next step (validate):</b> {item['suggested_next_step']}", styles["SmallCell"]),
            Spacer(1, 2 * mm),
        ]))
    trend = result.get("trend_analysis", {})
    story.append(Paragraph("Emerging problem detection", styles["Heading2"]))
    if trend.get("available"):
        story.append(Paragraph(
            f"Compared adjacent {int(trend.get('window_days', 30))}-day windows anchored to "
            f"the latest source date ({trend.get('latest_date', '')}). Earlier records: "
            f"{trend.get('previous_period', {}).get('records', 0)}; recent records: "
            f"{trend.get('recent_period', {}).get('records', 0)}.", styles["SmallCell"]
        ))
        for item in trend.get("trends", [])[:8]:
            change = item.get("change", 0)
            story.append(Paragraph(
                f"{item.get('theme', '')}: {item.get('previous_mentions', 0)} → "
                f"{item.get('recent_mentions', 0)} ({change:+d}); {item.get('signal', '')}", styles["SmallCell"]
            ))
        story.append(Paragraph(str(trend.get("method_note", "")), styles["SmallCell"]))
    else:
        story.append(Paragraph(
            f"Trend comparison unavailable: {xml_escape(str(trend.get('reason', 'No date analysis was generated.')))}",
            styles["SmallCell"],
        ))

    story.append(Paragraph("Problem investigation cards", styles["Heading2"]))
    for item in result["findings"][:6]:
        card = item.get("investigation", {})
        story.append(KeepTogether([
            Paragraph(f"<b>{item['theme']}</b> — {card.get('evidence_breadth', 'Not assessed')} evidence breadth", styles["BodyText"]),
            Paragraph(str(card.get("what_customers_report", "")), styles["SmallCell"]),
            Paragraph("<b>Checks to run:</b> " + "; ".join(card.get("investigation_checks", [])), styles["SmallCell"]),
            Paragraph("<b>Not established:</b> " + "; ".join(card.get("what_is_not_established", [])), styles["SmallCell"]),
            Spacer(1, 2 * mm),
        ]))

    story.append(Paragraph("Problem similarity clusters", styles["Heading2"]))
    cluster_data = result.get("problem_clusters", {})
    if cluster_data.get("available") and cluster_data.get("clusters"):
        story.append(Paragraph(f"Similarity method: {xml_escape(str(cluster_data.get('method', 'not recorded')))}. These groups indicate wording similarity, not proof of a shared root cause.", styles["SmallCell"]))
        for cluster in cluster_data.get("clusters", [])[:8]:
            story.append(Paragraph(f"<b>{xml_escape(str(cluster.get('cluster_id', '')))} · {xml_escape(str(cluster.get('theme', '')))}</b> — {int(cluster.get('mention_count', 0))} mentions; records: {xml_escape(', '.join(cluster.get('record_ids', [])[:12]))}", styles["SmallCell"]))
    else:
        story.append(Paragraph(xml_escape(str(cluster_data.get("reason", "No similarity clusters were identified."))), styles["SmallCell"]))

    story.append(Paragraph("Customer segmentation", styles["Heading2"]))
    segment_data = result.get("segment_analysis", {})
    if segment_data.get("available"):
        for dimension in segment_data.get("dimensions", []):
            for segment in dimension.get("segments", []):
                top = ", ".join(f"{item['theme']} ({item['mentions']})" for item in segment.get("top_themes", [])[:3])
                story.append(Paragraph(f"{xml_escape(str(dimension.get('column')))} = {xml_escape(str(segment.get('segment')))}: {int(segment.get('feedback_records', 0))} feedback records; top themes: {xml_escape(top)}", styles["SmallCell"]))
    else:
        story.append(Paragraph(xml_escape(str(segment_data.get("reason", "No segmentation fields were found."))), styles["SmallCell"]))

    story.append(Paragraph("Product decision drafts", styles["Heading2"]))
    for card in result.get("decision_pack", {}).get("prioritised_decision_cards", [])[:8]:
        hypotheses = "; ".join(item.get("hypothesis", "") for item in card.get("root_cause_hypotheses", [])[:2])
        story.append(Paragraph(f"<b>{xml_escape(str(card.get('theme', '')))}</b> — heuristic triage score {card.get('triage_score', 'n/a')}/100. {xml_escape(str(card.get('score_note', '')))}", styles["SmallCell"]))
        story.append(Paragraph(f"Candidate hypotheses (unverified): {xml_escape(hypotheses)}", styles["SmallCell"]))

    story.append(Paragraph("Supporting customer evidence", styles["Heading2"]))
    for item in result["findings"][:8]:
        evidence_group = [Paragraph(
            f"<b>{item['finding_id']} · {item['theme']}</b>", styles["BodyText"]
        )]
        for evidence in item["evidence"][:3]:
            quote = (evidence["quote"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            evidence_group.append(Paragraph(
                f"{quote} <font color='#64748B'>(record {evidence['record_id']}, source row {evidence['source_row']})</font>",
                styles["SmallCell"],
            ))
        evidence_group.append(Spacer(1, 2 * mm))
        # Keep each finding title with its first supporting quotes; avoid orphaned section headings.
        story.append(KeepTogether(evidence_group))
    story += [Spacer(1, 4 * mm), Paragraph("Method and limitations", styles["Heading2"])]
    story.append(Paragraph(
        "SIGNALDESK counts retained non-empty source records. Exact duplicate comments are flagged but "
        "not discarded, because repeated reports are meaningful frequency evidence. Theme labels are "
        "AI-assisted; record counts and prevalence are calculated deterministically in Python. "
        "Priority rank is based on observed frequency only. This analysis does not independently measure "
        "severity, revenue impact, or causal root cause. Evidence breadth describes distinct wording patterns, "
        "not statistical confidence. Emotion and urgency are language signals, not clinical or business-risk "
        "assessments. Trend comparisons use two adjacent windows anchored to the latest parseable date in "
        "the uploaded data. Theme labels are Qwen3-assisted when Ollama is "
        "available; if the model is unavailable, a keyword fallback is used and marked per record in "
        "the Processed Feedback sheet.", styles["SmallCell"],
    ))
    if result.get("warnings"):
        story += [Paragraph("Processing warnings", styles["Heading2"])]
        for warning in result["warnings"]:
            safe = warning.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(f"• {safe}", styles["SmallCell"]))
    doc.build(story)


def generate_reports(result: dict, output_dir: str | Path) -> dict[str, str]:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    chart_path = folder / "theme_frequencies.png"
    excel_path = folder / "signaldesk_research_report.xlsx"
    pdf_path = folder / "signaldesk_research_brief.pdf"
    _make_chart(result["findings"], chart_path)
    _make_excel(result, excel_path)
    _make_pdf(result, chart_path, pdf_path)
    return {"excel": str(excel_path), "pdf": str(pdf_path), "chart": str(chart_path)}
