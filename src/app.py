import streamlit as st
import os
from typing import Dict, TypedDict


# Set the pages directory to be relative to this file
os.environ["STREAMLIT_PAGES_DIR"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pages")

class ToolConfig(TypedDict):
    name: str
    description: str
    category: str

# Tool configurations
TOOL_CONFIG: Dict[str, ToolConfig] = {
    "flickr.py": {
        "name": "Flickr Downloader",
        "description": "Download images from Flickr pages in bulk",
        "category": "Image tools"
    }
}

def load_tools():
    """Load tool configurations from the pages directory."""
    # Get the absolute path to the pages directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    pages_dir = os.path.join(current_dir, "pages")
    tools_by_category = {}
    
    if not os.path.exists(pages_dir):
        st.error(f"Pages directory not found at: {pages_dir}")
        return tools_by_category
    
    for filename in os.listdir(pages_dir):
        if filename.endswith(".py"):
            tool_config = TOOL_CONFIG.get(filename, {
                "name": os.path.splitext(filename)[0].replace("_", " ").title(),
                "description": "",
                "category": "Other tools"
            })
            category = tool_config["category"]
            if category not in tools_by_category:
                tools_by_category[category] = []
            tools_by_category[category].append((filename, tool_config))
    
    return tools_by_category

def main():
    st.set_page_config(
        page_title="Tools",
        initial_sidebar_state="collapsed"
    )

    # Add custom CSS
    st.markdown("""
        <style>
        .main {
            max-width: 900px;
            padding: 2rem;
            margin: 0 auto;
        }
        .tool-list {
            list-style-type: none;
            padding-left: 1.5rem;
        }
        .tool-item {
            margin-bottom: 1rem;
            display: flex;
            align-items: baseline;
            font-size: 1.2rem;
        }
        .tool-item:before {
            content: "•";
            display: inline-block;
            width: 1em;
            margin-left: -1em;
        }
        .tool-link {
            margin-right: 0.5rem;
            font-weight: 500;
        }
        .tool-description {
            opacity: 0.8;
        }
        </style>
    """, unsafe_allow_html=True)

    tools_by_category = load_tools()
    
    st.markdown("# Tools\n")
    st.markdown("Inspired by [Simon Willion's Tools](https://tools.simonwillison.net/)")
    
    for category, tools in tools_by_category.items():
        st.markdown(f"## {category}")
        for filename, config in tools:
            label = f"{config['name']}"
            if config['description']:
                label += f" - *{config['description']}*"
            st.page_link(f"pages/{filename}", label=label)

if __name__ == "__main__":
    main()