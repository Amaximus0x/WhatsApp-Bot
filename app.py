import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import requests
from dotenv import load_dotenv
import openai
import tempfile
import aiohttp
import json
import subprocess
import logging
import asyncio

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

# Load environment variables
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")
openai.api_key = OPENAI_API_KEY

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Verify webhook for WhatsApp API"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return int(challenge)
        raise HTTPException(status_code=403, detail="Invalid verify token")
    raise HTTPException(status_code=400, detail="Invalid request")

async def download_audio(url: str) -> str:
    """Download audio file from WhatsApp servers"""
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                raise HTTPException(status_code=400, detail="Failed to download audio")
            
            # Create a temporary file to store the audio
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
                temp_file.write(await response.read())
                return temp_file.name

async def convert_audio(input_file: str) -> str:
    """Convert audio to format suitable for OpenAI Whisper"""
    output_file = input_file.replace(".ogg", ".mp3")
    try:
        subprocess.run(
            ["ffmpeg", "-i", input_file, "-acodec", "libmp3lame", output_file],
            check=True,
            capture_output=True
        )
        return output_file
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Audio conversion failed: {str(e)}")
    finally:
        if os.path.exists(input_file):
            os.remove(input_file)

async def transcribe_audio(file_path: str) -> str:
    """Transcribe audio using OpenAI Whisper"""
    try:
        with open(file_path, "rb") as audio_file:
            transcript = openai.Audio.transcribe(
                "whisper-1",
                audio_file
            )
        return transcript.text
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    finally:
        # Clean up the temporary file
        if os.path.exists(file_path):
            os.remove(file_path)

async def send_whatsapp_message(to: str, message: str):
    """Send message back to WhatsApp"""
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Simplified payload for development mode
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": { "body": message }
    }
    
    logger.debug(f"Sending message to WhatsApp API. URL: {url}")
    logger.debug(f"Headers: {headers}")
    logger.debug(f"Data: {data}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                response_json = await response.json()
                logger.debug(f"Raw API Response: {response_json}")
                
                if response.status != 200:
                    error_msg = response_json.get('error', {})
                    error_code = error_msg.get('code')
                    error_details = error_msg.get('error_data', {}).get('details', '')
                    
                    if error_code == 10:
                        logger.error(f"Permission error. Token might be invalid or missing permissions. Details: {error_details}")
                        raise HTTPException(
                            status_code=400,
                            detail="WhatsApp API permission error. Please verify your token has 'whatsapp_business_messaging' permission."
                        )
                    
                    logger.error(f"Failed to send WhatsApp message. Status: {response.status}, Response: {response_json}")
                    raise HTTPException(status_code=500, detail=f"Failed to send WhatsApp message: {response_json}")
                
                logger.debug(f"Successfully sent message to WhatsApp")
                return response_json
    except aiohttp.ClientError as e:
        logger.error(f"Network error when sending WhatsApp message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")
    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error sending WhatsApp message: {str(e)}")

async def process_transcript(transcript: str) -> str:
    """Process the transcript using OpenAI Assistant"""
    try:
        # Create a thread
        thread = await openai.beta.threads.create()

        # Add the transcript message to the thread
        await openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=transcript
        )

        # Replace this with your Assistant ID from the OpenAI playground
        ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")
        
        # Run the assistant
        run = await openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )

        # Wait for the completion
        while True:
            run_status = await openai.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            if run_status.status == 'completed':
                break
            await asyncio.sleep(1)  # Wait for 1 second before checking again

        # Get the assistant's response
        messages = await openai.beta.threads.messages.list(
            thread_id=thread.id
        )
        
        # Get the latest assistant response
        assistant_response = messages.data[0].content[0].text.value
        return assistant_response

    except Exception as e:
        logger.error(f"Transcript processing error: {str(e)}", exc_info=True)
        # If processing fails, return original transcript
        return transcript

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Handle incoming WhatsApp messages"""
    try:
        body = await request.json()
        logger.debug(f"Received webhook body: {json.dumps(body, indent=2)}")
        
        # Extract the message data
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            logger.debug("No messages found in webhook")
            return JSONResponse(content={"status": "No messages to process"})

        message = messages[0]
        logger.debug(f"Processing message: {json.dumps(message, indent=2)}")

        if message.get("type") != "audio":
            logger.debug(f"Not an audio message. Type: {message.get('type')}")
            return JSONResponse(content={"status": "Not an audio message"})

        # Get sender's phone number
        from_number = message.get("from")
        logger.debug(f"Message from: {from_number}")
        
        # Get voice message URL
        audio_message = message.get("audio", {})
        media_id = audio_message.get("id")
        logger.debug(f"Audio message ID: {media_id}")
        
        # Get media URL
        media_url = f"https://graph.facebook.com/v21.0/{media_id}"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        logger.debug(f"Fetching media URL from: {media_url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(media_url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Failed to get media URL. Status: {response.status}")
                    raise HTTPException(status_code=400, detail="Failed to get media URL")
                media_data = await response.json()
                audio_url = media_data.get("url")
                logger.debug(f"Got audio URL: {audio_url}")

        # Download and process the audio
        logger.debug("Downloading audio file...")
        audio_file = await download_audio(audio_url)
        logger.debug(f"Audio downloaded to: {audio_file}")
        
        logger.debug("Converting audio...")
        converted_file = await convert_audio(audio_file)
        logger.debug(f"Audio converted to: {converted_file}")
        
        logger.debug("Transcribing audio...")
        transcript = await transcribe_audio(converted_file)
        logger.debug(f"Transcription result: {transcript}")
        
        # Process the transcript
        logger.debug("Processing transcript with GPT...")
        processed_transcript = await process_transcript(transcript)
        logger.debug(f"Processed transcript: {processed_transcript}")
        
        # Send processed transcription back to user
        response_message = f"Transcription: {processed_transcript}"
        logger.debug(f"Sending response: {response_message}")
        await send_whatsapp_message(from_number, response_message)
        
        return JSONResponse(content={"status": "success"})
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.get("/")
async def root():
    return {"status": "WhatsApp Voice Transcription Bot is running"}

if __name__ == "__main__":
    import uvicorn
    try:
        port = int(os.getenv("PORT", "3000"))
        uvicorn.run(
            "app:app",
            host="0.0.0.0",
            port=port,
            reload=True
        )
    except Exception as e:
        print(f"Failed to start server: {e}") 