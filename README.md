# WhatsApp Voice Message Transcription Bot

This bot automatically transcribes voice messages sent to your WhatsApp business number using OpenAI's Whisper model. It supports multiple languages and works in real-time.

## Features

- 🎤 Transcribes voice messages automatically
- 🌍 Supports multiple languages (powered by Whisper)
- ⚡ Real-time processing
- 📱 Simple to use - just forward a voice message

## Prerequisites

1. Python 3.8 or higher
2. WhatsApp Business API access
3. OpenAI API key
4. A publicly accessible URL for webhook (e.g., using ngrok)

## Setup Instructions

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

4. Configure your environment variables in `.env`:
   - `WHATSAPP_TOKEN`: Your WhatsApp Cloud API token
   - `VERIFY_TOKEN`: A custom verification token for webhook setup
   - `PHONE_NUMBER_ID`: Your WhatsApp Business Phone Number ID
   - `OPENAI_API_KEY`: Your OpenAI API key

5. Start the server:
   ```bash
   python app.py
   ```

6. Use ngrok or similar to expose your local server:
   ```bash
   ngrok http 8000
   ```

7. Configure the WhatsApp Cloud API webhook:
   - URL: `https://your-domain/webhook`
   - Verify token: Use the same token as in your `.env` file
   - Subscribe to messages

## Usage

1. Add your WhatsApp Business number as a contact
2. Send or forward a voice message to the number
3. Wait for the transcription to be sent back

## Error Handling

The bot includes comprehensive error handling for:
- Invalid message types
- Failed downloads
- Transcription errors
- API communication issues

## Security Notes

- Keep your `.env` file secure and never commit it to version control
- Regularly rotate your API keys and tokens
- Use HTTPS for all webhook endpoints 