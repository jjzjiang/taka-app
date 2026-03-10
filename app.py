import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta

# --- 1. 配置与文件初始化 ---
st.set_page_config(page_title="Taka 进销存-库存逻辑修正版", layout="wide")
# 升级版本号以确保逻辑刷新
STOCK_FILE = "taka_stock_v8_final.csv" 
SALES_FILE = "taka_sales_v8_final.csv"

# 字段定义：总库存 = 展示 + 货柜 + 储物间 + 坏货 (不含已售)
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

# --- 2. 侧边栏：核心管理 ---
with st.sidebar:
    st.header("🛠️ 核心管理")
    with st.expander("➕ 新增产品 (Add SKU)", expanded=False):
        with st.form("new_sku"):
            n_name = st.text_input("产品名称")
            n_color = st.text_input("颜色")
            c1, c2, c3 = st.columns(3)
            n_cost, n_price, n_expect = c1.number_input("进价"), c2.number_input("售价"), c3.number_input("应收数量")
            st.write("--- 初始库存分布 (Physical) ---")
            i1, i2, i3, i4 = st.columns(4)
            n_disp, n_shelf, n_stor, n_dmg = i1.number_input("展示"), i2.number_input("货柜"), i3.number_input("储物"), i4.number_input("坏货")
            if st.form_submit_button("确认录入"):
                if n_name and n_color:
                    # 关键逻辑：总库存只计算当前的实物分布
                    total_remaining = n_disp + n_shelf + n_stor + n_dmg
                    new_r = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, n_dmg, 0, total_remaining]], columns=STOCK_COLS)
                    pd.concat([df_stock, new_r], ignore_index=True).to_csv(STOCK_FILE, index=False)
                    st.rerun()

    st.divider()
    st.write("### 💾 数据中心")
    st.download_button("📥 备份库存", df_stock.to_csv(index=False).encode('utf-8-sig'), "stock.csv", "text/csv")
    st.download_button("📥 备份流水", df_sales.to_csv(index=False).encode('utf-8-sig'), "sales.csv", "text/csv")

# --- 3. 筛选逻辑 ---
st.write("### 🔍 SKU 快速筛选")
q = st.text_input("输入关键词（名称或颜色）查找...")

def get_f(df, q):
    if q and not df.empty:
        return df[df['商品名称'].str.contains(q, case=False, na=False) | df['颜色'].str.contains(q, case=False, na=False)]
    return df

# --- 4. 主界面 ---
t1, t2, t3 = st.tabs(["📊 库存看板与编辑", "💰 销售记账 (从货柜扣减)", "📈 财务报表分析"])

with t1:
    f_stock = get_f(df_stock, q)
    st.subheader("当前柜台分布 (Remaining Physical Stock)")
    view_df = f_stock.copy()
    view_df['单件利润'] = view_df['售卖价格'] - view_df['进价成本']
    view_df['毛利率'] = ((view_df['单件利润'] / view_df['售卖价格']) * 100).fillna(0).map("{:.1f}%".format)
    # 重新整理列，清晰展示对账
    st.dataframe(view_df[['商品名称', '颜色', '应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '售卖价格', '毛利率']], use_container_width=True)
    
    # 底部校准
    if not df_stock.empty:
        st.divider()
        st.write("### ⚙️ 信息/实物校准")
        df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
        target = st.selectbox("选择商品", df_stock['label'])
        idx = df_stock[df_stock['label'] == target].index[0]
        with st.form("edit_stock"):
            e_name = st.text_input("名称", value=df_stock.at[idx, '商品名称'])
            c1, c2, c3 = st.columns(3)
            e_cost, e_price, e_sold = c1.number_input("成本", value=float(df_stock.at[idx, '进价成本'])), c2.number_input("售价", value=float(df_stock.at[idx, '售卖价格'])), c3.number_input("已售修正", value=int(df_stock.at[idx, '已售出数量']))
            i1, i2, i3, i4, i5 = st.columns(5)
            e_exp, e_dis, e_sh, e_st, e_dm = i1.number_input("应收", value=int(df_stock.at[idx, '应收到数量'])), i2.number_input("展示", value=int(df_stock.at[idx, '展示数量'])), i3.number_input("货柜", value=int(df_stock.at[idx, '货柜数量'])), i4.number_input("储物", value=int(df_stock.at[idx, '储物间数量'])), i5.number_input("坏货", value=int(df_stock.at[idx, '坏货数量']))
            if st.form_submit_button("保存校准"):
                df_stock.at[idx, '商品名称'] = e_name
                df_stock.at[idx, '进价成本'], df_stock.at[idx, '售卖价格'], df_stock.at[idx, '已售出数量'] = e_cost, e_price, e_sold
                df_stock.at[idx, '应收到数量'], df_stock.at[idx, '展示数量'], df_stock.at[idx, '货柜数量'], df_stock.at[idx, '储物间数量'], df_stock.at[idx, '坏货数量'] = e_exp, e_dis, e_sh, e_st, e_dm
                # 重新计算总库存：不包含已售出
                df_stock.at[idx, '总库存'] = e_dis + e_sh + e_st + e_dm
                df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                st.rerun()

with t2:
    st.subheader("销售记账")
    # ... (批量撤销逻辑保留)
    with st.expander("➕ 新增销售 (扣减柜台库存)", expanded=True):
        f_opts = get_f(df_stock, q)
        if not f_opts.empty:
            df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
            with st.form("add_sale"):
                s_l = st.selectbox("商品", f_opts['label'])
                c1, c2 = st.columns(2)
                s_q = c1.number_input("数量", min_value=1, step=1)
                idx_p = df_stock[df_stock['label'] == s_l].index[0]
                s_p = c2.number_input("成交单价", value=float(df_stock.at[idx_p, '售卖价格']))
                s_d = st.date_input("日期", value=datetime.now())
                if st.form_submit_button("确认记账"):
                    new_s = pd.DataFrame([[s_d.strftime("%Y-%m-%d"), df_stock.at[idx_p, '商品名称'], df_stock.at[idx_p, '颜色'], s_q, s_p, s_q*s_p]], columns=SALES_COLS)
                    pd.concat([new_s, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                    
                    # --- 核心扣减逻辑确认 ---
                    # 1. 仅从货柜数量扣除
                    df_stock.at[idx_p, '货柜数量'] -= s_q
                    # 2. 已售出增加
                    df_stock.at[idx_p, '已售出数量'] += s_q
                    # 3. 总库存重算：展示 + 货柜(已减少) + 储物 + 坏货
                    df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量', '坏货数量']].sum()
                    
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()
    # (此处保留批量撤销逻辑)

with t3:
    # ... (保持周期报表逻辑)
    st.subheader("📈 财务报表分析")
    if not df_sales.empty:
        period = st.radio("时间粒度", ["Daily", "Weekly (Mon Start)", "Monthly"], horizontal=True)
        # (报表生成代码...)
