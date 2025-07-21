from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
import openai
import os
import re
from sqlalchemy.orm import Session
from ..db import get_db
from ..crud import get_emr_type, update_emr_type
import boto3
from pydantic import BaseModel
import urllib.parse
from dotenv import load_dotenv
import mimetypes
from bs4 import BeautifulSoup
load_dotenv()

router = APIRouter(prefix="/ai", tags=["AI"])

openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

S3_BUCKET = os.getenv("S3_BUCKET_NAME")
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
    verify=False
)

class GenerateRequest(BaseModel):
    emr_type_id: str

class SaveResponseRequest(BaseModel):
    emr_type_id: str
    response: str

def extract_full_emr_text(html_content: str) -> str:
    """Extract complete EMR form with all fields, values, and sections"""
    print(f"=== DEBUG: HTML Content Length: {len(html_content)} characters ===")
    print(f"=== DEBUG: First 500 characters of HTML ===")
    print(html_content[:500])
    print("=== END HTML DEBUG ===")
    
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    text_lines = []
    
    # Extract form input values first - Enhanced for custom EMR components
    form_data = {}
    input_elements = soup.find_all(['input', 'textarea', 'select'])
    print(f"=== DEBUG: Found {len(input_elements)} input elements ===")
    
    for elem in input_elements:
        name = elem.get('name', '')
        value = elem.get('value', '')
        input_type = elem.get('type', '')
        elem_id = elem.get('id', '')
        
        # Handle different input types
        if input_type == 'checkbox':
            checked = elem.get('checked') is not None
            # Use id as name if name is empty
            field_name = name if name else elem_id
            if field_name:
                form_data[field_name] = 'true' if checked else 'false'
                print(f"  Checkbox: {field_name} = {'true' if checked else 'false'}")
        elif input_type == 'radio':
            if elem.get('checked') is not None:
                field_name = name if name else elem_id
                if field_name:
                    form_data[field_name] = value
                    print(f"  Radio: {field_name} = {value}")
        elif elem.name == 'select':
            # Handle select dropdowns
            selected_option = elem.find('option', selected=True)
            if selected_option:
                option_value = selected_option.get('value', selected_option.get_text(strip=True))
                field_name = name if name else elem_id
                if field_name:
                    form_data[field_name] = option_value
                    print(f"  Select: {field_name} = {option_value}")
        else:
            # Handle text inputs, textareas, etc.
            if value:
                field_name = name if name else elem_id
                if field_name:
                    form_data[field_name] = value
                    print(f"  Input: {field_name} = {value} (type: {input_type})")
    
    # Enhanced detection for custom EMR components
    print("=== DEBUG: Looking for custom EMR components ===")
    
    # Look for custom date/time pickers
    date_time_elements = soup.find_all(['div', 'span', 'input'], class_=re.compile(r'date|time|picker|calendar', re.IGNORECASE))
    for elem in date_time_elements:
        # Check for date/time values in various attributes
        for attr in ['data-value', 'data-date', 'data-time', 'title', 'placeholder']:
            attr_value = elem.get(attr, '')
            if attr_value and re.match(r'\d{1,2}/\d{1,2}/\d{4}|\d{2}:\d{2}', attr_value):
                elem_id = elem.get('id', '')
                if elem_id:
                    form_data[elem_id] = attr_value
                    print(f"  Custom date/time: {elem_id} = {attr_value}")
    
    # Look for custom checkboxes with data attributes
    checkbox_elements = soup.find_all(['div', 'span'], class_=re.compile(r'checkbox|check', re.IGNORECASE))
    for elem in checkbox_elements:
        # Check for checkbox state in data attributes
        for attr in ['data-checked', 'data-value', 'data-state']:
            attr_value = elem.get(attr, '')
            if attr_value.lower() in ['true', 'false', '1', '0', 'yes', 'no']:
                elem_id = elem.get('id', '')
                if elem_id:
                    # Convert to true/false
                    bool_value = 'true' if attr_value.lower() in ['true', '1', 'yes'] else 'false'
                    form_data[elem_id] = bool_value
                    print(f"  Custom checkbox: {elem_id} = {bool_value}")
    
    # Look for readonly inputs that might have values in nearby elements
    readonly_inputs = soup.find_all('input', readonly=True)
    for input_elem in readonly_inputs:
        input_id = input_elem.get('id', '')
        if input_id:
            # Look for value in nearby elements
            parent = input_elem.parent
            if parent:
                # Check sibling elements for the actual value
                siblings = parent.find_all(['div', 'span', 'p'])
                for sibling in siblings:
                    sibling_text = sibling.get_text(strip=True)
                    if sibling_text and len(sibling_text) > 0:
                        # Check if it looks like a value (not a label)
                        if not re.match(r'^[A-Za-z\s]+$', sibling_text) and len(sibling_text) < 100:
                            form_data[input_id] = sibling_text
                            print(f"  Readonly input value: {input_id} = {sibling_text}")
                            break
    
    # Look for custom dropdown/lookup fields
    lookup_elements = soup.find_all(['div', 'span'], class_=re.compile(r'lookup|dropdown|select', re.IGNORECASE))
    for elem in lookup_elements:
        # Check for selected values in data attributes or text content
        for attr in ['data-value', 'data-selected', 'data-text']:
            attr_value = elem.get(attr, '')
            if attr_value:
                elem_id = elem.get('id', '')
                if elem_id:
                    form_data[elem_id] = attr_value
                    print(f"  Custom dropdown: {elem_id} = {attr_value}")
        
        # Also check text content for dropdown values
        text_content = elem.get_text(strip=True)
        if text_content and len(text_content) < 100:
            elem_id = elem.get('id', '')
            if elem_id:
                form_data[elem_id] = text_content
                print(f"  Custom dropdown text: {elem_id} = {text_content}")
    
    # Look for any element with data-value attribute (common in custom components)
    data_value_elements = soup.find_all(attrs={'data-value': True})
    for elem in data_value_elements:
        data_value = elem.get('data-value', '')
        if data_value:
            elem_id = elem.get('id', '')
            if elem_id:
                form_data[elem_id] = data_value
                print(f"  Data-value element: {elem_id} = {data_value}")
    
    # Look for any element with aria-label that might contain field values
    aria_elements = soup.find_all(attrs={'aria-label': True})
    for elem in aria_elements:
        aria_label = elem.get('aria-label', '')
        if aria_label and ':' in aria_label:
            parts = aria_label.split(':', 1)
            if len(parts) == 2:
                label = parts[0].strip()
                value = parts[1].strip()
                if value and len(value) < 100:
                    elem_id = elem.get('id', '')
                    if elem_id:
                        form_data[elem_id] = value
                        print(f"  Aria-label value: {elem_id} = {value}")
    
    # Enhanced detection for ANY field with a value (comprehensive approach)
    print("=== DEBUG: Comprehensive field detection ===")
    
    # Look for ANY input element that might have a value (even without value attribute)
    all_inputs = soup.find_all('input')
    for input_elem in all_inputs:
        input_id = input_elem.get('id', '')
        input_name = input_elem.get('name', '')
        input_type = input_elem.get('type', '')
        
        # Check multiple sources for the value
        value_sources = [
            input_elem.get('value', ''),
            input_elem.get('data-value', ''),
            input_elem.get('data-text', ''),
            input_elem.get('placeholder', ''),
            input_elem.get('title', '')
        ]
        
        for value in value_sources:
            if value and len(value) > 0:
                field_name = input_id if input_id else input_name
                if field_name:
                    form_data[field_name] = value
                    print(f"  Input value found: {field_name} = {value}")
                    break
        
        # For checkboxes, also check if they're checked
        if input_type == 'checkbox':
            checked = input_elem.get('checked') is not None
            field_name = input_id if input_id else input_name
            if field_name:
                form_data[field_name] = 'true' if checked else 'false'
                print(f"  Checkbox state: {field_name} = {'true' if checked else 'false'}")
    
    # Look for ANY element that might contain a field value (broader search)
    all_elements = soup.find_all(['div', 'span', 'p', 'td', 'li'])
    for elem in all_elements:
        elem_id = elem.get('id', '')
        elem_class = elem.get('class', [])
        
        # Check if this element might contain a field value
        text_content = elem.get_text(strip=True)
        if text_content and len(text_content) < 100:
            # Check if it looks like a value (not just a label)
            if (re.match(r'\d{1,2}/\d{1,2}/\d{4}', text_content) or  # Date pattern
                re.match(r'\d{2}:\d{2}', text_content) or           # Time pattern
                text_content.lower() in ['true', 'false', 'yes', 'no'] or  # Boolean
                (len(text_content) > 0 and not re.match(r'^[A-Za-z\s]+$', text_content))):  # Not just letters
                
                if elem_id:
                    form_data[elem_id] = text_content
                    print(f"  Element value: {elem_id} = {text_content}")
    
    # Look for label-value pairs in ANY structure
    all_text_elements = soup.find_all(text=True)
    for text_elem in all_text_elements:
        text = text_elem.strip()
        if ':' in text and len(text) > 3:
            parts = text.split(':', 1)
            if len(parts) == 2:
                label = parts[0].strip()
                value = parts[1].strip()
                
                # Check if this looks like a form field
                if (len(label) < 50 and len(value) > 0 and len(value) < 100 and
                    not label.lower() in ['http', 'https', 'javascript', 'data'] and
                    not value.startswith('http')):
                    
                    # Try to find a nearby element with an ID
                    parent = text_elem.parent
                    if parent:
                        parent_id = parent.get('id', '')
                        if parent_id:
                            form_data[parent_id] = value
                            print(f"  Label-value pair: {parent_id} = {value}")
                        else:
                            # Use label as field name
                            form_data[label] = value
                            print(f"  Label-value pair: {label} = {value}")
    
    # Look for any element with a value-like pattern
    value_patterns = [
        r'\d{1,2}/\d{1,2}/\d{4}',  # Date pattern
        r'\d{2}:\d{2}',            # Time pattern
        r'[A-Za-z]+, [A-Za-z]+',   # Name pattern
        r'\d{3}-\d{3}-\d{4}',      # Phone pattern
        r'[A-Za-z\s]+\(Lic\.#\s+\d+[A-Z]?\)'  # License pattern
    ]
    
    for pattern in value_patterns:
        matching_elements = soup.find_all(text=re.compile(pattern))
        for elem in matching_elements:
            text = elem.strip()
            if text:
                parent = elem.parent
                if parent:
                    parent_id = parent.get('id', '')
                    if parent_id:
                        form_data[parent_id] = text
                        print(f"  Pattern match: {parent_id} = {text}")
    
    # Enhanced detection for specific field types that are commonly missed
    print("=== DEBUG: Enhanced specific field detection ===")
    
    # 1. Normalize Labels First - Improve label detection
    def normalize_label(label):
        """Normalize label text for better matching"""
        return label.lower().replace('-', ' ').replace('_', ' ').strip()
    
    # 2. Improve Date Matching (Appt Date) - Handle various date formats and locations
    print("=== DEBUG: Enhanced date detection ===")
    date_patterns = [r'\b\d{1,2}/\d{1,2}/\d{4}\b']
    for elem in soup.find_all(['div', 'span', 'p', 'td', 'input']):
        text = elem.get_text(strip=True)
        for pattern in date_patterns:
            if re.search(pattern, text):
                # Check if this is near an appointment date label
                parent = elem.parent
                if parent:
                    parent_text = parent.get_text(strip=True).lower()
                    if any(keyword in parent_text for keyword in ['appt date', 'appointment date', 'session date']):
                        date_match = re.search(pattern, text)
                        if date_match:
                            form_data['Appt Date'] = date_match.group(0)
                            print(f"  Appt Date found near label: {form_data['Appt Date']}")
                            break
    
    # Also look for date inputs specifically
    date_inputs = soup.find_all('input', type=['date', 'text'])
    for input_elem in date_inputs:
        input_value = input_elem.get('value', '')
        if input_value and re.match(r'\d{1,2}/\d{1,2}/\d{4}', input_value):
            # Check if this input is near an appointment date label
            parent = input_elem.parent
            if parent:
                parent_text = parent.get_text(strip=True).lower()
                if any(keyword in parent_text for keyword in ['appt date', 'appointment date', 'session date']):
                    form_data['Appt Date'] = input_value
                    print(f"  Appt Date input found: {form_data['Appt Date']}")
                    break
    
    # 3. Improve Duration Extraction - Handle various time formats
    print("=== DEBUG: Enhanced duration detection ===")
    duration_pattern = r'\b(\d+:\d{2}|\d{1,3})\b'
    for elem in soup.find_all(['div', 'span', 'td', 'li', 'input']):
        text = elem.get_text(strip=True)
        if 'duration' in text.lower() or 'time' in text.lower() or 'hh:mm' in text:
            match = re.search(duration_pattern, text)
            if match:
                duration_value = match.group(0)
                # Check if this is actually a duration field (not just any number)
                parent = elem.parent
                if parent:
                    parent_text = parent.get_text(strip=True).lower()
                    if any(keyword in parent_text for keyword in ['duration', 'time', 'length', 'hh:mm']):
                        form_data['Duration (hh:mm)'] = duration_value
                        print(f"  Duration value extracted: {form_data['Duration (hh:mm)']}")
                        break
    
    # Also look for duration inputs specifically
    duration_inputs = soup.find_all('input', type=['text', 'time'])
    for input_elem in duration_inputs:
        input_value = input_elem.get('value', '')
        if input_value and (re.match(r'\d+', input_value) or re.match(r'\d{2}:\d{2}', input_value)):
            # Check if this input is near a duration label
            parent = input_elem.parent
            if parent:
                parent_text = parent.get_text(strip=True).lower()
                if any(keyword in parent_text for keyword in ['duration', 'time', 'length', 'hh:mm']):
                    form_data['Duration (hh:mm)'] = input_value
                    print(f"  Duration input found: {form_data['Duration (hh:mm)']}")
                    break
    
    # 4. Dynamic Checkbox Detection - Find ANY checkbox state
    print("=== DEBUG: Dynamic checkbox detection ===")
    
    # Look for ANY checkbox input
    checkbox_inputs = soup.find_all('input', type='checkbox')
    for input_elem in checkbox_inputs:
        checked = input_elem.get('checked') is not None
        input_id = input_elem.get('id', '')
        input_name = input_elem.get('name', '')
        field_name = input_id if input_id else input_name
        
        if field_name:
            checkbox_state = 'true' if checked else 'false'
            form_data[field_name] = checkbox_state
            print(f"  Checkbox found: {field_name} = {checkbox_state}")
    
    # Look for ANY element that might be a checkbox (styled checkboxes)
    checkbox_elements = soup.find_all(['div', 'span'], class_=re.compile(r'checkbox|check|toggle', re.IGNORECASE))
    for elem in checkbox_elements:
        elem_id = elem.get('id', '')
        elem_class = ' '.join(elem.get('class', []))
        elem_text = elem.get_text(strip=True)
        
        # Check for checked state in attributes
        elem_attrs = str(elem.attrs).lower()
        if 'checked' in elem_attrs or 'true' in elem_attrs or 'aria-checked="true"' in elem_attrs:
            checkbox_state = 'true'
        else:
            checkbox_state = 'false'
        
        if elem_id:
            form_data[elem_id] = checkbox_state
            print(f"  Styled checkbox found: {elem_id} = {checkbox_state}")
    
    # 5. Dynamic label-to-field mapping - Find ANY label-value pairs
    print("=== DEBUG: Dynamic label-to-field mapping ===")
    
    # Look for ANY text that might be a field label
    all_text_elements = soup.find_all(text=True)
    for text_elem in all_text_elements:
        text = text_elem.strip()
        if text and len(text) < 100:
            normalized_text = normalize_label(text)
            
            # Look for ANY value nearby this label
            parent = text_elem.parent
            if parent:
                # Search in parent and siblings for ANY values
                nearby_elements = [parent] + list(parent.find_next_siblings())
                for nearby in nearby_elements:
                    nearby_text = nearby.get_text(strip=True)
                    
                    # Look for ANY value pattern (date, time, number, text)
                    if re.search(r'\b\d{1,2}/\d{1,2}/\d{4}\b', nearby_text):  # Date
                        date_match = re.search(r'\b\d{1,2}/\d{1,2}/\d{4}\b', nearby_text)
                        if date_match:
                            form_data[normalized_text] = date_match.group(0)
                            print(f"  Date value mapped: {normalized_text} = {date_match.group(0)}")
                    
                    elif re.search(r'\b(\d+:\d{2}|\d{1,3})\b', nearby_text):  # Time/Duration
                        time_match = re.search(r'\b(\d+:\d{2}|\d{1,3})\b', nearby_text)
                        if time_match:
                            form_data[normalized_text] = time_match.group(0)
                            print(f"  Time value mapped: {normalized_text} = {time_match.group(0)}")
                    
                    elif re.search(r'\b\d+\b', nearby_text):  # Number
                        number_match = re.search(r'\b\d+\b', nearby_text)
                        if number_match:
                            form_data[normalized_text] = number_match.group(0)
                            print(f"  Number value mapped: {normalized_text} = {number_match.group(0)}")
                    
                    elif len(nearby_text) > 0 and len(nearby_text) < 100:  # Text
                        if not re.match(r'^[A-Za-z\s]+$', nearby_text):  # Not just letters
                            form_data[normalized_text] = nearby_text
                            print(f"  Text value mapped: {normalized_text} = {nearby_text}")
    
    # Look for any input field that might be hidden or have custom styling
    all_inputs_deep = soup.find_all('input', recursive=True)
    for input_elem in all_inputs_deep:
        input_id = input_elem.get('id', '')
        input_name = input_elem.get('name', '')
        input_type = input_elem.get('type', '')
        
        # Check if this input has any value in any attribute
        for attr in ['value', 'data-value', 'data-text', 'placeholder', 'title', 'data-selected']:
            attr_value = input_elem.get(attr, '')
            if attr_value and len(attr_value) > 0:
                field_name = input_id if input_id else input_name
                if field_name:
                    # For checkboxes, convert to true/false
                    if input_type == 'checkbox':
                        bool_value = 'true' if attr_value.lower() in ['true', '1', 'yes', 'checked'] else 'false'
                        form_data[field_name] = bool_value
                        print(f"  Hidden checkbox: {field_name} = {bool_value}")
                    else:
                        form_data[field_name] = attr_value
                        print(f"  Hidden input: {field_name} = {attr_value}")
                    break
        
        # For checkboxes, also check the checked attribute
        if input_type == 'checkbox':
            checked = input_elem.get('checked') is not None
            field_name = input_id if input_id else input_name
            if field_name:
                form_data[field_name] = 'true' if checked else 'false'
                print(f"  Checkbox state: {field_name} = {'true' if checked else 'false'}")
    
    # Look for any element that might contain a field value but isn't an input
    all_elements_deep = soup.find_all(['div', 'span', 'p', 'td', 'li'], recursive=True)
    for elem in all_elements_deep:
        elem_id = elem.get('id', '')
        elem_class = ' '.join(elem.get('class', []))
        
        # Check if this element might be a field value container
        text_content = elem.get_text(strip=True)
        if text_content and len(text_content) < 50:
            # Check if it looks like a field value
            if (re.match(r'\d{1,2}/\d{1,2}/\d{4}', text_content) or  # Date
                re.match(r'\d+', text_content) or                    # Number
                re.match(r'\d{2}:\d{2}', text_content) or           # Time
                text_content.lower() in ['true', 'false', 'yes', 'no'] or  # Boolean
                (len(text_content) > 0 and not re.match(r'^[A-Za-z\s]+$', text_content))):  # Mixed content
                
                if elem_id:
                    # For boolean values, convert to true/false
                    if text_content.lower() in ['true', 'false', 'yes', 'no', '1', '0']:
                        bool_value = 'true' if text_content.lower() in ['true', 'yes', '1'] else 'false'
                        form_data[elem_id] = bool_value
                        print(f"  Boolean element: {elem_id} = {bool_value}")
                    else:
                        form_data[elem_id] = text_content
                        print(f"  Value element: {elem_id} = {text_content}")
    

    
    print(f"=== DEBUG: Extracted {len(form_data)} form values ===")
    for name, value in form_data.items():
        print(f"  {name}: {value}")
    
    # Find sections and extract content
    sections = []
    
    # Look for common section containers
    section_containers = soup.find_all(["fieldset", "section", "div", "form"])
    print(f"=== DEBUG: Found {len(section_containers)} section containers ===")
    
    # Look for forms specifically
    forms = soup.find_all("form")
    print(f"=== DEBUG: Found {len(forms)} forms ===")
    
    # Look for iframes that might contain the form
    iframes = soup.find_all("iframe")
    print(f"=== DEBUG: Found {len(iframes)} iframes ===")
    
    # Look for elements with "contact" or "address" in them
    contact_elements = soup.find_all(text=re.compile(r'contact|address|facility', re.IGNORECASE))
    print(f"=== DEBUG: Found {len(contact_elements)} elements with contact/address/facility ===")
    for elem in contact_elements[:5]:
        print(f"  Contact element: {elem.strip()}")
    
    for container in section_containers:
        # Find section title
        title = None
        title_elem = container.find(["legend", "h1", "h2", "h3", "h4", "strong", "label"])
        if title_elem:
            title = title_elem.get_text(strip=True)
        
        # Extract all text content in this section
        section_text = container.get_text(separator="\n", strip=True)
        
        if title and section_text:
            sections.append((title, section_text))
            print(f"  Section: {title}")
            
            # Check if this section contains contact/address info
            if any(keyword in title.lower() for keyword in ['contact', 'address', 'facility']):
                print(f"    *** Found contact-related section: {title} ***")
                print(f"    Content preview: {section_text[:200]}...")
    
    # If no sections found, try to organize by headers
    if not sections:
        headers = soup.find_all(["h1", "h2", "h3", "h4", "strong"])
        print(f"=== DEBUG: No sections found, trying headers. Found {len(headers)} headers ===")
        for header in headers:
            header_text = header.get_text(strip=True)
            if header_text:
                # Get content after this header until next header
                content_lines = []
                current = header.next_sibling
                while current and not (hasattr(current, 'name') and current.name in ["h1", "h2", "h3", "h4", "strong"]):
                    if hasattr(current, 'get_text'):
                        text = current.get_text(strip=True)
                        if text:
                            content_lines.append(text)
                    current = current.next_sibling
                
                if content_lines:
                    sections.append((header_text, "\n".join(content_lines)))
                    print(f"  Header: {header_text}")
    
    # Build the structured text
    text_lines.append("=== COMPLETE EMR FORM DATA ===")
    
    # Add form input values
    if form_data:
        text_lines.append("\n=== FORM INPUT VALUES ===")
        for name, value in form_data.items():
            text_lines.append(f"{name}: {value}")
    
    # Add sectioned content with improved field matching
    for title, content in sections:
        text_lines.append(f"\n=== {title} ===")
        
        # Try to find nearby labels and values in this section
        section_soup = BeautifulSoup(content, "html.parser")
        rows = section_soup.find_all(["div", "tr", "p", "td", "li"])
        
        for row in rows:
            text = row.get_text(separator=" ", strip=True)
            if len(text) > 0 and ':' in text:
                # Looks like a "Label: Value" pair
                parts = text.split(":", 1)
                label = parts[0].strip()
                value = parts[1].strip()
                if len(label) < 100 and len(value) > 0:
                    text_lines.append(f"{label}: {value}")
                    print(f"  Found field: {label}: {value}")
        
        # Also add the original content as fallback
        lines = content.split('\n')
        for line in lines:
            line_stripped = line.strip()
            if line_stripped and len(line_stripped) > 1:
                text_lines.append(line_stripped)
    
    # Enhanced parsing for visual label/value pairs not in input tags
    # This specifically targets fields like "Service Facility Address" that are rendered as plain HTML
    print("=== DEBUG: Enhanced parsing for label-value pairs ===")
    
    # Look for label-value patterns across the entire document
    all_elements = soup.find_all(["div", "tr", "p", "td", "li", "span", "label"])
    enhanced_fields = []
    
    for elem in all_elements:
        text = elem.get_text(separator=' ', strip=True)
        if ':' in text and len(text) > 3:
            # Split on first colon only
            parts = text.split(':', 1)
            if len(parts) == 2:
                label = parts[0].strip()
                value = parts[1].strip()
                
                # Filter for meaningful label-value pairs
                if (1 < len(label) < 100 and 
                    len(value) > 0 and 
                    not label.lower() in ['http', 'https', 'javascript', 'data'] and
                    not value.startswith('http')):
                    
                    # Extract ANY label-value pair (completely dynamic)
                    enhanced_fields.append((label, value))
                    print(f"  Enhanced field found: {label}: {value}")
    
    # Add enhanced fields to the output
    if enhanced_fields:
        text_lines.append("\n=== ENHANCED FIELD EXTRACTION ===")
        for label, value in enhanced_fields:
            text_lines.append(f"{label}: {value}")
    

    
    # Also look for iframe content which might contain the actual form
    iframes = soup.find_all("iframe")
    for iframe in iframes:
        srcdoc = iframe.get('srcdoc')
        if srcdoc:
            print(f"=== DEBUG: Found iframe with srcdoc content ===")
            iframe_soup = BeautifulSoup(srcdoc, "html.parser")
            
            # Extract from iframe content
            iframe_text = iframe_soup.get_text(separator="\n", strip=True)
            if iframe_text:
                text_lines.append(f"\n=== IFRAME CONTENT ===")
                lines = iframe_text.split('\n')
                for line in lines:
                    line_stripped = line.strip()
                    if line_stripped and len(line_stripped) > 1:
                        text_lines.append(line_stripped)
                
                # Also look for label-value pairs in iframe
                iframe_elements = iframe_soup.find_all(["div", "tr", "p", "td", "li", "span", "label"])
                for elem in iframe_elements:
                    text = elem.get_text(separator=' ', strip=True)
                    if ':' in text and len(text) > 3:
                        parts = text.split(':', 1)
                        if len(parts) == 2:
                            label = parts[0].strip()
                            value = parts[1].strip()
                            if (1 < len(label) < 100 and len(value) > 0):
                                text_lines.append(f"{label}: {value}")
                                print(f"  Iframe field: {label}: {value}")
    

    
    # If no structured content found, get all text
    if len(text_lines) <= 2:  # Only has header and form values
        all_text = soup.get_text(separator="\n", strip=True)
        text_lines.append("\n=== ALL FORM CONTENT ===")
        
        # Look for specific patterns that might contain the form data
        print("=== DEBUG: Searching for form patterns ===")
        
        # Look for any text that contains "Service Facility Address"
        service_address_matches = soup.find_all(text=re.compile(r'service facility address', re.IGNORECASE))
        print(f"Found {len(service_address_matches)} elements with 'Service Facility Address'")
        for match in service_address_matches:
            print(f"  Match: {match.strip()}")
            # Get parent element to see context
            parent = match.parent
            if parent:
                print(f"    Parent: {parent.name} - {parent.get_text(strip=True)[:100]}...")
        
        # Look for any text that contains the address
        address_matches = soup.find_all(text=re.compile(r'38 albert drive|monsey|10952', re.IGNORECASE))
        print(f"Found {len(address_matches)} elements with address content")
        for match in address_matches:
            print(f"  Address match: {match.strip()}")
        
        lines = all_text.split('\n')
        for line in lines:
            line_stripped = line.strip()
            if line_stripped and len(line_stripped) > 1:
                text_lines.append(line_stripped)
    
    final_text = "\n".join(text_lines)
    print(f"=== DEBUG: Final extracted text length: {len(final_text)} characters ===")
    print("=== DEBUG: Text Extract ===")
    print(final_text[:1500])
    print("=== END DEBUG ===")
    
    return final_text

def ask_gpt_about_emr(cleaned_text: str, question: str, html_content: str = None) -> str:
    """Ask GPT about the EMR content with HTML structure"""
    
    if html_content:
        # Extract comprehensive HTML structure (all elements with IDs, classes, inputs, etc.)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find ALL important elements
        all_elements = []
        
        # Get ALL input elements (form fields)
        inputs = soup.find_all('input')
        for inp in inputs:
            all_elements.append(str(inp))
        
        # Get ALL select elements (dropdowns)
        selects = soup.find_all('select')
        for sel in selects:
            all_elements.append(str(sel))
        
        # Get ALL textarea elements
        textareas = soup.find_all('textarea')
        for textarea in textareas:
            all_elements.append(str(textarea))
        
        # Get ALL elements with IDs (any element that has an ID)
        elements_with_ids = soup.find_all(attrs={'id': True})
        for elem in elements_with_ids:
            if elem.name not in ['input', 'select', 'textarea']:  # Avoid duplicates
                all_elements.append(str(elem))
        
        # Get ALL elements with classes (any element that has a class)
        elements_with_classes = soup.find_all(attrs={'class': True})
        for elem in elements_with_classes:
            if elem.name not in ['input', 'select', 'textarea']:  # Avoid duplicates
                all_elements.append(str(elem))
        
        # Get ALL div, span, p, td, li elements (common containers)
        common_elements = soup.find_all(['div', 'span', 'p', 'td', 'li', 'label'])
        for elem in common_elements:
            # Only add if it has meaningful content or attributes
            if (elem.get('id') or elem.get('class') or 
                elem.get_text(strip=True) or 
                elem.get('data-value') or elem.get('data-text')):
                all_elements.append(str(elem))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_elements = []
        for elem in all_elements:
            if elem not in seen:
                seen.add(elem)
                unique_elements.append(elem)
        
        # Combine all HTML parts
        comprehensive_html = '\n'.join(unique_elements[:300])  # Reduced to 300 elements for GPT-3.5-turbo
        
        # Truncate if still too long (reduced limit for GPT-3.5-turbo)
        MAX_HTML_CHARS = 20000
        if len(comprehensive_html) > MAX_HTML_CHARS:
            comprehensive_html = comprehensive_html[:MAX_HTML_CHARS] + "\n\n[HTML TRUNCATED - TOO LONG]"
            print(f"=== DEBUG: Comprehensive HTML truncated to {MAX_HTML_CHARS} characters ===")
        
        print(f"=== DEBUG: Sending {len(comprehensive_html)} characters of comprehensive HTML to GPT ===")
        print(f"=== DEBUG: Total unique elements: {len(unique_elements)} ===")
        
        # Send comprehensive HTML structure to GPT for DOM analysis
        prompt = f"""
Below is the comprehensive HTML structure of a psychotherapy EMR form. You have access to ALL elements including inputs, divs, spans, IDs, classes, and attributes. You can analyze the complete DOM structure to extract specific values.

COMPREHENSIVE HTML STRUCTURE:
{comprehensive_html}

EXTRACTED TEXT DATA:
{cleaned_text}

INSTRUCTIONS:
- Analyze the complete HTML DOM structure to find specific elements
- You can reference ANY element by tag, ID, class, or attributes
- Extract values from specific elements like: "span with class='service-address'", "div with id='appointment-date'", etc.
- Use the extracted text data as a reference, but prioritize the HTML structure for precise extraction
- You have access to ALL divs, spans, inputs, classes, IDs, and other HTML elements
- Look for elements with meaningful content, IDs, classes, or data attributes

QUESTION:
{question}

Please analyze the comprehensive HTML DOM structure and provide a clear, accurate answer. If the information is not found, say "not found."
"""
    else:
        # Fallback to text-only analysis
        prompt = f"""
Below is a complete psychotherapy EMR form with all fields and values extracted:

{cleaned_text}

{question}

Please analyze the form data and provide a clear, accurate answer. If the information is not found in the form, say "not found."
"""
    
    print(f"=== DEBUG: Question being asked: {question} ===")
    print(f"=== DEBUG: Prompt length: {len(prompt)} characters ===")
    print(f"=== DEBUG: First 1000 characters of prompt sent to GPT ===")
    print(prompt[:1000])
    print("=== DEBUG: Looking for Appt Date in HTML ===")
    if "07/12/2025" in comprehensive_html:
        print("✅ Found 07/12/2025 in HTML")
    else:
        print("❌ 07/12/2025 NOT found in HTML")
    if "06/16/2021" in comprehensive_html:
        print("❌ Found 06/16/2021 in HTML (OLD DATE)")
    else:
        print("✅ 06/16/2021 NOT found in HTML")
    print("=== END PROMPT DEBUG ===")
    
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that analyzes EMR forms. You can see all form fields, values, and sections. Answer questions about any part of the form clearly and accurately. If information is not present, say 'not found.'"},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=4000
    )
    
    gpt_response = response.choices[0].message.content
    print(f"=== DEBUG: GPT Response: {gpt_response} ===")
    
    return gpt_response

@router.post("/analyze-emr-file/")
def analyze_emr_file_for_ai(
    req: GenerateRequest,
    db: Session = Depends(get_db)
):
    emr_type_id = req.emr_type_id
    emr = get_emr_type(db, emr_type_id)
    if not emr:
        raise HTTPException(status_code=404, detail="EMR type not found")
    if not emr.files or len(emr.files) == 0:
        raise HTTPException(status_code=404, detail="No file found for this EMR type")
    if not emr.instructions:
        raise HTTPException(status_code=400, detail="No instructions found for this EMR type")
    
    file_url = emr.files[0].get('url')
    file_type = emr.files[0].get('type')
    if not file_url:
        raise HTTPException(status_code=400, detail="File URL missing in EMR type")
    
    region = os.getenv("AWS_REGION")
    prefix = f"https://{S3_BUCKET}.s3.{region}.amazonaws.com/"
    if not file_url.startswith(prefix):
        raise HTTPException(status_code=400, detail="File URL is not a valid S3 URL")
    
    s3_key = urllib.parse.unquote(file_url[len(prefix):])
    print(f"=== DEBUG: Loading file from S3: {s3_key} ===")
    s3_response = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
    file_content = s3_response['Body'].read()
    print(f"=== DEBUG: File content length: {len(file_content)} bytes ===")
    print(f"=== DEBUG: First 500 characters of file: {file_content.decode('utf-8', errors='ignore')[:500]} ===")
    
    if not file_type:
        file_type, _ = mimetypes.guess_type(s3_key)
    
    # Process the file content
    if file_type == "text/html":
        text = extract_full_emr_text(file_content.decode('utf-8', errors='ignore'))
    elif (file_type and file_type.startswith("text")) or file_type in [
        "application/json", "application/xml", "application/javascript", "application/xhtml+xml", "application/x-www-form-urlencoded", "application/csv"]:
        text = file_content.decode('utf-8', errors='ignore')
    else:
        raise HTTPException(status_code=400, detail=f"Cannot process non-text file type: {file_type or 'unknown'}")
    
    # GPT-4o can handle much larger files, so we can process more content
    # Only truncate if the file is extremely large (over 100,000 characters)
    MAX_CHARS = 100000  # Much larger limit for GPT-4o
    if len(text) > MAX_CHARS:
        # Truncate intelligently - try to keep complete sentences
        truncated = text[:MAX_CHARS]
        last_period = truncated.rfind('.')
        last_question = truncated.rfind('?')
        last_exclamation = truncated.rfind('!')
        
        # Find the last sentence ending
        last_sentence = max(last_period, last_question, last_exclamation)
        if last_sentence > MAX_CHARS * 0.8:  # If we can find a sentence ending in the last 20%
            text = truncated[:last_sentence + 1]
        else:
            text = truncated + "... [truncated]"
    
    # Use the instructions as the question for GPT
    answer = ask_gpt_about_emr(text, emr.instructions, file_content.decode('utf-8', errors='ignore'))
    
    # Save the response to the database
    update_emr_type(db, emr_type_id, response=answer)
    
    return {"result": answer}

@router.post("/save-response/")
def save_response(
    req: SaveResponseRequest,
    db: Session = Depends(get_db)
):
    """Save a response to the EMR type"""
    emr_type_id = req.emr_type_id
    emr = get_emr_type(db, emr_type_id)
    if not emr:
        raise HTTPException(status_code=404, detail="EMR type not found")
    
    # Update the EMR type with the response
    updated_emr = update_emr_type(db, emr_type_id, response=req.response)
    
    return {"message": "Response saved successfully", "emr_type_id": emr_type_id}

# @router.post("/analyze-emr/")
# async def analyze_emr(
#     file: UploadFile = File(...),
#     question: str = Form(...)
# ):
#     """Analyze EMR file with a specific question"""
#     file_content = await file.read()
#     file_type = file.content_type or mimetypes.guess_type(file.filename)[0]
    
#     if file_type == "text/html":
#         clean_text = extract_full_emr_text(file_content.decode('utf-8', errors='ignore'))
#     elif (file_type and file_type.startswith("text")) or file_type in [
#         "application/json", "application/xml", "application/javascript", "application/xhtml+xml", "application/x-www-form-urlencoded", "application/csv"]:
#         clean_text = file_content.decode('utf-8', errors='ignore')
#     else:
#         raise HTTPException(status_code=400, detail=f"Cannot process non-text file type: {file_type or 'unknown'}")
    
#     # Limit text length
#     MAX_CHARS = 50000
#     if len(clean_text) > MAX_CHARS:
#         clean_text = clean_text[:MAX_CHARS]
    
#     answer = ask_gpt_about_emr(clean_text, question, file_content.decode('utf-8', errors='ignore'))
#     return {"answer": answer} 


# @router.post("/analyze-html/")
# async def analyze_html(
#     instructions: str = Form(...),
#     file: UploadFile = File(...)
# ):
#     file_content = await file.read()
#     file_type = file.content_type or mimetypes.guess_type(file.filename)[0]
    
#     if (file_type and file_type.startswith("text")) or file_type in [
#         "application/json", "application/xml", "application/javascript", "application/xhtml+xml", "application/x-www-form-urlencoded", "application/csv"]:
#         text = file_content.decode('utf-8', errors='ignore')
#     else:
#         raise HTTPException(status_code=400, detail=f"Cannot process non-text file type: {file_type or 'unknown'}")
    
#     # If it's HTML, use the full EMR parser
#     if file_type == "text/html":
#         text = extract_full_emr_text(text)
    
#     prompt = f"{instructions}\n\nFile content:\n{text}"
#     response = openai_client.chat.completions.create(
#         model="gpt-3.5-turbo",
#         messages=[
#             {"role": "system", "content": "You are a helpful assistant. The user will provide a file and instructions. Follow the instructions using the file content."},
#             {"role": "user", "content": prompt}
#         ]
#     )
#     answer = response.choices[0].message.content
#     return {"result": answer}