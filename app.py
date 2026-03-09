import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. 基础配置 ---
st.set_page_config(page_title="Taka 零售与利润管理", layout="wide")
STOCK_FILE = "taka_stock_v4.csv"  # 升级版本号以更新表头
SALES_FILE = "taka_sales_v4.csv"

# 定义新的表头（增加了成本和价格）
STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '展示数量', '货柜数量', '储物间数量', '总库存']
SALES_COLS = ['日期', '商品名称', '颜色', '销售数量', '单价', '总额']

def init_file(file, columns):
    if not os.path.exists(file):
        pd.DataFrame(columns=columns).to_csv(file, index=False)
    else:
        test_df = pd.read_csv(file)
        if list(test_df.columns) != columns:
            # 如果列数不匹配，尝试平滑升级（保留旧数据，补全空列）
            new_df = pd.DataFrame(columns=columns)
            test_df = pd.concat([new_df, test_df], join='outer').fillna(0)
            test_df[columns].to_csv(file, index=False)

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
        c1, c2 = st.columns(2)
        n_cost = c1.number_input("进价成本 (SGD)", min_value=0.0)
        n_price = c2.number_input("售卖价格 (SGD)", min_value=0.0)
        if st.form_submit_button("确认添加"):
            if n_name and n_color:
                new_item = pd.DataFrame([[n_name, n_color, n_cost, n_price, 0, 0, 0, 0]], columns=STOCK_COLS)
                pd.concat([df_stock, new_item], ignore_index=True).to_csv(STOCK_FILE, index=False)
                st.rerun()

if not df_stock.empty:
    with st.sidebar.expander("📝 物理位置/价格校准"):
        df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
        with st.form("audit_form"):
            target = st.selectbox("选择商品", df_stock['label'])
            field = st.selectbox("修改项", ["展示数量", "货柜数量", "储物间数量", "进价成本", "售卖价格"])
            new_val = st.number_input("输入新的准确数值", min_value=0.0, step=1.0)
            if st.form_submit_button("确认修改"):
                idx = df_stock[df_stock['label'] == target].index[0]
                df_stock.at[idx, field] = new_val
                # 重新计算总库存（以防万一）
                df_stock.at[idx, '总库存'] = df_stock.iloc[idx][['展示数量', '货柜数量', '储物间数量']].sum()
                df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                st.success("数据已更新")
                st.rerun()

# --- 3. 主界面 ---
st.title("🏙️ Takashimaya 零售与利润管理系统")

tab1, tab2, tab3 = st.tabs(["📊 实时库存看板", "💰 每日销售记录", "📈 利润与成本分析"])

with tab1:
    st.subheader("当前柜台库存分布")
    st.dataframe(df_stock.drop(columns=['label']) if 'label' in df_stock.columns else df_stock, use_container_width=True)

with tab2:
    st.subheader("销售记账")
    if df_stock.empty:
        st.info("请先在左侧添加产品 SKU")
    else:
        with st.form("sales_entry_form"):
            c1, c2, c3 = st.columns([3, 1, 1])
            s_item_label = c1.selectbox("售出商品", df_stock['label'])
            s_qty = c2.number_input("数量", min_value=1, step=1)
            
            # 自动带出该商品的预设售价，但也允许手动修改（比如打折了）
            idx_p = df_stock[df_stock['label'] == s_item_label].index[0]
            default_price = float(df_stock.at[idx_p, '售卖价格'])
            s_price = c3.number_input("成交单价 (SGD)", min_value=0.0, value=default_price)
            
            sel_date = st.date_input("销售日期", value=datetime.now())
            
            if st.form_submit_button("确认提交账目"):
                name = df_stock.at[idx_p, '商品名称']
                color = df_stock.at[idx_p, '颜色']
                dt_str = sel_date.strftime("%Y-%m-%d")
                total_val = s_qty * s_price
                
                new_row = pd.DataFrame([[dt_str, name, color, s_qty, s_price, total_val]], columns=SALES_COLS)
                pd.concat([new_row, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                
                # 自动扣库存
                df_stock.at[idx_p, '货柜数量'] -= s_qty
                df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量']].sum()
                df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                st.rerun()
    st.dataframe(df_sales, use_container_width=True)

with tab3:
    st.subheader("💰 SKU 盈利能力分析")
    if df_stock.empty:
        st.write("暂无数据")
    else:
        # 计算每个 SKU 的利润
        analysis_df = df_stock.copy()
        analysis_df['单件利润'] = analysis_df['售卖价格'] - analysis_df['进价成本']
        analysis_df['毛利率 (%)'] = (analysis_df['单件利润'] / analysis_df['售卖价格'] * 100).fillna(0)
        
        # 关联销售数据计算总利润
        total_profit = 0
        if not df_sales.empty:
            # 简单的销售额与成本匹配逻辑
            # 注意：这里假设销售时的成本就是当前录入的成本
            summary_sales = df_sales.groupby(['商品名称', '颜色'])['销售数量'].sum().reset_index()
            analysis_df = analysis_df.merge(summary_sales, on=['商品名称', '颜色'], how='left').fillna(0)
            analysis_df['累计贡献利润'] = analysis_df['销售数量'] * analysis_df['单件利润']
            total_profit = analysis_df['累计贡献利润'].sum()
        
        # 核心指标卡片
        m1, m2, m3 = st.columns(3)
        m1.metric("总销售额 (累计)", f"${df_sales['总额'].sum():.2f}")
        m2.metric("预计总利润 (累计)", f"${total_profit:.2f}")
        avg_margin = analysis_df['毛利率 (%)'].mean()
        m3.metric("平均毛利率", f"{avg_margin:.1f}%")

        st.write("### 各 SKU 成本利润明细")
        st.dataframe(analysis_df[['商品名称', '颜色', '进价成本', '售卖价格', '单件利润', '毛利率 (%)', '累计贡献利润']], use_container_width=True)
