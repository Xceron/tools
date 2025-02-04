import streamlit as st
import bibtexparser
import requests
import time
import re
from typing import Dict, List, Optional
import urllib.request
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bparser import BibTexParser


def clean_title(title: str) -> str:
    """Clean title for search by removing special characters and common words."""
    clean = title.replace("{", "").replace("}", "").replace("--", " ").replace("-", " ")
    clean = "".join(c for c in clean if c.isalnum() or c.isspace())
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
                retry_after = int(response.headers.get("Retry-After", 30))
                st.warning(f"Rate limited by DBLP. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                retry_count += 1
                continue

            response.raise_for_status()
            data = response.json()
            hits = data.get("result", {}).get("hits", {}).get("hit", [])
            results = [hit.get("info", {}) for hit in hits]
            with st.spinner("Waiting 2 seconds before next request..."):
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
        author_list = authors.get("author", [])
    else:
        author_list = authors
    if isinstance(author_list, str):
        return author_list
    elif isinstance(author_list, list):
        author_names = [
            author.get("text", "N/A") if isinstance(author, dict) else str(author)
            for author in author_list
        ]
        return "; ".join(filter(None, author_names))
    return "N/A"


def format_entry_for_display(entry: Dict, is_dblp: bool = False) -> str:
    """Format an entry for display."""
    if is_dblp:
        return f"""📄 Title:
{entry.get("title", "N/A")}

👥 Authors:
{get_author_str(entry.get("authors"))}

📅 Year: {entry.get("year", "N/A")}
📍 Venue: {entry.get("venue", "N/A")}
📑 Type: {entry.get("type", "N/A")}
🔗 DOI: {entry.get("doi", "N/A")}
🌐 URL: {entry.get("url", "N/A")}"""
    else:
        return f"""📄 Title:
{entry.get("title", "N/A")}

👥 Authors:
{entry.get("author", "N/A")}

📅 Year: {entry.get("year", "N/A")}
📑 Type: {entry.get("ENTRYTYPE", "N/A")}
🏷️ Citation Key: {entry.get("ID", "N/A")}"""


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
    dblp_url = dblp_entry.get("url")
    if dblp_url:
        bib_entry_str = get_bib_from_dblp_url(dblp_url)
        if bib_entry_str:
            bib_parser = bibtexparser.bparser.BibTexParser(common_strings=True)
            bib_database = bibtexparser.loads(bib_entry_str, parser=bib_parser)
            if bib_database.entries:
                fetched_bib_entry = bib_database.entries[0]

                # Use the fetched entry but keep the original ID
                merged = fetched_bib_entry
                merged["ID"] = bibtex_entry.get("ID")
                return merged

    # Fallback to merging fields if direct .bib fetching fails
    field_mapping = {
        "title": "title",
        "year": "year",
        "doi": "doi",
        "url": "url",
        "venue": "journal",
        "type": "note",
    }

    for dblp_field, bibtex_field in field_mapping.items():
        if dblp_field in dblp_entry and dblp_entry[dblp_field]:
            merged[bibtex_field] = dblp_entry[dblp_field]

    if "authors" in dblp_entry:
        merged["author"] = get_author_str(dblp_entry["authors"])

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
    if "note" in entry:
        entry["note"] = f"{entry['note']}. {note}"
    else:
        entry["note"] = note
    return entry


# ----------------------
# MAIN PAGE CONTENT
# ----------------------


def clean_bibtex(bib_to_format: str) -> BibDatabase:
    """Clean BibTeX string by replacing field=VALUE with field={VALUE}."""

    def replace_macro(match):
        field, value = match.groups()
        return f"{field}={{{value}}}"

    # Pattern matches field=VALUE where VALUE is alphanumeric
    pattern = r"([a-zA-Z]+)\s*=\s*([A-Za-z0-9]+(?!\{|\"))"
    bibtex_str = re.sub(pattern, replace_macro, bib_to_format)
    parser = BibTexParser()
    bib_database = bibtexparser.loads(bibtex_str, parser)
    return bib_database


st.title("BibTeX DBLP Resolver")
st.write("Upload your BibTeX file and resolve entries with DBLP.")

uploaded_file = st.file_uploader("Choose a BibTeX file", type=["bib"])

if uploaded_file:
    # Initialize session state
    if "processed_entries" not in st.session_state:
        parser = BibTexParser(common_strings=True)
        bib_database = clean_bibtex(uploaded_file.getvalue().decode())
        
        st.session_state.processed_entries = []
        st.session_state.conflict_entries = []
        st.session_state.current_entry = 0
        st.session_state.current_conflict = 0
        st.session_state.processing_done = False
        st.session_state.resolution_done = False
        st.session_state.bib_database = bib_database

    # Processing phase
    if not st.session_state.processing_done:
        progress_text = st.empty()
        progress_bar = st.progress(0.0)
        bib_database = st.session_state.bib_database

        while st.session_state.current_entry < len(bib_database.entries):
            entry = bib_database.entries[st.session_state.current_entry]
            
            # Update progress
            progress = (st.session_state.current_entry + 1) / len(bib_database.entries)
            progress_text.markdown(f"**Processing entries:** {st.session_state.current_entry + 1}/{len(bib_database.entries)}")
            progress_bar.progress(progress)

            # Search DBLP
            with st.spinner(f"Searching DBLP for '{entry.get('title', '')}'..."):
                dblp_results = search_dblp(entry.get("title", ""))

            # Process results
            if dblp_results:
                # Find exact matches
                original_clean = clean_title(entry.get("title", ""))
                exact_matches = []
                other_matches = []

                for result in dblp_results:
                    result_clean = clean_title(result.get("title", ""))
                    overlap = set(original_clean.split()) & set(result_clean.split())
                    total_words = set(original_clean.split()) | set(result_clean.split())
                    similarity = len(overlap) / len(total_words) if total_words else 0

                    if similarity > 0.8:
                        exact_matches.append(result)
                    else:
                        other_matches.append(result)

                # Sort exact matches to prefer non-CoRR
                exact_matches.sort(key=lambda x: "CoRR" in x.get("venue", "") or "arXiv" in x.get("venue", ""))

                if exact_matches:
                    merged = merge_entries(entry, exact_matches[0])
                    st.session_state.processed_entries.append(merged)
                else:
                    st.session_state.conflict_entries.append({
                        "original": entry,
                        "matches": dblp_results
                    })
            else:
                # No matches found
                st.session_state.processed_entries.append(add_todo_note(entry))

            st.session_state.current_entry += 1

        st.session_state.processing_done = True
        st.rerun()

    # Conflict resolution phase
    elif not st.session_state.resolution_done:
        progress_text = st.empty()
        progress_bar = st.progress(0.0)
        total_conflicts = len(st.session_state.get('conflict_entries', []))

        if total_conflicts > 0:
            # Ensure current_conflict is within valid range
            st.session_state.current_conflict = max(0, min(st.session_state.current_conflict, total_conflicts - 1))
            
            conflict = st.session_state.conflict_entries[st.session_state.current_conflict]
            original = conflict["original"]
            matches = conflict["matches"]

            # Display conflict
            progress = (st.session_state.current_conflict + 1) / total_conflicts
            progress_text.markdown(f"**Resolving conflicts:** {st.session_state.current_conflict + 1}/{total_conflicts}")
            progress_bar.progress(progress)

            st.subheader("Original Entry")
            st.text(format_entry_for_display(original))

            st.subheader("DBLP Matches")
            for idx, match in enumerate(matches[:5]):
                col1, col2 = st.columns([0.1, 0.9])
                with col1:
                    if st.button(f"{idx+1}", key=f"match_{idx}"):
                        merged = merge_entries(original, match)
                        st.session_state.processed_entries.append(merged)
                        st.session_state.current_conflict += 1
                        st.rerun()
                with col2:
                    st.text(format_entry_for_display(match, is_dblp=True))

            if st.button("Skip", key="skip"):
                # Mark this conflict as skipped/resolved by adding the original entry
                st.session_state.processed_entries.append(conflict["original"])
                # Remove the conflict from the list so it won’t be processed again
                st.session_state.conflict_entries.pop(st.session_state.current_conflict)
                st.rerun()

        else:
            st.success("All conflicts resolved!")
            st.session_state.current_conflict = 0
            st.session_state.resolution_done = True
            st.rerun()

    # Final output
    else:
        st.success("All entries processed!")
        db = BibDatabase()
        db.entries = st.session_state.processed_entries
        bibtex_str = bibtexparser.dumps(db)

        st.download_button(
            label="Download processed BibTeX",
            data=bibtex_str,
            file_name="processed.bib",
            mime="text/plain",
        )

        if st.button("Process another file"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]