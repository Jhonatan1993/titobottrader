import io
import datetime
from typing import Optional, List, Dict, Any
import xlsxwriter

# Matplotlib headless para gráficos en PDF
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ReportLab para generación de PDF institucional
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether, PageBreak
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Canvas de ReportLab que calcula dinámicamente el total de páginas para el footer."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Línea de pie de página
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(40, 36, letter[0] - 40, 36)
        
        # Textos de footer
        gen_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.drawString(40, 24, f"TitoBotTrader Platform · Reporte Oficial de Auditoría · Generado: {gen_time}")
        page_text = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(letter[0] - 40, 24, page_text)
        self.restoreState()


def generate_trades_xlsx(journal, broker: Optional[str] = None) -> bytes:
    """
    Genera un archivo XLSX profesional con 2 hojas:
    1. 'Resumen Diario & Gráficos': Métricas agregadas por día con gráficos de barras interactivos de Excel.
    2. 'Detalle de Operaciones': Log exhaustivo de todas las operaciones con formato condicional y autofiltros.
    """
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    # ------------------ ESTILOS Y FORMATOS ------------------
    fmt_title = workbook.add_format({
        'bold': True, 'font_size': 16, 'font_color': '#0F172A', 'font_name': 'Segoe UI'
    })
    fmt_subtitle = workbook.add_format({
        'font_size': 10, 'font_color': '#475569', 'font_name': 'Segoe UI'
    })
    fmt_kpi_label = workbook.add_format({
        'bold': True, 'font_size': 9, 'font_color': '#64748B', 'font_name': 'Segoe UI',
        'bg_color': '#F1F5F9', 'border': 1, 'border_color': '#CBD5E1', 'align': 'center'
    })
    fmt_kpi_val = workbook.add_format({
        'bold': True, 'font_size': 13, 'font_color': '#0F172A', 'font_name': 'Segoe UI',
        'bg_color': '#FFFFFF', 'border': 1, 'border_color': '#CBD5E1', 'align': 'center'
    })
    fmt_kpi_val_pnl = workbook.add_format({
        'bold': True, 'font_size': 13, 'font_color': '#047857', 'font_name': 'Segoe UI',
        'bg_color': '#ECFDF5', 'border': 1, 'border_color': '#CBD5E1', 'align': 'center',
        'num_format': '$#,##0.00'
    })
    fmt_kpi_val_pnl_neg = workbook.add_format({
        'bold': True, 'font_size': 13, 'font_color': '#BE123C', 'font_name': 'Segoe UI',
        'bg_color': '#FFF1F2', 'border': 1, 'border_color': '#CBD5E1', 'align': 'center',
        'num_format': '$#,##0.00'
    })
    
    fmt_th = workbook.add_format({
        'bold': True, 'font_size': 10, 'font_color': '#FFFFFF', 'bg_color': '#1E293B',
        'border': 1, 'border_color': '#0F172A', 'align': 'center', 'valign': 'vcenter'
    })
    fmt_cell = workbook.add_format({
        'font_size': 9.5, 'font_color': '#1E293B', 'border': 1, 'border_color': '#E2E8F0',
        'valign': 'vcenter'
    })
    fmt_cell_center = workbook.add_format({
        'font_size': 9.5, 'font_color': '#1E293B', 'border': 1, 'border_color': '#E2E8F0',
        'align': 'center', 'valign': 'vcenter'
    })
    fmt_currency = workbook.add_format({
        'font_size': 9.5, 'font_color': '#1E293B', 'border': 1, 'border_color': '#E2E8F0',
        'num_format': '$#,##0.00', 'align': 'right', 'valign': 'vcenter'
    })
    fmt_pnl_pos = workbook.add_format({
        'font_size': 9.5, 'font_color': '#047857', 'bg_color': '#F0FDF4', 'bold': True,
        'border': 1, 'border_color': '#E2E8F0', 'num_format': '+$#,##0.00;-$#,##0.00;$0.00',
        'align': 'right', 'valign': 'vcenter'
    })
    fmt_pnl_neg = workbook.add_format({
        'font_size': 9.5, 'font_color': '#B91C1C', 'bg_color': '#FEF2F2', 'bold': True,
        'border': 1, 'border_color': '#E2E8F0', 'num_format': '+$#,##0.00;-$#,##0.00;$0.00',
        'align': 'right', 'valign': 'vcenter'
    })
    fmt_percent = workbook.add_format({
        'font_size': 9.5, 'font_color': '#1E293B', 'border': 1, 'border_color': '#E2E8F0',
        'num_format': '0.0%', 'align': 'right', 'valign': 'vcenter'
    })

    # Datos
    summaries = journal.get_daily_summary(broker=broker)
    total_trades_count = sum(d["total_trades"] for d in summaries)
    total_wins_count = sum(d["winning_trades"] for d in summaries)
    total_net_pnl = sum(d["realized_pnl"] for d in summaries)
    total_invested_vol = sum(d["total_invested"] for d in summaries)
    gross_wins = sum(d["gross_profit"] for d in summaries)
    gross_losses = sum(d["gross_loss"] for d in summaries)
    global_pf = round(gross_wins / gross_losses, 2) if gross_losses > 0 else (gross_wins if gross_wins > 0 else 1.0)
    global_wr = round((total_wins_count / total_trades_count) * 100, 1) if total_trades_count > 0 else 0.0

    # ------------------ HOJA 1: RESUMEN DIARIO & GRÁFICOS ------------------
    ws1 = workbook.add_worksheet('Resumen Diario & Gráficos')
    ws1.set_zoom(95)
    ws1.set_tab_color('#38BDF8')

    # Título & Encabezado
    broker_label = broker.upper() if broker and broker != "ALL" else "TODOS LOS BROKERS (CONSOLIDADO)"
    ws1.write(0, 0, "TITOBOTTRADER · REPORTE HISTÓRICO DE RENDIMIENTO POR DÍA", fmt_title)
    ws1.write(1, 0, f"Plataforma: {broker_label} | Generado: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", fmt_subtitle)

    # Tarjetas de KPIs Consolidados
    ws1.write(3, 0, "DÍAS OPERADOS", fmt_kpi_label)
    ws1.write(4, 0, len(summaries), fmt_kpi_val)

    ws1.write(3, 1, "TOTAL TRADES", fmt_kpi_label)
    ws1.write(4, 1, total_trades_count, fmt_kpi_val)

    ws1.write(3, 2, "WIN RATE GLOBAL", fmt_kpi_label)
    ws1.write(4, 2, global_wr / 100.0, fmt_percent)

    ws1.write(3, 3, "PNL NETO TOTAL", fmt_kpi_label)
    ws1.write(4, 3, total_net_pnl, fmt_kpi_val_pnl if total_net_pnl >= 0 else fmt_kpi_val_pnl_neg)

    ws1.write(3, 4, "VOLUMEN INVERTIDO", fmt_kpi_label)
    ws1.write(4, 4, total_invested_vol, fmt_currency)

    ws1.write(3, 5, "PROFIT FACTOR", fmt_kpi_label)
    ws1.write(4, 5, f"{global_pf:.2f}x", fmt_kpi_val)

    # Tabla de Resumen Diario
    table_headers = [
        "Fecha (Día)", "Broker", "Trades", "Ganadas", "Perdidas", "Empates",
        "Win Rate %", "PnL Neto USD", "Ganancia Bruta", "Pérdida Bruta",
        "Profit Factor", "Volumen Invertido", "Rendimiento Promedio %", "Mejor Trade", "Peor Trade"
    ]
    start_row = 6
    for col_idx, h in enumerate(table_headers):
        ws1.write(start_row, col_idx, h, fmt_th)

    curr_row = start_row + 1
    for d in summaries:
        ws1.write(curr_row, 0, d["date"], fmt_cell_center)
        ws1.write(curr_row, 1, d["broker"], fmt_cell_center)
        ws1.write(curr_row, 2, d["total_trades"], fmt_cell_center)
        ws1.write(curr_row, 3, d["winning_trades"], fmt_cell_center)
        ws1.write(curr_row, 4, d["losing_trades"], fmt_cell_center)
        ws1.write(curr_row, 5, d["tie_trades"], fmt_cell_center)
        ws1.write(curr_row, 6, d["win_rate"] / 100.0, fmt_percent)
        
        pnl_val = d["realized_pnl"]
        ws1.write(curr_row, 7, pnl_val, fmt_pnl_pos if pnl_val >= 0 else fmt_pnl_neg)
        ws1.write(curr_row, 8, d["gross_profit"], fmt_currency)
        ws1.write(curr_row, 9, d["gross_loss"], fmt_currency)
        ws1.write(curr_row, 10, d["profit_factor"], fmt_cell_center)
        ws1.write(curr_row, 11, d["total_invested"], fmt_currency)
        ws1.write(curr_row, 12, d["avg_return_percent"] / 100.0, fmt_percent)
        ws1.write(curr_row, 13, d["best_trade"], fmt_pnl_pos if d["best_trade"] >= 0 else fmt_pnl_neg)
        ws1.write(curr_row, 14, d["worst_trade"], fmt_pnl_pos if d["worst_trade"] >= 0 else fmt_pnl_neg)
        curr_row += 1

    # Ajustar anchos de columnas
    ws1.set_column('A:A', 13)
    ws1.set_column('B:B', 14)
    ws1.set_column('C:F', 9)
    ws1.set_column('G:G', 12)
    ws1.set_column('H:J', 14)
    ws1.set_column('K:K', 12)
    ws1.set_column('L:L', 16)
    ws1.set_column('M:M', 18)
    ws1.set_column('N:O', 13)

    # ------------------ GRÁFICOS INTERACTIVOS NATIVOS DE EXCEL ------------------
    num_days = len(summaries)
    if num_days > 0:
        # 1. Gráfico de Barras: PnL Diario ($ USD)
        chart_pnl = workbook.add_chart({'type': 'column'})
        chart_pnl.add_series({
            'name':       'PnL Diario ($ USD)',
            'categories': ['Resumen Diario & Gráficos', start_row + 1, 0, start_row + num_days, 0],
            'values':     ['Resumen Diario & Gráficos', start_row + 1, 7, start_row + num_days, 7],
            'fill':       {'color': '#10B981'},
            'data_labels': {'value': True, 'font': {'size': 8, 'name': 'Segoe UI'}}
        })
        chart_pnl.set_title({'name': 'Rendimiento Cuantitativo: PnL Diario ($ USD)', 'name_font': {'bold': True, 'size': 11, 'color': '#0F172A'}})
        chart_pnl.set_x_axis({'name': 'Jornada (Fecha)'})
        chart_pnl.set_y_axis({'name': 'USD Neto Realizado', 'major_gridlines': {'visible': True, 'line': {'color': '#E2E8F0'}}})
        chart_pnl.set_legend({'position': 'none'})
        chart_pnl.set_size({'width': 560, 'height': 280})
        ws1.insert_chart(f'A{curr_row + 2}', chart_pnl)

        # 2. Gráfico de Barras: Win Rate % por Día
        chart_wr = workbook.add_chart({'type': 'column'})
        chart_wr.add_series({
            'name':       'Tasa de Acierto (%)',
            'categories': ['Resumen Diario & Gráficos', start_row + 1, 0, start_row + num_days, 0],
            'values':     ['Resumen Diario & Gráficos', start_row + 1, 6, start_row + num_days, 6],
            'fill':       {'color': '#38BDF8'},
            'data_labels': {'value': True, 'num_format': '0%', 'font': {'size': 8, 'name': 'Segoe UI'}}
        })
        chart_wr.set_title({'name': 'Tasa de Acierto (Win Rate %) por Día', 'name_font': {'bold': True, 'size': 11, 'color': '#0F172A'}})
        chart_wr.set_x_axis({'name': 'Jornada (Fecha)'})
        chart_wr.set_y_axis({'name': 'Porcentaje de Éxito', 'min': 0, 'max': 1.0, 'num_format': '0%', 'major_gridlines': {'visible': True, 'line': {'color': '#E2E8F0'}}})
        chart_wr.set_legend({'position': 'none'})
        chart_wr.set_size({'width': 560, 'height': 280})
        ws1.insert_chart(f'I{curr_row + 2}', chart_wr)

    # ------------------ HOJA 2: DETALLE DE TODAS LAS OPERACIONES ------------------
    ws2 = workbook.add_worksheet('Detalle de Operaciones')
    ws2.set_zoom(95)
    ws2.set_tab_color('#10B981')
    ws2.freeze_panes(1, 0)

    trade_cols = [
        "Fecha (Día)", "ID", "Hora Cierre", "Broker", "Símbolo", "Activo", "Categoría",
        "Tipo", "Cantidad", "Precio Entrada", "Precio Salida", "Monto Invertido",
        "PnL USD", "Rendimiento %", "Resultado", "Duración", "Motivo / Estrategia IA"
    ]
    for col_idx, col_name in enumerate(trade_cols):
        ws2.write(0, col_idx, col_name, fmt_th)

    r2 = 1
    for d in summaries:
        for t in d["trades"]:
            t_pnl = t.get("pnl", 0.0)
            t_pct = (t.get("pnl_percent", 0.0)) / 100.0
            time_str = (t.get("closed_at") or t.get("opened_at") or "")[11:19] or "-"
            
            ws2.write(r2, 0, d["date"], fmt_cell_center)
            ws2.write(r2, 1, t.get("id", ""), fmt_cell_center)
            ws2.write(r2, 2, time_str, fmt_cell_center)
            t_broker = t.get("broker") or ("BINANCE" if t.get("category") == "CRYPTO" else ("ALPACA" if t.get("category") in ("TRADFI_STOCK", "ETF") else "SIMULATION"))
            ws2.write(r2, 3, t_broker, fmt_cell_center)
            ws2.write(r2, 4, t.get("symbol", ""), fmt_cell_center)
            ws2.write(r2, 5, t.get("name", ""), fmt_cell)
            ws2.write(r2, 6, t.get("category", ""), fmt_cell_center)
            ws2.write(r2, 7, t.get("type", "COMPRA / VENTA"), fmt_cell_center)
            ws2.write(r2, 8, t.get("quantity", 0), fmt_cell)
            ws2.write(r2, 9, t.get("entry_price", 0.0), fmt_currency)
            ws2.write(r2, 10, t.get("exit_price", 0.0), fmt_currency)
            ws2.write(r2, 11, t.get("invested_amount", 0.0), fmt_currency)
            ws2.write(r2, 12, t_pnl, fmt_pnl_pos if t_pnl >= 0 else fmt_pnl_neg)
            ws2.write(r2, 13, t_pct, fmt_percent)
            ws2.write(r2, 14, t.get("result", ""), fmt_cell_center)
            ws2.write(r2, 15, t.get("duration", ""), fmt_cell_center)
            ws2.write(r2, 16, t.get("reason", "Cierre por estrategia"), fmt_cell)
            r2 += 1

    # Autofilter en la hoja de detalle
    ws2.autofilter(0, 0, max(1, r2 - 1), len(trade_cols) - 1)
    ws2.set_column('A:A', 13)
    ws2.set_column('B:D', 12)
    ws2.set_column('E:E', 10)
    ws2.set_column('F:F', 22)
    ws2.set_column('G:H', 14)
    ws2.set_column('I:L', 14)
    ws2.set_column('M:N', 14)
    ws2.set_column('O:P', 14)
    ws2.set_column('Q:Q', 34)

    workbook.close()
    return output.getvalue()


def _generate_pnl_bar_chart(summaries: List[Dict[str, Any]]) -> io.BytesIO:
    """Genera gráfico de barras de PnL Diario con Matplotlib en memoria."""
    # Invertir para mostrar cronológicamente (antiguo -> reciente)
    chronological = list(reversed(summaries))
    dates = [d["date"][5:] for d in chronological]  # MM-DD para legibilidad
    pnls = [d["realized_pnl"] for d in chronological]
    bar_colors = ['#10B981' if p >= 0 else '#EF4444' for p in pnls]

    fig, ax = plt.subplots(figsize=(6.8, 2.5), dpi=220)
    fig.patch.set_facecolor('#F8FAFC')
    ax.set_facecolor('#FFFFFF')

    bars = ax.bar(dates, pnls, color=bar_colors, width=0.55, edgecolor='#CBD5E1', linewidth=0.7, zorder=3)
    ax.axhline(0, color='#64748B', linewidth=0.8, linestyle='--', zorder=4)
    ax.grid(axis='y', linestyle=':', alpha=0.6, color='#CBD5E1', zorder=1)

    # Etiquetas encima o debajo de cada barra
    for bar in bars:
        h = bar.get_height()
        va = 'bottom' if h >= 0 else 'top'
        y_pos = h + (0.5 if h >= 0 else -1.2)
        txt = f"+${h:.2f}" if h >= 0 else f"-${abs(h):.2f}"
        color = '#047857' if h >= 0 else '#B91C1C'
        ax.annotate(txt, xy=(bar.get_x() + bar.get_width() / 2, y_pos),
                    xytext=(0, 0), textcoords="offset points",
                    ha='center', va=va, fontsize=7.5, fontweight='bold', color=color)

    ax.set_title('Rendimiento Cuantitativo: PnL Diario Realizado ($ USD)', fontsize=10, fontweight='bold', color='#0F172A', pad=10)
    ax.set_ylabel('PnL USD ($)', fontsize=8, color='#475569')
    ax.tick_params(axis='both', labelsize=8, colors='#475569')
    for spine in ax.spines.values():
        spine.set_color('#E2E8F0')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


def _generate_winrate_bar_chart(summaries: List[Dict[str, Any]]) -> io.BytesIO:
    """Genera gráfico de barras de Win Rate (%) y distribución de operaciones."""
    chronological = list(reversed(summaries))
    dates = [d["date"][5:] for d in chronological]
    win_rates = [d["win_rate"] for d in chronological]

    fig, ax = plt.subplots(figsize=(6.8, 2.5), dpi=220)
    fig.patch.set_facecolor('#F8FAFC')
    ax.set_facecolor('#FFFFFF')

    bars = ax.bar(dates, win_rates, color='#38BDF8', width=0.55, edgecolor='#0284C7', linewidth=0.7, zorder=3)
    ax.axhline(50.0, color='#F59E0B', linewidth=1.0, linestyle='--', label='Meta Break-even (50%)', zorder=4)
    ax.grid(axis='y', linestyle=':', alpha=0.6, color='#CBD5E1', zorder=1)

    for idx, bar in enumerate(bars):
        h = bar.get_height()
        trades_info = f"{h:.1f}%\n({chronological[idx]['winning_trades']}G/{chronological[idx]['losing_trades']}P)"
        ax.annotate(trades_info, xy=(bar.get_x() + bar.get_width() / 2, h + 1.5),
                    xytext=(0, 0), textcoords="offset points",
                    ha='center', va='bottom', fontsize=7, fontweight='bold', color='#0369A1')

    ax.set_ylim(0, max(105, max(win_rates, default=50) + 15))
    ax.set_title('Tasa de Acierto (Win Rate %) y Balance de Operaciones por Día', fontsize=10, fontweight='bold', color='#0F172A', pad=10)
    ax.set_ylabel('Win Rate (%)', fontsize=8, color='#475569')
    ax.tick_params(axis='both', labelsize=8, colors='#475569')
    ax.legend(loc='upper right', fontsize=7.5, framealpha=0.8)
    for spine in ax.spines.values():
        spine.set_color('#E2E8F0')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_trades_pdf(journal, broker: Optional[str] = None) -> bytes:
    """
    Genera un informe institucional en PDF de alta fidelidad con:
    - Portada ejecutiva con KPIs consolidados
    - Gráficos de barras explicativos de rendimiento y acierto
    - Tablas de métricas por jornada con estilos corporativos
    - Desglose detallado de operaciones
    """
    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=46
    )

    styles = getSampleStyleSheet()
    
    # Estilos tipográficos
    style_title = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0F172A'),
        spaceAfter=3
    )
    style_subtitle = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#64748B'),
        spaceAfter=12
    )
    style_section_h = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor('#1E293B'),
        spaceBefore=10,
        spaceAfter=6
    )
    style_th = ParagraphStyle(
        'TableHead',
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1
    )
    style_td = ParagraphStyle(
        'TableCell',
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#1E293B'),
        alignment=1
    )
    style_td_left = ParagraphStyle(
        'TableCellLeft',
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#1E293B'),
        alignment=0
    )

    story = []

    # 1. Cabecera Institucional
    broker_name = broker.upper() if broker and broker != "ALL" else "TODOS LOS BROKERS (CONSOLIDADO)"
    story.append(Paragraph("TITOBOTTRADER · REPORTE EJECUTIVO DE AUDITORÍA", style_title))
    story.append(Paragraph(
        f"Histórico de Transacciones y Métricas por Día | Plataforma: <b>{broker_name}</b> | Fecha de emisión: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        style_subtitle
    ))

    # Obtener datos
    summaries = journal.get_daily_summary(broker=broker)
    total_trades_count = sum(d["total_trades"] for d in summaries)
    total_wins_count = sum(d["winning_trades"] for d in summaries)
    total_net_pnl = sum(d["realized_pnl"] for d in summaries)
    total_invested_vol = sum(d["total_invested"] for d in summaries)
    gross_wins = sum(d["gross_profit"] for d in summaries)
    gross_losses = sum(d["gross_loss"] for d in summaries)
    global_pf = round(gross_wins / gross_losses, 2) if gross_losses > 0 else (gross_wins if gross_wins > 0 else 1.0)
    global_wr = round((total_wins_count / total_trades_count) * 100, 1) if total_trades_count > 0 else 0.0

    # 2. Tarjetas de KPIs (Table)
    kpi_pnl_str = f"+${total_net_pnl:.2f} USD" if total_net_pnl >= 0 else f"-${abs(total_net_pnl):.2f} USD"
    kpi_pnl_color = "#047857" if total_net_pnl >= 0 else "#BE123C"

    kpi_data = [
        [
            Paragraph("<b>DÍAS OPERADOS</b>", style_th),
            Paragraph("<b>TOTAL TRADES</b>", style_th),
            Paragraph("<b>WIN RATE GLOBAL</b>", style_th),
            Paragraph("<b>PNL NETO TOTAL</b>", style_th),
            Paragraph("<b>VOLUMEN INVERTIDO</b>", style_th),
            Paragraph("<b>PROFIT FACTOR</b>", style_th)
        ],
        [
            Paragraph(f"<font size=12><b>{len(summaries)}</b></font>", style_td),
            Paragraph(f"<font size=12><b>{total_trades_count}</b></font>", style_td),
            Paragraph(f"<font size=12 color='#0284C7'><b>{global_wr}%</b></font>", style_td),
            Paragraph(f"<font size=12 color='{kpi_pnl_color}'><b>{kpi_pnl_str}</b></font>", style_td),
            Paragraph(f"<font size=12 color='#B45309'><b>${total_invested_vol:,.2f}</b></font>", style_td),
            Paragraph(f"<font size=12><b>{global_pf:.2f}x</b></font>", style_td)
        ]
    ]
    t_kpi = Table(kpi_data, colWidths=[90, 85, 95, 110, 105, 75])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#F8FAFC')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_kpi)
    story.append(Spacer(1, 12))

    # 3. Gráficos Explicativos de Barras (Matplotlib)
    if summaries:
        story.append(Paragraph("1. Análisis Gráfico de Rendimiento Cuantitativo", style_section_h))
        
        # Gráfico 1: PnL Diario
        buf_pnl = _generate_pnl_bar_chart(summaries)
        img_pnl = Image(buf_pnl, width=7.4 * inch, height=2.6 * inch)
        story.append(img_pnl)
        story.append(Spacer(1, 8))

        # Gráfico 2: Win Rate % por Jornada
        buf_wr = _generate_winrate_bar_chart(summaries)
        img_wr = Image(buf_wr, width=7.4 * inch, height=2.6 * inch)
        story.append(img_wr)
        story.append(Spacer(1, 14))

    # 4. Tabla de Resumen Diario de Métricas
    story.append(PageBreak())
    story.append(Paragraph("2. Resumen Consolidado de Métricas por Día", style_section_h))

    th_daily = [
        Paragraph("<b>Fecha</b>", style_th),
        Paragraph("<b>Broker</b>", style_th),
        Paragraph("<b>Trades</b>", style_th),
        Paragraph("<b>G / P</b>", style_th),
        Paragraph("<b>Win Rate</b>", style_th),
        Paragraph("<b>PnL Neto</b>", style_th),
        Paragraph("<b>Profit Fac.</b>", style_th),
        Paragraph("<b>Volumen</b>", style_th),
        Paragraph("<b>Mejor Trade</b>", style_th),
        Paragraph("<b>Top Activo</b>", style_th)
    ]
    daily_rows = [th_daily]
    for d in summaries:
        pnl = d["realized_pnl"]
        pnl_c = "#047857" if pnl >= 0 else "#BE123C"
        pnl_s = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        
        best = d["best_trade"]
        best_s = f"+${best:.2f}" if best >= 0 else f"-${abs(best):.2f}"
        best_c = "#047857" if best >= 0 else "#BE123C"

        daily_rows.append([
            Paragraph(f"<b>{d['date']}</b>", style_td),
            Paragraph(d["broker"], style_td),
            Paragraph(str(d["total_trades"]), style_td),
            Paragraph(f"{d['winning_trades']} / {d['losing_trades']}", style_td),
            Paragraph(f"<b>{d['win_rate']}%</b>", style_td),
            Paragraph(f"<b><font color='{pnl_c}'>{pnl_s}</font></b>", style_td),
            Paragraph(f"{d['profit_factor']:.2f}x", style_td),
            Paragraph(f"${d['total_invested']:,.2f}", style_td),
            Paragraph(f"<font color='{best_c}'>{best_s}</font>", style_td),
            Paragraph(f"<b>{d.get('most_profitable_symbol', '-')}</b>", style_td)
        ])

    t_daily = Table(daily_rows, colWidths=[65, 60, 40, 48, 55, 65, 52, 65, 55, 55])
    t_daily.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_daily)
    story.append(Spacer(1, 14))

    # 5. Muestra de Transacciones Recientes (Top Operaciones)
    story.append(Paragraph("3. Registro Reciente de Operaciones Auditadas", style_section_h))
    
    th_trades = [
        Paragraph("<b>Hora</b>", style_th),
        Paragraph("<b>ID</b>", style_th),
        Paragraph("<b>Broker</b>", style_th),
        Paragraph("<b>Activo</b>", style_th),
        Paragraph("<b>Entrada</b>", style_th),
        Paragraph("<b>Salida</b>", style_th),
        Paragraph("<b>Invertido</b>", style_th),
        Paragraph("<b>PnL USD</b>", style_th),
        Paragraph("<b>Retorno</b>", style_th),
        Paragraph("<b>Resultado</b>", style_th)
    ]
    trade_rows = [th_trades]
    
    # Recolectar trades de las jornadas
    all_trades = []
    for d in summaries:
        all_trades.extend(d["trades"])
    
    for t in all_trades[:50]:  # Mostrar los primeros 50 trades clave
        t_pnl = t.get("pnl", 0.0)
        t_c = "#047857" if t_pnl >= 0 else "#BE123C"
        t_s = f"+${t_pnl:.2f}" if t_pnl >= 0 else f"-${abs(t_pnl):.2f}"
        t_pct = t.get("pnl_percent", 0.0)
        pct_s = f"+{t_pct:.2f}%" if t_pct >= 0 else f"{t_pct:.2f}%"
        time_str = (t.get("closed_at") or t.get("opened_at") or "")[11:19] or "-"
        b_val = (t.get("broker") or ("BINANCE" if t.get("category") == "CRYPTO" else ("ALPACA" if t.get("category") in ("TRADFI_STOCK", "ETF") else "SIMULATION"))).upper()
        b_tag = "Binance" if b_val == "BINANCE" else ("Alpaca" if b_val == "ALPACA" else "Simulación")

        trade_rows.append([
            Paragraph(time_str, style_td),
            Paragraph(t.get("id", ""), style_td),
            Paragraph(b_tag, style_td),
            Paragraph(f"<b>{t.get('symbol', '')}</b>", style_td),
            Paragraph(f"${t.get('entry_price', 0.0):.2f}", style_td),
            Paragraph(f"${t.get('exit_price', 0.0):.2f}", style_td),
            Paragraph(f"${t.get('invested_amount', 0.0):.2f}", style_td),
            Paragraph(f"<b><font color='{t_c}'>{t_s}</font></b>", style_td),
            Paragraph(f"<font color='{t_c}'>{pct_s}</font>", style_td),
            Paragraph(t.get("result", "CERRADO"), style_td)
        ])

    t_trades = Table(trade_rows, colWidths=[55, 48, 52, 55, 55, 55, 60, 60, 55, 65])
    t_trades.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
    ]))
    story.append(t_trades)

    # Construir documento con numeración de páginas
    doc.build(story, canvasmaker=NumberedCanvas)
    return output.getvalue()
