import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime
import time

# --- CONFIGURATION & STYLING ---
st.set_page_config(page_title="RoboLab Inventory", page_icon="🤖", layout="wide")

# Custom CSS to mimic the previous UI look
st.markdown("""
<style>
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #111827;
        color: white;
    }
    section[data-testid="stSidebar"] .stButton button {
        width: 100%;
        text-align: left;
        background-color: transparent;
        color: #d1d5db;
        border: none;
    }
    section[data-testid="stSidebar"] .stButton button:hover {
        background-color: #374151;
        color: white;
    }
    
    /* Metrics styling */
    div[data-testid="stMetric"] {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border: 1px solid #e5e7eb;
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #1f2937; 
        font-family: 'Inter', sans-serif;
    }
</style>
""", unsafe_allow_html=True)

# --- DATABASE FUNCTIONS ---

def get_db_connection():
    conn = sqlite3.connect('robolab.db', check_same_thread=False)
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 emp_id TEXT UNIQUE NOT NULL,
                 name TEXT NOT NULL,
                 password TEXT NOT NULL,
                 role TEXT NOT NULL)''')
    
    # Inventory Table
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 name TEXT NOT NULL,
                 category TEXT,
                 location TEXT,
                 quantity INTEGER DEFAULT 0,
                 min_stock INTEGER DEFAULT 5,
                 price REAL DEFAULT 0.0)''')
    
    # Transactions Table
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 item_id INTEGER,
                 item_name TEXT,
                 type TEXT,
                 quantity INTEGER,
                 user TEXT,
                 timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                 notes TEXT)''')
    
    # Seed Admin User if empty
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        # Default Admin: admin / admin123 (hashed in real app, plain for demo)
        c.execute("INSERT INTO users (emp_id, name, password, role) VALUES (?, ?, ?, ?)",
                  ('admin', 'System Admin', 'admin123', 'admin'))
        c.execute("INSERT INTO users (emp_id, name, password, role) VALUES (?, ?, ?, ?)",
                  ('assistant', 'Lab Assistant', '123', 'assistant'))
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
            return data
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Database Error: {e}")
        conn.close()
        return False

def get_inventory_df():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM inventory", conn)
    conn.close()
    return df

# --- AUTHENTICATION ---

def login_user(emp_id, password):
    user = run_query("SELECT * FROM users WHERE emp_id = ? AND password = ?", (emp_id, password), fetch=True)
    if user:
        return {"id": user[0][0], "emp_id": user[0][1], "name": user[0][2], "role": user[0][4]}
    return None

# --- VIEWS ---

def view_dashboard():
    st.title("📊 Dashboard")
    df = get_inventory_df()
    
    if df.empty:
        st.info("Inventory is empty. Add items to see stats.")
        return

    # Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Components", int(df['quantity'].sum()))
    col2.metric("Inventory Value", f"₹{df.apply(lambda x: x['quantity'] * x['price'], axis=1).sum():,.2f}")
    
    low_stock_count = df[df['quantity'] <= df['min_stock']].shape[0]
    col3.metric("Low Stock Alerts", low_stock_count, delta_color="inverse")

    # Low Stock Table
    st.subheader("⚠️ Low Stock Items")
    low_stock = df[df['quantity'] <= df['min_stock']][['name', 'quantity', 'min_stock', 'location']]
    if not low_stock.empty:
        st.dataframe(low_stock, use_container_width=True)
    else:
        st.success("All items are well stocked.")

    # Recent Activity
    st.subheader("🕒 Recent Activity")
    conn = get_db_connection()
    trans_df = pd.read_sql_query("SELECT item_name, type, quantity, user, timestamp, notes FROM transactions ORDER BY timestamp DESC LIMIT 10", conn)
    conn.close()
    if not trans_df.empty:
        st.dataframe(trans_df, use_container_width=True)

def view_inventory():
    st.title("📦 Inventory Management")
    
    # Tabs for Actions
    tab1, tab2, tab3 = st.tabs(["View / Search", "Add New Item", "Bulk Upload (Excel)"])
    
    with tab1:
        df = get_inventory_df()
        
        # Filters
        col1, col2 = st.columns(2)
        search = col1.text_input("Search by Name")
        category = col2.selectbox("Filter by Category", ["All"] + list(df['category'].unique()) if not df.empty else ["All"])
        
        if not df.empty:
            if search:
                df = df[df['name'].str.contains(search, case=False)]
            if category != "All":
                df = df[df['category'] == category]
            
            st.dataframe(df, use_container_width=True)
            
            # Delete Action
            if st.session_state.user['role'] == 'admin':
                with st.expander("Delete Item"):
                    del_id = st.selectbox("Select Item to Delete", df['name'].tolist())
                    if st.button("Delete Selected Item"):
                        # Get ID
                        item_id = df[df['name'] == del_id]['id'].values[0]
                        run_query("DELETE FROM inventory WHERE id = ?", (int(item_id),))
                        st.rerun()

    with tab2:
        with st.form("add_item_form"):
            col1, col2 = st.columns(2)
            name = col1.text_input("Item Name")
            category = col2.selectbox("Category", ["Microcontrollers", "Sensors", "Motors", "Power", "Passive", "Tools", "Others"])
            location = col1.text_input("Location / Shelf")
            price = col2.number_input("Price (₹)", min_value=0.0)
            qty = col1.number_input("Initial Quantity", min_value=0)
            min_stock = col2.number_input("Min Stock Alert Level", min_value=0)
            
            if st.form_submit_button("Add Item"):
                if name:
                    run_query("INSERT INTO inventory (name, category, location, quantity, min_stock, price) VALUES (?, ?, ?, ?, ?, ?)",
                              (name, category, location, qty, min_stock, price))
                    st.success(f"Added {name}!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Name is required.")

    with tab3:
        st.write("Upload an Excel file (.xlsx) with columns: `Name`, `Category`, `Location`, `Quantity`, `MinStock`, `Price`")
        uploaded_file = st.file_uploader("Choose Excel File", type=['xlsx'])
        if uploaded_file:
            try:
                excel_data = pd.read_excel(uploaded_file)
                st.dataframe(excel_data.head())
                if st.button("Confirm Upload"):
                    count = 0
                    for index, row in excel_data.iterrows():
                        # Basic validation
                        item_name = row.get('Name') or row.get('name')
                        if item_name:
                            run_query("INSERT INTO inventory (name, category, location, quantity, min_stock, price) VALUES (?, ?, ?, ?, ?, ?)",
                                      (item_name, 
                                       row.get('Category', 'Others'), 
                                       row.get('Location', 'Unknown'), 
                                       row.get('Quantity', 0), 
                                       row.get('MinStock', 5), 
                                       row.get('Price', 0.0)))
                            count += 1
                    st.success(f"Successfully imported {count} items.")
                    time.sleep(2)
                    st.rerun()
            except Exception as e:
                st.error(f"Error reading file: {e}")

def view_stock_actions():
    st.title("🔄 Stock Operations")
    
    df = get_inventory_df()
    if df.empty:
        st.warning("No items in inventory.")
        return

    col1, col2 = st.columns(2)
    
    with col1:
        st.info("📥 Stock In (Add)")
        with st.form("stock_in"):
            item_in = st.selectbox("Select Item", df['name'].tolist(), key="in_select")
            qty_in = st.number_input("Quantity to Add", min_value=1, key="in_qty")
            notes_in = st.text_input("Notes (e.g., New Purchase)", key="in_notes")
            
            if st.form_submit_button("Add Stock"):
                curr_item = df[df['name'] == item_in].iloc[0]
                new_qty = int(curr_item['quantity'] + qty_in)
                
                # Update Inventory
                run_query("UPDATE inventory SET quantity = ? WHERE id = ?", (new_qty, int(curr_item['id'])))
                
                # Log Transaction
                run_query("INSERT INTO transactions (item_id, item_name, type, quantity, user, notes) VALUES (?, ?, ?, ?, ?, ?)",
                          (int(curr_item['id']), curr_item['name'], 'in', qty_in, st.session_state.user['name'], notes_in))
                
                st.success(f"Added {qty_in} to {item_in}")
                time.sleep(1)
                st.rerun()

    with col2:
        st.error("📤 Stock Out (Deduct)")
        with st.form("stock_out"):
            item_out = st.selectbox("Select Item", df['name'].tolist(), key="out_select")
            qty_out = st.number_input("Quantity to Remove", min_value=1, key="out_qty")
            notes_out = st.text_input("Notes (e.g., Project Usage)", key="out_notes")
            
            if st.form_submit_button("Deduct Stock"):
                curr_item = df[df['name'] == item_out].iloc[0]
                
                if curr_item['quantity'] < qty_out:
                    st.error(f"Insufficient stock! Current: {curr_item['quantity']}")
                else:
                    new_qty = int(curr_item['quantity'] - qty_out)
                    
                    # Update Inventory
                    run_query("UPDATE inventory SET quantity = ? WHERE id = ?", (new_qty, int(curr_item['id'])))
                    
                    # Log Transaction
                    run_query("INSERT INTO transactions (item_id, item_name, type, quantity, user, notes) VALUES (?, ?, ?, ?, ?, ?)",
                              (int(curr_item['id']), curr_item['name'], 'out', qty_out, st.session_state.user['name'], notes_out))
                    
                    st.success(f"Removed {qty_out} from {item_out}")
                    time.sleep(1)
                    st.rerun()

def view_shopping_list():
    st.title("🛒 Shopping List")
    df = get_inventory_df()
    
    to_buy = df[df['quantity'] < df['min_stock']].copy()
    
    if to_buy.empty:
        st.success("Everything is well stocked! No shopping needed.")
        return
        
    to_buy['Required'] = to_buy['min_stock'] - to_buy['quantity']
    to_buy['Est. Cost'] = to_buy['Required'] * to_buy['price']
    
    total_cost = to_buy['Est. Cost'].sum()
    
    st.metric("Estimated Total Cost", f"₹{total_cost:,.2f}")
    
    st.dataframe(to_buy[['name', 'category', 'quantity', 'min_stock', 'Required', 'price', 'Est. Cost']], use_container_width=True)
    
    csv = to_buy.to_csv(index=False).encode('utf-8')
    st.download_button("Download List as CSV", csv, "shopping_list.csv", "text/csv")

def view_reports():
    st.title("📈 Reports")
    
    conn = get_db_connection()
    trans_df = pd.read_sql_query("SELECT * FROM transactions", conn)
    conn.close()
    
    if trans_df.empty:
        st.info("No transaction data available yet.")
        return
        
    trans_df['timestamp'] = pd.to_datetime(trans_df['timestamp'])
    
    # Chart 1: Movements by Type
    st.subheader("Transaction Volume")
    type_counts = trans_df['type'].value_counts()
    st.bar_chart(type_counts)
    
    # Chart 2: Top Active Items
    st.subheader("Most Active Components")
    top_items = trans_df['item_name'].value_counts().head(10)
    st.bar_chart(top_items)
    
    # Table: Full History with Timestamps
    st.subheader("Detailed Transaction Log")
    st.dataframe(trans_df.sort_values('timestamp', ascending=False), use_container_width=True)

def view_users():
    st.title("👥 User Management")
    
    if st.session_state.user['role'] != 'admin':
        st.error("Access Denied. Admin only.")
        return

    conn = get_db_connection()
    users_df = pd.read_sql_query("SELECT id, emp_id, name, role FROM users", conn)
    conn.close()
    
    st.dataframe(users_df, use_container_width=True)
    
    with st.form("add_user"):
        st.subheader("Add New User")
        col1, col2 = st.columns(2)
        new_emp_id = col1.text_input("Employee ID")
        new_name = col2.text_input("Full Name")
        new_pass = col1.text_input("Password", type="password")
        new_role = col2.selectbox("Role", ["assistant", "admin"])
        
        if st.form_submit_button("Create User"):
            if run_query("INSERT INTO users (emp_id, name, password, role) VALUES (?, ?, ?, ?)", 
                         (new_emp_id, new_name, new_pass, new_role)):
                st.success("User created successfully")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Error creating user. ID might already exist.")

def view_profile():
    st.title("👤 My Profile")
    user = st.session_state.user
    
    st.write(f"**Employee ID:** {user['emp_id']}")
    st.write(f"**Role:** {user['role'].capitalize()}")
    
    with st.form("edit_profile"):
        new_name = st.text_input("Update Name", value=user['name'])
        new_pass = st.text_input("Update Password (leave blank to keep current)", type="password")
        
        if st.form_submit_button("Update Profile"):
            query = "UPDATE users SET name = ?"
            params = [new_name]
            
            if new_pass:
                query += ", password = ?"
                params.append(new_pass)
            
            query += " WHERE id = ?"
            params.append(user['id'])
            
            run_query(query, tuple(params))
            
            # Update Session
            st.session_state.user['name'] = new_name
            st.success("Profile Updated!")
            time.sleep(1)
            st.rerun()

# --- MAIN APP LOGIC ---

def main():
    init_db()
    
    if 'user' not in st.session_state:
        st.session_state.user = None

    if st.session_state.user is None:
        # Login Screen
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.markdown("<h1 style='text-align: center; color: #2563EB;'>🤖 RoboLab Login</h1>", unsafe_allow_html=True)
            with st.form("login_form"):
                emp_id = st.text_input("Employee ID")
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Login")
                
                if submit:
                    user = login_user(emp_id, password)
                    if user:
                        st.session_state.user = user
                        st.rerun()
                    else:
                        st.error("Invalid Credentials")
            st.info("Defaults: `admin` / `admin123` | `assistant` / `123`")
    else:
        # App Layout
        with st.sidebar:
            st.header(f"Welcome, {st.session_state.user['name']}")
            st.caption(f"Role: {st.session_state.user['role'].upper()}")
            
            st.markdown("---")
            
            menu = st.radio("Navigation", 
                ["Dashboard", "Inventory", "Stock Operations", "Reports", "Shopping List", "User Management", "My Profile"],
                label_visibility="collapsed"
            )
            
            st.markdown("---")
            if st.button("Log Out"):
                st.session_state.user = None
                st.rerun()
        
        # Router
        if menu == "Dashboard":
            view_dashboard()
        elif menu == "Inventory":
            view_inventory()
        elif menu == "Stock Operations":
            view_stock_actions()
        elif menu == "Reports":
            view_reports()
        elif menu == "Shopping List":
            view_shopping_list()
        elif menu == "User Management":
            view_users()
        elif menu == "My Profile":
            view_profile()

if __name__ == '__main__':
    main()
