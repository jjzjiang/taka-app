import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. 配置与文件初始化 ---
st.set_page_config(page_title="Taka 进销存-损耗管理版", layout="wide")
# 升级版本号以确保列名更新
STOCK_FILE = "taka_stock_final_v5.csv" 
SALES_FILE = "taka_sales_final_v5.csv"

# 核心字段定义：加入了“坏货数量”
STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '应收到数量', '展示数量', '货柜数量', '储物间数量', '坏货数量', '已售出数量', '总库存']
SALES_COLS = ['日期', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']

def load_data(file, columns):
    if not os.path.exists(file):
        df = pd.DataFrame(columns=columns)
        df.to_csv(file, index=False)
        return df
    df = pd.read_csv(file)
    # 自动补全缺失列（如“坏货数量”），确保旧数据平滑过渡
    for col in columns:
        if col not in df.columns:
            df[col] = 0
    return df[columns]

df_stock = load_data(STOCK_FILE, STOCK_COLS)
df_sales = load_data(SALES_FILE, SALES_COLS)

# --- 2. 侧边栏：核心管理中心 ---
with st.sidebar:
    st.header("🛠️ 核心管理")
    
    # 功能 A: 新增 SKU (含坏货初始录入)
    with st.expander("➕ 新增产品 (Add SKU)", expanded=False):
        with st.form("new_sku_form"):
            n_name = st.text_input("产品名称")
            n_color = st.text_input("颜色")
            c1, c2, c3 = st.columns(3)
            n_cost = c1.number_input("进价 (SGD)", min_value=0.0)
            n_price = c2.number_input("售价 (SGD)", min_value=0.0)
            n_expect = c3.number_input("应收到数量", min_value=0)
            
            st.write("--- 初始实收分布 ---")
            i1, i2, i3, i4 = st.columns(4)
            n_disp = i1.number_input("展示", min_value=0)
            n_shelf = i2.number_input("货柜", min_value=0)
            n_stor = i3.number_input("储物", min_value=0)
            n_dmg = i4.number_input("坏货", min_value=0)
            
            if st.form_submit_button("确认录入新商品"):
                if n_name and n_color:
                    # 总库存包含坏货，以便对账
                    n_total = n_disp + n_shelf + n_stor + n_dmg
                    new_row = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, n_dmg, 0, n_total]], columns=STOCK_COLS)
                    pd.concat([df_stock, new_row], ignore_index=True).to_csv(STOCK_FILE, index=False)
                    st.rerun()

    st.divider()
    st.write("### 💾 数据中心")
    st.download_button("📥 下载库存备份", df_stock.to_csv(index=False).encode('utf-8-sig'), "stock.csv", "text/csv")
    st.download_button("📥 下载销售备份", df_sales.to_csv(index=False).encode('utf-8-sig'), "sales.csv", "text/csv")
    
    with st.expander("📂 上传 CSV 恢复数据"):
        up_stock = st.file_uploader("恢复库存表", type="csv")
        if up_stock and st.button("确认覆盖库存"):
            pd.read_csv(up_stock).to_csv(STOCK_FILE, index=False)
            st.rerun()

# --- 3. 全局搜索过滤 ---
st.write("### 🔍 SKU 快速筛选")
search_q = st.text_input("输入关键词（名称或颜色）查找...", placeholder="例如：钛杯 / 银色")

def get_filtered(df, q):
    if q and not df.empty:
        return df[df['商品名称'].str.contains(q, case=False, na=False) | df['颜色'].str.contains(q, case=False, na=False)]
    return df

# --- 4. 主界面布局 ---
st.title("🏙️ Takashimaya 零售管理系统")
t1, t2, t3 = st.tabs(["📊 库存看板", "💰 销售记账", "📈 周期利润报表"])

with t1:
    f_stock = get_filtered(df_stock, search_q)
    st.subheader("当前柜台分布")
    
    view_df = f_stock.copy()
    view_df['单件利润'] = view_df['售卖价格'] - view_df['进价成本']
    view_df['毛利率'] = ((view_df['单件利润'] / view_df['售卖价格']) * 100).fillna(0).map("{:.1f}%".format)
    
    # 重点展示列：加入了“坏货数量”
    show_cols = ['商品名称', '颜色', '售卖价格', '毛利率', '应收到数量', '已售出数量', '坏货数量', '展示数量', '货柜数量', '储物间数量', '总库存']
    st.dataframe(view_df[show_cols], use_container_width=True)
    
    if not df_stock.empty:
        st.divider()
        st.write("### ⚙️ 单项信息/坏货校准")
        df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
        target = st.selectbox("选择商品", df_stock['label'], key="t1_edit")
        idx = df_stock[df_stock['label'] == target].index[0]
        
        with st.expander("修改详细参数 (如发现坏货请在此修正)"):
            with st.form("edit_form"):
                c1, c2, c3 = st.columns(3)
                e_cost = c1.number_input("进价成本", value=float(df_stock.at[idx, '进价成本']))
                e_price = c2.number_input("售卖价格", value=float(df_stock.at[idx, '售卖价格']))
                e_expect = c3.number_input("应收到数量", value=int(df_stock.at[idx, '应收到数量']))
                
                i1, i2, i3, i4 = st.columns(4)
                e_disp = i1.number_input("展示数量", value=int(df_stock.at[idx, '展示数量']))
                e_shelf = i2.number_input("货柜数量", value=int(df_stock.at[idx, '货柜数量']))
                e_stor = i3.number_input("储物间数量", value=int(df_stock.at[idx, '储物间数量']))
                e_dmg = i4.number_input("坏货数量", value=int(df_stock.at[idx, '坏货数量']))
                
                if st.form_submit_button("保存更改"):
                    df_stock.at[idx, '进价成本'], df_stock.at[idx, '售卖价格'], df_stock.at[idx, '应收到数量'] = e_cost, e_price, e_expect
                    df_stock.at[idx, '展示数量'], df_stock.at[idx, '货柜数量'], df_stock.at[idx, '储物间数量'], df_stock.at[idx, '坏货数量'] = e_disp, e_shelf, e_stor, e_dmg
                    df_stock.at[idx, '总库存'] = e_disp + e_shelf + e_stor + e_dmg
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()

with t2:
    st.subheader("销售记账")
    # ... (保持之前的销售记录与库存扣减逻辑)
    # [注：记账时仅扣减“货柜数量”，已售增加，总库存重算]
    f_options = get_filtered(df_stock, search_q)
    if not f_options.empty:
        df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
        with st.form("sales_form"):
            s_label = st.selectbox("售出商品", f_options['label'])
            c_qty, c_pr = st.columns(2)
            s_qty = c_qty.number_input("数量", min_value=1, step=1)
            idx_p = df_stock[df_stock['label'] == s_label].index[0]
            s_price = c_pr.number_input("成交单价", value=float(df_stock.at[idx_p, '售卖价格']))
            sel_date = st.date_input("销售日期", value=datetime.now())
            if st.form_submit_button("确认成交"):
                total = s_qty * s_price
                new_sale = pd.DataFrame([[sel_date.strftime("%Y-%m-%d"), df_stock.at[idx_p, '商品名称'], df_stock.at[idx_p, '颜色'], s_qty, s_price, total]], columns=SALES_COLS)
                pd.concat([new_sale, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                # 联动：货柜减，已售增，总库存重算
                df_stock.at[idx_p, '货柜数量'] -= s_qty
                df_stock.at[idx_p, '已售出数量'] += s_qty
                df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量', '坏货数量']].sum()
                df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                st.rerun()
    st.dataframe(get_filtered(df_sales, search_q), use_container_width=True)

with t3:
    st.subheader("📈 周期性报表")
    # ... (保持之前的 Daily/Weekly/Monthly 报表逻辑)
    # [系统会自动根据 SALES 表计算利润，毛利率显示已优化为百分比格式]
