from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from ..routes.auth import get_current_user_with_role, get_current_user_with_role_id
import openai
import os
import re
import json
import asyncio
# ThreadPoolExecutor no longer needed - using async instead
from sqlalchemy.orm import Session
from ..db import get_db
from ..crud import (
    get_emr_type, update_emr_type, get_all_emr_type_fields,
    create_emr_type_result, delete_all_emr_type_results_by_emr_type,
    get_emr_type_results_by_emr_type, get_manual_fields_by_emr_type
)
import boto3
import re
from pydantic import BaseModel
import urllib.parse
from dotenv import load_dotenv
import mimetypes
from bs4 import BeautifulSoup
from ..models import EMRTypeResult
from ..schemas import SaveSelectedChunkRequest, SelectedFieldData
from ..debug import debug
from typing import Optional
from app.utils.xpath_generator import generate_xpath_for_all_fields
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

class SaveSessionInstructionsRequest(BaseModel):
    emr_type_id: str
    session_instructions: str
    methods_instructions: Optional[str] = None
    progress_towards_goal_instructions: Optional[str] = None
    recommended_changes_instructions: Optional[str] = None

class DeleteResultRequest(BaseModel):
    emr_type_id: str
    key: str
    value: str

# create_chunks function to split HTML content into chunks its should fit within the token limit
def enhance_response_with_api_names(response_data: dict, db: Session) -> dict:
    """Enhance AI response by adding api_name from emrtypefields for each field"""
    try:
        # Get all EMR type fields from database
        from ..models import EMRTypeField
        from ..crud import _create_field_mapping, _find_matching_api_name
        
        emr_fields = db.query(EMRTypeField).all()
        
        # Use existing field mapping function instead of duplicating logic
        field_mapping = _create_field_mapping(emr_fields)
        
        # Enhance the response data with api_name
        enhanced_response = {}
        for field_key, field_data in response_data.items():
            # Use existing smart matching function instead of duplicating logic
            api_name = _find_matching_api_name(field_key, field_mapping)
            
            # Create enhanced field data (NO 'value' field)
            enhanced_field_data = {
                "api_name": api_name,
                "source": field_data.get("source", {})
            }
            
            enhanced_response[field_key] = enhanced_field_data
        
        debug("=== DEBUG: Enhanced response with api_names for {} fields ===", len(enhanced_response))
        return enhanced_response
        
    except Exception as e:
        debug("=== DEBUG: Error enhancing response with api_names: {}", str(e))
        # Return original response if enhancement fails
        return response_data



def create_chunks(html_content: str, chunk_size: int = 120000, overlap: int = 6000) -> list:
    """Split HTML content into overlapping chunks with smart chunking"""
    chunks = []
    start = 0

    while start < len(html_content):
        end = start + chunk_size
        chunk = html_content[start:end]

        # If this isn't the last chunk, try to break at a reasonable point
        if end < len(html_content):
            # Try to find a good break point (end of tag, line break, etc.)
            break_points = [
                chunk.rfind('</div>'),
                chunk.rfind('</p>'),
                chunk.rfind('</span>'),
                chunk.rfind('\n'),
                chunk.rfind(' ')
            ]

            # Find the latest break point
            valid_break_points = [bp for bp in break_points if bp > chunk_size * 0.8]
            if valid_break_points:
                best_break = max(valid_break_points)
                chunk = html_content[start:start + best_break]
                end = start + best_break

        # Smart chunking: Always include the chunk, but mark if it has meaningful content
        soup = BeautifulSoup(chunk, 'html.parser')

        # Remove script and style tags for content analysis only
        temp_soup = BeautifulSoup(str(soup), 'html.parser')
        for script in temp_soup(["script", "style"]):
            script.decompose()

        # Get text content for analysis
        text_content = temp_soup.get_text()
        meaningful_content = text_content.strip()

        # Always add the chunk (to ensure no HTML is lost)
        chunks.append(chunk)

        if meaningful_content and len(meaningful_content) > 50:
            debug("=== DEBUG: Added chunk {} with {} chars of meaningful content ===")
        else:
            debug("=== DEBUG: Added chunk {} with minimal content ({} chars) - keeping for completeness ===")

        start = end - overlap  # Overlap with previous chunk

    debug("=== DEBUG: Created {} meaningful chunks from {} characters ===")

    # Debug: Show what's in each chunk
    for i, chunk in enumerate(chunks):
        soup = BeautifulSoup(chunk, 'html.parser')
        text_content = soup.get_text().strip()
        debug("=== DEBUG: Chunk {}: {} chars, meaningful text: {} chars ===")
        debug("=== DEBUG: Chunk {}: starts with: {}... ===")
        debug("=== DEBUG: Chunk {}: ends with: ...{} ===")

    return chunks


async def process_chunk_async(chunk: str, prompt_template: str, field_instructions: str = None, field_names_str: str = None, emr_instructions: str = None) -> str:
    """Process a single chunk asynchronously - FASTER than ThreadPoolExecutor for API calls"""
    
    # Handle different parameter structures for different functions
    if field_instructions is not None:
        # For analyze_emr_type function
        prompt = prompt_template.format(
            field_instructions=field_instructions,
            html_content_for_gpt=chunk
        )
    elif field_names_str is not None and emr_instructions is not None:
        # For generate_response_emr_type function
        prompt = prompt_template.format(
            field_names_str=field_names_str,
            emr_instructions=emr_instructions,
            html_content_for_gpt=chunk
        )
    else:
        # Fallback for backward compatibility
        prompt = prompt_template.format(html_content_for_gpt=chunk)

    try:
        # Use thread pool to run synchronous create() in async context
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: openai_client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that analyzes EMR forms. Extract information accurately from the provided HTML content and return it in the specified JSON format."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000
            )
        )

        result = response.choices[0].message.content
        debug("=== DEBUG: AI Response for chunk: {}... ===")
        debug("=== DEBUG: AI Response length: {} ===")
        return result
    except Exception as e:
        debug("=== DEBUG: Error processing chunk: {} ===")
        debug("=== DEBUG: Error type: {} ===")
        return ""


async def process_chunks_async(chunks: list, prompt_template: str, emr_type_id: str = None, db: Session = None, field_instructions: str = None, field_names_str: str = None, emr_instructions: str = None) -> list:
    """Process all chunks asynchronously - MUCH FASTER than ThreadPoolExecutor"""
    debug("=== DEBUG: Processing {} chunks asynchronously ===")

    # Create async tasks for all chunks
    tasks = [
        process_chunk_async(chunk, prompt_template, field_instructions, field_names_str, emr_instructions)
        for chunk in chunks
    ]

    # Execute all tasks concurrently and track progress
    processed_responses = []
    completed_count = 0
    
    # Use asyncio.as_completed to get results as they finish
    for coro in asyncio.as_completed(tasks):
        try:
            response = await coro
            processed_responses.append(response)
            completed_count += 1
            
            # Update progress in database if emr_type_id provided
            if emr_type_id and db:
                debug("=== DEBUG: About to update database with processed_chunks={} ===")
                update_emr_type(db, emr_type_id, processed_chunks=completed_count, total_chunks=len(chunks))
                debug("=== DEBUG: Database update completed for processed_chunks={} ===")
                progress = int((completed_count / len(chunks)) * 100)
                debug("=== DEBUG: Progress: {}% ({}/{} chunks) ===")
                
        except Exception as e:
            debug("=== DEBUG: Error processing chunk: {} ===")
            processed_responses.append("")
            completed_count += 1
            
            #Update progress even for failed chunks
            if emr_type_id and db:
                update_emr_type(db, emr_type_id, processed_chunks=completed_count, total_chunks=len(chunks))
                progress = int((completed_count / len(chunks)) * 100)
                debug("=== DEBUG: Progress after error: {}% ({}/{} chunks) ===")

    return processed_responses


def normalize_field_name(field_name):
    """Normalize field name for consistency"""
    import re
    # Remove leading dashes and spaces
    cleaned = field_name.lstrip('- ').strip()
    # Normalize multiple spaces to single space
    cleaned = ' '.join(cleaned.split())
    # Replace dashes and underscores with spaces
    cleaned = re.sub(r'[-_]', ' ', cleaned)
    # Convert camelCase to spaces
    cleaned = re.sub(r'([a-z])([A-Z])', r'\1 \2', cleaned)
    # Normalize multiple spaces again
    cleaned = ' '.join(cleaned.split())
    # Convert to lowercase
    cleaned = cleaned.lower()
    return cleaned



# Genarate Response button from fe is calling that API
@router.post("/generate-response-emr-type/")
async def generate_response_emr_type(
    req: GenerateRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    emr_type_id = req.emr_type_id
    emr = get_emr_type(db, emr_type_id)
    if not emr:
        raise HTTPException(status_code=404, detail="EMR type not found")

    # Check if EMR type has been analyzed before allowing generate response
    if emr.status in ["draft", "processing"]:
        raise HTTPException(status_code=400, detail="EMR type must be analyzed first before generating response. Please run the Analyze button first.")
    
    # Check if xpath_pattern exists
    if not emr.xpath_pattern:
        raise HTTPException(status_code=400, detail="XPath pattern not found for this EMR type. Please re-analyze the EMR type.")

    # Check if all results have been processed (no more "found" or "not found" statuses)
    results = get_emr_type_results_by_emr_type(db, emr_type_id)
    unprocessed_results = [result for result in results if result.status in ['found', 'not found']]

    if unprocessed_results:
        unprocessed_fields = [result.key for result in unprocessed_results]
        raise HTTPException(
            status_code=400,
            detail=f"Cannot generate response while there are unprocessed fields with 'found' or 'not found' status. Please review and update the following fields: {', '.join(unprocessed_fields)}"
        )
    if not emr.files or len(emr.files) == 0:
        raise HTTPException(status_code=404, detail="No file found for this EMR type")
    # Get confirmed fields from results table
    confirmed_results = [result for result in results if result.status == "confirmed"]
    if not confirmed_results:
        raise HTTPException(status_code=400, detail="No confirmed fields found to generate response")
    
    debug("=== DEBUG: Generating response for {} confirmed fields ===", len(confirmed_results))
    
    # Build response data using xpath_pattern from emr_type
    xpath_patterns = emr.xpath_pattern  # Now a JSON object {label: xpath}
    
    if not xpath_patterns:
        raise HTTPException(status_code=400, detail="No XPath patterns found for this EMR type. Please re-analyze the EMR type.")
    
    response_data = {}
    
    for result in confirmed_results:
        field_key = result.key
        field_label = result.label
        
        # Look up field-specific XPath from JSON object
        field_xpath = xpath_patterns.get(field_label)
        
        if field_xpath:
            response_data[field_key] = {
                "source": {
                    "type": "xpath",
                    "xpath": field_xpath
                }
            }
            debug("=== DEBUG: Using XPath for field '{}': {} ===", field_key, field_xpath)
        else:
            debug("=== DEBUG: No XPath found for field '{}' with label '{}' ===", field_key, field_label)
    
    # Enhance the response with api_names
    enhanced_response_data = enhance_response_with_api_names(response_data, db)
    
    # Save the response to the database
    update_emr_type(db, emr_type_id, json_response=json.dumps(enhanced_response_data, indent=2), status='generated')
    debug("=== DEBUG: Updated EMR type status to 'Generated' with {} fields ===", len(enhanced_response_data))
    
    return {
        "message": "Response generated successfully",
        "fields_count": len(enhanced_response_data),
        "response": enhanced_response_data
    }


#Analyze button from the fe is calling this API
@router.post("/analyze-emr-type/{emr_type_id}")
async def analyze_emr_type(
    emr_type_id: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    # Check current status first
    emr_type = get_emr_type(db, emr_type_id)
    if not emr_type:
        raise HTTPException(status_code=404, detail="EMR type not found")
    
    # Simple logic: Check if analysis is in progress by comparing chunks
    # If total_chunks != processed_chunks, someone is analyzing
    total_chunks = emr_type.total_chunks or 0
    processed_chunks = emr_type.processed_chunks or 0
    
    debug("=== DEBUG: Analyze API - Status: {}, Total chunks: {}, Processed chunks: {}, Equal: {} ===")
    
    if total_chunks != processed_chunks:
        # Analysis is in progress - block anyone from starting new analysis
        if total_chunks and total_chunks > 0:
            progress = int((processed_chunks or 0) / total_chunks * 100)
            raise HTTPException(
                status_code=409, 
                detail=f"EMR analysis is already in progress ({progress}% complete). Please wait for it to complete."
            )
        else:
            raise HTTPException(
                status_code=409, 
                detail="EMR analysis is already in progress. Please wait for it to complete."
            )

    try:
        # Get EMR type
        emr_type = get_emr_type(db, emr_type_id)
        if not emr_type:
            raise HTTPException(status_code=404, detail="EMR type not found")

        if not emr_type.files or len(emr_type.files) == 0:
           raise HTTPException(status_code=404, detail="No file found for this EMR type")

        # Get the HTML file from S3
        file_url = emr_type.files[0].get('url')
        if not file_url:
            raise HTTPException(status_code=400, detail="File URL missing in EMR type")

        region = os.getenv("AWS_REGION")
        prefix = f"https://{S3_BUCKET}.s3.{region}.amazonaws.com/"
        if not file_url.startswith(prefix):
            raise HTTPException(status_code=400, detail="File URL is not a valid S3 URL")

        s3_key = urllib.parse.unquote(file_url[len(prefix):])
        debug("=== DEBUG: Loading file from S3: {} ===")
        s3_response = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        file_content = s3_response['Body'].read()

        # Decode the file content
        raw_html = file_content.decode('utf-8', errors='ignore')

        # Extract iframe content if present
        # soup = BeautifulSoup(raw_html, 'html.parser')
        # iframes = soup.find_all('iframe')
        # if iframes:
        #  print("✅ Found iframe content in HTML")
        #  for iframe in iframes:
        #     # Check srcdoc attribute first
        #     srcdoc = iframe.get('srcdoc')
        #     if srcdoc:
        #         debug("=== DEBUG: Found iframe with srcdoc content ===")
        #         raw_html += "\n<!-- IFRAME CONTENT -->\n" + srcdoc
        #     else:
        #         # Check src attribute
        #         src = iframe.get('src')
        #         if src:
        #             debug("=== DEBUG: Found iframe with src: {} ===")
        #         # Check inner content
        #         iframe_content = iframe.get_text(strip=True)
        #         if iframe_content:
        #             debug("=== DEBUG: Found iframe with inner content ===")
        #             raw_html += "\n<!-- IFRAME CONTENT -->\n" + iframe_content

        # Get all custom instructions from emr_type_results table
        results = get_emr_type_results_by_emr_type(db, emr_type_id)
        results = [result for result in results if result.status != "confirmed" and result.status != "ignore"]
        custom_instructions = []

        # 1. First append: Fields without instructions from results table
        fields_without_instructions = [result.key for result in results if not (result.instructions and result.instructions.strip())]
        if fields_without_instructions:
            debug("=== DEBUG: Found {} fields without instructions: {} ===")
            field_instructions = "\n".join([f"- {field_name}" for field_name in fields_without_instructions])
            custom_instructions.append(f"Fields to extract:\n{field_instructions}")

        # 2. Second append: Custom instructions from results table
        for result in results:
            if result.instructions and result.instructions.strip():
                custom_instructions.append(f"{result.key}: {result.instructions}")

        # 3. Third append: Fields that don't exist in results table at all
        all_fields = get_all_emr_type_fields(db)

        # Normalize field names for comparison (remove spaces, dashes, convert to lowercase)
        def normalize_for_comparison(name):
            return name.lower().replace(' ', '').replace('-', '').replace('_', '')

        # # 4. Fourth append: Fields which are missing in all_results table
        all_results = get_emr_type_results_by_emr_type(db, emr_type_id)
        all_results = [all_result.key for all_result in all_results]
        missing_fields = [field.name for field in all_fields if field.analyzable != "not_for_analyzing" 
                          and normalize_for_comparison(field.name) not in
                         [normalize_for_comparison(name) for name in all_results]]
        if missing_fields:
            debug("=== DEBUG: Found {} missing fields: {} ===")
            # Get instructions for missing fields from emr_type_fields table
            missing_field_instructions = []
            for field_name in missing_fields:
                # Find the field in all_fields to get its instructions
                field_obj = next((field for field in all_fields if field.name == field_name), None)
                if field_obj and field_obj.instructions and field_obj.instructions.strip():
                    missing_field_instructions.append(f"- {field_name}: {field_obj.instructions}")
                else:
                    missing_field_instructions.append(f"- {field_name}")
            
            field_instructions = "\n".join(missing_field_instructions)
            custom_instructions.append(f"Additional fields to extract:\n{field_instructions}")

        # Combine all instructions into one big instruction
        combined_instructions = "\n".join(custom_instructions)
        
        # Check if there are any fields to analyze
        if not custom_instructions or not combined_instructions.strip():
            raise HTTPException(
                status_code=400, 
                detail="There are no more fields to analyze. All fields that needs to be analyzed is already analyzed"
            )
        debug("=== DEBUG: Combined instructions: {} ===")

        # Create prompt template
        prompt_template = """Below is the HTML content of a psychotherapy EMR form. Please analyze the form and extract the following fields: {field_instructions}

Please extract ONLY the fields specified in the instructions above and provide the value found in the HTML and the actule label from where you take the value. If a field is not found or empty indicate "Not found" or "Empty".

IMPORTANT: Respond with ONLY the field names and values and label in this exact format:
FieldName: Value (label: ActualLabelFromHTML)
FieldName: Value (label: ActualLabelFromHTML)

CRITICAL FORMATTING RULES:
- Field names should NEVER be inside quotation marks - use them as plain text
- Do NOT wrap field names in quotes like "FieldName" - use FieldName directly
- Do NOT include any JSON formatting, code blocks, or fake field names
- Do NOT include any fields that were not actually found or analyzed
- Only include fields that were explicitly requested in the instructions
- Do NOT add any formatting characters like ```json, ```, or other code block markers
- Do NOT include any fields that don't exist in the original instructions

IMPORTANT — KEY NAMES
Use only the exact FieldName strings I provide.
Do not invent, alter, merge, normalize, or camelCase keys.
Key names are case-, space-, and punctuation-sensitive.
If a key is missing, still output the line with the exact FieldName key with value not found.
If a value is empty, still output the line with the exact FieldName key with value empty.

MATCHING RULES
Find the value associated with the matching on-page label.
If the HTML label differs (e.g., “Service facility address”) but clearly refers to the same field, extract the value but do not change my key.

IMPORTANT: For each field you extract, also include the actual label from the HTML that you used to find the value. For example, if you asked for "Client" but found "Client Name" in the HTML, include "Client Name" as the label. If you asked for "Appt Date" but found "Appointment Date" in the HTML, include "Appointment Date" as the label.

CRITICAL: Do NOT include any descriptive text, headers, explanations, or summary lines. Do NOT add lines like "The Requested Fields And Their Respective Values Extracted From The Html Content Are As Follows", "Here Are The Extracted Fields And Their Values From The Provided Html Content", "Certainly, Here Is The Extracted Information From The Html Content With The Specified Fields", "Here Is The Extracted Information From The Psychotherapy Emr Form", or ANY similar descriptive text. ONLY return the actual field names and their values and the label in the exact format: FieldName: Value (label: ActualLabelFromHTML)

HTML CONTENT: {html_content_for_gpt}"""

        # Create chunks from the full HTML content
        chunks = create_chunks(raw_html)

        # Store current status as previous_status before setting to processing
        current_emr = get_emr_type(db, emr_type_id)
        previous_status = current_emr.status if current_emr.status != "processing" else current_emr.previous_status
        
        # Set initial processing status with total chunks
        debug("=== DEBUG: About to update status to 'processing' for emr_type_id={} ===")
        update_emr_type(db, emr_type_id, status="processing", previous_status=previous_status, total_chunks=len(chunks), processed_chunks=0)
        debug("=== DEBUG: Status update to 'processing' completed ===")
        debug("=== DEBUG: Started processing {} chunks ===")

        if len(chunks) == 1:
            # Single chunk - process normally
            debug("=== DEBUG: Processing single chunk ===")
            prompt = prompt_template.format(
                field_instructions=combined_instructions,
                html_content_for_gpt=chunks[0]
            )

            try:
                response = openai_client.chat.completions.create(
                    model="gpt-5-mini",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that analyzes EMR forms. Extract information accurately from the provided HTML content and list each field with its value and label. CRITICAL: ALWAYS include the label for every field, even when the value is 'Empty' or 'Not found'. The format must be: FieldName: Value (label: ActualLabelFromHTML)."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4000
                )
                result = response.choices[0].message.content
                debug("=== DEBUG: AI Response: {} ===")

                # Return single chunk response
                return {
                    "message": "Analysis completed successfully",
                    "chunks_available": 1,
                    "all_chunks": [result]
                }

            except Exception as e:
                debug("=== DEBUG: Error processing single chunk: {} ===")
                raise HTTPException(status_code=500, detail=f"Error processing EMR content: {str(e)}")
        
        else:
            # Multiple chunks - process asynchronously with progress tracking
            debug("=== DEBUG: Processing {} chunks asynchronously ===")
            chunk_responses = await process_chunks_async(chunks, prompt_template, emr_type_id, db, field_instructions=combined_instructions)            
            # Format chunks for frontend
            formatted_chunks = []
            for i, response in enumerate(chunk_responses):
                formatted_chunks.append({
                    "chunk_index": i,
                    "response": response,
                    "chunk_size": len(chunks[i]) if i < len(chunks) else 0
                })
            
            # Keep status as "processing" - wait for user confirmation
            debug("=== DEBUG: Analysis completed successfully ===")
            
            return {
                "message": "Analysis completed successfully",
                "chunks_available": len(formatted_chunks),
                "all_chunks": formatted_chunks
            }

    except Exception as e:
        debug("=== DEBUG: Error in analyze_emr_type: {} ===")
        raise HTTPException(status_code=500, detail=f"Error analyzing EMR: {str(e)}")



@router.post("/save-selected-chunk/")
async def save_selected_chunk(
    req: SaveSelectedChunkRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Save the selected chunk data and individual fields to database"""
    emr_type_id = req.emr_type_id
    selected_chunks = req.selected_chunks or []
    selected_fields = req.selected_fields or []

    debug("=== DEBUG: Saving {} selected chunks and {} individual fields for EMR type {} ===", len(selected_chunks), len(selected_fields), emr_type_id)

    # Track unique values for each field
    field_values = {}

    # Process each chunk response only if selected_chunks is not empty
    if selected_chunks:
        for chunk_data in selected_chunks:
            selected_chunk_response = chunk_data.selected_chunk_response
            chunk_index = chunk_data.selected_chunk_index
            selected_chunk_label = chunk_data.selected_chunk_label or ''

            debug("=== DEBUG: Processing chunk {} with label: {} ===")

            # Parse the selected chunk response
            if selected_chunk_response and selected_chunk_response.strip():
                lines = selected_chunk_response.strip().split('\n')
                for line in lines:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()

                        # Extract label from value if present
                        extracted_label = ""
                        clean_value = value

                        # Check if value contains (label: ...) pattern
                        if '(label:' in value:
                            try:
                                # Find the label part
                                label_start = value.find('(label:')
                                label_end = value.find(')', label_start)

                                if label_start != -1 and label_end != -1:
                                    # Extract the label content
                                    label_content = value[label_start + 7:label_end].strip()  # 7 = len('(label:')

                                    # Remove the entire (label: ...) part from value
                                    clean_value = value[:label_start].strip()

                                    # Always use label if it has content, regardless of value status
                                    if label_content:
                                        extracted_label = label_content
                                    else:
                                        # Empty label, keep label empty
                                        extracted_label = ""
                                else:
                                    # Invalid format, keep original value
                                    clean_value = value
                            except:
                                # Any error, keep original value
                                clean_value = value
                        else:
                            # No label found, keep original value
                            clean_value = value

                        # Initialize field if not exists
                        if key not in field_values:
                            field_values[key] = {'values': set(), 'label': selected_chunk_label}

                        # Add clean value to field (set automatically handles duplicates)
                        field_values[key]['values'].add(clean_value)

                        # Update label if we extracted one
                        if extracted_label:
                            field_values[key]['label'] = extracted_label

                debug("=== DEBUG: Parsed results from chunk {}: {} ===")

    # Process individual field selections only if selected_fields is not empty
    if selected_fields:
        for field_data in selected_fields:
            field_name = field_data.field_name
            field_value = field_data.field_value
            chunk_index = field_data.chunk_index
            chunk_label = field_data.chunk_label or ''
            debug("=== DEBUG: Processing individual field '{}' with value '{}' from chunk {} ===", field_name, field_value, chunk_index)
            
            # Extract label from value if present (same logic as chunks)
            extracted_label = ""
            clean_value = field_value
            
            # Check if value contains (label: ...) pattern
            if '(label:' in field_value:
                try:
                    # Find the label part
                    label_start = field_value.find('(label:')
                    label_end = field_value.find(')', label_start)
                    
                    if label_start != -1 and label_end != -1:
                        # Extract the label content
                        label_content = field_value[label_start + 7:label_end].strip()  # 7 = len('(label:')
                        
                        # Remove the entire (label: ...) part from value
                        clean_value = field_value[:label_start].strip()
                        
                        # Use label if it has content
                        if label_content:
                            extracted_label = label_content
                    else:
                        # Invalid format, keep original value
                        clean_value = field_value
                except:
                    # Any error, keep original value
                    clean_value = field_value
            else:
                # No label found, keep original value
                clean_value = field_value
            
            # Initialize field if not exists
            if field_name not in field_values:
                field_values[field_name] = {'values': set(), 'label': chunk_label}
            
            # Add clean value to field (set automatically handles duplicates)
            field_values[field_name]['values'].add(clean_value)
            
            # Update label if we extracted one
            if extracted_label:
                field_values[field_name]['label'] = extracted_label
            
            debug("=== DEBUG: Added individual field '{}': '{}' (label: '{}') ===", field_name, clean_value, extracted_label or chunk_label)

    # Convert sets to lists and save each unique value as separate row
    for field, field_data in field_values.items():
        values_list = list(field_data['values'])  # Convert set to list (sets already handle duplicates)
        label = field_data['label']

        clean_key = normalize_field_name(field)
        # Check if this field already exists in the database
        existing_result = db.query(EMRTypeResult).filter(
            EMRTypeResult.emr_type_id == emr_type_id,
            EMRTypeResult.key == clean_key
        ).first()

        # Find the best value to use
        best_value = None
        best_label = ""
        
        if selected_chunks:
            for value in values_list:
                if value.lower() != "not found":
                    best_value = value
                    best_label = label
                    break
        elif selected_fields:
            best_value = values_list[0] if values_list else None
            best_label = label

        # If we found a good value, either update existing or create new
        if best_value:
            if existing_result and existing_result.status != "ignore" and existing_result.status != "confirmed":
                # Update existing result with new value and label
                existing_result.value = best_value
                existing_result.label = best_label
                existing_result.status = 'found' if 'not found' not in best_value.lower() else 'not found'
                db.commit()
                debug("=== DEBUG: Updated existing field {}: {} (label: {}) ===", field, best_value, best_label)
            else:
                # Create new result
                create_emr_type_result(
                    db=db,
                    emr_type_id=emr_type_id,
                    key=clean_key,
                    value=best_value,
                    status='found' if 'not found' not in best_value.lower() else 'not found',
                    label=best_label
                )
                debug("=== DEBUG: Created new field {}: {} (label: {}) ===", field, best_value, best_label)

    debug("=== DEBUG: Saved {} fields with multiple values ===")

    # Generate XPath pattern from the HTML and collected field data
    try:
        emr_type = get_emr_type(db, emr_type_id)
        if emr_type and emr_type.files and len(emr_type.files) > 0:
            # Get the HTML file from S3
            file_url = emr_type.files[0].get('url')
            if file_url:
                region = os.getenv("AWS_REGION")
                prefix = f"https://{S3_BUCKET}.s3.{region}.amazonaws.com/"
                if file_url.startswith(prefix):
                    s3_key = urllib.parse.unquote(file_url[len(prefix):])
                    s3_response = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
                    file_content = s3_response['Body'].read()
                    raw_html = file_content.decode('utf-8', errors='ignore')
                    
                    # Prepare field data for XPath generation (only fields with actual values)
                    field_data_for_xpath = {}
                    for field, field_data in field_values.items():
                        values_list = list(field_data['values'])
                        label = field_data['label']
                        
                        # Find a valid value and label (not "not found" or "empty")
                        for value in values_list:
                            if value.lower() in ['not found', 'empty', ''] or \
                               not label or label.lower() in ['not found', 'empty', '']:
                                continue
                            field_data_for_xpath[field] = {
                                'value': value,
                                'label': label
                            }
                            break
                    
                    # Generate individual XPath patterns for each field
                    if field_data_for_xpath:
                        debug("=== DEBUG: Generating individual XPath patterns for {} fields ===", len(field_data_for_xpath))
                        xpath_result = generate_xpath_for_all_fields(raw_html, field_data_for_xpath)
                        
                        if xpath_result and xpath_result.get('xpath_patterns') is not None:
                            new_xpath_patterns = xpath_result.get('xpath_patterns') or {}
                            is_popup = xpath_result.get('is_popup', False)
                            popup_root_selector = xpath_result.get('popup_root_selector')
                            
                            debug("=== DEBUG: Generated {} new XPath patterns ===", len(new_xpath_patterns))
                            debug("=== DEBUG: Popup detected: {}, Selector: {} ===", is_popup, popup_root_selector)
                            
                            # Always save generated XPaths (no validation check)
                            existing_xpaths = emr_type.xpath_pattern or {}
                            if isinstance(existing_xpaths, str):
                                # Handle legacy string format
                                existing_xpaths = {}
                            
                            # Merge: new patterns override existing ones for same labels
                            merged_xpaths = {**existing_xpaths, **new_xpath_patterns}
                            
                            debug("=== DEBUG: Merged XPaths: {} existing + {} new = {} total ===", 
                                  len(existing_xpaths), len(new_xpath_patterns), len(merged_xpaths))
                            
                            # Update EMR type with merged xpath_patterns, popup info, and status
                            update_emr_type(
                                db, 
                                emr_type_id, 
                                xpath_pattern=merged_xpaths, 
                                is_popup=is_popup,
                                popup_root_selector=popup_root_selector,
                                status='analyzed'
                            )
                            debug("=== DEBUG: Updated EMR type with merged XPath patterns, popup info, and status 'analyzed' ===")
                        else:
                            debug("=== DEBUG: Could not generate XPath patterns, updating status only ===")
                            update_emr_type(db, emr_type_id, status='analyzed')
                    else:
                        debug("=== DEBUG: No valid fields for XPath generation, updating status only ===")
                        update_emr_type(db, emr_type_id, status='analyzed')
                else:
                    update_emr_type(db, emr_type_id, status='analyzed')
            else:
                update_emr_type(db, emr_type_id, status='analyzed')
        else:
            update_emr_type(db, emr_type_id, status='analyzed')
    except Exception as e:
        debug("=== DEBUG: Error generating XPath pattern: {} ===", str(e))
        # Still update status even if XPath generation fails
        update_emr_type(db, emr_type_id, status='analyzed')

    total_selections = len(selected_chunks) + len(selected_fields)
    message_parts = []
    if selected_chunks:
        message_parts.append(f"{len(selected_chunks)} chunk{'' if len(selected_chunks) == 1 else 's'}")
    if selected_fields:
        message_parts.append(f"{len(selected_fields)} individual field{'' if len(selected_fields) == 1 else 's'}")
    
    message = f"Successfully saved {' and '.join(message_parts) if message_parts else 'no selections'}"
    
    return {
        "message": message,
        "chunks_processed": len(selected_chunks),
        "fields_processed": len(selected_fields),
        "total_processed": total_selections,
    }

# Get current analysis progress for a specific EMR type, get called every few seconds from the FE while analyzing
@router.get("/analyze-progress/{emr_type_id}")
async def get_analyze_progress(
    emr_type_id: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Get current analysis progress"""
    try:
        # Get EMR type
        emr_type = get_emr_type(db, emr_type_id)
        if not emr_type:
            raise HTTPException(status_code=404, detail="EMR type not found")

        # Get total chunks and processed chunks from database
        total_chunks = getattr(emr_type, 'total_chunks', 0)
        processed_chunks = getattr(emr_type, 'processed_chunks', 0)
        
        debug("=== DEBUG: Progress endpoint - total_chunks={}, processed_chunks={} ===")
        
        # Calculate progress based on actual chunks processed
        if total_chunks > 0:
            progress = int((processed_chunks / total_chunks) * 100)
        else:
            progress = 0
        
        debug("=== DEBUG: Progress endpoint - calculated progress={}% ===")
        
        # Check if analysis is complete
        if progress >= 100:
            return {
                "emr_type_id": emr_type_id,
                "progress": 100,
                "status": "completed",
                "message": "Analysis completed successfully"
            }
        else:
            return {
                "emr_type_id": emr_type_id,
                "progress": progress,
                "status": "processing",
                "message": f"Processing analysis... {progress}% complete ({processed_chunks}/{total_chunks} chunks)"
            }
    

    except Exception as e:
        debug("=== DEBUG: Error getting progress: {} ===")
        raise HTTPException(status_code=500, detail=f"Error getting progress: {str(e)}")

# Delete a specific result row from the database emr_type_results table
@router.delete("/delete-result/")
async def delete_result(
    req: DeleteResultRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role_id([3]))  # Only Role 3 (super_admin)
):
    """Delete a specific result row from the database"""
    emr_type_id = req.emr_type_id
    key = req.key
    value = req.value

    debug("=== DEBUG: Deleting result for EMR type {}, key: {}, value: {} ===")

    try:
        # Find and delete the specific result
        result = db.query(EMRTypeResult).filter(
            EMRTypeResult.emr_type_id == emr_type_id,
            EMRTypeResult.key == key,
            EMRTypeResult.value == value
        ).first()

        if result:
            db.delete(result)
            db.commit()
            debug("=== DEBUG: Successfully deleted result for key: {}, value: {} ===")
            return {
                "message": f"Result for key '{key}' with value '{value}' deleted successfully",
                "deleted_key": key,
                "deleted_value": value
            }
        else:
            raise HTTPException(status_code=404, detail=f"Result for key '{key}' with value '{value}' not found")

    except Exception as e:
        db.rollback()
        debug("=== DEBUG: Error deleting result: {} ===")
        raise HTTPException(status_code=500, detail=f"Error deleting result: {str(e)}")