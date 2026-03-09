import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. 配置与文件初始化 ---
st.set_page_config(page_title="Taka 进销存-全功能修复版", layout="wide")
STOCK_FILE = "taka_stock_final.csv" 
SALES_FILE = "taka_sales_final.csv"

# 统一表头
STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '展示数量', '货柜数量', '储物间数量', '总库存']
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

# --- 2. 侧边栏：核心管理中心 ---
with st.sidebar:
    st.header("🛠️ 核心管理")
    
    # 功能 A: 新增 SKU (已修复：加回初始数量输入)
    with st.expander("➕ 新增产品 (Add SKU)", expanded=True):
        with st.form("new_sku_form"):
            n_name = st.text_input("产品名称")
            n_color = st.text_input("颜色")
            
            st.write("--- 价格设置 ---")
            c1, c2 = st.columns(2)
            n_cost = c1.number_input("进价 (SGD)", min_value=0.0)
            n_price = c2.number_input("售价 (SGD)", min_value=0.0)
            
            st.write("--- 初始库存录入 ---")
            n_display = st.number_input("展示数量", min_value=0, step=1)
            n_shelf = st.number_input("货柜数量", min_value=0, step=1)
            n_storage = st.number_input("储物间数量", min_value=0, step=1)
            
            if st.form_submit_button("确认录入商品"):
                if n_name and n_color:
                    # 自动计算总库存
                    n_total = n_display + n_shelf + n_storage
                    new_row = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_display, n_shelf, n_storage, n_total]], columns=STOCK_COLS)
                    pd.concat([df_stock, new_row], ignore_index=True).to_csv(STOCK_FILE, index=False)
                    st.success(f"已录入: {n_name}，初始总库存: {n_total}")
                    st.rerun()
                else:
                    st.error("请完整填写名称和颜色")

    st.divider()
    # (保留数据备份与恢复功能...)
    st.write("### 💾 数据备份中心")
    st.download_button("📥 下载库存备份", df_stock.to_csv(index=False).encode('utf-8-sig'), f"stock_{datetime.now().strftime('%m%d')}.csv", "text/csv")
    st.download_button("📥 下载销售备份", df_sales.to_csv(index=False).encode('utf-8-sig'), f"sales_{datetime.now().strftime('%m%d')}.csv", "text/csv")

# --- 3. 全局搜索过滤 ---
st.write("### 🔍 SKU 快速筛选")
search_q = st.text_input("输入关键词查找商品", placeholder="例如：钛杯...")

def get_filtered(df, q):
    if q:
        mask = df['商品名称'].str.contains(q, case=False, na=False) | \
               df['颜色'].str.contains(q, case=False, na=False)
        return df[mask]
    return df

# --- 4. 主界面标签页 ---
st.title("🏙️ Takashimaya 零售管理系统")
t1, t2, t3 = st.tabs(["📊 库存看板", "💰 销售记账", "📈 利润分析"])

with t1:
    f_stock = get_filtered(df_stock, search_q)
    st.subheader("当前柜台分布")
    # 计算毛利率
    view_df = f_stock.copy()
    view_df['单件利润'] = view_df['售卖价格'] - view_df['进价成本']
    view_df['毛利率'] = ((view_df['单件利润'] / view_df['售卖价格']) * 100).fillna(0).map("{:.1f}%".format)
    st.dataframe(view_df[['商品名称', '颜色', '售卖价格', '毛利率', '展示数量', '货柜数量', '储物间数量', '总库存']], use_container_width=True)
    
    # 底部修正功能 (保留)
    if not df_stock.empty:
        st.divider()
        st.write("### ⚙️ 信息修正")
        df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
        target = st.selectbox("选择商品", df_stock['label'])
        idx = df_stock[df_stock['label'] == target].index[0]
        with st.expander("修改详情"):
            with st.form("edit_form"):
                e_name = st.text_input("产品名称", value=df_stock.at[idx, '商品名称'])
                c1, c2, c3 = st.columns(3)
                e_disp = c1.number_input("展示数量", value=int(df_stock.at[idx, '展示数量']))
                e_shelf = c2.number_input("货柜数量", value=int(df_stock.at[idx, '货柜数量']))
                e_stor = c3.number_input("储物间数量", value=int(df_stock.at[idx, '储物间数量']))
                if st.form_submit_button("保存修改"):
                    df_stock.at[idx, '商品名称'] = e_name
                    df_stock.at[idx, '展示数量'], df_stock.at[idx, '货柜数量'], df_stock.at[idx, '储物间数量'] = e_disp, e_shelf, e_stor
                    df_stock.at[idx, '总库存'] = e_disp + e_shelf + e_stor
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()

# --- 后续销售记账(t2)和利润分析(t3)逻辑保持不变 ---
# (为了节省篇幅，此处省略，请确保在你的文件中保留之前的完整代码)
