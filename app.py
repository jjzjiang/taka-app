import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. 基础配置与文件加载 ---
st.set_page_config(page_title="Taka 进销存完全版", layout="wide")
STOCK_FILE = "taka_stock_v6.csv" 
SALES_FILE = "taka_sales_v6.csv"

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

# --- 2. 侧边栏：管理与删除功能 ---
st.sidebar.header("🛠️ 基础管理")

# 模块：新增 SKU
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

# 模块：物理位置/价格调整
if not df_stock.empty:
    df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
    with st.sidebar.expander("📝 数量/价格校准"):
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

    # 模块：删除 SKU (危险区域)
    with st.sidebar.expander("⚠️ 危险区域 (删除 SKU)"):
        st.warning("删除 SKU 会抹除该商品所有库存数据，请谨慎操作。")
        del_target = st.selectbox("选择要删除的商品", df_stock['label'], key="del_sku")
        if st.button("彻底删除该产品"):
            df_stock = df_stock[df_stock['label'] != del_target]
            df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
            st.success(f"已删除 {del_target}")
            st.rerun()

# --- 3. 主界面布局 ---
st.title("🏙️ Takashimaya 零售管理系统")
t1, t2, t3 = st.tabs(["📊 实时库存看板", "💰 销售记账与撤销", "📈 利润分析看板"])

with t1:
    st.subheader("当前柜台库存分布")
    if not df_stock.empty:
        view_df = df_stock.copy()
        view_df['单件利润'] = view_df['售卖价格'] - view_df['进价成本']
        view_df['毛利率'] = ((view_df['单件利润'] / view_df['售卖价格']) * 100).fillna(0).map("{:.1f}%".format)
        cols_to_show = ['商品名称', '颜色', '售卖价格', '毛利率', '展示数量', '货柜数量', '储物间数量', '总库存']
        st.dataframe(view_df[cols_to_show], use_container_width=True)
    else:
        st.info("尚未录入产品")

with t2:
    st.subheader("销售记录管理")
    col_l, col_r = st.columns([1, 1])
    
    with col_l:
        st.write("### 1. 新增销售")
        if df_stock.empty: st.info("请先添加 SKU")
        else:
            with st.form("sales_form"):
                s_label = st.selectbox("售出商品", df_stock['label'])
                c_qty, c_pr = st.columns(2)
                s_qty = c_qty.number_input("数量", min_value=1, step=1)
                idx_p = df_stock[df_stock['label'] == s_label].index[0]
                s_price = c_pr.number_input("单价 (SGD)", min_value=0.0, value=float(df_stock.at[idx_p, '售卖价格']))
                sel_date = st.date_input("销售日期", value=datetime.now())
                if st.form_submit_button("确认提交记录"):
                    total = s_qty * s_price
                    new_sale = pd.DataFrame([[sel_date.strftime("%Y-%m-%d"), df_stock.at[idx_p, '商品名称'], df_stock.at[idx_p, '颜色'], s_qty, s_price, total]], columns=SALES_COLS)
                    pd.concat([new_sale, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                    # 扣减库存
                    df_stock.at[idx_p, '货柜数量'] -= s_qty
                    df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量']].sum()
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()

    with col_r:
        st.write("### 2. 撤销/删除记录")
        if not df_sales.empty:
            st.info("删除销售记录将自动归还库存至‘货柜数量’")
            # 显示带索引的简易列表方便选择
            df_sales['cancel_label'] = df_sales['日期'] + " | " + df_sales['商品名称'] + " (" + df_sales['销售数量'].astype(str) + "件)"
            del_idx = st.selectbox("选择要撤销的记录", options=range(len(df_sales)), format_func=lambda x: df_sales.iloc[x]['cancel_label'])
            
            if st.button("确认撤销此笔销售"):
                sale_to_del = df_sales.iloc[del_idx]
                # 寻找对应的库存并归还
                match_idx = df_stock[(df_stock['商品名称'] == sale_to_del['商品名称']) & (df_stock['颜色'] == sale_to_del['颜色'])].index
                if not match_idx.empty:
                    idx_s = match_idx[0]
                    df_stock.at[idx_s, '货柜数量'] += sale_to_del['销售数量']
                    df_stock.at[idx_s, '总库存'] = df_stock.iloc[idx_s][['展示数量', '货柜数量', '储物间数量']].sum()
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                
                # 删除销售行
                df_sales.drop(df_sales.index[del_idx]).drop(columns=['cancel_label']).to_csv(SALES_FILE, index=False)
                st.success("记录已撤销，库存已回退！")
                st.rerun()
        else:
            st.write("暂无销售记录")

    st.divider()
    st.write("### 销售流水清单")
    st.dataframe(df_sales.drop(columns=['cancel_label']) if 'cancel_label' in df_sales.columns else df_sales, use_container_width=True)

with t3:
    st.subheader("💰 盈利能力实时分析")
    if not df_stock.empty:
        analysis = df_stock.copy()
        analysis['单件利润'] = analysis['售卖价格'] - analysis['进价成本']
        analysis['毛利率 (%)'] = ((analysis['单件利润'] / analysis['售卖价格']) * 100).fillna(0)
        
        if not df_sales.empty:
            summary = df_sales.groupby(['商品名称', '颜色'])['销售数量'].sum().reset_index()
            analysis = analysis.merge(summary, on=['商品名称', '颜色'], how='left').fillna(0)
            analysis['累计毛利'] = analysis['销售数量'] * analysis['单件利润']
        else:
            analysis['销售数量'], analysis['累计毛利'] = 0, 0

        m1, m2, m3 = st.columns(3)
        m1.metric("总营业额", f"${df_sales['总营业额'].sum():.2f}")
        m2.metric("累计利润", f"${analysis['累计毛利'].sum():.2f}")
        m3.metric("平均毛利率", f"{analysis['毛利率 (%)'].mean():.1f}%")
        
        st.dataframe(analysis[['商品名称', '颜色', '进价成本', '售卖价格', '单件利润', '毛利率 (%)', '累计毛利']].style.format({'毛利率 (%)': "{:.1f}%"}), use_container_width=True)
