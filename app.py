import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import gspread 
from gspread.exceptions import WorksheetNotFound
import json
import plotly.express as px

# --- 1. 配置与云端数据库初始化 ---
st.set_page_config(page_title="Taka 零售终极管理系统", layout="wide")

try:
    key_dict = json.loads(st.secrets["google_key"])
    gc = gspread.service_account_from_dict(key_dict)
    sh = gc.open_by_url(st.secrets["sheet_url"]) 
except Exception as e:
    st.error(f"🔴 数据库连接失败 Database connection failed! Error: {e}")
    st.stop()

# ================= 🚀 国际化 (i18n) 双语翻译引擎 =================
if "lang" not in st.session_state:
    st.session_state.lang = "cn"

# 1. 静态界面文本翻译
def t(cn_text, en_text):
    return cn_text if st.session_state.lang == "cn" else en_text

# 2. 表头字段翻译映射
col_map = {
    '商品名称': 'Product', '颜色': 'Variant', '进价成本': 'Cost', '售卖价格': 'Price',
    '应收到数量': 'Expected', '展示数量': 'Display', '货柜数量': 'Cabinet', '储物间数量': 'Storage', 
    '坏货数量': 'Damaged', '已售出数量': 'Total Sold', '总库存': 'Total Stock', '期间售出': 'Period Sales',
    '订单号': 'Order ID', '日期': 'Date', '收银员': 'Cashier', '销售数量': 'Qty', '成交单价': 'Unit Price', 
    '总营业额': 'Total Amount', '小计': 'Subtotal', '有效客流': 'Traffic',
    '员工姓名': 'Staff Name', '职位': 'Role', '时薪': 'Hourly Wage', '状态': 'Status',
    '创建日期': 'Create Date', '客户名称': 'Client', '采购数量': 'Purchase Qty', 'B2B单价': 'B2B Price',
    '总计应收': 'Total Recv.', '已收定金': 'Deposit', '待收尾款': 'Balance', '约定交期': 'Deadline', '订单状态': 'Order Status', '备注': 'Notes',
    '记录日期': 'Log Date', '操作类型': 'Operation', '变动数量': 'Change Qty', '库位详情': 'Location Det.'
}

# 3. 🚀 动态核心数据内容翻译字典 (包含最新所有产品与颜色)
val_map_cn_to_en = {
    # --- 🎨 颜色 ---
    "黑": "Black", "金缮": "Kintsugi", "墨金": "Ink Gold", "银霜": "Silver", "黑玉": "Black",
    "陨星黑": "Meteorite Black", "陨星": "Meteorite", "天蓝": "Sky Blue", 
    "金色": "Gold", "蓝色": "Blue", "灰色": "Grey", "银色": "Silver", "黑色": "Black", "默认": "Default", "多件混装": "Mixed Combo",
    "粉色": "Pink", "绿色": "Green", "紫色": "Purple", "枫叶红": "Maple Red",
    
    # --- 📦 产品 ---
    "口红杯": "Lipstick Cup",
    "咖啡吸管杯 480ml": "Coffee Cup With Straw 480 ML",
    "臻享 焖茶壶": "Brew Bottle",
    "冲锋壶680ML": "Canteen Bottle 680ML",
    "焖茶杯": "Brew Bottle", "纯钛酒壶": "Pure Ti Wine Flask", "直滤杯": "Flat Bottom", "冲锋壶": "Canteen",
    "咖啡杯": "Coffee Cup With Straw", "口袋杯": "Pocket Cup", "筷子": "Chopstick", "保温壶": "Thermal Flask",
    "托盘": "Tray", "盘子": "Plate", "叶碟": "Leaf Plate", "随心杯": "Easy Cup", "主人杯": "Host Cup",
    "迷你杯": "Mini Cup", "钛艺T杯": "Ti Artisan Bottle", "圆融杯": "Round cup",
    "钛杯": "Titanium Cup", "常规水杯": "Standard Cup", "低价配件": "Accessories", "T杯": "T-Cup", "钛碗": "Titanium Bowl",
    
    # --- 身份与状态 ---
    "在职": "Active", "离职": "Resigned",
    "店长": "Manager", "全职店员": "Full-time", "兼职店员": "Part-time", "实习生": "Intern", "合作厂商": "Supplier", "其他": "Other",
    "意向/沟通中": "In Communication", "已付定金/备货中": "Deposit Paid", "已发货/待结尾款": "Shipped/Pending", "✅ 订单已完成": "✅ Completed",
    "入库": "Inbound", "调拨": "Transfer", "盘盈": "Surplus (+)", "盘亏": "Shortage (-)", "初始建档": "Initial Setup"
}
val_map_en_to_cn = {v: k for k, v in val_map_cn_to_en.items()}

def t_val(val, to_lang):
    if pd.isna(val): return val
    val_str = str(val).strip()
    if to_lang == 'en': return val_map_cn_to_en.get(val_str, val_str)
    else: return val_map_en_to_cn.get(val_str, val_str)

def translate_series(series):
    if st.session_state.lang == 'en':
        # 强制转换为字符串以防止 PyArrow 空值连接报错
        return series.map(lambda x: val_map_cn_to_en.get(str(x).strip(), str(x).strip())).astype(str)
    return series.astype(str)
# ===============================================================

STOCK_SHEET = "Stock"
SALES_SHEET = "Sales"
EMP_SHEET = "Employee"
ATT_SHEET = "Attendance"
B2B_SHEET = "B2B_Orders" 
FEEDBACK_SHEET = "Feedback"
RESTOCK_SHEET = "Restock_Log"
TRAFFIC_SHEET = "Traffic_Log"
CAMP_SHEET = "Campaigns"

STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '应收到数量', '展示数量', '货柜数量', '储物间数量', '坏货数量', '已售出数量', '总库存']
SALES_COLS = ['订单号', '日期', '收银员', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']
EMP_COLS = ['员工姓名', '职位', '时薪', '联系方式', '入职日期', '登录密码', '状态']
ATT_COLS = ['员工姓名', '日期', '开始时间', '结束时间', '工作时长', '核算薪资']
B2B_COLS = ['创建日期', '客户名称', '商品名称', '颜色', '采购数量', 'B2B单价', '总计应收', '货物成本', '物流成本', '关税', '已收定金', '待收尾款', '约定交期', '订单状态', '备注']
FEEDBACK_COLS = ['反馈日期', '商品名称', '客户画像', '反馈类型', '详细原话', '跟进状态']
RESTOCK_COLS = ['记录日期', '操作类型', '商品名称', '颜色', '变动数量', '库位详情', '单件成本', '备注']
TRAFFIC_COLS = ['日期', '有效客流']
CAMP_COLS = ['档期名称', '开始日期', '结束日期']

if "sheet_versions" not in st.session_state:
    st.session_state.sheet_versions = {
        STOCK_SHEET: 0, SALES_SHEET: 0, EMP_SHEET: 0,
        ATT_SHEET: 0, B2B_SHEET: 0, FEEDBACK_SHEET: 0, RESTOCK_SHEET: 0, TRAFFIC_SHEET: 0, CAMP_SHEET: 0
    }

if "pos_cart" not in st.session_state:
    st.session_state.pos_cart = []

@st.cache_data(ttl=300, show_spinner=False)
def load_raw_data(sheet_name, version):
    try:
        worksheet = sh.worksheet(sheet_name)
        records = worksheet.get_all_records()
        if not records:
            return pd.DataFrame()
        return pd.DataFrame(records)
    except Exception as e:
        return pd.DataFrame()

def load_data(sheet_name, columns):
    ver = st.session_state.sheet_versions.get(sheet_name, 0)
    df = load_raw_data(sheet_name, ver)
    if df.empty:
        df = pd.DataFrame(columns=columns)
    for col in columns:
        if col not in df.columns: 
            df[col] = "" 
    return df[columns]

def save_data(df, sheet_name):
    try:
        worksheet = sh.worksheet(sheet_name)
    except WorksheetNotFound:
        worksheet = sh.add_worksheet(title=sheet_name, rows="1000", cols="20")
        
    worksheet.clear() 
    df_safe = df.fillna("").astype(str)
    data_to_upload = [df_safe.columns.values.tolist()] + df_safe.values.tolist()
    worksheet.update(values=data_to_upload, range_name='A1')
    
    st.session_state.sheet_versions[sheet_name] = st.session_state.sheet_versions.get(sheet_name, 0) + 1

def clean_date_col(df, col_name):
    if not df.empty and col_name in df.columns:
        # 防报错：处理空值日期
        formatted = pd.to_datetime(df[col_name], errors='coerce').dt.strftime('%Y/%m/%d')
        df[col_name] = formatted.fillna('')
    return df

def load_safe_sales():
    df = clean_date_col(load_data(SALES_SHEET, SALES_COLS), '日期')
    if not df.empty:
        df['订单号'] = df['订单号'].astype(str).replace('0', '历史单').replace('', '历史单').replace('nan', '历史单')
        if '收银员' not in df.columns:
            df['收银员'] = '店长/历史'
        else:
            df['收银员'] = df['收银员'].astype(str).replace('0', '店长/历史').replace('', '店长/历史').replace('nan', '店长/历史')
    return df

def load_safe_emp():
    df = clean_date_col(load_data(EMP_SHEET, EMP_COLS), '入职日期') 
    if not df.empty:
        df['状态'] = df['状态'].astype(str).replace('0', '在职').replace('', '在职').replace('nan', '在职')
        df['登录密码'] = df['登录密码'].astype(str).replace('0', '').replace('nan', '')
    return df

def JIT_fetch(sheets_to_fetch):
    st.cache_data.clear() 
    res = {}
    if STOCK_SHEET in sheets_to_fetch: res[STOCK_SHEET] = load_data(STOCK_SHEET, STOCK_COLS)
    if SALES_SHEET in sheets_to_fetch: res[SALES_SHEET] = load_safe_sales()
    if RESTOCK_SHEET in sheets_to_fetch: res[RESTOCK_SHEET] = clean_date_col(load_data(RESTOCK_SHEET, RESTOCK_COLS), '记录日期')
    if B2B_SHEET in sheets_to_fetch: res[B2B_SHEET] = clean_date_col(clean_date_col(load_data(B2B_SHEET, B2B_COLS), '创建日期'), '约定交期')
    if FEEDBACK_SHEET in sheets_to_fetch: res[FEEDBACK_SHEET] = clean_date_col(load_data(FEEDBACK_SHEET, FEEDBACK_COLS), '反馈日期')
    if EMP_SHEET in sheets_to_fetch: res[EMP_SHEET] = load_safe_emp()
    if ATT_SHEET in sheets_to_fetch: res[ATT_SHEET] = clean_date_col(load_data(ATT_SHEET, ATT_COLS), '日期')
    if TRAFFIC_SHEET in sheets_to_fetch: res[TRAFFIC_SHEET] = clean_date_col(load_data(TRAFFIC_SHEET, TRAFFIC_COLS), '日期')
    return res

@st.cache_data(show_spinner=False)
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8-sig')

df_stock = load_data(STOCK_SHEET, STOCK_COLS)
df_sales = load_safe_sales()
df_employee = load_safe_emp()
df_attendance = clean_date_col(load_data(ATT_SHEET, ATT_COLS), '日期') 
df_b2b = clean_date_col(clean_date_col(load_data(B2B_SHEET, B2B_COLS), '创建日期'), '约定交期')
df_feedback = clean_date_col(load_data(FEEDBACK_SHEET, FEEDBACK_COLS), '反馈日期')
df_restock = clean_date_col(load_data(RESTOCK_SHEET, RESTOCK_COLS), '记录日期')
df_traffic = clean_date_col(load_data(TRAFFIC_SHEET, TRAFFIC_COLS), '日期')
df_camp = clean_date_col(clean_date_col(load_data(CAMP_SHEET, CAMP_COLS), '开始日期'), '结束日期')

if "stock_reset_key" not in st.session_state: st.session_state.stock_reset_key = 0
if "sales_reset_key" not in st.session_state: st.session_state.sales_reset_key = 0
if "emp_reset_key" not in st.session_state: st.session_state.emp_reset_key = 0
if "att_reset_key" not in st.session_state: st.session_state.att_reset_key = 0 
if "b2b_reset_key" not in st.session_state: st.session_state.b2b_reset_key = 0 
if "fb_reset_key" not in st.session_state: st.session_state.fb_reset_key = 0 

def clear_stock(): st.session_state.stock_reset_key += 1
def clear_sales(): st.session_state.sales_reset_key += 1
def clear_emp(): st.session_state.emp_reset_key += 1
def clear_att(): st.session_state.att_reset_key += 1
def clear_b2b(): st.session_state.b2b_reset_key += 1
def clear_fb(): st.session_state.fb_reset_key += 1

manager_password = "taka888"

# 🚀 门禁系统角色解析
if "role" not in st.session_state:
    query_role = st.query_params.get("role")
    query_user = st.query_params.get("user")
    
    if query_role == "admin":
        st.session_state.role = "admin"
        st.session_state.current_user = "店长"
    elif query_role in ["employee", "supplier"] and query_user:
        st.session_state.role = query_role
        st.session_state.current_user = query_user
    else:
        st.session_state.role = None
        st.session_state.current_user = None

# 🚀 全局档期状态初始化
if "camp_start" not in st.session_state: st.session_state.camp_start = datetime(2026, 3, 26).date()
if "camp_end" not in st.session_state: st.session_state.camp_end = datetime.now().date()
if "camp_name" not in st.session_state: st.session_state.camp_name = "默认全局"

with st.sidebar:
    st.header(t("🔐 系统门禁", "🔐 System Access"))
    
    if st.session_state.role is not None:
        if st.session_state.role == "admin": user_emoji = "👑"
        elif st.session_state.role == "supplier": user_emoji = "🏭"
        else: user_emoji = "🧑‍💼"
        
        st.success(t(f"{user_emoji} 欢迎回来：{st.session_state.current_user}", f"{user_emoji} Welcome back: {st.session_state.current_user}"))
        if st.button(t("🚪 退出系统 (交接班)", "🚪 Logout (Handover)"), use_container_width=True):
            st.session_state.role = None
            st.session_state.current_user = None
            st.query_params.clear()
            st.rerun()
            
        is_admin = (st.session_state.role == "admin")
        
        st.divider()
        if is_admin:
            st.header("🎯 全局档期基准台")
            st.info("💡 选定档期后，右侧报表的默认日历会自动跳转到该区间。")
            
            camp_options = df_camp['档期名称'].dropna().unique().tolist() if not df_camp.empty else []
            
            def on_camp_change():
                sel = st.session_state.camp_selector
                if sel != "手动自定义区间" and not df_camp.empty:
                    row = df_camp[df_camp['档期名称'] == sel].iloc[0]
                    try:
                        st.session_state.camp_start = pd.to_datetime(row['开始日期']).date()
                        st.session_state.camp_end = pd.to_datetime(row['结束日期']).date()
                        st.session_state.camp_name = sel
                    except:
                        pass
                else:
                    st.session_state.camp_name = "手动自定义区间"
            
            st.selectbox("📌 选择基准档期", ["手动自定义区间"] + camp_options, key="camp_selector", on_change=on_camp_change)
            
            st.write(f"**当前基准区间:** `{st.session_state.camp_start}` 至 `{st.session_state.camp_end}`")
                
            with st.expander("⚙️ 管理/自建档期名录", expanded=False):
                st.write("在此新增或修改你的 Pop-up 档期规划：")
                
                v_camp = df_camp.copy()
                if not v_camp.empty:
                    v_camp['开始日期'] = pd.to_datetime(v_camp['开始日期'], errors='coerce')
                    v_camp['结束日期'] = pd.to_datetime(v_camp['结束日期'], errors='coerce')
                else:
                    v_camp = pd.DataFrame(columns=CAMP_COLS)
                    
                edited_camp = st.data_editor(
                    v_camp, 
                    num_rows="dynamic",
                    column_config={
                        "开始日期": st.column_config.DateColumn("开始日期", format="YYYY/MM/DD"),
                        "结束日期": st.column_config.DateColumn("结束日期", format="YYYY/MM/DD"),
                    },
                    use_container_width=True
                )
                
                if st.button("💾 保存档期名录", type="primary", use_container_width=True):
                    # 修复 1：安全的日期转换，防止空行报错
                    edited_camp['开始日期'] = pd.to_datetime(edited_camp['开始日期'], errors='coerce').dt.strftime('%Y/%m/%d')
                    edited_camp['结束日期'] = pd.to_datetime(edited_camp['结束日期'], errors='coerce').dt.strftime('%Y/%m/%d')
                    
                    edited_camp = edited_camp[edited_camp['档期名称'].astype(str).str.strip() != '']
                    edited_camp['开始日期'] = edited_camp['开始日期'].fillna("")
                    edited_camp['结束日期'] = edited_camp['结束日期'].fillna("")
                    
                    save_data(edited_camp, CAMP_SHEET)
                    st.success("✅ 档期名录已更新入云端！")
                    st.rerun()
            
            st.divider()
            
            st.header("🛠️ 核心管理")
            with st.expander("➕ 新增产品建档 (Add SKU)"):
                with st.form("new_sku"):
                    n_name = st.text_input("产品名称")
                    n_color = st.text_input("颜色")
                    c1, c2, c3 = st.columns(3)
                    n_cost, n_price, n_expect = c1.number_input("进价", format="%.2f"), c2.number_input("售价", format="%.2f"), c3.number_input("应收")
                    i1, i2, i3, i4 = st.columns(4)
                    n_disp, n_shelf, n_stor, n_dmg = i1.number_input("展示"), i2.number_input("货柜"), i3.number_input("储物"), i4.number_input("坏货")
                    if st.form_submit_button("确认建档"):
                        if n_name and n_color:
                            fresh = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET])
                            latest_stock = fresh[STOCK_SHEET]
                            latest_restock = fresh[RESTOCK_SHEET]
                            
                            total = n_disp + n_shelf + n_stor 
                            new_r = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, n_dmg, 0, total]], columns=STOCK_COLS)
                            latest_stock = pd.concat([latest_stock, new_r], ignore_index=True)
                            
                            if total > 0 or n_dmg > 0:
                                log_date = datetime.now().strftime("%Y/%m/%d")
                                init_log = pd.DataFrame([[log_date, "初始建档", n_name, n_color, total+n_dmg, "多库位", n_cost, "侧边栏初始建档"]], columns=RESTOCK_COLS)
                                latest_restock = pd.concat([init_log, latest_restock], ignore_index=True)
                                save_data(latest_restock, RESTOCK_SHEET)
                                
                            save_data(latest_stock, STOCK_SHEET) 
                            st.success("✅ 云端建档成功！")
                            st.rerun()
    
    else:
        login_type = st.radio(t("请选择您的身份", "Select Role"), [t("🧑‍💼 门店店员 / 🏭 合作厂商", "🧑‍💼 Staff / 🏭 Supplier"), t("👑 店长/管理员", "👑 Admin")], horizontal=True)
        
        if login_type == t("👑 店长/管理员", "👑 Admin"):
            pwd_input = st.text_input(t("输入授权密码", "Enter Admin Password"), type="password")
            if st.button(t("🔓 登录后台", "🔓 Login"), use_container_width=True):
                if pwd_input == manager_password:
                    st.session_state.role = "admin"
                    st.session_state.current_user = "店长"
                    st.query_params["role"] = "admin"
                    st.rerun()
                else:
                    st.error(t("❌ 密码错误！", "❌ Incorrect Password!"))
        else:
            if df_employee.empty:
                st.warning(t("⚠️ 系统内暂无人员档案。请联系店长添加。", "⚠️ No staff records found. Contact Admin."))
            else:
                active_emps = df_employee[df_employee['状态'] != '离职']['员工姓名'].tolist()
                
                if not active_emps:
                    st.warning(t("⚠️ 系统中无在职人员。", "⚠️ No active staff found."))
                else:
                    emp_sel = st.selectbox(t("选择您的名字", "Select your name"), active_emps)
                    emp_row = df_employee[df_employee['员工姓名'] == emp_sel].iloc[0]
                    emp_pwd = str(emp_row['登录密码']).strip()
                    assigned_role = "supplier" if str(emp_row.get('职位', '')).strip() == '合作厂商' else "employee"
                    
                    if emp_pwd == "":
                        st.info(t("🌟 系统检测到您是首次登录，请设置专属 PIN 码。", "🌟 First time login. Please set your PIN."))
                        new_pwd = st.text_input(t("设置我的登录密码", "Set PIN"), type="password")
                        if st.button(t("💾 保存并进入系统", "💾 Save & Login"), use_container_width=True):
                            if new_pwd.strip() == "":
                                st.warning(t("密码不能为空哦！", "PIN cannot be empty!"))
                            else:
                                fresh_emp = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                                idx = fresh_emp[fresh_emp['员工姓名'] == emp_sel].index[0]
                                fresh_emp.at[idx, '登录密码'] = new_pwd
                                save_data(fresh_emp, EMP_SHEET)
                                
                                st.session_state.role = assigned_role
                                st.session_state.current_user = emp_sel
                                st.query_params["role"] = assigned_role
                                st.query_params["user"] = emp_sel
                                st.success("✅ 密码设置成功！")
                                st.rerun()
                    else:
                        emp_pwd_input = st.text_input(t("输入您的 PIN 码", "Enter PIN"), type="password")
                        if st.button(t("🔑 打卡/登录", "🔑 Login"), use_container_width=True):
                            if emp_pwd_input == emp_pwd:
                                st.session_state.role = assigned_role
                                st.session_state.current_user = emp_sel
                                st.query_params["role"] = assigned_role
                                st.query_params["user"] = emp_sel
                                st.rerun()
                            else:
                                st.error(t("❌ 密码不匹配！", "❌ Incorrect PIN!"))

if st.session_state.role is None:
    # --- 登录界面的语言切换器 ---
    col_t, col_l = st.columns([8, 2])
    with col_t:
        st.title(t("🏙️ Takashimaya 零售管理系统", "🏙️ Takashimaya Retail System"))
    with col_l:
        lang_choice = st.radio("🌐 Language", ["中文", "English"], index=0 if st.session_state.lang == 'cn' else 1, horizontal=True)
        if (lang_choice == "中文" and st.session_state.lang != "cn") or (lang_choice == "English" and st.session_state.lang != "en"):
            st.session_state.lang = 'cn' if lang_choice == "中文" else 'en'
            st.rerun()
            
    st.info(t("👈 请在左侧选择您的身份并完成登录。", "👈 Please select your role on the left menu to login."))
    st.stop()  

# ================= 🚀 主界面布局 =================
col_title, col_lang = st.columns([8, 2])
with col_title:
    st.title(t("🏙️ Takashimaya 零售管理系统 (云端同步版)", "🏙️ Takashimaya Retail System (Cloud Sync)"))
with col_lang:
    lang_choice = st.radio("🌐 Language", ["中文", "English"], index=0 if st.session_state.lang == 'cn' else 1, horizontal=True)
    if (lang_choice == "中文" and st.session_state.lang != "cn") or (lang_choice == "English" and st.session_state.lang != "en"):
        st.session_state.lang = 'cn' if lang_choice == "中文" else 'en'
        st.rerun()

q = st.text_input(t("🔍 快速筛选 (全局搜索)...", "🔍 Quick Search..."), placeholder=t("搜商品/单号/客户...", "Search items/orders/customers..."))

def get_f(df, q):
    if q and not df.empty:
        mask = pd.Series(False, index=df.index)
        # 支持中英文混合搜索 (输入英文也能搜到中文数据)
        q_cn = t_val(q, 'cn')
        for col in df.columns:
            mask = mask | df[col].fillna('').astype(str).str.contains(q, case=False, regex=False) | df[col].fillna('').astype(str).str.contains(q_cn, case=False, regex=False)
        return df[mask]
    return df

is_admin = st.session_state.role == "admin"
is_supplier = st.session_state.role == "supplier"
is_employee = st.session_state.role == "employee"

if is_admin:
    t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([t("📊 库存", "📊 Inventory"), t("💰 销售", "💰 Sales"), t("📈 毛利", "📈 Gross Margin"), t("👥 考勤", "👥 Staff"), t("💎 净利润", "💎 Net Profit"), t("🤝 B2B订单", "🤝 B2B"), t("🗣️ 客户反馈", "🗣️ Feedback"), t("🧠 战略(BI)", "🧠 Strategy BI")])
elif is_supplier:
    t1, t2, t3, t4 = st.tabs([t("📊 实时库存快照", "📊 Inventory Snapshot"), t("💰 销售报表对账", "💰 Sales Report"), t("📦 进货对账 (ERP流水)", "📦 Inbound Records"), t("🤝 B2B订单对账", "🤝 B2B Orders")])
else:
    t1, t2 = st.tabs([t("📊 实时库存查询", "📊 Inventory Snapshot"), t("🛒 智能POS收银台", "🛒 Smart POS")])

# ================= 🚀 Tab 1: 库存面板 =================
with t1:
    f_opts_stk = df_stock.copy()
    stock_list_labels = []
    if not f_opts_stk.empty:
        # 修复 2: 组装下拉菜单时，强制转换为字符串，防止 PyArrow 报错
        f_opts_stk['disp_name'] = translate_series(f_opts_stk['商品名称']).astype(str)
        f_opts_stk['disp_color'] = translate_series(f_opts_stk['颜色']).astype(str)
        f_opts_stk['label'] = f_opts_stk['disp_name'] + " (" + f_opts_stk['disp_color'] + ")"
        stock_list_labels = f_opts_stk['label'].tolist()
        
    if is_admin:
        st.subheader("📦 专业 ERP 库存与货位管家")
        t1_a, t1_b, t1_c = st.tabs(["📥 1. 补货入库 (Restock)", "🔄 2. 货位调拨 (Transfer)", "⚖️ 3. 盘点平账 (Adjust)"])
        
        with t1_a:
            with st.form("form_restock"):
                c1, c2, c3 = st.columns(3)
                r_sku = c1.selectbox("选择到货商品", stock_list_labels) if stock_list_labels else c1.selectbox("选择到货商品", ["请先在侧边栏新增商品"])
                r_date = c2.date_input("入库日期", value=datetime.now())
                r_loc = c3.selectbox("卸货存放至", ["储物间数量", "货柜数量", "展示数量"])
                
                c4, c5, c6 = st.columns(3)
                r_qty = c4.number_input("入库数量", min_value=1, step=1, value=50)
                r_cost = c5.number_input("此批单件进价 ($) - 留空不改", value=0.0, format="%.2f")
                r_note = c6.text_input("备注单号或说明", placeholder="如：国内空运第3批...")
                
                if st.form_submit_button("✅ 确认入库", type="primary", use_container_width=True):
                    if stock_list_labels:
                        fresh = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET])
                        latest_stock = fresh[STOCK_SHEET]
                        latest_restock = fresh[RESTOCK_SHEET]
                        
                        # 反向解析出中文真实名称存入数据库
                        sel_disp_name = r_sku.rsplit(" (", 1)[0]
                        sel_disp_color = r_sku.rsplit(" (", 1)[1].replace(")", "")
                        real_name = t_val(sel_disp_name, 'cn')
                        real_color = t_val(sel_disp_color, 'cn')
                        
                        idx = latest_stock[(latest_stock['商品名称'] == real_name) & (latest_stock['颜色'] == real_color)].index[0]
                        latest_stock.at[idx, r_loc] = int(pd.to_numeric(latest_stock.at[idx, r_loc], errors='coerce') or 0) + r_qty
                        latest_stock.at[idx, '总库存'] = sum([int(pd.to_numeric(latest_stock.at[idx, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                        if r_cost > 0: latest_stock.at[idx, '进价成本'] = r_cost 
                            
                        new_log = pd.DataFrame([[
                            r_date.strftime("%Y/%m/%d"), "入库", real_name, real_color, r_qty, 
                            f"存入: {r_loc.replace('数量','')}", r_cost, r_note
                        ]], columns=RESTOCK_COLS)
                        
                        latest_restock = pd.concat([new_log, latest_restock], ignore_index=True)
                        save_data(latest_stock, STOCK_SHEET)
                        save_data(latest_restock, RESTOCK_SHEET)
                        st.success(f"🎉 补货成功！已入库 {r_qty} 件至【{r_loc.replace('数量','')}】。")
                        st.rerun()

        with t1_b:
            with st.form("form_transfer"):
                c1, c2, c3, c4 = st.columns(4)
                t_sku = c1.selectbox("选择调拨商品", stock_list_labels, key="t_sku") if stock_list_labels else c1.selectbox("选择", ["空"])
                t_src = c2.selectbox("从何处移出 (源)", ["储物间数量", "货柜数量", "展示数量"])
                t_dst = c3.selectbox("移到何处去 (目标)", ["货柜数量", "展示数量", "储物间数量"])
                t_qty = c4.number_input("移动数量", min_value=1, step=1, value=10)
                
                if st.form_submit_button("🔄 确认移库", type="primary", use_container_width=True):
                    if stock_list_labels and t_src != t_dst:
                        fresh = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET])
                        latest_stock = fresh[STOCK_SHEET]
                        latest_restock = fresh[RESTOCK_SHEET]
                        
                        sel_disp_name = t_sku.rsplit(" (", 1)[0]
                        sel_disp_color = t_sku.rsplit(" (", 1)[1].replace(")", "")
                        real_name = t_val(sel_disp_name, 'cn')
                        real_color = t_val(sel_disp_color, 'cn')
                        
                        idx = latest_stock[(latest_stock['商品名称'] == real_name) & (latest_stock['颜色'] == real_color)].index[0]
                        curr_src_qty = int(pd.to_numeric(latest_stock.at[idx, t_src], errors='coerce') or 0)
                        if curr_src_qty < t_qty:
                            st.error(f"⚠️ {t_src.replace('数量','')} 库存不足！仅剩 {curr_src_qty} 件。")
                        else:
                            latest_stock.at[idx, t_src] = curr_src_qty - t_qty
                            latest_stock.at[idx, t_dst] = int(pd.to_numeric(latest_stock.at[idx, t_dst], errors='coerce') or 0) + t_qty
                            
                            new_log = pd.DataFrame([[
                                datetime.now().strftime("%Y/%m/%d"), "调拨", real_name, real_color, t_qty, 
                                f"{t_src.replace('数量','')} -> {t_dst.replace('数量','')}", 0, "内部货架整理"
                            ]], columns=RESTOCK_COLS)
                            
                            latest_restock = pd.concat([new_log, latest_restock], ignore_index=True)
                            save_data(latest_stock, STOCK_SHEET)
                            save_data(latest_restock, RESTOCK_SHEET)
                            st.success("✅ 移库成功！总库存数量不变。")
                            st.rerun()

        with t1_c:
            with st.form("form_adjust"):
                c1, c2, c3, c4 = st.columns(4)
                a_sku = c1.selectbox("选择需平账商品", stock_list_labels, key="a_sku") if stock_list_labels else c1.selectbox("选择", ["空"])
                a_loc = c2.selectbox("发生差异的库位", ["货柜数量", "展示数量", "储物间数量", "坏货数量"])
                a_diff = c3.number_input("盘点差异 (+为盘盈, -为盘亏丢失)", value=-1, step=1, help="例如发现被偷了1件，填 -1")
                a_note = c4.text_input("平账原因 (必填)", placeholder="例如：盘点发现丢失...")
                
                if st.form_submit_button("⚖️ 确认记账", type="primary", use_container_width=True):
                    if stock_list_labels and a_note.strip() != "" and a_diff != 0:
                        fresh = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET])
                        latest_stock = fresh[STOCK_SHEET]
                        latest_restock = fresh[RESTOCK_SHEET]
                        
                        sel_disp_name = a_sku.rsplit(" (", 1)[0]
                        sel_disp_color = a_sku.rsplit(" (", 1)[1].replace(")", "")
                        real_name = t_val(sel_disp_name, 'cn')
                        real_color = t_val(sel_disp_color, 'cn')
                        
                        idx = latest_stock[(latest_stock['商品名称'] == real_name) & (latest_stock['颜色'] == real_color)].index[0]
                        latest_stock.at[idx, a_loc] = int(pd.to_numeric(latest_stock.at[idx, a_loc], errors='coerce') or 0) + a_diff
                        if a_loc != '坏货数量':
                            latest_stock.at[idx, '总库存'] = sum([int(pd.to_numeric(latest_stock.at[idx, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                        adj_type = "盘盈" if a_diff > 0 else "盘亏"
                        new_log = pd.DataFrame([[
                            datetime.now().strftime("%Y/%m/%d"), adj_type, real_name, real_color, a_diff, 
                            f"库位: {a_loc.replace('数量','')}", 0, a_note
                        ]], columns=RESTOCK_COLS)
                        
                        latest_restock = pd.concat([new_log, latest_restock], ignore_index=True)
                        save_data(latest_stock, STOCK_SHEET)
                        save_data(latest_restock, RESTOCK_SHEET)
                        st.success(f"✅ 盘点账目已抹平！记录类型：{adj_type}。")
                        st.rerun()
        st.divider()

    role_title = t(" (厂商查阅版)", " (Supplier View)") if is_supplier else t(" (实时快照)", " (Snapshot)")
    st.subheader(t(f"📊 实时库存与期间动销快照{role_title}", f"📊 Real-time Inventory & Sales Snapshot{role_title}"))
    st.info(t("💡 【总库存】代表当下的真实剩余物理库存；【期间售出】代表您下方选定时间段内的实际销量。", "💡 [Total Stock] reflects real-time physical inventory. [Period Sales] shows items sold within the selected date range."))
    
    sel_range_t1 = st.date_input(
        t("⏳ 选择要分析的销售区间：", "⏳ Select Date Range:"), 
        value=[st.session_state.camp_start, st.session_state.camp_end],
        key="t1_date_picker"
    )
    if len(sel_range_t1) == 2: t1_start, t1_end = sel_range_t1[0], sel_range_t1[1]
    else: t1_start, t1_end = sel_range_t1[0], sel_range_t1[0]
        
    f_stock = get_f(df_stock, q)
    if not f_stock.empty:
        v_df = f_stock.copy()
        
        period_sales = pd.DataFrame()
        if not df_sales.empty:
            df_s_t1 = df_sales.copy()
            df_s_t1['日期_dt'] = pd.to_datetime(df_s_t1['日期'], errors='coerce')
            f_s_t1 = df_s_t1[(df_s_t1['日期_dt'] >= pd.Timestamp(t1_start)) & (df_s_t1['日期_dt'] <= pd.Timestamp(t1_end))]
            if not f_s_t1.empty:
                f_s_t1['销售数量'] = pd.to_numeric(f_s_t1['销售数量'], errors='coerce').fillna(0)
                period_sales = f_s_t1.groupby(['商品名称', '颜色'])['销售数量'].sum().reset_index()
                period_sales.rename(columns={'销售数量': '期间售出'}, inplace=True)
        
        if not period_sales.empty: v_df = v_df.merge(period_sales, on=['商品名称', '颜色'], how='left')
        else: v_df['期间售出'] = 0
            
        v_df['期间售出'] = v_df['期间售出'].fillna(0).astype(int)
        
        int_cols = ['应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '期间售出']
        for col in int_cols: 
            if col in v_df.columns:
                v_df[col] = pd.to_numeric(v_df[col], errors='coerce').fillna(0).astype(int)
                
        v_df['进价成本'] = pd.to_numeric(v_df['进价成本'], errors='coerce').fillna(0.0)
        v_df['售卖价格'] = pd.to_numeric(v_df['售卖价格'], errors='coerce').fillna(0.0)
        
        def calc_margin(row):
            price = row['售卖价格']
            cost = row['进价成本']
            if price > 0: return f"{((price - cost) / price * 100):.1f}%"
            return "0.0%"
            
        v_df['单品毛利率'] = v_df.apply(calc_margin, axis=1)
        v_df.insert(0, "选择", False)
        
        # 🚀 翻译数据列内容
        v_df['商品名称'] = translate_series(v_df['商品名称'])
        v_df['颜色'] = translate_series(v_df['颜色'])
        
        # 🚀 角色隔离显示逻辑与多语言渲染
        if is_supplier:
            display_cols = ['商品名称', '颜色', '期间售出', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '售卖价格']
            df_disp = v_df[display_cols].copy()
            if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
            price_col = 'Price' if st.session_state.lang == 'en' else '售卖价格'
            styled_df = df_disp.style.format({price_col: '${:.2f}'})
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            
        elif is_admin:
            display_cols = ['选择', '商品名称', '颜色', '期间售出', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '售卖价格', '进价成本', '单品毛利率']
            df_disp = v_df[display_cols].copy()
            if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
            
            p_col = 'Price' if st.session_state.lang == 'en' else '售卖价格'
            c_col = 'Cost' if st.session_state.lang == 'en' else '进价成本'
            stk_col = 'Total Stock' if st.session_state.lang == 'en' else '总库存'
            
            def highlight_low_stock(row):
                try:
                    if int(row[stk_col]) <= 2: return ['background-color: #ffe6e6; color: #cc0000; font-weight: bold;'] * len(row)
                except: pass
                return [''] * len(row)
                
            styled_df = df_disp.style.format({c_col: '${:.2f}', p_col: '${:.2f}'}).apply(highlight_low_stock, axis=1)
            sel_col = '选择'
            disabled_cols = [c for c in df_disp.columns if c != sel_col]
            
            edited_stock = st.data_editor(
                styled_df,
                column_config={sel_col: st.column_config.CheckboxColumn("Select" if st.session_state.lang == 'en' else "选择", default=False)},
                disabled=disabled_cols, use_container_width=True, hide_index=True, key=f"stock_editor_{st.session_state.stock_reset_key}"
            )
            selected_stock = edited_stock[edited_stock[sel_col] == True]
            
            if len(selected_stock) == 1:
                st.markdown("### ⚙️ SKU Edit")
                orig_disp_name = str(selected_stock.iloc[0]['Product' if st.session_state.lang == 'en' else '商品名称'])
                orig_disp_color = str(selected_stock.iloc[0]['Variant' if st.session_state.lang == 'en' else '颜色'])
                # 反向解析为中文
                real_orig_name = t_val(orig_disp_name, 'cn')
                real_orig_color = t_val(orig_disp_color, 'cn')
                
                raw_cost = str(selected_stock.iloc[0][c_col]).replace('$', '').replace(',', '')
                raw_price = str(selected_stock.iloc[0][p_col]).replace('$', '').replace(',', '')
                orig_cost = float(raw_cost) if raw_cost else 0.0
                orig_price = float(raw_price) if raw_price else 0.0

                with st.form("edit_base_info"):
                    ec1, ec2 = st.columns([1.5, 1.5])
                    e_name = ec1.text_input("Product Name (CN)", value=real_orig_name)
                    e_color = ec2.text_input("Variant/Color (CN)", value=real_orig_color)
                    ec4, ec5 = st.columns([1.5, 1.5])
                    e_cost = ec4.number_input("Cost ($)", value=orig_cost, format="%.2f")
                    e_price = ec5.number_input("Price ($)", value=orig_price, format="%.2f")
                    
                    if st.form_submit_button("💾 Save Changes", type="primary"):
                        fresh = JIT_fetch([STOCK_SHEET, SALES_SHEET, B2B_SHEET, RESTOCK_SHEET])
                        latest_stock = fresh[STOCK_SHEET]
                        latest_sales = fresh[SALES_SHEET]
                        latest_b2b = fresh[B2B_SHEET]
                        latest_restock = fresh[RESTOCK_SHEET]
                        
                        idx = latest_stock[(latest_stock['商品名称'] == real_orig_name) & (latest_stock['颜色'] == real_orig_color)].index[0]
                        latest_stock.at[idx, '商品名称'] = e_name
                        latest_stock.at[idx, '颜色'] = e_color
                        latest_stock.at[idx, '进价成本'] = e_cost
                        latest_stock.at[idx, '售卖价格'] = e_price
                        
                        if e_name != real_orig_name or e_color != real_orig_color:
                            if not latest_sales.empty:
                                latest_sales.loc[(latest_sales['商品名称'] == real_orig_name) & (latest_sales['颜色'] == real_orig_color), ['商品名称', '颜色']] = [e_name, e_color]
                                save_data(latest_sales, SALES_SHEET)
                            if not latest_restock.empty:
                                latest_restock.loc[(latest_restock['商品名称'] == real_orig_name) & (latest_restock['颜色'] == real_orig_color), ['商品名称', '颜色']] = [e_name, e_color]
                                save_data(latest_restock, RESTOCK_SHEET)
                            if not latest_b2b.empty:
                                latest_b2b.loc[(latest_b2b['商品名称'] == real_orig_name) & (latest_b2b['颜色'] == real_orig_color), ['商品名称', '颜色']] = [e_name, e_color]
                                save_data(latest_b2b, B2B_SHEET)
                        
                        save_data(latest_stock, STOCK_SHEET)
                        st.session_state.stock_reset_key += 1
                        st.success(f"✅ Product updated!")
                        st.rerun()

                if not selected_stock.empty:
                    if st.button("🗑️ 危险：彻底删档选中 (Delete)", type="primary", key="del_stock"):
                        fresh_stock = JIT_fetch([STOCK_SHEET])[STOCK_SHEET]
                        for _, row in selected_stock.iterrows():
                            d_name = row['Product' if st.session_state.lang == 'en' else '商品名称']
                            d_col = row['Variant' if st.session_state.lang == 'en' else '颜色']
                            fresh_stock = fresh_stock[~((fresh_stock['商品名称'] == t_val(d_name, 'cn')) & (fresh_stock['颜色'] == t_val(d_col, 'cn')))]
                        save_data(fresh_stock, STOCK_SHEET) 
                        st.session_state.stock_reset_key += 1 
                        st.rerun()
            
            with st.expander("📜 ERP底单 (Audit Logs)", expanded=False):
                df_restock_disp = get_f(df_restock, q).copy()
                df_restock_disp['操作类型'] = translate_series(df_restock_disp['操作类型'])
                df_restock_disp['商品名称'] = translate_series(df_restock_disp['商品名称'])
                df_restock_disp['颜色'] = translate_series(df_restock_disp['颜色'])
                df_restock_disp['库位详情'] = df_restock_disp['库位详情'].apply(lambda x: x.replace("存入: 货柜", "In: Cabinet").replace("存入: 展示", "In: Display").replace("存入: 储物间", "In: Storage") if st.session_state.lang == 'en' else x)
                if st.session_state.lang == 'en': df_restock_disp.rename(columns=col_map, inplace=True)
                st.dataframe(df_restock_disp, use_container_width=True)

        else: # 🧑‍💼 店员模式
            display_cols = ['商品名称', '颜色', '期间售出', '总库存', '展示数量', '货柜数量', '储物间数量', '售卖价格']
            df_disp = v_df[display_cols].copy()
            if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
            p_col = 'Price' if st.session_state.lang == 'en' else '售卖价格'
            styled_df = df_disp.style.format({p_col: '${:.2f}'})
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
    else:
        st.info(t("💡 暂无数据。", "💡 No data found."))

# ================= Tab 2: 销售/POS 面板 =================
with t2:
    if is_supplier:
        st.subheader(t("💰 销售报表对账查询", "💰 Sales Report Reconciliation"))
        if not df_sales.empty:
            df_s = df_sales.copy()
            df_s['日期_dt'] = pd.to_datetime(df_s['日期'], errors='coerce')
            df_s = df_s.dropna(subset=['日期_dt'])
            if not df_s.empty:
                min_date = df_s['日期_dt'].min().date()
                max_date = df_s['日期_dt'].max().date()
                sel_range = st.date_input(t("📅 选择查询日期区间", "📅 Select Date Range"), value=[st.session_state.camp_start, st.session_state.camp_end], key="sup_sales_date")
                
                if len(sel_range) == 2:
                    s_start, s_end = sel_range
                else:
                    s_start, s_end = sel_range[0], sel_range[0]
                    
                f_s = df_s[(df_s['日期_dt'].dt.date >= s_start) & (df_s['日期_dt'].dt.date <= s_end)]
                f_s = get_f(f_s, q)
                
                if not f_s.empty:
                    f_s['销售数量'] = pd.to_numeric(f_s['销售数量'], errors='coerce').fillna(0)
                    f_s['总营业额'] = pd.to_numeric(f_s['总营业额'], errors='coerce').fillna(0.0)
                    tot_qty = f_s['销售数量'].sum()
                    tot_rev = f_s['总营业额'].sum()
                    
                    c1, c2 = st.columns(2)
                    c1.metric(t("📦 区间总售出件数", "📦 Total Items Sold"), f"{int(tot_qty)}")
                    c2.metric(t("💰 区间总含税营业额", "💰 Total Sales Amount"), f"${tot_rev:.2f}")
                    
                    # 🚀 翻译商品名
                    f_s['商品名称'] = translate_series(f_s['商品名称'])
                    f_s['颜色'] = translate_series(f_s['颜色'])
                    
                    show_cols = ['订单号', '日期', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']
                    df_disp = f_s[show_cols].copy()
                    if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
                    u_col = 'Unit Price' if st.session_state.lang == 'en' else '成交单价'
                    t_col = 'Total Amount' if st.session_state.lang == 'en' else '总营业额'
                    st.dataframe(df_disp.style.format({u_col: '${:.2f}', t_col: '${:.2f}'}), use_container_width=True, hide_index=True)
                else:
                    st.info(t("该区间内无符合条件的记录。", "No records found in this range."))
    
    else:
        st.subheader(t("🛒 智能收银台", "🛒 Smart POS Cashier"))
        pos_col1, pos_col2 = st.columns([1.2, 1.5])
        
        f_opts = get_f(df_stock, "").copy() 
        if not f_opts.empty:
            # 修复 3：强行字符串化，防止 PyArrow 报错
            f_opts['disp_name'] = translate_series(f_opts['商品名称']).astype(str)
            f_opts['disp_color'] = translate_series(f_opts['颜色']).astype(str)
            f_opts['label'] = f_opts['disp_name'] + " (" + f_opts['disp_color'] + ")" 
            
            with pos_col1:
                with st.container(border=True):
                    st.markdown(t("#### 1️⃣ 扫码/点单区", "#### 1️⃣ Scan / Order"))
                    s_l = st.selectbox(t("选择售出商品", "Select Item"), f_opts['label'], key="pos_item")
                    selected_row = f_opts[f_opts['label'] == s_l].iloc[0]
                    base_price = float(pd.to_numeric(selected_row['售卖价格'], errors='coerce') or 0)
                    
                    c_q, c_d = st.columns(2)
                    s_q = c_q.number_input(t("销售数量", "Qty"), min_value=1, value=1, step=1, key="pos_qty")
                    if st.session_state.lang == 'cn':
                        d_opts = {"无折扣 (原价)": 1.0, "95折": 0.95, "9折": 0.90, "85折": 0.85, "8折": 0.80, "75折": 0.75, "7折": 0.70, "5折 (半价)": 0.50}
                    else:
                        d_opts = {"No Discount": 1.0, "5% Off": 0.95, "10% Off": 0.90, "15% Off": 0.85, "20% Off": 0.80, "25% Off": 0.75, "30% Off": 0.70, "50% Off": 0.50}
                    s_discount = c_d.selectbox(t("快捷折扣", "Discount"), list(d_opts.keys()), key="pos_disc")
                    
                    auto_calc_price = base_price * d_opts[s_discount]
                    s_p = st.number_input(t("此单品最终成交价 ($)", "Final Price per item ($)"), value=float(auto_calc_price), format="%.2f", key=f"price_{s_l}_{s_discount}")
                    
                    if st.button(t("➕ 加入当前购物车", "➕ Add to Cart"), use_container_width=True):
                        item_dict = {
                            "real_name": str(selected_row['商品名称']),
                            "real_color": str(selected_row['颜色']),
                            "disp_name": str(selected_row['disp_name']),
                            "disp_color": str(selected_row['disp_color']),
                            "数量": s_q,
                            "单价": s_p,
                            "小计": s_q * s_p
                        }
                        st.session_state.pos_cart.append(item_dict)
                        st.rerun()

            with pos_col2:
                with st.container(border=True):
                    st.markdown(t("#### 2️⃣ 当前购物车", "#### 2️⃣ Current Cart"))
                    if not st.session_state.pos_cart:
                        st.info(t("🛒 购物车空空如也。", "🛒 Cart is empty."))
                    else:
                        cart_df = pd.DataFrame(st.session_state.pos_cart)
                        df_disp = cart_df[['disp_name', 'disp_color', '数量', '单价', '小计']].copy()
                        df_disp.columns = ['商品名称', '颜色', '数量', '单价', '小计']
                        if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
                        u_col = 'Unit Price' if st.session_state.lang == 'en' else '单价'
                        s_col = 'Subtotal' if st.session_state.lang == 'en' else '小计'
                        st.dataframe(df_disp.style.format({u_col: '${:.2f}', s_col: '${:.2f}'}), use_container_width=True, hide_index=True)
                        
                        cart_total_qty = cart_df['数量'].sum()
                        cart_total_amt = cart_df['小计'].sum()
                        
                        st.markdown(f"**🛍️ Total:** `{cart_total_qty}` &nbsp;&nbsp;|&nbsp;&nbsp; **💰 Pay:** ` ${cart_total_amt:.2f}`")
                        
                        co_col1, co_col2 = st.columns([2, 1])
                        s_d = co_col1.date_input(t("交易日期 (可补录)", "Transaction Date"), value=datetime.now(), key="pos_date")
                        
                        if co_col2.button(t("🗑️ 清空购物车", "🗑️ Clear Cart"), use_container_width=True):
                            st.session_state.pos_cart = []
                            st.rerun()
                            
                        if st.button(t("💳 确认结账 (生成流水)", "💳 Checkout"), type="primary", use_container_width=True):
                            fresh = JIT_fetch([STOCK_SHEET, SALES_SHEET])
                            latest_stock = fresh[STOCK_SHEET]
                            latest_sales = fresh[SALES_SHEET]
                            order_id = "ORD-" + datetime.now().strftime("%Y%m%d-%H%M%S")
                            order_date = s_d.strftime("%Y/%m/%d")
                            curr_user = st.session_state.get("current_user", "未知")
                            new_rows = []
                            for item in st.session_state.pos_cart:
                                real_n = item['real_name']
                                real_c = item['real_color']
                                new_rows.append([order_id, order_date, curr_user, real_n, real_c, item['数量'], item['单价'], item['小计']])
                                idx_p = latest_stock[(latest_stock['商品名称'] == real_n) & (latest_stock['颜色'] == real_c)].index
                                if not idx_p.empty:
                                    i_p = idx_p[0]
                                    latest_stock.at[i_p, '货柜数量'] = int(pd.to_numeric(latest_stock.at[i_p, '货柜数量'], errors='coerce') or 0) - item['数量']
                                    latest_stock.at[i_p, '已售出数量'] = int(pd.to_numeric(latest_stock.at[i_p, '已售出数量'], errors='coerce') or 0) + item['数量']
                                    latest_stock.at[i_p, '总库存'] = sum([int(pd.to_numeric(latest_stock.at[i_p, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                            
                            new_sales_df = pd.DataFrame(new_rows, columns=SALES_COLS)
                            latest_sales = pd.concat([new_sales_df, latest_sales], ignore_index=True)
                            save_data(latest_sales, SALES_SHEET) 
                            save_data(latest_stock, STOCK_SHEET) 
                            st.session_state.pos_cart = []
                            st.success(t(f"🎉 结账成功！流水号 {order_id}", f"🎉 Checkout Success! ID: {order_id}"))
                            st.rerun()
                            
        else:
            st.info(t("请先在库存中添加商品。", "Please add items to stock first."))

        st.divider()
        
        with st.expander(t("🚶‍♂️ 录入/修正每日有效客流", "🚶‍♂️ Daily Traffic Log"), expanded=False):
            with st.form("traffic_form"):
                tc1, tc2 = st.columns(2)
                tr_date = tc1.date_input(t("📅 客流日期", "📅 Date"), value=datetime.now())
                tr_num = tc2.number_input(t("👁️ 有效咨询/看货人数", "👁️ Traffic Count"), min_value=0, step=1, value=0)
                if st.form_submit_button(t("💾 保存今日客流数据", "💾 Save Traffic"), type="primary", use_container_width=True):
                    fresh_traffic = JIT_fetch([TRAFFIC_SHEET])[TRAFFIC_SHEET]
                    tr_date_str = tr_date.strftime("%Y/%m/%d")
                    idx = fresh_traffic[fresh_traffic['日期'] == tr_date_str].index
                    if not idx.empty: fresh_traffic.at[idx[0], '有效客流'] = tr_num
                    else: fresh_traffic = pd.concat([pd.DataFrame([[tr_date_str, tr_num]], columns=TRAFFIC_COLS), fresh_traffic], ignore_index=True)
                    save_data(fresh_traffic, TRAFFIC_SHEET)
                    st.success("✅ Saved!")
                    st.rerun()

        with st.expander(t("🔄 客户换货处理 (Exchange)", "🔄 Item Exchange"), expanded=False):
            if not f_opts.empty:
                xc1, xc2 = st.columns(2)
                with xc1:
                    st.markdown(t("### 🔙 退回的商品 (入库)", "### 🔙 Return Item"))
                    ex_ret_l = st.selectbox("1. Return Item", f_opts['label'], key="ex_ret_sku")
                    ret_row = f_opts[f_opts['label'] == ex_ret_l].iloc[0]
                    ret_p = st.number_input("2. Return Value ($)", value=float(pd.to_numeric(ret_row['售卖价格'], errors='coerce') or 0), format="%.2f")
                    ret_dmg = st.checkbox(t("⚠️ 退回商品有瑕疵 (记入坏货库)", "⚠️ Item Damaged"), value=False)
                with xc2:
                    st.markdown(t("### 🆕 换购的商品 (出库)", "### 🆕 New Item"))
                    ex_new_l = st.selectbox("1. New Item", f_opts['label'], key="ex_new_sku")
                    new_row = f_opts[f_opts['label'] == ex_new_l].iloc[0]
                    new_p = st.number_input("2. New Item Price ($)", value=float(pd.to_numeric(new_row['售卖价格'], errors='coerce') or 0), format="%.2f")

                st.markdown("---")
                c_date, c_diff = st.columns(2)
                with c_date: ex_date_input = st.date_input("📅 Date", value=datetime.now(), key="ex_date_input")
                with c_diff:
                    diff = new_p - ret_p
                    if diff > 0: st.warning(t(f"💰 需补差价：${diff:.2f}", f"💰 Customer Pays: ${diff:.2f}"))
                    elif diff < 0: st.success(t(f"💸 需退差价：${abs(diff):.2f}", f"💸 Refund Customer: ${abs(diff):.2f}"))
                    else: st.info(t("🤝 等价交换", "🤝 Even Exchange"))

                if st.button(t("🔄 确认执行换货", "🔄 Confirm Exchange"), type="primary", use_container_width=True):
                    fresh = JIT_fetch([STOCK_SHEET, SALES_SHEET])
                    latest_stock, latest_sales = fresh[STOCK_SHEET], fresh[SALES_SHEET]
                    ex_date, ex_order_id, curr_user = ex_date_input.strftime("%Y/%m/%d"), "EXC-" + datetime.now().strftime("%Y%m%d-%H%M%S"), st.session_state.get("current_user", "Unknown")
                    r_name = t_val(ret_row['disp_name'], 'cn'); r_col = t_val(ret_row['disp_color'], 'cn')
                    n_name = t_val(new_row['disp_name'], 'cn'); n_col = t_val(new_row['disp_color'], 'cn')
                    
                    idx_ret = latest_stock[(latest_stock['商品名称'] == r_name) & (latest_stock['颜色'] == r_col)].index[0]
                    s_ret = pd.DataFrame([[ex_order_id, ex_date, curr_user, latest_stock.at[idx_ret,'商品名称'], latest_stock.at[idx_ret,'颜色'], -1, ret_p, -1 * ret_p]], columns=SALES_COLS)
                    idx_new = latest_stock[(latest_stock['商品名称'] == n_name) & (latest_stock['颜色'] == n_col)].index[0]
                    s_new = pd.DataFrame([[ex_order_id, ex_date, curr_user, latest_stock.at[idx_new,'商品名称'], latest_stock.at[idx_new,'颜色'], 1, new_p, 1 * new_p]], columns=SALES_COLS)
                    latest_sales = pd.concat([s_new, s_ret, latest_sales], ignore_index=True)
                    if ret_dmg: latest_stock.at[idx_ret, '坏货数量'] = int(pd.to_numeric(latest_stock.at[idx_ret, '坏货数量'], errors='coerce') or 0) + 1
                    else:
                        latest_stock.at[idx_ret, '货柜数量'] = int(pd.to_numeric(latest_stock.at[idx_ret, '货柜数量'], errors='coerce') or 0) + 1
                        latest_stock.at[idx_ret, '总库存'] = sum([int(pd.to_numeric(latest_stock.at[idx_ret, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                    latest_stock.at[idx_ret, '已售出数量'] = int(pd.to_numeric(latest_stock.at[idx_ret, '已售出数量'], errors='coerce') or 0) - 1
                    latest_stock.at[idx_new, '货柜数量'] = int(pd.to_numeric(latest_stock.at[idx_new, '货柜数量'], errors='coerce') or 0) - 1
                    latest_stock.at[idx_new, '已售出数量'] = int(pd.to_numeric(latest_stock.at[idx_new, '已售出数量'], errors='coerce') or 0) + 1
                    latest_stock.at[idx_new, '总库存'] = sum([int(pd.to_numeric(latest_stock.at[idx_new, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                    save_data(latest_sales, SALES_SHEET); save_data(latest_stock, STOCK_SHEET); st.rerun()

        st.divider()
        st.markdown(t("### 📝 今日流水 (Logs)", "### 📝 Today's Logs"))
        td = datetime.now().strftime("%Y/%m/%d")
        fsl = df_sales[df_sales['日期']==td].copy()
        if not fsl.empty:
            if is_admin:
                fsl.insert(0, "Sel", False)
                ed = st.data_editor(fsl, hide_index=True)
                if st.button("🔴 Revert Selected"):
                    sel = ed[ed["Sel"]==True]
                    f = JIT_fetch([STOCK_SHEET, SALES_SHEET]); ls, lsal = f[STOCK_SHEET], f[SALES_SHEET]
                    for _, r in sel.iterrows():
                        idx = ls[(ls['商品名称']==r['商品名称']) & (ls['颜色']==r['颜色'])].index[0]
                        ls.at[idx,'货柜数量'] = int(pd.to_numeric(ls.at[idx,'货柜数量'], errors='coerce') or 0) + int(r['销售数量'])
                        ls.at[idx,'已售出数量'] = int(pd.to_numeric(ls.at[idx,'已售出数量'], errors='coerce') or 0) - int(r['销售数量'])
                        ls.at[idx,'总库存'] = sum([int(pd.to_numeric(ls.at[idx,c], errors='coerce') or 0) for c in ['展示数量','货柜数量','储物间数量']])
                        lsal = lsal[~((lsal['订单号']==r['订单号']) & (lsal['商品名称']==r['商品名称']) & (lsal['颜色']==r['颜色']))]
                    save_data(ls, STOCK_SHEET); save_data(lsal, SALES_SHEET); st.rerun()
            else:
                fsl['商品名称'] = translate_series(fsl['商品名称']); fsl['颜色'] = translate_series(fsl['颜色'])
                if st.session_state.lang=='en': fsl.rename(columns=col_map, inplace=True)
                st.dataframe(fsl, hide_index=True)

# ================= 🚀 Tab 3-8: 后台管理层 (Admin) =================
if is_admin:
    with t3:
        st.subheader("📊 财务与客流报表")
        sel_range_t3 = st.date_input("⏳ 选择时间段：", value=[st.session_state.camp_start, st.session_state.camp_end], key="t3_date_picker")
        if len(sel_range_t3) == 2: t3_start, t3_end = sel_range_t3[0], sel_range_t3[1]
        else: t3_start, t3_end = sel_range_t3[0], sel_range_t3[0]

        if not df_sales.empty:
            df_sales['日期_dt'] = pd.to_datetime(df_sales['日期'], errors='coerce')
            df_sales_clean = df_sales.dropna(subset=['日期_dt']).copy()
            if not df_sales_clean.empty:
                f_sales_range = df_sales_clean[(df_sales_clean['日期_dt'] >= pd.Timestamp(t3_start)) & (df_sales_clean['日期_dt'] <= pd.Timestamp(t3_end))].copy()
                f_sales_range['销售数量'] = pd.to_numeric(f_sales_range['销售数量'], errors='coerce').fillna(0)
                f_sales_range['总营业额'] = pd.to_numeric(f_sales_range['总营业额'], errors='coerce').fillna(0.0)
                
                df_stock_calc = df_stock[['商品名称', '颜色', '进价成本']].copy()
                df_stock_calc['进价成本'] = pd.to_numeric(df_stock_calc['进价成本'], errors='coerce').fillna(0.0)
                f_sales_range = f_sales_range.merge(df_stock_calc, on=['商品名称', '颜色'], how='left')
                f_sales_range['具体毛利'] = f_sales_range['总营业额'] - (f_sales_range['销售数量'] * f_sales_range['进价成本'])
                f_sales_range = get_f(f_sales_range, q)
                
                if not f_sales_range.empty:
                    tot_rev = f_sales_range['总营业额'].sum()
                    tot_items = f_sales_range['销售数量'].sum()
                    tot_margin = f_sales_range['具体毛利'].sum()
                    valid_orders = f_sales_range[(~f_sales_range['订单号'].str.contains('历史单', na=False)) & (~f_sales_range['订单号'].str.contains('EXC-', na=False))]
                    order_count = valid_orders['订单号'].nunique()
                    legacy_orders = f_sales_range[f_sales_range['订单号'].str.contains('历史单', na=False)]
                    total_order_count = order_count + len(legacy_orders)
                    
                    df_traffic_clean = df_traffic.copy()
                    if not df_traffic_clean.empty:
                        df_traffic_clean['日期_dt'] = pd.to_datetime(df_traffic_clean['日期'], errors='coerce')
                        f_traffic_range = df_traffic_clean[(df_traffic_clean['日期_dt'] >= pd.Timestamp(t3_start)) & (df_traffic_clean['日期_dt'] <= pd.Timestamp(t3_end))]
                        total_traffic = pd.to_numeric(f_traffic_range['有效客流'], errors='coerce').fillna(0).sum()
                    else: total_traffic = 0
                        
                    conv_rate = (total_order_count / total_traffic * 100) if total_traffic > 0 else 0.0
                    acv = tot_rev / total_order_count if total_order_count > 0 else 0
                    upt = tot_items / total_order_count if total_order_count > 0 else 0
                    
                    period = st.radio("维度", ["Daily", "Weekly", "Monthly"], horizontal=True)
                    if "Daily" in period: f_sales_range['周期'] = f_sales_range['日期_dt'].dt.strftime('%Y/%m/%d')
                    elif "Weekly" in period: f_sales_range['周期'] = (f_sales_range['日期_dt'] - pd.to_timedelta(f_sales_range['日期_dt'].dt.dayofweek, unit='D')).dt.strftime('Week of %b %d')
                    else: f_sales_range['周期'] = f_sales_range['日期_dt'].dt.strftime('%Y/%m')
                    
                    summ = f_sales_range.groupby(['周期', '商品名称', '颜色']).agg({'销售数量':'sum', '总营业额':'sum', '具体毛利':'sum'}).reset_index()
                    delta_days = (t3_end - t3_start).days + 1
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("👁️ 有效总客流", f"{int(total_traffic)}")
                    m2.metric("💳 交易单数", f"{total_order_count}")
                    m3.metric("🔄 购买转化率", f"{conv_rate:.1f}%")
                    st.divider()
                    
                    m4, m5, m6 = st.columns(3)
                    m4.metric("💰 总营业额", f"${tot_rev:.2f}")
                    m5.metric("🛒 平均客单价 (ACV)", f"${acv:.2f}")
                    m6.metric("🛍️ 连带率 (UPT)", f"{upt:.2f}")
                    st.divider()
                    
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("具体毛利", f"${tot_margin:.2f}")
                    c2.metric("总售出件数", f"{int(tot_items)}")
                    avg_m = tot_margin / tot_rev * 100 if tot_rev > 0 else 0
                    c3.metric("平均毛利率", f"{avg_m:.1f}%")
                    avg_daily = tot_rev / delta_days if delta_days > 0 else 0
                    c4.metric("日均坪效 (每日营收)", f"${avg_daily:.2f}")
                    
                    chart_data_t3 = summ.groupby('周期')[['总营业额', '具体毛利']].sum().sort_index(ascending=True)
                    st.bar_chart(chart_data_t3, use_container_width=True)

    with t4:
        st.subheader("👥 员工档案与考勤")
        with st.form("new_emp"):
            c1, c2 = st.columns(2)
            nm = c1.text_input("人员姓名")
            rl = c2.selectbox("职位", ["店长", "全职店员", "兼职店员", "实习生", "合作厂商", "其他"])
            c3, c4, c5 = st.columns(3)
            wg = c3.number_input("时薪 ($/h)", value=12.0)
            ph = c4.text_input("联系方式")
            dt = c5.date_input("入职日期", value=datetime.now())
            if st.form_submit_button("Add") and nm:
                f = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                nl = pd.DataFrame([[nm, rl, wg, ph, dt.strftime("%Y/%m/%d"), "", "在职"]], columns=EMP_COLS)
                save_data(pd.concat([f, nl], ignore_index=True), EMP_SHEET); st.rerun()
                
        f_employee = get_f(df_employee, q) 
        if not f_employee.empty:
            v_emp = f_employee.copy()
            v_emp.insert(0, "选择", False)
            v_emp['时薪'] = pd.to_numeric(v_emp['时薪'], errors='coerce').fillna(0.0)
            styled_emp = v_emp.style.format({'时薪': '${:.2f}'})
            edited_emp = st.data_editor(styled_emp, column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, disabled=['员工姓名', '入职日期'], use_container_width=True, hide_index=True)
            if st.button("💾 手动保存员工修改"):
                for idx, row in edited_emp.iterrows():
                    fresh_emp = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                    for col in EMP_COLS: fresh_emp.at[idx, col] = row[col]
                    save_data(fresh_emp, EMP_SHEET)
                st.success("✅ Saved!")
        
        st.divider()
        st.subheader("⏰ 考勤打卡")
        with st.form("add_attendance"):
            c1, c2 = st.columns(2)
            att_name = c1.selectbox("选择员工", df_employee['员工姓名'].astype(str).tolist())
            att_date = c2.date_input("工作日期", value=datetime.now())
            c3, c4 = st.columns(2)
            att_start = c3.time_input("上班时间", value=time(10, 0))
            att_end = c4.time_input("下班时间", value=time(18, 0))
            if st.form_submit_button("确认记录考勤"):
                fresh_att = JIT_fetch([ATT_SHEET])[ATT_SHEET]
                dt_start = datetime.combine(att_date, att_start)
                dt_end = datetime.combine(att_date, att_end)
                if dt_end < dt_start: dt_end += timedelta(days=1)
                duration_hours = (dt_end - dt_start).total_seconds() / 3600.0
                wage_val = df_employee[df_employee['员工姓名'] == att_name]['时薪'].iloc[0]
                total_wage = duration_hours * float(pd.to_numeric(wage_val, errors='coerce') or 0.0)
                new_att = pd.DataFrame([[att_name, att_date.strftime("%Y/%m/%d"), att_start.strftime("%H:%M"), att_end.strftime("%H:%M"), round(duration_hours, 2), round(total_wage, 2)]], columns=ATT_COLS)
                save_data(pd.concat([new_att, fresh_att], ignore_index=True), ATT_SHEET); st.rerun()

    with t5:
        st.subheader("💎 真实净利润核算 (Net Profit P&L)")
        st.info("9% GST Stripped Logic applied.")
        sel_range_t5 = st.date_input("⏳ 分析区间：", value=[st.session_state.camp_start, st.session_state.camp_end], key="t5_date_picker")
        if len(sel_range_t5) == 2: t5_start, t5_end = sel_range_t5[0], sel_range_t5[1]
        else: t5_start, t5_end = sel_range_t5[0], sel_range_t5[0]
        if not df_sales.empty:
            df_s_np = df_sales.copy()
            df_s_np['日期_dt'] = pd.to_datetime(df_s_np['日期'], errors='coerce')
            df_s_np = df_s_np.dropna(subset=['日期_dt'])
            df_a_np = df_attendance.copy()
            if not df_a_np.empty:
                df_a_np['日期_dt'] = pd.to_datetime(df_a_np['日期'], errors='coerce')
                df_a_np = df_a_np.dropna(subset=['日期_dt'])
            else: df_a_np['日期_dt'] = pd.Series(dtype='datetime64[ns]')

            if not df_s_np.empty:
                fs = df_s_np[(df_s_np['日期_dt'] >= pd.Timestamp(t5_start)) & (df_s_np['日期_dt'] <= pd.Timestamp(t5_end))].copy()
                fa = df_a_np[(df_a_np['日期_dt'] >= pd.Timestamp(t5_start)) & (df_a_np['日期_dt'] <= pd.Timestamp(t5_end))].copy()
                fs['销售数量'] = pd.to_numeric(fs['销售数量'], errors='coerce').fillna(0)
                fs['总营业额'] = pd.to_numeric(fs['总营业额'], errors='coerce').fillna(0.0)
                df_stock_cost = df_stock[['商品名称', '颜色', '进价成本']].copy()
                df_stock_cost['进价成本'] = pd.to_numeric(df_stock_cost['进价成本'], errors='coerce').fillna(0.0)
                fs = fs.merge(df_stock_cost, on=['商品名称', '颜色'], how='left')
                fs['Cost'] = fs['销售数量'] * fs['进价成本']
                fs['日期_str'] = fs['日期_dt'].dt.strftime('%Y/%m/%d')
                daily_sales = fs.groupby('日期_str').agg({'总营业额': 'sum', 'Cost': 'sum'}).reset_index().rename(columns={'日期_str': '日期'})

                if not fa.empty:
                    fa['核算薪资'] = pd.to_numeric(fa['核算薪资'], errors='coerce').fillna(0.0)
                    fa['日期_str'] = fa['日期_dt'].dt.strftime('%Y/%m/%d')
                    daily_att = fa.groupby('日期_str').agg({'核算薪资': 'sum'}).reset_index().rename(columns={'日期_str': '日期', '核算薪资': 'Wage'})
                else: daily_att = pd.DataFrame(columns=['日期', 'Wage'])

                daily_np = pd.merge(daily_sales, daily_att, on='日期', how='outer').fillna(0.0).sort_values('日期', ascending=False)
                daily_np['Net_Rev'] = daily_np['总营业额'] / 1.09
                daily_np['GST'] = daily_np['总营业额'] - daily_np['Net_Rev']
                daily_np['Comm(36%)'] = daily_np['Net_Rev'] * 0.36
                daily_np['Actual_Recv'] = daily_np['Net_Rev'] - daily_np['Comm(36%)']
                daily_np['Gross_Profit'] = daily_np['Actual_Recv'] - daily_np['Cost']
                daily_np['Net_Profit'] = daily_np['Gross_Profit'] - daily_np['Wage']
                
                tot_gross = daily_np['总营业额'].sum()
                tot_net = daily_np['Net_Profit'].sum()
                pct_net = (tot_net / tot_gross * 100) if tot_gross > 0 else 0
                
                m1, m2 = st.columns(2)
                m1.metric("💰 选中期间总营业额", f"${tot_gross:.2f}")
                m2.metric("💎 选中期间纯利润", f"${tot_net:.2f}", delta=f"含税净利率: {pct_net:.1f}%")
                st.dataframe(daily_np.style.format({'总营业额': '${:.2f}', 'Net_Rev': '${:.2f}', 'GST': '${:.2f}', 'Comm(36%)': '${:.2f}', 'Actual_Recv': '${:.2f}', 'Cost': '${:.2f}', 'Wage': '${:.2f}', 'Gross_Profit': '${:.2f}', 'Net_Profit': '${:.2f}'}), use_container_width=True)

    with t6:
        st.subheader("🤝 B2B 订单管理")
        ed_b2b = st.data_editor(df_b2b, num_rows="dynamic", use_container_width=True, hide_index=True)
        if st.button("💾 Save B2B"): save_data(ed_b2b, B2B_SHEET); st.rerun()
        
    with t7:
        st.subheader("🗣️ 客户反馈追踪")
        ed_fb = st.data_editor(df_feedback, num_rows="dynamic", use_container_width=True, hide_index=True)
        if st.button("💾 Save Feedback"): save_data(ed_fb, FEEDBACK_SHEET); st.rerun()
        
    with t8:
        st.subheader(f"📈 选品战略罗盘 (锁定档期: {st.session_state.camp_name})")
        if not df_sales.empty and not df_stock.empty:
            df_s_bi = df_sales.copy()
            df_s_bi['日期_dt'] = pd.to_datetime(df_s_bi['日期'], errors='coerce')
            df_s_bi = df_s_bi[(df_s_bi['日期_dt'] >= pd.Timestamp(st.session_state.camp_start)) & (df_s_bi['日期_dt'] <= pd.Timestamp(st.session_state.camp_end))]
            df_s_bi['销售数量'] = pd.to_numeric(df_s_bi['销售数量'], errors='coerce').fillna(0)
            df_s_bi['总营业额'] = pd.to_numeric(df_s_bi['总营业额'], errors='coerce').fillna(0.0)
            bi_sales = df_s_bi.groupby(['商品名称', '颜色']).agg({'销售数量': 'sum', '总营业额': 'sum'}).reset_index()

            df_stk_bi = df_stock[['商品名称', '颜色', '进价成本', '总库存']].copy()
            df_stk_bi['进价成本'] = pd.to_numeric(df_stk_bi['进价成本'], errors='coerce').fillna(0.0)
            df_stk_bi['总库存'] = pd.to_numeric(df_stk_bi['总库存'], errors='coerce').fillna(0)

            bi_df = pd.merge(df_stk_bi, bi_sales, on=['商品名称', '颜色'], how='left').fillna(0)
            
            today = datetime.now().date()
            if today < st.session_state.camp_start: days_in_period = 1
            else: days_in_period = max((min(today, st.session_state.camp_end) - st.session_state.camp_start).days + 1, 1)
            
            bi_df['日均动销率'] = bi_df['销售数量'] / days_in_period
            bi_df['总进价成本'] = bi_df['销售数量'] * bi_df['进价成本']
            bi_df['具体毛利'] = bi_df['总营业额'] - bi_df['总进价成本']
            bi_df['毛利率(%)'] = ((bi_df['具体毛利'] / bi_df['总营业额']) * 100).fillna(0.0)

            def calc_cover(row): return int(row['总库存'] / row['日均动销率']) if row['日均动销率'] > 0 else 999 
            bi_df['可售天数'] = bi_df.apply(calc_cover, axis=1)
            bi_df['压货金额'] = bi_df['总库存'] * bi_df['进价成本']
            
            def get_tag(row):
                v, m, s, c = row['日均动销率'], row['毛利率(%)'], row['总库存'], row['可售天数']
                if s <= 2 and row['销售数量'] > 0 and c <= 7: return "🚨 爆款流血断货"
                elif v < 0.167 and c > 30 and s > 0: return "📦 积压套牢"
                elif v >= 0.33 and m >= 50.0: return "⭐ 绝对明星"
                elif v >= 0.33 and m < 50.0: return "🧲 引流款"
                elif v < 0.167 and m >= 50.0: return "🐢 利润陷阱"
                elif v < 0.167 and m < 50.0: return "☠️ 斩仓废柴"
                else: return "🚶 常规款"

            bi_df['诊断标签'] = bi_df.apply(get_tag, axis=1)
            bi_df['商品规格'] = translate_series(bi_df['商品名称']).astype(str) + " (" + translate_series(bi_df['颜色']).astype(str) + ")"
            bi_df['气泡视觉大小'] = bi_df['压货金额'].apply(lambda x: max(float(x), 10))
            
            fig = px.scatter(bi_df, x='日均动销率', y='毛利率(%)', color='诊断标签', size='气泡视觉大小', hover_name='商品规格', size_max=45, height=550, template="plotly_white")
            fig.add_vline(x=0.33, line_width=2, line_dash="dash", line_color="gray", annotation_text=" 达标销量(0.33件/天)")
            fig.add_hline(y=50.0, line_width=2, line_dash="dash", line_color="gray", annotation_text=" 达标毛利(50%)")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(bi_df[['商品规格', '诊断标签', '日均动销率', '毛利率(%)', '总库存', '压货金额']].sort_values('日均动销率', ascending=False), use_container_width=True, hide_index=True)

# ================= 🚀 Tab 3-4: 厂商对账层 (Supplier) =================
if is_sup:
    with tabs[2]:
        st.subheader("📦 Inbound Records")
        dr = df_restock.copy(); dr['dt'] = pd.to_datetime(dr['记录日期'], errors='coerce')
        fr = dr[(dr['dt'].dt.date>=st.session_state.camp_start) & (dr['dt'].dt.date<=st.session_state.camp_end)].copy()
        if not fr.empty:
            fr['操作类型'] = translate_series(fr['操作类型'])
            avail_ops = fr['操作类型'].unique().tolist()
            # 修复 2：防止 multiselect 空集报错
            safe_defs = [op for op in [t_val("入库", "en"), t_val("初始建档", "en"), "入库", "初始建档"] if op in avail_ops]
            
            type_filter = st.multiselect("Filter Operation", options=avail_ops, default=safe_defs)
            if type_filter:
                fr = fr[fr['操作类型'].isin(type_filter)]
                fr['商品名称'] = translate_series(fr['商品名称']); fr['颜色'] = translate_series(fr['颜色'])
                df_disp = fr[['记录日期','操作类型','商品名称','颜色','变动数量','备注']].copy()
                if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
                st.dataframe(df_disp, hide_index=True, use_container_width=True)
            else: st.info("Please select an operation type.")
        else: st.info("No records.")
        
    with tabs[3]:
        st.subheader("🤝 B2B Orders (Profit Masked)")
        db = df_b2b.copy(); db['dt'] = pd.to_datetime(db['创建日期'], errors='coerce')
        fb = db[(db['dt'].dt.date>=st.session_state.camp_start) & (db['dt'].dt.date<=st.session_state.camp_end)].copy()
        if not fb.empty:
            fb['商品名称'] = translate_series(fb['商品名称']); fb['颜色'] = translate_series(fb['颜色']); fb['订单状态'] = translate_series(fb['订单状态'])
            df_disp = fb[['创建日期','客户名称','商品名称','颜色','采购数量','总计应收','已收定金','订单状态']].copy()
            if st.session_state.lang=='en': df_disp.rename(columns=col_map, inplace=True)
            st.dataframe(df_disp, hide_index=True, use_container_width=True)
        else: st.info("No records.")
