import streamlit as st
import streamlit.components.v1 as components
import os

# Set page layout to wide to utilize full screen
st.set_page_config(layout="wide", page_title="RoboLab Inventory")

# Get the absolute path to the directory where this script is located
current_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(current_dir, "index.html")

try:
    # Read the HTML file with explicit utf-8 encoding
    with open(file_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Render the HTML content
    # height=1000 ensures enough space, scrolling=True allows internal scrolling if needed
    components.html(html_content, height=1000, scrolling=True)

except FileNotFoundError:
    st.error(f"Error: Could not find 'index.html'.")
    st.code(f"Looking for file at: {file_path}")
    st.info("Please ensure 'index.html' exists in the same directory as 'streamlit_app.py'.")
