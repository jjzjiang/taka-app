import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. 配置与文件初始化 ---
st.set_page_config(page_title="Taka 进销存-全功能版", layout="wide")
STOCK_FILE = "taka_stock_final.csv" 
SALES_FILE = "taka_sales_final.csv"

# 定义统一的表头
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
    
    # 功能 A: 新增 SKU (已加回！)
    with st.expander("➕ 新增产品 (Add SKU)", expanded=True):
        with st.form("new_sku_form"):
            n_name = st.text_input("产品名称")
            n_color = st.text_input("颜色")
            c1, c2 = st.columns(2)
            n_cost = c1.number_input("进价 (SGD)", min_value=0.0)
            n_price = c2.number_input("售价 (SGD)", min_value=0.0)
            if st.form_submit_button("确认录入"):
                if n_name and n_color:
                    new_row = pd.DataFrame([[n_name, n_color, n_cost, n_price, 0, 0, 0, 0]], columns=STOCK_COLS)
                    pd.concat([df_stock, new_row], ignore_index=True).to_csv(STOCK_FILE, index=False)
                    st.success(f"已录入: {n_name}")
                    st.rerun()
                else:
                    st.error("请完整填写名称和颜色")

    st.divider()

    # 功能 B: 数据备份与恢复
    st.write("### 💾 数据备份中心")
    st.download_button(
        label="📥 下载库存表备份",
        data=df_stock.to_csv(index=False).encode('utf-8-sig'),
        file_name=f"stock_backup_{datetime.now().strftime('%m%d')}.csv",
        mime="text/csv"
    )
    st.download_button(
        label="📥 下载销售流水备份",
        data=df_sales.to_csv(index=False).encode('utf-8-sig'),
        file_name=f"sales_backup_{datetime.now().strftime('%m%d')}.csv",
        mime="text/csv"
    )
    
    with st.expander("📂 上传旧数据恢复"):
        up_stock = st.file_uploader("上传库存 CSV", type="csv")
        if up_stock and st.button("覆盖当前库存"):
            pd.read_csv(up_stock).to_csv(STOCK_FILE, index=False)
            st.rerun()
        up_sales = st.file_uploader("上传销售 CSV", type="csv")
        if up_sales and st.button("覆盖当前销售"):
            pd.read_csv(up_sales).to_csv(SALES_FILE, index=False)
            st.rerun()

# --- 3. 全局搜索过滤 ---
st.write("### 🔍 SKU 快速筛选")
search_q = st.text_input("输入关键词查找商品（会同步联动下拉菜单）", placeholder="例如：钛杯...")

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
    view_df = f_stock.copy()
    view_df['单件利润'] = view_df['售卖价格'] - view_df['进价成本']
    view_df['毛利率'] = ((view_df['单件利润'] / view_df['售卖价格']) * 100).fillna(0).map("{:.1f}%".format)
    st.dataframe(view_df[['商品名称', '颜色', '售卖价格', '毛利率', '展示数量', '货柜数量', '储物间数量', '总库存']], use_container_width=True)
    
    st.divider()
    st.write("### ⚙️ SKU 信息修正与删除")
    if not df_stock.empty:
        df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
        col_edit, col_del = st.columns([2, 1])
        with col_edit:
            with st.expander("✏️ 修改基础信息 (名称/价格)"):
                target = st.selectbox("选择要修改的产品", df_stock['label'], key="edit_s")
                idx = df_stock[df_stock['label'] == target].index[0]
                with st.form("edit_form"):
                    e_name = st.text_input("新名称", value=df_stock.at[idx, '商品名称'])
                    e_color = st.text_input("新颜色", value=df_stock.at[idx, '颜色'])
                    c1, c2 = st.columns(2)
                    e_cost = c1.number_input("新进价", value=float(df_stock.at[idx, '进价成本']))
                    e_price = c2.number_input("新售价", value=float(df_stock.at[idx, '售卖价格']))
                    if st.form_submit_button("保存更改"):
                        df_stock.at[idx, '商品名称'], df_stock.at[idx, '颜色'] = e_name, e_color
                        df_stock.at[idx, '进价成本'], df_stock.at[idx, '售卖价格'] = e_cost, e_price
                        df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                        st.rerun()

with t2:
    st.subheader("销售流水管理")
    col_l, col_r = st.columns(2)
    with col_l:
        st.write("### 1. 记账 (Sales Entry)")
        f_options = get_filtered(df_stock, search_q)
        if f_options.empty: st.warning("请清空搜索框再选品")
        else:
            with st.form("sales_form"):
                s_label = st.selectbox("售出商品", f_options['label'])
                c1, c2 = st.columns(2)
                s_qty = c1.number_input("数量", min_value=1, step=1)
                idx_p = df_stock[df_stock['label'] == s_label].index[0]
                s_price = c2.number_input("单价", value=float(df_stock.at[idx_p, '售卖价格']))
                sel_date = st.date_input("销售日期", value=datetime.now())
                if st.form_submit_button("确认提交记录"):
                    total = s_qty * s_price
                    new_sale = pd.DataFrame([[sel_date.strftime("%Y-%m-%d"), df_stock.at[idx_p, '商品名称'], df_stock.at[idx_p, '颜色'], s_qty, s_price, total]], columns=SALES_COLS)
                    pd.concat([new_sale, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                    df_stock.at[idx_p, '货柜数量'] -= s_qty
                    df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量']].sum()
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()
    with col_r:
        st.write("### 2. 撤销记录")
        if not df_sales.empty:
            df_sales['cancel_l'] = df_sales['日期'] + " | " + df_sales['商品名称']
            del_idx = st.selectbox("选择撤销项", range(len(df_sales)), format_func=lambda x: df_sales.iloc[x]['cancel_l'])
            if st.button("确认撤销并退还库存"):
                sale_to_del = df_sales.iloc[del_idx]
                match = df_stock[(df_stock['商品名称'] == sale_to_del['商品名称']) & (df_stock['颜色'] == sale_to_del['颜色'])].index
                if not match.empty:
                    df_stock.at[match[0], '货柜数量'] += sale_to_del['销售数量']
                    df_stock.at[match[0], '总库存'] = df_stock.iloc[match[0]][['展示数量', '货柜数量', '储物间数量']].sum()
                    df_stock.to_csv(STOCK_FILE, index=False)
                df_sales.drop(df_sales.index[del_idx]).drop(columns=['cancel_l']).to_csv(SALES_FILE, index=False)
                st.rerun()

with t3:
    st.subheader("💰 财务与利润分析")
    analysis = get_filtered(df_stock, search_q).copy()
    if not analysis.empty:
        analysis['单件利润'] = analysis['售卖价格'] - analysis['进价成本']
        analysis['毛利率 (%)'] = ((analysis['单件利润'] / analysis['售卖价格']) * 100).fillna(0)
        
        # 计算累计数据
        if not df_sales.empty:
            summary = df_sales.groupby(['商品名称', '颜色'])['销售数量'].sum().reset_index()
            analysis = analysis.merge(summary, on=['商品名称', '颜色'], how='left').fillna(0)
            analysis['累计利润'] = analysis['销售数量'] * analysis['单件利润']
        else:
            analysis['销售数量'], analysis['累计利润'] = 0, 0

        m1, m2, m3 = st.columns(3)
        m1.metric("筛选总销售额", f"${(analysis['售卖价格']*analysis['销售数量']).sum():.2f}")
        m2.metric("筛选累计利润", f"${analysis['累计利润'].sum():.2f}")
        m3.metric("平均毛利率", f"{analysis['毛利率 (%)'].mean():.1f}%")
        
        st.dataframe(analysis[['商品名称', '颜色', '进价成本', '售卖价格', '单件利润', '毛利率 (%)', '累计利润']], use_container_width=True)
