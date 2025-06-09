# AI YouTube Video Generator - Portfolio Project

## 🚀 Looking to Hire a Skilled AI/ML Developer?

**Contact me: tuvshin.org@gmail.com**

This project demonstrates my expertise in:
- **Full-Stack AI Development** - Complete automation pipeline from data ingestion to deployment
- **Machine Learning Integration** - Ollama/LLaMA, Stable Diffusion, Whisper, Edge TTS
- **Video/Audio Processing** - FFmpeg, complex media manipulation, professional post-production
- **API Integration** - YouTube Data API, OAuth2, Google Cloud Services
- **Database Design** - SQLite with optimized performance and concurrency
- **System Architecture** - Scalable, modular pipeline design
- **DevOps & Automation** - Production-ready deployment and monitoring

---

## Project Overview

This sophisticated AI-powered system completely automates YouTube video creation from RSS feeds to published content. It showcases advanced integration of multiple AI models, media processing technologies, and cloud services in a production-ready pipeline.

**Key Achievement**: Built a fully autonomous content creation system that can generate, produce, and publish professional YouTube videos without human intervention.

## Features

- **Automated Content Generation**: Fetches RSS feeds from news sources (Snopes, Daily Mail)
- **AI Script Writing**: Uses Ollama/Llama3.2 to generate 6-scene video scripts
- **Visual Content Creation**: Generates images using Stable Diffusion WebUI Forge
- **Voice Synthesis**: Creates natural-sounding narration with Microsoft Edge TTS
- **Video Production**: Combines images, audio, and effects into complete videos
- **Subtitle Generation**: Word-level subtitle highlighting using Whisper
- **Background Music**: Automatically selects appropriate music from categorized library
- **Video Transitions**: Smooth transitions between scenes with various effects
- **Audio Mixing**: Professional audio processing with echo and EQ
- **YouTube Upload**: Automated publishing to YouTube with metadata

## System Requirements

- **Operating System**: Linux (Ubuntu/Debian recommended)
- **Python**: 3.8+
- **GPU**: NVIDIA GPU recommended for Stable Diffusion
- **Storage**: Adequate space for temp files and final videos
- **Network**: Stable internet connection for RSS feeds and API calls

## Dependencies

### Core Dependencies
- `sqlite3` - Database management
- `feedparser` - RSS feed processing
- `requests` - HTTP requests
- `beautifulsoup4` - HTML parsing
- `pydantic` - Data validation
- `ollama` - Local LLM integration

### AI/ML Dependencies
- `openai-whisper` - Speech transcription
- `edge-tts` - Text-to-speech synthesis
- Stable Diffusion WebUI Forge (external)

### Media Processing
- `ffmpeg` - Video/audio processing
- `ffmpeg-normalize` - Audio normalization

### YouTube Integration
- `google-api-python-client` - YouTube API
- `oauth2client` - Google OAuth
- `httplib2` - HTTP client

## Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd ai-youtube-generator
```

2. **Install Python dependencies**
```bash
pip install -r requirements.txt
```

3. **Install system dependencies**
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install ffmpeg sqlite3

# Install ffmpeg-normalize
pip install ffmpeg-normalize
```

4. **Setup Stable Diffusion WebUI Forge**
- Follow installation instructions for Stable Diffusion WebUI Forge
- Ensure API mode is available
- Configure model checkpoints

5. **Setup Ollama**
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull required model
ollama pull llama3.2:latest
```

6. **Setup YouTube API**
- Create Google Cloud Project
- Enable YouTube Data API v3
- Download client_secret.json
- Place in project root directory

## Configuration

### Database Setup
Run the database initialization script:
```bash
python create.py
```

This creates the SQLite database with required tables:
- `RSS` - RSS feed entries
- `SEED` - Video project metadata
- `SCENE` - Individual scene data
- `TASK` - Processing task tracking

### Directory Structure
The system uses the following directory structure:
```
/root/yikes/
├── main.db                 # SQLite database
├── client_secret.json      # YouTube API credentials
├── credentials.storage     # OAuth tokens
├── logs/                   # Application logs
├── song/                   # Background music library
│   ├── bright/
│   ├── calm/
│   ├── dark/
│   ├── dramatic/
│   ├── funky/
│   ├── happy/
│   ├── inspirational/
│   └── sad/
├── optic/                  # Optical flare effects (1.mp4-9.mp4)
├── temp/                   # Temporary processing files
│   ├── audio/
│   ├── clip/
│   ├── image/
│   ├── mix/
│   ├── subtitle/
│   ├── temp/
│   ├── video/
│   └── voice/
└── final/                  # Final video output
```

## Usage

The system runs as a pipeline with numbered scripts that should be executed in sequence:

### 1. Content Fetching (`01.feed.py`)
```bash
python 01.feed.py
```
- Fetches RSS feeds from configured news sources
- Extracts article content
- Stores in database
- Generates video titles, descriptions, and music selection using AI

### 2. Image Generation (`02.image.py`)
```bash
python 02.image.py
```
- Processes pending scenes
- Generates images using Stable Diffusion
- Saves images to temp directory

### 3. Voice Synthesis (`03.voice.py`)
```bash
python 03.voice.py
```
- Converts scene text to speech
- Uses Microsoft Edge TTS with female voice (en-US-AvaNeural)
- Creates audio files for each scene

### 4. Video Clip Creation (`04.clip.py`)
```bash
python 04.clip.py
```
- Combines images and audio into video clips
- Adds optical flare effects
- Applies proper timing and delays

### 5. Subtitle Generation (`05.subtitle.py`)
```bash
python 05.subtitle.py
```
- Transcribes audio using Whisper
- Creates word-level subtitle highlighting
- Burns subtitles into video

### 6. Transition Effects (`06.transition.py`)
```bash
python 06.transition.py
```
- Combines all scene videos
- Adds smooth transitions between scenes
- Creates cohesive full-length video

### 7. Audio Mixing (`07.mix.py`)
```bash
python 07.mix.py
```
- Extracts audio from video
- Adds background music
- Applies audio effects (echo, EQ)
- Normalizes audio levels

### 8. Final Assembly (`08.final.py`)
```bash
python 08.final.py
```
- Merges processed video with mixed audio
- Creates final output video
- Syncs audio/video timing

### 9. YouTube Upload (`09.upload.py`)
```bash
python 09.upload.py
```
- Uploads video to YouTube
- Sets title, description, and metadata
- Handles authentication and API rate limits

### 10. Cleanup (`10.clean.py`)
```bash
python 10.clean.py
```
- Removes temporary files for completed uploads
- Frees up disk space
- Maintains system performance

## Automation

For automated operation, create a cron job or systemd service to run the pipeline:

```bash
# Example cron job (runs every hour)
0 * * * * cd /path/to/project && python 01.feed.py && python 02.image.py && python 03.voice.py && python 04.clip.py && python 05.subtitle.py && python 06.transition.py && python 07.mix.py && python 08.final.py && python 09.upload.py && python 10.clean.py
```

## Configuration Options

### RSS Sources
Edit `01.feed.py` to modify RSS feed sources:
```python
feeds_to_try = [
    {
        "url": "https://www.dailymail.co.uk/articles.rss",
        "name": "dailymailv2",
        "content_selector": "#content > div.articleWide.cleared > div.alpha"
    }
]
```

### AI Models
Configure AI models in respective scripts:
- Stable Diffusion: Modify model checkpoint in `02.image.py`
- Ollama: Change model in `01.feed.py` (default: llama3.2:latest)
- Whisper: Adjust model size in `05.subtitle.py` (default: medium)

### Video Settings
Customize video parameters in `04.clip.py`:
- Resolution: 540x960 (vertical format)
- Frame rate: 30 FPS
- Video codec: H.264
- Audio codec: AAC

## Troubleshooting

### Common Issues

1. **Ollama Service Not Running**
   - Scripts automatically start/stop Ollama service
   - Check logs if issues persist

2. **Stable Diffusion API Errors**
   - Ensure WebUI Forge is running with `--api` flag
   - Check GPU memory availability

3. **YouTube Upload Failures**
   - Verify API credentials and quotas
   - Check OAuth token validity

4. **Database Lock Errors**
   - Scripts use WAL mode for better concurrency
   - Ensure proper connection closing

### Log Files
Monitor logs in `/root/yikes/logs/`:
- `feed.log` - Content fetching and AI generation
- `image.log` - Image generation
- `voice.log` - Voice synthesis
- `video.log` - Video processing
- `subtitle.log` - Subtitle generation
- `transition.log` - Video transitions
- `mix.log` - Audio mixing
- `final.log` - Final assembly
- `upload.log` - YouTube upload

---

## 💼 About the Developer

**Available for hire** - Experienced AI/ML Engineer with proven expertise in:

### Technical Skills Demonstrated:
- **AI/ML**: PyTorch, TensorFlow, Transformers, Computer Vision, NLP
- **Languages**: Python, JavaScript, SQL, Bash
- **Cloud Platforms**: Google Cloud, AWS, API integrations
- **Media Processing**: FFmpeg, OpenCV, Audio/Video manipulation
- **Databases**: SQLite, PostgreSQL, MongoDB
- **DevOps**: Docker, Linux administration, Automation

### Project Highlights:
- **End-to-End AI Pipeline**: Designed and implemented complete automation workflow
- **Multi-Modal AI Integration**: Successfully combined text, image, and audio AI models
- **Production System**: Built robust, scalable system with error handling and logging
- **API Mastery**: Complex integrations with multiple external services
- **Performance Optimization**: Efficient resource management and concurrent processing

### What I Can Bring to Your Team:
✅ **Rapid Prototyping** - Quick proof-of-concepts to validate ideas  
✅ **Production-Ready Code** - Scalable, maintainable, well-documented systems  
✅ **AI Integration Expertise** - Seamless incorporation of cutting-edge AI models  
✅ **Problem-Solving Skills** - Creative solutions to complex technical challenges  
✅ **Full-Stack Capability** - From backend APIs to frontend interfaces  

**Ready to discuss your next AI project: tuvshin.org@gmail.com**

---

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This portfolio project demonstrates technical capabilities. Ensure you have proper rights to use any content sources and comply with relevant terms of service and guidelines.# AI-YouTube-Video-Generator
