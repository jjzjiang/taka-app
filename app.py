import streamlit as st
import pandas as pd
import os
from datetime import datetime

# 页面基础配置
st.set_page_config(page_title="高岛屋库存管理", layout="wide")
DATA_FILE = "stock_data.csv"

# 初始化数据
if not os.path.exists(DATA_FILE):
    initial_data = {
        '商品ID': ['TK01', 'TK02', 'TK03'],
        '商品名称': ['TAIC钛杯-经典款', 'BlackInTi-商务款', '示例商品'],
        '当前库存': [50, 30, 20],
        '安全水位': [10, 5, 5]
    }
    pd.DataFrame(initial_data).to_csv(DATA_FILE, index=False)

df = pd.read_csv(DATA_FILE)

# 侧边栏
st.sidebar.header("库存操作")
with st.sidebar.form("my_form"):
    target = st.selectbox("选择商品", df['商品名称'])
    op = st.radio("类型", ["销售出库", "补货入库"])
    num = st.number_input("数量", min_value=1, value=1)
    if st.form_submit_button("提交"):
        idx = df[df['商品名称'] == target].index[0]
        df.at[idx, '当前库存'] += num if op == "补货入库" else -num
        df.to_csv(DATA_FILE, index=False)
        st.success("更新成功！")
        st.rerun()

# 主界面
st.title("🏙️ Takashimaya 每日库存管理")
st.dataframe(df, use_container_width=True)

# 导出
st.download_button("下载报表", df.to_csv(index=False).encode('utf-8'), "report.csv")
