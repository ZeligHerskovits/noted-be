from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from ..routes.auth import get_current_user_with_role
import openai
import os
import re
import asyncio
# ThreadPoolExecutor no longer needed - using async instead
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
from ..schemas import SaveSelectedChunkRequest
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



class DeleteResultRequest(BaseModel):
    emr_type_id: str
    key: str
    value: str

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
            print(f"=== DEBUG: Added chunk {len(chunks)} with {len(meaningful_content)} chars of meaningful content ===")
        else:
            print(f"=== DEBUG: Added chunk {len(chunks)} with minimal content ({len(meaningful_content)} chars) - keeping for completeness ===")

        start = end - overlap  # Overlap with previous chunk

    print(f"=== DEBUG: Created {len(chunks)} meaningful chunks from {len(html_content)} characters ===")

    # Debug: Show what's in each chunk
    for i, chunk in enumerate(chunks):
        soup = BeautifulSoup(chunk, 'html.parser')
        text_content = soup.get_text().strip()
        print(f"=== DEBUG: Chunk {i+1}: {len(chunk)} chars, meaningful text: {len(text_content)} chars ===")
        print(f"=== DEBUG: Chunk {i+1}: starts with: {chunk[:100]}... ===")
        print(f"=== DEBUG: Chunk {i+1}: ends with: ...{chunk[-100:]} ===")

    return chunks


async def process_chunk_async(chunk: str, prompt_template: str, field_instructions: str) -> str:
    """Process a single chunk asynchronously - FASTER than ThreadPoolExecutor for API calls"""
    prompt = prompt_template.format(
        field_instructions=field_instructions,
        html_content_for_gpt=chunk
    )

    try:
        # Use thread pool to run synchronous create() in async context
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that analyzes EMR forms. Extract information accurately from the provided HTML content and list each field with its value."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000
            )
        )

        result = response.choices[0].message.content
        print(f"=== DEBUG: AI Response for chunk: {result[:200]}... ===")
        return result
    except Exception as e:
        print(f"=== DEBUG: Error processing chunk: {str(e)} ===")
        return ""

# process_chunk_sync function removed - using async version instead

async def process_chunks_async(chunks: list, prompt_template: str, field_instructions: str, emr_type_id: str = None, db: Session = None) -> list:
    """Process all chunks asynchronously - MUCH FASTER than ThreadPoolExecutor"""
    print(f"=== DEBUG: Processing {len(chunks)} chunks asynchronously ===")

    # Create async tasks for all chunks
    tasks = [
        process_chunk_async(chunk, prompt_template, field_instructions)
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
                print(f"=== DEBUG: About to update database with processed_chunks={completed_count} ===")
                update_emr_type(db, emr_type_id, processed_chunks=completed_count, total_chunks=len(chunks))
                print(f"=== DEBUG: Database update completed for processed_chunks={completed_count} ===")
                progress = int((completed_count / len(chunks)) * 100)
                print(f"=== DEBUG: Progress: {progress}% ({completed_count}/{len(chunks)} chunks) ===")
                
        except Exception as e:
            print(f"=== DEBUG: Error processing chunk: {str(e)} ===")
            processed_responses.append("")
            completed_count += 1
            
            #Update progress even for failed chunks
            if emr_type_id and db:
                update_emr_type(db, emr_type_id, processed_chunks=completed_count, total_chunks=len(chunks))
                progress = int((completed_count / len(chunks)) * 100)
                print(f"=== DEBUG: Progress after error: {progress}% ({completed_count}/{len(chunks)} chunks) ===")

    return processed_responses


def normalize_field_name(field_name):
    """Normalize field name for consistency"""
    # Remove leading dashes and spaces
    cleaned = field_name.lstrip('- ').strip()
    # Normalize multiple spaces to single space
    cleaned = ' '.join(cleaned.split())
    # Remove any remaining dashes and normalize
    cleaned = cleaned.replace('-', ' ').strip()
    # Convert camelCase to spaces (e.g., "DeliveredOff" -> "Delivered Off")
    import re
    cleaned = re.sub(r'([a-z])([A-Z])', r'\1 \2', cleaned)
    # Normalize multiple spaces again
    cleaned = ' '.join(cleaned.split())
    # Convert to lowercase for case-insensitive comparison
    cleaned = cleaned.lower()
    return cleaned


def save_results_to_db_with_label(results: dict, emr_type_id: str, db: Session, label: str):
    """Save results to database with label"""
    for key, value in results.items():
        # Set status based on value
        if value and 'not found' in value.lower():
            status = 'not found'
        else:
            status = 'found'

        clean_key = normalize_field_name(key)

        # Check if result already exists to preserve instructions
        existing_result = db.query(EMRTypeResult).filter(
            EMRTypeResult.emr_type_id == emr_type_id,
            EMRTypeResult.key == clean_key,
            EMRTypeResult.value == value
        ).first()

        if existing_result:
          # Update only the value if status is not "confirmed"
            if existing_result.status != "confirmed":
               existing_result.value = value
            # Only update status if it's not "ignore"
            if existing_result.status != "ignore" and existing_result.status != "confirmed":
                existing_result.status = status
            # Update label
            if existing_result.status != "confirmed":
               existing_result.label = label
            db.commit()
            print(f"=== DEBUG: Updated {clean_key}: {value} (status: {existing_result.status}) (label: {label}) (preserved instructions) ===")
        else:
            # Create new result with empty instructions and status
            create_emr_type_result(
                db=db,
                emr_type_id=emr_type_id,
                key=clean_key,
                value=value,
                status=status,
                label=label
            )
            print(f"=== DEBUG: Created {clean_key}: {value} (status: {status}) (label: {label}) ===")


#Genarate Response button from fe is calling that API
@router.post("/analyze-emr-file/")
def analyze_emr_file_for_ai(
    req: GenerateRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    emr_type_id = req.emr_type_id
    emr = get_emr_type(db, emr_type_id)
    if not emr:
        raise HTTPException(status_code=404, detail="EMR type not found")

    # Check if EMR type has been analyzed before allowing generate response
    if emr.status == 'draft':
        raise HTTPException(status_code=400, detail="EMR type must be analyzed first before generating response. Please run the Analyze button first.")

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

# The save button on top from the instructions box in EMR Type Details was calling this but for now we took down that save button with instructions box from the fe
@router.post("/save-response/")
def save_response(
    req: SaveResponseRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Save a response to the EMR type"""
    emr_type_id = req.emr_type_id
    emr = get_emr_type(db, emr_type_id)
    if not emr:
        raise HTTPException(status_code=404, detail="EMR type not found")

    # Update the EMR type with the response
    updated_emr = update_emr_type(db, emr_type_id, response=req.response)

    return {"message": "Response saved successfully", "emr_type_id": emr_type_id}


#Analyze button from the fe is calling this API
@router.post("/analyze-emr-type/{emr_type_id}")
async def analyze_emr_type(
    emr_type_id: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    # Check current status first
    emr_type = get_emr_type(db, emr_type_id)
    if not emr_type:
        raise HTTPException(status_code=404, detail="EMR type not found")
    
    # Simple logic: Check if analysis is in progress by comparing chunks
    # If total_chunks != processed_chunks, someone is analyzing
    total_chunks = emr_type.total_chunks or 0
    processed_chunks = emr_type.processed_chunks or 0
    
    if total_chunks != processed_chunks:
        # Analysis is in progress - block anyone from starting new analysis
      
            progress = int((processed_chunks or 0) / total_chunks * 100)
            raise HTTPException(
                status_code=409, 
                detail=f"EMR analysis is already in progress ({progress}% complete). Please wait for it to complete."
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
        print(f"=== DEBUG: Loading file from S3: {s3_key} ===")
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
        #         print(f"=== DEBUG: Found iframe with srcdoc content ===")
        #         raw_html += "\n<!-- IFRAME CONTENT -->\n" + srcdoc
        #     else:
        #         # Check src attribute
        #         src = iframe.get('src')
        #         if src:
        #             print(f"=== DEBUG: Found iframe with src: {src} ===")
        #         # Check inner content
        #         iframe_content = iframe.get_text(strip=True)
        #         if iframe_content:
        #             print(f"=== DEBUG: Found iframe with inner content ===")
        #             raw_html += "\n<!-- IFRAME CONTENT -->\n" + iframe_content

        # Get all custom instructions from emr_type_results table
        results = get_emr_type_results_by_emr_type(db, emr_type_id)
        results = [result for result in results if result.status != "confirmed"]
        custom_instructions = []

        # 1. First append: Fields without instructions from results table
        fields_without_instructions = [result.key for result in results if result.status != "confirmed" and not (result.instructions and result.instructions.strip())]
        if fields_without_instructions:
            print(f"=== DEBUG: Found {len(fields_without_instructions)} fields without instructions: {fields_without_instructions} ===")
            field_instructions = "\n".join([f"- {field_name}" for field_name in fields_without_instructions])
            custom_instructions.append(f"Fields to extract:\n{field_instructions}")

        # 2. Second append: Custom instructions from results table
        for result in results:
            if result.instructions and result.instructions.strip():
                custom_instructions.append(f"{result.key}: {result.instructions}")

        # 3. Third append: Fields that don't exist in results table at all
        all_fields = get_all_emr_type_fields(db)
        existing_field_names = [result.key for result in results]

        # Normalize field names for comparison (remove spaces, dashes, convert to lowercase)
        def normalize_for_comparison(name):
            return name.lower().replace(' ', '').replace('-', '').replace('_', '')

        missing_fields = [field.name for field in all_fields
                         if normalize_for_comparison(field.name) not in
                         [normalize_for_comparison(name) for name in existing_field_names]]

        if missing_fields:
            print(f"=== DEBUG: Found {len(missing_fields)} missing fields: {missing_fields} ===")
            field_instructions = "\n".join([f"- {field_name}" for field_name in missing_fields])
            custom_instructions.append(f"Additional fields to extract:\n{field_instructions}")

        # Combine all instructions into one big instruction
        combined_instructions = "\n".join(custom_instructions)
        print(f"=== DEBUG: Combined instructions: {combined_instructions} ===")

        # Create prompt template
        prompt_template = """Below is the HTML content of a psychotherapy EMR form. Please analyze the form and extract the following fields: {field_instructions}

Please extract ONLY the fields specified in the instructions above and provide the value found in the HTML and the actule label from where you take the value. If a field is not found or empty indicate "Not found" or "Empty".

IMPORTANT: Respond with ONLY the field names and values and label in this exact format:
FieldName: Value (label: ActualLabelFromHTML)
FieldName: Value (label: ActualLabelFromHTML)

IMPORTANT: Always use the exact field names provided in the instructions as the keys in your response, even if the value is found under a similar or synonymous label in the HTML.

IMPORTANT: For each field you extract, also include the actual label from the HTML that you used to find the value. For example, if you asked for "Client" but found "Client Name" in the HTML, include "Client Name" as the label. If you asked for "Appt Date" but found "Appointment Date" in the HTML, include "Appointment Date" as the label.

CRITICAL: Do NOT include any descriptive text, headers, explanations, or summary lines. Do NOT add lines like "The Requested Fields And Their Respective Values Extracted From The Html Content Are As Follows", "Here Are The Extracted Fields And Their Values From The Provided Html Content", "Certainly, Here Is The Extracted Information From The Html Content With The Specified Fields", "Here Is The Extracted Information From The Psychotherapy Emr Form", or ANY similar descriptive text. ONLY return the actual field names and their values and the label in the exact format: FieldName: Value (label: ActualLabelFromHTML)

HTML CONTENT: {html_content_for_gpt}"""

        # Create chunks from the full HTML content
        chunks = create_chunks(raw_html)

        # Set initial processing status with total chunks
        print(f"=== DEBUG: About to update status to 'processing' for emr_type_id={emr_type_id} ===")
        update_emr_type(db, emr_type_id, status="processing", total_chunks=len(chunks), processed_chunks=0)
        print(f"=== DEBUG: Status update to 'processing' completed ===")
        print(f"=== DEBUG: Started processing {len(chunks)} chunks ===")

        if len(chunks) == 1:
            # Single chunk - process normally
            print("=== DEBUG: Processing single chunk ===")
            prompt = prompt_template.format(
                field_instructions=combined_instructions,
                html_content_for_gpt=chunks[0]
            )

            try:
                response = openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that analyzes EMR forms. Extract information accurately from the provided HTML content and list each field with its value and label."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4000
                )
                result = response.choices[0].message.content
                print(f"=== DEBUG: AI Response: {result} ===")

                # Return single chunk response
                return {
                    "message": "Analysis completed successfully",
                    "chunks_available": 1,
                    "all_chunks": [result]
                }

            except Exception as e:
                print(f"=== DEBUG: Error processing single chunk: {str(e)} ===")
                raise HTTPException(status_code=500, detail=f"Error processing EMR content: {str(e)}")
        
        else:
            # Multiple chunks - process asynchronously with progress tracking
            print(f"=== DEBUG: Processing {len(chunks)} chunks asynchronously ===")
            chunk_responses = await process_chunks_async(chunks, prompt_template, combined_instructions, emr_type_id, db)
            
            # Format chunks for frontend
            formatted_chunks = []
            for i, response in enumerate(chunk_responses):
                formatted_chunks.append({
                    "chunk_index": i,
                    "response": response,
                    "chunk_size": len(chunks[i]) if i < len(chunks) else 0
                })
            
            # Keep status as "processing" - wait for user confirmation
            print(f"=== DEBUG: Analysis completed successfully ===")
            
            return {
                "message": "Analysis completed successfully",
                "chunks_available": len(formatted_chunks),
                "all_chunks": formatted_chunks
            }

    except Exception as e:
        print(f"=== DEBUG: Error in analyze_emr_type: {str(e)} ===")
        raise HTTPException(status_code=500, detail=f"Error analyzing EMR: {str(e)}")

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

@router.post("/save-selected-chunk/")
async def save_selected_chunk(
    req: SaveSelectedChunkRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Save the selected chunk data to database"""
    emr_type_id = req.emr_type_id
    selected_chunks = req.selected_chunks

    print(f"=== DEBUG: Saving {len(selected_chunks)} selected chunks for EMR type {emr_type_id} ===")

    # Track unique values for each field
    field_values = {}

    # Process each chunk response
    for chunk_data in selected_chunks:
        selected_chunk_response = chunk_data.selected_chunk_response
        chunk_index = chunk_data.selected_chunk_index
        selected_chunk_label = chunk_data.selected_chunk_label or ''

        print(f"=== DEBUG: Processing chunk {chunk_index} with label: {selected_chunk_label} ===")

        # Parse the selected chunk response
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

                            # Only use label if it has content AND value is not "Not found"
                            if label_content and clean_value.lower() != "not found":
                                extracted_label = label_content
                            else:
                                # Empty label or "Not found" value, keep label empty
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

        print(f"=== DEBUG: Parsed results from chunk {chunk_index}: {dict(field_values)} ===")

    # Convert sets to lists and save each unique value as separate row
    for field, field_data in field_values.items():
        values_list = list(field_data['values'])  # Convert set to list (sets already handle duplicates)
        label = field_data['label']

        # Check if this field has instructions in the database
        existing_results = db.query(EMRTypeResult).filter(
            EMRTypeResult.emr_type_id == emr_type_id,
            EMRTypeResult.key == field
        ).all()

        # Find instruction row (has instructions)
        instruction_row = None
        for result in existing_results:
            if result.instructions and result.instructions.strip():
                instruction_row = result
                break

        # If instruction row exists, update it with the best value
        if instruction_row and values_list:
            # Find the best value (first non-"Not found")
            best_value = None
            best_label = ""
            for value in values_list:
                if value.lower() != "not found":
                    best_value = value
                    best_label = label
                    break

            # If we found a good value, update the instruction row
            if best_value:
                instruction_row.value = best_value
                instruction_row.label = best_label
                db.commit()
                print(f"=== DEBUG: Updated instruction row for {field}: {best_value} (label: {best_label}) ===")
                # Skip creating new rows for this key since we updated the instruction row
                continue  # Skip to next field, don't process other values for this key

        # Save each unique value as separate row in DB (duplicates handled automatically)
        for value in values_list:
            # Save this field-value-label pair to DB
            save_results_to_db_with_label({field: value}, emr_type_id, db, label)

    print(f"=== DEBUG: Saved {len(field_values)} fields with multiple values ===")

    # Generate JSON instructions from the results
    results = get_emr_type_results_by_emr_type(db, emr_type_id)
    # Filter out results with status "ignore"
    results = [result for result in results if result.status != "ignore"]

    json_instructions = generate_json_instructions_from_results(results)

    # Save the generated JSON instructions to the EMR type
    update_emr_type(db, emr_type_id, instructions=json_instructions)
    print(f"=== DEBUG: Saved generated JSON instructions to EMR type ===")

    # Update status to 'analyzed' after successful analysis
    update_emr_type(db, emr_type_id, status='analyzed')
    print(f"=== DEBUG: Updated EMR type status to 'analyzed' ===")

    return {
        "message": f"Selected chunks saved successfully",
        "chunks_processed": len(selected_chunks)
    }


@router.get("/analyze-progress/{emr_type_id}")
async def get_analyze_progress(
    emr_type_id: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
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
        
        print(f"=== DEBUG: Progress endpoint - total_chunks={total_chunks}, processed_chunks={processed_chunks} ===")
        
        # Calculate progress based on actual chunks processed
        if total_chunks > 0:
            progress = int((processed_chunks / total_chunks) * 100)
        else:
            progress = 0
        
        print(f"=== DEBUG: Progress endpoint - calculated progress={progress}% ===")
        
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
        print(f"=== DEBUG: Error getting progress: {str(e)} ===")
        raise HTTPException(status_code=500, detail=f"Error getting progress: {str(e)}")

@router.delete("/delete-result/")
async def delete_result(
    req: DeleteResultRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_with_role(["super_admin"]))
):
    """Delete a specific result row from the database"""
    emr_type_id = req.emr_type_id
    key = req.key
    value = req.value

    print(f"=== DEBUG: Deleting result for EMR type {emr_type_id}, key: {key}, value: {value} ===")

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
            print(f"=== DEBUG: Successfully deleted result for key: {key}, value: {value} ===")
            return {
                "message": f"Result for key '{key}' with value '{value}' deleted successfully",
                "deleted_key": key,
                "deleted_value": value
            }
        else:
            raise HTTPException(status_code=404, detail=f"Result for key '{key}' with value '{value}' not found")

    except Exception as e:
        db.rollback()
        print(f"=== DEBUG: Error deleting result: {str(e)} ===")
        raise HTTPException(status_code=500, detail=f"Error deleting result: {str(e)}")