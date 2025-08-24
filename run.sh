#!/usr/bin/env zsh

# FOMC Analysis Application Launcher Script
# Enhanced with better error handling, logging, and environment management

set -e  # Exit on any error

# --- Configuration ---
APP_NAME="FOMC Analysis"
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/run_$(date +%Y%m%d_%H%M%S).log"
PYTHON_EXEC="python"
FLASK_ENV="development"
HOST="127.0.0.1"
PORT="5000"

# --- Colors for output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --- Script Setup ---
mkdir -p "$LOG_DIR"

# --- Logging functions ---
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}
log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"
}
log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2 | tee -a "$LOG_FILE"
}

# --- Helper Functions ---

# Function to load environment variables from .env file
load_env() {
    if [ -f .env ]; then
        log_info "Loading environment variables from .env file..."
        export $(grep -v '^#' .env | xargs)
    fi
}

# Function to check and activate the conda environment
check_conda_env() {
    log_info "Checking conda environment..."
    if ! command -v conda &> /dev/null; then
        log_error "Conda is not installed or not in PATH."
        return 1
    fi
    
    if [[ "$CONDA_DEFAULT_ENV" != "fomc" ]]; then
        log_info "Activating 'fomc' conda environment..."
        # Correctly initialize conda for zsh
        eval "$(conda shell.zsh hook)"
        if ! conda activate fomc; then
            log_error "Failed to activate 'fomc' environment. Please create it first."
            return 1
        fi
    fi
    log_info "Conda environment '$CONDA_DEFAULT_ENV' is active."
}

# Function to check and install dependencies
check_dependencies() {
    log_info "Checking Python dependencies..."
    if [ -f "requirements.txt" ]; then
        if ! pip freeze | grep -q -f <(sed 's/==.*//' requirements.txt); then
             log_info "Installing/updating dependencies from requirements.txt..."
             pip install -r requirements.txt
        else
             log_info "Dependencies are up to date."
        fi
    else
        log_warn "requirements.txt not found. Skipping dependency check."
    fi
}

# Function to pre-build the FAISS index for the RAG chatbot
build_rag_index() {
    if [[ "$SKIP_RAG_INDEX" == "true" ]]; then
        log_info "Skipping RAG index build."
        return 0
    fi
    log_info "Checking and building RAG FAISS index..."
    $PYTHON_EXEC utils/rag_index.py ${REBUILD_RAG_INDEX:+--rebuild} || log_warn "RAG index build finished with warnings."
}

# Function to start the Flask application
start_flask_app() {
    log_info "Starting $APP_NAME..."
    log_info "Server will be available at: http://$HOST:$PORT"
    
    export FLASK_APP=app.py
    export FLASK_ENV=$FLASK_ENV
    
    flask run --host="$HOST" --port="$PORT"
}

# --- Argument Parsing ---
REBUILD_RAG_INDEX=""
SKIP_RAG_INDEX=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --rebuild-index)
            REBUILD_RAG_INDEX="true"
            shift
            ;;
        --skip-index)
            SKIP_RAG_INDEX="true"
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --rebuild-index    Force rebuild of the RAG FAISS index."
            echo "  --skip-index       Skip the RAG FAISS index build."
            echo "  --port PORT        Set port (default: 5000)."
            echo "  --host HOST        Set host (default: 127.0.0.1)."
            echo "  --help             Show this help message."
            exit 0
            ;;
        *)
            log_warn "Unknown option: $1"
            shift
            ;;
    esac
done

# --- Main Execution ---
main() {
    echo "============================================"
    echo "        $APP_NAME Launcher"
    echo "============================================"
    log_info "Log file: $LOG_FILE"
    
    load_env
    check_conda_env
    check_dependencies
    build_rag_index
    
    log_info "All preparation steps completed. Starting application..."
    start_flask_app
}

# --- Run main function ---
main