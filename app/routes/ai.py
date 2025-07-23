from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
import openai
import os
import re
from sqlalchemy.orm import Session
from ..db import get_db
from ..crud import (
    get_emr_type, update_emr_type, get_all_emr_type_fields,
    create_emr_type_result, delete_all_emr_type_results_by_emr_type,
    get_emr_type_results_by_emr_type
)
import boto3
from pydantic import BaseModel
import urllib.parse
from dotenv import load_dotenv
import mimetypes
from bs4 import BeautifulSoup
from ..models import EMRTypeResult
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

def truncate_html_for_tokens(html_content: str, max_chars: int = 150000) -> str:
    if len(html_content) <= max_chars:
        return html_content

    print(f"=== DEBUG: HTML too large ({len(html_content)} chars), truncating to {max_chars} chars ===")

    soup = BeautifulSoup(html_content, 'html.parser')

    form_elements = []

    # Keep ALL inputs, labels, selects, textareas (don't filter them out)
    inputs = soup.find_all(['input', 'label', 'select', 'textarea'])
    form_elements.extend(inputs)

    # Get divs with form-related classes (more inclusive filtering)
    form_divs = soup.find_all('div', class_=lambda x: x and any(word in x.lower() for word in ['form', 'control', 'group', 'description', 'lut']))
    form_elements.extend(form_divs)

    # Get spans with important content (more inclusive keywords)
    important_keywords = ['client', 'date', 'time', 'duration', 'program', 'location', 'address', 'staff', 'appt', 'no-show', 'delivered', 'service', 'facility']
    important_elements = soup.find_all(['span', 'div'], string=lambda x: x and any(word in x.lower() for word in important_keywords))
    form_elements.extend(important_elements)

    # Get ALL elements with title attributes (important for client names)
    title_elements = soup.find_all(attrs={'title': True})
    form_elements.extend(title_elements)

    # Get ALL elements with aria-label attributes (important for form fields)
    aria_elements = soup.find_all(attrs={'aria-label': True})
    form_elements.extend(aria_elements)

    new_html = f"""<!DOCTYPE html>
<html>
<head><title>Form Data</title></head>
<body>
"""

    element_count = 0
    max_elements = 400

    for element in form_elements:
        if element_count >= max_elements:
                    break
        new_html += str(element) + "\n"
        element_count += 1

    new_html += "</body></html>"

    if len(new_html) > max_chars:
        print(f"=== DEBUG: Still too large after form extraction ({len(new_html)} chars), using aggressive fallback ===")
        new_html = extract_only_essential_elements(html_content, max_chars)

    print(f"=== DEBUG: Final HTML size: {len(new_html)} chars with {element_count} elements ===")
    return new_html

def extract_only_essential_elements(html_content: str, max_chars: int) -> str:
    soup = BeautifulSoup(html_content, 'html.parser')
    
    essential_elements = []

    # Get ALL inputs (don't filter them out)
    all_inputs = soup.find_all('input')
    essential_elements.extend(all_inputs)

    # Get ALL labels
    all_labels = soup.find_all('label')
    essential_elements.extend(all_labels)

    # Get ALL elements with title attributes (important for client names)
    title_elements = soup.find_all(attrs={'title': True})
    essential_elements.extend(title_elements)

    # Get ALL elements with aria-label attributes (important for form fields)
    aria_elements = soup.find_all(attrs={'aria-label': True})
    essential_elements.extend(aria_elements)

    # Get elements with specific classes that contain our data
    essential_classes = soup.find_all(attrs={'class': lambda x: x and any(word in x.lower() for word in ['description-text', 'lut-description', 'form-control', 'form-group'])})
    essential_elements.extend(essential_classes)

    # Get elements with specific IDs or classes that contain our target data
    essential_ids = soup.find_all(attrs={'id': lambda x: x and any(word in x.lower() for word in ['date', 'time', 'duration', 'client', 'program', 'location', 'staff', 'ctrl'])})
    essential_elements.extend(essential_ids)

    new_html = f"""<!DOCTYPE html>
<html>
<head><title>Essential Form Data</title></head>
<body>
"""

    element_count = 0
    max_elements = 300

    for element in essential_elements:
        if element_count >= max_elements:
                        break
        new_html += str(element) + "\n"
        element_count += 1

    new_html += "</body></html>"

    if len(new_html) > max_chars:
        print(f"=== DEBUG: Even aggressive extraction too large ({len(new_html)} chars), final truncation ===")
        new_html = new_html[:max_chars] + "\n<!-- FINAL TRUNCATED -->"

    print(f"=== DEBUG: Aggressive extraction: {len(new_html)} chars with {element_count} essential elements ===")
    return new_html


@router.post("/analyze-emr-file/")
def analyze_emr_file_for_ai(
    req: GenerateRequest,
    db: Session = Depends(get_db)
):
    emr_type_id = req.emr_type_id
    emr = get_emr_type(db, emr_type_id)
    if not emr:
        raise HTTPException(status_code=404, detail="EMR type not found")
    
    # Check if EMR type has been analyzed before allowing generate response
    if emr.status != 'analyzed':
        raise HTTPException(status_code=400, detail="EMR type must be analyzed first before generating response. Please run the Analyze button first.")
    
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
    
    # Decode the file content
    raw_html = file_content.decode('utf-8', errors='ignore')
    print(f"=== DEBUG: First 500 characters of file: {raw_html[:500]} ===")
    
    # Extract iframe content if present
    soup = BeautifulSoup(raw_html, 'html.parser')
    iframes = soup.find_all('iframe')
    if iframes:
        print("✅ Found iframe content in HTML")
        for iframe in iframes:
            # Check srcdoc attribute first
            srcdoc = iframe.get('srcdoc')
            if srcdoc:
                print(f"=== DEBUG: Found iframe with srcdoc content ===")
                raw_html += "\n<!-- IFRAME CONTENT -->\n" + srcdoc
            else:
                # Check src attribute
                src = iframe.get('src')
                if src:
                    print(f"=== DEBUG: Found iframe with src: {src} ===")
                # Check inner content
                iframe_content = iframe.get_text(strip=True)
                if iframe_content:
                    print(f"=== DEBUG: Found iframe with inner content ===")
                    raw_html += "\n<!-- IFRAME CONTENT -->\n" + iframe_content
    
    # Check for 'checked' attribute in HTML
    if 'checked' in raw_html.lower():
        print("✅ Found 'checked' in HTML")
    
    print("=== END DEBUG ===")
    
    if not file_type:
        file_type, _ = mimetypes.guess_type(s3_key)
    
    # Process the file content
    if file_type == "text/html":
        # Use the new truncation function
        html_content_for_gpt = truncate_html_for_tokens(raw_html)
    elif (file_type and file_type.startswith("text")) or file_type in [
        "application/json", "application/xml", "application/javascript", "application/xhtml+xml", "application/x-www-form-urlencoded", "application/csv"]:
        # For non-HTML, just decode and pass as is
        html_content_for_gpt = raw_html
    else:
        raise HTTPException(status_code=400, detail=f"Cannot process non-text file type: {file_type or 'unknown'}")
    
    # Only truncate if the file is extremely large (over 100,000 characters)
    MAX_CHARS = 100000  # Much larger limit for GPT-4o
    if len(html_content_for_gpt) > MAX_CHARS:
        # Truncate intelligently - try to keep complete sentences
        truncated = html_content_for_gpt[:MAX_CHARS]
        last_period = truncated.rfind('.')
        last_question = truncated.rfind('?')
        last_exclamation = truncated.rfind('!')
        
        # Find the last sentence ending
        last_sentence = max(last_period, last_question, last_exclamation)
        if last_sentence > MAX_CHARS * 0.8:  # If we can find a sentence ending in the last 20%
            html_content_for_gpt = truncated[:last_sentence + 1]
        else:
            html_content_for_gpt = truncated + "... [truncated]"
    
    # Use the instructions as the question for GPT
    prompt = f"""
Below is the HTML content of a psychotherapy EMR form. Please analyze the form and extract the requested information.

HTML CONTENT:
{html_content_for_gpt}

INSTRUCTIONS:
{emr.instructions}

Please provide a clear, accurate response based on the HTML content and instructions provided.
"""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes EMR forms. Extract information accurately from the provided HTML content."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000
        )
        
        answer = response.choices[0].message.content
    except Exception as e:
        print(f"ERROR:root:Unhandled error for request http://localhost:8001/api/v1/ai/analyze-emr-file/: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")
    
    # Save the response to the database
    update_emr_type(db, emr_type_id, response=answer)
    
    # Update status to 'generated' after successful response generation
    update_emr_type(db, emr_type_id, status='generated')
    print(f"=== DEBUG: Updated EMR type status to 'Generated' after response generation ===")
    
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

@router.post("/analyze-emr-chatgpt-style/")
def analyze_emr_chatgpt_style(
    req: GenerateRequest,
    db: Session = Depends(get_db)
):
    """Analyze EMR file using ChatGPT-style approach"""
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
    
    # Decode the file content
    raw_html = file_content.decode('utf-8', errors='ignore')
    
    # Extract iframe content if present
    soup = BeautifulSoup(raw_html, 'html.parser')
    iframes = soup.find_all('iframe')
    if iframes:
        print("✅ Found iframe content in HTML")
        for iframe in iframes:
            # Check srcdoc attribute first
            srcdoc = iframe.get('srcdoc')
            if srcdoc:
                print(f"=== DEBUG: Found iframe with srcdoc content ===")
                raw_html += "\n<!-- IFRAME CONTENT -->\n" + srcdoc
            else:
                # Check src attribute
                src = iframe.get('src')
                if src:
                    print(f"=== DEBUG: Found iframe with src: {src} ===")
                # Check inner content
                iframe_content = iframe.get_text(strip=True)
                if iframe_content:
                    print(f"=== DEBUG: Found iframe with inner content ===")
                    raw_html += "\n<!-- IFRAME CONTENT -->\n" + iframe_content
    
    # Use the new truncation function
    html_content_for_gpt = truncate_html_for_tokens(raw_html)
    
    # Use the instructions as the question for GPT
    prompt = f"""
Below is the HTML content of a psychotherapy EMR form. Please analyze the form and extract the requested information.

HTML CONTENT:
{html_content_for_gpt}

INSTRUCTIONS:
{emr.instructions}

Please provide a clear, accurate response based on the HTML content and instructions provided.
"""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes EMR forms. Extract information accurately from the provided HTML content."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000
        )
        
        answer = response.choices[0].message.content
    except Exception as e:
        print(f"ERROR:root:Unhandled error for request http://localhost:8001/api/v1/ai/analyze-emr-chatgpt-style/: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")
    
    # Save the response to the database
    update_emr_type(db, emr_type_id, response=answer)
    
    return {"result": answer}

@router.post("/analyze-emr-type/{emr_type_id}")
def analyze_emr_type(
    emr_type_id: str,
    db: Session = Depends(get_db)
):
    """Analyze EMR type using field definitions and save results"""
    
    # Get the EMR type
    emr = get_emr_type(db, emr_type_id)
    if not emr:
        raise HTTPException(status_code=404, detail="EMR type not found")
    
    if not emr.files or len(emr.files) == 0:
        raise HTTPException(status_code=404, detail="No file found for this EMR type")
    
    # Get all field names from emr_type_fields
    fields = get_all_emr_type_fields(db)
    if not fields:
        raise HTTPException(status_code=404, detail="No fields defined for EMR type")
    
    field_names = [field.name for field in fields]
    print(f"=== DEBUG: Found {len(field_names)} fields to extract: {field_names} ===")
    
    # Get the HTML file from S3
    file_url = emr.files[0].get('url')
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
    
    # Decode the file content
    raw_html = file_content.decode('utf-8', errors='ignore')
    
    # Extract iframe content if present
    soup = BeautifulSoup(raw_html, 'html.parser')
    iframes = soup.find_all('iframe')
    if iframes:
        print("✅ Found iframe content in HTML")
        for iframe in iframes:
            srcdoc = iframe.get('srcdoc')
            if srcdoc:
                print(f"=== DEBUG: Found iframe with srcdoc content ===")
                raw_html += "\n<!-- IFRAME CONTENT -->\n" + srcdoc
    
    # Use the truncation function
    html_content_for_gpt = truncate_html_for_tokens(raw_html)
    
    # Create dynamic instructions based on field names
    field_instructions = "\n".join([f"- {field_name}" for field_name in field_names])
    
    # Create the prompt with dynamic field instructions
    prompt = f"""
Below is the HTML content of a psychotherapy EMR form. Please analyze the form and extract the following fields:

{field_instructions}

Please extract each field and provide the value found in the HTML. If a field is not found or empty, indicate "Not found" or "Empty".

IMPORTANT: Respond with ONLY the field names and values in this exact format:
FieldName: Value
FieldName: Value

Do not include any descriptive text, explanations, or other content.

HTML CONTENT:
{html_content_for_gpt}
"""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes EMR forms. Extract information accurately from the provided HTML content and list each field with its value."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000
        )
        
        answer = response.choices[0].message.content
        print(f"=== DEBUG: AI Response: {answer} ===")
        
        # Parse the AI response into key-value pairs
        # Expected format: "Client: John Doe\nDate: 07/12/2025\nDuration: 00:30"
        lines = answer.strip().split('\n')
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                # Check if result already exists to preserve instructions
                existing_result = db.query(EMRTypeResult).filter(
                    EMRTypeResult.emr_type_id == emr_type_id,
                    EMRTypeResult.key == key
                ).first()
                
                if existing_result:
                    # Update only the value, preserve existing instructions
                    existing_result.value = value
                    db.commit()
                    print(f"=== DEBUG: Updated {key}: {value} (preserved instructions) ===")
                else:
                    # Create new result with empty instructions
                    create_emr_type_result(
                        db=db,
                        emr_type_id=emr_type_id,
                        key=key,
                        value=value
                    )
                    print(f"=== DEBUG: Created {key}: {value} ===")
        
        # Generate JSON instructions from the results
        results = get_emr_type_results_by_emr_type(db, emr_type_id)
        json_instructions = generate_json_instructions_from_results(results)
        
        # Save the generated JSON instructions to the EMR type
        update_emr_type(db, emr_type_id, instructions=json_instructions)
        print(f"=== DEBUG: Saved generated JSON instructions to EMR type ===")
        
        # Update status to 'analyzed' after successful analysis
        update_emr_type(db, emr_type_id, status='analyzed')
        print(f"=== DEBUG: Updated EMR type status to 'Analyzed' ===")
        
        return {"message": "Analysis completed successfully"}
        
    except Exception as e:
        print(f"ERROR: Analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

def generate_json_instructions_from_results(results):
    """Generate JSON instructions from analysis results"""
    
    # Start with the header
    json_instructions = """JSON OUTPUT INSTRUCTION
return a single JSON object in the following format:

"""
    
    # Generate the JSON structure for each result
    json_instructions += "{\n"
    
    for i, result in enumerate(results):
        # Check if field has specific instructions
        if result.instructions and result.instructions.strip():
            # Field HAS instructions - generate specific JSON based on instructions
            selector, attribute = parse_instructions_to_selector(result.instructions)
            
            json_instructions += f'  "{result.key}": {{\n'
            json_instructions += f'    "value": "put the extracted value here",\n'
            json_instructions += f'    "source": {{\n'
            json_instructions += f'      "selector": "{selector}",\n'
            json_instructions += f'      "attribute": "{attribute}"\n'
            json_instructions += f'    }}\n'
            json_instructions += f'  }}{"," if i < len(results) - 1 else ""}\n'
        else:
            # Field has NO instructions - use current generic template
            template_selector = f"exact CSS selector path (e.g. {result.key.lower()}-selector)"
            
            json_instructions += f'  "{result.key}": {{\n'
            json_instructions += f'    "value": "put the extracted value here",\n'
            json_instructions += f'    "source": {{\n'
            json_instructions += f'      "selector": "{template_selector}",\n'
            json_instructions += f'      "attribute": "attribute you used (title, value, textContent, checked)"\n'
            json_instructions += f'    }}\n'
            json_instructions += f'  }}{"," if i < len(results) - 1 else ""}\n'
    
    json_instructions += """}

IMPORTANT RULES:
1. The "selector" should ONLY contain the CSS selector path - DO NOT include the actual values in the selector
2. The "attribute" should specify which attribute you used to extract the value (title, value, textContent, checked)
3. Look for the EXACT selectors in the HTML you receive. Don't use generic selectors - use the specific IDs, classes, and attributes you actually see in the HTML.
4. The selector should be reusable - someone should be able to use that same selector to find the element again.

You must output JSON for all fields. Always display in source the selector and attribute even if value is "empty" or "false"."""
    
    return json_instructions

def parse_instructions_to_selector(instructions):
    """Parse instructions to generate specific CSS selector and attribute"""
    instructions_lower = instructions.lower()
    
    # Default values
    selector = "exact CSS selector path"
    attribute = "attribute you used (title, value, textContent, checked)"
    
    # Parse for element types
    if "<a>" in instructions_lower or "a element" in instructions_lower:
        selector = "a"
    elif "<input>" in instructions_lower or "input element" in instructions_lower:
        selector = "input"
    elif "<div>" in instructions_lower or "div element" in instructions_lower:
        selector = "div"
    elif "<span>" in instructions_lower or "span element" in instructions_lower:
        selector = "span"
    elif "<label>" in instructions_lower or "label element" in instructions_lower:
        selector = "label"
    
    # Parse for classes
    if "class containing" in instructions_lower:
        # Extract class names from instructions
        import re
        class_matches = re.findall(r'class.*?["\']([^"\']+)["\']', instructions, re.IGNORECASE)
        if class_matches:
            classes = class_matches[0].split()
            selector += "." + ".".join(classes)
        else:
            # Look for class names mentioned
            class_keywords = ["formset-link-format", "lut-description", "client-name", "date-input", "time-input"]
            found_classes = []
            for keyword in class_keywords:
                if keyword in instructions_lower:
                    found_classes.append(keyword)
            if found_classes:
                selector += "." + ".".join(found_classes)
    
    # Parse for IDs
    if "id containing" in instructions_lower:
        # Extract ID patterns from instructions
        import re
        id_matches = re.findall(r'id.*?["\']([^"\']+)["\']', instructions, re.IGNORECASE)
        if id_matches:
            selector = f"#{id_matches[0]}"
        else:
            # Look for ID patterns mentioned
            if "input-date" in instructions_lower and "input-time" in instructions_lower:
                selector = "input[id*='input-date'], input[id*='input-time']"
            elif "input-date" in instructions_lower:
                selector = "input[id*='input-date']"
            elif "input-time" in instructions_lower:
                selector = "input[id*='input-time']"
    
    # Parse for attributes
    if "title attribute" in instructions_lower or "title" in instructions_lower:
        attribute = "title"
    elif "value attribute" in instructions_lower or "value" in instructions_lower:
        attribute = "value"
    elif "textcontent" in instructions_lower or "text content" in instructions_lower:
        attribute = "textContent"
    elif "checked" in instructions_lower:
        attribute = "checked"
    
    return selector, attribute

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