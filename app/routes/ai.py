from fastapi import APIRouter, UploadFile, File, Form, Depends
import openai
import os
from sqlalchemy.orm import Session
from ..db import get_db
from ..crud import get_emr_type
import boto3
from pydantic import BaseModel
import urllib.parse
from dotenv import load_dotenv
load_dotenv()

router = APIRouter(prefix="/ai", tags=["AI"])

openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

S3_BUCKET = os.getenv("S3_BUCKET_NAME")
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)

class GenerateRequest(BaseModel):
    emr_type_id: str

@router.post("/analyze-html/")
async def analyze_html(
    instructions: str = Form(...),
    file: UploadFile = File(...)
):
    # Read HTML file content as text
    html_content = await file.read()
    html_text = html_content.decode('utf-8', errors='ignore')
    
    # Compose prompt for OpenAI
    prompt = f"{instructions}\n\nHTML file content:\n{html_text}"
    
    # Call OpenAI (new API)
    response = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant. The user will provide an HTML file and instructions. Follow the instructions using the file content."},
            {"role": "user", "content": prompt}
        ]
    )
    answer = response.choices[0].message.content
    return {"result": answer} 

@router.post("/generate-response/")
def generate_response_for_emr(
    req: GenerateRequest,
    db: Session = Depends(get_db)
):
    emr_type_id = req.emr_type_id
    emr = get_emr_type(db, emr_type_id)
    if not emr:
        return {"error": "EMR type not found"}
    if not emr.files or len(emr.files) == 0:
        return {"error": "No file found for this EMR type"}
    if not emr.instructions:
        return {"error": "No instructions found for this EMR type"}
    # Get the first file's S3 key
    file_url = emr.files[0].get('url')
    if not file_url:
        return {"error": "File URL missing in EMR type"}
    # Extract S3 key from URL (include region)
    region = os.getenv("AWS_REGION")
    prefix = f"https://{S3_BUCKET}.s3.{region}.amazonaws.com/"
    if not file_url.startswith(prefix):
        return {"error": "File URL is not a valid S3 URL"}
    s3_key = urllib.parse.unquote(file_url[len(prefix):])
    # Download file from S3
    s3_response = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
    file_content = s3_response['Body'].read()
    html_text = file_content.decode('utf-8', errors='ignore')
    # Compose prompt for OpenAI
    prompt = f"{emr.instructions}\n\nHTML file content:\n{html_text}"
    # Call OpenAI (new API)
    response = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant. The user will provide an HTML file and instructions. Follow the instructions using the file content."},
            {"role": "user", "content": prompt}
        ]
    )
    answer = response.choices[0].message.content
    return {"result": answer} 