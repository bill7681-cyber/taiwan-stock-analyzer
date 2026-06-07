import base64
import io
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

matplotlib.use("Agg")
matplotlib.rcParams["axes.unicode_minus"] = False


def _get_chinese_font():
    candidates = [
        "Microsoft JhengHei",
        "Microsoft YaHei",
        "SimHei",
        "PingFang TC",
        "Noto Sans CJK TC",
        "Noto Sans TC",
        "WenQuanYi Micro Hei",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            return name
    return None


def _render(fig) -> bytes:
    """Render figure to PNG bytes at dpi=100, then close it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _to_b64_src(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _img_block(data: bytes, alt: str, style: str = "max-width:100%;") -> str:
    if not data:
        return ""
    src = _to_b64_src(data)
    return (
        f'<div style="width:100%;display:block;text-align:center;margin:16px 0;">'
        f'<img src="{src}" alt="{alt}" '
        f'style="{style}border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,0.12);">'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# 漲跌幅長條圖  14 x 10 inch
# ---------------------------------------------------------------------------

def generate_change_bar_chart(results: list) -> bytes:
    """漲幅前10 / 跌幅前5 水平長條圖，回傳 PNG bytes。"""
    gainers = [s for s in results if s.get("change_float", 0) > 0][:10]
    losers  = sorted(
        [s for s in results if s.get("change_float", 0) < 0],
        key=lambda x: x["change_float"]
    )[:5]
    if not gainers and not losers:
        return b""

    stocks = list(reversed(gainers)) + losers
    labels = [f"{s['stock_id']} {s['stock_name']}" for s in stocks]
    values = [s["change_float"] for s in stocks]
    colors = ["#d32f2f" if v > 0 else "#00897b" for v in values]

    fig, ax = plt.subplots(figsize=(8, 6))

    font_name = _get_chinese_font()
    if font_name:
        plt.rcParams["font.family"] = font_name
    fk = {"fontname": font_name} if font_name else {}

    bars = ax.barh(labels, values, color=colors, edgecolor="white", linewidth=0.5)
    for bar, val in zip(bars, values):
        off = 0.05 if val >= 0 else -0.05
        ax.text(val + off, bar.get_y() + bar.get_height() / 2,
                f"{val:+.2f}%", va="center", ha="left" if val >= 0 else "right",
                fontsize=10, color="#333333", **fk)

    ax.axvline(0, color="#555", linewidth=0.8)
    ax.set_xlabel("漲跌幅 (%)", fontsize=12, **fk)
    ax.set_title("今日漲跌幅排行（漲幅前10 / 跌幅前5）", fontsize=14,
                 fontweight="bold", pad=14, **fk)
    if font_name:
        for lbl in ax.get_yticklabels():
            lbl.set_fontname(font_name)
            lbl.set_fontsize(10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_facecolor("#fafafa")
    fig.patch.set_facecolor("#ffffff")
    plt.tight_layout()
    return _render(fig)


def chart_html_block(results: list) -> str:
    return _img_block(generate_change_bar_chart(results), "漲跌幅排行圖")


# ---------------------------------------------------------------------------
# 大盤多空比例圓餅圖  8 x 8 inch
# ---------------------------------------------------------------------------

def generate_market_breadth_pie(results: list) -> bytes:
    """上漲=綠、下跌=紅、平盤=灰，回傳 PNG bytes。"""
    up   = sum(1 for s in results if s.get("change_float", 0) > 0)
    down = sum(1 for s in results if s.get("change_float", 0) < 0)
    flat = sum(1 for s in results if s.get("change_float", 0) == 0)
    total = up + down + flat
    if total == 0:
        return b""

    sizes, labels, colors = [], [], []
    if up > 0:
        sizes.append(up);   labels.append(f"上漲\n{up}支\n({up/total*100:.1f}%)");   colors.append("#43a047")
    if down > 0:
        sizes.append(down); labels.append(f"下跌\n{down}支\n({down/total*100:.1f}%)"); colors.append("#e53935")
    if flat > 0:
        sizes.append(flat); labels.append(f"平盤\n{flat}支\n({flat/total*100:.1f}%)"); colors.append("#9e9e9e")

    fig, ax = plt.subplots(figsize=(8, 7))
    font_name = _get_chinese_font()
    if font_name:
        plt.rcParams["font.family"] = font_name
    fk = {"fontname": font_name} if font_name else {}

    ax.pie(sizes, labels=labels, colors=colors, startangle=90,
           wedgeprops={"edgecolor": "white", "linewidth": 2},
           textprops={"fontsize": 13, **({"fontname": font_name} if font_name else {})})
    ax.set_title("大盤多空比例", fontsize=16, fontweight="bold", pad=18, **fk)
    fig.patch.set_facecolor("#ffffff")
    plt.tight_layout()
    return _render(fig)


def market_breadth_html_block(results: list) -> str:
    return _img_block(generate_market_breadth_pie(results), "大盤多空比例圖",
                      "max-width:100%;")


# ---------------------------------------------------------------------------
# 法人買賣超長條圖  14 x 8 inch
# ---------------------------------------------------------------------------

def generate_institutional_bar_chart(gainers: list) -> bytes:
    """漲幅前10名三大法人合計，買超=綠、賣超=紅，單位千張，回傳 PNG bytes。"""
    stocks = [s for s in gainers[:10] if s.get("institutional")]
    if not stocks:
        return b""

    labels = [f"{s['stock_id']} {s['stock_name']}" for s in stocks]
    values = [s["institutional"].get("three_major_net", 0) / 1000 for s in stocks]
    colors = ["#388e3c" if v >= 0 else "#c62828" for v in values]

    fig, ax = plt.subplots(figsize=(8, 6))

    font_name = _get_chinese_font()
    if font_name:
        plt.rcParams["font.family"] = font_name
    fk = {"fontname": font_name} if font_name else {}

    bars = ax.barh(labels, values, color=colors, edgecolor="white", linewidth=0.5)
    max_abs = max(abs(v) for v in values) or 1
    for bar, val in zip(bars, values):
        off = 0.02 * max_abs
        ax.text(val + (off if val >= 0 else -off),
                bar.get_y() + bar.get_height() / 2,
                f"{val:+.1f}千張", va="center",
                ha="left" if val >= 0 else "right",
                fontsize=10, color="#333333", **fk)

    ax.axvline(0, color="#555", linewidth=0.8)
    ax.set_xlabel("三大法人合計（千張）", fontsize=12, **fk)
    ax.set_title("漲幅前10名 — 法人買賣超", fontsize=14, fontweight="bold", pad=14, **fk)
    if font_name:
        for lbl in ax.get_yticklabels():
            lbl.set_fontname(font_name)
            lbl.set_fontsize(10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_facecolor("#fafafa")
    fig.patch.set_facecolor("#ffffff")
    plt.tight_layout()
    return _render(fig)


def institutional_bar_html_block(gainers: list) -> str:
    return _img_block(generate_institutional_bar_chart(gainers), "法人買賣超圖")
