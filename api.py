"""
PLFS Dashboard API
==================

FastAPI application for serving PLFS labor market data.

Usage:
    uvicorn api:app --reload
    
Endpoints:
    GET /api/dashboard - Get dashboard summary data
    GET /api/states - Get state-level data
    GET /api/demographics/{category} - Get demographic breakdowns
    GET /api/health - Health check
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import Optional, List, Dict, Any
import json
import pandas as pd
from datetime import datetime

# Initialize FastAPI app
app = FastAPI(
    title="PLFS Dashboard API",
    description="API for PLFS Labor Market Data",
    version="1.0.0"
)

# CORS middleware (allow frontend to access API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React default
        "http://localhost:8080",  # Vue default
        "http://localhost:5173",  # Vite default
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
DATA_PATH = Path("./data/output")
DASHBOARD_FILE = DATA_PATH / "dashboard_data.json"
SUMMARY_FILE = DATA_PATH / "summary_statistics.json"
PROCESSED_FILE = DATA_PATH / "plfs_processed_full.parquet"


# ============================================
# Helper Functions
# ============================================

def load_json_file(filepath: Path) -> Dict[str, Any]:
    """Load JSON file with error handling."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Data file not found: {filepath.name}"
        )
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid JSON in file: {filepath.name}"
        )


def load_processed_data() -> pd.DataFrame:
    """Load processed Parquet data with error handling."""
    try:
        return pd.read_parquet(PROCESSED_FILE)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Processed data file not found. Run pipeline first."
        )


# ============================================
# API Endpoints
# ============================================

@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "name": "PLFS Dashboard API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    
    # Check if required files exist
    files_status = {
        "dashboard_data": DASHBOARD_FILE.exists(),
        "summary_statistics": SUMMARY_FILE.exists(),
        "processed_data": PROCESSED_FILE.exists()
    }
    
    all_healthy = all(files_status.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.now().isoformat(),
        "files": files_status
    }


@app.get("/api/dashboard")
async def get_dashboard_data():
    """
    Get comprehensive dashboard data.
    
    Returns:
        Dashboard summary with national indicators, demographics, and age groups
    """
    data = load_json_file(DASHBOARD_FILE)
    return JSONResponse(content=data)


@app.get("/api/indicators/national")
async def get_national_indicators():
    """
    Get national-level labor market indicators.
    
    Returns:
        Unemployment rate, LFPR, and WPR
    """
    data = load_json_file(DASHBOARD_FILE)
    return JSONResponse(content=data.get("national_indicators", {}))


@app.get("/api/demographics/gender")
async def get_gender_statistics():
    """
    Get gender-disaggregated statistics.
    
    Returns:
        Male and female unemployment rates and LFPR
    """
    data = load_json_file(DASHBOARD_FILE)
    return JSONResponse(content=data.get("demographics", {}).get("by_gender", {}))


@app.get("/api/demographics/sector")
async def get_sector_statistics():
    """
    Get rural-urban statistics.
    
    Returns:
        Rural and urban unemployment rates
    """
    data = load_json_file(DASHBOARD_FILE)
    return JSONResponse(content=data.get("demographics", {}).get("by_sector", {}))


@app.get("/api/demographics/age-groups")
async def get_age_group_statistics():
    """
    Get age-group statistics.
    
    Returns:
        List of age groups with unemployment rates
    """
    data = load_json_file(DASHBOARD_FILE)
    return JSONResponse(content=data.get("age_groups", []))


@app.get("/api/states")
async def get_state_data(
    top_n: Optional[int] = Query(None, description="Return top N states by unemployment")
):
    """
    Get state-level data.
    
    Args:
        top_n: Optional limit to top N states
        
    Returns:
        State-level unemployment data
    """
    summary = load_json_file(SUMMARY_FILE)
    
    if "by_state" not in summary:
        raise HTTPException(
            status_code=404,
            detail="State-level data not available"
        )
    
    state_data = summary["by_state"]["unemployment"]
    
    # Convert to list of dicts
    states = [
        {"state_code": state, "unemployment_rate": rate}
        for state, rate in state_data.items()
    ]
    
    # Sort by unemployment rate
    states.sort(key=lambda x: x["unemployment_rate"], reverse=True)
    
    # Limit if requested
    if top_n:
        states = states[:top_n]
    
    return JSONResponse(content={"states": states})


@app.get("/api/custom-query")
async def custom_query(
    group_by: str = Query(..., description="Variable to group by (e.g., 'STATE', 'SEX')"),
    metric: str = Query("unemployment", description="Metric to calculate"),
):
    """
    Execute custom query on processed data.
    
    Args:
        group_by: Column to group by
        metric: Metric to calculate (unemployment, lfpr, wpr)
        
    Returns:
        Calculated statistics
    """
    df = load_processed_data()
    
    # Validate group_by column exists
    if group_by not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"Column '{group_by}' not found in data"
        )
    
    # Calculate metric
    if metric == "unemployment":
        result = df.groupby(group_by).apply(
            lambda x: (x['unemployed'] * x['WEIGHT']).sum() / x['WEIGHT'].sum() * 100
        )
    elif metric == "lfpr":
        result = df.groupby(group_by).apply(
            lambda x: (x['in_labor_force'] * x['WEIGHT']).sum() / x['WEIGHT'].sum() * 100
        )
    elif metric == "wpr":
        result = df.groupby(group_by).apply(
            lambda x: (x['employed'] * x['WEIGHT']).sum() / x['WEIGHT'].sum() * 100
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metric: {metric}. Use: unemployment, lfpr, or wpr"
        )
    
    # Convert to JSON-serializable format
    data = {
        "group_by": group_by,
        "metric": metric,
        "results": result.to_dict()
    }
    
    return JSONResponse(content=data)


@app.get("/api/metadata")
async def get_metadata():
    """
    Get dataset metadata.
    
    Returns:
        Metadata about the dataset
    """
    data = load_json_file(DASHBOARD_FILE)
    return JSONResponse(content=data.get("metadata", {}))


# ============================================
# Error Handlers
# ============================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Custom 404 handler."""
    return JSONResponse(
        status_code=404,
        content={"error": "Resource not found", "detail": str(exc.detail)}
    )


@app.exception_handler(500)
async def server_error_handler(request, exc):
    """Custom 500 handler."""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


# ============================================
# Run Server
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
