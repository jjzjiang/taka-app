{\rtf1\ansi\ansicpg936\cocoartf2818
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 import streamlit as st\
import pandas as pd\
import os\
from datetime import datetime\
\
# --- 1. \uc0\u22522 \u30784 \u37197 \u32622  ---\
st.set_page_config(page_title="\uc0\u39640 \u23707 \u23627 \u24211 \u23384 \u31649 \u29702 ", layout="wide")\
DATA_FILE = "stock_data.csv"  # \uc0\u25968 \u25454 \u24211 \u25991 \u20214 \
\
# --- 2. \uc0\u21021 \u22987 \u21270 \u25968 \u25454 \u36923 \u36753  ---\
# \uc0\u22914 \u26524 \u25991 \u20214 \u19981 \u23384 \u22312 \u65292 \u21019 \u24314 \u19968 \u20010 \u21021 \u22987 \u34920 \u26684 \
if not os.path.exists(DATA_FILE):\
    initial_data = \{\
        '\uc0\u21830 \u21697 ID': ['A01', 'A02', 'A03'],\
        '\uc0\u21830 \u21697 \u21517 \u31216 ': ['\u21270 \u22918 \u21697 A', '\u21517 \u29260 \u21253 B', '\u23567 \u23478 \u30005 C'],\
        '\uc0\u24403 \u21069 \u24211 \u23384 ': [100, 20, 15],\
        '\uc0\u23433 \u20840 \u24211 \u23384 ': [10, 5, 5]\
    \}\
    pd.DataFrame(initial_data).to_csv(DATA_FILE, index=False)\
\
# \uc0\u35835 \u21462 \u26368 \u26032 \u25968 \u25454 \
df = pd.read_csv(DATA_FILE)\
\
# --- 3. \uc0\u20391 \u36793 \u26639 \u65306 \u25805 \u20316 \u36755 \u20837 \u21306  ---\
st.sidebar.header("\uc0\u24211 \u23384 \u25805 \u20316 \u38754 \u26495 ")\
\
with st.sidebar.form("input_form"):\
    target_name = st.selectbox("\uc0\u36873 \u25321 \u21830 \u21697 ", df['\u21830 \u21697 \u21517 \u31216 '])\
    op_type = st.radio("\uc0\u25805 \u20316 \u31867 \u22411 ", ["\u38144 \u21806 \u20986 \u24211 ", "\u34917 \u36135 \u20837 \u24211 "])\
    quantity = st.number_input("\uc0\u25968 \u37327 ", min_value=1, value=1)\
    \
    submit_btn = st.form_submit_button("\uc0\u25552 \u20132 \u26356 \u26032 ")\
\
if submit_btn:\
    # \uc0\u25214 \u21040 \u36873 \u20013 \u21830 \u21697 \u22312 \u34920 \u26684 \u20013 \u30340 \u20301 \u32622 \
    row_index = df[df['\uc0\u21830 \u21697 \u21517 \u31216 '] == target_name].index[0]\
    \
    # \uc0\u26681 \u25454 \u25805 \u20316 \u31867 \u22411 \u22686 \u20943 \u24211 \u23384 \
    if op_type == "\uc0\u38144 \u21806 \u20986 \u24211 ":\
        df.at[row_index, '\uc0\u24403 \u21069 \u24211 \u23384 '] -= quantity\
    else:\
        df.at[row_index, '\uc0\u24403 \u21069 \u24211 \u23384 '] += quantity\
    \
    # \uc0\u20445 \u23384 \u21040 \u25991 \u20214 \u24182 \u21047 \u26032 \
    df.to_csv(DATA_FILE, index=False)\
    st.sidebar.success(f"\uc0\u26356 \u26032 \u25104 \u21151 \u65306 \{target_name\} \u25968 \u37327 \u24050 \u21464 \u21160 \u12290 ")\
    st.rerun()\
\
# --- 4. \uc0\u20027 \u30028 \u38754 \u65306 \u25968 \u25454 \u26174 \u31034 \u21306  ---\
st.title("\uc0\u39640 \u23707 \u23627  (Takashimaya) \u27599 \u26085 \u24211 \u23384 \u28165 \u21333 ")\
\
# \uc0\u35686 \u25253 \u25552 \u31034 \u65306 \u22914 \u26524 \u24403 \u21069 \u24211 \u23384  <= \u23433 \u20840 \u24211 \u23384 \u65292 \u23601 \u26174 \u31034 \u35686 \u21578 \
low_stock_items = df[df['\uc0\u24403 \u21069 \u24211 \u23384 '] <= df['\u23433 \u20840 \u24211 \u23384 ']]\
if not low_stock_items.empty:\
    st.warning(f"\uc0\u27880 \u24847 \u65306 \u20197 \u19979 \u21830 \u21697 \u24211 \u23384 \u19981 \u36275 \u65292 \u35831 \u21450 \u26102 \u34917 \u36135 \u65281 ")\
    st.write(low_stock_items[['\uc0\u21830 \u21697 \u21517 \u31216 ', '\u24403 \u21069 \u24211 \u23384 ']])\
\
st.divider() # \uc0\u20998 \u21106 \u32447 \
\
# \uc0\u26174 \u31034 \u23436 \u25972 \u24211 \u23384 \u34920 \u26684 \
st.subheader("\uc0\u23454 \u26102 \u24211 \u23384 \u27010 \u35272 ")\
st.dataframe(df, use_container_width=True)\
\
# \uc0\u23548 \u20986 \u25353 \u38062 \
csv_data = df.to_csv(index=False).encode('utf-8')\
st.download_button(\
    label="\uc0\u23548 \u20986 \u25968 \u25454 \u20026  Excel (CSV)",\
    data=csv_data,\
    file_name=f"Taka_Stock_\{datetime.now().strftime('%Y%m%d')\}.csv",\
    mime="text/csv"\
)}