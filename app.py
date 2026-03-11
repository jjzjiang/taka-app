import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import gspread 
import json

# --- 1. 配置与云端数据库初始化 ---
st.set_page_config(page_title="Taka 零售终极管理系统", layout="wide")

try:
    key_dict = json.loads(st.secrets["google_key"])
    gc = gspread.service_account_from_dict(key_dict)
    sh = gc.open_by_url(st.secrets["sheet_url"]) 
except Exception as e:
    st.error(f"🔴 连接云端数据库失败！详细错误: {e}")
    st.stop()

STOCK_SHEET = "Stock"
SALES_SHEET = "Sales"
EMP_SHEET = "Employee"
ATT_SHEET = "Attendance"

STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '应收到数量', '展示数量', '货柜数量', '储物间数量', '坏货数量', '已售出数量', '总库存']
SALES_COLS = ['日期', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']
EMP_COLS = ['员工姓名', '职位', '时薪', '联系方式', '入职日期']
ATT_COLS = ['员工姓名', '日期', '开始时间', '结束时间', '工作时长', '核算薪资']

@st.cache_data(ttl=300, show_spinner=False)
def load_raw_data(sheet_name):
    try:
        worksheet = sh.worksheet(sheet_name)
        records = worksheet.get_all_records()
        if not records:
            return pd.DataFrame()
        return pd.DataFrame(records)
    except Exception as e:
        return pd.DataFrame()

def load_data(sheet_name, columns):
    df = load_raw_data(sheet_name)
    if df.empty:
        df = pd.DataFrame(columns=columns)
    for col in columns:
        if col not in df.columns: df[col] = 0
    return df[columns]

def save_data(df, sheet_name):
    worksheet = sh.worksheet(sheet_name)
    worksheet.clear() 
    df_safe = df.fillna("").astype(str)
    data_to_upload = [df_safe.columns.values.tolist()] + df_safe.values.tolist()
    worksheet.update(values=data_to_upload, range_name='A1')
    st.cache_data.clear()

def clean_date_col(df, col_name):
    if not df.empty and col_name in df.columns:
        formatted = pd.to_datetime(df[col_name], errors='coerce').dt.strftime('%Y/%m/%d')
        df[col_name] = formatted.fillna(df[col_name])
    return df

df_stock = load_data(STOCK_SHEET, STOCK_COLS)
df_sales = clean_date_col(load_data(SALES_SHEET, SALES_COLS), '日期') 
df_employee = clean_date_col(load_data(EMP_SHEET, EMP_COLS), '入职日期') 
df_attendance = clean_date_col(load_data(ATT_SHEET, ATT_COLS), '日期') 

if "stock_reset_key" not in st.session_state: st.session_state.stock_reset_key = 0
if "sales_reset_key" not in st.session_state: st.session_state.sales_reset_key = 0
if "emp_reset_key" not in st.session_state: st.session_state.emp_reset_key = 0
if "att_reset_key" not in st.session_state: st.session_state.att_reset_key = 0 

def clear_stock(): st.session_state.stock_reset_key += 1
def clear_sales(): st.session_state.sales_reset_key += 1
def clear_emp(): st.session_state.emp_reset_key += 1
def clear_att(): st.session_state.att_reset_key += 1

# --- 2. 侧边栏：核心管理 ---
with st.sidebar:
    st.header("🛠️ 核心管理")
    with st.expander("➕ 新增产品 (Add SKU)"):
        with st.form("new_sku"):
            n_name = st.text_input("产品名称")
            n_color = st.text_input("颜色")
            c1, c2, c3 = st.columns(3)
            n_cost, n_price, n_expect = c1.number_input("进价", format="%.2f"), c2.number_input("售价", format="%.2f"), c3.number_input("应收")
            i1, i2, i3, i4 = st.columns(4)
            n_disp, n_shelf, n_stor, n_dmg = i1.number_input("展示"), i2.number_input("货柜"), i3.number_input("储物"), i4.number_input("坏货")
            if st.form_submit_button("确认录入"):
                if n_name and n_color:
                    total = n_disp + n_shelf + n_stor 
                    new_r = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, n_dmg, 0, total]], columns=STOCK_COLS)
                    df_stock = pd.concat([df_stock, new_r], ignore_index=True)
                    save_data(df_stock, STOCK_SHEET) 
                    st.success("✅ 云端录入成功！")
                    st.rerun()

    st.divider()
    st.write("### ☁️ 云端数据中心")
    st.info("💡 数据实时同步至 Google Sheets。")

# --- 3. 辅助功能 ---
q = st.text_input("🔍 快速筛选 (SKU / 颜色 / 员工姓名)...", placeholder="搜索将同步联动所有标签页")

def get_f(df, q):
    if q and not df.empty:
        if '商品名称' in df.columns and '颜色' in df.columns:
            return df[df['商品名称'].astype(str).str.contains(q, case=False, na=False) | df['颜色'].astype(str).str.contains(q, case=False, na=False)]
        elif '员工姓名' in df.columns:
            return df[df['员工姓名'].astype(str).str.contains(q, case=False, na=False)]
    return df

# --- 4. 主界面布局 (新增 Tab 5) ---
st.title("🏙️ Takashimaya 零售管理系统 (云端同步版)")
t1, t2, t3, t4, t5 = st.tabs(["📊 库存看板", "💰 销售记账", "📈 财务(毛利)分析", "👥 员工与考勤", "💎 真实净利润核算"])

with t1:
    st.subheader("库存实物分布 (低库存自动标红预警)")
    f_stock = get_f(df_stock, q)
    if not f_stock.empty:
        v_df = f_stock.copy()
        
        int_cols = ['应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量']
        for col in int_cols: 
            v_df[col] = pd.to_numeric(v_df[col], errors='coerce').fillna(0).astype(int)
            
        v_df['进价成本'] = pd.to_numeric(v_df['进价成本'], errors='coerce').fillna(0.0)
        v_df['售卖价格'] = pd.to_numeric(v_df['售卖价格'], errors='coerce').fillna(0.0)
        
        def calc_margin(row):
            price = row['售卖价格']
            cost = row['进价成本']
            if price > 0:
                return f"{((price - cost) / price * 100):.1f}%"
            return "0.0%"
            
        v_df['单品毛利率'] = v_df.apply(calc_margin, axis=1)
        v_df.insert(0, "选择", False)
        
        display_cols = ['选择', '商品名称', '颜色', '应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '售卖价格', '进价成本', '单品毛利率']
        display_df = v_df[display_cols]

        def highlight_low_stock(row):
            try:
                stock_val = int(row['总库存'])
                if stock_val <= 2:
                    return ['background-color: #ffe6e6; color: #cc0000; font-weight: bold;'] * len(row)
            except:
                pass
            return [''] * len(row)

        styled_df = display_df.style.format({'进价成本': '${:.2f}', '售卖价格': '${:.2f}'}).apply(highlight_low_stock, axis=1)
        
        edited_stock = st.data_editor(
            styled_df,
            column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)},
            disabled=[col for col in display_cols if col != "选择"],
            use_container_width=True, hide_index=True, 
            key=f"stock_editor_{st.session_state.stock_reset_key}" 
        )
        
        selected_stock = edited_stock[edited_stock["选择"] == True]
        
        if not selected_stock.empty:
            col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 4])
            with col_btn1:
                if st.button("🗑️ 批量删除选中", type="primary", key="del_stock"):
                    for _, row in selected_stock.iterrows():
                        df_stock = df_stock[~((df_stock['商品名称'] == row['商品名称']) & (df_stock['颜色'] == row['颜色']))]
                    save_data(df_stock, STOCK_SHEET) 
                    st.session_state.stock_reset_key += 1 
                    st.rerun()
            with col_btn2: st.button("🔄 取消所有选中", key="btn_cancel_stock", on_click=clear_stock)
            
            if len(selected_stock) == 1:
                st.write("### ⚙️ 编辑选中商品信息")
                row = selected_stock.iloc[0]
                orig_idx = df_stock[(df_stock['商品名称'] == row['商品名称']) & (df_stock['颜色'] == row['颜色'])].index[0]
                with st.form("edit_selected_stock"):
                    e_name = st.text_input("产品名称", value=str(df_stock.at[orig_idx, '商品名称']))
                    c1, c2, c3 = st.columns(3)
                    e_cost = c1.number_input("进价", value=float(pd.to_numeric(df_stock.at[orig_idx, '进价成本'], errors='coerce') or 0), format="%.2f")
                    e_price = c2.number_input("售价", value=float(pd.to_numeric(df_stock.at[orig_idx, '售卖价格'], errors='coerce') or 0), format="%.2f")
                    e_sold = c3.number_input("已售修正", value=int(pd.to_numeric(df_stock.at[orig_idx, '已售出数量'], errors='coerce') or 0))
                    
                    i1, i2, i3, i4, i5 = st.columns(5)
                    e_exp = i1.number_input("应收", value=int(pd.to_numeric(df_stock.at[orig_idx, '应收到数量'], errors='coerce') or 0))
                    e_dis = i2.number_input("展示", value=int(pd.to_numeric(df_stock.at[orig_idx, '展示数量'], errors='coerce') or 0))
                    e_sh = i3.number_input("货柜", value=int(pd.to_numeric(df_stock.at[orig_idx, '货柜数量'], errors='coerce') or 0))
                    e_st = i4.number_input("储物", value=int(pd.to_numeric(df_stock.at[orig_idx, '储物间数量'], errors='coerce') or 0))
                    e_dm = i5.number_input("坏货", value=int(pd.to_numeric(df_stock.at[orig_idx, '坏货数量'], errors='coerce') or 0))
                    
                    if st.form_submit_button("保存校准"):
                        df_stock.at[orig_idx, '商品名称'] = e_name
                        df_stock.at[orig_idx, '进价成本'], df_stock.at[orig_idx, '售卖价格'], df_stock.at[orig_idx, '已售出数量'] = e_cost, e_price, e_sold
                        df_stock.at[orig_idx, '应收到数量'], df_stock.at[orig_idx, '展示数量'], df_stock.at[orig_idx, '货柜数量'], df_stock.at[orig_idx, '储物间数量'], df_stock.at[orig_idx, '坏货数量'] = e_exp, e_dis, e_sh, e_st, e_dm
                        df_stock.at[orig_idx, '总库存'] = e_dis + e_sh + e_st 
                        save_data(df_stock, STOCK_SHEET) 
                        st.session_state.stock_reset_key += 1 
                        st.rerun()

with t2:
    st.subheader("销售记账与流水管理")
    with st.expander("➕ 新增销售", expanded=True):
        f_opts = get_f(df_stock, q).copy() 
        if not f_opts.empty:
            f_opts['label'] = f_opts['商品名称'].astype(str) + " (" + f_opts['颜色'].astype(str) + ")" 
            with st.form("add_sale"):
                s_l = st.selectbox("商品", f_opts['label'])
                selected_row = f_opts[f_opts['label'] == s_l].iloc[0]
                default_price = float(pd.to_numeric(selected_row['售卖价格'], errors='coerce') or 0)
                c1, c2 = st.columns(2)
                s_q, s_p = c1.number_input("数量", 1), c2.number_input("单价", value=default_price, format="%.2f")
                s_d = st.date_input("日期", value=datetime.now())
                
                if st.form_submit_button("确认"):
                    idx_p = df_stock[(df_stock['商品名称'] == selected_row['商品名称']) & (df_stock['颜色'] == selected_row['颜色'])].index[0]
                    new_s = pd.DataFrame([[s_d.strftime("%Y/%m/%d"), df_stock.at[idx_p,'商品名称'], df_stock.at[idx_p,'颜色'], s_q, s_p, s_q*s_p]], columns=SALES_COLS)
                    df_sales = pd.concat([new_s, df_sales], ignore_index=True)
                    
                    df_stock.at[idx_p, '货柜数量'] = int(pd.to_numeric(df_stock.at[idx_p, '货柜数量'], errors='coerce') or 0) - s_q
                    df_stock.at[idx_p, '已售出数量'] = int(pd.to_numeric(df_stock.at[idx_p, '已售出数量'], errors='coerce') or 0) + s_q
                    df_stock.at[idx_p, '总库存'] = sum([int(pd.to_numeric(df_stock.at[idx_p, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                    
                    save_data(df_sales, SALES_SHEET) 
                    save_data(df_stock, STOCK_SHEET) 
                    st.rerun()

    st.divider()
    f_sl = get_f(df_sales, q)
    if not f_sl.empty:
        f_sl_sel = f_sl.copy(); f_sl_sel.insert(0, "选择", False)
        
        f_sl_sel['成交单价'] = pd.to_numeric(f_sl_sel['成交单价'], errors='coerce').fillna(0.0)
        f_sl_sel['总营业额'] = pd.to_numeric(f_sl_sel['总营业额'], errors='coerce').fillna(0.0)
        styled_sl = f_sl_sel.style.format({'成交单价': '${:.2f}', '总营业额': '${:.2f}'})
        
        edt = st.data_editor(styled_sl, column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, disabled=f_sl.columns, use_container_width=True, hide_index=True, key=f"sales_editor_{st.session_state.sales_reset_key}")
        sel = edt[edt["选择"] == True]
        
        if not sel.empty:
            sc1, sc2, _ = st.columns([1.5, 1.5, 4])
            with sc1:
                if st.button("🔴 批量撤销流水", type="primary"):
                    for _, r in sel.iterrows():
                        m = df_stock[(df_stock['商品名称']==r['商品名称']) & (df_stock['颜色']==r['颜色'])].index
                        if not m.empty:
                            df_stock.at[m[0], '货柜数量'] = int(pd.to_numeric(df_stock.at[m[0], '货柜数量'], errors='coerce') or 0) + int(pd.to_numeric(r['销售数量'], errors='coerce') or 0)
                            df_stock.at[m[0], '已售出数量'] = int(pd.to_numeric(df_stock.at[m[0], '已售出数量'], errors='coerce') or 0) - int(pd.to_numeric(r['销售数量'], errors='coerce') or 0)
                            df_stock.at[m[0], '总库存'] = sum([int(pd.to_numeric(df_stock.at[m[0], col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                    for _, r in sel.iterrows():
                        df_sales = df_sales[~((df_sales['日期']==r['日期']) & (df_sales['商品名称']==r['商品名称']) & (df_sales['颜色']==r['颜色']) & (df_sales['销售数量']==r['销售数量']))]
                    save_data(df_stock, STOCK_SHEET); save_data(df_sales, SALES_SHEET)
                    st.session_state.sales_reset_key += 1
                    st.rerun()
            with sc2: st.button("🔄 取消所有选中", key="btn_cancel_sales", on_click=clear_sales)

with t3:
    st.subheader("📊 财务报表 (仅含商品毛利)")
    if not df_sales.empty:
        df_sales['日期_dt'] = pd.to_datetime(df_sales['日期'], errors='coerce')
        df_sales_clean = df_sales.dropna(subset=['日期_dt']).copy()
        
        if not df_sales_clean.empty:
            sel_range = st.date_input("选择查看时间段", value=[df_sales_clean['日期_dt'].min().date(), df_sales_clean['日期_dt'].max().date()])
            if len(sel_range) == 2:
                start, end = sel_range
                f_sales_range = df_sales_clean[(df_sales_clean['日期_dt'] >= pd.Timestamp(start)) & (df_sales_clean['日期_dt'] <= pd.Timestamp(end))].copy()
                
                f_sales_range['销售数量'] = pd.to_numeric(f_sales_range['销售数量'], errors='coerce').fillna(0)
                f_sales_range['总营业额'] = pd.to_numeric(f_sales_range['总营业额'], errors='coerce').fillna(0.0)
                
                period = st.radio("维度", ["Daily", "Weekly", "Monthly"], horizontal=True)
                if "Daily" in period: f_sales_range['周期'] = f_sales_range['日期_dt'].dt.strftime('%Y/%m/%d')
                elif "Weekly" in period: f_sales_range['周期'] = (f_sales_range['日期_dt'] - pd.to_timedelta(f_sales_range['日期_dt'].dt.dayofweek, unit='D')).dt.strftime('Week of %b %d')
                else: f_sales_range['周期'] = f_sales_range['日期_dt'].dt.strftime('%Y/%m')
                
                summ = f_sales_range.groupby(['周期', '商品名称', '颜色']).agg({'销售数量':'sum', '总营业额':'sum'}).reset_index()
                
                df_stock_calc = df_stock[['商品名称', '颜色', '进价成本']].copy()
                df_stock_calc['进价成本'] = pd.to_numeric(df_stock_calc['进价成本'], errors='coerce').fillna(0.0)
                
                summ = summ.merge(df_stock_calc, on=['商品名称', '颜色'], how='left')
                summ['具体毛利'] = summ['总营业额'] - (summ['销售数量'] * summ['进价成本'])
                
                filtered_summ = get_f(summ, q) 
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("总营业额", f"${filtered_summ['总营业额'].sum():.2f}")
                c2.metric("具体毛利", f"${filtered_summ['具体毛利'].sum():.2f}")
                c3.metric("总售出件数", f"{int(filtered_summ['销售数量'].sum())} 件")
                avg_m = filtered_summ['具体毛利'].sum() / filtered_summ['总营业额'].sum() * 100 if filtered_summ['总营业额'].sum() > 0 else 0
                c4.metric("平均毛利率", f"{avg_m:.1f}%")
                
                st.dataframe(filtered_summ.sort_values('周期', ascending=False).style.format({'总营业额':"${:.2f}", '具体毛利':"${:.2f}", '销售数量':"{:d}"}), use_container_width=True)
        else:
            st.info("流水表中没有有效的日期数据。")

with t4:
    st.subheader("👥 员工档案管理")
    with st.expander("➕ 新增员工档案", expanded=False):
        with st.form("add_employee"):
            c1, c2 = st.columns(2)
            e_name = c1.text_input("员工姓名")
            e_role = c2.selectbox("职位", ["店长", "全职店员", "兼职店员", "实习生", "其他"])
            c3, c4, c5 = st.columns(3)
            e_wage = c3.number_input("时薪 ($/小时)", min_value=0.0, step=0.5, value=12.0, format="%.2f")
            e_phone = c4.text_input("联系方式 (选填)")
            e_date = c5.date_input("入职日期", value=datetime.now())
            if st.form_submit_button("保存员工信息"):
                if e_name.strip() == "": st.warning("⚠️ 员工姓名不能为空！")
                elif e_name in df_employee['员工姓名'].values: st.warning(f"⚠️ 员工 {e_name} 已经存在！")
                else:
                    new_emp = pd.DataFrame([[e_name, e_role, e_wage, e_phone, e_date.strftime("%Y/%m/%d")]], columns=EMP_COLS)
                    df_employee = pd.concat([df_employee, new_emp], ignore_index=True)
                    save_data(df_employee, EMP_SHEET) 
                    st.session_state.emp_reset_key += 1
                    st.rerun()

    f_employee = get_f(df_employee, q) 
    if not f_employee.empty:
        v_emp = f_employee.copy()
        v_emp.insert(0, "选择", False)
        
        v_emp['时薪'] = pd.to_numeric(v_emp['时薪'], errors='coerce').fillna(0.0)
        styled_emp = v_emp.style.format({'时薪': '${:.2f}'})
        
        edited_emp = st.data_editor(styled_emp, column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, disabled=f_employee.columns.tolist(), use_container_width=True, hide_index=True, key=f"emp_editor_{st.session_state.emp_reset_key}")
        selected_emp = edited_emp[edited_emp["选择"] == True]
        
        if not selected_emp.empty:
            col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 4])
            with col_btn1:
                if st.button("🗑️ 批量删除员工", type="primary", key="del_emp"):
                    for _, row in selected_emp.iterrows():
                        df_employee = df_employee[df_employee['员工姓名'] != row['员工姓名']]
                    save_data(df_employee, EMP_SHEET)
                    st.session_state.emp_reset_key += 1; st.rerun()
            with col_btn2: st.button("🔄 取消所有选中", key="btn_cancel_emp", on_click=clear_emp)
            
            if len(selected_emp) == 1:
                st.write("### ⚙️ 编辑员工信息")
                row = selected_emp.iloc[0]
                orig_idx = df_employee[df_employee['员工姓名'] == row['员工姓名']].index[0]
                with st.form("edit_selected_emp"):
                    c1, c2 = st.columns(2)
                    edit_name = c1.text_input("员工姓名", value=str(df_employee.at[orig_idx, '员工姓名']))
                    roles = ["店长", "全职店员", "兼职店员", "实习生", "其他"]
                    current_role = str(df_employee.at[orig_idx, '职位'])
                    edit_role = c2.selectbox("职位", roles, index=roles.index(current_role) if current_role in roles else 0)
                    c3, c4, c5 = st.columns(3)
                    
                    current_wage = pd.to_numeric(df_employee.at[orig_idx, '时薪'], errors='coerce')
                    if pd.isna(current_wage): current_wage = 0.0
                    
                    edit_wage = c3.number_input("时薪 ($/小时)", min_value=0.0, step=0.5, value=float(current_wage), format="%.2f")
                    current_phone = str(df_employee.at[orig_idx, '联系方式'])
                    edit_phone = c4.text_input("联系方式 (选填)", value="" if current_phone=="nan" else current_phone)
                    
                    try: parsed_date = pd.to_datetime(str(df_employee.at[orig_idx, '入职日期'])).date()
                    except: parsed_date = datetime.now().date()
                    edit_date = c5.date_input("入职日期", value=parsed_date)
                    
                    if st.form_submit_button("保存修改"):
                        if edit_name != row['员工姓名'] and edit_name in df_employee['员工姓名'].values: st.error(f"⚠️ 无法修改：员工 {edit_name} 已存在。")
                        else:
                            df_employee.at[orig_idx, '员工姓名'], df_employee.at[orig_idx, '职位'], df_employee.at[orig_idx, '时薪'] = edit_name, edit_role, edit_wage
                            df_employee.at[orig_idx, '联系方式'], df_employee.at[orig_idx, '入职日期'] = edit_phone, edit_date.strftime("%Y/%m/%d")
                            save_data(df_employee, EMP_SHEET)
                            st.session_state.emp_reset_key += 1; st.rerun()

    st.divider()
    st.subheader("⏰ 排班与打卡记录")
    
    if df_employee.empty:
        st.info("💡 请先在上方添加至少一名员工，才能开始记录考勤。")
    else:
        with st.expander("➕ 登记工作排班/打卡", expanded=True):
            with st.form("add_attendance"):
                c1, c2 = st.columns(2)
                att_name = c1.selectbox("选择员工", df_employee['员工姓名'].astype(str).tolist())
                att_date = c2.date_input("工作日期", value=datetime.now())
                
                c3, c4 = st.columns(2)
                att_start = c3.time_input("上班时间", value=time(10, 0))
                att_end = c4.time_input("下班时间", value=time(18, 0))
                
                if st.form_submit_button("确认记录考勤"):
                    dt_start = datetime.combine(att_date, att_start)
                    dt_end = datetime.combine(att_date, att_end)
                    if dt_end < dt_start: dt_end += timedelta(days=1)
                        
                    duration_hours = (dt_end - dt_start).total_seconds() / 3600.0
                    
                    wage_val = df_employee[df_employee['员工姓名'] == att_name]['时薪'].iloc[0]
                    hourly_wage = float(pd.to_numeric(wage_val, errors='coerce') or 0.0)
                    total_wage = duration_hours * hourly_wage
                    
                    new_att = pd.DataFrame([[
                        att_name, att_date.strftime("%Y/%m/%d"), 
                        att_start.strftime("%H:%M"), att_end.strftime("%H:%M"), 
                        round(duration_hours, 2), round(total_wage, 2)
                    ]], columns=ATT_COLS)
                    
                    df_attendance = pd.concat([new_att, df_attendance], ignore_index=True)
                    save_data(df_attendance, ATT_SHEET) 
                    
                    st.success(f"已记录 {att_name} 的工时: {round(duration_hours, 1)} 小时，核算薪资: ${round(total_wage, 2)}")
                    st.rerun()

        f_att = get_f(df_attendance, q)
        if not f_att.empty:
            v_att = f_att.copy()
            v_att.insert(0, "选择", False)
            
            v_att['核算薪资'] = pd.to_numeric(v_att['核算薪资'], errors='coerce').fillna(0.0)
            styled_att = v_att.style.format({'核算薪资': '${:.2f}'})
            
            edited_att = st.data_editor(
                styled_att, 
                column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, 
                disabled=f_att.columns.tolist(), 
                use_container_width=True, hide_index=True, 
                key=f"att_editor_{st.session_state.att_reset_key}"
            )
            selected_att = edited_att[edited_att["选择"] == True]
            
            if not selected_att.empty:
                col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 4])
                with col_btn1:
                    if st.button("🗑️ 删除选中打卡记录", type="primary", key="del_att"):
                        for _, row in selected_att.iterrows():
                            df_attendance = df_attendance[~((df_attendance['员工姓名'] == row['员工姓名']) & (df_attendance['日期'] == row['日期']) & (df_attendance['开始时间'] == row['开始时间']))]
                        save_data(df_attendance, ATT_SHEET)
                        st.session_state.att_reset_key += 1 
                        st.rerun()
                with col_btn2: st.button("🔄 取消所有选中", key="btn_cancel_att", on_click=clear_att)
            
            st.divider()
            total_hours = pd.to_numeric(f_att['工作时长'], errors='coerce').fillna(0).sum()
            total_wage = pd.to_numeric(f_att['核算薪资'], errors='coerce').fillna(0).sum()
            
            c_t1, c_t2, c_t3 = st.columns([2, 1, 1])
            c_t1.markdown(f"**🧾 列表总计** (共 {len(f_att)} 条记录)")
            c_t2.metric("当前列表总工时", f"{total_hours:.1f} 小时")
            c_t3.metric("当前列表总薪资支出", f"${total_wage:.2f}")

# 🚀 全新重磅功能：Tab 5 真实净利润核算中心
with t5:
    st.subheader("💎 真实净利润核算 (Net Profit)")
    st.info("💡 这里的【净利润】 = 总营业额 - 商品进价成本 - 员工打卡工资成本。")

    if not df_sales.empty:
        # 提取并清理销售数据日期
        df_s_np = df_sales.copy()
        df_s_np['日期_dt'] = pd.to_datetime(df_s_np['日期'], errors='coerce')
        df_s_np = df_s_np.dropna(subset=['日期_dt'])

        # 提取并清理考勤数据日期
        df_a_np = df_attendance.copy()
        if not df_a_np.empty:
            df_a_np['日期_dt'] = pd.to_datetime(df_a_np['日期'], errors='coerce')
            df_a_np = df_a_np.dropna(subset=['日期_dt'])
        else:
            df_a_np['日期_dt'] = pd.Series(dtype='datetime64[ns]')

        if not df_s_np.empty:
            # 找到业务发生的最早和最晚日期，设定日历选择器的默认范围
            min_date = df_s_np['日期_dt'].min().date()
            max_date = df_s_np['日期_dt'].max().date()
            if not df_a_np.empty:
                min_date = min(min_date, df_a_np['日期_dt'].min().date())
                max_date = max(max_date, df_a_np['日期_dt'].max().date())

            np_range = st.date_input("选择核算时间段", value=[min_date, max_date], key="np_date_range")

            if len(np_range) == 2:
                start_d, end_d = np_range
                
                # 按时间段过滤数据
                fs = df_s_np[(df_s_np['日期_dt'] >= pd.Timestamp(start_d)) & (df_s_np['日期_dt'] <= pd.Timestamp(end_d))].copy()
                fa = df_a_np[(df_a_np['日期_dt'] >= pd.Timestamp(start_d)) & (df_a_np['日期_dt'] <= pd.Timestamp(end_d))].copy()

                # --- 1. 计算销售端的营业额和成本 ---
                fs['销售数量'] = pd.to_numeric(fs['销售数量'], errors='coerce').fillna(0)
                fs['总营业额'] = pd.to_numeric(fs['总营业额'], errors='coerce').fillna(0.0)

                # 关联进价
                df_stock_cost = df_stock[['商品名称', '颜色', '进价成本']].copy()
                df_stock_cost['进价成本'] = pd.to_numeric(df_stock_cost['进价成本'], errors='coerce').fillna(0.0)
                fs = fs.merge(df_stock_cost, on=['商品名称', '颜色'], how='left')
                fs['总进价成本'] = fs['销售数量'] * fs['进价成本']

                # 按天汇总营业额和商品成本
                fs['日期_str'] = fs['日期_dt'].dt.strftime('%Y/%m/%d')
                daily_sales = fs.groupby('日期_str').agg({'总营业额': 'sum', '总进价成本': 'sum'}).reset_index()

                # --- 2. 计算考勤端的人工成本 ---
                if not fa.empty:
                    fa['核算薪资'] = pd.to_numeric(fa['核算薪资'], errors='coerce').fillna(0.0)
                    fa['日期_str'] = fa['日期_dt'].dt.strftime('%Y/%m/%d')
                    daily_att = fa.groupby('日期_str').agg({'核算薪资': 'sum'}).reset_index()
                    daily_att.rename(columns={'核算薪资': '人工成本'}, inplace=True)
                else:
                    daily_att = pd.DataFrame(columns=['日期_str', '人工成本'])

                # --- 3. 跨表融合 (Outer Merge) ---
                daily_np = pd.merge(daily_sales, daily_att, on='日期_str', how='outer').fillna(0.0)
                daily_np = daily_np.sort_values('日期_str', ascending=False)

                # --- 4. 算账！---
                daily_np['毛利润'] = daily_np['总营业额'] - daily_np['总进价成本']
                daily_np['真实净利润'] = daily_np['毛利润'] - daily_np['人工成本']

                # 顶层看板指标计算
                tot_rev = daily_np['总营业额'].sum()
                tot_cogs = daily_np['总进价成本'].sum()
                tot_wage = daily_np['人工成本'].sum()
                tot_gross = daily_np['毛利润'].sum()
                tot_net = daily_np['真实净利润'].sum()

                st.markdown("### 📊 阶段性核心指标")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("💰 总营业额 (Revenue)", f"${tot_rev:.2f}")
                m2.metric("📦 总商品成本 (COGS)", f"${tot_cogs:.2f}")
                m3.metric("👥 总人工成本 (Wages)", f"${tot_wage:.2f}")

                # 净利润带颜色提示
                m4.metric("💎 真实净利润 (Net Profit)", f"${tot_net:.2f}", delta=f"对比毛利: ${tot_gross:.2f}", delta_color="normal")

                st.divider()
                st.markdown("### 📅 每日盈亏明细榜 (Daily P&L)")

                # 表格美化展示，赚钱背景变绿，亏钱背景变红
                show_np = daily_np.rename(columns={'日期_str': '日期'})
                
                # 构建带有颜色渲染的数据框
                st.dataframe(
                    show_np.style.format({
                        '总营业额': '${:.2f}',
                        '总进价成本': '${:.2f}',
                        '人工成本': '${:.2f}',
                        '毛利润': '${:.2f}',
                        '真实净利润': '${:.2f}'
                    }).background_gradient(subset=['真实净利润'], cmap='RdYlGn'),
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.info("暂无有效销售数据进行核算。")
    else:
        st.info("💡 目前没有流水记录，无法计算利润。")
