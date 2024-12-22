import streamlit as st
import requests
import re
import os
import time
import io
import zipfile
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime

SUFFIX_ORDER = ["_k", "_h", "_b", "_z", "_m"]

def try_download_flickr_image(base_url, headers, timeout=10):
    """
    Attempt to download an image from 'base_url' by trying different Flickr suffixes.
    Returns a tuple (success, message_or_final_url).
    """
    match = re.search(r'(_[a-z])\.jpg$', base_url)
    if not match:
        return _attempt_download(base_url, headers, timeout=timeout)

    prefix = base_url[:match.start()]
    
    for suffix in SUFFIX_ORDER:
        candidate_url = prefix + suffix + ".jpg"
        success, msg = _attempt_download(candidate_url, headers, timeout=timeout)
        if success:
            return True, candidate_url
    return False, msg


def _attempt_download(url, headers, timeout=10):
    """
    Helper function that tries to perform a GET request on 'url'.
    Returns a tuple (success, message_or_url).
    """
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return True, url
    except requests.exceptions.RequestException as e:
        return False, str(e)


def extract_flickr_image_urls(html):
    """
    Use BeautifulSoup to find all images pointing to staticflickr.com within an HTML page.
    Returns a list of image URLs.
    """
    soup = BeautifulSoup(html, "html.parser")
    image_elements = soup.find_all("img")
    image_urls = []

    for img in image_elements:
        # Try different img attributes for the source
        src = (
            img.get("src")
            or img.get("data-defer-src")
            or img.get("data-original")
            or ""
        )

        # If the 'src' is missing, try the 'srcset' (sometimes used for multiple sizes)
        if not src:
            srcset = img.get("srcset", "")
            if "staticflickr.com" in srcset:
                # Usually, the largest size is the second-last item in the list
                # e.g., "https://... 500w https://... 1000w" -> pick the 1000w
                largest = srcset.split()[-2]
                src = largest

        if "staticflickr.com" in src:
            # Some Flickr images start with "//", so prepend "https:" if needed
            if src.startswith("//"):
                src = "https:" + src
            image_urls.append(src)

    return image_urls


st.title("Flickr Image Downloader")
flickr_url = st.text_input("Enter a Flickr URL (e.g., https://www.flickr.com/...):")

if st.button("Download Images"):
    if not flickr_url.strip():
        st.error("Please enter a valid Flickr URL.")
        st.stop()
    
    # Create memory file for zip
    zip_buffer = io.BytesIO()
    
    # Create a timestamp for the zip filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    success_count = 0
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.flickr.com/"
        }

        try:
            response = requests.get(flickr_url, headers=headers, timeout=10)
            response.raise_for_status()
            html = response.text
        except requests.exceptions.RequestException as e:
            st.error(f"Failed to fetch {flickr_url}.\nError: {e}")
            st.stop()

        flickr_links = extract_flickr_image_urls(html)
        if not flickr_links:
            st.info("No Flickr images found on that page.")
            st.stop()

        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.write(f"Found {len(flickr_links)} image(s). Starting download...")

        for index, link in enumerate(flickr_links):
            parsed_url = urlparse(link)
            filename = os.path.basename(parsed_url.path)

            # Ensure filename is unique and valid
            base_name, ext = os.path.splitext(filename)
            filename = f"{base_name}_{index}{ext}"

            if "staticflickr.com" in link:
                success, final_url = try_download_flickr_image(link, headers)
                if not success:
                    status_text.warning(f"Failed to download {link}: {final_url}")
                    time.sleep(0.5)
                    continue
                link = final_url

            try:
                r = requests.get(link, headers=headers, timeout=10)
                r.raise_for_status()
                
                # Create a ZipInfo object for more control
                zip_info = zipfile.ZipInfo(filename)
                zip_info.date_time = time.localtime()[:6]
                zip_info.compress_type = zipfile.ZIP_DEFLATED
                
                # Write the file to the zip
                zip_file.writestr(zip_info, r.content)
                success_count += 1
                status_text.success(f"Added {filename} to zip file.")
                
                # Update progress bar
                progress_bar.progress((index + 1) / len(flickr_links))
                time.sleep(0.5)

            except requests.exceptions.RequestException as e:
                status_text.error(f"Failed to download {link}: {e}")
                time.sleep(0.5)

        progress_bar.progress(1.0)
        
    if success_count > 0:
        # Prepare zip file for download
        zip_buffer.seek(0)
        
        # Create download button with timestamp in filename
        st.download_button(
            label=f"Download {success_count} images as ZIP",
            data=zip_buffer,
            file_name=f"flickr_images_{timestamp}.zip",
            mime="application/zip",
            help="Click to download all successfully retrieved images as a ZIP file"
        )
    else:
        st.error("No images were successfully downloaded.")
