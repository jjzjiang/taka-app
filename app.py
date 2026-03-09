import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta

# --- 1. 配置与文件初始化 ---
st.set_page_config(page_title="Taka 零售与财务专业版", layout="wide")
# 维持 v6 版本确保字段一致
STOCK_FILE = "taka_stock_final_v6.csv" 
SALES_FILE = "taka_sales_final_v6.csv"

STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '应收到数量', '展示数量', '货柜数量', '储物间数量', '坏货数量', '已售出数量', '总库存']
SALES_COLS = ['日期', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']

def load_data(file, columns):
    if not os.path.exists(file):
        df = pd.DataFrame(columns=columns)
        df.to_csv(file, index=False)
        return df
    df = pd.read_csv(file)
    for col in columns:
        if col not in df.columns: df[col] = 0
    return df[columns]

df_stock = load_data(STOCK_FILE, STOCK_COLS)
df_sales = load_data(SALES_FILE, SALES_COLS)

# --- 2. 侧边栏：核心管理与备份恢复 ---
with st.sidebar:
    st.header("🛠️ 核心管理")
    with st.expander("➕ 新增产品 (Add SKU)", expanded=False):
        with st.form("new_sku_form"):
            n_name = st.text_input("产品名称")
            n_color = st.text_input("颜色")
            c1, c2, c3 = st.columns(3)
            n_cost = c1.number_input("进价 (SGD)", min_value=0.0)
            n_price = c2.number_input("售价 (SGD)", min_value=0.0)
            n_expect = c3.number_input("应收到数量", min_value=0)
            st.write("--- 初始库存分布 ---")
            i1, i2, i3, i4 = st.columns(4)
            n_disp, n_shelf, n_stor, n_dmg = i1.number_input("展示"), i2.number_input("货柜"), i3.number_input("储物"), i4.number_input("坏货")
            if st.form_submit_button("确认录入商品"):
                if n_name and n_color:
                    n_total = n_disp + n_shelf + n_stor + n_dmg
                    new_row = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, n_dmg, 0, n_total]], columns=STOCK_COLS)
                    pd.concat([df_stock, new_row], ignore_index=True).to_csv(STOCK_FILE, index=False)
                    st.rerun()

    st.divider()
    st.write("### 💾 数据中心")
    st.download_button("📥 下载库存备份", df_stock.to_csv(index=False).encode('utf-8-sig'), "stock.csv", "text/csv")
    st.download_button("📥 下载销售记录", df_sales.to_csv(index=False).encode('utf-8-sig'), "sales.csv", "text/csv")
    with st.expander("📂 恢复备份 (CSV)"):
        up_st = st.file_uploader("1. 恢复库存", type="csv")
        if up_st and st.button("确认覆盖库存"):
            pd.read_csv(up_st).to_csv(STOCK_FILE, index=False)
            st.rerun()
        up_sl = st.file_uploader("2. 恢复销售", type="csv")
        if up_sl and st.button("确认覆盖销售"):
            pd.read_csv(up_sl).to_csv(SALES_FILE, index=False)
            st.rerun()

# --- 3. 全局搜索 ---
st.write("### 🔍 SKU 快速筛选")
search_q = st.text_input("输入关键词查找...", placeholder="搜索将同步联动所有报表...")

def get_filtered(df, q):
    if q and not df.empty:
        return df[df['商品名称'].str.contains(q, case=False, na=False) | df['颜色'].str.contains(q, case=False, na=False)]
    return df

# --- 4. 主界面布局 ---
st.title("🏙️ Takashimaya 零售管理系统")
t1, t2, t3 = st.tabs(["📊 库存看板与编辑", "💰 批量销售记账", "📈 周期财务分析"])

with t1:
    f_stock = get_filtered(df_stock, search_q)
    st.subheader("当前柜台分布")
    view_df = f_stock.copy()
    view_df['单件利润'] = view_df['售卖价格'] - view_df['进价成本']
    view_df['毛利率'] = ((view_df['单件利润'] / view_df['售卖价格']) * 100).fillna(0).map("{:.1f}%".format)
    show_cols = ['商品名称', '颜色', '售卖价格', '毛利率', '应收到数量', '已售出数量', '坏货数量', '展示数量', '货柜数量', '储物间数量', '总库存']
    st.dataframe(view_df[show_cols], use_container_width=True)
    
    if not df_stock.empty:
        st.divider()
        st.write("### ⚙️ SKU 信息修正与校准")
        df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
        target = st.selectbox("选择商品", df_stock['label'], key="t1_edit")
        idx = df_stock[df_stock['label'] == target].index[0]
        with st.expander("点击展开修改参数"):
            with st.form("edit_form"):
                e_name = st.text_input("产品名称", value=df_stock.at[idx, '商品名称'])
                c1, c2, c3 = st.columns(3)
                e_cost = c1.number_input("进价成本", value=float(df_stock.at[idx, '进价成本']))
                e_price = c2.number_input("售卖价格", value=float(df_stock.at[idx, '售卖价格']))
                e_sold = c3.number_input("已售数量修正", value=int(df_stock.at[idx, '已售出数量']))
                i1, i2, i3, i4, i5 = st.columns(5)
                e_expect, e_disp, e_shelf, e_stor, e_dmg = i1.number_input("应收", value=int(df_stock.at[idx, '应收到数量'])), i2.number_input("展示", value=int(df_stock.at[idx, '展示数量'])), i3.number_input("货柜", value=int(df_stock.at[idx, '货柜数量'])), i4.number_input("储物", value=int(df_stock.at[idx, '储物间数量'])), i5.number_input("坏货", value=int(df_stock.at[idx, '坏货数量']))
                if st.form_submit_button("保存更改"):
                    df_stock.at[idx, '商品名称'] = e_name
                    df_stock.at[idx, '进价成本'], df_stock.at[idx, '售卖价格'], df_stock.at[idx, '已售出数量'] = e_cost, e_price, e_sold
                    df_stock.at[idx, '应收到数量'], df_stock.at[idx, '展示数量'], df_stock.at[idx, '货柜数量'], df_stock.at[idx, '储物间数量'], df_stock.at[idx, '坏货数量'] = e_expect, e_disp, e_shelf, e_stor, e_dmg
                    df_stock.at[idx, '总库存'] = e_disp + e_shelf + e_stor + e_dmg
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()

with t2:
    st.subheader("销售记账与批量操作")
    with st.expander("➕ 新增销售记账", expanded=True):
        f_options = get_filtered(df_stock, search_q)
        if not f_options.empty:
            df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
            with st.form("sales_form"):
                s_label = st.selectbox("售出商品", f_options['label'])
                c_qty, c_pr = st.columns(2)
                s_qty = c_qty.number_input("数量", min_value=1, step=1)
                idx_p = df_stock[df_stock['label'] == s_label].index[0]
                s_price = c_pr.number_input("成交价", value=float(df_stock.at[idx_p, '售卖价格']))
                sel_date = st.date_input("日期", value=datetime.now())
                if st.form_submit_button("确认成交"):
                    new_sale = pd.DataFrame([[sel_date.strftime("%Y-%m-%d"), df_stock.at[idx_p, '商品名称'], df_stock.at[idx_p, '颜色'], s_qty, s_price, s_qty*s_price]], columns=SALES_COLS)
                    pd.concat([new_sale, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                    df_stock.at[idx_p, '货柜数量'] -= s_qty
                    df_stock.at[idx_p, '已售出数量'] += s_qty
                    df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量', '坏货数量']].sum()
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()

    st.divider()
    st.write("### 🧾 勾选批量撤销记录")
    f_sales = get_filtered(df_sales, search_q)
    if not f_sales.empty:
        f_sales_select = f_sales.copy()
        f_sales_select.insert(0, "选择", False)
        edited_df = st.data_editor(f_sales_select, column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, disabled=f_sales.columns, use_container_width=True, hide_index=True)
        selected = edited_df[edited_df["选择"] == True]
        if not selected.empty:
            if st.button("🔴 批量撤销选中记录", type="primary"):
                for _, row in selected.iterrows():
                    match = df_stock[(df_stock['商品名称'] == row['商品名称']) & (df_stock['颜色'] == row['颜色'])].index
                    if not match.empty:
                        s_idx = match[0]
                        df_stock.at[s_idx, '货柜数量'] += row['销售数量']
                        df_stock.at[s_idx, '已售出数量'] -= row['销售数量']
                        df_stock.at[s_idx, '总库存'] = df_stock.iloc[s_idx][['展示数量', '货柜数量', '储物间数量', '坏货数量']].sum()
                for _, row in selected.iterrows():
                    df_sales = df_sales[~((df_sales['日期'] == row['日期']) & (df_sales['商品名称'] == row['商品名称']) & (df_sales['颜色'] == row['颜色']) & (df_sales['销售数量'] == row['销售数量']))]
                df_stock.to_csv(STOCK_FILE, index=False); df_sales.to_csv(SALES_FILE, index=False)
                st.rerun()

with t3:
    st.subheader("📈 财务周期报表 (MBA 决策版)")
    if df_sales
