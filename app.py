import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. 核心配置与文件初始化 ---
st.set_page_config(page_title="Taka 零售与利润管理", layout="wide")
STOCK_FILE = "taka_stock_final.csv"
SALES_FILE = "taka_sales_final.csv"

# 严格定义的列名
STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '展示数量', '货柜数量', '储物间数量', '总库存']
SALES_COLS = ['日期', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']

def load_data(file, columns):
    if not os.path.exists(file):
        df = pd.DataFrame(columns=columns)
        df.to_csv(file, index=False)
        return df
    return pd.read_csv(file)

df_stock = load_data(STOCK_FILE, STOCK_COLS)
df_sales = load_data(SALES_FILE, SALES_COLS)

# --- 2. 侧边栏：SKU 与库存管理 ---
st.sidebar.header("🛠️ 基础管理")

with st.sidebar.expander("➕ 添加新产品 (SKU)"):
    with st.form("new_sku_form"):
        n_name = st.text_input("产品名称")
        n_color = st.text_input("颜色")
        c1, c2 = st.columns(2)
        n_cost = c1.number_input("进价成本 (SGD)", min_value=0.0)
        n_price = c2.number_input("建议售价 (SGD)", min_value=0.0)
        if st.form_submit_button("确认录入"):
            if n_name and n_color:
                new_row = pd.DataFrame([[n_name, n_color, n_cost, n_price, 0, 0, 0, 0]], columns=STOCK_COLS)
                pd.concat([df_stock, new_row], ignore_index=True).to_csv(STOCK_FILE, index=False)
                st.rerun()

if not df_stock.empty:
    with st.sidebar.expander("📝 物理位置/价格调整"):
        df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
        with st.form("audit_form"):
            target = st.selectbox("选择商品", df_stock['label'])
            field = st.selectbox("修改项", ["展示数量", "货柜数量", "储物间数量", "进价成本", "售卖价格"])
            new_val = st.number_input("输入新数值", min_value=0.0, step=1.0)
            if st.form_submit_button("确认修改"):
                idx = df_stock[df_stock['label'] == target].index[0]
                df_stock.at[idx, field] = new_val
                df_stock.at[idx, '总库存'] = df_stock.iloc[idx][['展示数量', '货柜数量', '储物间数量']].sum()
                df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                st.rerun()

# --- 3. 主界面布局 ---
st.title("🏙️ Takashimaya 零售管理系统")
t1, t2, t3 = st.tabs(["📊 实时库存看板", "💰 销售记账 (补录)", "📈 利润分析看板"])

with t1:
    st.subheader("当前柜台库存分布")
    st.dataframe(df_stock.drop(columns=['label']) if 'label' in df_stock.columns else df_stock, use_container_width=True)

with t2:
    st.subheader("销售数据录入")
    if df_stock.empty:
        st.info("请先在左侧添加 SKU")
    else:
        with st.form("sales_form"):
            c1, c2, c3 = st.columns([2, 1, 1])
            s_label = c1.selectbox("售出商品", df_stock['label'])
            s_qty = c2.number_input("数量", min_value=1, step=1)
            # 自动带出价格
            idx_p = df_stock[df_stock['label'] == s_label].index[0]
            s_price = c3.number_input("成交单价", min_value=0.0, value=float(df_stock.at[idx_p, '售卖价格']))
            
            sel_date = st.date_input("销售日期", value=datetime.now())
            
            if st.form_submit_button("确认提交"):
                name = df_stock.at[idx_p, '商品名称']
                color = df_stock.at[idx_p, '颜色']
                total = s_qty * s_price
                # 写入销售日志
                new_sale = pd.DataFrame([[sel_date.strftime("%Y-%m-%d"), name, color, s_qty, s_price, total]], columns=SALES_COLS)
                pd.concat([new_sale, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                # 扣减货柜库存
                df_stock.at[idx_p, '货柜数量'] -= s_qty
                df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量']].sum()
                df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                st.success(f"已成功录入 {name} 的销售记录")
                st.rerun()
    st.dataframe(df_sales, use_container_width=True)

with t3:
    st.subheader("💰 盈利能力实时分析")
    if df_stock.empty:
        st.write("暂无产品数据")
    else:
        # 计算逻辑
        analysis = df_stock.copy()
        analysis['单件利润'] = analysis['售卖价格'] - analysis['进价成本']
        analysis['毛利率 (%)'] = (analysis['单件利润'] / analysis['售卖价格'] * 100).fillna(0)
        
        # 统计销售
        if not df_sales.empty:
            summary = df_sales.groupby(['商品名称', '颜色'])['销售数量'].sum().reset_index()
            analysis = analysis.merge(summary, on=['商品名称', '颜色'], how='left').fillna(0)
            analysis['累计毛利'] = analysis['销售数量'] * analysis['单件利润']
        else:
            analysis['销售数量'] = 0
            analysis['累计毛利'] = 0

        # 指标卡
        m1, m2, m3 = st.columns(3)
        m1.metric("总营业额", f"${df_sales['总营业额'].sum():.2f}")
        m2.metric("累计利润", f"${analysis['累计毛利'].sum():.2f}")
        m3.metric("平均毛利率", f"{analysis['毛利率 (%)'].mean():.1f}%")
        
        st.write("### 各 SKU 盈利明细")
        st.dataframe(analysis[['商品名称', '颜色', '进价成本', '售卖价格', '单件利润', '销售数量', '累计毛利']], use_container_width=True)
