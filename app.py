import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import gspread 
from gspread.exceptions import WorksheetNotFound
import json
import plotly.express as px

# ================= 1. 基础配置与数据库 =================
st.set_page_config(page_title="Taka 零售终端系统", layout="wide")

try:
    key_dict = json.loads(st.secrets["google_key"])
    gc = gspread.service_account_from_dict(key_dict)
    sh = gc.open_by_url(st.secrets["sheet_url"]) 
except Exception as e:
    st.error(f"🔴 数据库连接失败! Error: {e}")
    st.stop()

# ================= 2. 全局常量与表名 =================
STOCK_SHEET, SALES_SHEET, EMP_SHEET = "Stock", "Sales", "Employee"
ATT_SHEET, B2B_SHEET, FEEDBACK_SHEET = "Attendance", "B2B_Orders", "Feedback"
RESTOCK_SHEET, TRAFFIC_SHEET, CAMP_SHEET = "Restock_Log", "Traffic_Log", "Campaigns"

STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '应收到数量', '展示数量', '货柜数量', '储物间数量', '坏货数量', '已售出数量', '总库存']
SALES_COLS = ['订单号', '日期', '收银员', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']
EMP_COLS = ['员工姓名', '职位', '时薪', '联系方式', '入职日期', '登录密码', '状态']
ATT_COLS = ['员工姓名', '日期', '开始时间', '结束时间', '工作时长', '核算薪资']
B2B_COLS = ['创建日期', '客户名称', '商品名称', '颜色', '采购数量', 'B2B单价', '总计应收', '货物成本', '物流成本', '关税', '已收定金', '待收尾款', '约定交期', '订单状态', '备注']
FEEDBACK_COLS = ['反馈日期', '商品名称', '客户画像', '反馈类型', '详细原话', '跟进状态']
RESTOCK_COLS = ['记录日期', '操作类型', '商品名称', '颜色', '变动数量', '库位详情', '单件成本', '备注']
TRAFFIC_COLS = ['日期', '有效客流']
CAMP_COLS = ['档期名称', '开始日期', '结束日期']

all_sheets = [STOCK_SHEET, SALES_SHEET, EMP_SHEET, ATT_SHEET, B2B_SHEET, FEEDBACK_SHEET, RESTOCK_SHEET, TRAFFIC_SHEET, CAMP_SHEET]

if "sheet_versions" not in st.session_state: st.session_state.sheet_versions = {s: 0 for s in all_sheets}
if "pos_cart" not in st.session_state: st.session_state.pos_cart = []

# ================= 3. 数据层核心引擎 =================
@st.cache_data(ttl=300, show_spinner=False)
def load_raw_data(sheet_name, version):
    try:
        records = sh.worksheet(sheet_name).get_all_records()
        return pd.DataFrame(records) if records else pd.DataFrame()
    except Exception: return pd.DataFrame()

def load_data(sheet_name, columns):
    ver = st.session_state.sheet_versions.get(sheet_name, 0)
    df = load_raw_data(sheet_name, ver)
    if df.empty: df = pd.DataFrame(columns=columns)
    for col in columns:
        if col not in df.columns: df[col] = "" 
    return df[columns]

def save_data(df, sheet_name):
    try: ws = sh.worksheet(sheet_name)
    except WorksheetNotFound: ws = sh.add_worksheet(title=sheet_name, rows="1000", cols="20")
    ws.clear() 
    df_safe = df.fillna("").astype(str)
    ws.update(values=[df_safe.columns.values.tolist()] + df_safe.values.tolist(), range_name='A1')
    st.session_state.sheet_versions[sheet_name] = st.session_state.sheet_versions.get(sheet_name, 0) + 1

def clean_date_col(df, col_name):
    if not df.empty and col_name in df.columns: df[col_name] = pd.to_datetime(df[col_name], errors='coerce').dt.strftime('%Y/%m/%d').fillna('')
    return df

def JIT_fetch(sheets_to_fetch):
    st.cache_data.clear() 
    res = {}
    if STOCK_SHEET in sheets_to_fetch: res[STOCK_SHEET] = load_data(STOCK_SHEET, STOCK_COLS)
    if SALES_SHEET in sheets_to_fetch: 
        df = clean_date_col(load_data(SALES_SHEET, SALES_COLS), '日期')
        if not df.empty: df['订单号'] = df['订单号'].fillna('').astype(str).replace(['0','','nan'], '历史单')
        res[SALES_SHEET] = df
    if RESTOCK_SHEET in sheets_to_fetch: res[RESTOCK_SHEET] = clean_date_col(load_data(RESTOCK_SHEET, RESTOCK_COLS), '记录日期')
    if B2B_SHEET in sheets_to_fetch: res[B2B_SHEET] = clean_date_col(clean_date_col(load_data(B2B_SHEET, B2B_COLS), '创建日期'), '约定交期')
    if FEEDBACK_SHEET in sheets_to_fetch: res[FEEDBACK_SHEET] = clean_date_col(load_data(FEEDBACK_SHEET, FEEDBACK_COLS), '反馈日期')
    if EMP_SHEET in sheets_to_fetch: res[EMP_SHEET] = clean_date_col(load_data(EMP_SHEET, EMP_COLS), '入职日期')
    if ATT_SHEET in sheets_to_fetch: res[ATT_SHEET] = clean_date_col(load_data(ATT_SHEET, ATT_COLS), '日期')
    if TRAFFIC_SHEET in sheets_to_fetch: res[TRAFFIC_SHEET] = clean_date_col(load_data(TRAFFIC_SHEET, TRAFFIC_COLS), '日期')
    return res

@st.cache_data(show_spinner=False)
def convert_df_to_csv(df): return df.to_csv(index=False).encode('utf-8-sig')

df_stock = load_data(STOCK_SHEET, STOCK_COLS)
df_sales = clean_date_col(load_data(SALES_SHEET, SALES_COLS), '日期')
if not df_sales.empty: df_sales['订单号'] = df_sales['订单号'].fillna('').astype(str).replace(['0','','nan'], '历史单')
df_employee = clean_date_col(load_data(EMP_SHEET, EMP_COLS), '入职日期')
df_attendance = clean_date_col(load_data(ATT_SHEET, ATT_COLS), '日期') 
df_b2b = clean_date_col(clean_date_col(load_data(B2B_SHEET, B2B_COLS), '创建日期'), '约定交期')
df_feedback = clean_date_col(load_data(FEEDBACK_SHEET, FEEDBACK_COLS), '反馈日期')
df_restock = clean_date_col(load_data(RESTOCK_SHEET, RESTOCK_COLS), '记录日期')
df_traffic = clean_date_col(load_data(TRAFFIC_SHEET, TRAFFIC_COLS), '日期')
df_camp = clean_date_col(clean_date_col(load_data(CAMP_SHEET, CAMP_COLS), '开始日期'), '结束日期')

if "reset_keys" not in st.session_state:
    st.session_state.reset_keys = {"stock":0, "sales":0, "emp":0, "att":0, "b2b":0, "fb":0}

# ================= 4. 门禁与侧边栏 =================
if "role" not in st.session_state:
    qr, qu = st.query_params.get("role"), st.query_params.get("user")
    if qr == "admin": st.session_state.role, st.session_state.current_user = "admin", "店长"
    elif qr in ["employee", "supplier"] and qu: st.session_state.role, st.session_state.current_user = qr, qu
    else: st.session_state.role = st.session_state.current_user = None

if "camp_start" not in st.session_state: st.session_state.camp_start = datetime(2026, 3, 26).date()
if "camp_end" not in st.session_state: st.session_state.camp_end = datetime.now().date()
if "camp_name" not in st.session_state: st.session_state.camp_name = "默认全局"

with st.sidebar:
    st.header("🔐 系统门禁")
    if st.session_state.role is not None:
        ue = "👑" if st.session_state.role == "admin" else ("🏭" if st.session_state.role == "supplier" else "🧑‍💼")
        st.success(f"{ue} 欢迎回来：{st.session_state.current_user}")
        if st.button("🚪 退出系统 (交接班)", use_container_width=True):
            st.session_state.role = st.session_state.current_user = None; st.query_params.clear(); st.rerun()
            
        if st.session_state.role == "admin":
            st.divider()
            st.header("🎯 全局时间控制器")
            camp_opts = df_camp['档期名称'].dropna().unique().tolist() if not df_camp.empty else []
            sel_camp = st.selectbox("📌 预设档期", ["手动自定义区间"] + camp_opts, index=0)
            c1, c2 = st.columns(2)
            ms = c1.date_input("开始日期", value=st.session_state.camp_start)
            me = c2.date_input("结束日期", value=st.session_state.camp_end)
            if st.button("🚀 应用此全局时间", type="primary", use_container_width=True):
                if sel_camp != "手动自定义区间" and not df_camp.empty:
                    row = df_camp[df_camp['档期名称'] == sel_camp].iloc[0]
                    try:
                        st.session_state.camp_start, st.session_state.camp_end, st.session_state.camp_name = pd.to_datetime(row['开始日期']).date(), pd.to_datetime(row['结束日期']).date(), sel_camp
                    except: pass
                else: st.session_state.camp_start, st.session_state.camp_end, st.session_state.camp_name = ms, me, "手动自定义区间"
                st.rerun()
            st.success(f"**已锁定:** `{st.session_state.camp_start}` 至 `{st.session_state.camp_end}`")
                
            with st.expander("⚙️ 自建预设档期", expanded=False):
                v_camp = df_camp.copy() if not df_camp.empty else pd.DataFrame(columns=CAMP_COLS)
                ed_camp = st.data_editor(v_camp, num_rows="dynamic", use_container_width=True) # 纯文本防止出错
                if st.button("💾 保存档期名录", type="primary", use_container_width=True):
                    ed_camp = ed_camp[ed_camp['档期名称'].fillna('').astype(str).str.strip() != '']
                    save_data(ed_camp, CAMP_SHEET); st.success("✅ 档期已更新！"); st.rerun()
            
            st.divider()
            st.header("🛠️ 核心管理")
            with st.expander("➕ 新增产品建档"):
                with st.form("new_sku"):
                    nn, nc = st.text_input("产品名称"), st.text_input("颜色")
                    cc1, cc2, cc3 = st.columns(3)
                    n_cost, n_price, n_expect = cc1.number_input("进价", format="%.2f"), cc2.number_input("售价", format="%.2f"), cc3.number_input("应收")
                    i1, i2, i3, i4 = st.columns(4)
                    n_disp, n_shelf, n_stor, n_dmg = i1.number_input("展示"), i2.number_input("货柜"), i3.number_input("储物"), i4.number_input("坏货")
                    if st.form_submit_button("确认建档"):
                        if nn and nc:
                            f = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET]); ls, lr = f[STOCK_SHEET], f[RESTOCK_SHEET]
                            tot = n_disp + n_shelf + n_stor 
                            nr = pd.DataFrame([[nn, nc, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, n_dmg, 0, tot]], columns=STOCK_COLS)
                            ls = pd.concat([ls, nr], ignore_index=True)
                            if tot > 0 or n_dmg > 0:
                                nl = pd.DataFrame([[datetime.now().strftime("%Y/%m/%d"), "初始建档", nn, nc, tot+n_dmg, "多库位", n_cost, "系统建档"]], columns=RESTOCK_COLS)
                                lr = pd.concat([nl, lr], ignore_index=True); save_data(lr, RESTOCK_SHEET)
                            save_data(ls, STOCK_SHEET); st.success("✅ 建档成功！"); st.rerun()
    else:
        log_type = st.radio("请选择您的身份", ["🧑‍💼 店员/厂商", "👑 店长"], horizontal=True)
        if log_type == "👑 店长":
            if st.button("🔓 登录后台", use_container_width=True) if st.text_input("输入授权密码", type="password") == manager_password else False:
                st.session_state.role, st.session_state.current_user = "admin", "店长"; st.query_params["role"] = "admin"; st.rerun()
        else:
            if df_employee.empty: st.warning("⚠️ 暂无人员档案。")
            else:
                act = df_employee[df_employee['状态'] != '离职']['员工姓名'].tolist()
                if not act: st.warning("⚠️ 无在职人员。")
                else:
                    emp_sel = st.selectbox("选择您的名字", act)
                    emp_row = df_employee[df_employee['员工姓名'] == emp_sel].iloc[0]
                    emp_pwd = str(emp_row['登录密码']).strip()
                    assign_role = "supplier" if str(emp_row.get('职位', '')).strip() == '合作厂商' else "employee"
                    
                    if emp_pwd == "":
                        st.info("🌟 首次登录请设置 PIN 码。")
                        new_pwd = st.text_input("设置密码", type="password")
                        if st.button("💾 保存并进入", use_container_width=True):
                            if new_pwd.strip() == "": st.warning("密码不能为空！")
                            else:
                                fe = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                                e_idx = fe[fe['员工姓名'].astype(str).str.strip() == str(emp_sel).strip()].index
                                if not e_idx.empty:
                                    fe.at[e_idx[0], '登录密码'] = new_pwd; save_data(fe, EMP_SHEET)
                                    st.session_state.role, st.session_state.current_user = assign_role, emp_sel
                                    st.query_params["role"], st.query_params["user"] = assign_role, emp_sel; st.rerun()
                    else:
                        if st.button("🔑 打卡/登录", use_container_width=True) if st.text_input("输入 PIN 码", type="password") == emp_pwd else False:
                            st.session_state.role, st.session_state.current_user = assign_role, emp_sel
                            st.query_params["role"], st.query_params["user"] = assign_role, emp_sel; st.rerun()

if st.session_state.role is None:
    st.title("🏙️ Takashimaya 零售管理系统")
    st.info("👈 请在左侧选择您的身份并完成登录。")
    st.stop()  

# ================= 5. 主界面头部 =================
st.title("🏙️ Takashimaya 零售管理系统 (云端同步版)")
q = st.text_input("🔍 全局筛查 (输入单号/客户/商品，过滤所有看板)...")

def get_f(df, kw):
    if kw and not df.empty:
        m = pd.Series(False, index=df.index)
        for c in df.columns: m = m | df[c].fillna('').astype(str).str.contains(kw, case=False, regex=False)
        return df[m]
    return df

is_admin, is_supplier, is_employee = st.session_state.role == "admin", st.session_state.role == "supplier", st.session_state.role == "employee"

# 页面 Tabs 分发
if is_admin: t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs(["📊 库存", "💰 销售", "📈 毛利", "👥 考勤", "💎 净利润", "🤝 B2B订单", "🗣️ 客户反馈", "🧠 战略(BI)"])
elif is_supplier: t1, t2, t3, t4 = st.tabs(["📊 实时库存快照", "💰 销售报表对账", "📦 进货对账 (ERP流水)", "🤝 B2B订单对账"])
else: t1, t2, t3 = st.tabs(["📊 实时库存查询", "🛒 智能POS收银台", "⏰ 考勤打卡"])

# =========================================================================================
# ============================ 🚀 公共核心组件：防止功能丢失 ================================
# =========================================================================================
# 5.1 公共：库存底单展示与修改
def render_inventory_snapshot(role):
    st.subheader("📊 实时库存与期间动销快照")
    
    t1_s, t1_e = st.session_state.camp_start, st.session_state.camp_end
    st.info(f"📅 期间售出已随全局锁定在：**{t1_s}** 至 **{t1_e}**")
        
    fs = get_f(df_stock, q)
    if not fs.empty:
        vd = fs.copy()
        ps = pd.DataFrame()
        if not df_sales.empty:
            ds1 = df_sales.copy(); ds1['dt'] = pd.to_datetime(ds1['日期'], errors='coerce')
            fs1 = ds1[(ds1['dt'] >= pd.Timestamp(t1_s)) & (ds1['dt'] <= pd.Timestamp(t1_e))]
            if not fs1.empty:
                fs1['销售数量'] = pd.to_numeric(fs1['销售数量'], errors='coerce').fillna(0)
                ps = fs1.groupby(['商品名称', '颜色'])['销售数量'].sum().reset_index().rename(columns={'销售数量': '期间售出'})
        
        vd = vd.merge(ps, on=['商品名称', '颜色'], how='left') if not ps.empty else vd.assign(期间售出=0)
        vd['期间售出'] = vd['期间售出'].fillna(0).astype(int)
        
        for c in ['应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '期间售出']: 
            if c in vd.columns: vd[c] = pd.to_numeric(vd[c], errors='coerce').fillna(0).astype(int)
                
        vd['进价成本'], vd['售卖价格'] = pd.to_numeric(vd['进价成本'], errors='coerce').fillna(0.0), pd.to_numeric(vd['售卖价格'], errors='coerce').fillna(0.0)
        vd['单品毛利率'] = vd.apply(lambda r: f"{((r['售卖价格'] - r['进价成本']) / r['售卖价格'] * 100):.1f}%" if r['售卖价格'] > 0 else "0.0%", axis=1)
        vd.insert(0, "选择", False)
        
        if role in ['supplier', 'employee']:
            dc = ['商品名称', '颜色', '期间售出', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '售卖价格'] if role == 'supplier' else ['商品名称', '颜色', '期间售出', '总库存', '展示数量', '货柜数量', '储物间数量', '售卖价格']
            st.dataframe(vd[dc].style.format({'售卖价格': '${:.2f}'}), use_container_width=True, hide_index=True)
            
        elif role == 'admin':
            dc = ['选择', '商品名称', '颜色', '期间售出', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '售卖价格', '进价成本', '单品毛利率']
            dd = vd[dc].copy()
            def hl(row):
                try: return ['background-color: #ffe6e6; color: #cc0000; font-weight: bold;'] * len(row) if int(row['总库存']) <= 2 else [''] * len(row)
                except: return [''] * len(row)
                
            sd = dd.style.format({'进价成本': '${:.2f}', '售卖价格': '${:.2f}'}).apply(hl, axis=1)
            dis = [c for c in dd.columns if c != "选择"]
            
            ed = st.data_editor(sd, column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, disabled=dis, use_container_width=True, hide_index=True, key=f"s_ed_{st.session_state.reset_keys['stock']}")
            sel = ed[ed["选择"] == True] if "选择" in ed.columns else pd.DataFrame()
            
            if len(sel) == 1:
                st.markdown("### ⚙️ SKU 档案修改机")
                rn, rc = str(sel.iloc[0]['商品名称']).strip(), str(sel.iloc[0]['颜色']).strip()
                v_c, v_p = str(sel.iloc[0]['进价成本']).replace('$','').replace(',',''), str(sel.iloc[0]['售卖价格']).replace('$','').replace(',','')
                with st.form("e_base"):
                    ec1, ec2 = st.columns(2)
                    en, ec = ec1.text_input("Name", value=rn), ec2.text_input("Color", value=rc)
                    e4, e5 = st.columns(2)
                    ecst, eprc = e4.number_input("Cost ($)", value=float(v_c) if v_c else 0.0, format="%.2f"), e5.number_input("Price ($)", value=float(v_p) if v_p else 0.0, format="%.2f")
                    if st.form_submit_button("💾 Save Changes", type="primary"):
                        f = JIT_fetch([STOCK_SHEET, SALES_SHEET, B2B_SHEET, RESTOCK_SHEET])
                        ls, lsal, lb, lr = f[STOCK_SHEET], f[SALES_SHEET], f[B2B_SHEET], f[RESTOCK_SHEET]
                        m = ls[(ls['商品名称'].astype(str).str.strip() == rn) & (ls['颜色'].astype(str).str.strip() == rc)].index
                        if not m.empty:
                            ls.loc[m[0], ['商品名称', '颜色', '进价成本', '售卖价格']] = [en, ec, ecst, eprc]
                            if en != rn or ec != rc:
                                if not lsal.empty: lsal.loc[(lsal['商品名称'].astype(str).str.strip() == rn) & (lsal['颜色'].astype(str).str.strip() == rc), ['商品名称', '颜色']] = [en, ec]
                                if not lr.empty: lr.loc[(lr['商品名称'].astype(str).str.strip() == rn) & (lr['颜色'].astype(str).str.strip() == rc), ['商品名称', '颜色']] = [en, ec]
                                if not lb.empty: lb.loc[(lb['商品名称'].astype(str).str.strip() == rn) & (lb['颜色'].astype(str).str.strip() == rc), ['商品名称', '颜色']] = [en, ec]
                                save_data(lsal, SALES_SHEET); save_data(lr, RESTOCK_SHEET); save_data(lb, B2B_SHEET)
                            save_data(ls, STOCK_SHEET); st.session_state.reset_keys['stock'] += 1; st.success("✅ Updated!"); st.rerun()
                        else: st.error("⚠️ 找不到该商品。")
                if not sel.empty:
                    cb1, cb2, _ = st.columns([1.5, 1.5, 4])
                    if cb1.button("🗑️ 彻底删档", type="primary"):
                        fss = JIT_fetch([STOCK_SHEET])[STOCK_SHEET]
                        for _, rw in sel.iterrows():
                            fss = fss[~((fss['商品名称'].astype(str).str.strip() == str(rw['商品名称']).strip()) & (fss['颜色'].astype(str).str.strip() == str(rw['颜色']).strip()))]
                        save_data(fss, STOCK_SHEET); st.session_state.reset_keys['stock'] += 1; st.rerun()
                    if cb2.button("🔄 取消选中"): st.session_state.reset_keys['stock'] += 1; st.rerun()

# 5.2 公共：POS 收银系统与单据操作
def render_pos_engine(role):
    st.subheader("🛒 智能 POS 收银台 (多件合并结账)")
    p1, p2 = st.columns([1.2, 1.5])
    fo = get_f(df_stock, "").copy() 
    if not fo.empty:
        fo['l'] = fo['商品名称'].fillna('').astype(str) + " (" + fo['颜色'].fillna('').astype(str) + ")" 
        with p1:
            with st.container(border=True):
                st.markdown("#### 1️⃣ 扫码/点单区")
                skw = st.text_input("🔍 键盘输入搜商品 (自动过滤下拉菜单)", key=f"ps_{role}")
                fop = fo[fo['l'].str.contains(skw, case=False, na=False)] if skw else fo
                if not fop.empty:
                    sl = st.selectbox("选择商品", fop['l'], key=f"pi_{role}")
                    rw = fop[fop['l'] == sl].iloc[0]
                    bp = float(pd.to_numeric(rw['售卖价格'], errors='coerce') or 0)
                    cq, cd = st.columns(2)
                    sq = cq.number_input("数量", min_value=1, value=1, step=1, key=f"pq_{role}")
                    do = {"无折扣": 1.0, "95折": 0.95, "9折": 0.90, "85折": 0.85, "8折": 0.80, "75折": 0.75, "7折": 0.70, "5折": 0.50}
                    sdi = cd.selectbox("快捷折扣", list(do.keys()), key=f"pd_{role}")
                    sp = st.number_input("最终单价 ($)", value=float(bp * do[sdi]), format="%.2f", key=f"pp_{role}")
                    
                    if st.button("➕ 加入购物车", use_container_width=True, key=f"ba_{role}"):
                        st.session_state.pos_cart.append({"商品名称": str(rw['商品名称']), "颜色": str(rw['颜色']), "数量": sq, "单价": sp, "小计": sq * sp})
                        st.rerun()
                else: st.warning("未找到商品。")
        with p2:
            with st.container(border=True):
                st.markdown("#### 2️⃣ 当前购物车")
                if not st.session_state.pos_cart: st.info("🛒 购物车空。")
                else:
                    cdf = pd.DataFrame(st.session_state.pos_cart)
                    st.dataframe(cdf.style.format({'单价': '${:.2f}', '小计': '${:.2f}'}), use_container_width=True, hide_index=True)
                    st.markdown(f"**🛍️ 共计:** `{cdf['数量'].sum()}` | **💰 应收:** ` ${cdf['小计'].sum():.2f}`")
                    cc1, cc2 = st.columns([2, 1])
                    sdt = cc1.date_input("交易日期", value=datetime.now(), key=f"pdt_{role}")
                    if cc2.button("🗑️ 清空", use_container_width=True, key=f"bcl_{role}"): st.session_state.pos_cart = []; st.rerun()
                    if st.button("💳 确认结账 (生成流水)", type="primary", use_container_width=True, key=f"bco_{role}"):
                        f = JIT_fetch([STOCK_SHEET, SALES_SHEET]); ls, lsal = f[STOCK_SHEET], f[SALES_SHEET]
                        oid, odt, usr = "ORD-" + datetime.now().strftime("%Y%m%d-%H%M%S"), sdt.strftime("%Y/%m/%d"), st.session_state.get("current_user", "Unknown")
                        nr = []
                        for i in st.session_state.pos_cart:
                            nr.append([oid, odt, usr, i['商品名称'], i['颜色'], i['数量'], i['单价'], i['小计']])
                            idx = ls[(ls['商品名称'].astype(str).str.strip() == str(i['商品名称']).strip()) & (ls['颜色'].astype(str).str.strip() == str(i['颜色']).strip())].index
                            if not idx.empty:
                                i_p = idx[0]
                                ls.at[i_p, '货柜数量'] = int(pd.to_numeric(ls.at[i_p, '货柜数量'], errors='coerce') or 0) - i['数量']
                                ls.at[i_p, '已售出数量'] = int(pd.to_numeric(ls.at[i_p, '已售出数量'], errors='coerce') or 0) + i['数量']
                                ls.at[i_p, '总库存'] = sum([int(pd.to_numeric(ls.at[i_p, c], errors='coerce') or 0) for c in ['展示数量', '货柜数量', '储物间数量']])
                        save_data(pd.concat([pd.DataFrame(nr, columns=SALES_COLS), lsal], ignore_index=True), SALES_SHEET); save_data(ls, STOCK_SHEET) 
                        st.session_state.pos_cart = []; st.success(f"🎉 结账成功！单号 {oid}"); st.rerun()
    st.divider()
    
    with st.expander("🚶‍♂️ 录入/修正每日有效客流", expanded=False):
        with st.form(f"trf_{role}"):
            tc1, tc2 = st.columns(2)
            trd = tc1.date_input("📅 客流日期", value=datetime.now())
            trn = tc2.number_input("👁️ 客流人数", min_value=0, step=1, value=0)
            if st.form_submit_button("💾 保存客流数据", type="primary", use_container_width=True):
                ft = JIT_fetch([TRAFFIC_SHEET])[TRAFFIC_SHEET]; tds = trd.strftime("%Y/%m/%d")
                idx = ft[ft['日期'].astype(str).str.strip() == tds].index
                if not idx.empty: ft.at[idx[0], '有效客流'] = trn
                else: ft = pd.concat([pd.DataFrame([[tds, trn]], columns=TRAFFIC_COLS), ft], ignore_index=True)
                save_data(ft, TRAFFIC_SHEET); st.success("✅ Saved!"); st.rerun()

    with st.expander("🔄 客户换货处理 (Exchange)", expanded=False):
        if not fo.empty:
            xc1, xc2 = st.columns(2)
            with xc1:
                st.markdown("### 🔙 退回的商品")
                exr = st.selectbox("1. Return Item", fo['l'], key=f"exr_{role}")
                r_r = fo[fo['l'] == exr].iloc[0]
                rp = st.number_input("2. Return Value ($)", value=float(pd.to_numeric(r_r['售卖价格'], errors='coerce') or 0), format="%.2f", key=f"rp_{role}")
                rd = st.checkbox("⚠️ 有瑕疵 (记入坏货)", value=False, key=f"rd_{role}")
            with xc2:
                st.markdown("### 🆕 换购的商品")
                exn = st.selectbox("1. New Item", fo['l'], key=f"exn_{role}")
                n_r = fo[fo['l'] == exn].iloc[0]
                np = st.number_input("2. New Item Price ($)", value=float(pd.to_numeric(n_r['售卖价格'], errors='coerce') or 0), format="%.2f", key=f"np_{role}")
            c_d, c_df = st.columns(2)
            with c_d: exd = st.date_input("📅 Date", value=datetime.now(), key=f"exd_{role}")
            with c_df:
                dfi = np - rp
                if dfi > 0: st.warning(f"💰 需补差价：${dfi:.2f}")
                elif dfi < 0: st.success(f"💸 需退差价：${abs(dfi):.2f}")
                else: st.info("🤝 等价交换")
            if st.button("🔄 确认执行换货", type="primary", use_container_width=True, key=f"bex_{role}"):
                f = JIT_fetch([STOCK_SHEET, SALES_SHEET]); ls, lsal = f[STOCK_SHEET], f[SALES_SHEET]
                edt, oid, usr = exd.strftime("%Y/%m/%d"), "EXC-" + datetime.now().strftime("%Y%m%d-%H%M%S"), st.session_state.get("current_user", "Unknown")
                rn, rc, nn, nc = str(r_r['商品名称']), str(r_r['颜色']), str(n_r['商品名称']), str(n_r['颜色'])
                
                ir = ls[(ls['商品名称'].astype(str).str.strip() == rn.strip()) & (ls['颜色'].astype(str).str.strip() == rc.strip())].index[0]
                in_ = ls[(ls['商品名称'].astype(str).str.strip() == nn.strip()) & (ls['颜色'].astype(str).str.strip() == nc.strip())].index[0]
                
                lsal = pd.concat([pd.DataFrame([[oid, edt, usr, nn, nc, 1, np, np], [oid, edt, usr, rn, rc, -1, rp, -rp]], columns=SALES_COLS), lsal], ignore_index=True)
                
                if rd: ls.at[ir, '坏货数量'] = int(pd.to_numeric(ls.at[ir, '坏货数量'], errors='coerce') or 0) + 1
                else: 
                    ls.at[ir, '货柜数量'] = int(pd.to_numeric(ls.at[ir, '货柜数量'], errors='coerce') or 0) + 1
                    ls.at[ir, '总库存'] = sum([int(pd.to_numeric(ls.at[ir, c], errors='coerce') or 0) for c in ['展示数量', '货柜数量', '储物间数量']])
                ls.at[ir, '已售出数量'] = int(pd.to_numeric(ls.at[ir, '已售出数量'], errors='coerce') or 0) - 1
                ls.at[in_, '货柜数量'] = int(pd.to_numeric(ls.at[in_, '货柜数量'], errors='coerce') or 0) - 1
                ls.at[in_, '已售出数量'] = int(pd.to_numeric(ls.at[in_, '已售出数量'], errors='coerce') or 0) + 1
                ls.at[in_, '总库存'] = sum([int(pd.to_numeric(ls.at[in_, c], errors='coerce') or 0) for c in ['展示数量', '货柜数量', '储物间数量']])
                save_data(lsal, SALES_SHEET); save_data(ls, STOCK_SHEET); st.success("✅ Exchange Success!"); st.rerun()

# =========================================================================================
# ================================== 🚀 Admin 视图展开 =====================================
# =========================================================================================
if is_admin:
    with t1:
        st.subheader("📦 专业 ERP 库存与货位管家")
        opts_l = []
        if not df_stock.empty:
            df_stock['l'] = df_stock['商品名称'].fillna('').astype(str) + " (" + df_stock['颜色'].fillna('').astype(str) + ")"
            opts_l = df_stock['l'].tolist()
            
        t1a, t1b, t1c = st.tabs(["📥 1. 补货入库", "🔄 2. 货位调拨", "⚖️ 3. 盘点平账"])
        with t1a:
            with st.form("f_res"):
                c1, c2, c3 = st.columns(3)
                r_sku = c1.selectbox("到货商品", opts_l) if opts_l else c1.selectbox("商品", ["空"])
                r_dt = c2.date_input("入库日期", value=datetime.now())
                r_loc = c3.selectbox("存放至", ["储物间数量", "货柜数量", "展示数量"])
                c4, c5, c6 = st.columns(3)
                r_qty = c4.number_input("数量", min_value=1, step=1, value=50)
                r_cst = c5.number_input("单件进价 ($)", value=0.0, format="%.2f")
                r_nt = c6.text_input("备注单号")
                if st.form_submit_button("✅ 确认入库", type="primary") and opts_l:
                    f = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET]); ls, lr = f[STOCK_SHEET], f[RESTOCK_SHEET]
                    rn, rc = r_sku.rsplit(" (", 1)[0], r_sku.rsplit(" (", 1)[1].replace(")", "")
                    midx = ls[(ls['商品名称'].astype(str).str.strip() == str(rn).strip()) & (ls['颜色'].astype(str).str.strip() == str(rc).strip())].index
                    if not midx.empty:
                        i = midx[0]
                        ls.at[i, r_loc] = int(pd.to_numeric(ls.at[i, r_loc], errors='coerce') or 0) + r_qty
                        ls.at[i, '总库存'] = sum([int(pd.to_numeric(ls.at[i, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                        if r_cst > 0: ls.at[i, '进价成本'] = r_cst 
                        nl = pd.DataFrame([[r_dt.strftime("%Y/%m/%d"), "入库", rn, rc, r_qty, f"存入: {r_loc.replace('数量','')}", r_cst, r_nt]], columns=RESTOCK_COLS)
                        save_data(ls, STOCK_SHEET); save_data(pd.concat([nl, lr], ignore_index=True), RESTOCK_SHEET); st.success("✅ 补货成功！"); st.rerun()
                    else: st.error("找不到该商品。")

        with t1b:
            with st.form("f_trf"):
                c1, c2, c3, c4 = st.columns(4)
                t_sku = c1.selectbox("调拨商品", opts_l) if opts_l else c1.selectbox("商品", ["空"])
                t_src, t_dst, t_qty = c2.selectbox("移出(源)", ["储物间数量", "货柜数量", "展示数量"]), c3.selectbox("移入(目标)", ["货柜数量", "展示数量", "储物间数量"]), c4.number_input("数量", min_value=1, step=1, value=10)
                if st.form_submit_button("🔄 确认移库", type="primary") and opts_l and t_src != t_dst:
                    f = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET]); ls, lr = f[STOCK_SHEET], f[RESTOCK_SHEET]
                    rn, rc = t_sku.rsplit(" (", 1)[0], t_sku.rsplit(" (", 1)[1].replace(")", "")
                    midx = ls[(ls['商品名称'].astype(str).str.strip() == str(rn).strip()) & (ls['颜色'].astype(str).str.strip() == str(rc).strip())].index
                    if not midx.empty:
                        i = midx[0]
                        cq = int(pd.to_numeric(ls.at[i, t_src], errors='coerce') or 0)
                        if cq < t_qty: st.error("库存不足！")
                        else:
                            ls.at[i, t_src] = cq - t_qty
                            ls.at[i, t_dst] = int(pd.to_numeric(ls.at[i, t_dst], errors='coerce') or 0) + t_qty
                            nl = pd.DataFrame([[datetime.now().strftime("%Y/%m/%d"), "调拨", rn, rc, t_qty, f"{t_src.replace('数量','')} -> {t_dst.replace('数量','')}", 0, "内部移库"]], columns=RESTOCK_COLS)
                            save_data(ls, STOCK_SHEET); save_data(pd.concat([nl, lr], ignore_index=True), RESTOCK_SHEET); st.success("✅ 移库成功！"); st.rerun()

        with t1c:
            with st.form("f_adj"):
                c1, c2, c3, c4 = st.columns(4)
                a_sku = c1.selectbox("平账商品", opts_l) if opts_l else c1.selectbox("商品", ["空"])
                a_loc, a_diff, a_note = c2.selectbox("发生差异的库位", ["货柜数量", "展示数量", "储物间数量", "坏货数量"]), c3.number_input("差异 (+为盘盈, -为盘亏)", value=0, step=1), c4.text_input("平账原因 (必填)")
                if st.form_submit_button("⚖️ 确认记账", type="primary"):
                    if not opts_l or a_sku == "空": st.error("没商品。")
                    elif a_diff == 0: st.error("差异不能为0。")
                    elif a_note.strip() == "": st.error("原因必填！")
                    else:
                        f = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET]); ls, lr = f[STOCK_SHEET], f[RESTOCK_SHEET]
                        rn, rc = a_sku.rsplit(" (", 1)[0], a_sku.rsplit(" (", 1)[1].replace(")", "")
                        midx = ls[(ls['商品名称'].astype(str).str.strip() == str(rn).strip()) & (ls['颜色'].astype(str).str.strip() == str(rc).strip())].index
                        if not midx.empty:
                            i = midx[0]
                            ls.at[i, a_loc] = int(pd.to_numeric(ls.at[i, a_loc], errors='coerce') or 0) + a_diff
                            if a_loc != '坏货数量': ls.at[i, '总库存'] = sum([int(pd.to_numeric(ls.at[i, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                            aty = "盘盈" if a_diff > 0 else "盘亏"
                            nl = pd.DataFrame([[datetime.now().strftime("%Y/%m/%d"), aty, rn, rc, a_diff, f"库位: {a_loc.replace('数量','')}", 0, a_note]], columns=RESTOCK_COLS)
                            save_data(ls, STOCK_SHEET); save_data(pd.concat([nl, lr], ignore_index=True), RESTOCK_SHEET); st.success(f"✅ 平账成功！"); st.rerun()

        st.divider()
        render_inventory_snapshot('admin')
        with st.expander("📜 ERP底单：查看所有出入库/平账流水账", expanded=False):
            st.dataframe(get_f(df_restock, q), use_container_width=True)

    with t2:
        render_pos_engine('admin')
        st.divider()
        st.markdown("### 📝 销售流水修改与撤销")
        f_sl = get_f(df_sales, q)
        if not f_sl.empty:
            f_sl_sel = f_sl.copy()
            f_sl_sel['成交单价'] = pd.to_numeric(f_sl_sel['成交单价'], errors='coerce').fillna(0.0)
            f_sl_sel['总营业额'] = pd.to_numeric(f_sl_sel['总营业额'], errors='coerce').fillna(0.0)
            f_sl_sel.insert(0, "选择", False)
            
            # 🔥 精准解除复选框禁用
            dis_cols = [c for c in f_sl_sel.columns if c != "选择"]
            edt = st.data_editor(f_sl_sel.style.format({'成交单价': '${:.2f}', '总营业额': '${:.2f}'}), column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, disabled=dis_cols, use_container_width=True, hide_index=True, key=f"s_ed_{st.session_state.reset_keys['sales']}")
            
            sel = edt[edt["选择"] == True] if "选择" in edt.columns else pd.DataFrame()
            
            if not sel.empty:
                sc1, sc2, _ = st.columns([1.5, 1.5, 4])
                if sc1.button("🔴 批量撤销流水", type="primary"):
                    fresh = JIT_fetch([STOCK_SHEET, SALES_SHEET]); ls, lsal = fresh[STOCK_SHEET], fresh[SALES_SHEET]
                    for _, r in sel.iterrows():
                        rn, rc = str(r['商品名称']).strip(), str(r['颜色']).strip()
                        qv = int(pd.to_numeric(r['销售数量'], errors='coerce') or 0)
                        
                        m = ls[(ls['商品名称'].astype(str).str.strip() == rn) & (ls['颜色'].astype(str).str.strip() == rc)].index
                        if not m.empty:
                            ls.at[m[0], '货柜数量'] = int(pd.to_numeric(ls.at[m[0], '货柜数量'], errors='coerce') or 0) + qv
                            ls.at[m[0], '已售出数量'] = int(pd.to_numeric(ls.at[m[0], '已售出数量'], errors='coerce') or 0) - qv
                            ls.at[m[0], '总库存'] = sum([int(pd.to_numeric(ls.at[m[0], col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                        
                        oid, odt = str(r['订单号']).strip(), str(r['日期']).strip()
                        cond = (lsal['订单号'].astype(str).str.strip() == oid) & (lsal['商品名称'].astype(str).str.strip() == rn) & (lsal['颜色'].astype(str).str.strip() == rc) & (pd.to_numeric(lsal['销售数量'], errors='coerce').fillna(0).astype(int) == qv)
                        lsal = lsal[~cond]
                    save_data(ls, STOCK_SHEET); save_data(lsal, SALES_SHEET); st.session_state.reset_keys['sales'] += 1; st.rerun()
                
                if sc2.button("🔄 取消所有选中"): st.session_state.reset_keys['sales'] += 1; st.rerun()

                if len(sel) == 1:
                    st.markdown("### ⚙️ 修改此笔流水")
                    r = sel.iloc[0]
                    rn, rc, oid, odt = str(r['商品名称']).strip(), str(r['颜色']).strip(), str(r['订单号']).strip(), str(r['日期']).strip()
                    oq, op = int(pd.to_numeric(r['销售数量'], errors='coerce') or 0), float(pd.to_numeric(r['成交单价'], errors='coerce') or 0.0)

                    fo = get_f(df_stock, "").copy()
                    fo['l'] = fo['商品名称'].fillna('').astype(str) + " (" + fo['颜色'].fillna('').astype(str) + ")"
                    sls = fo['l'].tolist()
                    cl = f"{rn} ({rc})"
                    if cl not in sls: sls.insert(0, cl)
                    
                    with st.form("es_f"):
                        e1, e2, e3, e4 = st.columns(4)
                        try: p_dt = pd.to_datetime(odt).date()
                        except: p_dt = datetime.now().date()
                        edt_dt = e1.date_input("交易日期", value=p_dt)
                        epd = e2.selectbox("商品", sls, index=sls.index(cl))
                        eqt = e3.number_input("数量", value=oq, min_value=1)
                        epr = e4.number_input("单价 ($)", value=op, format="%.2f")
                        
                        if st.form_submit_button("💾 保存修改", type="primary"):
                            fresh = JIT_fetch([STOCK_SHEET, SALES_SHEET]); ls, lsal = fresh[STOCK_SHEET], fresh[SALES_SHEET]
                            cond = (lsal['订单号'].astype(str).str.strip() == oid) & (lsal['商品名称'].astype(str).str.strip() == rn) & (lsal['颜色'].astype(str).str.strip() == rc) & (pd.to_numeric(lsal['销售数量'], errors='coerce').fillna(0).astype(int) == oq)
                            ti = lsal[cond].index
                            if not ti.empty:
                                ti0 = ti[0]
                                m_old = ls[(ls['商品名称'].astype(str).str.strip() == rn) & (ls['颜色'].astype(str).str.strip() == rc)].index
                                if not m_old.empty:
                                    ls.at[m_old[0], '货柜数量'] = int(pd.to_numeric(ls.at[m_old[0], '货柜数量'], errors='coerce') or 0) + oq
                                    ls.at[m_old[0], '已售出数量'] = int(pd.to_numeric(ls.at[m_old[0], '已售出数量'], errors='coerce') or 0) - oq
                                    ls.at[m_old[0], '总库存'] = sum([int(pd.to_numeric(ls.at[m_old[0], col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                                    
                                nn, nc = epd.rsplit(" (", 1)[0], epd.rsplit(" (", 1)[1].replace(")", "")
                                m_new = ls[(ls['商品名称'].astype(str).str.strip() == nn) & (ls['颜色'].astype(str).str.strip() == nc)].index
                                if not m_new.empty:
                                    ls.at[m_new[0], '货柜数量'] = int(pd.to_numeric(ls.at[m_new[0], '货柜数量'], errors='coerce') or 0) - eqt
                                    ls.at[m_new[0], '已售出数量'] = int(pd.to_numeric(ls.at[m_new[0], '已售出数量'], errors='coerce') or 0) + eqt
                                    ls.at[m_new[0], '总库存'] = sum([int(pd.to_numeric(ls.at[m_new[0], col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                                    
                                lsal.at[ti0, '日期'], lsal.at[ti0, '商品名称'], lsal.at[ti0, '颜色'], lsal.at[ti0, '销售数量'], lsal.at[ti0, '成交单价'], lsal.at[ti0, '总营业额'] = edt_dt.strftime("%Y/%m/%d"), nn, nc, eqt, epr, eqt * epr
                                save_data(ls, STOCK_SHEET); save_data(lsal, SALES_SHEET); st.session_state.reset_keys['sales'] += 1; st.success("✅ 修改成功！"); st.rerun()
                            else: st.error("⚠️ 未在云端找到该流水！可能是已被删除或数量有偏差。")

    with t3:
        st.subheader("📊 财务与客流报表")
        t3s, t3e = st.session_state.camp_start, st.session_state.camp_end
        st.info(f"📅 财务数据已锁定在：**{t3s}** 至 **{t3e}**")

        if not df_sales.empty:
            ds = df_sales.copy(); ds['dt'] = pd.to_datetime(ds['日期'], errors='coerce'); ds = ds.dropna(subset=['dt'])
            if not ds.empty:
                fs = ds[(ds['dt'].dt.date >= t3s) & (ds['dt'].dt.date <= t3e)].copy()
                fs['销售数量'], fs['总营业额'] = pd.to_numeric(fs['销售数量'], errors='coerce').fillna(0), pd.to_numeric(fs['总营业额'], errors='coerce').fillna(0.0)
                dc = df_stock[['商品名称', '颜色', '进价成本']].copy(); dc['进价成本'] = pd.to_numeric(dc['进价成本'], errors='coerce').fillna(0.0)
                fs = fs.merge(dc, on=['商品名称', '颜色'], how='left')
                fs['具体毛利'] = fs['总营业额'] - (fs['销售数量'] * fs['进价成本'])
                fs = get_f(fs, q)
                if not fs.empty:
                    tr, ti, tm = fs['总营业额'].sum(), fs['销售数量'].sum(), fs['具体毛利'].sum()
                    vo = fs[(~fs['订单号'].astype(str).str.contains('历史单', na=False)) & (~fs['订单号'].astype(str).str.contains('EXC-', na=False))]['订单号'].nunique() + len(fs[fs['订单号'].astype(str).str.contains('历史单', na=False)])
                    dtf = df_traffic.copy()
                    if not dtf.empty:
                        dtf['dt'] = pd.to_datetime(dtf['日期'], errors='coerce')
                        ftf = dtf[(dtf['dt'].dt.date >= t3s) & (dtf['dt'].dt.date <= t3e)]
                        tt = pd.to_numeric(ftf['有效客流'], errors='coerce').fillna(0).sum()
                    else: tt = 0
                    cr, acv, upt = (vo / tt * 100) if tt > 0 else 0.0, tr / vo if vo > 0 else 0, ti / vo if vo > 0 else 0
                    
                    per = st.radio("维度", ["Daily", "Weekly", "Monthly"], horizontal=True)
                    if "Daily" in per: fs['周期'] = fs['dt'].dt.strftime('%Y/%m/%d')
                    elif "Weekly" in per: fs['周期'] = (fs['dt'] - pd.to_timedelta(fs['dt'].dt.dayofweek, unit='D')).dt.strftime('Wk %b %d')
                    else: fs['周期'] = fs['dt'].dt.strftime('%Y/%m')
                    sm = fs.groupby(['周期', '商品名称', '颜色']).agg({'销售数量':'sum', '总营业额':'sum', '具体毛利':'sum'}).reset_index()
                    dd = (t3e - t3s).days + 1
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("👁️ 有效总客流", f"{int(tt)} 人"); m2.metric("💳 交易单数", f"{vo} 单"); m3.metric("🔄 购买转化率", f"{cr:.1f}%")
                    st.divider()
                    m4, m5, m6 = st.columns(3)
                    m4.metric("💰 总营业额", f"${tr:.2f}"); m5.metric("🛒 平均客单价 (ACV)", f"${acv:.2f}"); m6.metric("🛍️ 连带率 (UPT)", f"{upt:.2f} 件/单")
                    st.divider()
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("具体毛利", f"${tm:.2f}"); c2.metric("总售出件数", f"{int(ti)} 件"); c3.metric("平均毛利率", f"{(tm / tr * 100) if tr > 0 else 0:.1f}%"); c4.metric("日均坪效", f"${(tr / dd) if dd > 0 else 0:.2f}")
                    st.divider()
                    st.bar_chart(sm.groupby('周期')[['总营业额', '具体毛利']].sum().sort_index(ascending=True), use_container_width=True)
                    dl1, dl2 = st.columns([1, 4])
                    dl1.download_button("⬇️ 导出毛利报表", convert_df_to_csv(sm), f"Taka_Margin_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv", type="primary")
                    st.dataframe(sm.sort_values('周期', ascending=False).style.format({'总营业额':"${:.2f}", '具体毛利':"${:.2f}", '销售数量':"{:d}"}), use_container_width=True)

    with t4:
        st.subheader("👥 员工档案与考勤管理")
        with st.expander("➕ 新增人员档案"):
            with st.form("add_emp"):
                c1, c2 = st.columns(2)
                enm, erl = c1.text_input("姓名"), c2.selectbox("职位", ["店长", "全职店员", "兼职店员", "实习生", "合作厂商", "其他"])
                c3, c4, c5 = st.columns(3)
                ewg, eph, edt = c3.number_input("时薪 ($/h)", min_value=0.0, step=0.5, value=12.0, format="%.2f"), c4.text_input("联系方式"), c5.date_input("入职日期", value=datetime.now())
                if st.form_submit_button("保存信息"):
                    if enm.strip() == "": st.warning("⚠️ 姓名为空！")
                    else:
                        fe = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                        save_data(pd.concat([fe, pd.DataFrame([[enm, erl, ewg, eph, edt.strftime("%Y/%m/%d"), "", "在职"]], columns=EMP_COLS)], ignore_index=True), EMP_SHEET); st.session_state.reset_keys['emp'] += 1; st.rerun()

        fe = get_f(df_employee, q) 
        if not fe.empty:
            ve = fe.copy(); ve.insert(0, "选择", False)
            ve['时薪'] = pd.to_numeric(ve['时薪'], errors='coerce').fillna(0.0)
            ede = st.data_editor(ve.style.format({'时薪': '${:.2f}'}), column_config={"选择": st.column_config.CheckboxColumn("选择", default=False), "状态": st.column_config.SelectboxColumn("状态", options=["在职", "离职"])}, disabled=['员工姓名', '入职日期'], use_container_width=True, hide_index=True, key=f"e_ed_{st.session_state.reset_keys['emp']}")
            if st.session_state.get(f"e_ed_{st.session_state.reset_keys['emp']}", {}).get("edited_rows"):
                he = False; fre = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                for idx, r in ede.iterrows():
                    for c in EMP_COLS:
                        if str(r[c]) != str(ve.loc[idx, c]): he = True; fre.at[idx, c] = r[c]
                if he: save_data(fre, EMP_SHEET); st.success("✅ 保存！"); st.session_state.reset_keys['emp'] += 1; st.rerun()
            sele = ede[ede["选择"] == True]
            if not sele.empty:
                cb1, cb2, _ = st.columns([1.5, 1.5, 4])
                if cb1.button("🗑️ 删除人员", type="primary"):
                    fre = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                    for _, r in sele.iterrows(): fre = fre[fre['员工姓名'].astype(str).str.strip() != str(r['员工姓名']).strip()]
                    save_data(fre, EMP_SHEET); st.session_state.reset_keys['emp'] += 1; st.rerun()
                if cb2.button("🔄 取消"): st.session_state.reset_keys['emp'] += 1; st.rerun()

        st.divider(); st.subheader("⏰ 排班与打卡记录")
        with st.expander("➕ 帮员工补打卡", expanded=True):
            with st.form("a_att"):
                c1, c2 = st.columns(2)
                an, ad = c1.selectbox("员工", df_employee['员工姓名'].astype(str).tolist() if not df_employee.empty else ["空"]), c2.date_input("工作日期", value=datetime.now())
                c3, c4 = st.columns(2)
                ast, aen = c3.time_input("上班时间", value=time(10, 0)), c4.time_input("下班时间", value=time(18, 0))
                if st.form_submit_button("记录考勤"):
                    fa = JIT_fetch([ATT_SHEET])[ATT_SHEET]
                    dts, dte = datetime.combine(ad, ast), datetime.combine(ad, aen)
                    if dte < dts: dte += timedelta(days=1)
                    dh = (dte - dts).total_seconds() / 3600.0
                    er = df_employee[df_employee['员工姓名'] == an]
                    tw = dh * float(pd.to_numeric(er['时薪'].iloc[0] if not er.empty else 0.0, errors='coerce') or 0.0)
                    save_data(pd.concat([pd.DataFrame([[an, ad.strftime("%Y/%m/%d"), ast.strftime("%H:%M"), aen.strftime("%H:%M"), round(dh, 2), round(tw, 2)]], columns=ATT_COLS), fa], ignore_index=True), ATT_SHEET); st.rerun()

        fa = get_f(df_attendance, q)
        if not fa.empty:
            va = fa.copy(); va.insert(0, "选择", False)
            va['核算薪资'] = pd.to_numeric(va['核算薪资'], errors='coerce').fillna(0.0)
            eda = st.data_editor(va.style.format({'核算薪资': '${:.2f}'}), column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, disabled=fa.columns.tolist(), use_container_width=True, hide_index=True, key=f"a_ed_{st.session_state.reset_keys['att']}")
            sela = eda[eda["选择"] == True]
            if not sela.empty:
                cb1, cb2, _ = st.columns([1.5, 1.5, 4])
                if cb1.button("🗑️ 删除选中打卡", type="primary"):
                    fra = JIT_fetch([ATT_SHEET])[ATT_SHEET]
                    for _, r in sela.iterrows(): fra = fra[~((fra['员工姓名'].astype(str).str.strip() == str(r['员工姓名']).strip()) & (fra['日期'].astype(str).str.strip() == str(r['日期']).strip()) & (fra['开始时间'].astype(str).str.strip() == str(r['开始时间']).strip()))]
                    save_data(fra, ATT_SHEET); st.session_state.reset_keys['att'] += 1; st.rerun()
                if cb2.button("🔄 取消"): st.session_state.reset_keys['att'] += 1; st.rerun()
            c_t1, c_t2, c_t3 = st.columns([2, 1, 1])
            c_t1.markdown(f"**🧾 共 {len(fa)} 条**"); c_t2.metric("总工时", f"{pd.to_numeric(fa['工作时长'], errors='coerce').fillna(0).sum():.1f} h"); c_t3.metric("总薪资", f"${pd.to_numeric(fa['核算薪资'], errors='coerce').fillna(0).sum():.2f}")

    with t5:
        st.subheader(f"💎 真实净利润核算 (9% GST 剥离版)")
        t5_s, t5_e = st.session_state.camp_start, st.session_state.camp_end
        st.info(f"📅 净利数据锁定在：**{t5_s}** 至 **{t5_e}**")

        if not df_sales.empty:
            dsnp = df_sales.copy(); dsnp['dt'] = pd.to_datetime(dsnp['日期'], errors='coerce'); dsnp = dsnp.dropna(subset=['dt'])
            danp = df_attendance.copy()
            if not danp.empty: danp['dt'] = pd.to_datetime(danp['日期'], errors='coerce'); danp = danp.dropna(subset=['dt'])
            else: danp['dt'] = pd.Series(dtype='datetime64[ns]')

            if not dsnp.empty:
                fs = dsnp[(dsnp['dt'].dt.date >= t5_s) & (dsnp['dt'].dt.date <= t5_e)].copy()
                fa = danp[(danp['dt'].dt.date >= t5_s) & (danp['dt'].dt.date <= t5_e)].copy()
                fs['销售数量'], fs['总营业额'] = pd.to_numeric(fs['销售数量'], errors='coerce').fillna(0), pd.to_numeric(fs['总营业额'], errors='coerce').fillna(0.0)
                dc = df_stock[['商品名称', '颜色', '进价成本']].copy(); dc['进价成本'] = pd.to_numeric(dc['进价成本'], errors='coerce').fillna(0.0)
                fs = fs.merge(dc, on=['商品名称', '颜色'], how='left')
                fs['总进价成本'] = fs['销售数量'] * fs['进价成本']
                fs['d_str'] = fs['dt'].dt.strftime('%Y/%m/%d')
                ds_agg = fs.groupby('d_str').agg({'总营业额': 'sum', '总进价成本': 'sum'}).reset_index()

                if not fa.empty:
                    fa['核算薪资'] = pd.to_numeric(fa['核算薪资'], errors='coerce').fillna(0.0)
                    fa['d_str'] = fa['dt'].dt.strftime('%Y/%m/%d')
                    da_agg = fa.groupby('d_str').agg({'核算薪资': 'sum'}).reset_index().rename(columns={'核算薪资': '人工成本'})
                else: da_agg = pd.DataFrame(columns=['d_str', '人工成本'])

                dnp = pd.merge(ds_agg, da_agg, on='d_str', how='outer').fillna(0.0).sort_values('d_str', ascending=False)
                dnp['免税额'] = dnp['总营业额'] / 1.09
                dnp['代扣GST'] = dnp['总营业额'] - dnp['免税额']
                dnp['商场抽成'] = dnp['免税额'] * 0.36
                dnp['回款'] = dnp['免税额'] - dnp['商场抽成']
                dnp['毛利'] = dnp['回款'] - dnp['总进价成本']
                dnp['真实净利润'] = dnp['毛利'] - dnp['人工成本']

                tg, tre, tgs, tco, tse, tcg, twg, tnt = dnp['总营业额'].sum(), dnp['免税额'].sum(), dnp['代扣GST'].sum(), dnp['商场抽成'].sum(), dnp['回款'].sum(), dnp['总进价成本'].sum(), dnp['人工成本'].sum(), dnp['真实净利润'].sum()
                pgs, pco, pcg, pwg, pnt = [((x/tg)*100) if tg>0 else 0 for x in [tgs, tco, tcg, twg, tnt]]

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("💰 总营业额", f"${tg:.2f}"); m2.metric("🏛️ GST(9%)", f"${tgs:.2f}", delta=f"{pgs:.1f}%", delta_color="off")
                m3.metric("📉 抽成(36%)", f"${tco:.2f}", delta=f"{pco:.1f}%", delta_color="off"); m4.metric("💵 实际回款", f"${tse:.2f}")
                st.divider()
                m5, m6, m7, m8 = st.columns(4)
                m5.metric("📦 进价成本", f"${tcg:.2f}", delta=f"{pcg:.1f}%", delta_color="off"); m6.metric("👥 人工成本", f"${twg:.2f}", delta=f"{pwg:.1f}%", delta_color="off")
                m7.metric("💎 纯利润", f"${tnt:.2f}", delta=f"净利率: {pnt:.1f}%", delta_color="normal")
                
                st.divider()
                st.bar_chart(dnp.set_index('d_str')[['总营业额', '真实净利润']].sort_index(ascending=True), use_container_width=True)
                dl, _ = st.columns([1.5, 4])
                dl.download_button("⬇️ 导出净利润 (CSV)", convert_df_to_csv(dnp), f"NetProfit_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv", type="primary")
                st.dataframe(dnp.rename(columns={'d_str': '日期'}).style.format({c: '${:.2f}' for c in dnp.columns if c!='d_str'}), use_container_width=True, hide_index=True)

    with t6:
        st.subheader("🤝 B2B 订单")
        if not df_b2b.empty:
            df_b2b['总计应收'], df_b2b['已收定金'], df_b2b['货物成本'], df_b2b['物流成本'], df_b2b['关税'] = [pd.to_numeric(df_b2b[c], errors='coerce').fillna(0.0) for c in ['总计应收', '已收定金', '货物成本', '物流成本', '关税']]
            df_b2b['待收尾款'] = df_b2b['总计应收'] - df_b2b['已收定金']
            df_b2b['B2B净利'] = df_b2b['总计应收'] - df_b2b['货物成本'] - df_b2b['物流成本'] - df_b2b['关税']
            tv, tc, tp, tpr = df_b2b['总计应收'].sum(), df_b2b['已收定金'].sum(), df_b2b['待收尾款'].sum(), df_b2b['B2B净利'].sum()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💼 合同额", f"${tv:.2f}"); c2.metric("💰 已回款", f"${tc:.2f}"); c3.metric("⏳ 待结清", f"${tp:.2f}"); c4.metric("💎 净利润", f"${tpr:.2f}", delta=f"{(tpr/tv*100) if tv>0 else 0:.1f}%", delta_color="off")

        with st.expander("➕ 录入 B2B 订单", expanded=False):
            c1, c2 = st.columns(2)
            bc, bd = c1.text_input("客户/企业 (必填)"), c2.date_input("建单日期", value=datetime.now())
            om = st.radio("模式", ["单商品", "组合"], horizontal=True)
            fn, fc, fq, fp, ft, fnote = "", "", 0, 0.0, 0.0, ""
            if om == "单商品":
                sl = (df_stock['商品名称'].fillna('').astype(str) + " (" + df_stock['颜色'].fillna('').astype(str) + ")").tolist() if not df_stock.empty else []
                cs1, cs2, cs3 = st.columns([2, 1.5, 1])
                bp, bcp, bcc = cs1.selectbox("选现有", ["空"] + sl), cs2.text_input("手动产品"), cs3.text_input("定制颜色")
                cq, cp = st.columns(2)
                bq, bpr = cq.number_input("数量", min_value=1, value=100), cp.number_input("单价 ($)", format="%.2f", min_value=0.0)
                ft, fq, fp = bq * bpr, bq, bpr
                if bcp.strip(): fn, fc = bcp.strip(), bcc.strip()
                elif bp != "空": fn, fc = bp.rsplit(" (", 1)[0], bp.rsplit(" (", 1)[1].replace(")", "")
            else:
                cnm = st.text_input("组合大单名称")
                ed_c = st.data_editor(pd.DataFrame([{"名称": "杯子", "颜色": "默认", "单价($)": 0.0, "数量": 1}]), num_rows="dynamic", use_container_width=True)
                di = []
                for _, r in ed_c.iterrows():
                    try:
                        p, q_ = float(r["单价($)"]), int(r["数量"])
                        n, c_ = str(r["名称"]).strip(), str(r["颜色"]).strip()
                        if n: ft, fq = ft + p * q_, fq + q_; di.append(f"{n}({c_})x{q_}")
                    except: pass
                st.info(f"🧮 共 **{fq}** 件，**${ft:.2f}**"); fn, fc, fp, fnote = f"【组合】{cnm.strip()}", "多件混装", 0.0, " + ".join(di)

            c10, c11, c12, c13 = st.columns(4)
            bdep, bcog, bshp, btax = c10.number_input("已收定金 ($)", format="%.2f"), c11.number_input("货本 ($)", format="%.2f"), c12.number_input("物流 ($)", format="%.2f"), c13.number_input("关税 ($)", format="%.2f")
            c8, c9, cd = st.columns([1, 1.5, 1])
            bsts, bnt, bdl = c8.selectbox("状态", ["沟通中", "备货中", "待结尾款", "✅ 已完成"]), c9.text_input("备注"), cd.date_input("交期", value=datetime.now() + timedelta(days=30))

            if st.button("🚀 创建订单", type="primary", use_container_width=True):
                if bc.strip() and fn and fn != "【组合】":
                    fnc = f"明细: {fnote} | {bnt}" if om == "组合" else bnt
                    save_data(pd.concat([pd.DataFrame([[bd.strftime("%Y/%m/%d"), bc, fn, fc, fq, fp, ft, bcog, bshp, btax, bdep, ft-bdep, bdl.strftime("%Y/%m/%d"), bsts, fnc]], columns=B2B_COLS), JIT_fetch([B2B_SHEET])[B2B_SHEET]], ignore_index=True), B2B_SHEET); st.success("✅ 成功！"); st.rerun()

        st.divider()
        fb2b = get_f(df_b2b, q)
        if not fb2b.empty:
            vb = fb2b.copy(); vb.insert(0, "选择", False)
            edb = st.data_editor(vb.style.format({'B2B单价':'${:.2f}', '总计应收':'${:.2f}', '货物成本':'${:.2f}', '物流成本':'${:.2f}', '关税':'${:.2f}', '已收定金':'${:.2f}', '待收尾款':'${:.2f}'}), column_config={"选择": st.column_config.CheckboxColumn("选择", default=False), "订单状态": st.column_config.SelectboxColumn("订单状态", options=["沟通中", "备货中", "待结尾款", "✅ 已完成"])}, disabled=['待收尾款'], use_container_width=True, hide_index=True, key=f"b2b_e_{st.session_state.reset_keys['b2b']}")
            if st.session_state.get(f"b2b_e_{st.session_state.reset_keys['b2b']}", {}).get("edited_rows"):
                he = False; frb = JIT_fetch([B2B_SHEET])[B2B_SHEET]
                for idx, r in edb.iterrows():
                    for c in ['货物成本', '物流成本', '关税', '已收定金', '订单状态', '约定交期', '备注']:
                        if str(r[c]) != str(vb.loc[idx, c]): he = True; frb.at[idx, c] = r[c]
                if he: save_data(frb, B2B_SHEET); st.success("✅ 保存！"); st.session_state.reset_keys['b2b'] += 1; st.rerun()
            selb = edb[edb["选择"] == True]
            if not selb.empty and st.button("🗑️ 删除订单", type="primary"):
                frb = JIT_fetch([B2B_SHEET])[B2B_SHEET]
                for _, r in selb.iterrows(): frb = frb[~((frb['客户名称'].astype(str).str.strip() == str(r['客户名称']).strip()) & (frb['创建日期'].astype(str).str.strip() == str(r['创建日期']).strip()))]
                save_data(frb, B2B_SHEET); st.session_state.reset_keys['b2b'] += 1; st.rerun()

    with t7:
        st.subheader("🗣️ 客户反馈池")
        fops = ["功能性", "优化", "效能", "外观", "材质", "清洗", "密封性", "价格", "🌏 本土化", "夸奖", "其他"]
        cops = ["散客", "VIP", "送礼", "游客", "B2B企业"]
        sops = ["🚨 待处理", "📝 已反馈工厂", "✅ 已解决"]

        with st.expander("➕ 录入反馈", expanded=True):
            with st.form("a_fb"):
                c1, c2 = st.columns(2)
                fbd = c1.date_input("反馈日期", value=datetime.now())
                fbp = c2.selectbox("商品", df_stock['商品名称'].unique().tolist() + ["全系/通用"]) if not df_stock.empty else c2.text_input("商品")
                c3, c4 = st.columns(2)
                fbt, fbc = c3.selectbox("痛点", fops), c4.selectbox("画像", cops)
                fbdt = st.text_area("🗣️ 描述"); fbs = st.selectbox("状态", sops)
                if st.form_submit_button("保存", type="primary", use_container_width=True) and fbdt.strip():
                    save_data(pd.concat([pd.DataFrame([[fbd.strftime("%Y/%m/%d"), fbp, fbc, fbt, fbdt, fbs]], columns=FEEDBACK_COLS), JIT_fetch([FEEDBACK_SHEET])[FEEDBACK_SHEET]], ignore_index=True), FEEDBACK_SHEET); st.success("✅ 成功！"); st.rerun()

        st.divider(); ff = get_f(df_feedback, q)
        if not ff.empty:
            fc1, fc2 = st.columns(2)
            fc1.bar_chart(ff['反馈类型'].value_counts()); fc2.bar_chart(ff['商品名称'].value_counts())
            vf = ff.copy(); vf.insert(0, "选择", False)
            edf = st.data_editor(vf, column_config={"选择": st.column_config.CheckboxColumn("选择", default=False), "跟进状态": st.column_config.SelectboxColumn("状态", options=sops), "反馈类型": st.column_config.SelectboxColumn("类型", options=fops), "客户画像": st.column_config.SelectboxColumn("画像", options=cops)}, use_container_width=True, hide_index=True, key=f"f_ed_{st.session_state.reset_keys['fb']}")
            if st.session_state.get(f"f_ed_{st.session_state.reset_keys['fb']}", {}).get("edited_rows"):
                he = False; frf = JIT_fetch([FEEDBACK_SHEET])[FEEDBACK_SHEET]
                for idx, r in edf.iterrows():
                    for c in FEEDBACK_COLS:
                        if str(r[c]) != str(vf.loc[idx, c]): he = True; frf.at[idx, c] = r[c]
                if he: save_data(frf, FEEDBACK_SHEET); st.success("✅ 保存！"); st.session_state.reset_keys['fb'] += 1; st.rerun()
            selfb = edf[edf["选择"] == True]
            if not selfb.empty and st.button("🗑️ 删除反馈", type="primary"):
                frf = JIT_fetch([FEEDBACK_SHEET])[FEEDBACK_SHEET]
                for _, r in selfb.iterrows(): frf = frf[~((frf['详细原话'].astype(str).str.strip() == str(r['详细原话']).strip()) & (frf['商品名称'].astype(str).str.strip() == str(r['商品名称']).strip()))]
                save_data(frf, FEEDBACK_SHEET); st.session_state.reset_keys['fb'] += 1; st.rerun()

# =========================================================================================
# ================================== 🚀 Supplier 视图展开 ==================================
# =========================================================================================
elif is_supplier:
    with t1: render_inventory_snapshot('supplier')
    with t2:
        st.subheader("💰 销售报表对账查询")
        dr = st.date_input("📅 查询日期", value=[st.session_state.camp_start, st.session_state.camp_end])
        ss, se = (dr[0], dr[1]) if len(dr) == 2 else (dr[0], dr[0])
        fs = df_sales.copy(); fs['dt'] = pd.to_datetime(fs['日期'], errors='coerce'); fs = fs.dropna(subset=['dt'])
        f = fs[(fs['dt'].dt.date >= ss) & (fs['dt'].dt.date <= se)]
        f = get_f(f, q)
        if not f.empty:
            f['销售数量'], f['总营业额'] = pd.to_numeric(f['销售数量'], errors='coerce').fillna(0), pd.to_numeric(f['总营业额'], errors='coerce').fillna(0.0)
            c1, c2 = st.columns(2)
            c1.metric("📦 区间售出", f"{int(f['销售数量'].sum())}"); c2.metric("💰 营业额", f"${f['总营业额'].sum():.2f}")
            st.dataframe(f[['订单号', '日期', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']].style.format({'成交单价': '${:.2f}', '总营业额': '${:.2f}'}), use_container_width=True, hide_index=True)
        else: st.info("该区间无记录。")
    with t3:
        st.subheader("📦 进货与入库对账单")
        rs, re = st.session_state.camp_start, st.session_state.camp_end
        st.info(f"📅 锁定在：**{rs}** 至 **{re}**")
        dr = df_restock.copy(); dr['dt'] = pd.to_datetime(dr['记录日期'], errors='coerce'); dr = dr.dropna(subset=['dt'])
        fr = dr[(dr['dt'].dt.date >= rs) & (dr['dt'].dt.date <= re)]
        fr = get_f(fr, q)
        if not fr.empty:
            a_ops = [str(x) for x in fr['操作类型'].fillna('').unique().tolist() if str(x).strip()]
            tf = st.multiselect("筛选操作", options=a_ops, default=list(set([op for op in ["入库", "初始建档"] if op in a_ops])))
            if tf:
                fr = fr[fr['操作类型'].isin(tf)]
                st.metric("🚛 累计变动", f"{int(fr['变动数量'].apply(lambda x: pd.to_numeric(x, errors='coerce')).fillna(0).sum())}")
                st.dataframe(fr[['记录日期', '操作类型', '商品名称', '颜色', '变动数量', '库位详情', '备注']], use_container_width=True, hide_index=True)
    with t4:
        st.subheader("🤝 B2B 订单对账单")
        bs, be = st.session_state.camp_start, st.session_state.camp_end
        db = df_b2b.copy(); db['dt'] = pd.to_datetime(db['创建日期'], errors='coerce'); db = db.dropna(subset=['dt'])
        fb = db[(db['dt'].dt.date >= bs) & (db['dt'].dt.date <= be)]
        fb = get_f(fb, q)
        if not fb.empty:
            for c in ['采购数量', 'B2B单价', '总计应收', '已收定金']: fb[c] = pd.to_numeric(fb[c], errors='coerce').fillna(0.0)
            fb['待收尾款'] = fb['总计应收'] - fb['已收定金']
            c1, c2 = st.columns(2)
            c1.metric("📦 B2B 总采购件数", f"{int(fb['采购数量'].sum())}"); c2.metric("💰 B2B 总计应收", f"${fb['总计应收'].sum():.2f}")
            st.dataframe(fb[['创建日期', '客户名称', '商品名称', '颜色', '采购数量', 'B2B单价', '总计应收', '已收定金', '待收尾款', '约定交期', '订单状态', '备注']].style.format({'B2B单价': '${:.2f}', '总计应收': '${:.2f}', '已收定金': '${:.2f}', '待收尾款': '${:.2f}'}), use_container_width=True, hide_index=True)

# =========================================================================================
# ================================== 🚀 Employee 视图展开 ==================================
# =========================================================================================
elif is_employee:
    with t1: render_inventory_snapshot('employee')
    with t2:
        render_pos_engine('employee')
        st.divider(); st.markdown("### 📝 今日流水 (只读)")
        fsl = get_f(df_sales, q); tds = datetime.now().strftime("%Y/%m/%d")
        tsl = fsl[fsl['日期'] == tds].copy() if not fsl.empty else pd.DataFrame()
        if not tsl.empty:
            tsl['成交单价'], tsl['总营业额'] = pd.to_numeric(tsl['成交单价'], errors='coerce').fillna(0.0), pd.to_numeric(tsl['总营业额'], errors='coerce').fillna(0.0)
            st.dataframe(tsl.style.format({'成交单价': '${:.2f}', '总营业额': '${:.2f}'}), use_container_width=True, hide_index=True)
        else: st.write("今日无流水。")
    with t3:
        st.subheader("⏰ 员工考勤打卡")
        with st.form("e_att"):
            en = st.session_state.current_user
            st.markdown(f"**打卡人:** `{en}`"); ad = st.date_input("工作日期", value=datetime.now())
            c1, c2 = st.columns(2)
            ast, aen = c1.time_input("上班", value=time(10, 0)), c2.time_input("下班", value=time(18, 0))
            if st.form_submit_button("✅ 确认打卡", type="primary", use_container_width=True):
                fa, fe = JIT_fetch([ATT_SHEET])[ATT_SHEET], JIT_fetch([EMP_SHEET])[EMP_SHEET]
                dts, dte = datetime.combine(ad, ast), datetime.combine(ad, aen)
                if dte < dts: dte += timedelta(days=1)
                dh = (dte - dts).total_seconds() / 3600.0
                er = fe[fe['员工姓名'].astype(str).str.strip() == str(en).strip()]
                hw = float(pd.to_numeric(er.iloc[0]['时薪'], errors='coerce') or 0.0) if not er.empty else 0.0
                tw = dh * hw
                save_data(pd.concat([pd.DataFrame([[en, ad.strftime("%Y/%m/%d"), ast.strftime("%H:%M"), aen.strftime("%H:%M"), round(dh, 2), round(tw, 2)]], columns=ATT_COLS), fa], ignore_index=True), ATT_SHEET); st.success(f"打卡成功！共 {round(dh, 1)} 小时。"); st.rerun()

        st.divider(); st.markdown("### 📝 我的打卡记录")
        f_att = get_f(df_attendance, q)
        ma = f_att[f_att['员工姓名'].astype(str).str.strip() == str(st.session_state.current_user).strip()].copy() if not f_att.empty else pd.DataFrame()
        if not ma.empty:
            ma['核算薪资'] = pd.to_numeric(ma['核算薪资'], errors='coerce').fillna(0.0)
            st.dataframe(ma.style.format({'核算薪资': '${:.2f}'}), use_container_width=True, hide_index=True)
            c3, c4 = st.columns(2)
            c3.metric("总工时", f"{pd.to_numeric(ma['工作时长'], errors='coerce').fillna(0).sum():.1f}"); c4.metric("预估总薪资", f"${ma['核算薪资'].sum():.2f}")
