import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. 配置与文件初始化 ---
st.set_page_config(page_title="Taka 零售专业管理系统", layout="wide")
# 维持 v4 版本号以确保字段兼容性
STOCK_FILE = "taka_stock_final_v4.csv" 
SALES_FILE = "taka_sales_final_v4.csv"

# 核心字段定义
STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '应收到数量', '展示数量', '货柜数量', '储物间数量', '已售出数量', '总库存']
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

# --- 2. 侧边栏：核心管理与数据中心 ---
with st.sidebar:
    st.header("🛠️ 核心管理")
    
    # 功能 A: 新增 SKU (包含初始库存和应收数量)
    with st.expander("➕ 新增产品 (Add SKU)", expanded=False):
        with st.form("new_sku_form"):
            n_name = st.text_input("产品名称")
            n_color = st.text_input("颜色")
            c1, c2, c3 = st.columns(3)
            n_cost = c1.number_input("进价 (SGD)", min_value=0.0)
            n_price = c2.number_input("售价 (SGD)", min_value=0.0)
            n_expect = c3.number_input("应收到数量", min_value=0)
            i1, i2, i3 = st.columns(3)
            n_disp = i1.number_input("展示数量", min_value=0)
            n_shelf = i2.number_input("货柜数量", min_value=0)
            n_stor = i3.number_input("储物间数量", min_value=0)
            if st.form_submit_button("确认录入新商品"):
                if n_name and n_color:
                    new_row = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, 0, n_disp+n_shelf+n_stor]], columns=STOCK_COLS)
                    pd.concat([df_stock, new_row], ignore_index=True).to_csv(STOCK_FILE, index=False)
                    st.rerun()

    st.divider()
    
    # 功能 B: 数据备份与恢复 (已全部找回！)
    st.write("### 💾 数据中心")
    st.download_button("📥 下载库存备份", df_stock.to_csv(index=False).encode('utf-8-sig'), f"stock_{datetime.now().strftime('%m%d')}.csv", "text/csv")
    st.download_button("📥 下载销售备份", df_sales.to_csv(index=False).encode('utf-8-sig'), f"sales_{datetime.now().strftime('%m%d')}.csv", "text/csv")
    
    with st.expander("📂 上传 CSV 恢复数据"):
        st.warning("上传将覆盖当前云端/网页数据，请确认文件格式正确。")
        up_stock = st.file_uploader("恢复库存表", type="csv")
        if up_stock and st.button("确认覆盖库存"):
            pd.read_csv(up_stock).to_csv(STOCK_FILE, index=False)
            st.success("库存已恢复")
            st.rerun()
            
        up_sales = st.file_uploader("恢复销售流水", type="csv")
        if up_sales and st.button("确认覆盖销售"):
            pd.read_csv(up_sales).to_csv(SALES_FILE, index=False)
            st.success("流水已恢复")
            st.rerun()

# --- 3. 全局搜索过滤 ---
st.write("### 🔍 SKU 快速筛选")
search_q = st.text_input("输入产品名或颜色（会同步联动下拉菜单和报表）", placeholder="例如：钛杯...")

def get_filtered(df, q):
    if q and not df.empty:
        return df[df['商品名称'].str.contains(q, case=False, na=False) | df['颜色'].str.contains(q, case=False, na=False)]
    return df

# --- 4. 主界面布局 ---
st.title("🏙️ Takashimaya 零售管理系统")
t1, t2, t3 = st.tabs(["📊 库存看板", "💰 销售记账与撤销", "📈 周期利润报表"])

with t1:
    f_stock = get_filtered(df_stock, search_q)
    st.subheader("当前柜台分布")
    view_df = f_stock.copy()
    view_df['单件利润'] = view_df['售卖价格'] - view_df['进价成本']
    view_df['毛利率'] = ((view_df['单件利润'] / view_df['售卖价格']) * 100).fillna(0).map("{:.1f}%".format)
    # 调整列显示顺序
    show_cols = ['商品名称', '颜色', '售卖价格', '毛利率', '应收到数量', '已售出数量', '展示数量', '货柜数量', '储物间数量', '总库存']
    st.dataframe(view_df[show_cols], use_container_width=True)
    
    # 底部校准模块
    if not df_stock.empty:
        st.divider()
        st.write("### ⚙️ 单项信息修正")
        df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
        target = st.selectbox("选择商品", df_stock['label'], key="t1_edit")
        idx = df_stock[df_stock['label'] == target].index[0]
        with st.expander("修改详细参数"):
            with st.form("edit_form"):
                c1, c2, c3 = st.columns(3)
                e_cost = c1.number_input("进价成本", value=float(df_stock.at[idx, '进价成本']))
                e_price = c2.number_input("售卖价格", value=float(df_stock.at[idx, '售卖价格']))
                e_expect = c3.number_input("应收到数量", value=int(df_stock.at[idx, '应收到数量']))
                i1, i2, i3 = st.columns(3)
                e_disp = i1.number_input("展示数量", value=int(df_stock.at[idx, '展示数量']))
                e_shelf = i2.number_input("货柜数量", value=int(df_stock.at[idx, '货柜数量']))
                e_stor = i3.number_input("储物间数量", value=int(df_stock.at[idx, '储物间数量']))
                if st.form_submit_button("保存更改"):
                    df_stock.at[idx, '进价成本'], df_stock.at[idx, '售卖价格'], df_stock.at[idx, '应收到数量'] = e_cost, e_price, e_expect
                    df_stock.at[idx, '展示数量'], df_stock.at[idx, '货柜数量'], df_stock.at[idx, '储物间数量'] = e_disp, e_shelf, e_stor
                    df_stock.at[idx, '总库存'] = e_disp + e_shelf + e_stor
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()

with t2:
    st.subheader("销售记录管理")
    col_l, col_r = st.columns(2)
    with col_l:
        st.write("### 1. 新增记账")
        f_options = get_filtered(df_stock, search_q)
        if f_options.empty: st.info("请先添加 SKU")
        else:
            df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
            with st.form("sales_form"):
                s_label = st.selectbox("售出商品", f_options['label'])
                c_qty, c_pr = st.columns(2)
                s_qty = c_qty.number_input("数量", min_value=1, step=1)
                idx_p = df_stock[df_stock['label'] == s_label].index[0]
                s_price = c_pr.number_input("单价", value=float(df_stock.at[idx_p, '售卖价格']))
                sel_date = st.date_input("销售日期", value=datetime.now())
                if st.form_submit_button("确认提交"):
                    total = s_qty * s_price
                    new_sale = pd.DataFrame([[sel_date.strftime("%Y-%m-%d"), df_stock.at[idx_p, '商品名称'], df_stock.at[idx_p, '颜色'], s_qty, s_price, total]], columns=SALES_COLS)
                    pd.concat([new_sale, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                    # 自动联动库存和已售数量
                    df_stock.at[idx_p, '货柜数量'] -= s_qty
                    df_stock.at[idx_p, '已售出数量'] += s_qty
                    df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量']].sum()
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()
    with col_r:
        st.write("### 2. 撤销记录")
        if not df_sales.empty:
            df_sales['cancel_l'] = df_sales['日期'] + " | " + df_sales['商品名称'] + " (" + df_sales['销售数量'].astype(str) + "件)"
            del_idx = st.selectbox("选择撤销项", range(len(df_sales)), format_func=lambda x: df_sales.iloc[x]['cancel_l'])
            if st.button("确认撤销并退还库存"):
                sale_to_del = df_sales.iloc[del_idx]
                match = df_stock[(df_stock['商品名称'] == sale_to_del['商品名称']) & (df_stock['颜色'] == sale_to_del['颜色'])].index
                if not match.empty:
                    df_stock.at[match[0], '货柜数量'] += sale_to_del['销售数量']
                    df_stock.at[match[0], '已售出数量'] -= sale_to_del['销售数量']
                    df_stock.at[match[0], '总库存'] = df_stock.iloc[match[0]][['展示数量', '货柜数量', '储物间数量']].sum()
                    df_stock.to_csv(STOCK_FILE, index=False)
                df_sales.drop(df_sales.index[del_idx]).drop(columns=['cancel_l']).to_csv(SALES_FILE, index=False)
                st.rerun()
    st.dataframe(get_filtered(df_sales, search_q), use_container_width=True)

with t3:
    st.subheader("📊 财务周期报表")
    if df_sales.empty: st.info("暂无数据")
    else:
        report_type = st.radio("选择维度", ["Daily", "Weekly", "Monthly"], horizontal=True)
        report_df = df_sales.copy()
        report_df['日期'] = pd.to_datetime(report_df['日期'])
        if "Daily" in report_type: report_df['周期'] = report_df['日期'].dt.strftime('%Y-%m-%d')
        elif "Weekly" in report_type: report_df['周期'] = report_df['日期'].dt.to_period('W').apply(lambda r: r.start_time.strftime('%Y-%m-%d'))
        else: report_df['周期'] = report_df['日期'].dt.strftime('%Y-%m')
        
        summary = report_df.groupby(['周期', '商品名称', '颜色']).agg({'销售数量':'sum','总营业额':'sum'}).reset_index()
        summary = summary.merge(df_stock[['商品名称', '颜色', '进价成本']], on=['商品名称', '颜色'], how='left')
        summary['总成本'] = summary['销售数量'] * summary['进价成本']
        summary['总利润'] = summary['总营业额'] - summary['总成本']
        summary['毛利率 (%)'] = ((summary['总利润'] / summary['总营业额']) * 100).fillna(0)
        
        f_summary = get_filtered(summary, search_q)
        c1, c2, c3 = st.columns(3)
        c1.metric("总营业额", f"${f_summary['总营业额'].sum():.2f}")
        c2.metric("总利润", f"${f_summary['总利润'].sum():.2f}")
        c3.metric("平均毛利率", f"{(f_summary['毛利率 (%)'].mean() if not f_summary.empty else 0):.1f}%")
        st.dataframe(f_summary.style.format({'总营业额':"${:.2f}",'总利润':"${:.2f}",'毛利率 (%)':"{:.1f}%"}), use_container_width=True)
