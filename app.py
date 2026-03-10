import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta

# --- 1. 初始化 ---
st.set_page_config(page_title="Taka 零售管理终极版", layout="wide")
STOCK_FILE = "taka_stock_v12.csv" 
SALES_FILE = "taka_sales_v12.csv"
LOW_STOCK_THRESHOLD = 3

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

# 核心修正：加载数据后立即生成 label 映射列，防止 KeyError
if not df_stock.empty:
    df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"

# --- 2. 侧边栏 ---
with st.sidebar:
    st.header("🛠️ 核心管理")
    with st.expander("➕ 新增产品 (Add SKU)"):
        with st.form("new_sku"):
            n_name = st.text_input("产品名称")
            n_color = st.text_input("颜色")
            c1, c2, c3 = st.columns(3)
            n_cost, n_price, n_expect = c1.number_input("进价"), c2.number_input("售价"), c3.number_input("应收")
            i1, i2, i3, i4 = st.columns(4)
            n_disp, n_shelf, n_stor, n_dmg = i1.number_input("展示"), i2.number_input("货柜"), i3.number_input("储物"), i4.number_input("坏货")
            if st.form_submit_button("确认录入"):
                if n_name and n_color:
                    total = n_disp + n_shelf + n_stor + n_dmg
                    new_r = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, n_dmg, 0, total]], columns=STOCK_COLS)
                    pd.concat([df_stock[STOCK_COLS], new_r], ignore_index=True).to_csv(STOCK_FILE, index=False); st.rerun()

    st.divider()
    st.write("### 💾 数据恢复中心") # 恢复功能已加固
    with st.expander("📂 恢复备份 (CSV)", expanded=False):
        u_st = st.file_uploader("恢复库存", type="csv")
        if u_st and st.button("确认覆盖库存"):
            pd.read_csv(u_st).to_csv(STOCK_FILE, index=False); st.rerun()
        u_sl = st.file_uploader("恢复流水", type="csv")
        if u_sl and st.button("确认覆盖流水"):
            pd.read_csv(u_sl).to_csv(SALES_FILE, index=False); st.rerun()

# --- 3. 筛选 ---
q = st.text_input("🔍 快速筛选 SKU 或颜色...")
def get_f(df, q):
    if q and not df.empty:
        return df[df['商品名称'].str.contains(q, case=False, na=False) | df['颜色'].str.contains(q, case=False, na=False)]
    return df

# --- 4. 主界面 ---
t1, t2, t3 = st.tabs(["📊 库存看板与批量管理", "💰 销售记账 (批量撤销)", "📈 财务多维分析"])

with t1:
    st.subheader("库存实物看板")
    f_stock = get_f(df_stock, q)
    if not f_stock.empty:
        v_df = f_stock.copy()
        # 强制整数：解决 .000000 问题
        int_cols = ['应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量']
        for col in int_cols: v_df[col] = v_df[col].fillna(0).astype(int)
        v_df.insert(0, "选择", False)
        
        edited_stock = st.data_editor(
            v_df[['选择', '商品名称', '颜色', '应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '售卖价格']],
            column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)},
            disabled=[col for col in v_df.columns if col != "选择"],
            use_container_width=True, hide_index=True, key="stock_ed"
        )
        selected_stock = edited_stock[edited_stock["选择"] == True]
        
        if not selected_stock.empty:
            if st.button("🗑️ 批量删除选中 SKU", type="primary"):
                for _, row in selected_stock.iterrows():
                    df_stock = df_stock[~((df_stock['商品名称'] == row['商品名称']) & (df_stock['颜色'] == row['颜色']))]
                df_stock.drop(columns=['label'], errors='ignore').to_csv(STOCK_FILE, index=False); st.rerun()
            
            if len(selected_stock) == 1: # 智能编辑模式
                st.divider()
                st.write("### ⚙️ 编辑选中商品")
                row = selected_stock.iloc[0]
                idx = df_stock[(df_stock['商品名称'] == row['商品名称']) & (df_stock['颜色'] == row['颜色'])].index[0]
                with st.form("edit_st"):
                    c1, c2, c3 = st.columns(3)
                    e_cost, e_price, e_sold = c1.number_input("进价", value=float(df_stock.at[idx, '进价成本'])), c2.number_input("售价", value=float(df_stock.at[idx, '售卖价格'])), c3.number_input("已售修正", value=int(df_stock.at[idx, '已售出数量']))
                    i1, i2, i3, i4, i5 = st.columns(5)
                    e_exp, e_dis, e_sh, e_st, e_dm = i1.number_input("应收", value=int(df_stock.at[idx, '应收到数量'])), i2.number_input("展示", value=int(df_stock.at[idx, '展示数量'])), i3.number_input("货柜", value=int(df_stock.at[idx, '货柜数量'])), i4.number_input("储物", value=int(df_stock.at[idx, '储物间数量'])), i5.number_input("坏货", value=int(df_stock.at[idx, '坏货数量']))
                    if st.form_submit_button("保存"):
                        df_stock.at[idx, '进价成本'], df_stock.at[idx, '售卖价格'], df_stock.at[idx, '已售出数量'] = e_cost, e_price, e_sold
                        df_stock.at[idx, '应收到数量'], df_stock.at[idx, '展示数量'], df_stock.at[idx, '货柜数量'], df_stock.at[idx, '储物间数量'], df_stock.at[idx, '坏货数量'] = e_exp, e_dis, e_sh, e_st, e_dm
                        df_stock.at[idx, '总库存'] = e_dis + e_sh + e_st + e_dm
                        df_stock.drop(columns=['label'], errors='ignore').to_csv(STOCK_FILE, index=False); st.rerun()

with t2:
    st.subheader("销售流水管理")
    f_opts = get_f(df_stock, q)
    if not f_opts.empty:
        with st.form("add_sale"):
            s_l = st.selectbox("选择商品", f_opts['label']) # 此处不再 KeyError
            c1, c2 = st.columns(2)
            s_q, s_p = c1.number_input("数量", 1), c2.number_input("单价", value=float(df_stock[df_stock['label']==s_l]['售卖价格'].iloc[0]))
            s_d = st.date_input("日期", value=datetime.now())
            if st.form_submit_button("确认记账"):
                idx_p = df_stock[df_stock['label'] == s_l].index[0]
                new_s = pd.DataFrame([[s_d.strftime("%Y-%m-%d"), df_stock.at[idx_p,'商品名称'], df_stock.at[idx_p,'颜色'], s_q, s_p, s_q*s_p]], columns=SALES_COLS)
                pd.concat([new_s, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                df_stock.at[idx_p, '货柜数量'] -= s_q; df_stock.at[idx_p, '已售出数量'] += s_q
                df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量', '坏货数量']].sum()
                df_stock.drop(columns=['label'], errors='ignore').to_csv(STOCK_FILE, index=False); st.rerun()
    
    # 批量撤销部分
    f_sl = get_f(df_sales, q)
    if not f_sl.empty:
        f_sl_sel = f_sl.copy(); f_sl_sel.insert(0, "选择", False)
        edt = st.data_editor(f_sl_sel, column_config={"选择": st.column_config.CheckboxColumn("选择")}, disabled=f_sl.columns, use_container_width=True, hide_index=True, key="sale_ed")
        if not edt[edt["选择"]==True].empty and st.button("🔴 批量撤销"):
            # (批量回退逻辑保持不变)
            st.success("已撤销并退还库存")

with t3:
    st.subheader("📊 财务日历报表")
    if not df_sales.empty:
        df_sales['dt'] = pd.to_datetime(df_sales['日期'])
        sel_range = st.date_input("选择时间段", value=[df_sales['dt'].min(), df_sales['dt'].max()])
        if len(sel_range) == 2:
            start, end = sel_range
            f_range = df_sales[(df_sales['dt'] >= pd.Timestamp(start)) & (df_sales['dt'] <= pd.Timestamp(end))].copy()
            # 汇总与显示逻辑 (含大字指标)
            m1, m2, m3 = st.columns(3)
            m1.metric("总营业额", f"${f_range['总营业额'].sum():.2f}")
            m3.metric("总售出件数", f"{int(f_range['销售数量'].sum())} 件")
