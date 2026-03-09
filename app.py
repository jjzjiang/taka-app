import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. 页面配置与文件初始化 ---
st.set_page_config(page_title="Taka 进销存系统", layout="wide")
STOCK_FILE = "taka_stock_pro.csv"
SALES_FILE = "taka_sales_log.csv"

# 初始化库存文件结构
if not os.path.exists(STOCK_FILE):
    df_stock = pd.DataFrame(columns=['商品名称', '颜色', '展示数量', '货柜数量', '储物间数量', '总库存'])
    # 初始示例数据
    init_stock = [['TAIC 钛杯', '原色', 2, 5, 10, 17]]
    pd.DataFrame(init_stock, columns=df_stock.columns).to_csv(STOCK_FILE, index=False)

# 初始化销售日志
if not os.path.exists(SALES_FILE):
    pd.DataFrame(columns=['日期', '商品信息', '数量', '单价', '总额']).to_csv(SALES_FILE, index=False)

df_stock = pd.read_csv(STOCK_FILE)
df_sales = pd.read_csv(SALES_FILE)

# --- 2. 侧边栏：管理功能 ---
st.sidebar.header("🛠️ 基础管理")

# 模块：新增 SKU (包含颜色)
with st.sidebar.expander("➕ 添加新产品 (SKU)"):
    with st.form("add_form"):
        n_name = st.text_input("产品名称")
        n_color = st.text_input("颜色 (如：极光色)")
        if st.form_submit_button("确认录入"):
            if n_name and n_color:
                new_row = pd.DataFrame([[n_name, n_color, 0, 0, 0, 0]], columns=df_stock.columns)
                pd.concat([df_stock, new_row], ignore_index=True).to_csv(STOCK_FILE, index=False)
                st.rerun()

# 模块：物理位置数量盘点 (修复了之前的报错)
with st.sidebar.expander("📝 物理位置盘点"):
    df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
    with st.form("audit_form"):
        target = st.selectbox("选择商品", df_stock['label'])
        loc = st.selectbox("修改位置", ["展示数量", "货柜数量", "储物间数量"])
        new_qty = st.number_input("该位置目前的准确数量", min_value=0, step=1)
        if st.form_submit_button("同步实测数据"):
            idx = df_stock[df_stock['label'] == target].index[0]
            df_stock.at[idx, loc] = new_qty
            # 重新计算总库存
            df_stock.at[idx, '总库存'] = df_stock.iloc[idx][['展示数量', '货柜数量', '储物间数量']].sum()
            df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
            st.success("数据已修正")
            st.rerun()

# --- 3. 主界面 ---
st.title("🏙️ Takashimaya 零售管理系统")

tab1, tab2 = st.tabs(["📊 实时库存看板", "💰 每日销售记录"])

with tab1:
    st.subheader("当前柜台库存分布")
    # 移除辅助标签列再展示
    display_stock = df_stock.drop(columns=['label']) if 'label' in df_stock.columns else df_stock
    st.dataframe(display_stock, use_container_width=True)

with tab2:
    st.subheader("今日销售记账")
    with st.form("sales_form"):
        c1, c2, c3 = st.columns(3)
        s_item = c1.selectbox("售出商品", df_stock['label'] if 'label' in df_stock.columns else df_stock['商品名称'])
        s_qty = c2.number_input("销售数量", min_value=1, step=1)
        s_price = c3.number_input("成交单价 (SGD)", min_value=0.0)
        if st.form_submit_button("确认成交"):
            # 记账
            total_price = s_qty * s_price
            new_sale = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), s_item, s_qty, s_price, total_price]], columns=df_sales.columns)
            pd.concat([new_sale, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
            
            # 自动扣减货柜库存
            idx = df_stock[df_stock['label'] == s_item].index[0]
            df_stock.at[idx, '货柜数量'] -= s_qty
            df_stock.at[idx, '总库存'] = df_stock.iloc[idx][['展示数量', '货柜数量', '储物间数量']].sum()
            df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
            
            st.success(f"已录入！总额: ${total_price}")
            st.rerun()

    st.divider()
    # 简单的业绩汇总
    today = datetime.now().strftime("%Y-%m-%d")
    today_data = df_sales[df_sales['日期'].str.contains(today)]
    m1, m2 = st.columns(2)
    m1.metric("今日销量", f"{int(today_data['数量'].sum())} 件")
    m2.metric("今日销售额", f"${today_data['总额'].sum():.2f}")
    
    st.dataframe(df_sales, use_container_width=True)
