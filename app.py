import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. 配置与文件初始化 ---
st.set_page_config(page_title="Taka 进销存-销售关联版", layout="wide")
# 升级版本号以确保列名更新
STOCK_FILE = "taka_stock_final_v3.csv" 
SALES_FILE = "taka_sales_final_v3.csv"

# 更新表头：加入了“已售出数量”
STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '应收到数量', '展示数量', '货柜数量', '储物间数量', '已售出数量', '总库存']
SALES_COLS = ['日期', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']

def load_data(file, columns):
    if not os.path.exists(file):
        df = pd.DataFrame(columns=columns)
        df.to_csv(file, index=False)
        return df
    df = pd.read_csv(file)
    # 自动补全缺失列，确保旧数据平滑过渡
    for col in columns:
        if col not in df.columns:
            df[col] = 0
    return df[columns]

df_stock = load_data(STOCK_FILE, STOCK_COLS)
df_sales = load_data(SALES_FILE, SALES_COLS)

# --- 2. 侧边栏：核心管理中心 ---
with st.sidebar:
    st.header("🛠️ 核心管理")
    
    # 功能 A: 新增 SKU
    with st.expander("➕ 新增产品 (Add SKU)", expanded=True):
        with st.form("new_sku_form"):
            n_name = st.text_input("产品名称")
            n_color = st.text_input("颜色")
            
            st.write("--- 财务与物流对账 ---")
            c1, c2, c3 = st.columns(3)
            n_cost = c1.number_input("进价 (SGD)", min_value=0.0)
            n_price = c2.number_input("售价 (SGD)", min_value=0.0)
            n_expect = c3.number_input("应收到数量", min_value=0, step=1)
            
            st.write("--- 初始实收库存 ---")
            i1, i2, i3 = st.columns(3)
            n_display = i1.number_input("展示数量", min_value=0, step=1)
            n_shelf = i2.number_input("货柜数量", min_value=0, step=1)
            n_storage = i3.number_input("储物间数量", min_value=0, step=1)
            
            if st.form_submit_button("确认录入"):
                if n_name and n_color:
                    n_total = n_display + n_shelf + n_storage
                    # 初始已售出数量设为 0
                    new_row = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_display, n_shelf, n_storage, 0, n_total]], columns=STOCK_COLS)
                    pd.concat([df_stock, new_row], ignore_index=True).to_csv(STOCK_FILE, index=False)
                    st.success(f"已录入: {n_name}")
                    st.rerun()

    st.divider()
    st.write("### 💾 数据备份中心")
    st.download_button("📥 下载库存表", df_stock.to_csv(index=False).encode('utf-8-sig'), f"stock_{datetime.now().strftime('%m%d')}.csv", "text/csv")
    st.download_button("📥 下载销售流水", df_sales.to_csv(index=False).encode('utf-8-sig'), f"sales_{datetime.now().strftime('%m%d')}.csv", "text/csv")

# --- 3. 全局搜索过滤 ---
st.write("### 🔍 SKU 快速筛选")
search_q = st.text_input("输入关键词查找商品...", placeholder="搜索将同步联动下拉菜单...")

def get_filtered(df, q):
    if q:
        mask = df['商品名称'].str.contains(q, case=False, na=False) | \
               df['颜色'].str.contains(q, case=False, na=False)
        return df[mask]
    return df

# --- 4. 主界面标签页 ---
st.title("🏙️ Takashimaya 零售管理系统")
t1, t2, t3 = st.tabs(["📊 库存看板", "💰 销售记账与撤销", "📈 利润分析"])

with t1:
    f_stock = get_filtered(df_stock, search_q)
    st.subheader("当前柜台分布")
    
    view_df = f_stock.copy()
    view_df['单件利润'] = view_df['售卖价格'] - view_df['进价成本']
    view_df['毛利率'] = ((view_df['单件利润'] / view_df['售卖价格']) * 100).fillna(0).map("{:.1f}%".format)
    
    # 调整显示顺序：加入了“已售出数量”
    show_cols = ['商品名称', '颜色', '售卖价格', '毛利率', '应收到数量', '已售出数量', '展示数量', '货柜数量', '储物间数量', '总库存']
    st.dataframe(view_df[show_cols], use_container_width=True)
    
    if not df_stock.empty:
        st.divider()
        st.write("### ⚙️ 信息校准")
        df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
        target = st.selectbox("选择商品进行校准", df_stock['label'])
        idx = df_stock[df_stock['label'] == target].index[0]
        
        with st.expander("修改详情 (含手动修正已售数量)"):
            with st.form("edit_form"):
                e_name = st.text_input("产品名称", value=df_stock.at[idx, '商品名称'])
                c1, c2, c3 = st.columns(3)
                e_cost = c1.number_input("进价成本", value=float(df_stock.at[idx, '进价成本']))
                e_price = c2.number_input("售卖价格", value=float(df_stock.at[idx, '售卖价格']))
                e_sold = c3.number_input("已售出数量 (手动修正)", value=int(df_stock.at[idx, '已售出数量']))
                
                i1, i2, i3, i4 = st.columns(4)
                e_expect = i1.number_input("应收到数量", value=int(df_stock.at[idx, '应收到数量']))
                e_disp = i2.number_input("展示数量", value=int(df_stock.at[idx, '展示数量']))
                e_shelf = i3.number_input("货柜数量", value=int(df_stock.at[idx, '货柜数量']))
                e_stor = i4.number_input("储物间数量", value=int(df_stock.at[idx, '储物间数量']))
                
                if st.form_submit_button("保存所有更改"):
                    df_stock.at[idx, '商品名称'] = e_name
                    df_stock.at[idx, '进价成本'], df_stock.at[idx, '售卖价格'], df_stock.at[idx, '已售出数量'] = e_cost, e_price, e_sold
                    df_stock.at[idx, '应收到数量'], df_stock.at[idx, '展示数量'] = e_expect, e_disp
                    df_stock.at[idx, '货柜数量'], df_stock.at[idx, '储物间数量'] = e_shelf, e_stor
                    df_stock.at[idx, '总库存'] = e_disp + e_shelf + e_stor
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()

with t2:
    st.subheader("销售记录管理")
    col_l, col_r = st.columns(2)
    
    with col_l:
        st.write("### 1. 记账")
        f_options = get_filtered(df_stock, search_q)
        if f_options.empty: st.info("请先在搜索框输入或添加 SKU")
        else:
            df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
            with st.form("sales_form"):
                s_label = st.selectbox("售出商品", f_options['label'])
                c_qty, c_pr = st.columns(2)
                s_qty = c_qty.number_input("数量", min_value=1, step=1)
                idx_p = df_stock[df_stock['label'] == s_label].index[0]
                s_price = c_pr.number_input("成交单价 (SGD)", min_value=0.0, value=float(df_stock.at[idx_p, '售卖价格']))
                sel_date = st.date_input("销售日期", value=datetime.now())
                
                if st.form_submit_button("确认提交记录"):
                    total = s_qty * s_price
                    new_sale = pd.DataFrame([[sel_date.strftime("%Y-%m-%d"), df_stock.at[idx_p, '商品名称'], df_stock.at[idx_p, '颜色'], s_qty, s_price, total]], columns=SALES_COLS)
                    pd.concat([new_sale, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                    
                    # --- 核心关联逻辑 ---
                    # 1. 扣减货柜库存
                    df_stock.at[idx_p, '货柜数量'] -= s_qty
                    # 2. 增加已售出数量
                    df_stock.at[idx_p, '已售出数量'] += s_qty
                    # 3. 重新计算总库存
                    df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量']].sum()
                    
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()

    with col_r:
        st.write("### 2. 撤销记录")
        if not df_sales.empty:
            df_sales['cancel_l'] = df_sales['日期'] + " | " + df_sales['商品名称'] + " (" + df_sales['销售数量'].astype(str) + "件)"
            del_idx = st.selectbox("选择要撤销的记录", options=range(len(df_sales)), format_func=lambda x: df_sales.iloc[x]['cancel_l'])
            
            if st.button("确认撤销此笔销售"):
                sale_to_del = df_sales.iloc[del_idx]
                match = df_stock[(df_stock['商品名称'] == sale_to_del['商品名称']) & (df_stock['颜色'] == sale_to_del['颜色'])].index
                
                if not match.empty:
                    idx_s = match[0]
                    # 1. 退还货柜库存
                    df_stock.at[idx_s, '货柜数量'] += sale_to_del['销售数量']
                    # 2. 扣减已售出数量
                    df_stock.at[idx_s, '已售出数量'] -= sale_to_del['销售数量']
                    # 3. 重新计算总库存
                    df_stock.at[idx_s, '总库存'] = df_stock.iloc[idx_s][['展示数量', '货柜数量', '储物间数量']].sum()
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                
                df_sales.drop(df_sales.index[del_idx]).drop(columns=['cancel_l']).to_csv(SALES_FILE, index=False)
                st.rerun()

    st.divider()
    st.dataframe(get_filtered(df_sales, search_q), use_container_width=True)

with t3:
    st.subheader("💰 盈利能力看板")
    # (此处的累计毛利计算会自动基于 STOCK 表中最新的 已售出数量 进行更准确的展示)
    analysis = get_filtered(df_stock, search_q).copy()
    if not analysis.empty:
        analysis['单件利润'] = analysis['售卖价格'] - analysis['进价成本']
        analysis['毛利率 (%)'] = ((analysis['单件利润'] / analysis['售卖价格']) * 100).fillna(0)
        # 直接使用关联后的 已售出数量
        analysis['累计利润'] = analysis['已售出数量'] * analysis['单件利润']
        
        m1, m2 = st.columns(2)
        m1.metric("当前筛选-总营业额", f"${(analysis['售卖价格'] * analysis['已售出数量']).sum():.2f}")
        m2.metric("当前筛选-累计利润", f"${analysis['累计利润'].sum():.2f}")
        
        st.dataframe(analysis[['商品名称', '颜色', '进价成本', '售卖价格', '单件利润', '毛利率 (%)', '已售出数量', '累计利润']].style.format({'毛利率 (%)': "{:.1f}%"}), use_container_width=True)
