import streamlit as st
import pandas as pd
import os
from datetime import datetime, time

# --- 1. 基础配置 ---
st.set_page_config(page_title="Taka 零售管理系统", layout="wide")
STOCK_FILE = "taka_stock_v3.csv"
SALES_FILE = "taka_sales_v3.csv"

# 定义统一的表头
STOCK_COLS = ['商品名称', '颜色', '展示数量', '货柜数量', '储物间数量', '总库存']
SALES_COLS = ['日期', '商品名称', '颜色', '销售数量', '单价', '总额']

# 初始化文件
def init_file(file, columns):
    if not os.path.exists(file):
        pd.DataFrame(columns=columns).to_csv(file, index=False)
    else:
        test_df = pd.read_csv(file)
        if list(test_df.columns) != columns:
            pd.DataFrame(columns=columns).to_csv(file, index=False)

init_file(STOCK_FILE, STOCK_COLS)
init_file(SALES_FILE, SALES_COLS)

df_stock = pd.read_csv(STOCK_FILE)
df_sales = pd.read_csv(SALES_FILE)

# --- 2. 侧边栏管理 ---
st.sidebar.header("🛠️ 基础管理")

with st.sidebar.expander("➕ 添加新产品 (SKU)"):
    with st.form("add_sku_form"):
        n_name = st.text_input("产品名称")
        n_color = st.text_input("颜色")
        if st.form_submit_button("确认添加"):
            if n_name and n_color:
                new_item = pd.DataFrame([[n_name, n_color, 0, 0, 0, 0]], columns=STOCK_COLS)
                pd.concat([df_stock, new_item], ignore_index=True).to_csv(STOCK_FILE, index=False)
                st.rerun()

if not df_stock.empty:
    with st.sidebar.expander("📝 物理位置盘点"):
        df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
        with st.form("audit_form"):
            target = st.selectbox("选择商品", df_stock['label'])
            loc = st.selectbox("修改位置", ["展示数量", "货柜数量", "储物间数量"])
            new_qty = st.number_input("实测准确数量", min_value=0, step=1)
            if st.form_submit_button("同步实测数据"):
                idx = df_stock[df_stock['label'] == target].index[0]
                df_stock.at[idx, loc] = new_qty
                df_stock.at[idx, '总库存'] = df_stock.iloc[idx][['展示数量', '货柜数量', '储物间数量']].sum()
                df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                st.success("库存已修正")
                st.rerun()

# --- 3. 主界面 ---
st.title("🏙️ Takashimaya 零售管理系统")

tab1, tab2 = st.tabs(["📊 实时库存看板", "💰 每日销售记录"])

with tab1:
    st.subheader("当前柜台库存分布")
    st.dataframe(df_stock.drop(columns=['label']) if 'label' in df_stock.columns else df_stock, use_container_width=True)

with tab2:
    st.subheader("销售记账 (支持补录)")
    if df_stock.empty:
        st.info("请先在左侧添加产品 SKU")
    else:
        with st.form("sales_entry_form"):
            # 第一行：商品和数量
            c1, c2, c3 = st.columns([3, 1, 1])
            s_item_label = c1.selectbox("售出商品", df_stock['label'])
            s_qty = c2.number_input("数量", min_value=1, step=1)
            s_price = c3.number_input("单价 (SGD)", min_value=0.0)
            
            # 第二行：自定义时间 (新功能)
            c4, c5 = st.columns(2)
            sel_date = c4.date_input("销售日期", value=datetime.now())
            sel_time = c5.time_input("销售具体时间", value=datetime.now().time())
            
            if st.form_submit_button("确认提交账目"):
                # 获取商品信息
                idx = df_stock[df_stock['label'] == s_item_label].index[0]
                name = df_stock.at[idx, '商品名称']
                color = df_stock.at[idx, '颜色']
                
                # 合并日期和时间
                dt_combined = datetime.combine(sel_date, sel_time).strftime("%Y-%m-%d %H:%M")
                
                # 1. 记账
                total_val = s_qty * s_price
                new_row = pd.DataFrame([[dt_combined, name, color, s_qty, s_price, total_val]], columns=SALES_COLS)
                pd.concat([new_row, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                
                # 2. 自动扣减库存
                df_stock.at[idx, '货柜数量'] -= s_qty
                df_stock.at[idx, '总库存'] = df_stock.iloc[idx][['展示数量', '货柜数量', '储物间数量']].sum()
                df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                
                st.success(f"已补录 {dt_combined} 的账目！总额: ${total_val}")
                st.rerun()

    st.divider()
    # 业绩统计
    st.write("### 历史销售统计")
    m1, m2 = st.columns(2)
    m1.metric("累计销售总量", f"{int(df_sales['销售数量'].sum())} 件")
    m2.metric("累计总营业额", f"${df_sales['总额'].sum():.2f}")
    
    st.dataframe(df_sales, use_container_width=True)
