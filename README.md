# LLM-RANK: AI Visibility Tracker

LLM-RANK is a full-stack application designed to track and analyze a domain's visibility across different Large Language Models (LLMs) such as Google's Gemini and Perplexity. It automates the generation of industry-specific questions, queries LLMs, and scores how well a target domain is represented or cited in the models' responses.

## Features

- **Automated Scanning**: Query multiple LLM providers (Gemini, Perplexity) in parallel.
- **AI Question Generation**: Automatically generate relevant industry questions for a domain in various languages.
- **Scoring & Visibility Tracking**: Calculate visibility scores based on whether the target domain is cited in the LLM's response or search grounding.
- **Content Gap Analysis**: Identify which questions your domain fails to rank for across different models.
- **FastAPI Backend**: Asynchronous Python backend powered by FastAPI and SQLAlchemy (SQLite).
- **React Frontend**: Modern, responsive dashboard built with React, Vite, Tailwind CSS, and Recharts.
- **CLI Interface**: Perform headless scans or start the API server directly from the command line.

## Architecture

- `backend/`: FastAPI application, SQLite database models, LLM API integration (Gemini, Perplexity), and prompt engineering for question generation.
- `frontend/`: React application providing a UI to manage domains, trigger scans, and visualize historical visibility trends.
- `run.py`: The main entry point for the CLI and starting the backend server.
- `setup.sh`: A bootstrap script to install system dependencies, configure the Python virtual environment, and install Node.js packages.

## Prerequisites

- **Python**: 3.11+
- **Node.js**: 20+
- **OS**: Linux / macOS (Ubuntu/Debian supported by the setup script)

## Installation

1. **Run the setup script** to install system dependencies, create a virtual environment, and install Python/Node packages:
   ```bash
   ./setup.sh
   ```
2. **Activate the virtual environment**:
   ```bash
   source venv/bin/activate
   ```
3. **Configure Environment Variables**:
   The setup script creates a `.env` file from `.env.example` (if it exists). Alternatively, create a `.env` file in the root directory with the following variables:
   ```env
   # API Keys for LLM integrations
   GOOGLE_API_KEY=your_google_api_key
   PERPLEXITY_API_KEY=your_perplexity_api_key
   ANTHROPIC_API_KEY=your_anthropic_api_key

   # Server Configuration (Optional)
   LLM_RANK_HOST=127.0.0.1
   LLM_RANK_PORT=8000

   # Models to scan (comma-separated, e.g. "gemini,perplexity")
   LLM_RANK_ENABLED_MODELS=gemini,perplexity
   ```

## Usage

### 1. Command Line Interface (CLI)

You can run domain scans directly from the terminal without starting the web UI.

```bash
# Basic scan (creates domain if it doesn't exist and generates initial questions)
python run.py --domain example.com --industry "E-commerce platform"

# Scan with a specific language for questions
python run.py --domain example.pl --industry "Sklep internetowy" --language "Polish"

# Force regeneration of questions before scanning
python run.py --domain example.com --industry "Tech blog" --generate-questions
```

### 2. Web Interface

To use the interactive dashboard, you need to run both the backend server and the frontend development server.

**Start the Backend API Server:**
```bash
python run.py --serve
```
The API will be available at `http://127.0.0.1:8000`.

**Start the Frontend Server:**
Open a new terminal window, navigate to the `frontend` directory, and start Vite:
```bash
cd frontend
npm run dev
```
The dashboard will be available at `http://localhost:5173`.

## License

Private/Proprietary.
