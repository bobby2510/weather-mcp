import os
import random
import time
import base64 # <-- Add this line
import httpx
from datetime import datetime
from typing import Literal, Optional, Any, List
import uvicorn

# --- Document Generation Libraries ---
from fpdf import FPDF
from docx import Document
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# --- FastMCP Imports (FileContent dependency removed) ---
from mcp.server.fastmcp import FastMCP
# from mcp.types import FileContent # <-- REMOVED
from fastmcp.exceptions import ToolError

# --- Configuration ---
# NOTE: Replace 'YOUR_API_TOKEN' with the actual token or set it in your environment
API_KEY = 'b27fe189341c46fe8ad63338251509' #os.environ.get("WEATHER_API_TOKEN", "YOUR_API_TOKEN") 
BASE_URL = "http://api.weatherapi.com/v1"

# Initialize the FastMCP server
# The name and description are what the AI sees.
mcp = FastMCP(
    name="Weather and Document Generator",
    instructions="A powerful server for fetching current, forecast, and historical weather data, and generating professional reports in PDF, DOCX, PNG, and Markdown formats.",
)

# ----------------------------------------------------
# ⛈️ Weather API Tools (Tools 1-3)
# ----------------------------------------------------

async def make_weather_request(endpoint: str, params: dict) -> dict:
    """Helper function to make asynchronous GET requests to the Weather API."""
    if API_KEY == "YOUR_API_TOKEN":
        raise ToolError(
            f"API_KEY is not configured. Please set the WEATHER_API_TOKEN environment variable."
        )

    url = f"{BASE_URL}/{endpoint}.json"
    full_params = {"key": API_KEY, **params}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url, params=full_params)
            response.raise_for_status()
            
            data = response.json()
            # If the API returns an error in the JSON body, raise a ToolError
            if 'error' in data:
                raise ToolError(f"Weather API Error: {data['error']['message']}")
            
            return data
        except httpx.HTTPStatusError as e:
            # Handle specific HTTP errors
            raise ToolError(f"HTTP Error {e.response.status_code}: Could not reach weather API.")
        except httpx.RequestError as e:
            # Handle network/connection errors
            raise ToolError(f"Network Error: Could not connect to weather API: {e}")
        except ToolError:
            # Re-raise ToolError if it originated from the data validation above
            raise
        except Exception as e:
            # Catch all other exceptions
            raise ToolError(f"An unexpected error occurred during API call: {e}")


@mcp.tool()
async def get_current_weather(q: str) -> dict:
    """
    Retrieves the current/real-time weather for a given location.
    
    Args:
        q: The query string. Can be a city name (e.g., 'London'), US Zipcode, UK Postcode, or Latitude/Longitude (e.g., '30.3,-97.7').
        
    Returns:
        A JSON object containing the current weather details.
    """
    return await make_weather_request("current", {"q": q})


@mcp.tool()
async def get_forecast_weather(q: str, days: Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]) -> dict:
    """
    Retrieves the weather forecast for a location for up to 14 days.
    
    Args:
        q: The query string. Can be a city name, postal code, or Lat/Lon.
        days: The number of days for the forecast (1 to 14).
        
    Returns:
        A JSON object containing the weather forecast details.
    """
    # Cast days to int to ensure correct JSON-RPC/API parameter type
    return await make_weather_request("forecast", {"q": q, "days": int(days)})


@mcp.tool()
async def get_history_weather(q: str, dt: str) -> dict:
    """
    Retrieves historical weather for a specific date on or after 2015-01-01.
    
    Args:
        q: The query string. Can be a city name, postal code, or Lat/Lon.
        dt: The date in 'YYYY-MM-DD' format (e.g., '2025-10-28').
        
    Returns:
        A JSON object containing the historical weather details.
    """
    try:
        # Validate date format to match API requirement
        datetime.strptime(dt, '%Y-%m-%d')
    except ValueError:
        raise ToolError(f"Invalid date format: '{dt}'. Must be in YYYY-MM-DD format.")
        
    return await make_weather_request("history", {"q": q, "dt": dt})

# ----------------------------------------------------
# 📝 Document Generation Tools (Tools 4-7)
# ----------------------------------------------------

# Helper function to ensure we have a valid filename
def get_report_filename(file_name: Optional[str], extension: str) -> str:
    """Generates a filename with a timestamp if none is provided."""
    if file_name is None or file_name.strip() == "":
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"report_{timestamp}.{extension}"
    # Ensure filename ends with the correct extension
    if not file_name.lower().endswith(f".{extension}"):
        file_name = f"{file_name}.{extension}"
    return file_name

# Helper function to handle a successful file generation result
# The return type is List[Any] because we are using FastMCP's auto-conversion of raw bytes.
def handle_file_result(file_path: str, mime_type: str) -> List[Any]:
    """
    Returns the file data as bytes wrapped in a dictionary for MCP to auto-convert
    into a file-like content block, eliminating the need for the FileContent class.
    """
    file_data = open(file_path, "rb").read() 
    encoded_data = base64.b64encode(file_data).decode('utf-8')
    return [
        {
            "data": encoded_data,
            "mime_type": mime_type,
            "name": os.path.basename(file_path),
        }
    ]
@mcp.tool()
def generate_pdf_report(content: str, file_name: Optional[str] = None) -> List[Any]:
    """
    Generates a PDF document from the provided text content.
    ...
    """
    file_path = get_report_filename(file_name, "pdf")
    
    # Simple PDF generation using fpdf2
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, content)

    # FIX: Remove the second positional argument ("F") which is deprecated/removed.
    # The function now takes only the file path.
    pdf.output(file_path) 
    
    return handle_file_result(file_path, "application/pdf")


@mcp.tool()
def generate_docx_report(content: str, file_name: Optional[str] = None) -> List[Any]: # Return type updated
    """
    Generates a Microsoft Word (.docx) document from the provided text content.
    
    Args:
        content: The text content to be written into the DOCX file.
        file_name: Optional filename for the report. Defaults to 'report_<timestamp>.docx'.
        
    Returns:
        A list containing a file content block with the DOCX data (via raw bytes).
    """
    file_path = get_report_filename(file_name, "docx")
    
    # Simple DOCX generation using python-docx
    document = Document()
    document.add_paragraph(content)
    document.save(file_path)
    
    return handle_file_result(file_path, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@mcp.tool()
def generate_png_image(content: str, file_name: Optional[str] = None) -> List[Any]: # Return type updated
    """
    Generates a PNG image containing the provided text content.
    
    Args:
        content: The text content to be rendered on the PNG image.
        file_name: Optional filename for the image. Defaults to 'report_<timestamp>.png'.
        
    Returns:
        A list containing a file content block with the PNG data (via raw bytes).
    """
    file_path = get_report_filename(file_name, "png")
    
    try:
        # Create a simple image (white background)
        img_width, img_height = 800, 400
        img = Image.new('RGB', (img_width, img_height), color='white')
        d = ImageDraw.Draw(img)
        
        # Use a default font, requires a font file to be present (e.g., Arial.ttf)
        # Fallback to default PIL font if no standard font is found
        try:
            # Note: 'arial.ttf' often isn't available by default in environments.
            # Using a known font path or falling back to default is best practice.
            font = ImageFont.truetype("arial.ttf", 20)
        except IOError:
            font = ImageFont.load_default()

        # Simple text wrapping and rendering (This is simplified)
        d.text((50, 50), content, fill='black', font=font)
        
        # Save to a file
        img.save(file_path, "PNG")

        return handle_file_result(file_path, "image/png")

    except Exception as e:
        raise ToolError(f"Failed to generate PNG image: {e}")


@mcp.tool()
def generate_md_report(content: str, file_name: Optional[str] = None) -> List[Any]: # Return type updated
    """
    Generates a Markdown (.md) file containing the provided text content.
    
    Args:
        content: The text content to be written into the Markdown file.
        file_name: Optional filename for the report. Defaults to 'report_<timestamp>.md'.
        
    Returns:
        A list containing a file content block with the Markdown data (via raw bytes).
    """
    file_path = get_report_filename(file_name, "md")
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# Report Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(content)

    return handle_file_result(file_path, "text/markdown")


@mcp.tool()
def list_tools() -> dict:
    return {
        "tools": [
            "get_current_weather",
            "get_forecast_weather",
            "get_history_weather",
            "generate_pdf_report",
            "generate_docx_report",
            "generate_png_image",
            "generate_md_report"
        ]
    }

# ... (code up to mcp initialization)

if __name__ == "__main__":
   
    asgi_app = mcp._app # Re-try .app, maybe the error was transient?
    uvicorn.run(
        asgi_app, 
        host='127.0.0.1', 
        port=8000
    )
    #fastmcp run script.py (run cmd)
