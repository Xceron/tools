import streamlit as st
import bibtexparser
import requests
import time
from typing import Dict, List
from streamlit_shortcuts import button


def clean_title(title: str) -> str:
    """Clean title for search by removing special characters and common words."""
    # Remove special characters and braces
    clean = title.replace("{", "").replace("}", "").replace("--", " ").replace("-", " ")

    # Remove punctuation
    clean = "".join(c for c in clean if c.isalnum() or c.isspace())

    # Convert to lowercase
    clean = clean.lower()

    return clean


def search_dblp(title: str, num_results: int = 5, max_retries: int = 5) -> List[Dict]:
    """
    Search DBLP for a paper by title with retry handling based on DBLP's Retry-After header.

    Args:
        title (str): Title of the paper to search for
        num_results (int): Number of results to return
        max_retries (int): Maximum number of retries for rate limited requests

    Returns:
        list: List of DBLP entries
    """
    # Clean the title for search
    clean_search_title = clean_title(title)

    # DBLP API endpoint
    url = "https://dblp.org/search/publ/api"

    # Parameters for the search
    params = {
        "q": clean_search_title,
        "format": "json",
        "h": num_results,
    }

    retry_count = 0
    while retry_count < max_retries:
        try:
            response = requests.get(url, params=params)

            # Handle rate limiting
            if response.status_code == 429:
                # Get retry time from header, default to 30 seconds if not provided
                retry_after = int(response.headers.get("Retry-After", 30))
                st.warning(
                    f"Rate limited by DBLP. Waiting {retry_after} seconds as specified by the server..."
                )
                time.sleep(retry_after)
                retry_count += 1
                continue

            response.raise_for_status()
            data = response.json()

            # Check if we have any hits
            hits = data.get("result", {}).get("hits", {}).get("hit", [])
            results = [hit.get("info", {}) for hit in hits]

            # Add a small delay with progress indicator to avoid overwhelming the API
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
    """Extract author string from DBLP author field which can have various formats."""
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
        # Extract author names from the list of author objects/dictionaries
        author_names = []
        for author in author_list:
            if isinstance(author, dict):
                # Get the author name from the 'text' field
                author_name = author.get("text", "")
                # Remove any numerical suffixes (e.g., "0016")
                if author_name:
                    parts = author_name.split()
                    if parts[-1].isdigit():
                        author_name = " ".join(parts[:-1])
                author_names.append(author_name if author_name else "N/A")
            else:
                author_names.append(str(author))
        return "; ".join(filter(None, author_names))

    return "N/A"


def format_entry_for_display(entry: Dict, is_dblp: bool = False) -> str:
    """Format an entry for display in the UI."""
    if is_dblp:
        # DBLP entry
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
        # BibTeX entry
        return f"""📄 Title:
{entry.get("title", "N/A")}

👥 Authors:
{entry.get("author", "N/A")}

📅 Year: {entry.get("year", "N/A")}
📑 Type: {entry.get("ENTRYTYPE", "N/A")}
🏷️ Citation Key: {entry.get("ID", "N/A")}"""


def merge_entries(bibtex_entry: Dict, dblp_entry: Dict) -> Dict:
    """Merge DBLP entry into BibTeX entry, keeping the original ID."""
    merged = bibtex_entry.copy()

    # Map DBLP fields to BibTeX fields
    field_mapping = {
        "title": "title",
        "year": "year",
        "doi": "doi",
        "url": "url",
        "venue": "journal",  # or 'booktitle' for conferences
        "type": "note",
    }

    for dblp_field, bibtex_field in field_mapping.items():
        if dblp_field in dblp_entry and dblp_entry[dblp_field]:
            merged[bibtex_field] = dblp_entry[dblp_field]

    # Handle authors separately
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

st.title("BibTeX DBLP Resolver")
st.write("Upload your BibTeX file and resolve entries with DBLP.")

# Add keyboard shortcuts info
st.markdown("""
**Keyboard Shortcuts:**
- `Enter` or `Y`: Accept match
- `Esc` or `N`: Decline match
- `1`-`5`: Select match number (when multiple matches shown)

**Note:** Exact matches are automatically accepted
""")

# File uploader
uploaded_file = st.file_uploader("Choose a BibTeX file", type=["bib"])

if uploaded_file:
    # Parse BibTeX file
    parser = bibtexparser.bparser.BibTexParser(common_strings=True)
    bib_database = bibtexparser.loads(uploaded_file.getvalue().decode())

    # Initialize session state for tracking progress
    if "current_entry" not in st.session_state:
        st.session_state.current_entry = 0
        st.session_state.processed_entries = []
        st.session_state.processing_done = False  # Flag for processing status

    # Show progress
    progress_text = st.empty()
    progress_bar = st.progress(0.0)

    if not st.session_state.processing_done:
        if st.session_state.current_entry < len(bib_database.entries):
            entry = bib_database.entries[st.session_state.current_entry]

            # Update progress text and bar
            progress_fraction = (st.session_state.current_entry + 1) / len(
                bib_database.entries
            )
            progress_text.write(
                f"Processing entry {st.session_state.current_entry + 1} of {len(bib_database.entries)}"
            )
            progress_bar.progress(progress_fraction)

            # Search DBLP
            with st.spinner(f"Searching DBLP for '{entry['title']}'..."):
                dblp_results = search_dblp(entry["title"])

            if dblp_results:
                # Check for exact title match
                exact_matches = []
                other_matches = []

                original_clean = clean_title(entry["title"])

                for result in dblp_results:
                    result_clean = clean_title(result["title"])
                    # Estimate a simple word overlap ratio
                    overlap = set(original_clean.split()) & set(result_clean.split())
                    total_words = set(original_clean.split()) | set(
                        result_clean.split()
                    )
                    similarity = len(overlap) / len(total_words) if total_words else 0

                    if similarity > 0.8:  # More than 80% word overlap
                        exact_matches.append(result)
                    else:
                        other_matches.append(result)

                # Sort exact matches, preferring conferences over arXiv/CoRR
                exact_matches.sort(
                    key=lambda x: "CoRR" in x.get("venue", "")
                    or "arXiv" in x.get("venue", "")
                )

                if exact_matches:
                    # Automatically accept exact match
                    handle_accept(entry, exact_matches[0])
                    # st.rerun() # Removed to prevent infinite loop

                else:
                    st.subheader("Similar Matches Found")

                    # Show original entry on the left
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Original Entry**")
                        st.text(format_entry_for_display(entry))

                    # Show each potential match on the right
                    with col2:
                        for i, result in enumerate(dblp_results):
                            st.markdown(f"**Match {i + 1}** (Press {i + 1})")
                            st.text(format_entry_for_display(result, True))
                            if (
                                i < len(dblp_results) - 1
                            ):  # Don't add separator after the last match
                                st.markdown("---")

                    # Create a row of buttons for each match with keyboard shortcuts
                    cols = st.columns(
                        min(len(dblp_results) + 1, 6)
                    )  # +1 for decline button

                    # Add number buttons
                    for i in range(min(len(dblp_results), 5)):
                        with cols[i]:
                            if button(
                                f"{i + 1}",
                                str(i + 1),
                                lambda i=i: handle_accept(entry, dblp_results[i]),
                                hint=True,
                            ):
                                pass

                    # Add decline button in the last column
                    with cols[-1]:
                        if button(
                            "❌", "Escape", lambda: handle_decline(entry), hint=True
                        ):
                            pass

            else:
                st.subheader("No Matches Found")
                # Show the entry that couldn't be found
                st.text(format_entry_for_display(entry))
                st.warning(
                    "This entry will be marked with a TODO note for manual search."
                )

                # Automatically continue to the next entry and add a TODO note
                handle_decline(add_todo_note(entry))
                # st.rerun() # Removed to prevent infinite loop

            if st.session_state.current_entry < len(bib_database.entries):
                st.rerun()
            else:
                st.session_state.processing_done = True
                st.rerun()  # Rerun once to update the UI

    if st.session_state.processing_done:
        progress_bar.progress(1.0)
        progress_text.write("Processing complete!")

        st.success("All entries processed!")

        # Create new BibTeX database with processed entries
        # Convert the list of entries to a BibDatabase object
        from bibtexparser.bibdatabase import BibDatabase

        db = BibDatabase()
        db.entries = st.session_state.processed_entries

        # Generate the new BibTeX file
        bibtex_str = bibtexparser.dumps(db)  # Use dumps() instead of write_string

        # Offer download
        st.download_button(
            label="Download processed BibTeX",
            data=bibtex_str,
            file_name="processed.bib",
            mime="text/plain",
        )

        # Reset session state for new file
        if st.button("Process another file"):
            del st.session_state.current_entry
            del st.session_state.processed_entries
            st.session_state.processing_done = False  # Reset the flag
            st.rerun()
