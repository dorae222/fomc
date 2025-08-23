#!/usr/bin/env zsh

# FOMC Analysis Application Launcher Script
# Enhanced with better error handling, logging, and environment management

set -e  # Exit on any error

# Configuration
APP_NAME="FOMC Analysis"
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/run_$(date +%Y%m%d_%H%M%S).log"
PYTHON_EXEC="python"
FLASK_ENV="development"
FLASK_DEBUG="true"
HOST="127.0.0.1"
PORT="5000"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create logs directory
mkdir -p "$LOG_DIR"

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: $1" >> "$LOG_FILE" 2>/dev/null || true
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN: $1" >> "$LOG_FILE" 2>/dev/null || true
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >> "$LOG_FILE" 2>/dev/null || true
}

# Function to check if conda environment exists and is active
check_conda_env() {
    log_info "Checking conda environment..."
    
    if ! command -v conda &> /dev/null; then
        log_error "Conda is not installed or not in PATH"
        return 1
    fi
    
    # Activate conda env only if not already active
    if [[ "$CONDA_DEFAULT_ENV" != "fomc" ]]; then
        log_info "Activating fomc conda environment..."
        eval "$(conda shell.zsh hook)" 2>/dev/null || true
        conda activate fomc 2>/dev/null || {
            log_error "Failed to activate fomc environment"
            log_error "Please create the environment: conda create -n fomc python=3.10"
            return 1
        }
    fi
    
    log_info "Using conda environment: $CONDA_DEFAULT_ENV"
    return 0
}

# Function to check Python and required packages
check_dependencies() {
    log_info "Checking Python installation and dependencies..."
    
    # Check Python version
    local python_version
    python_version=$($PYTHON_EXEC --version 2>&1 | cut -d' ' -f2)
    log_info "Python version: $python_version"
    
    # Check if key packages are importable
    local packages_to_check=("flask" "pandas" "sqlite3" "plotly")
    local missing_packages=()
    
    for package in "${packages_to_check[@]}"; do
        if ! $PYTHON_EXEC -c "import $package" 2>/dev/null; then
            missing_packages+=("$package")
        fi
    done
    
    if [[ ${#missing_packages[@]} -gt 0 ]]; then
        log_warn "Some packages may need installation: ${missing_packages[*]}"
        log_info "Installing from requirements.txt if available..."
        if [[ -f "requirements.txt" ]]; then
            pip install -r requirements.txt || log_warn "Failed to install from requirements.txt"
        fi
    fi
    
    log_info "Dependency check completed"
    return 0
}

# Function to setup database
setup_database() {
    log_info "Setting up database..."
    
    if [[ ! -f "fomc_analysis.db" ]] || [[ "$RESET_DB" == "true" ]]; then
        log_info "Initializing database..."
        if [[ "$RESET_DB" == "true" ]]; then
            $PYTHON_EXEC setup_db.py --reset --log-level INFO || {
                log_warn "Database reset failed, continuing..."
            }
        else
            $PYTHON_EXEC setup_db.py --log-level INFO || {
                log_warn "Database setup had issues, continuing..."
            }
        fi
    else
        log_info "Database exists, checking for migrations..."
        $PYTHON_EXEC -c "
from database.migrations import run_migrations
try:
    run_migrations()
    print('Migrations completed')
except Exception as e:
    print(f'Migration check failed: {e}')
" || log_warn "Migration check failed, continuing anyway"
    fi
    
    return 0
}

# Function to run data quality checks
run_quality_checks() {
    if [[ "$SKIP_QUALITY_CHECK" == "true" ]]; then
        log_info "Skipping data quality checks"
        return 0
    fi
    
    log_info "Running data quality checks..."
    $PYTHON_EXEC utils/data_quality.py --log-level WARNING 2>/dev/null || {
        log_warn "Data quality checks completed with warnings"
    }
    return 0
}

# Function to run precomputation
run_precompute() {
    if [[ "$SKIP_PRECOMPUTE" == "true" ]]; then
        log_info "Skipping precomputation"
        return 0
    fi
    
    log_info "Running precomputation tasks..."
    $PYTHON_EXEC utils/precompute.py --limit-pairs 6 --log-level WARNING 2>/dev/null || {
        log_warn "Precomputation completed with warnings"
    }
    return 0
}

# Function to start the Flask application
start_flask_app() {
    log_info "Starting $APP_NAME..."
    log_info "Server will be available at: http://$HOST:$PORT"
    
    # Export Flask configuration
    export FLASK_APP=app.py
    export FLASK_ENV=$FLASK_ENV
    export FLASK_DEBUG=$FLASK_DEBUG
    
    # Start the Flask application
    log_info "Launching Flask application..."
    flask run --host="$HOST" --port="$PORT" --debug || {
        log_error "Flask application failed to start"
        return 1
    }
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --reset-db)
            RESET_DB="true"
            shift
            ;;
        --skip-quality)
            SKIP_QUALITY_CHECK="true"
            shift
            ;;
        --skip-precompute)
            SKIP_PRECOMPUTE="true"
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
            echo "  --reset-db         Reset database"
            echo "  --skip-quality     Skip quality checks"
            echo "  --skip-precompute  Skip precomputation"
            echo "  --port PORT        Set port (default: 5000)"
            echo "  --host HOST        Set host (default: 127.0.0.1)"
            exit 0
            ;;
        *)
            log_warn "Unknown option: $1"
            shift
            ;;
    esac
done

# Main execution
main() {
    echo "============================================"
    echo "        $APP_NAME Launcher"
    echo "============================================"
    
    log_info "Starting $APP_NAME launcher..."
    log_info "Log file: $LOG_FILE"
    
    # Check conda environment
    if ! check_conda_env; then
        log_error "Environment check failed"
        exit 1
    fi
    
    # Check dependencies
    check_dependencies
    
    # Setup database (non-blocking)
    setup_database
    
    # Run quality checks (non-blocking)
    run_quality_checks
    
    # Run precomputation (non-blocking)
    run_precompute
    
    # Start Flask application
    log_info "All preparation steps completed, starting application..."
    start_flask_app
}

# Run main function
main
