import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import gspread 
from gspread.exceptions import WorksheetNotFound, APIError
import json
import hmac
import hashlib
import time as pytime
import plotly.express as px

# Popup BI is kept inside app.py so Streamlit Cloud can run even when only this file is deployed.
BI_SKU_KEYS = ["商品名称", "颜色"]
BI_INBOUND_OPS = {"入库", "初始建档", "Inbound", "Initial Setup"}

def _bi_empty_frame():
    return pd.DataFrame(columns=[
        "SKU", "商品名称", "颜色", "期初库存", "本期入库", "本期可售量", "本期POS售出", "换货参考数量",
        "售罄率", "日均销量", "当前库存", "库存年龄天数", "销售额", "单件毛利", "毛利率", "毛利贡献",
        "动销分", "利润分", "系统分类", "辅助标签"
    ])

def _bi_num(value, default=0.0):
    converted = pd.to_numeric(value, errors="coerce")
    if isinstance(converted, pd.Series):
        return converted.fillna(default)
    return default if pd.isna(converted) else converted

def _bi_dates(df, col):
    if df.empty or col not in df.columns:
        return pd.Series(pd.NaT, index=df.index)
    return pd.to_datetime(df[col], errors="coerce").dt.date

def _bi_norm_stock(stock_df):
    stock = stock_df.copy()
    if stock.empty:
        return pd.DataFrame(columns=BI_SKU_KEYS + ["当前库存", "进价成本", "售卖价格"])
    for col in BI_SKU_KEYS:
        if col not in stock.columns:
            stock[col] = ""
        stock[col] = stock[col].fillna("").astype(str).str.strip()
    for col in ["展示数量", "货柜数量", "储物间数量", "总库存", "进价成本", "售卖价格"]:
        if col not in stock.columns:
            stock[col] = 0
        stock[col] = _bi_num(stock[col])
    location_total = stock[["展示数量", "货柜数量", "储物间数量"]].sum(axis=1)
    stock["当前库存"] = location_total.where(location_total > 0, stock["总库存"])
    return stock.drop_duplicates(subset=BI_SKU_KEYS, keep="last")[BI_SKU_KEYS + ["当前库存", "进价成本", "售卖价格"]]

def _bi_norm_sales(sales_df):
    sales = sales_df.copy()
    if sales.empty:
        return pd.DataFrame(columns=BI_SKU_KEYS + ["日期_dt", "订单号", "销售数量", "总营业额"])
    for col in BI_SKU_KEYS + ["订单号"]:
        if col not in sales.columns:
            sales[col] = ""
        sales[col] = sales[col].fillna("").astype(str).str.strip()
    if "日期" not in sales.columns:
        sales["日期"] = ""
    sales["日期_dt"] = _bi_dates(sales, "日期")
    for col in ["销售数量", "总营业额"]:
        if col not in sales.columns:
            sales[col] = 0
        sales[col] = _bi_num(sales[col])
    return sales

def _bi_norm_restock(restock_df):
    restock = restock_df.copy()
    if restock.empty:
        return pd.DataFrame(columns=BI_SKU_KEYS + ["记录日期_dt", "操作类型", "变动数量"])
    for col in BI_SKU_KEYS + ["操作类型"]:
        if col not in restock.columns:
            restock[col] = ""
        restock[col] = restock[col].fillna("").astype(str).str.strip()
    if "记录日期" not in restock.columns:
        restock["记录日期"] = ""
    restock["记录日期_dt"] = _bi_dates(restock, "记录日期")
    if "变动数量" not in restock.columns:
        restock["变动数量"] = 0
    restock["变动数量"] = _bi_num(restock["变动数量"])
    return restock

def _bi_sum(df, value_col, output_col):
    if df.empty:
        return pd.DataFrame(columns=BI_SKU_KEYS + [output_col])
    out = df.groupby(BI_SKU_KEYS, as_index=False)[value_col].sum()
    return out.rename(columns={value_col: output_col})

def _bi_max0(value):
    return max(float(value), 0.0)

def _bi_score_row(row, max_daily_sales, max_profit):
    available = _bi_max0(row["本期可售量"])
    sell_through = _bi_max0(row["售罄率"])
    daily_sales = _bi_max0(row["日均销量"])
    age_days = _bi_max0(row["库存年龄天数"])
    speed_score = (daily_sales / max_daily_sales * 30) if max_daily_sales > 0 else 0
    sell_through_score = min(sell_through, 1.0) * 55
    sample_bonus = 10 if 0 < available <= 6 and sell_through >= 0.6 else 0
    age_penalty = min(age_days / 60 * 20, 20) if sell_through < 0.4 else 0
    movement_score = max(0, min(100, sell_through_score + speed_score + sample_bonus - age_penalty))
    margin_rate_score = min(_bi_max0(row["毛利率"]), 1.0) * 35
    unit_margin_score = min(_bi_max0(row["单件毛利"]) / 120, 1.0) * 30
    contribution_score = (_bi_max0(row["毛利贡献"]) / max_profit * 35) if max_profit > 0 else 0
    return round(movement_score, 1), round(max(0, min(100, margin_rate_score + unit_margin_score + contribution_score)), 1)

def _bi_classify(row):
    available = _bi_max0(row["本期可售量"])
    sold = _bi_max0(row["本期POS售出"])
    current_stock = _bi_max0(row["当前库存"])
    sell_through = _bi_max0(row["售罄率"])
    daily_sales = _bi_max0(row["日均销量"])
    age_days = _bi_max0(row["库存年龄天数"])

    if available <= 0 and current_stock <= 0 and sold <= 0:
        return "无库存/未参与"
    if age_days >= 30 and current_stock > 0 and sold == 0:
        return "滞销款"
    if age_days >= 45 and current_stock > 0 and sell_through <= 0.35:
        return "滞销款"
    if current_stock > 0 and available > 0 and sold <= 1 and sell_through <= 0.15:
        return "滞销款"
    if available <= 6 and sold > 0 and sell_through >= 0.7 and current_stock <= 1 and age_days <= 45:
        return "潜力款"
    if sold > 0 and (sell_through >= 0.75 or (sell_through >= 0.55 and daily_sales >= 0.08)):
        return "畅销款"
    if sold > 0:
        return "常规款"
    return "常规款"

def _bi_tags(row):
    available = _bi_max0(row["本期可售量"])
    sold = _bi_max0(row["本期POS售出"])
    current_stock = _bi_max0(row["当前库存"])
    sell_through = _bi_max0(row["售罄率"])
    age_days = _bi_max0(row["库存年龄天数"])
    margin_rate = _bi_max0(row["毛利率"])
    unit_margin = _bi_max0(row["单件毛利"])
    inbound = _bi_max0(row["本期入库"])
    tags = []
    if margin_rate >= 0.65 or unit_margin >= 150:
        tags.append("高毛利")
    if sold > 0 and sell_through >= 0.75 and current_stock <= 1:
        tags.append("可能断货")
    if available > 0 and available <= 6:
        tags.append("小样本")
    if age_days >= 60 and current_stock > 0:
        tags.append("老库存")
    if inbound > 0 and age_days <= 30:
        tags.append("新入库")
    return "、".join(tags) if tags else "-"

def compute_period_sku_bi(stock_df, sales_df, restock_df, start_date, end_date):
    start_date = pd.to_datetime(start_date).date()
    end_date = pd.to_datetime(end_date).date()
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    stock = _bi_norm_stock(stock_df)
    sales = _bi_norm_sales(sales_df)
    restock = _bi_norm_restock(restock_df)
    if stock.empty and sales.empty and restock.empty:
        return _bi_empty_frame()
    exchange_sales = sales[sales["订单号"].str.startswith("EXC-", na=False)].copy()
    normal_sales = sales[~sales["订单号"].str.startswith("EXC-", na=False)].copy()
    inbound = restock[restock["操作类型"].isin(BI_INBOUND_OPS)].copy()
    period_sales = normal_sales[(normal_sales["日期_dt"] >= start_date) & (normal_sales["日期_dt"] <= end_date)]
    period_exchange = exchange_sales[(exchange_sales["日期_dt"] >= start_date) & (exchange_sales["日期_dt"] <= end_date)]
    period_inbound = inbound[(inbound["记录日期_dt"] >= start_date) & (inbound["记录日期_dt"] <= end_date)]
    after_start_sales = normal_sales[normal_sales["日期_dt"] >= start_date]
    after_start_inbound = inbound[inbound["记录日期_dt"] >= start_date]
    sku_base = pd.concat([stock[BI_SKU_KEYS], normal_sales[BI_SKU_KEYS], inbound[BI_SKU_KEYS], exchange_sales[BI_SKU_KEYS]], ignore_index=True).drop_duplicates()
    if sku_base.empty:
        return _bi_empty_frame()
    result = sku_base.merge(stock, on=BI_SKU_KEYS, how="left")
    for agg in [
        _bi_sum(period_inbound, "变动数量", "本期入库"),
        _bi_sum(period_sales, "销售数量", "本期POS售出"),
        _bi_sum(period_sales, "总营业额", "销售额"),
        _bi_sum(period_exchange, "销售数量", "换货参考数量"),
        _bi_sum(after_start_sales, "销售数量", "期后售出"),
        _bi_sum(after_start_inbound, "变动数量", "期后入库"),
    ]:
        result = result.merge(agg, on=BI_SKU_KEYS, how="left")
    for col in ["当前库存", "进价成本", "售卖价格", "本期入库", "本期POS售出", "销售额", "换货参考数量", "期后售出", "期后入库"]:
        result[col] = _bi_num(result[col])
    result["期初库存"] = (result["当前库存"] + result["期后售出"] - result["期后入库"]).clip(lower=0)
    result["本期可售量"] = result["期初库存"] + result["本期入库"]
    period_days = max((end_date - start_date).days + 1, 1)
    result["售罄率"] = result.apply(lambda r: round(float(r["本期POS售出"]) / float(r["本期可售量"]), 4) if float(r["本期可售量"]) > 0 else 0.0, axis=1)
    result["日均销量"] = (result["本期POS售出"] / period_days).round(3)
    result["单件毛利"] = result["售卖价格"] - result["进价成本"]
    result["毛利率"] = result.apply(lambda r: round(float(r["单件毛利"]) / float(r["售卖价格"]), 4) if float(r["售卖价格"]) > 0 else 0.0, axis=1)
    result["毛利贡献"] = result["销售额"] - result["本期POS售出"] * result["进价成本"]
    first_inbound = inbound.dropna(subset=["记录日期_dt"]).groupby(BI_SKU_KEYS, as_index=False)["记录日期_dt"].min().rename(columns={"记录日期_dt": "首次入库日期"})
    result = result.merge(first_inbound, on=BI_SKU_KEYS, how="left")
    result["库存年龄天数"] = result["首次入库日期"].apply(lambda d: max((end_date - d).days + 1, 0) if pd.notna(d) else 0)
    max_daily_sales = float(result["日均销量"].max()) if not result.empty else 0.0
    max_profit = float(result["毛利贡献"].max()) if not result.empty else 0.0
    scores = result.apply(lambda row: _bi_score_row(row, max_daily_sales, max_profit), axis=1)
    result["动销分"] = [s[0] for s in scores]
    result["利润分"] = [s[1] for s in scores]
    result["系统分类"] = result.apply(_bi_classify, axis=1)
    result["辅助标签"] = result.apply(_bi_tags, axis=1)
    result["SKU"] = result["商品名称"] + " (" + result["颜色"] + ")"
    for col in ["期初库存", "本期入库", "本期可售量", "本期POS售出", "换货参考数量", "当前库存", "库存年龄天数"]:
        result[col] = result[col].round(0).astype(int)
    return result[[
        "SKU", "商品名称", "颜色", "期初库存", "本期入库", "本期可售量", "本期POS售出", "换货参考数量",
        "售罄率", "日均销量", "当前库存", "库存年龄天数", "销售额", "单件毛利", "毛利率", "毛利贡献",
        "动销分", "利润分", "系统分类", "辅助标签"
    ]].sort_values(["系统分类", "动销分", "利润分"], ascending=[True, False, False]).reset_index(drop=True)

def compare_periods(stock_df, sales_df, restock_df, period_a, period_b):
    name_a, start_a, end_a = period_a
    name_b, start_b, end_b = period_b
    a = compute_period_sku_bi(stock_df, sales_df, restock_df, start_a, end_a)
    b = compute_period_sku_bi(stock_df, sales_df, restock_df, start_b, end_b)
    key_cols = ["SKU", "商品名称", "颜色"]
    compare_cols = ["本期POS售出", "售罄率", "销售额", "毛利贡献", "动销分", "利润分", "系统分类"]
    merged = a[key_cols + compare_cols].merge(b[key_cols + compare_cols], on=key_cols, how="outer", suffixes=("_A_raw", "_B_raw")).fillna(0)
    for col in compare_cols:
        merged.rename(columns={f"{col}_A_raw": f"A_{col}", f"{col}_B_raw": f"B_{col}"}, inplace=True)
    merged["档期A"] = name_a
    merged["档期B"] = name_b
    merged["售出变化"] = _bi_num(merged["B_本期POS售出"]) - _bi_num(merged["A_本期POS售出"])
    merged["售罄率变化"] = _bi_num(merged["B_售罄率"]) - _bi_num(merged["A_售罄率"])
    merged["销售额变化"] = _bi_num(merged["B_销售额"]) - _bi_num(merged["A_销售额"])
    merged["毛利贡献变化"] = _bi_num(merged["B_毛利贡献"]) - _bi_num(merged["A_毛利贡献"])
    merged["分类变化"] = merged.apply(lambda r: r["B_系统分类"] if r["A_系统分类"] == r["B_系统分类"] else f"{r['A_系统分类']} → {r['B_系统分类']}", axis=1)
    return merged.sort_values(["售出变化", "销售额变化"], ascending=[False, False]).reset_index(drop=True)

def compute_period_financials(stock_df, sales_df, attendance_df, start_date, end_date):
    start_date = pd.to_datetime(start_date).date()
    end_date = pd.to_datetime(end_date).date()
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    sales = _bi_norm_sales(sales_df)
    stock = _bi_norm_stock(stock_df)
    attendance = attendance_df.copy()
    period_sales = sales[(sales["日期_dt"] >= start_date) & (sales["日期_dt"] <= end_date)].copy()
    if not period_sales.empty:
        period_sales = period_sales.merge(stock[BI_SKU_KEYS + ["进价成本"]], on=BI_SKU_KEYS, how="left")
        period_sales["进价成本"] = _bi_num(period_sales["进价成本"])
        period_sales["总进价成本"] = period_sales["销售数量"] * period_sales["进价成本"]
    else:
        period_sales["总进价成本"] = pd.Series(dtype="float64")
    if attendance.empty:
        wage_total = 0.0
    else:
        if "日期" not in attendance.columns:
            attendance["日期"] = ""
        attendance["日期_dt"] = _bi_dates(attendance, "日期")
        if "核算薪资" not in attendance.columns:
            attendance["核算薪资"] = 0
        attendance["核算薪资"] = _bi_num(attendance["核算薪资"])
        period_att = attendance[(attendance["日期_dt"] >= start_date) & (attendance["日期_dt"] <= end_date)]
        wage_total = float(period_att["核算薪资"].sum()) if not period_att.empty else 0.0
    gross = float(period_sales["总营业额"].sum()) if not period_sales.empty else 0.0
    cogs = float(period_sales["总进价成本"].sum()) if not period_sales.empty else 0.0
    net_revenue = gross / 1.09 if gross else 0.0
    gst = gross - net_revenue
    commission = net_revenue * 0.36
    settlement = net_revenue - commission
    gross_profit = settlement - cogs
    net_profit = gross_profit - wage_total
    net_margin = (net_profit / gross * 100) if gross > 0 else 0.0
    return {
        "总营业额": round(gross, 2),
        "免税净营业额": round(net_revenue, 2),
        "代扣GST(9%)": round(gst, 2),
        "商场抽成(36%)": round(commission, 2),
        "商场实际回款": round(settlement, 2),
        "总进价成本": round(cogs, 2),
        "人工成本": round(wage_total, 2),
        "毛利润": round(gross_profit, 2),
        "真实净利润": round(net_profit, 2),
        "含税净利率%": round(net_margin, 2),
    }

def _dashboard_traffic(traffic_df):
    traffic = traffic_df.copy()
    if traffic.empty:
        return pd.DataFrame(columns=["日期_dt", "有效客流"])
    if "日期" not in traffic.columns:
        traffic["日期"] = ""
    traffic["日期_dt"] = _bi_dates(traffic, "日期")
    if "有效客流" not in traffic.columns:
        traffic["有效客流"] = 0
    traffic["有效客流"] = _bi_num(traffic["有效客流"])
    return traffic

def _dashboard_sales_with_cost(stock_df, sales_df, start_date, end_date):
    sales = _bi_norm_sales(sales_df)
    stock = _bi_norm_stock(stock_df)
    period_sales = sales[(sales["日期_dt"] >= start_date) & (sales["日期_dt"] <= end_date)].copy()
    if period_sales.empty:
        period_sales["进价成本"] = pd.Series(dtype="float64")
        period_sales["总进价成本"] = pd.Series(dtype="float64")
        period_sales["具体毛利"] = pd.Series(dtype="float64")
        return period_sales
    period_sales = period_sales.merge(stock[BI_SKU_KEYS + ["进价成本"]], on=BI_SKU_KEYS, how="left")
    period_sales["进价成本"] = _bi_num(period_sales["进价成本"])
    period_sales["总进价成本"] = period_sales["销售数量"] * period_sales["进价成本"]
    period_sales["具体毛利"] = period_sales["总营业额"] - period_sales["总进价成本"]
    return period_sales

def compute_period_dashboard(stock_df, sales_df, attendance_df, traffic_df, start_date, end_date):
    start_date = pd.to_datetime(start_date).date()
    end_date = pd.to_datetime(end_date).date()
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    period_sales = _dashboard_sales_with_cost(stock_df, sales_df, start_date, end_date)
    financials = compute_period_financials(stock_df, sales_df, attendance_df, start_date, end_date)
    traffic = _dashboard_traffic(traffic_df)
    period_traffic = traffic[(traffic["日期_dt"] >= start_date) & (traffic["日期_dt"] <= end_date)]
    total_traffic = float(period_traffic["有效客流"].sum()) if not period_traffic.empty else 0.0
    total_revenue = float(period_sales["总营业额"].sum()) if not period_sales.empty else 0.0
    total_items = float(period_sales["销售数量"].sum()) if not period_sales.empty else 0.0
    gross_margin = float(period_sales["具体毛利"].sum()) if not period_sales.empty else 0.0
    if not period_sales.empty:
        valid_orders = period_sales[
            (~period_sales["订单号"].astype(str).str.contains("历史单", na=False)) &
            (~period_sales["订单号"].astype(str).str.contains("EXC-", na=False))
        ]
        legacy_orders = period_sales[period_sales["订单号"].astype(str).str.contains("历史单", na=False)]
        order_count = int(valid_orders["订单号"].nunique() + len(legacy_orders))
    else:
        order_count = 0
    conversion = (order_count / total_traffic * 100) if total_traffic > 0 else 0.0
    acv = total_revenue / order_count if order_count > 0 else 0.0
    upt = total_items / order_count if order_count > 0 else 0.0
    avg_margin_rate = (gross_margin / total_revenue * 100) if total_revenue > 0 else 0.0
    days = max((end_date - start_date).days + 1, 1)
    if period_sales.empty:
        daily_sales = pd.DataFrame(columns=["日期", "总营业额", "具体毛利", "销售数量"])
    else:
        daily_sales = period_sales.copy()
        daily_sales["日期"] = pd.to_datetime(daily_sales["日期_dt"]).dt.strftime("%Y/%m/%d")
        daily_sales = daily_sales.groupby("日期", as_index=False).agg({"总营业额": "sum", "具体毛利": "sum", "销售数量": "sum"})
    financial_daily = daily_sales.copy()
    if not financial_daily.empty:
        financial_daily["免税净营业额"] = financial_daily["总营业额"] / 1.09
        financial_daily["商场抽成(36%)"] = financial_daily["免税净营业额"] * 0.36
        financial_daily["商场实际回款"] = financial_daily["免税净营业额"] - financial_daily["商场抽成(36%)"]
        financial_daily["真实净利润"] = financial_daily["商场实际回款"] - (financial_daily["总营业额"] - financial_daily["具体毛利"])
    else:
        financial_daily["真实净利润"] = pd.Series(dtype="float64")
    summary = {
        "有效客流": int(total_traffic),
        "交易单数": int(order_count),
        "购买转化率%": round(conversion, 2),
        "总营业额": round(total_revenue, 2),
        "平均客单价": round(acv, 2),
        "连带率": round(upt, 2),
        "具体毛利": round(gross_margin, 2),
        "总售出件数": int(total_items),
        "平均毛利率%": round(avg_margin_rate, 2),
        "日均营收": round(total_revenue / days, 2),
    }
    summary.update(financials)
    return {"summary": summary, "daily": financial_daily}

def _period_change_rate(after, before):
    after = float(after)
    before = float(before)
    if before == 0:
        return 0.0 if after == 0 else 100.0
    return (after - before) / abs(before) * 100

def compare_financial_periods(stock_df, sales_df, attendance_df, period_a, period_b):
    name_a, start_a, end_a = period_a
    name_b, start_b, end_b = period_b
    summary_a = compute_period_financials(stock_df, sales_df, attendance_df, start_a, end_a)
    summary_b = compute_period_financials(stock_df, sales_df, attendance_df, start_b, end_b)
    metric_order = ["总营业额", "免税净营业额", "代扣GST(9%)", "商场抽成(36%)", "商场实际回款", "总进价成本", "人工成本", "毛利润", "真实净利润", "含税净利率%"]
    rows = []
    for metric in metric_order:
        a_val = summary_a.get(metric, 0.0)
        b_val = summary_b.get(metric, 0.0)
        rows.append({
            "指标": metric,
            "档期A": name_a,
            "A值": a_val,
            "档期B": name_b,
            "B值": b_val,
            "变化": round(b_val - a_val, 2),
            "变化率%": round(_period_change_rate(b_val, a_val), 2),
        })
    return pd.DataFrame(rows)

COMMISSION_TIERS = [
    (15000, 0.004),
    (20000, 0.006),
    (30000, 0.008),
    (50000, 0.012),
    (65000, 0.015),
    (80000, 0.018),
    (100000, 0.022),
    (120000, 0.025),
]
COMMISSION_PROFIT_CAP_RATE = 0.20
DEFAULT_MANAGER_CASHIERS = {"店长", "店长/历史", "老板", "admin", "Admin", "Manager", "Unknown"}

def _commission_num(value, default=0.0):
    converted = pd.to_numeric(value, errors="coerce")
    if isinstance(converted, pd.Series):
        return converted.fillna(default)
    return default if pd.isna(converted) else converted

def _commission_dates(df, col):
    if df.empty or col not in df.columns:
        return pd.Series(pd.NaT, index=df.index)
    return pd.to_datetime(df[col], errors="coerce").dt.date

def _commission_norm_sales(sales_df):
    sales = sales_df.copy()
    if sales.empty:
        return pd.DataFrame(columns=["订单号", "日期_dt", "收银员", "商品名称", "颜色", "销售数量", "总营业额"])
    for col in ["订单号", "收银员", "商品名称", "颜色"]:
        if col not in sales.columns:
            sales[col] = ""
        sales[col] = sales[col].fillna("").astype(str).str.strip()
    if "日期" not in sales.columns:
        sales["日期"] = ""
    sales["日期_dt"] = _commission_dates(sales, "日期")
    for col in ["销售数量", "总营业额"]:
        if col not in sales.columns:
            sales[col] = 0
        sales[col] = _commission_num(sales[col])
    return sales

def _commission_rate_for_gross(gross):
    gross = float(gross or 0)
    rate = 0.0
    for threshold, tier_rate in COMMISSION_TIERS:
        if gross >= threshold:
            rate = tier_rate
    return rate

def _commission_annualized_gross(gross, start_date, end_date):
    start_date = pd.to_datetime(start_date).date()
    end_date = pd.to_datetime(end_date).date()
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    days = max((end_date - start_date).days + 1, 1)
    return float(gross or 0.0) / days * 30

def _commission_period_financials(stock_df, sales_df, attendance_df, start_date, end_date):
    start_date = pd.to_datetime(start_date).date()
    end_date = pd.to_datetime(end_date).date()
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    sales = _commission_norm_sales(sales_df)
    period_sales = sales[(sales["日期_dt"] >= start_date) & (sales["日期_dt"] <= end_date)].copy()
    cogs = 0.0
    if not period_sales.empty and stock_df is not None and not stock_df.empty:
        stock = stock_df.copy()
        for col in ["商品名称", "颜色"]:
            if col not in stock.columns:
                stock[col] = ""
            stock[col] = stock[col].fillna("").astype(str).str.strip()
        if "进价成本" not in stock.columns:
            stock["进价成本"] = 0
        stock["进价成本"] = _commission_num(stock["进价成本"])
        period_sales = period_sales.merge(
            stock[["商品名称", "颜色", "进价成本"]].drop_duplicates(["商品名称", "颜色"], keep="last"),
            on=["商品名称", "颜色"],
            how="left",
        )
        period_sales["进价成本"] = _commission_num(period_sales["进价成本"])
        cogs = float((period_sales["销售数量"] * period_sales["进价成本"]).sum())

    wage_total = 0.0
    attendance = attendance_df.copy() if attendance_df is not None else pd.DataFrame()
    if not attendance.empty:
        if "日期" not in attendance.columns:
            attendance["日期"] = ""
        attendance["日期_dt"] = _commission_dates(attendance, "日期")
        if "核算薪资" not in attendance.columns:
            attendance["核算薪资"] = 0
        attendance["核算薪资"] = _commission_num(attendance["核算薪资"])
        period_att = attendance[(attendance["日期_dt"] >= start_date) & (attendance["日期_dt"] <= end_date)]
        wage_total = float(period_att["核算薪资"].sum()) if not period_att.empty else 0.0

    gross = float(period_sales["总营业额"].sum()) if not period_sales.empty else 0.0
    settlement = (gross / 1.09) * 0.64 if gross else 0.0
    return {
        "总营业额": round(gross, 2),
        "总进价成本": round(cogs, 2),
        "人工成本": round(wage_total, 2),
        "真实净利润": round(settlement - cogs - wage_total, 2),
    }

def compute_monthly_commission(
    sales_df,
    attendance_df,
    staff_purchase_df,
    stock_df,
    start_date,
    end_date,
    manager_cashiers=None,
    pre_commission_net_profit=None,
    profit_cap_rate=COMMISSION_PROFIT_CAP_RATE,
    tier_basis_gross=None,
):
    start_date = pd.to_datetime(start_date).date()
    end_date = pd.to_datetime(end_date).date()
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    manager_cashiers = set(manager_cashiers or DEFAULT_MANAGER_CASHIERS)

    sales = _commission_norm_sales(sales_df)
    period_sales = sales[(sales["日期_dt"] >= start_date) & (sales["日期_dt"] <= end_date)].copy()
    retail_sales = period_sales[~period_sales["订单号"].astype(str).str.startswith("EXC-")].copy() if not period_sales.empty else period_sales

    monthly_gross = float(retail_sales["总营业额"].sum()) if not retail_sales.empty else 0.0
    manager_sales = retail_sales[retail_sales["收银员"].isin(manager_cashiers)].copy()
    employee_sales = retail_sales[~retail_sales["收银员"].isin(manager_cashiers)].copy()
    manager_sales_total = float(manager_sales["总营业额"].sum()) if not manager_sales.empty else 0.0
    employee_sales_total = float(employee_sales["总营业额"].sum()) if not employee_sales.empty else 0.0

    tier_basis_gross = monthly_gross if tier_basis_gross is None else float(tier_basis_gross or 0.0)
    tier_rate = _commission_rate_for_gross(tier_basis_gross)
    theoretical_pool = monthly_gross * tier_rate
    if pre_commission_net_profit is None:
        pre_commission_net_profit = _commission_period_financials(stock_df, sales_df, attendance_df, start_date, end_date)["真实净利润"]
    profit_cap = max(0.0, float(pre_commission_net_profit or 0.0) * float(profit_cap_rate or 0.0))
    final_pool = min(theoretical_pool, profit_cap) if profit_cap_rate is not None else theoretical_pool

    sales_by_staff = pd.DataFrame(columns=["员工姓名", "个人销售额"])
    if not employee_sales.empty:
        sales_by_staff = employee_sales.groupby("收银员", as_index=False)["总营业额"].sum()
        sales_by_staff = sales_by_staff.rename(columns={"收银员": "员工姓名", "总营业额": "个人销售额"})

    wage_by_staff = pd.DataFrame(columns=["员工姓名", "工作时长", "基础工资"])
    attendance = attendance_df.copy() if attendance_df is not None else pd.DataFrame()
    if not attendance.empty:
        if "日期" not in attendance.columns:
            attendance["日期"] = ""
        attendance["日期_dt"] = _commission_dates(attendance, "日期")
        if "员工姓名" not in attendance.columns:
            attendance["员工姓名"] = ""
        attendance["员工姓名"] = attendance["员工姓名"].fillna("").astype(str).str.strip()
        for col in ["工作时长", "核算薪资"]:
            if col not in attendance.columns:
                attendance[col] = 0
            attendance[col] = _commission_num(attendance[col])
        period_att = attendance[(attendance["日期_dt"] >= start_date) & (attendance["日期_dt"] <= end_date)]
        if not period_att.empty:
            wage_by_staff = period_att.groupby("员工姓名", as_index=False).agg({"工作时长": "sum", "核算薪资": "sum"})
            wage_by_staff = wage_by_staff.rename(columns={"核算薪资": "基础工资"})

    deduct_by_staff = pd.DataFrame(columns=["员工姓名", "内购扣款"])
    purchases = staff_purchase_df.copy() if staff_purchase_df is not None else pd.DataFrame()
    if not purchases.empty:
        if "日期" not in purchases.columns:
            purchases["日期"] = ""
        purchases["日期_dt"] = _commission_dates(purchases, "日期")
        if "员工姓名" not in purchases.columns:
            purchases["员工姓名"] = ""
        purchases["员工姓名"] = purchases["员工姓名"].fillna("").astype(str).str.strip()
        if "扣款金额" not in purchases.columns:
            purchases["扣款金额"] = 0
        purchases["扣款金额"] = _commission_num(purchases["扣款金额"])
        period_purchases = purchases[(purchases["日期_dt"] >= start_date) & (purchases["日期_dt"] <= end_date)]
        if not period_purchases.empty:
            deduct_by_staff = period_purchases.groupby("员工姓名", as_index=False)["扣款金额"].sum()
            deduct_by_staff = deduct_by_staff.rename(columns={"扣款金额": "内购扣款"})

    employees = pd.merge(wage_by_staff, sales_by_staff, on="员工姓名", how="outer")
    employees = pd.merge(employees, deduct_by_staff, on="员工姓名", how="outer")
    if employees.empty:
        employees = pd.DataFrame(columns=["员工姓名", "工作时长", "基础工资", "个人销售额", "销售贡献占比", "Commission", "内购扣款", "最终应发"])
    else:
        employees["员工姓名"] = employees["员工姓名"].fillna("").astype(str).str.strip()
        for col in ["工作时长", "基础工资", "个人销售额", "内购扣款"]:
            if col not in employees.columns:
                employees[col] = 0.0
            employees[col] = pd.to_numeric(employees[col], errors="coerce").fillna(0.0)
        employees["销售贡献占比"] = employees["个人销售额"] / employee_sales_total if employee_sales_total > 0 else 0.0
        employees["Commission"] = employees["销售贡献占比"] * final_pool
        employees["最终应发"] = employees["基础工资"] + employees["Commission"] - employees["内购扣款"]
        for col in ["工作时长", "基础工资", "个人销售额", "销售贡献占比", "Commission", "内购扣款", "最终应发"]:
            employees[col] = pd.to_numeric(employees[col], errors="coerce").fillna(0.0).round(4)
        employees = employees[["员工姓名", "工作时长", "基础工资", "个人销售额", "销售贡献占比", "Commission", "内购扣款", "最终应发"]].sort_values(
            ["Commission", "个人销售额", "员工姓名"], ascending=[False, False, True]
        )

    summary = {
        "月总营业额": round(monthly_gross, 2),
        "老板/店长销售额": round(manager_sales_total, 2),
        "员工可分配销售额": round(employee_sales_total, 2),
        "月化档位营业额": round(tier_basis_gross, 2),
        "当前档位比例": round(tier_rate, 4),
        "理论提成池": round(theoretical_pool, 2),
        "扣提成前真实净利润": round(float(pre_commission_net_profit or 0.0), 2),
        "利润保护上限": round(profit_cap, 2),
        "最终提成池": round(final_pool, 2),
        "提成后真实净利润": round(float(pre_commission_net_profit or 0.0) - final_pool, 2),
    }
    return {"summary": summary, "employees": employees.reset_index(drop=True)}

def get_employee_commission_view(commission_result, staff_name):
    staff_name = str(staff_name).strip()
    summary = commission_result.get("summary", {}) if isinstance(commission_result, dict) else {}
    employees = commission_result.get("employees", pd.DataFrame()) if isinstance(commission_result, dict) else pd.DataFrame()
    if employees.empty:
        employee = pd.DataFrame(columns=["员工姓名", "工作时长", "基础工资", "个人销售额", "销售贡献占比", "Commission", "内购扣款", "最终应发"])
    else:
        employee = employees[employees["员工姓名"].astype(str).str.strip() == staff_name].copy()
        employee = employee[["员工姓名", "工作时长", "基础工资", "个人销售额", "销售贡献占比", "Commission", "内购扣款", "最终应发"]]
    return {
        "summary": {
            "当前档位比例": summary.get("当前档位比例", 0.0),
            "最终提成池": summary.get("最终提成池", 0.0),
        },
        "employee": employee.reset_index(drop=True),
    }

# --- 1. 配置与云端数据库初始化 ---
st.set_page_config(page_title="Taka 零售终极管理系统", layout="wide")

try:
    key_dict = json.loads(st.secrets["google_key"])
    gc = gspread.service_account_from_dict(key_dict)
    sh = gc.open_by_url(st.secrets["sheet_url"]) 
except Exception as e:
    st.error(f"🔴 数据库连接失败 Database connection failed! Error: {e}")
    st.stop()

# ================= 🚀 国际化 (i18n) 双语翻译引擎 =================
if "lang" not in st.session_state:
    st.session_state.lang = "cn"

def t(cn_text, en_text):
    return cn_text if st.session_state.lang == "cn" else en_text

col_map = {
    '商品名称': 'Product', '颜色': 'Variant', '进价成本': 'Cost', '售卖价格': 'Price',
    '应收到数量': 'Expected', '展示数量': 'Display', '货柜数量': 'Cabinet', '储物间数量': 'Storage', 
    '坏货数量': 'Damaged', '已售出数量': 'Total Sold', '总库存': 'Total Stock', '期间售出': 'Period Sales',
    '订单号': 'Order ID', '日期': 'Date', '收银员': 'Cashier', '销售数量': 'Qty', '成交单价': 'Unit Price', 
    '总营业额': 'Total Amount', '小计': 'Subtotal', '有效客流': 'Traffic',
    '员工姓名': 'Staff Name', '职位': 'Role', '时薪': 'Hourly Wage', '状态': 'Status',
    '创建日期': 'Create Date', '客户名称': 'Client', '采购数量': 'Purchase Qty', 'B2B单价': 'B2B Price',
    '总计应收': 'Total Recv.', '已收定金': 'Deposit', '待收尾款': 'Balance', '约定交期': 'Deadline', '订单状态': 'Order Status', '备注': 'Notes',
    '记录日期': 'Log Date', '操作类型': 'Operation', '变动数量': 'Change Qty', '库位详情': 'Location Det.',
    '开始时间': 'Start Time', '结束时间': 'End Time', '工作时长': 'Hours', '核算薪资': 'Est. Wage',
    '内购单号': 'Staff Purchase ID', '购买数量': 'Purchase Qty', '内购单价': 'Staff Price',
    '扣款金额': 'Deduction Amount', '成本合计': 'Cost Total', '记录人': 'Recorded By', '是否扣库存': 'Deduct Stock'
}

val_map_cn_to_en = {
    "黑": "Black", "金缮": "Kintsugi", "墨金": "Ink Gold", "银霜": "Silver", "黑玉": "Black Jade",
    "陨星黑": "Meteorite Black", "陨星": "Meteorite", "天蓝": "Sky Blue", 
    "金色": "Gold", "蓝色": "Blue", "灰色": "Grey", "银色": "Silver", "黑色": "Black", "默认": "Default", "多件混装": "Mixed Combo",
    "粉色": "Pink", "绿色": "Green", "紫色": "Purple", "枫叶红": "Maple Red",
    "口红杯": "Lipstick Cup", "咖啡吸管杯 480ml": "Coffee Cup With Straw 480 ML", "臻享 焖茶壶": "Brew Bottle", "冲锋壶680ML": "Canteen Bottle 680ML",
    "焖茶杯": "Brew Bottle", "纯钛酒壶": "Pure Ti Wine Flask", "直滤杯": "Flat Bottom", "冲锋壶": "Canteen",
    "咖啡杯": "Coffee Cup With Straw", "口袋杯": "Pocket Cup", "筷子": "Chopstick", "保温壶": "Thermal Flask",
    "托盘": "Tray", "盘子": "Plate", "叶碟": "Leaf Plate", "随心杯": "Easy Cup", "主人杯": "Host Cup",
    "迷你杯": "Mini Cup", "钛艺T杯": "Ti Artisan Bottle", "圆融杯": "Round cup",
    "钛杯": "Titanium Cup", "常规水杯": "Standard Cup", "低价配件": "Accessories", "T杯": "T-Cup", "钛碗": "Titanium Bowl",
    "在职": "Active", "离职": "Resigned", "店长": "Manager", "全职店员": "Full-time", "兼职店员": "Part-time", "实习生": "Intern", "合作厂商": "Supplier", "其他": "Other",
    "意向/沟通中": "In Communication", "已付定金/备货中": "Deposit Paid", "已发货/待结尾款": "Shipped/Pending", "✅ 订单已完成": "✅ Completed",
    "入库": "Inbound", "调拨": "Transfer", "盘盈": "Surplus (+)", "盘亏": "Shortage (-)", "初始建档": "Initial Setup"
}
val_map_en_to_cn = {v: k for k, v in val_map_cn_to_en.items()}

def t_val(val, to_lang):
    if pd.isna(val): return ""
    val_str = str(val).strip()
    if to_lang == 'en': return val_map_cn_to_en.get(val_str, val_str)
    else: return val_map_en_to_cn.get(val_str, val_str)

def translate_series(series):
    if st.session_state.lang == 'en':
        return series.fillna('').astype(str).map(lambda x: val_map_cn_to_en.get(x.strip(), x.strip()))
    return series.fillna('').astype(str)

# ---------- 稳定性工具函数：避免 Google Sheet 空值/非法数字导致 ValueError ----------
def to_int(value, default=0):
    v = pd.to_numeric(value, errors='coerce')
    return int(v) if pd.notna(v) else default

def to_float(value, default=0.0):
    v = pd.to_numeric(value, errors='coerce')
    return float(v) if pd.notna(v) else default

def recalc_total_stock(df, idx):
    return sum(to_int(df.at[idx, col]) for col in ['展示数量', '货柜数量', '储物间数量'])

# POS 出库策略：用【总库存】判断是否可卖，但实际扣减仍从具体库位扣，避免库位出现负数。
def deduct_pos_stock_from_locations(df, idx, qty, priority=None):
    if priority is None:
        priority = ['货柜数量', '展示数量', '储物间数量']
    remaining = int(qty)
    for col in priority:
        available = to_int(df.at[idx, col])
        if available <= 0:
            continue
        take = min(available, remaining)
        df.at[idx, col] = available - take
        remaining -= take
        if remaining <= 0:
            break
    df.at[idx, '总库存'] = recalc_total_stock(df, idx)
    return remaining == 0

def split_sku_label(label):
    label = str(label)
    if " (" not in label:
        return label.strip(), ""
    name, color = label.rsplit(" (", 1)
    return name.strip(), color.replace(")", "").strip()

# 日期区间默认值：从今天到今天。
# 之前这里固定为 2026/03/26，导致每次打开毛利/考勤/净利润等区间都要从 3 月手动调到当天。
def date_range_picker(label_cn, label_en, key, default_start=None, default_end=None):
    today = datetime.now().date()
    start_default = default_start if default_start is not None else today
    end_default = default_end if default_end is not None else today
    selected = st.date_input(
        t(label_cn, label_en),
        value=(start_default, end_default),
        key=key
    )
    if isinstance(selected, (list, tuple)):
        if len(selected) >= 2:
            start_date, end_date = selected[0], selected[1]
        elif len(selected) == 1:
            start_date = end_date = selected[0]
        else:
            start_date, end_date = start_default, end_default
    else:
        start_date = end_date = selected
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    st.caption(t(f"当前查询日期：{start_date} 至 {end_date}", f"Current range: {start_date} to {end_date}"))
    return start_date, end_date

def filter_by_date_range(df, date_col, start_date, end_date):
    if df.empty or date_col not in df.columns:
        return df.copy()
    out = df.copy()
    out['_date_filter_dt'] = pd.to_datetime(out[date_col], errors='coerce').dt.date
    out = out.dropna(subset=['_date_filter_dt'])
    out = out[(out['_date_filter_dt'] >= start_date) & (out['_date_filter_dt'] <= end_date)]
    return out.drop(columns=['_date_filter_dt'])

def sort_sales_latest_first(df):
    """让最新 POS 流水显示在最上面。append_rows 会把新数据写到 Sheet 底部，
    如果界面不排序，用户会误以为销售记录没有更新。"""
    if df.empty:
        return df.copy()
    out = df.copy()
    order_str = out['订单号'].fillna('').astype(str) if '订单号' in out.columns else pd.Series('', index=out.index)
    # 支持 ORD-20260520-133803 和 ORD-20260520-133803-123456 两种格式。
    extracted = order_str.str.extract(r'(\d{8}-\d{6})', expand=False)
    out['_order_sort_dt'] = pd.to_datetime(extracted, format='%Y%m%d-%H%M%S', errors='coerce')
    out['_date_sort_dt'] = pd.to_datetime(out['日期'], errors='coerce') if '日期' in out.columns else pd.NaT
    out['_orig_sort_pos'] = range(len(out))
    out = out.sort_values(
        by=['_order_sort_dt', '_date_sort_dt', '_orig_sort_pos'],
        ascending=[False, False, False],
        na_position='last'
    )
    return out.drop(columns=['_order_sort_dt', '_date_sort_dt', '_orig_sort_pos'], errors='ignore')

def append_rows_data(sheet_name, rows, columns):
    if not rows:
        return
    try:
        worksheet = get_worksheet_cached(sheet_name)
    except WorksheetNotFound:
        worksheet = sh.add_worksheet(title=sheet_name, rows="1000", cols=str(max(20, len(columns) + 5)))
        worksheet.update(values=[columns], range_name='A1')

    safe_rows = [["" if pd.isna(v) else str(v) for v in row] for row in rows]
    last_error = None
    for attempt in range(3):
        try:
            worksheet.append_rows(safe_rows, value_input_option="USER_ENTERED")
            # 写入成功后必须清掉全局 cache。否则刷新页面后新 session 的 sheet_versions 会回到 0，
            # 可能命中旧的 load_raw_data(sheet_name, 0) 缓存，导致新销售/SKU/补货看起来消失。
            st.session_state.sheet_versions[sheet_name] = st.session_state.sheet_versions.get(sheet_name, 0) + 1
            invalidate_data_cache(sheet_name)
            return
        except APIError as e:
            last_error = e
            msg = str(e)
            if ('429' in msg or 'Quota exceeded' in msg) and attempt < 2:
                pytime.sleep(2 + attempt * 3)
                continue
            st.error(f"🔴 追加写入 {sheet_name} 失败。Google Sheets 额度可能暂时超限，请等 30-60 秒再试。Error: {e}")
            st.stop()
        except Exception as e:
            last_error = e
            st.error(f"🔴 追加写入 {sheet_name} 失败。请检查网络/Google Sheet权限后重试。Error: {e}")
            st.stop()
    st.error(f"🔴 追加写入 {sheet_name} 失败。Error: {last_error}")
    st.stop()

# ================= 🚀 数据定义与初始化 =================
DEFAULT_CATEGORY_SYSTEM = "titanium"
SYSTEM_PERMISSION_COL = "可进入系统"
CATEGORY_SYSTEMS = {
    "titanium": {
        "label": "钛杯系统",
        "stock": "Stock",
        "sales": "Sales",
        "restock": "Restock_Log",
        "traffic": "Traffic_Log",
        "campaign": "Campaigns",
        "b2b": "B2B_Orders",
        "feedback": "Feedback",
        "staff_purchase": "Staff_Purchases",
    },
    "silk": {
        "label": "丝绸系统",
        "stock": "Silk_Stock",
        "sales": "Silk_Sales",
        "restock": "Silk_Restock_Log",
        "traffic": "Silk_Traffic_Log",
        "campaign": "Silk_Campaigns",
        "b2b": "Silk_B2B_Orders",
        "feedback": "Silk_Feedback",
        "staff_purchase": "Silk_Staff_Purchases",
    },
}

def get_category_system_config(system_key):
    system_key = str(system_key or DEFAULT_CATEGORY_SYSTEM).strip()
    return CATEGORY_SYSTEMS.get(system_key, CATEGORY_SYSTEMS[DEFAULT_CATEGORY_SYSTEM])

def resolve_system_sheets(system_key):
    config = get_category_system_config(system_key)
    return {k: config[k] for k in ["stock", "sales", "restock", "traffic", "campaign", "b2b", "feedback", "staff_purchase"]}

def parse_allowed_systems(value):
    raw = "" if value is None else str(value)
    normalized = raw.replace("，", ",")
    labels = {cfg["label"]: key for key, cfg in CATEGORY_SYSTEMS.items()}
    allowed = []
    for part in normalized.split(","):
        token = part.strip()
        if not token:
            continue
        key = labels.get(token, token)
        if key in CATEGORY_SYSTEMS and key not in allowed:
            allowed.append(key)
    if not allowed:
        allowed = [DEFAULT_CATEGORY_SYSTEM]
    return [key for key in CATEGORY_SYSTEMS if key in allowed]

def get_active_system_from_state(state):
    selected = state.get("current_category_system", DEFAULT_CATEGORY_SYSTEM)
    return selected if selected in CATEGORY_SYSTEMS else DEFAULT_CATEGORY_SYSTEM

def choose_employee_default_system(allowed_systems):
    allowed = [s for s in allowed_systems if s in CATEGORY_SYSTEMS]
    if len(allowed) == 1:
        return allowed[0]
    return None

ACTIVE_CATEGORY_SYSTEM = get_active_system_from_state(st.session_state)
ACTIVE_SYSTEM_CONFIG = get_category_system_config(ACTIVE_CATEGORY_SYSTEM)
ACTIVE_SYSTEM_SHEETS = resolve_system_sheets(ACTIVE_CATEGORY_SYSTEM)

STOCK_SHEET = ACTIVE_SYSTEM_SHEETS["stock"]
SALES_SHEET = ACTIVE_SYSTEM_SHEETS["sales"]
EMP_SHEET = "Employee"
ATT_SHEET = "Attendance"
B2B_SHEET = ACTIVE_SYSTEM_SHEETS["b2b"]
FEEDBACK_SHEET = ACTIVE_SYSTEM_SHEETS["feedback"]
RESTOCK_SHEET = ACTIVE_SYSTEM_SHEETS["restock"]
TRAFFIC_SHEET = ACTIVE_SYSTEM_SHEETS["traffic"]
CAMP_SHEET = ACTIVE_SYSTEM_SHEETS["campaign"]
STAFF_PURCHASE_SHEET = ACTIVE_SYSTEM_SHEETS["staff_purchase"]

STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '应收到数量', '展示数量', '货柜数量', '储物间数量', '坏货数量', '已售出数量', '总库存']
SALES_COLS = ['订单号', '日期', '收银员', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']
EMP_COLS = ['员工姓名', '职位', '时薪', '联系方式', '入职日期', '登录密码', '状态', SYSTEM_PERMISSION_COL]
ATT_COLS = ['员工姓名', '日期', '开始时间', '结束时间', '工作时长', '核算薪资']
B2B_COLS = ['创建日期', '客户名称', '商品名称', '颜色', '采购数量', 'B2B单价', '总计应收', '货物成本', '物流成本', '关税', '已收定金', '待收尾款', '约定交期', '订单状态', '备注']
FEEDBACK_COLS = ['反馈日期', '商品名称', '客户画像', '反馈类型', '详细原话', '跟进状态']
RESTOCK_COLS = ['记录日期', '操作类型', '商品名称', '颜色', '变动数量', '库位详情', '单件成本', '备注']
TRAFFIC_COLS = ['日期', '有效客流']
CAMP_COLS = ['档期名称', '开始日期', '结束日期']
STAFF_PURCHASE_COLS = ['内购单号', '日期', '员工姓名', '商品名称', '颜色', '购买数量', '内购单价', '扣款金额', '成本合计', '记录人', '是否扣库存', '备注']

all_sheets = [STOCK_SHEET, SALES_SHEET, EMP_SHEET, ATT_SHEET, B2B_SHEET, FEEDBACK_SHEET, RESTOCK_SHEET, TRAFFIC_SHEET, CAMP_SHEET, STAFF_PURCHASE_SHEET]

if "sheet_versions" not in st.session_state:
    st.session_state.sheet_versions = {s: 0 for s in all_sheets}


def invalidate_data_cache(sheet_name=None):
    """
    清掉 Streamlit 的全局数据缓存。
    原因：st.cache_data 是跨 session 共享的；如果用户刷新页面后 sheet_versions 归零，
    可能重新读到旧的 version=0 缓存，造成新增销售/SKU/补货看起来"消失"。
    每次写入成功后清缓存，确保刷新/重新登录也能看到 Google Sheet 最新数据。
    """
    try:
        load_raw_data.clear()
    except Exception:
        try:
            st.cache_data.clear()
        except Exception:
            pass


@st.cache_resource(show_spinner=False)
def get_worksheet_cached(sheet_name):
    # 缓存 worksheet 对象，避免每次 rerun 都先请求一次 worksheet metadata。
    return sh.worksheet(sheet_name)

@st.cache_data(ttl=900, show_spinner=False)
def load_raw_data(sheet_name, version):
    last_error = None
    for attempt in range(3):
        try:
            worksheet = get_worksheet_cached(sheet_name)
            records = worksheet.get_all_records()
            if not records:
                return pd.DataFrame()
            return pd.DataFrame(records)
        except WorksheetNotFound:
            # 新表允许为空；保存时会自动创建
            return pd.DataFrame()
        except APIError as e:
            last_error = e
            msg = str(e)
            if '429' in msg or 'Quota exceeded' in msg or 'Read requests per minute' in msg:
                if attempt < 2:
                    pytime.sleep(2 + attempt * 3)
                    continue
                st.error(
                    f"🔴 Google Sheets 读取额度暂时超限。系统已自动重试但仍失败。"
                    f"请等 30-60 秒再刷新，不要连续猛点刷新。Sheet: {sheet_name}. Error: {e}"
                )
                st.stop()
            st.error(f"🔴 读取 {sheet_name} 失败，请检查 Google Sheet 权限。Error: {e}")
            st.stop()
        except Exception as e:
            last_error = e
            # 重要：不要把网络/API错误伪装成空表，否则下一次保存可能覆盖掉真实数据
            st.error(f"🔴 读取 {sheet_name} 失败，请刷新重试或检查 Google Sheet 权限。Error: {e}")
            st.stop()
    st.error(f"🔴 读取 {sheet_name} 失败。Error: {last_error}")
    st.stop()

def load_data(sheet_name, columns):
    ver = st.session_state.sheet_versions.get(sheet_name, 0)
    df = load_raw_data(sheet_name, ver)
    if df.empty:
        df = pd.DataFrame(columns=columns)
    for col in columns:
        if col not in df.columns: 
            df[col] = "" 
    return df[columns]

def save_data(df, sheet_name):
    try:
        worksheet = get_worksheet_cached(sheet_name)
    except WorksheetNotFound:
        worksheet = sh.add_worksheet(title=sheet_name, rows="1000", cols="20")

    df_safe = df.fillna("").astype(str)
    data_to_upload = [df_safe.columns.values.tolist()] + df_safe.values.tolist()

    try:
        # 先扩容再写入；绝对不要先 worksheet.clear()，否则网络中断会留下空表
        min_rows = max(1000, len(data_to_upload) + 100)
        min_cols = max(20, len(df_safe.columns) + 5)
        if worksheet.row_count < min_rows or worksheet.col_count < min_cols:
            worksheet.resize(rows=max(worksheet.row_count, min_rows), cols=max(worksheet.col_count, min_cols))

        worksheet.update(values=data_to_upload, range_name='A1')

        # 写入成功后再清理旧数据尾巴；即使清理失败，也不会丢失新数据
        next_row = len(data_to_upload) + 1
        if worksheet.row_count >= next_row:
            worksheet.batch_clear([f"A{next_row}:ZZ{worksheet.row_count}"])

        # 写入成功后必须清掉全局 cache。否则刷新页面后新 session 的 sheet_versions 会回到 0，
        # 可能命中旧的 load_raw_data(sheet_name, 0) 缓存，导致新销售/SKU/补货看起来消失。
        st.session_state.sheet_versions[sheet_name] = st.session_state.sheet_versions.get(sheet_name, 0) + 1
        invalidate_data_cache(sheet_name)
    except Exception as e:
        st.error(f"🔴 保存 {sheet_name} 失败，数据没有被清空。请检查网络/Google Sheet权限后重试。Error: {e}")
        st.stop()

def clean_date_col(df, col_name):
    if not df.empty and col_name in df.columns:
        formatted = pd.to_datetime(df[col_name], errors='coerce').dt.strftime('%Y/%m/%d')
        df[col_name] = formatted.fillna('')
    return df

def load_safe_sales():
    df = clean_date_col(load_data(SALES_SHEET, SALES_COLS), '日期')
    if not df.empty:
        df['订单号'] = df['订单号'].fillna('').astype(str).replace('0', '历史单').replace('', '历史单').replace('nan', '历史单')
        if '收银员' not in df.columns:
            df['收银员'] = '店长/历史'
        else:
            df['收银员'] = df['收银员'].fillna('').astype(str).replace('0', '店长/历史').replace('', '店长/历史').replace('nan', '店长/历史')
    return df

def load_safe_emp():
    df = clean_date_col(load_data(EMP_SHEET, EMP_COLS), '入职日期') 
    if not df.empty:
        df['状态'] = df['状态'].fillna('').astype(str).replace('0', '在职').replace('', '在职').replace('nan', '在职')
        df['登录密码'] = df['登录密码'].fillna('').astype(str).replace('0', '').replace('nan', '')
        df[SYSTEM_PERMISSION_COL] = df[SYSTEM_PERMISSION_COL].fillna('').astype(str).replace('0', '').replace('nan', '')
        df[SYSTEM_PERMISSION_COL] = df[SYSTEM_PERMISSION_COL].replace('', CATEGORY_SYSTEMS[DEFAULT_CATEGORY_SYSTEM]["label"])
    return df

def JIT_fetch(sheets_to_fetch):
    # 写入/结账前需要取最新数据，但不能 load_raw_data.clear() 清空所有表缓存。
    # 这里只让本次真正需要的表失效，避免触发 Google Sheets per-minute read quota。
    for s_name in sheets_to_fetch:
        st.session_state.sheet_versions[s_name] = st.session_state.sheet_versions.get(s_name, 0) + 1

    res = {}
    if STOCK_SHEET in sheets_to_fetch: res[STOCK_SHEET] = load_data(STOCK_SHEET, STOCK_COLS)
    if SALES_SHEET in sheets_to_fetch: res[SALES_SHEET] = load_safe_sales()
    if RESTOCK_SHEET in sheets_to_fetch: res[RESTOCK_SHEET] = clean_date_col(load_data(RESTOCK_SHEET, RESTOCK_COLS), '记录日期')
    if B2B_SHEET in sheets_to_fetch: res[B2B_SHEET] = clean_date_col(clean_date_col(load_data(B2B_SHEET, B2B_COLS), '创建日期'), '约定交期')
    if FEEDBACK_SHEET in sheets_to_fetch: res[FEEDBACK_SHEET] = clean_date_col(load_data(FEEDBACK_SHEET, FEEDBACK_COLS), '反馈日期')
    if EMP_SHEET in sheets_to_fetch: res[EMP_SHEET] = load_safe_emp()
    if ATT_SHEET in sheets_to_fetch: res[ATT_SHEET] = clean_date_col(load_data(ATT_SHEET, ATT_COLS), '日期')
    if STAFF_PURCHASE_SHEET in sheets_to_fetch: res[STAFF_PURCHASE_SHEET] = clean_date_col(load_data(STAFF_PURCHASE_SHEET, STAFF_PURCHASE_COLS), '日期')
    if TRAFFIC_SHEET in sheets_to_fetch: res[TRAFFIC_SHEET] = clean_date_col(load_data(TRAFFIC_SHEET, TRAFFIC_COLS), '日期')
    if CAMP_SHEET in sheets_to_fetch: res[CAMP_SHEET] = clean_date_col(clean_date_col(load_data(CAMP_SHEET, CAMP_COLS), '开始日期'), '结束日期')
    return res

@st.cache_data(show_spinner=False)
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8-sig')

# 登录页只需要 Employee 表。不要在登录前一次性读取所有 Sheet，否则刷新/多人打开会很容易触发 429。
df_stock = pd.DataFrame(columns=STOCK_COLS)
df_sales = pd.DataFrame(columns=SALES_COLS)
df_employee = load_safe_emp()
df_attendance = pd.DataFrame(columns=ATT_COLS)
df_staff_purchase = pd.DataFrame(columns=STAFF_PURCHASE_COLS)
df_b2b = pd.DataFrame(columns=B2B_COLS)
df_feedback = pd.DataFrame(columns=FEEDBACK_COLS)
df_restock = pd.DataFrame(columns=RESTOCK_COLS)
df_traffic = pd.DataFrame(columns=TRAFFIC_COLS)
df_campaign = pd.DataFrame(columns=CAMP_COLS)

if "stock_reset_key" not in st.session_state: st.session_state.stock_reset_key = 0
if "sales_reset_key" not in st.session_state: st.session_state.sales_reset_key = 0
if "emp_reset_key" not in st.session_state: st.session_state.emp_reset_key = 0
if "att_reset_key" not in st.session_state: st.session_state.att_reset_key = 0 
if "staff_purchase_reset_key" not in st.session_state: st.session_state.staff_purchase_reset_key = 0
if "b2b_reset_key" not in st.session_state: st.session_state.b2b_reset_key = 0 
if "fb_reset_key" not in st.session_state: st.session_state.fb_reset_key = 0 
if "camp_reset_key" not in st.session_state: st.session_state.camp_reset_key = 0
if "admin_page" not in st.session_state: st.session_state.admin_page = "main"

def clear_stock(): st.session_state.stock_reset_key += 1
def clear_sales(): st.session_state.sales_reset_key += 1
def clear_emp(): st.session_state.emp_reset_key += 1
def clear_att(): st.session_state.att_reset_key += 1
def clear_staff_purchase(): st.session_state.staff_purchase_reset_key += 1
def clear_b2b(): st.session_state.b2b_reset_key += 1
def clear_fb(): st.session_state.fb_reset_key += 1
def clear_campaign(): st.session_state.camp_reset_key += 1

manager_password = "taka888"

# 🚀 门禁系统角色解析
# 说明：Streamlit 的 session_state 在浏览器硬刷新/手机后台恢复时可能重置。
# 为了避免一刷新就掉回登录页，这里用 URL query params 保存一个轻量登录 token。
# token 会绑定角色、用户名和当前密码/PIN；员工改 PIN 后旧链接自动失效。
AUTH_SALT = "taka-retail-login-v2"

def _qp_get(name, default=""):
    try:
        val = st.query_params.get(name, default)
        if isinstance(val, list):
            return val[0] if val else default
        return default if val is None else str(val)
    except Exception:
        return default

def _auth_digest(role, user, secret):
    raw = f"{AUTH_SALT}|{role}|{user}|{secret}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def make_auth_token(role, user):
    role = str(role).strip()
    user = str(user).strip()
    if role == "admin":
        return _auth_digest("admin", "店长", manager_password)

    if role in ["employee", "supplier"] and not df_employee.empty:
        emp_matches = df_employee[df_employee['员工姓名'].fillna('').astype(str).str.strip() == user]
        if emp_matches.empty:
            return None
        emp_row_for_token = emp_matches.iloc[0]
        if str(emp_row_for_token.get('状态', '')).strip() == '离职':
            return None
        expected_role = "supplier" if str(emp_row_for_token.get('职位', '')).strip() == '合作厂商' else "employee"
        if expected_role != role:
            return None
        pin_secret = str(emp_row_for_token.get('登录密码', '')).strip()
        if pin_secret == "":
            return None
        return _auth_digest(role, user, pin_secret)
    return None

def restore_login_from_url():
    role = _qp_get("role")
    user = _qp_get("user", "店长" if role == "admin" else "")
    token = _qp_get("auth")
    if not role or not token:
        return False

    if role == "admin":
        user = "店长"
    elif role not in ["employee", "supplier"] or not user:
        return False

    expected_token = make_auth_token(role, user)
    if expected_token and hmac.compare_digest(str(token), str(expected_token)):
        st.session_state.role = role
        st.session_state.current_user = user
        if role in ["employee", "supplier"] and not df_employee.empty:
            emp_matches = df_employee[df_employee['员工姓名'].fillna('').astype(str).str.strip() == user]
            if not emp_matches.empty:
                apply_employee_system_access(emp_matches.iloc[0])
        return True
    return False

def persist_login_to_url(role, user):
    token = make_auth_token(role, user)
    if token:
        st.query_params["role"] = role
        st.query_params["user"] = user
        st.query_params["auth"] = token

def apply_employee_system_access(emp_row):
    allowed_systems = parse_allowed_systems(emp_row.get(SYSTEM_PERMISSION_COL, ""))
    st.session_state.allowed_category_systems = allowed_systems
    chosen_system = choose_employee_default_system(allowed_systems)
    st.session_state.current_category_system = chosen_system or allowed_systems[0]

if "role" not in st.session_state:
    if not restore_login_from_url():
        st.session_state.role = None
        st.session_state.current_user = None

# 日期筛选已改为各看板独立选择，不再使用侧边栏全局档期。

# ================= 🚀 侧边栏 =================
with st.sidebar:
    st.header(t("🔐 系统门禁", "🔐 System Access"))
    
    if st.session_state.role is not None:
        if st.session_state.role == "admin": user_emoji = "👑"
        elif st.session_state.role == "supplier": user_emoji = "🏭"
        else: user_emoji = "🧑‍💼"
        
        st.success(t(f"{user_emoji} 欢迎回来：{st.session_state.current_user}", f"{user_emoji} Welcome back: {st.session_state.current_user}"))
        st.caption(t(f"当前系统：{ACTIVE_SYSTEM_CONFIG['label']}", f"Current system: {ACTIVE_SYSTEM_CONFIG['label']}"))
        
        if st.button(t("🚪 退出系统 (交接班)", "🚪 Logout (Handover)"), use_container_width=True):
            st.session_state.role = None
            st.session_state.current_user = None
            st.session_state.allowed_category_systems = []
            st.query_params.clear()
            st.rerun()
            
        is_admin = (st.session_state.role == "admin")
        
        st.divider()
        
        if is_admin:
            system_keys = list(CATEGORY_SYSTEMS.keys())
            system_labels = [CATEGORY_SYSTEMS[key]["label"] for key in system_keys]
            current_idx = system_keys.index(ACTIVE_CATEGORY_SYSTEM) if ACTIVE_CATEGORY_SYSTEM in system_keys else 0
            selected_label = st.radio("当前系统", system_labels, index=current_idx, key="admin_category_system_selector")
            selected_key = system_keys[system_labels.index(selected_label)]
            if selected_key != st.session_state.get("current_category_system", DEFAULT_CATEGORY_SYSTEM):
                st.session_state.current_category_system = selected_key
                st.rerun()
            st.divider()
            st.header("🛠️ 核心管理")
            with st.expander("➕ 新增产品建档 (Add SKU)"):
                with st.form("new_sku"):
                    n_name = st.text_input("产品名称")
                    n_color = st.text_input("颜色")
                    c1, c2, c3 = st.columns(3)
                    n_cost = c1.number_input("进价", format="%.2f")
                    n_price = c2.number_input("售价", format="%.2f")
                    n_expect = c3.number_input("应收")
                    i1, i2, i3, i4 = st.columns(4)
                    n_disp = i1.number_input("展示")
                    n_shelf = i2.number_input("货柜")
                    n_stor = i3.number_input("储物")
                    n_dmg = i4.number_input("坏货")
                    if st.form_submit_button("确认建档"):
                        if n_name and n_color:
                            fresh = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET])
                            latest_stock, latest_restock = fresh[STOCK_SHEET], fresh[RESTOCK_SHEET]
                            total = n_disp + n_shelf + n_stor 
                            new_r = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, n_dmg, 0, total]], columns=STOCK_COLS)
                            latest_stock = pd.concat([latest_stock, new_r], ignore_index=True)
                            if total > 0 or n_dmg > 0:
                                log_date = datetime.now().strftime("%Y/%m/%d")
                                init_log = pd.DataFrame([[log_date, "初始建档", n_name, n_color, total+n_dmg, "多库位", n_cost, "系统建档"]], columns=RESTOCK_COLS)
                                latest_restock = pd.concat([init_log, latest_restock], ignore_index=True)
                                save_data(latest_restock, RESTOCK_SHEET)
                            save_data(latest_stock, STOCK_SHEET) 
                            st.success("✅ 云端建档成功！")
                            st.rerun()
            st.divider()
            if st.button("📅 档期中心 / Popup 对比", use_container_width=True):
                st.session_state.admin_page = "campaign_bi"
                st.rerun()
            if st.session_state.get("admin_page") == "campaign_bi":
                if st.button("↩️ 返回日常管理台", use_container_width=True):
                    st.session_state.admin_page = "main"
                    st.rerun()
        elif st.session_state.role == "employee":
            allowed_systems = st.session_state.get("allowed_category_systems", [DEFAULT_CATEGORY_SYSTEM])
            allowed_systems = [s for s in allowed_systems if s in CATEGORY_SYSTEMS] or [DEFAULT_CATEGORY_SYSTEM]
            if len(allowed_systems) > 1:
                system_labels = [CATEGORY_SYSTEMS[key]["label"] for key in allowed_systems]
                current_idx = allowed_systems.index(ACTIVE_CATEGORY_SYSTEM) if ACTIVE_CATEGORY_SYSTEM in allowed_systems else 0
                selected_label = st.radio("我的系统", system_labels, index=current_idx, key="employee_category_system_selector")
                selected_key = allowed_systems[system_labels.index(selected_label)]
                if selected_key != ACTIVE_CATEGORY_SYSTEM:
                    st.session_state.current_category_system = selected_key
                    st.rerun()
    
    else:
        login_type = st.radio(t("请选择您的身份", "Select Role"), [t("🧑‍💼 门店店员 / 🏭 合作厂商", "🧑‍💼 Staff / 🏭 Supplier"), t("👑 店长/管理员", "👑 Admin")], horizontal=True)
        
        if login_type == t("👑 店长/管理员", "👑 Admin"):
            pwd_input = st.text_input(t("输入授权密码", "Enter Admin Password"), type="password")
            if st.button(t("🔓 登录后台", "🔓 Login"), use_container_width=True):
                if hmac.compare_digest(str(pwd_input), str(manager_password)):
                    st.session_state.role = "admin"
                    st.session_state.current_user = "店长"
                    persist_login_to_url("admin", "店长")
                    st.rerun()
                else:
                    st.error(t("❌ 密码错误！", "❌ Incorrect Password!"))
        else:
            if df_employee.empty:
                st.warning(t("⚠️ 系统内暂无人员档案。请联系店长添加。", "⚠️ No staff records found. Contact Admin."))
            else:
                active_emps = df_employee[df_employee['状态'] != '离职']['员工姓名'].tolist()
                if not active_emps:
                    st.warning(t("⚠️ 系统中无在职人员。", "⚠️ No active staff found."))
                else:
                    emp_sel = st.selectbox(t("选择您的名字", "Select your name"), active_emps)
                    emp_row = df_employee[df_employee['员工姓名'] == emp_sel].iloc[0]
                    emp_pwd = str(emp_row['登录密码']).strip()
                    assigned_role = "supplier" if str(emp_row.get('职位', '')).strip() == '合作厂商' else "employee"
                    
                    if emp_pwd == "":
                        st.info(t("🌟 系统检测到您是首次登录，请设置专属 PIN 码。", "🌟 First time login. Please set your PIN."))
                        new_pwd = st.text_input(t("设置我的登录密码", "Set PIN"), type="password")
                        if st.button(t("💾 保存并进入系统", "💾 Save & Login"), use_container_width=True):
                            if new_pwd.strip() == "":
                                st.warning(t("密码不能为空哦！", "PIN cannot be empty!"))
                            else:
                                fresh_emp = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                                e_idx = fresh_emp[fresh_emp['员工姓名'].astype(str).str.strip() == str(emp_sel).strip()].index
                                if not e_idx.empty:
                                    fresh_emp.at[e_idx[0], '登录密码'] = new_pwd
                                    save_data(fresh_emp, EMP_SHEET)
                                    st.session_state.role = assigned_role
                                    st.session_state.current_user = emp_sel
                                    apply_employee_system_access(emp_row)
                                    persist_login_to_url(assigned_role, emp_sel)
                                    st.success("✅ 密码设置成功！")
                                    st.rerun()
                                else:
                                    st.error("⚠️ 未找到人员档案，无法设置密码。")
                    else:
                        emp_pwd_input = st.text_input(t("输入您的 PIN 码", "Enter PIN"), type="password")
                        if st.button(t("🔑 打卡/登录", "🔑 Login"), use_container_width=True):
                            if emp_pwd_input == emp_pwd:
                                st.session_state.role = assigned_role
                                st.session_state.current_user = emp_sel
                                apply_employee_system_access(emp_row)
                                persist_login_to_url(assigned_role, emp_sel)
                                st.rerun()
                            else:
                                st.error(t("❌ 密码不匹配！", "❌ Incorrect PIN!"))

if st.session_state.role is None:
    col_t, col_l = st.columns([8, 2])
    with col_t:
        st.title(t("🏙️ Takashimaya 零售管理系统", "🏙️ Takashimaya Retail System"))
    with col_l:
        lang_choice = st.radio("🌐 Language", ["中文", "English"], index=0 if st.session_state.lang == 'cn' else 1, horizontal=True)
        if (lang_choice == "中文" and st.session_state.lang != "cn") or (lang_choice == "English" and st.session_state.lang != "en"):
            st.session_state.lang = 'cn' if lang_choice == "中文" else 'en'
            st.rerun()
    st.info(t("👈 请在左侧选择您的身份并完成登录。", "👈 Please select your role on the left menu to login."))
    st.stop()  

# 登录后按身份懒加载数据：Admin 需要全量；员工/POS 只加载必要表；供应商只加载对账相关表。
role_now = st.session_state.get("role")
if role_now == "admin":
    df_stock = load_data(STOCK_SHEET, STOCK_COLS)
    df_sales = load_safe_sales()
    df_employee = load_safe_emp()
    df_attendance = clean_date_col(load_data(ATT_SHEET, ATT_COLS), '日期')
    df_staff_purchase = clean_date_col(load_data(STAFF_PURCHASE_SHEET, STAFF_PURCHASE_COLS), '日期')
    df_b2b = clean_date_col(clean_date_col(load_data(B2B_SHEET, B2B_COLS), '创建日期'), '约定交期')
    df_feedback = clean_date_col(load_data(FEEDBACK_SHEET, FEEDBACK_COLS), '反馈日期')
    df_restock = clean_date_col(load_data(RESTOCK_SHEET, RESTOCK_COLS), '记录日期')
    df_traffic = clean_date_col(load_data(TRAFFIC_SHEET, TRAFFIC_COLS), '日期')
    df_campaign = clean_date_col(clean_date_col(load_data(CAMP_SHEET, CAMP_COLS), '开始日期'), '结束日期')
elif role_now == "supplier":
    df_stock = load_data(STOCK_SHEET, STOCK_COLS)
    df_sales = load_safe_sales()
    df_restock = clean_date_col(load_data(RESTOCK_SHEET, RESTOCK_COLS), '记录日期')
    df_b2b = clean_date_col(clean_date_col(load_data(B2B_SHEET, B2B_COLS), '创建日期'), '约定交期')
elif role_now == "employee":
    df_stock = load_data(STOCK_SHEET, STOCK_COLS)
    df_sales = load_safe_sales()
    df_attendance = clean_date_col(load_data(ATT_SHEET, ATT_COLS), '日期')
    df_traffic = clean_date_col(load_data(TRAFFIC_SHEET, TRAFFIC_COLS), '日期')

# ================= 🚀 主界面布局 =================
col_title, col_lang = st.columns([8, 2])
with col_title:
    st.title(t("🏙️ Takashimaya 零售管理系统 (云端同步版)", "🏙️ Takashimaya Retail System (Cloud Sync)"))
    st.caption(t(f"当前系统：{ACTIVE_SYSTEM_CONFIG['label']}", f"Current system: {ACTIVE_SYSTEM_CONFIG['label']}"))
with col_lang:
    lang_choice = st.radio("🌐 Language", ["中文", "English"], index=0 if st.session_state.lang == 'cn' else 1, horizontal=True)
    if (lang_choice == "中文" and st.session_state.lang != "cn") or (lang_choice == "English" and st.session_state.lang != "en"):
        st.session_state.lang = 'cn' if lang_choice == "中文" else 'en'
        st.rerun()

q = st.text_input(t("🔍 全局筛查 (输入单号/客户/商品，过滤所有看板)...", "🔍 Quick Search..."), placeholder=t("搜商品/单号/客户...", "Search items/orders/customers..."))

def get_f(df, q):
    if q and not df.empty:
        mask = pd.Series(False, index=df.index)
        q_cn = t_val(q, 'cn')
        for col in df.columns:
            mask = mask | df[col].fillna('').astype(str).str.contains(q, case=False, regex=False) | df[col].fillna('').astype(str).str.contains(q_cn, case=False, regex=False)
        return df[mask]
    return df

is_admin = st.session_state.role == "admin"
is_supplier = st.session_state.role == "supplier"
is_employee = st.session_state.role == "employee"

def _campaign_options():
    if df_campaign.empty:
        return {}
    out = {}
    for _, row in df_campaign.iterrows():
        name = str(row.get('档期名称', '')).strip()
        try:
            start = pd.to_datetime(row.get('开始日期'), errors='coerce').date()
            end = pd.to_datetime(row.get('结束日期'), errors='coerce').date()
        except Exception:
            continue
        if name and pd.notna(start) and pd.notna(end):
            if start > end:
                start, end = end, start
            out[f"{name} ({start} 至 {end})"] = (name, start, end)
    return out

def _render_bi_table(df, key_prefix):
    if df.empty:
        st.info("这个范围内没有可分析的 SKU 数据。")
        return
    view = get_f(df, q).copy()
    if view.empty:
        st.info("没有符合全局搜索条件的 SKU。")
        return
    view['售罄率%'] = (pd.to_numeric(view['售罄率'], errors='coerce').fillna(0) * 100).round(1)
    view['毛利率%'] = (pd.to_numeric(view['毛利率'], errors='coerce').fillna(0) * 100).round(1)
    show_cols = [
        'SKU', '系统分类', '辅助标签', '期初库存', '本期入库', '本期可售量', '本期POS售出',
        '售罄率%', '日均销量', '当前库存', '库存年龄天数', '销售额',
        '单件毛利', '毛利率%', '毛利贡献', '动销分', '利润分', '换货参考数量'
    ]
    st.dataframe(
        view[show_cols].style.format({
            '售罄率%': '{:.1f}%',
            '毛利率%': '{:.1f}%',
            '日均销量': '{:.2f}',
            '销售额': '${:.2f}',
            '单件毛利': '${:.2f}',
            '毛利贡献': '${:.2f}',
            '动销分': '{:.1f}',
            '利润分': '{:.1f}',
        }),
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "⬇️ 导出当前 BI 明细 CSV",
        data=convert_df_to_csv(view),
        file_name=f"Takashimaya_Popup_BI_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        key=f"download_bi_{key_prefix}",
    )

def _pick_period(label, key_prefix):
    campaigns = _campaign_options()
    mode = st.radio(
        label,
        ["选择已保存档期", "临时日期范围"],
        horizontal=True,
        key=f"{key_prefix}_mode",
    )
    if mode == "选择已保存档期" and campaigns:
        selected = st.selectbox("选择档期", list(campaigns.keys()), key=f"{key_prefix}_campaign")
        return campaigns[selected]
    if mode == "选择已保存档期" and not campaigns:
        st.warning("还没有保存档期，先用临时日期范围。")
    start, end = date_range_picker("📅 临时分析日期区间", "📅 BI Date Range", key=f"{key_prefix}_range")
    return ("临时日期范围", start, end)

def render_campaign_bi_center():
    st.title("📅 档期中心 / Popup 对比")
    st.caption("用于复盘每次 popup 的 SKU 动销、利润贡献、库存风险和两档期变化。动销评分只计算正常 POS 零售订单，不包含 B2B、员工内购和换货。")

    with st.expander("➕ 新增保存档期", expanded=df_campaign.empty):
        with st.form("add_campaign_form"):
            c1, c2, c3 = st.columns([2, 1, 1])
            camp_name = c1.text_input("档期名称", placeholder="例如：2026 高岛屋第一期 Popup")
            camp_start = c2.date_input("开始日期", value=datetime.now().date(), key="new_campaign_start")
            camp_end = c3.date_input("结束日期", value=datetime.now().date(), key="new_campaign_end")
            if st.form_submit_button("💾 保存档期", type="primary", use_container_width=True):
                if not camp_name.strip():
                    st.warning("档期名称不能为空。")
                else:
                    fresh_camp = JIT_fetch([CAMP_SHEET])[CAMP_SHEET]
                    new_row = pd.DataFrame([[camp_name.strip(), camp_start.strftime("%Y/%m/%d"), camp_end.strftime("%Y/%m/%d")]], columns=CAMP_COLS)
                    fresh_camp = pd.concat([fresh_camp, new_row], ignore_index=True)
                    save_data(fresh_camp[CAMP_COLS], CAMP_SHEET)
                    st.session_state.camp_reset_key += 1
                    st.success("✅ 档期已保存。")
                    st.rerun()

    if not df_campaign.empty:
        with st.expander("📋 已保存档期", expanded=False):
            camp_view = df_campaign.copy()
            camp_view.insert(0, "选择", False)
            edited_camp = st.data_editor(
                camp_view,
                column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)},
                disabled=[c for c in camp_view.columns if c != "选择"],
                use_container_width=True,
                hide_index=True,
                key=f"campaign_editor_{st.session_state.camp_reset_key}",
            )
            selected_camp = edited_camp[edited_camp["选择"] == True]
            if not selected_camp.empty:
                dc1, dc2, _ = st.columns([1.6, 1.4, 4])
                with dc1:
                    if st.button("🗑️ 删除选中档期", type="primary", key="delete_campaign"):
                        fresh_camp = JIT_fetch([CAMP_SHEET])[CAMP_SHEET]
                        for _, row in selected_camp.iterrows():
                            fresh_camp = fresh_camp[~(
                                (fresh_camp['档期名称'].astype(str).str.strip() == str(row['档期名称']).strip()) &
                                (fresh_camp['开始日期'].astype(str).str.strip() == str(row['开始日期']).strip()) &
                                (fresh_camp['结束日期'].astype(str).str.strip() == str(row['结束日期']).strip())
                            )]
                        save_data(fresh_camp[CAMP_COLS], CAMP_SHEET)
                        st.session_state.camp_reset_key += 1
                        st.rerun()
                with dc2:
                    st.button("🔄 取消选中", key="cancel_campaign_selection", on_click=clear_campaign)

    mode_tab1, mode_tab2, mode_tab3, mode_tab4 = st.tabs(["📊 单档期复盘", "📈 档期看板", "⚖️ 双档期对比", "💎 档期财务对比"])

    with mode_tab1:
        period_name, start_date, end_date = _pick_period("选择单档期分析方式", "single_bi")
        bi_df = compute_period_sku_bi(df_stock, df_sales, df_restock, start_date, end_date)
        st.markdown(f"### {period_name}：{start_date} 至 {end_date}")
        if not bi_df.empty:
            total_sold = pd.to_numeric(bi_df['本期POS售出'], errors='coerce').fillna(0).sum()
            total_revenue = pd.to_numeric(bi_df['销售额'], errors='coerce').fillna(0).sum()
            total_profit = pd.to_numeric(bi_df['毛利贡献'], errors='coerce').fillna(0).sum()
            avg_sell_through = pd.to_numeric(bi_df['售罄率'], errors='coerce').fillna(0).mean() * 100
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("本期 POS 售出", f"{int(total_sold)} 件")
            m2.metric("本期销售额", f"${total_revenue:.2f}")
            m3.metric("毛利贡献", f"${total_profit:.2f}")
            m4.metric("SKU 平均售罄率", f"{avg_sell_through:.1f}%")

            category_order = ["潜力款", "畅销款", "常规款", "滞销款", "无库存/未参与"]
            category_counts = bi_df['系统分类'].value_counts().reindex(category_order).fillna(0).astype(int)
            st.bar_chart(category_counts, use_container_width=True)

            category_tabs = st.tabs(["全部"] + category_order)
            with category_tabs[0]:
                _render_bi_table(bi_df.sort_values(['动销分', '利润分'], ascending=False), "all")
            for tab, cat in zip(category_tabs[1:], category_order):
                with tab:
                    cat_df = bi_df[bi_df['系统分类'] == cat].sort_values(['动销分', '利润分'], ascending=False)
                    _render_bi_table(cat_df, cat)
        else:
            st.info("当前档期没有可分析数据。")

    with mode_tab2:
        campaigns = _campaign_options()
        if campaigns:
            labels = list(campaigns.keys())
            selected_label = st.selectbox("选择档期看板", labels, index=0, key="dashboard_period")
            period = campaigns[selected_label]
            dashboard = compute_period_dashboard(df_stock, df_sales, df_attendance, df_traffic, period[1], period[2])
            summary = dashboard["summary"]
            daily = dashboard["daily"]

            st.markdown(f"### {period[0]}：{period[1]} 至 {period[2]}")
            st.info("这个看板把「毛利」和「净利润」tab 的核心数据按已保存档期汇总。")

            d1, d2, d3 = st.columns(3)
            d1.metric("有效客流", f"{summary['有效客流']} 人")
            d2.metric("交易单数", f"{summary['交易单数']} 单")
            d3.metric("购买转化率", f"{summary['购买转化率%']:.1f}%")

            st.divider()
            d4, d5, d6 = st.columns(3)
            d4.metric("总营业额", f"${summary['总营业额']:,.2f}")
            d5.metric("平均客单价 ACV", f"${summary['平均客单价']:,.2f}")
            d6.metric("连带率 UPT", f"{summary['连带率']:.2f} 件/单")

            st.divider()
            d7, d8, d9, d10 = st.columns(4)
            d7.metric("具体毛利", f"${summary['具体毛利']:,.2f}")
            d8.metric("总售出件数", f"{summary['总售出件数']} 件")
            d9.metric("平均毛利率", f"{summary['平均毛利率%']:.1f}%")
            d10.metric("日均营收", f"${summary['日均营收']:,.2f}")

            st.divider()
            d11, d12, d13, d14 = st.columns(4)
            d11.metric("剥离 GST (9%)", f"${summary['代扣GST(9%)']:,.2f}")
            d12.metric("商场抽成 (36%)", f"${summary['商场抽成(36%)']:,.2f}")
            d13.metric("商场实际回款", f"${summary['商场实际回款']:,.2f}")
            d14.metric("真实净利润", f"${summary['真实净利润']:,.2f}", delta=f"净利率 {summary['含税净利率%']:.1f}%")

            st.divider()
            d15, d16 = st.columns(2)
            d15.metric("商品进价成本", f"${summary['总进价成本']:,.2f}")
            d16.metric("打卡人工成本", f"${summary['人工成本']:,.2f}")

            if not daily.empty:
                chart_df = daily.set_index("日期")[["总营业额", "具体毛利", "真实净利润"]].sort_index()
                st.markdown("### 每日营收 / 毛利 / 净利润走势")
                st.bar_chart(chart_df, use_container_width=True)
                st.markdown("### 每日明细")
                st.dataframe(
                    daily.style.format({
                        "总营业额": "${:.2f}",
                        "具体毛利": "${:.2f}",
                        "真实净利润": "${:.2f}",
                        "销售数量": "{:.0f}",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("这个档期暂无销售流水，无法生成每日走势。")
        else:
            st.info("请先保存至少 1 个档期，再使用档期看板。")

    with mode_tab3:
        campaigns = _campaign_options()
        if len(campaigns) >= 2:
            c1, c2 = st.columns(2)
            labels = list(campaigns.keys())
            label_a = c1.selectbox("档期 A", labels, index=0, key="compare_period_a")
            label_b = c2.selectbox("档期 B", labels, index=1 if len(labels) > 1 else 0, key="compare_period_b")
            period_a = campaigns[label_a]
            period_b = campaigns[label_b]
            compared = compare_periods(df_stock, df_sales, df_restock, period_a, period_b)
            if not compared.empty:
                compared = get_f(compared, q).copy()
                compared['A_售罄率%'] = (pd.to_numeric(compared['A_售罄率'], errors='coerce').fillna(0) * 100).round(1)
                compared['B_售罄率%'] = (pd.to_numeric(compared['B_售罄率'], errors='coerce').fillna(0) * 100).round(1)
                compared['售罄率变化%'] = (pd.to_numeric(compared['售罄率变化'], errors='coerce').fillna(0) * 100).round(1)
                show_cols = [
                    'SKU', 'A_本期POS售出', 'B_本期POS售出', '售出变化',
                    'A_售罄率%', 'B_售罄率%', '售罄率变化%',
                    'A_销售额', 'B_销售额', '销售额变化',
                    'A_毛利贡献', 'B_毛利贡献', '毛利贡献变化', '分类变化'
                ]
                c_top1, c_top2, c_top3 = st.columns(3)
                c_top1.metric("售出变化合计", f"{int(pd.to_numeric(compared['售出变化'], errors='coerce').fillna(0).sum())} 件")
                c_top2.metric("销售额变化合计", f"${pd.to_numeric(compared['销售额变化'], errors='coerce').fillna(0).sum():.2f}")
                c_top3.metric("毛利变化合计", f"${pd.to_numeric(compared['毛利贡献变化'], errors='coerce').fillna(0).sum():.2f}")
                st.dataframe(
                    compared[show_cols].style.format({
                        'A_售罄率%': '{:.1f}%',
                        'B_售罄率%': '{:.1f}%',
                        '售罄率变化%': '{:+.1f}%',
                        'A_销售额': '${:.2f}',
                        'B_销售额': '${:.2f}',
                        '销售额变化': '${:+.2f}',
                        'A_毛利贡献': '${:.2f}',
                        'B_毛利贡献': '${:.2f}',
                        '毛利贡献变化': '${:+.2f}',
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
                st.download_button(
                    "⬇️ 导出双档期对比 CSV",
                    data=convert_df_to_csv(compared),
                    file_name=f"Takashimaya_Popup_Compare_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    key="download_bi_compare",
                )
            else:
                st.info("两个档期没有可比较的 SKU 数据。")
        else:
            st.info("请先至少保存 2 个档期，再使用双档期对比。")

    with mode_tab4:
        campaigns = _campaign_options()
        if len(campaigns) >= 2:
            st.info("财务口径沿用「净利润」tab：含税营业额剥离 9% GST，商场 36% 抽成按免税净额计算，再扣商品成本和打卡人工成本。")
            c1, c2 = st.columns(2)
            labels = list(campaigns.keys())
            label_a = c1.selectbox("财务档期 A", labels, index=0, key="finance_period_a")
            label_b = c2.selectbox("财务档期 B", labels, index=1 if len(labels) > 1 else 0, key="finance_period_b")
            period_a = campaigns[label_a]
            period_b = campaigns[label_b]
            summary_a = compute_period_financials(df_stock, df_sales, df_attendance, period_a[1], period_a[2])
            summary_b = compute_period_financials(df_stock, df_sales, df_attendance, period_b[1], period_b[2])
            finance_compare = compare_financial_periods(df_stock, df_sales, df_attendance, period_a, period_b)

            def _fmt_money(v):
                return f"${float(v):,.2f}"

            def _fmt_delta(metric):
                row = finance_compare[finance_compare["指标"] == metric]
                if row.empty:
                    return "0.0%"
                change = float(row.iloc[0]["变化率%"])
                sign = "+" if change > 0 else ""
                return f"{sign}{change:.1f}% vs A"

            st.markdown(f"### {period_a[0]} vs {period_b[0]}")
            st.caption(f"档期 A：{period_a[1]} 至 {period_a[2]}｜档期 B：{period_b[1]} 至 {period_b[2]}")

            top1, top2, top3, top4 = st.columns(4)
            top1.metric("B 总营业额", _fmt_money(summary_b["总营业额"]), delta=_fmt_delta("总营业额"))
            top2.metric("B 商场实际回款", _fmt_money(summary_b["商场实际回款"]), delta=_fmt_delta("商场实际回款"))
            top3.metric("B 真实净利润", _fmt_money(summary_b["真实净利润"]), delta=_fmt_delta("真实净利润"))
            top4.metric("B 含税净利率", f"{summary_b['含税净利率%']:.1f}%", delta=_fmt_delta("含税净利率%"))

            st.divider()
            compare_view = finance_compare.copy()
            compare_view["A值显示"] = compare_view.apply(lambda r: f"{r['A值']:.1f}%" if r["指标"] == "含税净利率%" else f"${r['A值']:,.2f}", axis=1)
            compare_view["B值显示"] = compare_view.apply(lambda r: f"{r['B值']:.1f}%" if r["指标"] == "含税净利率%" else f"${r['B值']:,.2f}", axis=1)
            compare_view["变化显示"] = compare_view.apply(lambda r: f"{r['变化']:+.1f} pct" if r["指标"] == "含税净利率%" else f"${r['变化']:+,.2f}", axis=1)
            compare_view["变化率显示"] = compare_view["变化率%"].apply(lambda x: f"{x:+.1f}%")
            st.dataframe(
                compare_view[["指标", "A值显示", "B值显示", "变化显示", "变化率显示"]].rename(columns={
                    "A值显示": "档期A",
                    "B值显示": "档期B",
                    "变化显示": "B-A变化",
                    "变化率显示": "B相对A变化率",
                }),
                use_container_width=True,
                hide_index=True,
            )

            chart_df = pd.DataFrame([
                {"档期": "A", "总营业额": summary_a["总营业额"], "真实净利润": summary_a["真实净利润"], "商场实际回款": summary_a["商场实际回款"]},
                {"档期": "B", "总营业额": summary_b["总营业额"], "真实净利润": summary_b["真实净利润"], "商场实际回款": summary_b["商场实际回款"]},
            ]).set_index("档期")
            st.bar_chart(chart_df, use_container_width=True)

            st.download_button(
                "⬇️ 导出档期财务对比 CSV",
                data=convert_df_to_csv(finance_compare),
                file_name=f"Takashimaya_Finance_Compare_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                key="download_finance_compare",
            )
        else:
            st.info("请先至少保存 2 个档期，再使用档期财务对比。")

if is_admin and st.session_state.get("admin_page") == "campaign_bi":
    render_campaign_bi_center()
    st.stop()

if is_admin:
    t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([t("📊 库存", "📊 Inventory"), t("💰 销售", "💰 Sales"), t("📈 毛利", "📈 Margin"), t("👥 考勤", "👥 Staff"), t("💎 净利润", "💎 Net Profit"), t("🤝 B2B订单", "🤝 B2B"), t("🗣️ 客户反馈", "🗣️ Feedback"), t("🧠 战略(BI)", "🧠 BI")])
elif is_supplier:
    t1, t2, t3, t4 = st.tabs([t("📊 实时库存快照", "📊 Inventory Snapshot"), t("💰 销售报表对账", "💰 Sales Report"), t("📦 进货对账 (ERP流水)", "📦 Inbound Records"), t("🤝 B2B订单对账", "🤝 B2B Orders")])
else:
    t1, t2, t3 = st.tabs([t("📊 实时库存查询", "📊 Inventory Snapshot"), t("🛒 智能POS收银台", "🛒 Smart POS"), t("⏰ 考勤打卡", "⏰ Timeclock")])

# ================= 🚀 公共核心组件函数化 (防丢利器) =================

def render_inventory_snapshot(role_prefix):
    st.subheader(t(f"📊 实时库存与期间动销快照", f"📊 Real-time Inventory & Sales Snapshot"))
    
    t1_start, t1_end = date_range_picker("📅 期间售出日期区间", "📅 Period Sales Date Range", key=f"inventory_range_today_{role_prefix}")
    st.info(f"📅 此看板的【期间售出】按上方日期区间计算：**{t1_start}** 至 **{t1_end}**")
        
    f_stock = get_f(df_stock, q)
    if not f_stock.empty:
        v_df = f_stock.copy()
        
        period_sales = pd.DataFrame()
        if not df_sales.empty:
            df_s_t1 = df_sales.copy()
            df_s_t1['日期_dt'] = pd.to_datetime(df_s_t1['日期'], errors='coerce')
            f_s_t1 = df_s_t1[(df_s_t1['日期_dt'] >= pd.Timestamp(t1_start)) & (df_s_t1['日期_dt'] <= pd.Timestamp(t1_end))]
            if not f_s_t1.empty:
                f_s_t1['销售数量'] = pd.to_numeric(f_s_t1['销售数量'], errors='coerce').fillna(0)
                period_sales = f_s_t1.groupby(['商品名称', '颜色'])['销售数量'].sum().reset_index()
                period_sales.rename(columns={'销售数量': '期间售出'}, inplace=True)
        
        if not period_sales.empty:
            v_df = v_df.merge(period_sales, on=['商品名称', '颜色'], how='left')
        else:
            v_df['期间售出'] = 0
            
        v_df['期间售出'] = v_df['期间售出'].fillna(0).astype(int)
        
        int_cols = ['应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '期间售出']
        for col in int_cols: 
            if col in v_df.columns:
                v_df[col] = pd.to_numeric(v_df[col], errors='coerce').fillna(0).astype(int)
                
        v_df['进价成本'] = pd.to_numeric(v_df['进价成本'], errors='coerce').fillna(0.0)
        v_df['售卖价格'] = pd.to_numeric(v_df['售卖价格'], errors='coerce').fillna(0.0)
        
        def calc_margin(row):
            price = row['售卖价格']
            cost = row['进价成本']
            if price > 0:
                return f"{((price - cost) / price * 100):.1f}%"
            return "0.0%"
            
        v_df['单品毛利率'] = v_df.apply(calc_margin, axis=1)
        v_df.insert(0, "选择", False)
        
        v_df['商品名称'] = translate_series(v_df['商品名称'])
        v_df['颜色'] = translate_series(v_df['颜色'])
        
        if role_prefix in ['supplier', 'employee']:
            display_cols = ['商品名称', '颜色', '期间售出', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '售卖价格'] if role_prefix == 'supplier' else ['商品名称', '颜色', '期间售出', '总库存', '展示数量', '货柜数量', '储物间数量', '售卖价格']
            df_disp = v_df[display_cols].copy()
            if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
            p_col = 'Price' if st.session_state.lang == 'en' else '售卖价格'
            st.dataframe(df_disp.style.format({p_col: '${:.2f}'}), use_container_width=True, hide_index=True)
            
        elif role_prefix == 'admin':
            display_cols = ['选择', '商品名称', '颜色', '期间售出', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '售卖价格', '进价成本', '单品毛利率']
            df_disp = v_df[display_cols].copy()
            if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
            
            p_col = 'Price' if st.session_state.lang == 'en' else '售卖价格'
            c_col = 'Cost' if st.session_state.lang == 'en' else '进价成本'
            stk_col = 'Total Stock' if st.session_state.lang == 'en' else '总库存'
            sel_col_name = "Sel" if st.session_state.lang == 'en' else "选择"
            
            def highlight_low_stock(row):
                try:
                    if int(row[stk_col]) <= 2: return ['background-color: #ffe6e6; color: #cc0000; font-weight: bold;'] * len(row)
                except: pass
                return [''] * len(row)
                
            styled_df = df_disp.style.format({c_col: '${:.2f}', p_col: '${:.2f}'}).apply(highlight_low_stock, axis=1)
            d_disable = [c for c in df_disp.columns if c not in ["选择", "Sel"]]
            
            edited_stock = st.data_editor(
                styled_df,
                column_config={sel_col_name: st.column_config.CheckboxColumn(sel_col_name, default=False)},
                disabled=d_disable,
                use_container_width=True, hide_index=True, 
                key=f"stock_editor_{st.session_state.stock_reset_key}"
            )
            
            selected_stock = edited_stock[edited_stock[sel_col_name] == True] if sel_col_name in edited_stock.columns else pd.DataFrame()
            
            if len(selected_stock) == 1:
                st.markdown("### ⚙️ SKU 档案修改机")
                
                orig_disp_name = str(selected_stock.iloc[0]['Product' if st.session_state.lang == 'en' else '商品名称'])
                orig_disp_color = str(selected_stock.iloc[0]['Variant' if st.session_state.lang == 'en' else '颜色'])
                
                real_orig_name = t_val(orig_disp_name, 'cn')
                real_orig_color = t_val(orig_disp_color, 'cn')
                
                raw_cost = str(selected_stock.iloc[0][c_col]).replace('$', '').replace(',', '')
                raw_price = str(selected_stock.iloc[0][p_col]).replace('$', '').replace(',', '')
                orig_cost = float(raw_cost) if raw_cost else 0.0
                orig_price = float(raw_price) if raw_price else 0.0

                with st.form("edit_base_info"):
                    ec1, ec2 = st.columns([1.5, 1.5])
                    e_name = ec1.text_input("Product Name (CN)", value=real_orig_name)
                    e_color = ec2.text_input("Variant/Color (CN)", value=real_orig_color)
                    ec4, ec5 = st.columns([1.5, 1.5])
                    e_cost = ec4.number_input("Cost ($)", value=orig_cost, format="%.2f")
                    e_price = ec5.number_input("Price ($)", value=orig_price, format="%.2f")
                    
                    if st.form_submit_button("💾 Save Changes", type="primary"):
                        fresh = JIT_fetch([STOCK_SHEET, SALES_SHEET, B2B_SHEET, RESTOCK_SHEET])
                        latest_stock = fresh[STOCK_SHEET]
                        latest_sales = fresh[SALES_SHEET]
                        latest_b2b = fresh[B2B_SHEET]
                        latest_restock = fresh[RESTOCK_SHEET]
                        
                        m_idx = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(real_orig_name).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(real_orig_color).strip())].index
                        if not m_idx.empty:
                            idx = m_idx[0]
                            latest_stock.loc[idx, ['商品名称', '颜色', '进价成本', '售卖价格']] = [e_name, e_color, e_cost, e_price]
                            
                            if e_name != real_orig_name or e_color != real_orig_color:
                                if not latest_sales.empty:
                                    latest_sales.loc[(latest_sales['商品名称'].astype(str).str.strip() == str(real_orig_name).strip()) & (latest_sales['颜色'].astype(str).str.strip() == str(real_orig_color).strip()), ['商品名称', '颜色']] = [e_name, e_color]
                                    save_data(latest_sales, SALES_SHEET)
                                if not latest_restock.empty:
                                    latest_restock.loc[(latest_restock['商品名称'].astype(str).str.strip() == str(real_orig_name).strip()) & (latest_restock['颜色'].astype(str).str.strip() == str(real_orig_color).strip()), ['商品名称', '颜色']] = [e_name, e_color]
                                    save_data(latest_restock, RESTOCK_SHEET)
                                if not latest_b2b.empty:
                                    latest_b2b.loc[(latest_b2b['商品名称'].astype(str).str.strip() == str(real_orig_name).strip()) & (latest_b2b['颜色'].astype(str).str.strip() == str(real_orig_color).strip()), ['商品名称', '颜色']] = [e_name, e_color]
                                    save_data(latest_b2b, B2B_SHEET)
                            
                            save_data(latest_stock, STOCK_SHEET)
                            st.session_state.stock_reset_key += 1
                            st.success(f"✅ Product updated!")
                            st.rerun()
                        else:
                            st.error(f"⚠️ 在云端找不到商品档案，可能含有隐藏空格或已被删除。")

                if not selected_stock.empty:
                    col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 4])
                    with col_btn1:
                        if st.button("🗑️ 危险：彻底删档选中 (Delete)", type="primary", key="del_stock"):
                            fresh_stock = JIT_fetch([STOCK_SHEET])[STOCK_SHEET]
                            for _, row in selected_stock.iterrows():
                                d_n = row['Product' if st.session_state.lang == 'en' else '商品名称']
                                d_c = row['Variant' if st.session_state.lang == 'en' else '颜色']
                                fresh_stock = fresh_stock[~((fresh_stock['商品名称'].astype(str).str.strip() == t_val(d_n, 'cn').strip()) & (fresh_stock['颜色'].astype(str).str.strip() == t_val(d_c, 'cn').strip()))]
                            save_data(fresh_stock, STOCK_SHEET) 
                            st.session_state.stock_reset_key += 1 
                            st.rerun()
                    with col_btn2: 
                        st.button("🔄 取消选中", key="btn_cancel_stock", on_click=clear_stock)


def render_pos_engine(role_prefix):
    st.subheader(t("🛒 智能 POS 收银台 (多件合并结账)", "🛒 Smart POS Cashier"))
    
    pos_col1, pos_col2 = st.columns([1.2, 1.5])
    
    f_opts = get_f(df_stock, "").copy() 
    if not f_opts.empty:
        f_opts['disp_name'] = translate_series(f_opts['商品名称']).fillna('').astype(str)
        f_opts['disp_color'] = translate_series(f_opts['颜色']).fillna('').astype(str)
        f_opts['label'] = f_opts['disp_name'] + " (" + f_opts['disp_color'] + ")" 
        
        with pos_col1:
            with st.container(border=True):
                st.markdown(t("#### 1️⃣ 扫码/点单区", "#### 1️⃣ Scan / Order"))
                
                search_kw = st.text_input(t("🔍 键盘输入搜商品 (自动过滤下拉菜单)", "🔍 Type to search item"), key=f"pos_search_{role_prefix}")
                filtered_opts = f_opts[f_opts['label'].str.contains(search_kw, case=False, na=False)] if search_kw else f_opts
                
                if not filtered_opts.empty:
                    s_l = st.selectbox(t("选择商品", "Select Item"), filtered_opts['label'], key=f"pos_item_{role_prefix}")
                    selected_row = filtered_opts[filtered_opts['label'] == s_l].iloc[0]
                    base_price = to_float(selected_row['售卖价格'])
                    
                    c_q, c_d = st.columns(2)
                    s_q = c_q.number_input(t("销售数量", "Qty"), min_value=1, value=1, step=1, key=f"pos_qty_{role_prefix}")
                    d_opts = {"无折扣 (原价)": 1.0, "95折": 0.95, "9折": 0.90, "85折": 0.85, "8折": 0.80, "75折": 0.75, "7折": 0.70, "5折 (半价)": 0.50} if st.session_state.lang == 'cn' else {"No Discount": 1.0, "5% Off": 0.95, "10% Off": 0.90, "15% Off": 0.85, "20% Off": 0.80, "25% Off": 0.75, "30% Off": 0.70, "50% Off": 0.50}
                    s_discount = c_d.selectbox(t("快捷折扣", "Discount"), list(d_opts.keys()), key=f"pos_disc_{role_prefix}")
                    
                    auto_calc_price = round(base_price * d_opts[s_discount], 2)
                    price_key = f"pos_final_p_{role_prefix}"
                    price_sig_key = f"pos_final_price_sig_{role_prefix}"
                    price_sig = f"{s_l}|{s_discount}|{base_price:.4f}"
                    
                    # Streamlit 的 number_input 有 key 后，会优先保留旧的 session_state。
                    # 所以必须在商品/折扣变化时，主动把成交价刷新成新的折后价；
                    # 但如果商品和折扣没变，允许店员手动改价，不会被反复覆盖。
                    if st.session_state.get(price_sig_key) != price_sig:
                        st.session_state[price_key] = float(auto_calc_price)
                        st.session_state[price_sig_key] = price_sig
                    
                    s_p = st.number_input(
                        t("此单品最终成交价 ($)", "Final Price per item ($)"),
                        format="%.2f",
                        key=price_key,
                        help=t("会根据所选商品和折扣自动刷新，也可以手动改价。", "Auto-updates by selected item/discount, but can be manually overridden.")
                    )
                    st.caption(t(f"系统折后价：${auto_calc_price:.2f}，如需特殊价格可直接手动修改上方金额。", f"Auto discounted price: ${auto_calc_price:.2f}. You can manually override the amount above."))
                    
                    if st.button(t("➕ 加入当前购物车", "➕ Add to Cart"), use_container_width=True, key=f"btn_add_cart_{role_prefix}"):
                        if "pos_cart" not in st.session_state:
                            st.session_state.pos_cart = []
                        st.session_state.pos_cart.append({
                            "real_name": str(selected_row['商品名称']),
                            "real_color": str(selected_row['颜色']),
                            "disp_name": str(selected_row['disp_name']),
                            "disp_color": str(selected_row['disp_color']),
                            "数量": s_q,
                            "单价": s_p,
                            "小计": s_q * s_p
                        })
                        st.rerun()
                else:
                    st.warning(t("未找到符合条件的商品。", "No item found."))

        with pos_col2:
            with st.container(border=True):
                st.markdown(t("#### 2️⃣ 当前购物车", "#### 2️⃣ Current Cart"))
                if not st.session_state.get("pos_cart"):
                    st.info(t("🛒 购物车空空如也。", "🛒 Cart is empty."))
                else:
                    cart_df = pd.DataFrame(st.session_state.pos_cart)
                    df_disp = cart_df[['disp_name', 'disp_color', '数量', '单价', '小计']].copy()
                    df_disp.columns = ['商品名称', '颜色', '数量', '单价', '小计']
                    if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
                    u_col = 'Unit Price' if st.session_state.lang == 'en' else '单价'
                    s_col = 'Subtotal' if st.session_state.lang == 'en' else '小计'
                    st.dataframe(df_disp.style.format({u_col: '${:.2f}', s_col: '${:.2f}'}), use_container_width=True, hide_index=True)
                    
                    cart_total_qty = cart_df['数量'].sum()
                    cart_total_amt = cart_df['小计'].sum()
                    
                    st.markdown(f"**{t('🛍️ 本单共计:', '🛍️ Total Qty:')}** `{cart_total_qty}` &nbsp;&nbsp;|&nbsp;&nbsp; **{t('💰 合计应收:', '💰 Total Pay:')}** ` ${cart_total_amt:.2f}`")
                    
                    if role_prefix == "admin":
                        co_col1, co_col_staff, co_col2 = st.columns([1.1, 1.4, 1])
                        s_d = co_col1.date_input(t("交易日期 (可补录)", "Transaction Date"), value=datetime.now(), key=f"pos_date_{role_prefix}")

                        cashier_options = ["店长"]
                        if not df_employee.empty:
                            active_staff_df = df_employee[df_employee['状态'].fillna('').astype(str).str.strip() != '离职'].copy()
                            if '职位' in active_staff_df.columns:
                                active_staff_df = active_staff_df[active_staff_df['职位'].fillna('').astype(str).str.strip() != '合作厂商']
                            staff_names = active_staff_df['员工姓名'].fillna('').astype(str).str.strip().tolist()
                            cashier_options += [name for name in staff_names if name and name not in cashier_options]

                        curr_user = co_col_staff.selectbox(
                            t("实际销售员工", "Actual salesperson"),
                            cashier_options,
                            key=f"pos_cashier_{role_prefix}",
                            help=t("管理员代录销售时，这里选择真正完成销售的员工。", "When admin records a sale, choose the employee who actually made the sale."),
                        )
                    else:
                        co_col1, co_col2 = st.columns([2, 1])
                        s_d = co_col1.date_input(t("交易日期 (可补录)", "Transaction Date"), value=datetime.now(), key=f"pos_date_{role_prefix}")
                        curr_user = st.session_state.get("current_user", "Unknown")
                    
                    if co_col2.button(t("🗑️ 清空购物车", "🗑️ Clear Cart"), use_container_width=True, key=f"btn_clear_cart_{role_prefix}"):
                        st.session_state.pos_cart = []
                        st.rerun()
                        
                    if st.button(t("💳 确认结账 (生成流水)", "💳 Checkout"), type="primary", use_container_width=True, key=f"btn_checkout_{role_prefix}"):
                        fresh = JIT_fetch([STOCK_SHEET])
                        latest_stock = fresh[STOCK_SHEET]
                        
                        order_id = "ORD-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                        order_date = s_d.strftime("%Y/%m/%d")
                        
                        new_rows = []
                        stock_errors = []
                        cart_required = {}

                        # 先按 SKU 汇总购物车数量，避免同一个商品分两行加入时绕过库存检查。
                        for item in st.session_state.pos_cart:
                            key = (str(item['real_name']).strip(), str(item['real_color']).strip())
                            cart_required[key] = cart_required.get(key, 0) + int(item['数量'])

                        # POS 现在看【总库存】是否足够；总库存按 展示+货柜+储物 实时重算，避免 Google Sheet 里的旧值误导。
                        for (real_n, real_c), need_qty in cart_required.items():
                            idx_p = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == real_n) & (latest_stock['颜色'].astype(str).str.strip() == real_c)].index
                            if idx_p.empty:
                                stock_errors.append(f"找不到商品：{real_n} ({real_c})")
                                continue
                            i_p = idx_p[0]
                            current_total = recalc_total_stock(latest_stock, i_p)
                            latest_stock.at[i_p, '总库存'] = current_total
                            if current_total < need_qty:
                                stock_errors.append(f"{real_n} ({real_c}) 总库存不足：现有 {current_total}，需要 {need_qty}")

                        if stock_errors:
                            st.error("⚠️ 无法结账：\n" + "\n".join(stock_errors))
                            st.stop()

                        for item in st.session_state.pos_cart:
                            real_n = str(item['real_name']).strip()
                            real_c = str(item['real_color']).strip()
                            sell_qty = int(item['数量'])
                            new_rows.append([order_id, order_date, curr_user, real_n, real_c, sell_qty, item['单价'], item['小计']])
                            idx_p = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == real_n) & (latest_stock['颜色'].astype(str).str.strip() == real_c)].index
                            i_p = idx_p[0]
                            ok = deduct_pos_stock_from_locations(latest_stock, i_p, sell_qty)
                            if not ok:
                                st.error(f"⚠️ 出库失败：{real_n} ({real_c}) 库位库存和总库存不一致，请刷新后重试。")
                                st.stop()
                            latest_stock.at[i_p, '已售出数量'] = to_int(latest_stock.at[i_p, '已售出数量']) + sell_qty
                        
                        save_data(latest_stock, STOCK_SHEET)
                        append_rows_data(SALES_SHEET, new_rows, SALES_COLS)
                        
                        # 让结账后的销售流水表立即换 key 并刷新；否则 data_editor 可能保留旧 widget 状态，
                        # 同时新流水 append 在 Sheet 底部，用户会误以为没有更新。
                        st.session_state.sales_reset_key += 1
                        st.session_state.stock_reset_key += 1
                        st.session_state.last_order_id = order_id
                        
                        st.session_state.pos_cart = []
                        st.success(t(f"🎉 结账成功！流水号 {order_id}", f"🎉 Checkout Success! ID: {order_id}"))
                        st.rerun()
                        
    else:
        st.info(t("请先在库存中添加商品。", "Please add items to stock first."))

    st.divider()
    
    with st.expander(t("🚶‍♂️ 录入/修正每日有效客流", "🚶‍♂️ Daily Traffic Log"), expanded=False):
        with st.form(f"traffic_form_{role_prefix}"):
            tc1, tc2 = st.columns(2)
            tr_date = tc1.date_input(t("📅 客流日期", "📅 Date"), value=datetime.now())
            tr_num = tc2.number_input(t("👁️ 有效咨询/看货人数", "👁️ Traffic Count"), min_value=0, step=1, value=0)
            
            if st.form_submit_button(t("💾 保存今日客流数据", "💾 Save Traffic Data"), type="primary", use_container_width=True):
                fresh_traffic = JIT_fetch([TRAFFIC_SHEET])[TRAFFIC_SHEET]
                tr_date_str = tr_date.strftime("%Y/%m/%d")
                
                idx = fresh_traffic[fresh_traffic['日期'].astype(str).str.strip() == tr_date_str].index
                if not idx.empty:
                    fresh_traffic.at[idx[0], '有效客流'] = tr_num
                else:
                    new_row = pd.DataFrame([[tr_date_str, tr_num]], columns=TRAFFIC_COLS)
                    fresh_traffic = pd.concat([new_row, fresh_traffic], ignore_index=True)
                
                save_data(fresh_traffic, TRAFFIC_SHEET)
                st.success("✅ Saved!")
                st.rerun()

    with st.expander(t("🔄 客户换货处理 (Exchange)", "🔄 Item Exchange"), expanded=False):
        if not f_opts.empty:
            xc1, xc2 = st.columns(2)
            with xc1:
                st.markdown(t("### 🔙 退回的商品 (入库)", "### 🔙 Return Item"))
                ex_ret_l = st.selectbox("1. Return Item", f_opts['label'], key=f"ex_ret_sku_{role_prefix}")
                ret_row = f_opts[f_opts['label'] == ex_ret_l].iloc[0]
                ret_base_p = to_float(ret_row['售卖价格'])
                ret_p = st.number_input("2. Return Value ($)", value=ret_base_p, format="%.2f", key=f"ret_val_{role_prefix}")
                ret_dmg = st.checkbox(t("⚠️ 退回商品有瑕疵 (记入坏货)", "⚠️ Item Damaged"), value=False, key=f"dmg_{role_prefix}")

            with xc2:
                st.markdown(t("### 🆕 换购的商品 (出库)", "### 🆕 New Item"))
                ex_new_l = st.selectbox("1. New Item", f_opts['label'], key=f"ex_new_sku_{role_prefix}")
                new_row = f_opts[f_opts['label'] == ex_new_l].iloc[0]
                new_base_p = to_float(new_row['售卖价格'])
                new_p = st.number_input("2. New Item Price ($)", value=new_base_p, format="%.2f", key=f"new_val_{role_prefix}")

            st.markdown("---")
            
            c_date, c_diff = st.columns(2)
            with c_date:
                ex_date_input = st.date_input("📅 Date", value=datetime.now(), key=f"ex_date_input_{role_prefix}")
            
            with c_diff:
                diff = new_p - ret_p
                if diff > 0:
                    st.warning(t(f"💰 需补差价：${diff:.2f}", f"💰 Customer Pays: ${diff:.2f}"))
                elif diff < 0:
                    st.success(t(f"💸 需退差价：${abs(diff):.2f}", f"💸 Refund Customer: ${abs(diff):.2f}"))
                else:
                    st.info(t("🤝 等价交换", "🤝 Even Exchange"))

            if st.button(t("🔄 确认执行换货", "🔄 Confirm Exchange"), type="primary", use_container_width=True, key=f"btn_exchange_{role_prefix}"):
                fresh = JIT_fetch([STOCK_SHEET, SALES_SHEET])
                latest_stock = fresh[STOCK_SHEET]
                latest_sales = fresh[SALES_SHEET]
                
                ex_date = ex_date_input.strftime("%Y/%m/%d")
                ex_order_id = "EXC-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") 
                curr_user = st.session_state.get("current_user", "Unknown")
                
                r_name = t_val(ret_row['disp_name'], 'cn')
                r_col = t_val(ret_row['disp_color'], 'cn')
                n_name = t_val(new_row['disp_name'], 'cn')
                n_col = t_val(new_row['disp_color'], 'cn')
                
                idx_ret_list = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(r_name).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(r_col).strip())].index
                idx_new_list = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(n_name).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(n_col).strip())].index
                if idx_ret_list.empty or idx_new_list.empty:
                    st.error("⚠️ 换货失败：退回或换购商品在最新库存表中不存在，请刷新后重试。")
                    st.stop()
                idx_ret = idx_ret_list[0]
                idx_new = idx_new_list[0]
                if to_int(latest_stock.at[idx_new, '货柜数量']) < 1:
                    st.error(f"⚠️ 换货失败：{n_name} ({n_col}) 货柜库存不足。")
                    st.stop()
                s_ret = pd.DataFrame([[ex_order_id, ex_date, curr_user, latest_stock.at[idx_ret,'商品名称'], latest_stock.at[idx_ret,'颜色'], -1, ret_p, -1 * ret_p]], columns=SALES_COLS)
                s_new = pd.DataFrame([[ex_order_id, ex_date, curr_user, latest_stock.at[idx_new,'商品名称'], latest_stock.at[idx_new,'颜色'], 1, new_p, 1 * new_p]], columns=SALES_COLS)
                
                latest_sales = pd.concat([s_new, s_ret, latest_sales], ignore_index=True)
                
                if ret_dmg:
                    latest_stock.at[idx_ret, '坏货数量'] = to_int(latest_stock.at[idx_ret, '坏货数量']) + 1
                else:
                    latest_stock.at[idx_ret, '货柜数量'] = to_int(latest_stock.at[idx_ret, '货柜数量']) + 1
                    latest_stock.at[idx_ret, '总库存'] = recalc_total_stock(latest_stock, idx_ret)
                latest_stock.at[idx_ret, '已售出数量'] = to_int(latest_stock.at[idx_ret, '已售出数量']) - 1
                
                latest_stock.at[idx_new, '货柜数量'] = to_int(latest_stock.at[idx_new, '货柜数量']) - 1
                latest_stock.at[idx_new, '已售出数量'] = to_int(latest_stock.at[idx_new, '已售出数量']) + 1
                latest_stock.at[idx_new, '总库存'] = recalc_total_stock(latest_stock, idx_new)
                
                save_data(latest_sales, SALES_SHEET) 
                save_data(latest_stock, STOCK_SHEET) 
                st.success("✅ Exchange Success!")
                st.rerun()

# =========================================================================================
# ================================== 🚀 Admin 专属代码 ======================================
# =========================================================================================
if is_admin:
    with t1:
        f_opts_stk = df_stock.copy()
        stock_list_labels = []
        if not f_opts_stk.empty:
            f_opts_stk['disp_name'] = translate_series(f_opts_stk['商品名称']).fillna('').astype(str)
            f_opts_stk['disp_color'] = translate_series(f_opts_stk['颜色']).fillna('').astype(str)
            f_opts_stk['label'] = f_opts_stk['disp_name'] + " (" + f_opts_stk['disp_color'] + ")"
            stock_list_labels = f_opts_stk['label'].tolist()
            
        st.subheader("📦 专业 ERP 库存与货位管家")
        t1_a, t1_b, t1_c = st.tabs(["📥 1. 补货入库 (Restock)", "🔄 2. 货位调拨 (Transfer)", "⚖️ 3. 盘点平账 (Adjust)"])
        
        with t1_a:
            with st.form("form_restock"):
                c1, c2, c3 = st.columns(3)
                r_sku = c1.selectbox("选择到货商品", stock_list_labels) if stock_list_labels else c1.selectbox("选择到货商品", ["请先在侧边栏新增商品"])
                r_date = c2.date_input("入库日期", value=datetime.now())
                r_loc = c3.selectbox("卸货存放至", ["储物间数量", "货柜数量", "展示数量"])
                
                c4, c5, c6 = st.columns(3)
                r_qty = c4.number_input("入库数量", min_value=1, step=1, value=50)
                r_cost = c5.number_input("此批单件进价 ($) - 留空不改", value=0.0, format="%.2f")
                r_note = c6.text_input("备注单号或说明", placeholder="如：国内空运第3批...")
                
                if st.form_submit_button("✅ 确认入库", type="primary", use_container_width=True):
                    if stock_list_labels:
                        fresh = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET])
                        latest_stock = fresh[STOCK_SHEET]
                        latest_restock = fresh[RESTOCK_SHEET]
                        
                        sel_disp_name = r_sku.rsplit(" (", 1)[0]
                        sel_disp_color = r_sku.rsplit(" (", 1)[1].replace(")", "")
                        real_name = t_val(sel_disp_name, 'cn')
                        real_color = t_val(sel_disp_color, 'cn')
                        
                        match_idx = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(real_name).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(real_color).strip())].index
                        if not match_idx.empty:
                            idx = match_idx[0]
                            latest_stock.at[idx, r_loc] = to_int(latest_stock.at[idx, r_loc]) + r_qty
                            latest_stock.at[idx, '总库存'] = recalc_total_stock(latest_stock, idx)
                            if r_cost > 0: latest_stock.at[idx, '进价成本'] = r_cost 
                                
                            new_log = pd.DataFrame([[
                                r_date.strftime("%Y/%m/%d"), "入库", real_name, real_color, r_qty, 
                                f"存入: {r_loc.replace('数量','')}", r_cost, r_note
                            ]], columns=RESTOCK_COLS)
                            
                            latest_restock = pd.concat([new_log, latest_restock], ignore_index=True)
                            save_data(latest_stock, STOCK_SHEET)
                            save_data(latest_restock, RESTOCK_SHEET)
                            st.success(f"🎉 补货成功！已入库 {r_qty} 件至【{r_loc.replace('数量','')}】。")
                            st.rerun()
                        else:
                            st.error(f"⚠️ 找不到对应商品：{real_name} ({real_color})，请检查是否已被删除。")

        with t1_b:
            with st.form("form_transfer"):
                c1, c2, c3, c4 = st.columns(4)
                t_sku = c1.selectbox("选择调拨商品", stock_list_labels, key="t_sku") if stock_list_labels else c1.selectbox("选择", ["空"])
                t_src = c2.selectbox("从何处移出 (源)", ["储物间数量", "货柜数量", "展示数量"])
                t_dst = c3.selectbox("移到何处去 (目标)", ["货柜数量", "展示数量", "储物间数量"])
                t_qty = c4.number_input("移动数量", min_value=1, step=1, value=10)
                
                if st.form_submit_button("🔄 确认移库", type="primary", use_container_width=True):
                    if stock_list_labels and t_src != t_dst:
                        fresh = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET])
                        latest_stock = fresh[STOCK_SHEET]
                        latest_restock = fresh[RESTOCK_SHEET]
                        
                        sel_disp_name = t_sku.rsplit(" (", 1)[0]
                        sel_disp_color = t_sku.rsplit(" (", 1)[1].replace(")", "")
                        real_name = t_val(sel_disp_name, 'cn')
                        real_color = t_val(sel_disp_color, 'cn')
                        
                        match_idx = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(real_name).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(real_color).strip())].index
                        if not match_idx.empty:
                            idx = match_idx[0]
                            curr_src_qty = to_int(latest_stock.at[idx, t_src])
                            if curr_src_qty < t_qty:
                                st.error(f"⚠️ {t_src.replace('数量','')} 库存不足！仅剩 {curr_src_qty} 件。")
                            else:
                                latest_stock.at[idx, t_src] = curr_src_qty - t_qty
                                latest_stock.at[idx, t_dst] = to_int(latest_stock.at[idx, t_dst]) + t_qty
                                
                                new_log = pd.DataFrame([[
                                    datetime.now().strftime("%Y/%m/%d"), "调拨", real_name, real_color, t_qty, 
                                    f"{t_src.replace('数量','')} -> {t_dst.replace('数量','')}", 0, "内部货架整理"
                                ]], columns=RESTOCK_COLS)
                                
                                latest_restock = pd.concat([new_log, latest_restock], ignore_index=True)
                                save_data(latest_stock, STOCK_SHEET)
                                save_data(latest_restock, RESTOCK_SHEET)
                                st.success("✅ 移库成功！总库存数量不变。")
                                st.rerun()
                        else:
                            st.error(f"⚠️ 找不到对应商品：{real_name} ({real_color})。")

        with t1_c:
            with st.form("form_adjust"):
                c1, c2, c3, c4 = st.columns(4)
                a_sku = c1.selectbox("选择需平账商品", stock_list_labels, key="a_sku") if stock_list_labels else c1.selectbox("选择", ["空"])
                a_loc = c2.selectbox("发生差异的库位", ["货柜数量", "展示数量", "储物间数量", "坏货数量"])
                a_diff = c3.number_input("盘点差异 (+为盘盈, -为盘亏丢失)", value=0, step=1, help="例如发现被偷了1件，填 -1")
                a_note = c4.text_input("平账原因 (必填)", placeholder="例如：盘点发现丢失...")
                
                submitted = st.form_submit_button("⚖️ 确认记账", type="primary", use_container_width=True)
                if submitted:
                    if not stock_list_labels or a_sku == "空":
                        st.error("⚠️ 当前没有可供平账的商品档案！")
                    elif a_diff == 0:
                        st.error("⚠️ 盘点差异不能为 0！(填0等于没修改库存)")
                    elif a_note.strip() == "":
                        st.error("⚠️ 平账原因不能为空！请简要填写由于什么导致的差异，方便查账。")
                    else:
                        fresh = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET])
                        latest_stock = fresh[STOCK_SHEET]
                        latest_restock = fresh[RESTOCK_SHEET]
                        
                        sel_disp_name = a_sku.rsplit(" (", 1)[0]
                        sel_disp_color = a_sku.rsplit(" (", 1)[1].replace(")", "")
                        real_name = t_val(sel_disp_name, 'cn')
                        real_color = t_val(sel_disp_color, 'cn')
                        
                        match_idx = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(real_name).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(real_color).strip())].index
                        if not match_idx.empty:
                            idx = match_idx[0]
                            latest_stock.at[idx, a_loc] = to_int(latest_stock.at[idx, a_loc]) + a_diff
                            if a_loc != '坏货数量':
                                latest_stock.at[idx, '总库存'] = recalc_total_stock(latest_stock, idx)
                            
                            adj_type = "盘盈" if a_diff > 0 else "盘亏"
                            new_log = pd.DataFrame([[
                                datetime.now().strftime("%Y/%m/%d"), adj_type, real_name, real_color, a_diff, 
                                f"库位: {a_loc.replace('数量','')}", 0, a_note
                            ]], columns=RESTOCK_COLS)
                            
                            latest_restock = pd.concat([new_log, latest_restock], ignore_index=True)
                            save_data(latest_stock, STOCK_SHEET)
                            save_data(latest_restock, RESTOCK_SHEET)
                            st.success(f"✅ 盘点账目已抹平！记录类型：{adj_type}。")
                            st.rerun()
                        else:
                            st.error(f"⚠️ 找不到对应商品：{real_name} ({real_color})。")
        st.divider()

        # 🔥 调用统一的库存快照引擎
        render_inventory_snapshot('admin')
        
        with st.expander("📜 ERP底单：查看所有出入库/平账流水账", expanded=False):
            df_r_disp = get_f(df_restock, q).copy()
            df_r_disp['操作类型'] = translate_series(df_r_disp['操作类型'])
            df_r_disp['商品名称'] = translate_series(df_r_disp['商品名称'])
            df_r_disp['颜色'] = translate_series(df_r_disp['颜色'])
            if st.session_state.lang == 'en': df_r_disp.rename(columns=col_map, inplace=True)
            st.dataframe(df_r_disp, use_container_width=True)

    with t2:
        # 🔥 调用统一的 POS 收银引擎
        render_pos_engine('admin')
        
        st.divider()
        st.markdown("### 📝 销售流水编辑与防飞单机制")
        if st.session_state.get("last_order_id"):
            st.success(f"✅ 刚刚已写入销售流水：{st.session_state.last_order_id}。最新流水会显示在下方最上面。")
        if st.button("🔄 手动刷新销售流水", use_container_width=True, key="btn_refresh_sales_table_admin"):
            st.session_state.sheet_versions[SALES_SHEET] = st.session_state.sheet_versions.get(SALES_SHEET, 0) + 1
            st.session_state.sales_reset_key += 1
            st.rerun()
        f_sl = sort_sales_latest_first(get_f(df_sales, q))
        if not f_sl.empty:
            f_sl_sel = f_sl.copy()
            # 保留这条流水在 Sales 表里的原始行号，用来做“单条精确撤销”。
            # 这列会被隐藏，不展示给用户。
            f_sl_sel['__sales_source_index'] = f_sl_sel.index.astype(int)
            
            f_sl_sel['成交单价'] = pd.to_numeric(f_sl_sel['成交单价'], errors='coerce').fillna(0.0)
            f_sl_sel['总营业额'] = pd.to_numeric(f_sl_sel['总营业额'], errors='coerce').fillna(0.0)
            
            f_sl_sel['商品名称'] = translate_series(f_sl_sel['商品名称'])
            f_sl_sel['颜色'] = translate_series(f_sl_sel['颜色'])
            
            sel_col_name = "Sel" if st.session_state.lang == 'en' else "选择"
            f_sl_sel.insert(0, sel_col_name, False)
            
            if st.session_state.lang == 'en': f_sl_sel.rename(columns=col_map, inplace=True)
            
            u_col = 'Unit Price' if st.session_state.lang == 'en' else '成交单价'
            t_col = 'Total Amount' if st.session_state.lang == 'en' else '总营业额'
            
            styled_sl = f_sl_sel.style.format({u_col: '${:.2f}', t_col: '${:.2f}'})
            
            d_disable = [c for c in f_sl_sel.columns if c != sel_col_name]
            visible_sales_cols = [c for c in f_sl_sel.columns if c != '__sales_source_index']
            
            edt = st.data_editor(
                styled_sl, 
                column_config={
                    sel_col_name: st.column_config.CheckboxColumn(sel_col_name, default=False),
                    '__sales_source_index': None,
                }, 
                column_order=visible_sales_cols,
                disabled=d_disable, 
                use_container_width=True, hide_index=True, 
                key=f"sales_editor_{st.session_state.sales_reset_key}"
            )
            
            sel = edt[edt[sel_col_name] == True] if sel_col_name in edt.columns else pd.DataFrame()
            
            if not sel.empty:
                if len(sel) > 1:
                    st.warning("⚠️ 为了防止误删，现在不支持批量撤销。请只勾选 1 条销售流水。")
                    st.button("🔄 取消所有选中", key="btn_cancel_sales", on_click=clear_sales)
                else:
                    r_del = sel.iloc[0]
                    del_order_id = str(r_del['Order ID' if st.session_state.lang == 'en' else '订单号']).strip()
                    del_product = str(r_del['Product' if st.session_state.lang == 'en' else '商品名称']).strip()
                    del_variant = str(r_del['Variant' if st.session_state.lang == 'en' else '颜色']).strip()
                    del_qty = to_int(r_del['Qty' if st.session_state.lang == 'en' else '销售数量'])
                    del_amount = to_float(r_del['Total Amount' if st.session_state.lang == 'en' else '总营业额'])
                    st.warning(f"即将撤销 1 条销售流水：`{del_order_id}` / `{del_product} ({del_variant})` / 数量 `{del_qty}` / 金额 `${del_amount:.2f}`。此操作会同步回补库存。")

                    sc1, sc2, _ = st.columns([1.8, 1.5, 4])
                    with sc1:
                        if st.button("🗑️ 确认撤销这 1 条流水", type="primary"):
                            fresh = JIT_fetch([STOCK_SHEET, SALES_SHEET])
                            latest_stock = fresh[STOCK_SHEET]
                            latest_sales = fresh[SALES_SHEET]
                            
                            real_n = t_val(del_product, 'cn')
                            real_c = t_val(del_variant, 'cn')
                            q_val = del_qty

                            try:
                                source_idx = int(float(r_del.get('__sales_source_index', -1)))
                            except Exception:
                                source_idx = -1

                            t_idx = None
                            if source_idx in latest_sales.index:
                                row_check = latest_sales.loc[source_idx]
                                same_row = (
                                    str(row_check.get('订单号', '')).strip() == del_order_id and
                                    str(row_check.get('商品名称', '')).strip() == str(real_n).strip() and
                                    str(row_check.get('颜色', '')).strip() == str(real_c).strip() and
                                    to_int(row_check.get('销售数量', 0)) == q_val
                                )
                                if same_row:
                                    t_idx = source_idx

                            if t_idx is None:
                                cond = (latest_sales['订单号'].astype(str).str.strip() == del_order_id) & \
                                       (latest_sales['商品名称'].astype(str).str.strip() == str(real_n).strip()) & \
                                       (latest_sales['颜色'].astype(str).str.strip() == str(real_c).strip()) & \
                                       (pd.to_numeric(latest_sales['销售数量'], errors='coerce').fillna(0).astype(int) == q_val)
                                match_idxs = latest_sales[cond].index.tolist()
                                if len(match_idxs) == 1:
                                    t_idx = match_idxs[0]
                                elif len(match_idxs) > 1:
                                    st.error("⚠️ 检测到多条完全相似的流水。为防止误删，请先点「手动刷新销售流水」后再试。")
                                    st.stop()
                                else:
                                    st.error("⚠️ 未在云端找到这条流水，可能已被删除或页面不是最新。请先手动刷新。")
                                    st.stop()

                            m = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(real_n).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(real_c).strip())].index
                            if not m.empty:
                                latest_stock.at[m[0], '货柜数量'] = to_int(latest_stock.at[m[0], '货柜数量']) + q_val
                                latest_stock.at[m[0], '已售出数量'] = to_int(latest_stock.at[m[0], '已售出数量']) - q_val
                                latest_stock.at[m[0], '总库存'] = recalc_total_stock(latest_stock, m[0])

                            latest_sales = latest_sales.drop(index=t_idx).reset_index(drop=True)
                            save_data(latest_stock, STOCK_SHEET)
                            save_data(latest_sales, SALES_SHEET)
                            st.session_state.sales_reset_key += 1
                            st.success("✅ 已精确撤销 1 条销售流水。")
                            st.rerun()
                    with sc2:
                        st.button("🔄 取消所有选中", key="btn_cancel_sales", on_click=clear_sales)

                if len(sel) == 1:
                    st.markdown("### ⚙️ 修改此笔流水 (Edit Log)")
                    r = sel.iloc[0]
                    real_n = t_val(r['Product' if st.session_state.lang == 'en' else '商品名称'], 'cn')
                    real_c = t_val(r['Variant' if st.session_state.lang == 'en' else '颜色'], 'cn')
                    o_id = str(r['Order ID' if st.session_state.lang == 'en' else '订单号']).strip()
                    o_dt = str(r['Date' if st.session_state.lang == 'en' else '日期']).strip()
                    o_qty = to_int(r['Qty' if st.session_state.lang == 'en' else '销售数量'])
                    o_prc = to_float(r['Unit Price' if st.session_state.lang == 'en' else '成交单价'])

                    f_opts_stk = df_stock.copy()
                    f_opts_stk['dn'] = translate_series(f_opts_stk['商品名称']).fillna('').astype(str)
                    f_opts_stk['dc'] = translate_series(f_opts_stk['颜色']).fillna('').astype(str)
                    f_opts_stk['label'] = f_opts_stk['dn'] + " (" + f_opts_stk['dc'] + ")"
                    stk_lbls = f_opts_stk['label'].tolist()
                    
                    curr_lbl = f"{t_val(real_n, 'en' if st.session_state.lang == 'en' else 'cn')} ({t_val(real_c, 'en' if st.session_state.lang == 'en' else 'cn')})"
                    if curr_lbl not in stk_lbls: stk_lbls.insert(0, curr_lbl)
                    
                    with st.form("edit_sale_form_admin"):
                        e_c1, e_c2, e_c3, e_c4 = st.columns(4)
                        try: parsed_date = pd.to_datetime(o_dt).date()
                        except: parsed_date = datetime.now().date()
                        
                        e_date = e_c1.date_input("交易日期 Date", value=parsed_date)
                        e_prod = e_c2.selectbox("商品 Product", stk_lbls, index=stk_lbls.index(curr_lbl))
                        e_qty = e_c3.number_input("数量 Qty", value=o_qty, min_value=1)
                        e_price = e_c4.number_input("单价 Price ($)", value=o_prc, format="%.2f")
                        
                        if st.form_submit_button("💾 保存修改 (Save)", type="primary"):
                            fresh = JIT_fetch([STOCK_SHEET, SALES_SHEET])
                            latest_stock = fresh[STOCK_SHEET]
                            latest_sales = fresh[SALES_SHEET]
                            
                            cond = (latest_sales['订单号'].astype(str).str.strip() == o_id) & \
                                   (latest_sales['商品名称'].astype(str).str.strip() == str(real_n).strip()) & \
                                   (latest_sales['颜色'].astype(str).str.strip() == str(real_c).strip()) & \
                                   (pd.to_numeric(latest_sales['销售数量'], errors='coerce').fillna(0).astype(int) == o_qty)
                            
                            true_idx = latest_sales[cond].index
                            if not true_idx.empty:
                                t_idx = true_idx[0]
                                m_old = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(real_n).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(real_c).strip())].index
                                if not m_old.empty:
                                    latest_stock.at[m_old[0], '货柜数量'] = to_int(latest_stock.at[m_old[0], '货柜数量']) + o_qty
                                    latest_stock.at[m_old[0], '已售出数量'] = to_int(latest_stock.at[m_old[0], '已售出数量']) - o_qty
                                    latest_stock.at[m_old[0], '总库存'] = recalc_total_stock(latest_stock, m_old[0])
                                    
                                new_n = t_val(e_prod.rsplit(" (", 1)[0], 'cn')
                                new_c = t_val(e_prod.rsplit(" (", 1)[1].replace(")", ""), 'cn')
                                
                                m_new = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(new_n).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(new_c).strip())].index
                                if not m_new.empty:
                                    latest_stock.at[m_new[0], '货柜数量'] = to_int(latest_stock.at[m_new[0], '货柜数量']) - e_qty
                                    latest_stock.at[m_new[0], '已售出数量'] = to_int(latest_stock.at[m_new[0], '已售出数量']) + e_qty
                                    latest_stock.at[m_new[0], '总库存'] = recalc_total_stock(latest_stock, m_new[0])
                                    
                                latest_sales.at[t_idx, '日期'] = e_date.strftime("%Y/%m/%d")
                                latest_sales.at[t_idx, '商品名称'] = new_n
                                latest_sales.at[t_idx, '颜色'] = new_c
                                latest_sales.at[t_idx, '销售数量'] = e_qty
                                latest_sales.at[t_idx, '成交单价'] = e_price
                                latest_sales.at[t_idx, '总营业额'] = e_qty * e_price
                                
                                save_data(latest_stock, STOCK_SHEET)
                                save_data(latest_sales, SALES_SHEET)
                                st.session_state.sales_reset_key += 1
                                st.success("✅ 修改成功！"); st.rerun()
                            else:
                                st.error("⚠️ 未在云端找到该流水！可能是已被删除或数量有偏差。")
        else:
            st.info("No logs.")

    with t3:
        st.subheader("📊 财务与客流报表")
        
        t3_start, t3_end = date_range_picker("📅 毛利/客流日期区间", "📅 Margin / Traffic Date Range", key="admin_margin_range_today")
        st.info(f"📅 此看板的财务数据按上方日期区间计算：**{t3_start}** 至 **{t3_end}**")

        if not df_sales.empty:
            df_sales['日期_dt'] = pd.to_datetime(df_sales['日期'], errors='coerce')
            df_sales_clean = df_sales.dropna(subset=['日期_dt']).copy()
            
            if not df_sales_clean.empty:
                f_sales_range = df_sales_clean[(df_sales_clean['日期_dt'] >= pd.Timestamp(t3_start)) & (df_sales_clean['日期_dt'] <= pd.Timestamp(t3_end))].copy()
                
                f_sales_range['销售数量'] = pd.to_numeric(f_sales_range['销售数量'], errors='coerce').fillna(0)
                f_sales_range['总营业额'] = pd.to_numeric(f_sales_range['总营业额'], errors='coerce').fillna(0.0)
                
                # Tab 3 only: normalize and deduplicate the SKU cost lookup before merging.
                # Otherwise duplicate Stock rows can duplicate a sales row during merge and distort margin.
                df_stock_calc = df_stock[['商品名称', '颜色', '进价成本']].copy()
                df_stock_calc['_sku_name'] = df_stock_calc['商品名称'].fillna('').astype(str).str.strip()
                df_stock_calc['_sku_color'] = df_stock_calc['颜色'].fillna('').astype(str).str.strip()
                df_stock_calc['进价成本'] = pd.to_numeric(df_stock_calc['进价成本'], errors='coerce').fillna(0.0)
                df_stock_calc = df_stock_calc.drop_duplicates(subset=['_sku_name', '_sku_color'], keep='last')

                f_sales_range['_sku_name'] = f_sales_range['商品名称'].fillna('').astype(str).str.strip()
                f_sales_range['_sku_color'] = f_sales_range['颜色'].fillna('').astype(str).str.strip()
                f_sales_range = f_sales_range.merge(
                    df_stock_calc[['_sku_name', '_sku_color', '进价成本']],
                    on=['_sku_name', '_sku_color'],
                    how='left'
                )
                f_sales_range['进价成本'] = pd.to_numeric(f_sales_range['进价成本'], errors='coerce').fillna(0.0)
                f_sales_range['具体毛利'] = f_sales_range['总营业额'] - (f_sales_range['销售数量'] * f_sales_range['进价成本'])
                f_sales_range.drop(columns=['_sku_name', '_sku_color'], inplace=True, errors='ignore')
                
                f_sales_range = get_f(f_sales_range, q)
                
                if not f_sales_range.empty:
                    tot_rev = f_sales_range['总营业额'].sum()
                    tot_items = f_sales_range['销售数量'].sum()
                    tot_margin = f_sales_range['具体毛利'].sum()
                    
                    valid_orders = f_sales_range[
                        (~f_sales_range['订单号'].astype(str).str.contains('历史单', na=False)) & 
                        (~f_sales_range['订单号'].astype(str).str.contains('EXC-', na=False))
                    ]
                    order_count = valid_orders['订单号'].nunique()
                    
                    legacy_orders = f_sales_range[f_sales_range['订单号'].astype(str).str.contains('历史单', na=False)]
                    total_order_count = order_count + len(legacy_orders)
                    
                    df_traffic_clean = df_traffic.copy()
                    if not df_traffic_clean.empty:
                        df_traffic_clean['日期_dt'] = pd.to_datetime(df_traffic_clean['日期'], errors='coerce')
                        f_traffic_range = df_traffic_clean[(df_traffic_clean['日期_dt'] >= pd.Timestamp(t3_start)) & (df_traffic_clean['日期_dt'] <= pd.Timestamp(t3_end))]
                        total_traffic = pd.to_numeric(f_traffic_range['有效客流'], errors='coerce').fillna(0).sum()
                    else:
                        total_traffic = 0
                        
                    conv_rate = (total_order_count / total_traffic * 100) if total_traffic > 0 else 0.0
                    acv = tot_rev / total_order_count if total_order_count > 0 else 0
                    upt = tot_items / total_order_count if total_order_count > 0 else 0
                    
                    period = st.radio("维度", ["Daily", "Weekly", "Monthly"], horizontal=True)
                    if "Daily" in period: f_sales_range['周期'] = f_sales_range['日期_dt'].dt.strftime('%Y/%m/%d')
                    elif "Weekly" in period: f_sales_range['周期'] = (f_sales_range['日期_dt'] - pd.to_timedelta(f_sales_range['日期_dt'].dt.dayofweek, unit='D')).dt.strftime('Week of %b %d')
                    else: f_sales_range['周期'] = f_sales_range['日期_dt'].dt.strftime('%Y/%m')
                    
                    summ = f_sales_range.groupby(['周期', '商品名称', '颜色']).agg({'销售数量':'sum', '总营业额':'sum', '具体毛利':'sum'}).reset_index()
                    
                    delta_days = (t3_end - t3_start).days + 1
                    
                    st.markdown(f"### 🏬 核心客流漏斗矩阵 {f'(已过滤: {q})' if q else ''}")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("👁️ 有效总客流 (选中期间)", f"{int(total_traffic)} 人")
                    m2.metric("💳 交易单数", f"{total_order_count} 单")
                    m3.metric("🔄 购买转化率", f"{conv_rate:.1f}%")
                    
                    st.divider()
                    
                    m4, m5, m6 = st.columns(3)
                    m4.metric("💰 总营业额", f"${tot_rev:.2f}")
                    m5.metric("🛒 平均客单价 (ACV)", f"${acv:.2f}")
                    m6.metric("🛍️ 连带率 (UPT)", f"{upt:.2f} 件/单")
                    
                    st.divider()
                    
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("具体毛利", f"${tot_margin:.2f}")
                    c2.metric("总售出件数", f"{int(tot_items)} 件")
                    
                    avg_m = tot_margin / tot_rev * 100 if tot_rev > 0 else 0
                    c3.metric("平均毛利率", f"{avg_m:.1f}%")
                    
                    avg_daily = tot_rev / delta_days if delta_days > 0 else 0
                    c4.metric("日均坪效 (每日营收)", f"${avg_daily:.2f}")
                    
                    st.divider()
                    st.markdown("### 📈 营收与毛利走势")
                    chart_data_t3 = summ.groupby('周期')[['总营业额', '具体毛利']].sum().sort_index(ascending=True)
                    st.bar_chart(chart_data_t3, use_container_width=True)

                    dl_c1, dl_c2 = st.columns([1, 4])
                    with dl_c1:
                        csv_t3 = convert_df_to_csv(summ)
                        st.download_button(
                            label="⬇️ 一键导出毛利报表 (CSV)",
                            data=csv_t3,
                            file_name=f"Takashimaya_毛利报表_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv",
                            type="primary"
                        )
                    
                    st.dataframe(summ.sort_values('周期', ascending=False).style.format({'总营业额':"${:.2f}", '具体毛利':"${:.2f}", '销售数量':"{:d}"}), use_container_width=True)
                else:
                    st.info("💡 在选定时间段内没有找到符合搜索条件的销售记录。")
            else:
                st.info("流水表中没有有效的日期数据。")

    with t4:
        st.subheader("👥 员工档案与门禁管理")
        with st.expander("➕ 新增人员档案 (含合作厂商)", expanded=False):
            with st.form("add_employee"):
                c1, c2 = st.columns(2)
                e_name = c1.text_input("人员姓名")
                e_role = c2.selectbox("身份职位", ["店长", "全职店员", "兼职店员", "实习生", "合作厂商", "其他"])
                c3, c4, c5 = st.columns(3)
                e_wage = c3.number_input("时薪 ($/小时, 厂商填0)", min_value=0.0, step=0.5, value=12.0, format="%.2f")
                e_phone = c4.text_input("联系方式 (选填)")
                e_date = c5.date_input("入职/开通日期", value=datetime.now())
                system_labels = [cfg["label"] for cfg in CATEGORY_SYSTEMS.values()]
                e_systems = st.multiselect(
                    "可进入系统",
                    system_labels,
                    default=[CATEGORY_SYSTEMS[DEFAULT_CATEGORY_SYSTEM]["label"]],
                    help="只授权丝绸系统的员工，登录后会直接进入丝绸系统；授权两个系统的员工可自行切换。",
                )
                if st.form_submit_button("保存人员信息"):
                    if e_name.strip() == "": st.warning("⚠️ 姓名不能为空！")
                    elif not e_systems: st.warning("⚠️ 请至少选择一个可进入系统。")
                    elif e_name in df_employee['员工姓名'].values: st.warning(f"⚠️ 人员 {e_name} 已经存在！")
                    else:
                        fresh_emp = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                        new_emp = pd.DataFrame([[e_name, e_role, e_wage, e_phone, e_date.strftime("%Y/%m/%d"), "", "在职", ", ".join(e_systems)]], columns=EMP_COLS)
                        fresh_emp = pd.concat([fresh_emp, new_emp], ignore_index=True)
                        save_data(fresh_emp, EMP_SHEET) 
                        st.session_state.emp_reset_key += 1
                        st.rerun()

        f_employee = get_f(df_employee, q) 
        if not f_employee.empty:
            v_emp = f_employee.copy()
            v_emp.insert(0, "选择", False)
            
            v_emp['时薪'] = pd.to_numeric(v_emp['时薪'], errors='coerce').fillna(0.0)
            styled_emp = v_emp.style.format({'时薪': '${:.2f}'})
            
            editor_key = f"emp_editor_{st.session_state.emp_reset_key}"
            edited_emp = st.data_editor(
                styled_emp, 
                column_config={
                    "选择": st.column_config.CheckboxColumn("选择", default=False),
                    "状态": st.column_config.SelectboxColumn("在离职状态", options=["在职", "离职"]),
                    "登录密码": st.column_config.TextColumn("登录密码 (店长清空后，人员可重新设置)"),
                    SYSTEM_PERMISSION_COL: st.column_config.TextColumn("可进入系统（钛杯系统, 丝绸系统）")
                }, 
                disabled=['员工姓名', '入职日期'], 
                use_container_width=True, hide_index=True, key=editor_key
            )
            
            editor_state = st.session_state.get(editor_key, {})
            if editor_state.get("edited_rows"):
                has_real_edits = False
                fresh_emp = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                for idx, row in edited_emp.iterrows():
                    is_changed = False
                    for c in EMP_COLS:
                        if str(row[c]) != str(v_emp.loc[idx, c]):
                            is_changed = True
                            break
                    if is_changed:
                        has_real_edits = True
                        for col in EMP_COLS:
                            fresh_emp.at[idx, col] = row[col]
                if has_real_edits:
                    save_data(fresh_emp, EMP_SHEET)
                    st.success("✅ 人员档案修改已保存！")
                    st.session_state.emp_reset_key += 1
                    st.rerun()
            
            selected_emp = edited_emp[edited_emp["选择"] == True]
            if not selected_emp.empty:
                col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 4])
                with col_btn1:
                    if st.button("🗑️ 彻底删除人员 (不建议)", type="primary", key="del_emp"):
                        fresh_emp = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                        for _, row in selected_emp.iterrows():
                            fresh_emp = fresh_emp[fresh_emp['员工姓名'].astype(str).str.strip() != str(row['员工姓名']).strip()]
                        save_data(fresh_emp, EMP_SHEET)
                        st.session_state.emp_reset_key += 1; st.rerun()
                with col_btn2: st.button("🔄 取消所有选中", key="btn_cancel_emp", on_click=clear_emp)

        st.divider()
        st.subheader("⏰ 排班与打卡记录")
        
        if df_employee.empty:
            st.info("💡 请先在上方添加人员。")
        else:
            with st.expander("➕ 帮员工补录打卡", expanded=True):
                with st.form("add_attendance_admin"):
                    c1, c2 = st.columns(2)
                    att_name = c1.selectbox("选择员工", df_employee['员工姓名'].astype(str).tolist())
                    att_date = c2.date_input("工作日期", value=datetime.now())
                    
                    c3, c4 = st.columns(2)
                    att_start = c3.time_input("上班时间", value=time(10, 0))
                    att_end = c4.time_input("下班时间", value=time(18, 0))
                    
                    if st.form_submit_button("确认记录考勤"):
                        fresh_att = JIT_fetch([ATT_SHEET])[ATT_SHEET]
                        dt_start = datetime.combine(att_date, att_start)
                        dt_end = datetime.combine(att_date, att_end)
                        if dt_end < dt_start: dt_end += timedelta(days=1)
                            
                        duration_hours = (dt_end - dt_start).total_seconds() / 3600.0
                        
                        wage_val = df_employee[df_employee['员工姓名'] == att_name]['时薪'].iloc[0]
                        hourly_wage = to_float(wage_val)
                        total_wage = duration_hours * hourly_wage
                        
                        new_att = pd.DataFrame([[
                            att_name, att_date.strftime("%Y/%m/%d"), 
                            att_start.strftime("%H:%M"), att_end.strftime("%H:%M"), 
                            round(duration_hours, 2), round(total_wage, 2)
                        ]], columns=ATT_COLS)
                        
                        fresh_att = pd.concat([new_att, fresh_att], ignore_index=True)
                        save_data(fresh_att, ATT_SHEET) 
                        
                        st.success(f"已记录 {att_name} 的工时: {round(duration_hours, 1)} 小时，核算薪资: ${round(total_wage, 2)}")
                        st.rerun()

            st.markdown("### 🕒 考勤记录查询")
            att_start, att_end = date_range_picker("📅 考勤记录日期区间", "📅 Attendance Date Range", key="admin_attendance_range_today")
            f_att = filter_by_date_range(df_attendance, '日期', att_start, att_end)
            f_att = get_f(f_att, q)
            if not f_att.empty:
                v_att = f_att.copy()
                v_att.insert(0, "选择", False)
                
                v_att['核算薪资'] = pd.to_numeric(v_att['核算薪资'], errors='coerce').fillna(0.0)
                styled_att = v_att.style.format({'核算薪资': '${:.2f}'})
                
                edited_att = st.data_editor(
                    styled_att, 
                    column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, 
                    disabled=f_att.columns.tolist(), 
                    use_container_width=True, hide_index=True, 
                    key=f"att_editor_{st.session_state.att_reset_key}"
                )
                selected_att = edited_att[edited_att["选择"] == True]
                
                if not selected_att.empty:
                    col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 4])
                    with col_btn1:
                        if st.button("🗑️ 删除选中打卡记录", type="primary", key="del_att"):
                            fresh_att = JIT_fetch([ATT_SHEET])[ATT_SHEET]
                            for _, row in selected_att.iterrows():
                                fresh_att = fresh_att[~((fresh_att['员工姓名'].astype(str).str.strip() == str(row['员工姓名']).strip()) & (fresh_att['日期'].astype(str).str.strip() == str(row['日期']).strip()) & (fresh_att['开始时间'].astype(str).str.strip() == str(row['开始时间']).strip()))]
                            save_data(fresh_att, ATT_SHEET)
                            st.session_state.att_reset_key += 1 
                            st.rerun()
                    with col_btn2: st.button("🔄 取消所有选中", key="btn_cancel_att", on_click=clear_att)
                
                st.divider()
                total_hours = pd.to_numeric(f_att['工作时长'], errors='coerce').fillna(0).sum()
                total_wage = pd.to_numeric(f_att['核算薪资'], errors='coerce').fillna(0).sum()
                
                c_t1, c_t2, c_t3 = st.columns([2, 1, 1])
                c_t1.markdown(f"**🧾 列表总计** (共 {len(f_att)} 条记录)")
                c_t2.metric("当前列表总工时", f"{total_hours:.1f} 小时")
                c_t3.metric("当前列表总薪资支出", f"${total_wage:.2f}")

            st.divider()
            st.subheader("🛍️ 员工内购扣款")
            st.caption("用于记录员工拿货/内购金额。发工资时可直接从薪资中扣除；如勾选扣库存，系统会同步从库存中出库。")

            active_staff_for_purchase = df_employee[df_employee['状态'].fillna('').astype(str).str.strip() != '离职']['员工姓名'].astype(str).tolist() if not df_employee.empty else []
            stock_purchase_options = []
            if not df_stock.empty:
                sp_stock_opts = df_stock.copy()
                sp_stock_opts['disp_name'] = translate_series(sp_stock_opts['商品名称']).fillna('').astype(str)
                sp_stock_opts['disp_color'] = translate_series(sp_stock_opts['颜色']).fillna('').astype(str)
                sp_stock_opts['label'] = sp_stock_opts['disp_name'] + " (" + sp_stock_opts['disp_color'] + ")"
                stock_purchase_options = sp_stock_opts['label'].tolist()

            with st.expander("➕ 记录一笔员工内购", expanded=True):
                if not active_staff_for_purchase:
                    st.warning("⚠️ 暂无在职员工，无法记录内购。")
                elif not stock_purchase_options:
                    st.warning("⚠️ 暂无库存商品，无法记录内购。")
                else:
                    with st.form("add_staff_purchase_form"):
                        sp_c1, sp_c2 = st.columns(2)
                        sp_staff = sp_c1.selectbox("内购员工", active_staff_for_purchase)
                        sp_date = sp_c2.date_input("内购日期", value=datetime.now().date())

                        sp_sku = st.selectbox("内购商品", stock_purchase_options)
                        sel_disp_name, sel_disp_color = split_sku_label(sp_sku)
                        sp_real_name = t_val(sel_disp_name, 'cn')
                        sp_real_color = t_val(sel_disp_color, 'cn')
                        sp_row = df_stock[(df_stock['商品名称'].astype(str).str.strip() == str(sp_real_name).strip()) & (df_stock['颜色'].astype(str).str.strip() == str(sp_real_color).strip())]
                        sp_cost = to_float(sp_row.iloc[0]['进价成本']) if not sp_row.empty else 0.0
                        sp_retail = to_float(sp_row.iloc[0]['售卖价格']) if not sp_row.empty else 0.0
                        sp_available = 0
                        if not sp_row.empty:
                            sp_available = sum(to_int(sp_row.iloc[0][col]) for col in ['展示数量', '货柜数量', '储物间数量'])
                        st.info(f"当前总库存：{sp_available} 件｜进价成本：${sp_cost:.2f}｜原售价：${sp_retail:.2f}")

                        sp_c3, sp_c4, sp_c5 = st.columns(3)
                        sp_qty = sp_c3.number_input("内购数量", min_value=1, step=1, value=1)
                        sp_unit_price = sp_c4.number_input("内购单价 / 工资扣款单价 ($)", min_value=0.0, value=float(sp_retail), format="%.2f", key=f"staff_purchase_unit_{sp_sku}_{st.session_state.staff_purchase_reset_key}")
                        sp_deduct_stock = sp_c5.checkbox("同步扣库存", value=True)
                        sp_note = st.text_input("备注", placeholder="例如：员工福利价/工资扣款/样品自用...")
                        sp_total = round(float(sp_qty) * float(sp_unit_price), 2)
                        sp_cost_total = round(float(sp_qty) * float(sp_cost), 2)
                        st.markdown(f"**本笔工资扣款金额：`${sp_total:.2f}`**")

                        if st.form_submit_button("💾 保存员工内购记录", type="primary", use_container_width=True):
                            fresh = JIT_fetch([STAFF_PURCHASE_SHEET, STOCK_SHEET])
                            latest_sp = fresh[STAFF_PURCHASE_SHEET]
                            latest_stock = fresh[STOCK_SHEET]

                            stock_match = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(sp_real_name).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(sp_real_color).strip())].index
                            if sp_deduct_stock and stock_match.empty:
                                st.error("⚠️ 找不到对应库存商品，无法扣库存。")
                            else:
                                if sp_deduct_stock:
                                    idx_sp = stock_match[0]
                                    latest_total_stock = recalc_total_stock(latest_stock, idx_sp)
                                    if latest_total_stock < int(sp_qty):
                                        st.error(f"⚠️ 总库存不足：当前只有 {latest_total_stock} 件，无法内购 {int(sp_qty)} 件。")
                                        st.stop()
                                    deduct_pos_stock_from_locations(latest_stock, idx_sp, int(sp_qty))
                                    latest_stock.at[idx_sp, '已售出数量'] = to_int(latest_stock.at[idx_sp, '已售出数量']) + int(sp_qty)
                                    latest_stock.at[idx_sp, '总库存'] = recalc_total_stock(latest_stock, idx_sp)

                                sp_id = "EMPBUY-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")[-22:]
                                new_sp = pd.DataFrame([[
                                    sp_id, sp_date.strftime("%Y/%m/%d"), sp_staff, sp_real_name, sp_real_color,
                                    int(sp_qty), round(float(sp_unit_price), 2), sp_total, sp_cost_total,
                                    st.session_state.get("current_user", "店长"), "是" if sp_deduct_stock else "否", sp_note
                                ]], columns=STAFF_PURCHASE_COLS)

                                latest_sp = pd.concat([new_sp, latest_sp], ignore_index=True)
                                save_data(latest_sp, STAFF_PURCHASE_SHEET)
                                if sp_deduct_stock:
                                    save_data(latest_stock, STOCK_SHEET)
                                st.session_state.staff_purchase_reset_key += 1
                                st.success(f"✅ 已记录 {sp_staff} 的内购扣款：${sp_total:.2f}")
                                st.rerun()

            sp_view = filter_by_date_range(df_staff_purchase, '日期', att_start, att_end)
            sp_view = get_f(sp_view, q)
            if not sp_view.empty:
                sp_view = sp_view.copy()
                for c in ['购买数量', '内购单价', '扣款金额', '成本合计']:
                    sp_view[c] = pd.to_numeric(sp_view[c], errors='coerce').fillna(0.0)

                sp_total_deduction = sp_view['扣款金额'].sum()
                sp_total_qty = sp_view['购买数量'].sum()
                sp_m1, sp_m2 = st.columns(2)
                sp_m1.metric("当前区间内购件数", f"{int(sp_total_qty)} 件")
                sp_m2.metric("当前区间工资扣款总额", f"${sp_total_deduction:.2f}")

                st.markdown("### 📋 员工内购明细")
                sp_display = sp_view.copy()
                sp_display.insert(0, "选择", False)
                sp_display['商品名称'] = translate_series(sp_display['商品名称'])
                sp_display['颜色'] = translate_series(sp_display['颜色'])
                styled_sp = sp_display.style.format({'内购单价': '${:.2f}', '扣款金额': '${:.2f}', '成本合计': '${:.2f}'})
                edited_sp = st.data_editor(
                    styled_sp,
                    column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)},
                    disabled=[c for c in sp_display.columns if c != "选择"],
                    use_container_width=True,
                    hide_index=True,
                    key=f"staff_purchase_editor_{st.session_state.staff_purchase_reset_key}"
                )
                selected_sp = edited_sp[edited_sp["选择"] == True]
                if len(selected_sp) > 1:
                    st.warning("⚠️ 为避免误删，员工内购记录一次只能撤销 1 条。请只勾选 1 条。")
                elif len(selected_sp) == 1:
                    row_sp = selected_sp.iloc[0]
                    st.warning(f"即将撤销 1 条内购记录：{row_sp['员工姓名']} / {row_sp['商品名称']} ({row_sp['颜色']}) / 数量 {row_sp['购买数量']} / 扣款 ${to_float(row_sp['扣款金额']):.2f}")
                    del_c1, del_c2, _ = st.columns([1.8, 1.5, 4])
                    with del_c1:
                        if st.button("🗑️ 确认撤销这 1 条内购", type="primary", key="delete_one_staff_purchase"):
                            fresh = JIT_fetch([STAFF_PURCHASE_SHEET, STOCK_SHEET])
                            latest_sp = fresh[STAFF_PURCHASE_SHEET]
                            latest_stock = fresh[STOCK_SHEET]
                            del_id = str(row_sp['内购单号']).strip()
                            matched_old = latest_sp[latest_sp['内购单号'].astype(str).str.strip() == del_id]
                            if matched_old.empty:
                                st.error("⚠️ 云端找不到这条内购记录，可能已经被删除。")
                                st.stop()
                            old = matched_old.iloc[0]
                            if str(old.get('是否扣库存', '')).strip() == '是':
                                real_old_n = t_val(old['商品名称'], 'cn')
                                real_old_c = t_val(old['颜色'], 'cn')
                                old_qty = to_int(old['购买数量'])
                                m_stock = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(real_old_n).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(real_old_c).strip())].index
                                if not m_stock.empty:
                                    idx_old = m_stock[0]
                                    latest_stock.at[idx_old, '货柜数量'] = to_int(latest_stock.at[idx_old, '货柜数量']) + old_qty
                                    latest_stock.at[idx_old, '已售出数量'] = max(0, to_int(latest_stock.at[idx_old, '已售出数量']) - old_qty)
                                    latest_stock.at[idx_old, '总库存'] = recalc_total_stock(latest_stock, idx_old)
                                    save_data(latest_stock, STOCK_SHEET)
                            latest_sp = latest_sp[latest_sp['内购单号'].astype(str).str.strip() != del_id]
                            save_data(latest_sp, STAFF_PURCHASE_SHEET)
                            st.session_state.staff_purchase_reset_key += 1
                            st.success("✅ 已撤销这 1 条员工内购记录。")
                            st.rerun()
                    with del_c2:
                        st.button("🔄 取消选中", key="cancel_staff_purchase_selection", on_click=clear_staff_purchase)
            else:
                st.info("该考勤日期区间内暂无员工内购扣款记录。")

            st.markdown("### 💳 发工资扣款汇总")
            payroll_wage = pd.DataFrame(columns=['员工姓名', '工作时长', '核算薪资'])
            if not f_att.empty:
                tmp_att_pay = f_att.copy()
                tmp_att_pay['工作时长'] = pd.to_numeric(tmp_att_pay['工作时长'], errors='coerce').fillna(0.0)
                tmp_att_pay['核算薪资'] = pd.to_numeric(tmp_att_pay['核算薪资'], errors='coerce').fillna(0.0)
                payroll_wage = tmp_att_pay.groupby('员工姓名', as_index=False).agg({'工作时长': 'sum', '核算薪资': 'sum'})

            payroll_deduct = pd.DataFrame(columns=['员工姓名', '内购扣款'])
            if not sp_view.empty:
                tmp_sp_pay = sp_view.copy()
                tmp_sp_pay['扣款金额'] = pd.to_numeric(tmp_sp_pay['扣款金额'], errors='coerce').fillna(0.0)
                payroll_deduct = tmp_sp_pay.groupby('员工姓名', as_index=False).agg({'扣款金额': 'sum'}).rename(columns={'扣款金额': '内购扣款'})

            payroll_summary = pd.merge(payroll_wage, payroll_deduct, on='员工姓名', how='outer').fillna(0.0)
            if not payroll_summary.empty:
                payroll_summary['应发工资'] = payroll_summary['核算薪资']
                payroll_summary['实发参考'] = payroll_summary['应发工资'] - payroll_summary['内购扣款']
                payroll_summary = payroll_summary[['员工姓名', '工作时长', '应发工资', '内购扣款', '实发参考']].sort_values('员工姓名')
                st.dataframe(
                    payroll_summary.style.format({'工作时长': '{:.2f}', '应发工资': '${:.2f}', '内购扣款': '${:.2f}', '实发参考': '${:.2f}'}),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("当前区间暂无工资或内购扣款数据。")

            st.divider()
            st.subheader("💵 月度工资与提成结算")
            st.caption("整月适合长期专柜；自定义日期适合 popup。自定义日期会用 30 天月化营业额判断档位，但提成池仍按实际期间营业额发放。")

            commission_mode = st.radio(
                "选择结算方式",
                ["按整月结算", "自定义日期范围"],
                horizontal=True,
                key="admin_commission_mode",
            )
            if commission_mode == "按整月结算":
                default_commission_month = datetime.now().date().replace(day=1)
                commission_month_pick = st.date_input("选择结算月份", value=default_commission_month, key="admin_commission_month")
                commission_start = commission_month_pick.replace(day=1)
                if commission_start.month == 12:
                    commission_next_month = commission_start.replace(year=commission_start.year + 1, month=1, day=1)
                else:
                    commission_next_month = commission_start.replace(month=commission_start.month + 1, day=1)
                commission_end = commission_next_month - timedelta(days=1)
                commission_tier_basis = None
                commission_period_label = "当前结算月份"
            else:
                custom_c1, custom_c2 = st.columns(2)
                commission_start = custom_c1.date_input("开始日期", value=datetime.now().date().replace(day=1), key="admin_commission_custom_start")
                commission_end = custom_c2.date_input("结束日期", value=datetime.now().date(), key="admin_commission_custom_end")
                if commission_start > commission_end:
                    commission_start, commission_end = commission_end, commission_start
                commission_tier_basis = None
                commission_period_label = "当前自定义结算期"

            commission_result = compute_monthly_commission(
                sales_df=df_sales,
                attendance_df=df_attendance,
                staff_purchase_df=df_staff_purchase,
                stock_df=df_stock,
                start_date=commission_start,
                end_date=commission_end,
                manager_cashiers=DEFAULT_MANAGER_CASHIERS,
                tier_basis_gross=commission_tier_basis,
            )
            commission_summary = commission_result["summary"]
            commission_employees = commission_result["employees"].copy()
            if commission_mode == "自定义日期范围":
                commission_tier_basis = _commission_annualized_gross(
                    commission_summary["月总营业额"],
                    commission_start,
                    commission_end,
                )
                commission_result = compute_monthly_commission(
                    sales_df=df_sales,
                    attendance_df=df_attendance,
                    staff_purchase_df=df_staff_purchase,
                    stock_df=df_stock,
                    start_date=commission_start,
                    end_date=commission_end,
                    manager_cashiers=DEFAULT_MANAGER_CASHIERS,
                    tier_basis_gross=commission_tier_basis,
                )
                commission_summary = commission_result["summary"]
                commission_employees = commission_result["employees"].copy()

            st.info(f"{commission_period_label}：**{commission_start.strftime('%Y-%m-%d')} 至 {commission_end.strftime('%Y-%m-%d')}**。提成营业额不含换货 EXC 流水；净利润保护沿用「净利润」tab 的 GST/高岛屋抽成/成本/人工逻辑。")

            cm1, cm2, cm3, cm4 = st.columns(4)
            cm1.metric("选中期间 POS 零售总营业额", f"${commission_summary['月总营业额']:,.2f}")
            cm2.metric("当前提成档位", f"{commission_summary['当前档位比例'] * 100:.1f}%")
            cm3.metric("最终提成池", f"${commission_summary['最终提成池']:,.2f}", delta=f"理论 ${commission_summary['理论提成池']:,.2f}", delta_color="off")
            cm4.metric("提成后真实净利润", f"${commission_summary['提成后真实净利润']:,.2f}", delta=f"保护上限 ${commission_summary['利润保护上限']:,.2f}", delta_color="off")

            cm5, cm6, cm7, cm8 = st.columns(4)
            cm5.metric("老板/店长销售额", f"${commission_summary['老板/店长销售额']:,.2f}", help="计入店铺总营业额，但不参与员工提成分配。")
            cm6.metric("员工可分配销售额", f"${commission_summary['员工可分配销售额']:,.2f}")
            cm7.metric("档位判断营业额", f"${commission_summary['月化档位营业额']:,.2f}", help="整月模式等于实际营业额；自定义日期模式会折算成 30 天月化营业额。")
            cm8.metric("扣提成前真实净利润", f"${commission_summary['扣提成前真实净利润']:,.2f}")

            tier_df = pd.DataFrame(
                [
                    {"月总营业额达到": "$15,000", "提成池比例": "0.4%"},
                    {"月总营业额达到": "$20,000", "提成池比例": "0.6%"},
                    {"月总营业额达到": "$30,000", "提成池比例": "0.8%"},
                    {"月总营业额达到": "$50,000", "提成池比例": "1.2%"},
                    {"月总营业额达到": "$65,000", "提成池比例": "1.5%"},
                    {"月总营业额达到": "$80,000", "提成池比例": "1.8%"},
                    {"月总营业额达到": "$100,000", "提成池比例": "2.2%"},
                    {"月总营业额达到": "$120,000", "提成池比例": "2.5%"},
                ]
            )
            with st.expander("查看提成档位表", expanded=False):
                st.dataframe(tier_df, use_container_width=True, hide_index=True)
                st.caption("最终提成池最多不超过扣提成前真实净利润的 20%。")

            if commission_employees.empty:
                st.info("该月份暂无员工销售、考勤或内购记录。")
            else:
                display_commission = commission_employees.copy()
                display_commission["销售贡献占比"] = display_commission["销售贡献占比"] * 100
                st.markdown("### 员工结算明细")
                st.dataframe(
                    display_commission.style.format({
                        "工作时长": "{:.2f}",
                        "基础工资": "${:.2f}",
                        "个人销售额": "${:.2f}",
                        "销售贡献占比": "{:.1f}%",
                        "Commission": "${:.2f}",
                        "内购扣款": "${:.2f}",
                        "最终应发": "${:.2f}",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
                export_commission = commission_employees.copy()
                export_commission["销售贡献占比"] = export_commission["销售贡献占比"] * 100
                st.download_button(
                    "⬇️ 导出月度工资与提成 CSV",
                    export_commission.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"payroll_commission_{commission_start.strftime('%Y%m%d')}_{commission_end.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    with t5:
        st.subheader(f"💎 真实净利润核算 (9% GST 剥离版)")
        
        t5_start, t5_end = date_range_picker("📅 净利润核算日期区间", "📅 Net Profit Date Range", key="admin_net_profit_range_today")
        st.info(f"📅 此看板的净利数据按上方日期区间计算：**{t5_start}** 至 **{t5_end}**")

        if not df_sales.empty:
            df_s_np = df_sales.copy()
            df_s_np['日期_dt'] = pd.to_datetime(df_s_np['日期'], errors='coerce')
            df_s_np = df_s_np.dropna(subset=['日期_dt'])

            df_a_np = df_attendance.copy()
            if not df_a_np.empty:
                df_a_np['日期_dt'] = pd.to_datetime(df_a_np['日期'], errors='coerce')
                df_a_np = df_a_np.dropna(subset=['日期_dt'])
            else:
                df_a_np['日期_dt'] = pd.Series(dtype='datetime64[ns]')

            if not df_s_np.empty:
                fs = df_s_np[(df_s_np['日期_dt'] >= pd.Timestamp(t5_start)) & (df_s_np['日期_dt'] <= pd.Timestamp(t5_end))].copy()
                fa = df_a_np[(df_a_np['日期_dt'] >= pd.Timestamp(t5_start)) & (df_a_np['日期_dt'] <= pd.Timestamp(t5_end))].copy()

                fs['销售数量'] = pd.to_numeric(fs['销售数量'], errors='coerce').fillna(0)
                fs['总营业额'] = pd.to_numeric(fs['总营业额'], errors='coerce').fillna(0.0)

                df_stock_cost = df_stock[['商品名称', '颜色', '进价成本']].copy()
                df_stock_cost['进价成本'] = pd.to_numeric(df_stock_cost['进价成本'], errors='coerce').fillna(0.0)
                fs = fs.merge(df_stock_cost, on=['商品名称', '颜色'], how='left')
                fs['总进价成本'] = fs['销售数量'] * fs['进价成本']

                fs['日期_str'] = fs['日期_dt'].dt.strftime('%Y/%m/%d')
                daily_sales = fs.groupby('日期_str').agg({'总营业额': 'sum', '总进价成本': 'sum'}).reset_index()

                if not fa.empty:
                    fa['核算薪资'] = pd.to_numeric(fa['核算薪资'], errors='coerce').fillna(0.0)
                    fa['日期_str'] = fa['日期_dt'].dt.strftime('%Y/%m/%d')
                    daily_att = fa.groupby('日期_str').agg({'核算薪资': 'sum'}).reset_index()
                    daily_att.rename(columns={'核算薪资': '人工成本'}, inplace=True)
                else:
                    daily_att = pd.DataFrame(columns=['日期_str', '人工成本'])

                daily_np = pd.merge(daily_sales, daily_att, on='日期_str', how='outer').fillna(0.0).sort_values('日期_str', ascending=False)

                daily_np['免税净营业额'] = daily_np['总营业额'] / 1.09
                daily_np['代扣GST(9%)'] = daily_np['总营业额'] - daily_np['免税净营业额']
                daily_np['商场抽成(36%)'] = daily_np['免税净营业额'] * 0.36
                daily_np['商场实际回款'] = daily_np['免税净营业额'] - daily_np['商场抽成(36%)']
                daily_np['毛利润'] = daily_np['商场实际回款'] - daily_np['总进价成本']
                daily_np['真实净利润'] = daily_np['毛利润'] - daily_np['人工成本']

                tot_gross = daily_np['总营业额'].sum()
                tot_net_rev = daily_np['免税净营业额'].sum()
                tot_gst = daily_np['代扣GST(9%)'].sum()
                tot_comm = daily_np['商场抽成(36%)'].sum()
                tot_settlement = daily_np['商场实际回款'].sum()
                tot_cogs = daily_np['总进价成本'].sum()
                tot_wage = daily_np['人工成本'].sum()
                tot_net = daily_np['真实净利润'].sum()

                pct_gst = (tot_gst / tot_gross * 100) if tot_gross > 0 else 0
                pct_comm = (tot_comm / tot_gross * 100) if tot_gross > 0 else 0
                pct_cogs = (tot_cogs / tot_gross * 100) if tot_gross > 0 else 0
                pct_wage = (tot_wage / tot_gross * 100) if tot_gross > 0 else 0
                pct_net = (tot_net / tot_gross * 100) if tot_gross > 0 else 0

                st.info("💡 财务脱水逻辑：顾客支付的含税总额中，9% 为政府消费税 (GST)。高岛屋的 36% 抽成基于**免税净额**计算。实际回款 = 免税净额 - 抽成。")
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("💰 选中期间总营业额", f"${tot_gross:.2f}", delta="100.0% (营收基准)", delta_color="off")
                m2.metric("🏛️ 剥离 GST (9%)", f"${tot_gst:.2f}", delta=f"占比: {pct_gst:.1f}%", delta_color="off")
                m3.metric("📉 商场抽成 (36%)", f"${tot_comm:.2f}", delta=f"占比: {pct_comm:.1f}%", delta_color="off")
                m4.metric("💵 商场实际回款", f"${tot_settlement:.2f}", help="免税额减去抽成后，高岛屋真正打给你的钱")
                
                st.divider()
                
                m5, m6, m7, m8 = st.columns(4)
                m5.metric("📦 商品进价成本", f"${tot_cogs:.2f}", delta=f"占比: {pct_cogs:.1f}%", delta_color="off")
                m6.metric("👥 打卡人工成本", f"${tot_wage:.2f}", delta=f"占比: {pct_wage:.1f}%", delta_color="off")
                m7.metric("💎 选中期间纯利润", f"${tot_net:.2f}", delta=f"含税净利率: {pct_net:.1f}%", delta_color="normal")
                m8.empty()

                st.divider()
                st.markdown("### 📈 每日营收 vs 净利润趋势")
                chart_data_t5 = daily_np.set_index('日期_str')[['总营业额', '真实净利润']].sort_index(ascending=True)
                st.bar_chart(chart_data_t5, use_container_width=True)

                st.markdown("### 📅 每日盈亏明细榜 (Daily P&L)")
                dl_c3, dl_c4 = st.columns([1.5, 4])
                with dl_c3:
                    csv_t5 = convert_df_to_csv(daily_np)
                    st.download_button(
                        label="⬇️ 一键导出净利润明细 (CSV)",
                        data=csv_t5,
                        file_name=f"Takashimaya_净利明细_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        type="primary"
                    )

                show_np = daily_np.rename(columns={'日期_str': '日期'})
                
                def color_net_profit(val):
                    try:
                        val = float(val)
                        if val > 0: return 'background-color: #e6ffe6; color: #006600; font-weight: bold;'
                        elif val < 0: return 'background-color: #ffe6e6; color: #cc0000; font-weight: bold;'
                    except: pass
                    return ''
                
                format_dict = {
                    '总营业额': '${:.2f}', '免税净营业额': '${:.2f}', '代扣GST(9%)': '${:.2f}',
                    '商场抽成(36%)': '${:.2f}', '商场实际回款': '${:.2f}',
                    '总进价成本': '${:.2f}', '人工成本': '${:.2f}',
                    '毛利润': '${:.2f}', '真实净利润': '${:.2f}'
                }
                
                try:
                    styled_np = show_np.style.format(format_dict).map(color_net_profit, subset=['真实净利润'])
                except AttributeError:
                    styled_np = show_np.style.format(format_dict).applymap(color_net_profit, subset=['真实净利润'])

                st.dataframe(styled_np, use_container_width=True, hide_index=True)
            else:
                st.info("暂无有效销售数据进行核算。")
        else:
            st.info("💡 目前没有流水记录，无法计算利润。")

    with t6:
        st.subheader("🤝 B2B 大客户与企采订单管理")
        st.info("💡 B2B订单独立核算，免收快闪店抽成！支持【单一商品】与【多件组合套装】双模式。")

        if not df_b2b.empty:
            for num_col in ['总计应收', '已收定金', '货物成本', '物流成本', '关税']:
                df_b2b[num_col] = pd.to_numeric(df_b2b[num_col], errors='coerce').fillna(0.0)
                
            df_b2b['待收尾款'] = df_b2b['总计应收'] - df_b2b['已收定金']
            df_b2b['B2B净利润'] = df_b2b['总计应收'] - df_b2b['货物成本'] - df_b2b['物流成本'] - df_b2b['关税']
            
            df_b2b['预估净利率'] = df_b2b.apply(lambda r: f"{(r['B2B净利润'] / r['总计应收'] * 100):.1f}%" if r['总计应收'] > 0 else "0.0%", axis=1)
            
            tot_b2b_val = df_b2b['总计应收'].sum()
            tot_b2b_collected = df_b2b['已收定金'].sum()
            tot_b2b_pending = df_b2b['待收尾款'].sum()
            tot_b2b_profit = df_b2b['B2B净利润'].sum()
            
            pct_b2b_profit = (tot_b2b_profit / tot_b2b_val * 100) if tot_b2b_val > 0 else 0.0
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💼 B2B 总合同额", f"${tot_b2b_val:.2f}")
            c2.metric("💰 已回款金额", f"${tot_b2b_collected:.2f}")
            c3.metric("⏳ 待结清尾款", f"${tot_b2b_pending:.2f}")
            c4.metric("💎 B2B 预估净利润", f"${tot_b2b_profit:.2f}", delta=f"净利率: {pct_b2b_profit:.1f}%", delta_color="off")

        with st.expander("➕ 录入全新 B2B 订单", expanded=False):
            col1, col2 = st.columns(2)
            b2b_client = col1.text_input("🏢 客户/企业名称 (必填)", placeholder="例如：NGS")
            b2b_date = col2.date_input("📅 建单日期", value=datetime.now())

            order_mode = st.radio("🛒 选择订单商品模式", ["🎯 单一商品 (常规下单)", "📦 多件组合 / 礼盒套装"], horizontal=True)

            final_name = ""
            final_color = ""
            final_qty = 0
            final_price = 0.0
            final_total = 0.0
            final_notes = ""

            if order_mode == "🎯 单一商品 (常规下单)":
                st.write("📦 **商品信息 (二选一)**")
                f_opts_b2b = get_f(df_stock, "").copy() 
                stock_list = []
                if not f_opts_b2b.empty:
                    f_opts_b2b['dn'] = translate_series(f_opts_b2b['商品名称']).fillna('').astype(str)
                    f_opts_b2b['dc'] = translate_series(f_opts_b2b['颜色']).fillna('').astype(str)
                    f_opts_b2b['label'] = f_opts_b2b['dn'] + " (" + f_opts_b2b['dc'] + ")" 
                    stock_list = f_opts_b2b['label'].tolist()
                    
                col_sel, col_cust_name, col_cust_color = st.columns([2, 1.5, 1])
                b2b_prod = col_sel.selectbox("方式A：选择现有商品", ["(不选择)"] + stock_list)
                b2b_custom_prod = col_cust_name.text_input("方式B：手动输入定制商品", placeholder="填写此项将覆盖左侧")
                b2b_custom_color = col_cust_color.text_input("定制颜色", placeholder="选填")

                c_q, c_p = st.columns(2)
                b2b_qty = c_q.number_input("采购数量", min_value=1, value=100, step=10)
                b2b_price = c_p.number_input("B2B 批发单价 ($)", format="%.2f", min_value=0.0)

                final_total = b2b_qty * b2b_price
                final_qty = b2b_qty
                final_price = b2b_price

                if b2b_custom_prod.strip() != "":
                    final_name = b2b_custom_prod.strip()
                    final_color = b2b_custom_color.strip()
                else:
                    if b2b_prod != "(不选择)":
                        sel_disp_name = b2b_prod.rsplit(" (", 1)[0]
                        sel_disp_color = b2b_prod.rsplit(" (", 1)[1].replace(")", "")
                        final_name = t_val(sel_disp_name, 'cn')
                        final_color = t_val(sel_disp_color, 'cn')
                    else:
                        final_name = ""

            else:
                combo_name = st.text_input("📦 组合大单名称 (必填)", placeholder="例如：NGS 100件定制混装礼盒")
                st.write("👇 **请在下方表格中录入组合包含的商品明细 (可自由添加多行)**")
                
                default_df = pd.DataFrame([{"商品或定制名称": "钛杯", "颜色/规格": "默认", "单价($)": 0.0, "数量": 1}])
                
                edited_cart = st.data_editor(
                    default_df, 
                    num_rows="dynamic", 
                    use_container_width=True, 
                    key="b2b_combo_cart",
                    column_config={
                        "单价($)": st.column_config.NumberColumn(format="%.2f", min_value=0.0), 
                        "数量": st.column_config.NumberColumn(min_value=1, step=1)
                    }
                )

                desc_items = []
                for cart_idx, cart_row in edited_cart.iterrows():
                    try:
                        cart_p = float(cart_row["单价($)"])
                        cart_q = int(cart_row["数量"])
                        cart_n = str(cart_row["商品或定制名称"]).strip()
                        cart_c = str(cart_row["颜色/规格"]).strip()
                        if cart_n:
                            final_total += cart_p * cart_q
                            final_qty += cart_q
                            item_str = f"{cart_n}({cart_c})x{cart_q}" if cart_c else f"{cart_n}x{cart_q}"
                            desc_items.append(item_str)
                    except:
                        pass

                st.info(f"🧮 **系统实时核算：** 此组合共计 **{final_qty}** 件物品，总金额 **${final_total:.2f}**")
                final_name = f"【组合】{combo_name.strip()}"
                final_color = "多件混装"
                final_price = 0.0 
                combo_details_str = " + ".join(desc_items)

            st.markdown("---")
            st.write("🚚 **履约成本与交易状态**")
            c10, c11, c12, c13 = st.columns(4)
            b2b_deposit = c10.number_input("已收定金/首款 ($)", format="%.2f", min_value=0.0)
            b2b_cogs = c11.number_input("预估总货物成本 ($)", format="%.2f", min_value=0.0)
            b2b_shipping = c12.number_input("预估物流总成本 ($)", format="%.2f", min_value=0.0)
            b2b_tax = c13.number_input("预估关税 ($)", format="%.2f", min_value=0.0)

            c8, c9, c_dead = st.columns([1, 1.5, 1])
            b2b_status = c8.selectbox("当前状态", ["意向/沟通中", "已付定金/备货中", "已发货/待结尾款", "✅ 订单已完成"])
            b2b_notes = c9.text_input("附加备注信息", placeholder="发货要求等...")
            b2b_deadline = c_dead.date_input("约定交货日期", value=datetime.now() + timedelta(days=30))

            if st.button("🚀 确认创建 B2B 订单", type="primary", use_container_width=True):
                if b2b_client.strip() == "":
                    st.error("⚠️ 请填写客户/企业名称！")
                elif not final_name or final_name == "【组合】":
                    st.error("⚠️ 请正确选择商品或填写组合名称！")
                else:
                    fresh_b2b = JIT_fetch([B2B_SHEET])[B2B_SHEET]
                    
                    balance = final_total - b2b_deposit
                    if order_mode == "📦 多件组合 / 礼盒套装":
                        final_notes_combined = f"明细: {combo_details_str} | 备注: {b2b_notes}"
                    else:
                        final_notes_combined = b2b_notes

                    new_b2b = pd.DataFrame([[
                        b2b_date.strftime("%Y/%m/%d"), b2b_client, final_name, final_color,
                        final_qty, final_price, final_total, b2b_cogs, b2b_shipping, b2b_tax, b2b_deposit, balance,
                        b2b_deadline.strftime("%Y/%m/%d"), b2b_status, final_notes_combined
                    ]], columns=B2B_COLS)

                    fresh_b2b = pd.concat([new_b2b, fresh_b2b], ignore_index=True)
                    save_data(fresh_b2b, B2B_SHEET)
                    st.success(f"✅ B2B 订单创建成功！客户：{b2b_client}")
                    st.rerun()

        st.divider()
        st.markdown("### 📋 B2B 订单明细榜 (全字段解禁，可直接双击涂改)")
        
        f_b2b = get_f(df_b2b, q)
        if not f_b2b.empty:
            v_b2b = f_b2b.copy()
            v_b2b.insert(0, "选择", False)
            
            disabled_cols = ['待收尾款', 'B2B净利润', '预估净利率']
            
            styled_b2b = v_b2b.style.format({
                'B2B单价': '${:.2f}', '总计应收': '${:.2f}', 
                '货物成本': '${:.2f}', '物流成本': '${:.2f}', '关税': '${:.2f}',
                '已收定金': '${:.2f}', '待收尾款': '${:.2f}', 'B2B净利润': '${:.2f}'
            })
            
            editor_key = f"b2b_editor_{st.session_state.b2b_reset_key}"
            edited_b2b = st.data_editor(
                styled_b2b, 
                column_config={
                    "选择": st.column_config.CheckboxColumn("选择", default=False),
                    "订单状态": st.column_config.SelectboxColumn("订单状态", options=["意向/沟通中", "已付定金/备货中", "已发货/待结尾款", "✅ 订单已完成"])
                }, 
                disabled=disabled_cols, 
                use_container_width=True, hide_index=True, 
                key=editor_key
            )
            
            editor_state = st.session_state.get(editor_key, {})
            if editor_state.get("edited_rows"):
                has_real_edits = False
                fresh_b2b = JIT_fetch([B2B_SHEET])[B2B_SHEET]
                for idx, row in edited_b2b.iterrows():
                    editable_cols = ['货物成本', '物流成本', '关税', '已收定金', '订单状态', '约定交期', '备注']
                    is_changed = False
                    for c in editable_cols:
                        if str(row[c]) != str(v_b2b.loc[idx, c]):
                            is_changed = True
                            break
                    
                    if is_changed:
                        has_real_edits = True
                        for col in B2B_COLS:
                            if col in row:
                                fresh_b2b.at[idx, col] = row[col]
                        
                        total_receivable = float(row['总计应收'] or 0)
                        deposit = float(row['已收定金'] or 0)
                        fresh_b2b.at[idx, '待收尾款'] = total_receivable - deposit
                        
                if has_real_edits:
                    save_data(fresh_b2b[B2B_COLS], B2B_SHEET) 
                    st.success("✅ B2B 订单修改已全量精准保存！")
                    st.session_state.b2b_reset_key += 1
                    st.rerun()

            selected_b2b = edited_b2b[edited_b2b["选择"] == True]
            if not selected_b2b.empty:
                bc1, bc2, _ = st.columns([1.5, 1.5, 4])
                with bc1:
                    if st.button("🗑️ 删除选中订单", type="primary", key="del_b2b"):
                        fresh_b2b = JIT_fetch([B2B_SHEET])[B2B_SHEET]
                        for _, row in selected_b2b.iterrows():
                            fresh_b2b = fresh_b2b[~((fresh_b2b['客户名称'].astype(str).str.strip() == str(row['客户名称']).strip()) & (fresh_b2b['商品名称'].astype(str).str.strip() == str(row['商品名称']).strip()) & (fresh_b2b['创建日期'].astype(str).str.strip() == str(row['创建日期']).strip()))]
                        save_data(fresh_b2b[B2B_COLS], B2B_SHEET)
                        st.session_state.b2b_reset_key += 1 
                        st.rerun()
                with bc2: st.button("🔄 取消选中", key="btn_cancel_b2b", on_click=clear_b2b)
        else:
            st.info("💡 暂无 B2B 订单记录或没有找到符合搜索条件的订单。")

    with t7:
        st.subheader("🗣️ 新加坡本地客户产品反馈池")
        st.info("💡 收集一线真实声音：不论是产品性能还是非产品的本土化优化，都是下一步行动的数据支撑！")

        fb_type_options = [
            "产品功能性", "产品优化", 
            "保温保冷效能", "外观颜值 / 颜色", "材质手感 / 重量", 
            "清洗 / 异味问题", "杯盖 / 密封性", "价格因素", 
            "🌏 本土化优化 (非产品)", "夸奖 / 好评", "其他建议"
        ]
        fb_customer_options = ["本地散客", "VIP / 老客复购", "送礼需求", "游客", "B2B企业客户"]
        fb_status_options = ["🚨 待处理 / 待评估", "📝 已记录 / 待反馈工厂", "✅ 已解决 / 已采纳"]

        with st.expander("➕ 快速录入新反馈", expanded=True):
            f_opts_fb = get_f(df_stock, "").copy()
            with st.form("add_feedback"):
                c1, c2 = st.columns(2)
                fb_date = c1.date_input("反馈日期", value=datetime.now())
                if not f_opts_fb.empty:
                    fb_prod = c2.selectbox("提及的商品", f_opts_fb['商品名称'].unique().tolist() + ["全系产品 / 通用"])
                else:
                    fb_prod = c2.text_input("提及的商品", "全系产品 / 通用")

                c3, c4 = st.columns(2)
                fb_type = c3.selectbox("反馈痛点 / 类型", fb_type_options)
                fb_customer = c4.selectbox("客户画像", fb_customer_options)

                fb_detail = st.text_area("🗣️ 客户原话或详细描述 (越具体越好)", placeholder="例如：客人觉得杯盖拧起来有点紧，或者希望包装袋能换成本地人更喜欢的材质...")

                fb_status = st.selectbox("当前跟进状态", fb_status_options)

                if st.form_submit_button("保存客户反馈", type="primary", use_container_width=True):
                    if fb_detail.strip() == "":
                        st.warning("⚠️ 详细反馈内容不能为空！")
                    else:
                        fresh_fb = JIT_fetch([FEEDBACK_SHEET])[FEEDBACK_SHEET]
                        new_fb = pd.DataFrame([[
                            fb_date.strftime("%Y/%m/%d"), fb_prod, fb_customer, fb_type, fb_detail, fb_status
                        ]], columns=FEEDBACK_COLS)
                        fresh_fb = pd.concat([new_fb, fresh_fb], ignore_index=True)
                        save_data(fresh_fb, FEEDBACK_SHEET)
                        st.success("✅ 宝贵的一线反馈已入库！")
                        st.rerun()

        st.divider()
        
        f_fb = get_f(df_feedback, q)
        if not f_fb.empty:
            fb_c1, fb_c2 = st.columns(2)
            with fb_c1:
                st.markdown("**📌 哪些痛点被疯狂吐槽？(分类雷达)**")
                type_counts = f_fb['反馈类型'].value_counts()
                st.bar_chart(type_counts)
            with fb_c2:
                st.markdown("**📌 哪款产品话题度最高？(商品雷达)**")
                prod_counts = f_fb['商品名称'].value_counts()
                st.bar_chart(prod_counts)

            st.markdown("### 📋 客户反馈追踪处理台 (可直接涂改所有项目)")
            v_fb = f_fb.copy()
            v_fb.insert(0, "选择", False)

            editor_key = f"fb_editor_{st.session_state.fb_reset_key}"
            edited_fb = st.data_editor(
                v_fb,
                column_config={
                    "选择": st.column_config.CheckboxColumn("选择", default=False),
                    "跟进状态": st.column_config.SelectboxColumn("跟进状态", options=fb_status_options),
                    "反馈类型": st.column_config.SelectboxColumn("反馈类型", options=fb_type_options),
                    "客户画像": st.column_config.SelectboxColumn("客户画像", options=fb_customer_options)
                },
                disabled=[], 
                use_container_width=True, hide_index=True,
                key=editor_key
            )

            editor_state = st.session_state.get(editor_key, {})
            if editor_state.get("edited_rows"):
                has_real_edits = False
                fresh_fb = JIT_fetch([FEEDBACK_SHEET])[FEEDBACK_SHEET]
                for idx, row in edited_fb.iterrows():
                    is_changed = False
                    for c in FEEDBACK_COLS:
                        if str(row[c]) != str(v_fb.loc[idx, c]):
                            is_changed = True
                            break
                    if is_changed:
                        has_real_edits = True
                        for col in FEEDBACK_COLS:
                            fresh_fb.at[idx, col] = row[col]
                if has_real_edits:
                    save_data(fresh_fb, FEEDBACK_SHEET)
                    st.success("✅ 客户反馈修改已全量精准保存！")
                    st.session_state.fb_reset_key += 1
                    st.rerun()

            selected_fb = edited_fb[edited_fb["选择"] == True]
            if not selected_fb.empty:
                fbc1, fbc2, _ = st.columns([1.5, 1.5, 4])
                with fbc1:
                    if st.button("🗑️ 删除选中反馈", type="primary", key="del_fb"):
                        fresh_fb = JIT_fetch([FEEDBACK_SHEET])[FEEDBACK_SHEET]
                        for _, row in selected_fb.iterrows():
                            fresh_fb = fresh_fb[~((fresh_fb['详细原话'].astype(str).str.strip() == str(row['详细原话']).strip()) & (fresh_fb['反馈日期'].astype(str).str.strip() == str(row['反馈日期']).strip()) & (fresh_fb['商品名称'].astype(str).str.strip() == str(row['商品名称']).strip()))]
                        save_data(fresh_fb, FEEDBACK_SHEET)
                        st.session_state.fb_reset_key += 1
                        st.rerun()
                with fbc2: st.button("🔄 取消选中", key="btn_cancel_fb", on_click=clear_fb)
        else:
            st.info("💡 暂无客户反馈记录或没有找到符合条件的反馈。")

    with t8:
        st.subheader("🧠 战略 BI")
        st.info("新的 BI 已移到左侧「📅 档期中心 / Popup 对比」。在那里可以管理档期、做单档期 SKU 复盘，并进行两个 popup 档期对比。")
        if st.button("📅 打开档期中心 / Popup 对比", type="primary", use_container_width=True, key="open_campaign_bi_from_tab"):
            st.session_state.admin_page = "campaign_bi"
            st.rerun()

# ================= 🚀 Tab 3/4: 厂商专属层 (Supplier) =================
elif is_supplier:
    with t1:
        render_inventory_snapshot('supplier')
        
    with t2:
        st.subheader(t("💰 销售报表对账查询", "💰 Sales Report Reconciliation"))
        if not df_sales.empty:
            df_s = df_sales.copy()
            df_s['日期_dt'] = pd.to_datetime(df_s['日期'], errors='coerce')
            df_s = df_s.dropna(subset=['日期_dt'])
            if not df_s.empty:
                s_start, s_end = date_range_picker("📅 选择查询日期区间", "📅 Select Date Range", key="sup_sales_date_today")
                    
                f_s = df_s[(df_s['日期_dt'].dt.date >= s_start) & (df_s['日期_dt'].dt.date <= s_end)]
                f_s = get_f(f_s, q)
                if not f_s.empty:
                    f_s['销售数量'] = pd.to_numeric(f_s['销售数量'], errors='coerce').fillna(0)
                    f_s['总营业额'] = pd.to_numeric(f_s['总营业额'], errors='coerce').fillna(0.0)
                    tot_qty, tot_rev = f_s['销售数量'].sum(), f_s['总营业额'].sum()
                    
                    c1, c2 = st.columns(2)
                    c1.metric(t("📦 区间总售出件数", "📦 Total Items Sold"), f"{int(tot_qty)}")
                    c2.metric(t("💰 区间总含税营业额", "💰 Total Sales Amount"), f"${tot_rev:.2f}")
                    
                    f_s['商品名称'] = translate_series(f_s['商品名称'])
                    f_s['颜色'] = translate_series(f_s['颜色'])
                    
                    show_cols = ['订单号', '日期', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']
                    df_disp = f_s[show_cols].copy()
                    if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
                    u_col, t_col = ('Unit Price', 'Total Amount') if st.session_state.lang == 'en' else ('成交单价', '总营业额')
                    st.dataframe(df_disp.style.format({u_col: '${:.2f}', t_col: '${:.2f}'}), use_container_width=True, hide_index=True)
                else: st.info(t("该区间内无符合条件的记录。", "No records found in this range."))
    
    with t3:
        st.subheader(t("📦 进货与入库对账单 (ERP 底单)", "📦 Inbound Records"))
        r_s, r_e = date_range_picker("📅 入库对账日期区间", "📅 Inbound Record Date Range", key="supplier_restock_range_today")
        st.info(f"📅 此对账单按上方日期区间计算：**{r_s}** 至 **{r_e}**")
        
        if not df_restock.empty:
            dr = df_restock.copy()
            dr['dt'] = pd.to_datetime(dr['记录日期'], errors='coerce')
            dr = dr.dropna(subset=['dt'])
            if not dr.empty:
                fr = dr[(dr['dt'].dt.date >= r_s) & (dr['dt'].dt.date <= r_e)]
                fr = get_f(fr, q)
                
                if not fr.empty:
                    fr['操作类型'] = translate_series(fr['操作类型'])
                    a_ops = [str(x) for x in fr['操作类型'].fillna('').unique().tolist() if str(x).strip() != '']
                    s_defs = list(set([op for op in [t_val("入库", "en"), t_val("初始建档", "en"), "入库", "初始建档"] if op in a_ops]))
                    
                    tf = st.multiselect(t("筛选操作类型", "Filter Ops"), options=a_ops, default=s_defs)
                    if tf:
                        fr = fr[fr['操作类型'].isin(tf)]
                        fr['商品名称'] = translate_series(fr['商品名称'])
                        fr['颜色'] = translate_series(fr['颜色'])
                        
                        tot_i = fr['变动数量'].apply(lambda x: pd.to_numeric(x, errors='coerce')).fillna(0).sum()
                        st.metric(t("🚛 筛选后累计变动数量", "🚛 Total Qty"), f"{int(tot_i)}")
                        
                        show_cols = ['记录日期', '操作类型', '商品名称', '颜色', '变动数量', '库位详情', '备注']
                        df_disp = fr[show_cols].copy()
                        if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
                        st.dataframe(df_disp, use_container_width=True, hide_index=True)
                    else:
                        st.info(t("无对应类型的记录。", "No records matched."))
                else:
                    st.info(t("该区间无对账记录。", "No records in range."))

    with t4:
        st.subheader(t("🤝 B2B 订单对账单", "🤝 B2B Orders"))
        b_s, b_e = date_range_picker("📅 B2B 订单日期区间", "📅 B2B Order Date Range", key="supplier_b2b_range_today")
        st.info(f"📅 此对账单按上方日期区间计算：**{b_s}** 至 **{b_e}**")
        
        if not df_b2b.empty:
            db = df_b2b.copy()
            db['dt'] = pd.to_datetime(db['创建日期'], errors='coerce')
            db = db.dropna(subset=['dt'])
            if not db.empty:
                fb = db[(db['dt'].dt.date >= b_s) & (db['dt'].dt.date <= b_e)]
                fb = get_f(fb, q)
                
                if not fb.empty:
                    for c in ['采购数量', 'B2B单价', '总计应收', '已收定金']:
                        if c in fb.columns: fb[c] = pd.to_numeric(fb[c], errors='coerce').fillna(0.0)
                    fb['待收尾款'] = fb['总计应收'] - fb['已收定金']
                    
                    c1, c2 = st.columns(2)
                    c1.metric(t("📦 B2B 总采购件数", "📦 Total B2B Qty"), f"{int(fb['采购数量'].sum())}")
                    c2.metric(t("💰 B2B 总计应收金额", "💰 Total B2B Value"), f"${fb['总计应收'].sum():.2f}")
                    
                    fb['商品名称'] = translate_series(fb['商品名称'])
                    fb['颜色'] = translate_series(fb['颜色'])
                    fb['订单状态'] = translate_series(fb['订单状态'])
                    
                    df_disp = fb[['创建日期', '客户名称', '商品名称', '颜色', '采购数量', 'B2B单价', '总计应收', '已收定金', '待收尾款', '约定交期', '订单状态', '备注']].copy()
                    if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
                    uc, tc, dc, bc = ('B2B Price', 'Total Recv.', 'Deposit', 'Balance') if st.session_state.lang == 'en' else ('B2B单价', '总计应收', '已收定金', '待收尾款')
                    st.dataframe(df_disp.style.format({uc: '${:.2f}', tc: '${:.2f}', dc: '${:.2f}', bc: '${:.2f}'}), use_container_width=True, hide_index=True)
                else:
                    st.info(t("该区间无数据。", "No records in range."))

# ================= 🚀 Tab 3: 员工打卡层 (Employee) =================
elif is_employee:
    with t1:
        render_inventory_snapshot('employee')
        
    with t2:
        render_pos_engine('employee')
        st.divider()
        st.markdown(t("### 📝 我的销售流水 (只读)", "### 📝 My Sales Logs (Read-only)"))
        log_date = st.date_input(t("查询日期", "Log Date"), value=datetime.now().date(), key="employee_sales_log_date")
        fresh_sales_view = JIT_fetch([SALES_SHEET])[SALES_SHEET]
        f_sl = get_f(fresh_sales_view, q)
        if not f_sl.empty:
            log_date_str = log_date.strftime("%Y/%m/%d")
            current_staff = str(st.session_state.get("current_user", "")).strip()
            today_sales = f_sl[(f_sl['日期'].astype(str).str.strip() == log_date_str) & (f_sl['收银员'].astype(str).str.strip() == current_staff)].copy()
            today_sales = sort_sales_latest_first(today_sales)
            if not today_sales.empty:
                today_sales['成交单价'] = pd.to_numeric(today_sales['成交单价'], errors='coerce').fillna(0.0)
                today_sales['总营业额'] = pd.to_numeric(today_sales['总营业额'], errors='coerce').fillna(0.0)
                today_sales['商品名称'] = translate_series(today_sales['商品名称'])
                today_sales['颜色'] = translate_series(today_sales['颜色'])
                if st.session_state.lang == 'en': today_sales.rename(columns=col_map, inplace=True)
                
                u_col = 'Unit Price' if st.session_state.lang == 'en' else '成交单价'
                t_col = 'Total Amount' if st.session_state.lang == 'en' else '总营业额'
                st.dataframe(today_sales.style.format({u_col: '${:.2f}', t_col: '${:.2f}'}), use_container_width=True, hide_index=True)
            else:
                st.write(t("该日期暂无你的销售流水。", "No sales logs for you on this date."))
                
    with t3:
        st.subheader(t("⏰ 员工考勤打卡", "⏰ Staff Timeclock"))
        st.info(t("💡 请如实填报您的上下班时间，系统将自动核算工资。", "💡 Please log your daily working hours below. System will auto-calculate wage."))
        
        with st.form("emp_attendance_form"):
            emp_name = st.session_state.current_user
            st.markdown(f"**{t('当前打卡人', 'Current Staff')}:** `{emp_name}`")
            
            att_date = st.date_input(t("工作日期", "Work Date"), value=datetime.now())
            
            c1, c2 = st.columns(2)
            att_start = c1.time_input(t("上班时间", "Clock In Time"), value=time(10, 0))
            att_end = c2.time_input(t("下班时间", "Clock Out Time"), value=time(18, 0))
            
            if st.form_submit_button(t("✅ 确认打卡 (提交本班次)", "✅ Submit Time"), type="primary", use_container_width=True):
                fresh_att = JIT_fetch([ATT_SHEET])[ATT_SHEET]
                fresh_emp = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                
                # 计算时长
                dt_start = datetime.combine(att_date, att_start)
                dt_end = datetime.combine(att_date, att_end)
                if dt_end < dt_start: dt_end += timedelta(days=1)
                duration_hours = (dt_end - dt_start).total_seconds() / 3600.0
                
                # 强转去空格防匹配报错
                emp_rows = fresh_emp[fresh_emp['员工姓名'].astype(str).str.strip() == str(emp_name).strip()]
                if not emp_rows.empty: hourly_wage = to_float(emp_rows.iloc[0]['时薪'])
                else: hourly_wage = 0.0
                
                total_wage = duration_hours * hourly_wage
                
                new_att = pd.DataFrame([[
                    emp_name, att_date.strftime("%Y/%m/%d"), 
                    att_start.strftime("%H:%M"), att_end.strftime("%H:%M"), 
                    round(duration_hours, 2), round(total_wage, 2)
                ]], columns=ATT_COLS)
                
                fresh_att = pd.concat([new_att, fresh_att], ignore_index=True)
                save_data(fresh_att, ATT_SHEET) 
                
                st.success(t(f"打卡成功！共计 {round(duration_hours, 1)} 小时。", f"Success! Total {round(duration_hours, 1)} hrs."))
                st.rerun()

        st.divider()
        st.markdown(t("### 📝 我的历史打卡记录 (只读)", "### 📝 My Time Logs (Read-only)"))
        f_att = get_f(df_attendance, q)
        my_att = f_att[f_att['员工姓名'].astype(str).str.strip() == str(st.session_state.current_user).strip()].copy() if not f_att.empty else pd.DataFrame()
        
        if not my_att.empty:
            my_att['核算薪资'] = pd.to_numeric(my_att['核算薪资'], errors='coerce').fillna(0.0)
            my_disp = my_att.copy()
            if st.session_state.lang == 'en': my_disp.rename(columns=col_map, inplace=True)
            w_col = 'Est. Wage' if st.session_state.lang == 'en' else '核算薪资'
            st.dataframe(my_disp.style.format({w_col: '${:.2f}'}), use_container_width=True, hide_index=True)
            
            tot_h = pd.to_numeric(my_att['工作时长'], errors='coerce').fillna(0).sum()
            tot_w = my_att['核算薪资'].sum()
            c3, c4 = st.columns(2)
            c3.metric(t("累积总工时", "Total Hours"), f"{tot_h:.1f}")
            c4.metric(t("预估总薪资", "Total Est. Wage"), f"${tot_w:.2f}")
        else:
            st.info(t("暂无打卡记录。", "No time logs found."))

        st.divider()
        st.markdown(t("### 💵 我的提成与工资", "### 💵 My Commission & Wage"))
        st.caption(t(
            "这里只显示你自己的结算数据；自定义日期会用 30 天月化营业额判断档位，但提成按实际期间营业额发放。",
            "Only your own payroll data is shown here. Custom range uses 30-day annualized sales for tiering, while payout uses actual selected-period sales."
        ))

        emp_commission_mode = st.radio(
            t("选择结算方式", "Settlement Mode"),
            [t("按整月结算", "Monthly"), t("自定义日期范围", "Custom Date Range")],
            horizontal=True,
            key="employee_commission_mode",
        )
        if emp_commission_mode == t("按整月结算", "Monthly"):
            emp_commission_month = st.date_input(t("选择结算月份", "Select Month"), value=datetime.now().date().replace(day=1), key="employee_commission_month")
            emp_commission_start = emp_commission_month.replace(day=1)
            if emp_commission_start.month == 12:
                emp_next_month = emp_commission_start.replace(year=emp_commission_start.year + 1, month=1, day=1)
            else:
                emp_next_month = emp_commission_start.replace(month=emp_commission_start.month + 1, day=1)
            emp_commission_end = emp_next_month - timedelta(days=1)
            emp_tier_basis = None
        else:
            emp_c1, emp_c2 = st.columns(2)
            emp_commission_start = emp_c1.date_input(t("开始日期", "Start Date"), value=datetime.now().date().replace(day=1), key="employee_commission_custom_start")
            emp_commission_end = emp_c2.date_input(t("结束日期", "End Date"), value=datetime.now().date(), key="employee_commission_custom_end")
            if emp_commission_start > emp_commission_end:
                emp_commission_start, emp_commission_end = emp_commission_end, emp_commission_start
            emp_tier_basis = None

        emp_commission_result = compute_monthly_commission(
            sales_df=df_sales,
            attendance_df=df_attendance,
            staff_purchase_df=df_staff_purchase,
            stock_df=df_stock,
            start_date=emp_commission_start,
            end_date=emp_commission_end,
            manager_cashiers=DEFAULT_MANAGER_CASHIERS,
            tier_basis_gross=emp_tier_basis,
        )
        if emp_commission_mode == t("自定义日期范围", "Custom Date Range"):
            emp_tier_basis = _commission_annualized_gross(
                emp_commission_result["summary"]["月总营业额"],
                emp_commission_start,
                emp_commission_end,
            )
            emp_commission_result = compute_monthly_commission(
                sales_df=df_sales,
                attendance_df=df_attendance,
                staff_purchase_df=df_staff_purchase,
                stock_df=df_stock,
                start_date=emp_commission_start,
                end_date=emp_commission_end,
                manager_cashiers=DEFAULT_MANAGER_CASHIERS,
                tier_basis_gross=emp_tier_basis,
            )

        emp_commission_view = get_employee_commission_view(emp_commission_result, st.session_state.current_user)
        emp_safe_summary = emp_commission_view["summary"]
        emp_row = emp_commission_view["employee"]
        st.info(t(
            f"当前结算区间：**{emp_commission_start.strftime('%Y-%m-%d')} 至 {emp_commission_end.strftime('%Y-%m-%d')}**",
            f"Settlement period: **{emp_commission_start.strftime('%Y-%m-%d')} to {emp_commission_end.strftime('%Y-%m-%d')}**"
        ))

        if emp_row.empty:
            st.info(t("该区间暂无你的工资或提成数据。", "No wage or commission data for you in this period."))
        else:
            emp_one = emp_row.iloc[0]
            ec1, ec2, ec3, ec4 = st.columns(4)
            ec1.metric(t("我的销售额", "My Sales"), f"${float(emp_one['个人销售额']):,.2f}")
            ec2.metric(t("我的 Commission", "My Commission"), f"${float(emp_one['Commission']):,.2f}", delta=f"{emp_safe_summary['当前档位比例'] * 100:.1f}% tier", delta_color="off")
            ec3.metric(t("我的基础工资", "My Base Wage"), f"${float(emp_one['基础工资']):,.2f}")
            ec4.metric(t("最终应发", "Final Pay"), f"${float(emp_one['最终应发']):,.2f}")

            emp_display = emp_row.copy()
            emp_display["销售贡献占比"] = emp_display["销售贡献占比"] * 100
            st.dataframe(
                emp_display.style.format({
                    "工作时长": "{:.2f}",
                    "基础工资": "${:.2f}",
                    "个人销售额": "${:.2f}",
                    "销售贡献占比": "{:.1f}%",
                    "Commission": "${:.2f}",
                    "内购扣款": "${:.2f}",
                    "最终应发": "${:.2f}",
                }),
                use_container_width=True,
                hide_index=True,
            )
