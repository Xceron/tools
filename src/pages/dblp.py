import streamlit as st
import bibtexparser
from pathlib import Path
import requests
import time
import json
import re
from datetime import datetime
from typing import Dict, List, Optional
import urllib.request
from bibtexparser.bibdatabase import BibDatabase

def clean_title(title: str) -> str:
    """Clean title for search by removing special characters and common words."""
    clean = title.replace('{', '').replace('}', '').replace('--', ' ').replace('-', ' ')
    clean = ''.join(c for c in clean if c.isalnum() or c.isspace())
    clean = clean.lower()
    return clean

def search_dblp(title: str, num_results: int = 5, max_retries: int = 5) -> List[Dict]:
    """Search DBLP and return results."""
    clean_search_title = clean_title(title)
    url = "https://dblp.org/search/publ/api"
    params = {
        "q": clean_search_title,
        "format": "json",
        "h": num_results,
    }
    
    retry_count = 0
    while retry_count < max_retries:
        try:
            response = requests.get(url, params=params)
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 30))
                st.warning(f"Rate limited by DBLP. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                retry_count += 1
                continue
            
            response.raise_for_status()
            data = response.json()
            hits = data.get('result', {}).get('hits', {}).get('hit', [])
            results = [hit.get('info', {}) for hit in hits]
            with st.spinner('Waiting 2 seconds before next request...'):
                time.sleep(2)
            return results
        except requests.exceptions.RequestException as e:
            if retry_count < max_retries - 1:
                st.error(f"Error accessing DBLP: {e}. Retrying...")
                retry_count += 1
            else:
                st.error(f"Failed to access DBLP after {max_retries} attempts: {e}")
                return []

def get_author_str(authors) -> str:
    """Extract author string from DBLP author field."""
    if not authors:
        return "N/A"
    if isinstance(authors, str):
        return authors
    if isinstance(authors, dict):
        author_list = authors.get('author', [])
    else:
        author_list = authors
    if isinstance(author_list, str):
        return author_list
    elif isinstance(author_list, list):
        author_names = [author.get('text', 'N/A') if isinstance(author, dict) else str(author) for author in author_list]
        return "; ".join(filter(None, author_names))
    return "N/A"

def format_entry_for_display(entry: Dict, is_dblp: bool = False) -> str:
    """Format an entry for display."""
    if is_dblp:
        return f"""📄 Title:
{entry.get('title', 'N/A')}

👥 Authors:
{get_author_str(entry.get('authors'))}

📅 Year: {entry.get('year', 'N/A')}
📍 Venue: {entry.get('venue', 'N/A')}
📑 Type: {entry.get('type', 'N/A')}
🔗 DOI: {entry.get('doi', 'N/A')}
🌐 URL: {entry.get('url', 'N/A')}"""
    else:
        return f"""📄 Title:
{entry.get('title', 'N/A')}

👥 Authors:
{entry.get('author', 'N/A')}

📅 Year: {entry.get('year', 'N/A')}
📑 Type: {entry.get('ENTRYTYPE', 'N/A')}
🏷️ Citation Key: {entry.get('ID', 'N/A')}"""

def get_bib_from_dblp_url(dblp_url: str) -> Optional[str]:
    """Fetches the .bib entry from DBLP using the DBLP URL."""
    try:
        bib_url = dblp_url.replace("/rec/", "/rec/bibtex/")
        with urllib.request.urlopen(bib_url) as response:
            bib_entry = response.read().decode()
            if "not found" not in bib_entry.lower():
                return bib_entry
            else:
                st.warning(f"Could not retrieve .bib for {dblp_url}")
                return None
    except Exception as e:
        st.error(f"Error fetching .bib from {bib_url}: {e}")
        return None

def merge_entries(bibtex_entry: Dict, dblp_entry: Dict) -> Dict:
    """Merge DBLP entry into BibTeX entry, using fetched bib if available."""
    merged = bibtex_entry.copy()
    
    # Fetch .bib from DBLP URL
    dblp_url = dblp_entry.get('url')
    if dblp_url:
        bib_entry_str = get_bib_from_dblp_url(dblp_url)
        if bib_entry_str:
            bib_parser = bibtexparser.bparser.BibTexParser(common_strings=True)
            bib_database = bibtexparser.loads(bib_entry_str, parser=bib_parser)
            if bib_database.entries:
                fetched_bib_entry = bib_database.entries[0]
                
                # Use the fetched entry but keep the original ID
                merged = fetched_bib_entry
                merged['ID'] = bibtex_entry.get('ID')
                return merged

    # Fallback to merging fields if direct .bib fetching fails
    field_mapping = {
        'title': 'title',
        'year': 'year',
        'doi': 'doi',
        'url': 'url',
        'venue': 'journal',
        'type': 'note',
    }

    for dblp_field, bibtex_field in field_mapping.items():
        if dblp_field in dblp_entry and dblp_entry[dblp_field]:
            merged[bibtex_field] = dblp_entry[dblp_field]

    if 'authors' in dblp_entry:
        merged['author'] = get_author_str(dblp_entry['authors'])

    return merged

def handle_accept(entry, dblp_entry):
    merged_entry = merge_entries(entry, dblp_entry)
    st.session_state.processed_entries.append(merged_entry)
    st.session_state.current_entry += 1

def handle_decline(entry, dblp_entry=None):
    st.session_state.processed_entries.append(entry)
    st.session_state.current_entry += 1

def add_todo_note(entry: Dict) -> Dict:
    """Add a TODO note to the entry."""
    entry = entry.copy()
    note = "TODO: Search for this entry manually in DBLP"
    if 'note' in entry:
        entry['note'] = f"{entry['note']}. {note}"
    else:
        entry['note'] = note
    return entry

# ----------------------
# MAIN PAGE CONTENT
# ----------------------

st.title("BibTeX DBLP Resolver")
st.write("Upload your BibTeX file and resolve entries with DBLP.")

uploaded_file = st.file_uploader("Choose a BibTeX file", type=['bib'])

if uploaded_file:
    parser = bibtexparser.bparser.BibTexParser(common_strings=True)
    bib_database = bibtexparser.loads(uploaded_file.getvalue().decode())
    
    if 'current_entry' not in st.session_state:
        st.session_state.current_entry = 0
        st.session_state.processed_entries = []
        st.session_state.processing_done = False

    progress_text = st.empty()
    progress_bar = st.progress(0.0)

    if not st.session_state.processing_done:
        if st.session_state.current_entry < len(bib_database.entries):
            entry = bib_database.entries[st.session_state.current_entry]
            
            progress_fraction = (st.session_state.current_entry + 1) / len(bib_database.entries)
            progress_text.write(f"Processing entry {st.session_state.current_entry + 1} of {len(bib_database.entries)}")
            progress_bar.progress(progress_fraction)
            
            with st.spinner(f"Searching DBLP for '{entry['title']}'..."):
                dblp_results = search_dblp(entry['title'])
            
            if dblp_results:
                exact_matches = []
                other_matches = []
                original_clean = clean_title(entry['title'])
                
                for result in dblp_results:
                    result_clean = clean_title(result['title'])
                    overlap = set(original_clean.split()) & set(result_clean.split())
                    total_words = set(original_clean.split()) | set(result_clean.split())
                    similarity = len(overlap) / len(total_words) if total_words else 0
                    
                    if similarity > 0.8:
                        exact_matches.append(result)
                    else:
                        other_matches.append(result)
                
                exact_matches.sort(key=lambda x: 'CoRR' in x.get('venue', '') or 'arXiv' in x.get('venue', ''))
                
                if exact_matches:
                    handle_accept(entry, exact_matches[0])
                else:
                    st.subheader("Similar Matches Found")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Original Entry**")
                        st.text(format_entry_for_display(entry))
                    with col2:
                        for i, result in enumerate(dblp_results):
                            st.markdown(f"**Match {i + 1}** (Press {i + 1})")
                            st.text(format_entry_for_display(result, True))
                            if i < len(dblp_results) - 1:
                                st.markdown("---")
                    
                    cols = st.columns(min(len(dblp_results) + 1, 6))
                    for i in range(min(len(dblp_results), 5)):
                        with cols[i]:
                            if st.button(f"{i + 1}"):
                                handle_accept(entry, dblp_results[i])
                    with cols[-1]:
                        if st.button("❌"):
                            handle_decline(entry)
            else:
                st.subheader("No Matches Found")
                st.text(format_entry_for_display(entry))
                st.warning("This entry will be marked with a TODO note for manual search.")
                handle_decline(add_todo_note(entry))

            if st.session_state.current_entry < len(bib_database.entries):
                st.rerun()
            else:
                st.session_state.processing_done = True
                st.rerun()
    
    if st.session_state.processing_done:
        progress_bar.progress(1.0)
        progress_text.write("Processing complete!")
        st.success("All entries processed!")
        
        db = BibDatabase()
        db.entries = st.session_state.processed_entries
        bibtex_str = bibtexparser.dumps(db)
        
        st.download_button(
            label="Download processed BibTeX",
            data=bibtex_str,
            file_name="processed.bib",
            mime="text/plain"
        )
        
        if st.button("Process another file"):
            del st.session_state.current_entry
            del st.session_state.processed_entries
            st.session_state.processing_done = False
            st.rerun()
