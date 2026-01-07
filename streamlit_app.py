import streamlit as st
import pandas as pd
import sqlite3
import time
import math
import json
import uuid
import altair as alt
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(page_title="RoboLab Inventory", page_icon="🤖", layout="wide")

# --- THEME CONFIGURATION ---
THEMES = {
    "TSRS (Red/Grey)": {
        "primary": "#A6192E",
        "secondary": "#58595B",
        "bg_sidebar": "#F3F4F6",
        "text_sidebar": "#1F2937",
        "hover": "#E5E7EB",
        "active": "#A6192E",
        "active_text": "#FFFFFF"
    },
    "Night Mode (Dark/Blue)": {
        "primary": "#3B82F6",
        "secondary": "#9CA3AF",
        "bg_sidebar": "#111827",
        "text_sidebar": "#E5E7EB",
        "hover": "#374151",
        "active": "#1D4ED8",
        "active_text": "#FFFFFF"
    }
}

if 'theme' not in st.session_state:
    st.session_state.theme = "TSRS (Red/Grey)"

current_theme = THEMES[st.session_state.theme]

st.markdown(f"""
<style>
    .stApp {{ font-family: 'Inter', sans-serif; }}
    section[data-testid="stSidebar"] {{ background-color: {current_theme['bg_sidebar']}; }}
    
    .nav-btn {{
        width: 100%; text-align: left; padding: 12px 15px; margin: 5px 0;
        border: none; border-radius: 8px; background-color: transparent;
        color: {current_theme['text_sidebar']}; font-size: 16px; cursor: pointer;
        display: flex; align-items: center; gap: 10px;
    }}
    .nav-btn:hover {{ background-color: {current_theme['hover']}; }}
    
    div[data-testid="stMetric"] {{
        background-color: white; padding: 20px; border-radius: 12px;
        border-left: 5px solid {current_theme['primary']};
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }}
    
    h1, h2, h3 {{ color: {current_theme['secondary']}; }}
    h1 {{ color: {current_theme['primary']}; border-bottom: 2px solid #E5E7EB; padding-bottom: 10px; }}
    
    .login-box {{
        background: white; padding: 40px; border-radius: 20px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.1); border-top: 6px solid {current_theme['primary']};
    }}
</style>
""", unsafe_allow_html=True)

# --- DATABASE FUNCTIONS ---

def get_db_connection():
    conn = sqlite3.connect('robolab.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Users
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 emp_id TEXT UNIQUE NOT NULL,
                 name TEXT NOT NULL,
                 password TEXT NOT NULL,
                 role TEXT NOT NULL,
                 dob TEXT, gender TEXT, address TEXT, phone TEXT)''')
    
    # 2. Roles (New Feature)
    c.execute('''CREATE TABLE IF NOT EXISTS roles (
                 name TEXT PRIMARY KEY,
                 permissions TEXT)''')
    
    # 3. Inventory
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 name TEXT NOT NULL,
                 category TEXT,
                 location TEXT,
                 quantity INTEGER DEFAULT 0,
                 min_stock INTEGER DEFAULT 5,
                 price REAL DEFAULT 0.0)''')
    
    # 4. Transactions
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 item_id INTEGER,
                 item_name TEXT,
                 type TEXT,
                 quantity INTEGER,
                 user TEXT,
                 timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                 notes TEXT)''')
    
    # 5. Sessions (New Feature)
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
                 token TEXT PRIMARY KEY,
                 user_id INTEGER,
                 expires_at DATETIME)''')

    # SEED DATA
    
    # Seed Roles
    c.execute("SELECT count(*) FROM roles")
    if c.fetchone()[0] == 0:
        # Admin: Access Everything
        all_perms = json.dumps(["Dashboard", "Inventory", "Stock Operations", "Reports", "Shopping List", "User Management", "Settings"])
        c.execute("INSERT INTO roles (name, permissions) VALUES (?, ?)", ('admin', all_perms))
        
        # Assistant: No User Mgmt, No Settings
        asst_perms = json.dumps(["Dashboard", "Inventory", "Stock Operations", "Reports", "Shopping List"])
        c.execute("INSERT INTO roles (name, permissions) VALUES (?, ?)", ('assistant', asst_perms))
        
        conn.commit()

    # Seed Users
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (emp_id, name, password, role) VALUES (?, ?, ?, ?)", ('admin', 'System Admin', 'admin123', 'admin'))
        c.execute("INSERT INTO users (emp_id, name, password, role) VALUES (?, ?, ?, ?)", ('assistant', 'Lab Assistant', '123', 'assistant'))
        conn.commit()
    
    conn.close()

def run_query(query, params=(), fetch=False):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(query, params)
        if fetch:
            data = c.fetchall()
            conn.close()
            return [dict(row) for row in data]
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Database Error: {e}")
        conn.close()
        return False

# --- AUTH & SESSION MANAGEMENT ---

def create_session(user_id):
    token = str(uuid.uuid4())
    expiry = datetime.now() + timedelta(minutes=5) # 5 Minute Session
    run_query("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, user_id, expiry))
    return token

def validate_session(token):
    # Clean up old sessions first
    run_query("DELETE FROM sessions WHERE expires_at < ?", (datetime.now(),))
    
    data = run_query("SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?", (token, datetime.now()), fetch=True)
    if data:
        user_id = data[0]['user_id']
        # Extend session
        new_expiry = datetime.now() + timedelta(minutes=5)
        run_query("UPDATE sessions SET expires_at = ? WHERE token = ?", (new_expiry, token))
        
        # Get User Details
        user = run_query("SELECT * FROM users WHERE id = ?", (user_id,), fetch=True)
        return user[0] if user else None
    return None

def logout_user():
    if 'session_token' in st.query_params:
        token = st.query_params['session_token']
        run_query("DELETE FROM sessions WHERE token = ?", (token,))
    st.query_params.clear()
    st.session_state.user = None
    st.rerun()

def get_permissions(role_name):
    data = run_query("SELECT permissions FROM roles WHERE name = ?", (role_name,), fetch=True)
    if data:
        return json.loads(data[0]['permissions'])
    return []

# --- VIEWS ---

def view_dashboard():
    st.title("📊 Lab Analytics")
    df = pd.read_sql_query("SELECT * FROM inventory", get_db_connection())
    
    if df.empty:
        st.info("Inventory is empty.")
        return

    # 1. Top Level Metrics
    c1, c2, c3, c4 = st.columns(4)
    total_qty = df['quantity'].sum()
    total_val = (df['quantity'] * df['price']).sum()
    low_stock = df[df['quantity'] <= df['min_stock']].shape[0]
    unique_items = df['name'].nunique()

    c1.metric("Total Items", total_qty)
    c2.metric("Inventory Value", f"₹{total_val:,.0f}")
    c3.metric("Unique Components", unique_items)
    c4.metric("Alerts", f"{low_stock}", delta="Action Needed" if low_stock > 0 else "All Good", delta_color="inverse")

    st.markdown("---")

    # 2. Visualizations using Altair
    col_charts_1, col_charts_2 = st.columns(2)
    
    with col_charts_1:
        st.subheader("📦 Category Distribution")
        cat_data = df['category'].value_counts().reset_index()
        cat_data.columns = ['Category', 'Count']
        
        donut = alt.Chart(cat_data).mark_arc(innerRadius=50).encode(
            theta=alt.Theta(field="Count", type="quantitative"),
            color=alt.Color(field="Category", type="nominal"),
            tooltip=['Category', 'Count']
        )
        st.altair_chart(donut, use_container_width=True)

    with col_charts_2:
        st.subheader("💰 Value by Category")
        df['total_value'] = df['quantity'] * df['price']
        val_data = df.groupby('category')['total_value'].sum().reset_index()
        
        bar = alt.Chart(val_data).mark_bar().encode(
            x='total_value',
            y=alt.Y('category', sort='-x'),
            color='category',
            tooltip=['category', 'total_value']
        )
        st.altair_chart(bar, use_container_width=True)

    # 3. Stock Health
    st.subheader("🏥 Stock Health Overview")
    health_data = pd.DataFrame({
        'Status': ['Healthy', 'Low Stock'],
        'Count': [len(df[df['quantity'] > df['min_stock']]), len(df[df['quantity'] <= df['min_stock']])]
    })
    
    health_chart = alt.Chart(health_data).mark_bar().encode(
        x='sum(Count)',
        color=alt.Color('Status', scale=alt.Scale(domain=['Healthy', 'Low Stock'], range=['#10B981', '#EF4444']))
    ).properties(height=50)
    st.altair_chart(health_chart, use_container_width=True)

def view_user_management():
    st.title("👥 User & Role Management")
    
    tab_users, tab_roles = st.tabs(["Manage Users", "Manage Roles"])
    
    # --- MANAGE USERS TAB ---
    with tab_users:
        conn = get_db_connection()
        users_df = pd.read_sql_query("SELECT id, emp_id, name, role, phone, dob FROM users", conn)
        conn.close()
        
        # Display Users
        st.dataframe(users_df, use_container_width=True)
        
        # Action Area
        col_add, col_edit = st.columns(2)
        
        # CREATE USER
        with col_add:
            with st.expander("➕ Create New User", expanded=False):
                with st.form("create_user"):
                    roles_list = [r['name'] for r in run_query("SELECT name FROM roles", fetch=True)]
                    
                    uid = st.text_input("Employee ID")
                    uname = st.text_input("Name")
                    upass = st.text_input("Password", type="password")
                    urole = st.selectbox("Role", roles_list)
                    
                    if st.form_submit_button("Create User"):
                        if run_query("INSERT INTO users (emp_id, name, password, role) VALUES (?, ?, ?, ?)", (uid, uname, upass, urole)):
                            st.success("User Created")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Error creating user")

        # EDIT USER (Requested Feature)
        with col_edit:
            with st.expander("✏️ Edit Existing User", expanded=False):
                selected_user_id = st.selectbox("Select User to Edit", users_df['emp_id'].tolist())
                
                if selected_user_id:
                    # Fetch current details
                    curr = run_query("SELECT * FROM users WHERE emp_id = ?", (selected_user_id,), fetch=True)[0]
                    roles_list = [r['name'] for r in run_query("SELECT name FROM roles", fetch=True)]
                    
                    with st.form("edit_other_user"):
                        e_name = st.text_input("Name", value=curr['name'])
                        e_role = st.selectbox("Role", roles_list, index=roles_list.index(curr['role']) if curr['role'] in roles_list else 0)
                        e_phone = st.text_input("Phone", value=curr['phone'] if curr['phone'] else "")
                        e_pass = st.text_input("Reset Password (leave blank to keep)", type="password")
                        
                        if st.form_submit_button("Update User"):
                            q = "UPDATE users SET name=?, role=?, phone=?"
                            p = [e_name, e_role, e_phone]
                            if e_pass:
                                q += ", password=?"
                                p.append(e_pass)
                            q += " WHERE emp_id=?"
                            p.append(selected_user_id)
                            
                            run_query(q, tuple(p))
                            st.success(f"Updated {selected_user_id}")
                            time.sleep(1)
                            st.rerun()

    # --- MANAGE ROLES TAB ---
    with tab_roles:
        st.info("Define custom roles and select which pages they can access.")
        
        all_pages = ["Dashboard", "Inventory", "Stock Operations", "Reports", "Shopping List", "User Management", "Settings"]
        
        # Existing Roles
        roles_data = run_query("SELECT * FROM roles", fetch=True)
        
        for role in roles_data:
            with st.expander(f"Role: {role['name'].upper()}", expanded=False):
                current_perms = json.loads(role['permissions'])
                
                with st.form(f"edit_role_{role['name']}"):
                    st.write(f"Permissions for {role['name']}")
                    new_perms = []
                    cols = st.columns(4)
                    for i, page in enumerate(all_pages):
                        with cols[i%4]:
                            if st.checkbox(page, value=(page in current_perms), key=f"perm_{role['name']}_{page}"):
                                new_perms.append(page)
                    
                    if st.form_submit_button("Save Permissions"):
                        run_query("UPDATE roles SET permissions = ? WHERE name = ?", (json.dumps(new_perms), role['name']))
                        st.success("Permissions updated!")
                        time.sleep(1)
                        st.rerun()

        # Create New Role
        st.markdown("---")
        with st.form("new_role_form"):
            st.subheader("Create Custom Role")
            new_role_name = st.text_input("Role Name (e.g., Student Leader)").lower().replace(" ", "_")
            st.write("Select Access:")
            
            nr_perms = []
            cols = st.columns(4)
            for i, page in enumerate(all_pages):
                with cols[i%4]:
                    if st.checkbox(page, key=f"new_role_{page}"):
                        nr_perms.append(page)
            
            if st.form_submit_button("Create Role"):
                if new_role_name:
                    run_query("INSERT INTO roles (name, permissions) VALUES (?, ?)", (new_role_name, json.dumps(nr_perms)))
                    st.success(f"Role '{new_role_name}' created!")
                    st.rerun()

# --- OTHER VIEWS (Simplified for brevity, logic remains same) ---

def view_inventory():
    st.title("📦 Inventory Manager")
    tab1, tab2, tab3 = st.tabs(["🔎 Search", "➕ Add", "📂 Upload"])
    with tab1:
        df = pd.read_sql_query("SELECT * FROM inventory", get_db_connection())
        st.dataframe(df, use_container_width=True)
    with tab2:
        with st.form("add"):
            name = st.text_input("Name")
            cat = st.selectbox("Category", ["Microcontrollers", "Sensors", "Motors", "Power", "Passive", "Tools"])
            qty = st.number_input("Qty", value=0)
            if st.form_submit_button("Add"):
                run_query("INSERT INTO inventory (name, category, quantity) VALUES (?, ?, ?)", (name, cat, qty))
                st.success("Added")
                st.rerun()
    with tab3:
        f = st.file_uploader("Excel", type=['xlsx'])
        if f and st.button("Upload"):
            d = pd.read_excel(f)
            # Dummy upload logic
            st.success("Uploaded")

def view_stock_ops():
    st.title("🔄 Operations")
    df = pd.read_sql_query("SELECT * FROM inventory", get_db_connection())
    if df.empty: return
    
    c1, c2 = st.columns(2)
    with c1:
        with st.form("in"):
            i = st.selectbox("Item", df['name'])
            q = st.number_input("Qty", 1)
            if st.form_submit_button("Stock In"):
                run_query("UPDATE inventory SET quantity = quantity + ? WHERE name = ?", (q, i))
                st.success("Updated")
                st.rerun()
    with c2:
        with st.form("out"):
            i = st.selectbox("Item", df['name'], key='o')
            q = st.number_input("Qty", 1)
            if st.form_submit_button("Stock Out"):
                run_query("UPDATE inventory SET quantity = quantity - ? WHERE name = ?", (q, i))
                st.success("Updated")
                st.rerun()

def view_reports():
    st.title("📈 Reports")
    df = pd.read_sql_query("SELECT * FROM transactions", get_db_connection())
    st.dataframe(df, use_container_width=True)

def view_shopping():
    st.title("🛒 Shopping List")
    df = pd.read_sql_query("SELECT * FROM inventory WHERE quantity < min_stock", get_db_connection())
    st.dataframe(df, use_container_width=True)

def view_profile():
    st.title("👤 My Profile")
    u = st.session_state.user
    with st.form("self_edit"):
        n = st.text_input("Name", u['name'])
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Save"):
            q = "UPDATE users SET name = ?"
            arr = [n]
            if p: 
                q += ", password = ?"
                arr.append(p)
            q += " WHERE id = ?"
            arr.append(u['id'])
            run_query(q, tuple(arr))
            st.success("Updated")
            st.rerun()

def view_settings():
    st.title("⚙️ Settings")
    t = st.selectbox("Theme", list(THEMES.keys()))
    if t != st.session_state.theme:
        st.session_state.theme = t
        st.rerun()

# --- MAIN CONTROLLER ---

def main():
    init_db()
    
    # 1. Session Check (Token in URL?)
    if 'user' not in st.session_state:
        st.session_state.user = None
        
    if st.session_state.user is None and 'session_token' in st.query_params:
        token = st.query_params['session_token']
        user = validate_session(token)
        if user:
            st.session_state.user = dict(user)
            st.toast("Session Restored 🔄")
        else:
            # Invalid token
            del st.query_params['session_token']

    # 2. Login Screen
    if st.session_state.user is None:
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.markdown(f"<div class='login-box'><h1 style='color:{current_theme['primary']};'>TSRS</h1><h3>Inventory</h3></div>", unsafe_allow_html=True)
            
            with st.form("login"):
                u = st.text_input("Employee ID")
                p = st.text_input("Password", type="password")
                if st.form_submit_button("Login", type="primary", use_container_width=True):
                    # Check Credentials
                    user_data = run_query("SELECT * FROM users WHERE emp_id = ? AND password = ?", (u, p), fetch=True)
                    if user_data:
                        user = user_data[0]
                        st.session_state.user = dict(user)
                        
                        # Create Session
                        token = create_session(user['id'])
                        st.query_params['session_token'] = token
                        
                        st.rerun()
                    else:
                        st.error("Invalid Credentials")

    # 3. App Interface
    else:
        # Get Permissions
        perms = get_permissions(st.session_state.user['role'])
        
        # Sidebar
        with st.sidebar:
            st.header(f"Welcome, {st.session_state.user['name']}")
            st.caption(f"Role: {st.session_state.user['role']}")
            st.markdown("---")
            
            # Dynamic Menu based on Permissions
            nav_map = {
                "Dashboard": "📊", "Inventory": "📦", "Stock Operations": "🔄", 
                "Reports": "📈", "Shopping List": "🛒", "User Management": "👥", 
                "Settings": "⚙️"
            }
            
            # Always allow Profile
            if st.button("👤 My Profile", use_container_width=True):
                st.session_state.current_view = "My Profile"
                st.rerun()

            for page, icon in nav_map.items():
                if page in perms:
                    if st.button(f"{icon} {page}", use_container_width=True):
                        st.session_state.current_view = page
                        st.rerun()

            st.markdown("---")
            if st.button("🚪 Logout", use_container_width=True):
                logout_user()

        # Routing
        if 'current_view' not in st.session_state:
            st.session_state.current_view = "Dashboard"
        
        v = st.session_state.current_view
        
        # Access Control Check
        if v != "My Profile" and v not in perms:
            st.error("⛔ Access Denied")
        else:
            if v == "Dashboard": view_dashboard()
            elif v == "Inventory": view_inventory()
            elif v == "Stock Operations": view_stock_ops()
            elif v == "Reports": view_reports()
            elif v == "Shopping List": view_shopping()
            elif v == "User Management": view_user_management()
            elif v == "My Profile": view_profile()
            elif v == "Settings": view_settings()

if __name__ == '__main__':
    main()
