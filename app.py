import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. 文件与初始化 ---
st.set_page_config(page_title="Taka 进销存系统", layout="wide")
STOCK_FILE = "taka_stock_pro.csv"
SALES_FILE = "taka_sales_log.csv"

# 初始化库存文件
if not os.path.exists(STOCK_FILE):
    df_stock = pd.DataFrame(columns=['商品名称', '颜色', '展示数量', '货柜数量', '储物间数量', '总库存'])
    # 预设你主打的品牌数据
    init_stock = [
        ['TAIC钛杯-经典款', '钛色', 2, 5, 20, 27],
        ['BlackInTi-商务款', '哑光黑', 1, 3, 15, 19]
    ]
    pd.DataFrame(init_stock, columns=df_stock.columns).to_csv(STOCK_FILE, index=False)

# 初始化销售日志文件
if not os.path.exists(SALES_FILE):
    df_sales = pd.DataFrame(columns=['日期', '商品信息', '数量', '单价', '总额', '备注'])
    df_sales.to_csv(SALES_FILE, index=False)

df_stock = pd.read_csv(STOCK_FILE)
df_sales = pd.read_csv(SALES_FILE)

# --- 2. 侧边栏：SKU 管理与库存更新 ---
st.sidebar.header("🛠️ 基础管理")

# 模块 A：新增 SKU
with st.sidebar.expander("➕ 添加新产品"):
    with st.form("add_form"):
        n_name = st.text_input("产品名称")
        n_color = st.text_input("颜色")
        if st.form_submit_button("确认添加"):
            if n_name and n_color:
                new_row = pd.DataFrame([[n_name, n_color, 0, 0, 0, 0]], columns=df_stock.columns)
                df_stock = pd.concat([df_stock, new_row], ignore_index=True)
                df_stock.to_csv(STOCK_FILE, index=False)
                st.rerun()

# 模块 B：盘点更新（直接修改物理位置数量）
with st.sidebar.expander("📝 物理盘点更新"):
    df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
    target = st.selectbox("选择商品", df_stock['label'])
    loc = st.selectbox("修改位置", ["展示数量", "货柜数量", "储物间数量"])
    new_qty = st.number_input("实测准确数量", min_value=0, step=1)
    if st.form_submit_button("同步实测数据"):
        idx = df_stock[df_stock['label'] == target].index[0]
        df_stock.at[idx, loc] = new_qty
        # 重新计算该行总库存
        df_stock.at[idx, '总库存'] = df_stock.iloc[idx][['展示数量', '货柜数量', '储物间数量']].sum()
        df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
        st.success("库存已修正")
        st.rerun()

# --- 3. 主界面逻辑 ---
st.title("🏙️ Takashimaya 零售管理系统")

# 使用标签页区分功能
tab1, tab2 = st.tabs(["📊 实时库存看板", "💰 每日销售记录"])

with tab1:
    st.subheader("当前柜台库存分布")
    st.dataframe(df_stock.drop(columns=['label']) if 'label' in df_stock.columns else df_stock, use_container_width=True)
    
    # 简单的库存预警
    low_stock = df_stock[df_stock['总库存'] < 5]
    if not low_stock.empty:
        st.error(f"⚠️ 以下商品总库存低于5件，请注意补货: {', '.join(low_stock['商品名称'].tolist())}")

with tab2:
    st.subheader("今日销售录入")
    col1, col2, col3, col4 = st.columns([3, 1, 1, 2])
    
    with st.form("sales_form"):
        c1, c2, c3 = st.columns(3)
        s_item = c1.selectbox("售出商品", df_stock['label'])
        s_qty = c2.number_input("销售数量", min_value=1, step=1)
        s_price = c3.number_input("成交单价 (SGD)", min_value=0.0, step=0.1)
        s_note = st.text_input("备注 (如：客户姓名或折扣原因)")
        
        if st.form_submit_button("确认记账"):
            total_price = s_qty * s_price
            today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            new_sale = pd.DataFrame([[today_str, s_item, s_qty, s_price, total_price, s_note]], columns=df_sales.columns)
            
            # 保存销售记录
            new_df_sales = pd.concat([new_sale, df_sales], ignore_index=True)
            new_df_sales.to_csv(SALES_FILE, index=False)
            
            # 【重要】自动扣减“货柜数量”（通常默认从货柜拿货）
            idx = df_stock[df_stock['label'] == s_item].index[0]
            df_stock.at[idx, '货柜数量'] -= s_qty
            df_stock.at[idx, '总库存'] = df_stock.iloc[idx][['展示数量', '货柜数量', '储物间数量']].sum()
            df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
            
            st.success(f"记账成功！总额: ${total_price}")
            st.rerun()

    st.divider()
    
    # 业绩汇总
    today_date = datetime.now().strftime("%Y-%m-%d")
    # 筛选今天的记录（简单匹配日期字符串）
    today_sales = df_sales[df_sales['日期'].str.contains(today_date)]
    
    m1, m2, m3 = st.columns(3)
    m1.metric("今日销售总量", f"{int(today_sales['数量'].sum())} 件")
    m2.metric("今日总营业额", f"${today_sales['总额'].sum():.2f}")
    m3.metric("平均客单价", f"${today_sales['单价'].mean() if not today_sales.empty else 0:.2f}")

    st.subheader("历史销售流水")
    st.dataframe(df_sales, use_container_width=True)

# 导出按钮
if st.button("导出所有数据 (CSV)"):
    st.download_button("下载库存表", df_stock.to_csv(index=False).encode('utf-8'), "stock.csv")
    st.download_button("下载销售日志", df_sales.to_csv(index=False).encode('utf-8'), "sales.csv")
