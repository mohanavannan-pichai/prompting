"""
Art Of Prompting - FastAPI application (single-file)
Author: ChatGPT (example)
Run with: gunicorn -k uvicorn.workers.UvicornWorker main:app -w 4

Requirements (pip):
  - fastapi
  - uvicorn
  - pandas
  - sqlalchemy
  - pymysql         # or mysqlclient
  - requests
  - jinja2
  - python-multipart
  - pdfkit (optional for PDF generation)
  - openpyxl        # for reading .xlsx
"""

import os
import io
import json
import tempfile
from typing import List, Optional
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from sqlalchemy import create_engine, text
import requests
from starlette.responses import RedirectResponse

# Optional pdf generation
try:
    import pdfkit
    PDFKIT_AVAILABLE = True
except Exception:
    PDFKIT_AVAILABLE = False

# -----------------------
# CONFIGURATION - EDIT THESE TO MATCH YOUR ENVIRONMENT
# -----------------------
EXCEL_PATH = os.environ.get("KCOMP_PATH", "Occupation_Data.xlsx")
# MySQL connection string (SQLAlchemy) - update user, password, host, port, dbname
mysql_username="promptuser"
mysql_password="promptuser123"
mysql_database="promptdb"
MYSQL_URL = os.environ.get("MYSQL_URL", f"mysql+pymysql://{mysql_username}:{mysql_password}@localhost:3306/{mysql_database}")
# Table and column names expected in MySQL table that stores contexts by role.
# Table should have columns: role (string) and context (text)
CONTEXT_TABLE = os.environ.get("CONTEXT_TABLE", "role_contexts")
ROLE_COLUMN = os.environ.get("ROLE_COLUMN", "role")
CONTEXT_COLUMN = os.environ.get("CONTEXT_COLUMN", "context")

# Ollama endpoint (local)
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# Ollama model names (change to your local model names)
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral:latest")        # example name
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen3:4b")                     # example name

# Available formats & styles - you can expand
PREDEFINED_FORMATS = [
    "Research report",
    "Project report",
    "Blog post",
    "Email",
    "Code",
    "Presentation outline",
    "Bullet summary",
]
PREPOPULATED_STYLES = [
    "Professional",
    "Casual",
    "Funky",
    "Academic",
    "Concise",
    "Humorous",
]

# -----------------------
# Initialize
# -----------------------
app = FastAPI(title="Art Of Prompting - API")

# Allow CORS for local frontend usage (optional)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# mount static if you want (not necessary here)
if not os.path.exists("static"):
    os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Load roles from EXCEL at startup
def load_roles_from_excel(path: str) -> List[str]:
    if not os.path.exists(path):
        print(f"[warning] Excel file not found at {path}. Continuing with empty roles.")
        return []
    df = pd.read_excel(path)
    # Heuristic: find first column that looks like Role/role/name
    col_candidates = [c for c in df.columns if 'Title' in c.lower() or 'name' in c.lower()]
    if not col_candidates:
        # fallback to first column
        col = df.columns[1]
    else:
        col = col_candidates[1]
    roles = df[col].dropna().astype(str).tolist()
    # Remove duplicates while preserving order
    seen = set()
    out = []
    for r in roles:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out

ROLES = load_roles_from_excel(EXCEL_PATH)

# Setup DB engine (SQLAlchemy)
try:
    engine = create_engine(MYSQL_URL, pool_pre_ping=True)
    # test connection
    with engine.connect() as conn:
        pass
except Exception as e:
    engine = None
    print(f"[warning] Could not create DB engine: {e}. Context fetching will fail until configured.")

# -----------------------
# Helper functions
# -----------------------

def fetch_context_for_role(role: str) -> str:
    """
    Fetch context text from MySQL table for the given role.
    Expects table with ROLE_COLUMN and CONTEXT_COLUMN.
    """
    if engine is None:
        return ""
    query = text(f"SELECT `{CONTEXT_COLUMN}` FROM `{CONTEXT_TABLE}` WHERE `{ROLE_COLUMN}` = :role LIMIT 1")
    with engine.connect() as conn:
        res = conn.execute(query, {"role": role}).fetchone()
        if res:
            return res[0] or ""
    return ""

def make_prompt(payload: dict) -> str:
    """
    Compose a single prompt string from the UI details.
    payload should contain role, context, example, audience, format, style, constraints, task
    """
    parts = []
    parts.append(f"Role: {payload.get('role','')}")
    context = payload.get('context','')
    if context:
        parts.append(f"Context:\n{context}")
    example = payload.get('example','')
    if example:
        parts.append(f"Example:\n{example}")
    audience = payload.get('audience','')
    if audience:
        parts.append(f"Target audience: {audience}")
    fmt = payload.get('format','')
    if fmt:
        parts.append(f"Format: {fmt}")
    style = payload.get('style','')
    if style:
        parts.append(f"Style: {style}")
    constraints = payload.get('constraints','')
    if constraints:
        parts.append(f"Constraints: {constraints}")
    task = payload.get('task','')
    if task:
        parts.append(f"Task:\n{task}")
    # Make a final instruction to the model
    parts.append("\nPlease produce a complete, well-structured response for the task above. "
                 "Label sections clearly if appropriate and keep responses within reasonable length.")
    return "\n\n".join(parts)

def call_ollama_generate(model_name: str, prompt: str, max_tokens: int = 512, stream=False):
    """
    Call local Ollama /api/generate?model=<model_name>
    Returns the generated text (or raises).
    """
    url = f"{OLLAMA_HOST}/api/generate"
    headers = {"Content-Type": "application/json"}
    payload = {
        "model":model_name,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "stream":False
        # you may add other parameters like temperature, top_p, stop, etc.
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        response.raise_for_status()
        # Ollama typically returns JSON with a "container" or "output" structure - but to be robust,
        # try to parse text from common fields.
        data = response.json()
        full_response = ""
        for line in response.iter_lines():
          if line:
              # Decode the line and parse the JSON object
              decoded_line = line.decode('utf-8')
              try:
                  json_data = json.loads(decoded_line)
                  
                  # Extract the 'response' part of the data chunk
                  chunk = json_data.get("response", "")
                  
                  # Print the chunk immediately
                  print(chunk, end="", flush=True)
                  
                  # Accumulate for the full response if needed later
                  full_response += chunk
                  
                  # Check for the end of the stream
                  if json_data.get("done"):
                      break
              except json.JSONDecodeError:
                  # Handle cases where a line might not be a valid JSON object
                  # (This is less common but good for robustness)
                  pass

        return full_response
    except requests.RequestException as e:
        raise RuntimeError(f"Ollama request failed: {e}")

# -----------------------
# API Models
# -----------------------
class GenerateRequest(BaseModel):
    role: str
    context: Optional[str] = ""
    example: Optional[str] = ""
    audience: Optional[str] = ""
    format: Optional[str] = ""
    style: Optional[str] = ""
    constraints: Optional[str] = ""
    task: str

# -----------------------
# Routes - API
# -----------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    """
    Serve the single-page UI (HTML + JS). 
    This returns a complete HTML page using Bootstrap for quick styling.
    """
    # The HTML is intentionally self-contained (JS calls the endpoints below)
    html = f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width,initial-scale=1"/>
    <title>Art Of Prompting</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet"/>
    <style>
      body {{ padding: 20px; background: #f7fafc; }}
      .card {{ box-shadow: 0 6px 18px rgba(0,0,0,0.08); border-radius: 12px; }}
      textarea[disabled] {{ background:#f1f5f9; }}
      .small-muted {{ font-size: 0.85rem; color: #6b7280; }}
    </style>
  </head>
  <body>
    <div class="container">
      <div class="text-center mb-4">
        <h1 class="display-6">Art Of Prompting</h1>
        <p class="small-muted">Build powerful prompts and compare Mistral & Qwen outputs</p>
      </div>

      <div class="row g-3">
        <div class="col-md-6">
          <div class="card p-3">
            <div class="mb-2"><strong>Role</strong></div>
            <input type="text" id="roleSelect" list="rolesList">
            <datalist id="rolesList"></datalist>

            <div class="mb-2"><strong>Context</strong></div>
            <textarea id="contextArea" class="form-control mb-2" rows="6" disabled></textarea>

            <div class="mb-2"><strong>Example</strong></div>
            <textarea id="exampleArea" class="form-control mb-2" rows="3" placeholder="Optional example..."></textarea>

            <div class="mb-2"><strong>Audience</strong></div>
            <select id="audienceSelect" class="form-select mb-2"></select>

            <div class="mb-2"><strong>Format</strong></div>
            <select id="formatSelect" class="form-select mb-2">
              {"".join(f'<option>{fmt}</option>' for fmt in PREDEFINED_FORMATS)}
            </select>

            <div class="mb-2"><strong>Style</strong></div>
            <select id="styleSelect" class="form-select mb-2">
              {"".join(f'<option>{s}</option>' for s in PREPOPULATED_STYLES)}
            </select>

            <div class="mb-2"><strong>Constraints</strong></div>
            <textarea id="constraintsArea" class="form-control mb-2" rows="2" placeholder="Any constraints (length, banned words, tone)..."></textarea>
          </div>
        </div>

        <div class="col-md-6">
          <div class="card p-3">
            <div class="mb-2"><strong>Task</strong></div>
            <textarea id="taskArea" class="form-control mb-2" rows="6" placeholder="Describe the task you want the LLM to perform..."></textarea>
            <div class="d-flex gap-2">
              <button id="workBtn" class="btn btn-primary">Work on it</button>
              <button id="clearBtn" class="btn btn-outline-secondary">Clear</button>
            </div>

            <hr/>
            <div class="mb-2"><strong>Final Prompt</strong></div>
            <textarea id="promptArea" class="form-control mb-2" rows="6" disabled></textarea>

            <div class="row">
              <div class="col-6">
                <div class="mb-1"><strong>Mistral Output</strong></div>
                <textarea id="mistralOut" class="form-control mb-1" rows="8" disabled></textarea>
              </div>
              <div class="col-6">
                <div class="mb-1"><strong>Qwen Output</strong></div>
                <textarea id="qwenOut" class="form-control mb-1" rows="8" disabled></textarea>
              </div>
            </div>

            <div class="mt-2 d-flex gap-2">
              <select id="reportType" class="form-select w-auto">
                <option value="txt">Text file (.txt)</option>
                <option value="html">Single-file web page (.html)</option>
                <option value="pdf">PDF (.pdf)</option>
              </select>
              <button id="genReportBtn" class="btn btn-success">Generate report</button>
            </div>

          </div>
        </div>
      </div>

      <footer class="mt-4 text-center small-muted">
        <div>Local Ollama models expected: {MISTRAL_MODEL} and {QWEN_MODEL} at {OLLAMA_HOST}</div>
      </footer>
    </div>

    <script>
      // Helper functions
      async function fetchJson(url, opts) {{
        const r = await fetch(url, opts || {{}});
        if (!r.ok) {{
          throw new Error(await r.text());
        }}
        return r.json();
      }}

      async function init() {{
        // Load roles
        try {{
          const roles = await fetchJson('/api/roles');
          const roleSel = document.getElementById('rolesList');
          roleSel.innerHTML = '';
          roles.forEach(r => {{
            const o = document.createElement('option'); o.value = r; o.text = r; roleSel.appendChild(o);
          }});
          populateAudience(roles);
          if (roles.length) roleSel.value = roles[0];
          // trigger load context
          await onRoleChange();
        }} catch (e) {{
          console.error('Failed to load roles', e);
        }}
      }}

      function populateAudience(roles) {{
        const a = document.getElementById('audienceSelect');
        a.innerHTML = '';
        roles.forEach(r => {{
          const o = document.createElement('option'); o.value = r; o.text = r; a.appendChild(o);
        }});
      }}

      async function onRoleChange() {{
        const role = document.getElementById('roleSelect').value;
        try {{
          const res = await fetch('/api/context?role=' + encodeURIComponent(role));
          if (res.ok) {{
            const data = await res.json();
            document.getElementById('contextArea').value = data.context || '';
            // set audience default to role
            const aud = document.getElementById('audienceSelect');
            aud.value = role;
          }} else {{
            document.getElementById('contextArea').value = '';
          }}
        }} catch(e) {{
          console.error(e);
          document.getElementById('contextArea').value = '';
        }}
      }}

      document.addEventListener('DOMContentLoaded', () => {{
        init();

        document.getElementById('roleSelect').addEventListener('change', onRoleChange);

        document.getElementById('workBtn').addEventListener('click', async () => {{
          const payload = {{
            role: document.getElementById('roleSelect').value,
            context: document.getElementById('contextArea').value,
            example: document.getElementById('exampleArea').value,
            audience: document.getElementById('audienceSelect').value,
            format: document.getElementById('formatSelect').value,
            style: document.getElementById('styleSelect').value,
            constraints: document.getElementById('constraintsArea').value,
            task: document.getElementById('taskArea').value,
          }};
          let prompt_string="";
          prompt_string+="Role:" + document.getElementById('roleSelect').value;
          prompt_string+="\\nContext:" + document.getElementById('contextArea').value;
          prompt_string+="\\nExample:" + document.getElementById('exampleArea').value;
          prompt_string+="\\nAudience:" + document.getElementById('audienceSelect').value;
          prompt_string+="\\nFormat:" + document.getElementById('formatSelect').value;
          prompt_string+="\\nStyle:" + document.getElementById('styleSelect').value;
          prompt_string+="\\nConstraints:" + document.getElementById('constraintsArea').value;
          prompt_string+="\\nTask:" + document.getElementById('taskArea').value;
          const prompt = document.getElementById('promptArea');
          prompt.value = prompt_string;
          // Reset outputs
          document.getElementById('mistralOut').value = 'Working...';
          document.getElementById('qwenOut').value = 'Working...';
          try {{
            const r = await fetch('/api/generate', {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify(payload)
            }});
            if (!r.ok) {{
              const t = await r.text();
              alert('Generate failed: ' + t);
              document.getElementById('mistralOut').value = '';
              document.getElementById('qwenOut').value = '';
              return;
            }}
            const data = await r.json();
            document.getElementById('mistralOut').value = data.mistral || '';
            document.getElementById('qwenOut').value = data.qwen || '';
          }} catch (e) {{
            alert('Error: ' + e);
            document.getElementById('mistralOut').value = '';
            document.getElementById('qwenOut').value = '';
          }}
        }});

        document.getElementById('clearBtn').addEventListener('click', () => {{
          document.getElementById('exampleArea').value = '';
          document.getElementById('constraintsArea').value = '';
          document.getElementById('taskArea').value = '';
          document.getElementById('mistralOut').value = '';
          document.getElementById('qwenOut').value = '';
          document.getElementById('promptArea').value='';
        }});

        document.getElementById('genReportBtn').addEventListener('click', async () => {{
          const rtype = document.getElementById('reportType').value;
          const mistral = document.getElementById('mistralOut').value;
          const qwen = document.getElementById('qwenOut').value;
          if (!mistral && !qwen) {{
            alert('No outputs to include in report.');
            return;
          }}
          // send POST to create report
          const res = await fetch('/api/report', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ type: rtype, mistral: mistral, qwen: qwen }})
          }});
          if (!res.ok) {{
            alert('Report generation failed: ' + await res.text());
            return;
          }}
          const blob = await res.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          const ext = rtype === 'txt' ? 'txt' : (rtype === 'html' ? 'html' : 'pdf');
          a.download = 'art_of_prompting_report.' + ext;
          document.body.appendChild(a);
          a.click();
          a.remove();
          window.URL.revokeObjectURL(url);
        }});
      }});
    </script>

  </body>
</html>
    """
    return HTMLResponse(content=html, status_code=200)

@app.get("/api/roles")
async def api_roles():
    """Return list of roles loaded from the Excel file"""
    return JSONResponse(content=ROLES)

@app.get("/api/context")
async def api_context(role: str):
    """Return the context for the given role fetched from MySQL"""
    ctx = fetch_context_for_role(role)
    return JSONResponse(content={"context": ctx})

@app.post("/api/generate")
async def api_generate(req: GenerateRequest):
    """
    Compose prompt from provided UI data, call both Mistral and Qwen via Ollama,
    and return both outputs.
    """
    payload = req.dict()
    prompt = make_prompt(payload)

    # Call Mistral
    try:
        mistral_out = call_ollama_generate(MISTRAL_MODEL, prompt, max_tokens=1024)
    except Exception as e:
        mistral_out = f"[Error calling Mistral model {MISTRAL_MODEL}: {e}]"

    # Call Qwen
    try:
        qwen_out = call_ollama_generate(QWEN_MODEL, prompt, max_tokens=1024)
    except Exception as e:
        qwen_out = f"[Error calling Qwen model {QWEN_MODEL}: {e}]"

    return JSONResponse(content={"mistral": mistral_out, "qwen": qwen_out})

@app.post("/api/report")
async def api_report(payload: dict):
    """
    Generate a report (txt/html/pdf) from supplied mistral + qwen outputs.
    payload: { type: 'txt'|'html'|'pdf', mistral: str, qwen: str }
    """
    rtype = payload.get("type", "txt")
    mistral = payload.get("mistral", "")
    qwen = payload.get("qwen", "")

    # Build a basic HTML report
    html_content = f"""
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Art Of Prompting Report</title>
<style>body{{font-family: Arial, Helvetica, sans-serif; padding:20px;}} .box{{border-radius:8px;padding:12px;margin-bottom:12px;box-shadow:0 6px 12px rgba(0,0,0,0.06);}}</style>
</head>
<body>
<h1>Art Of Prompting - Report</h1>
<h2>Mistral Output</h2>
<div class="box"><pre style="white-space:pre-wrap">{mistral}</pre></div>
<h2>Qwen Output</h2>
<div class="box"><pre style="white-space:pre-wrap">{qwen}</pre></div>
</body></html>
"""
    if rtype == "txt":
        txt = f"=== Mistral Output ===\n{mistral}\n\n=== Qwen Output ===\n{qwen}\n"
        return FileResponse(io.BytesIO(txt.encode("utf-8")), media_type="text/plain", filename="art_of_prompting_report.txt")
    elif rtype == "html":
        b = io.BytesIO(html_content.encode("utf-8"))
        return FileResponse(b, media_type="text/html", filename="art_of_prompting_report.html")
    elif rtype == "pdf":
        if not PDFKIT_AVAILABLE:
            return JSONResponse(status_code=400, content={"error": "PDF generation not available on server (pdfkit/wkhtmltopdf missing)."})
        # generate pdf to temp file
        tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmpf.close()
        # pdfkit.from_string requires wkhtmltopdf installed and accessible
        pdfkit.from_string(html_content, tmpf.name)
        return FileResponse(tmpf.name, media_type="application/pdf", filename="art_of_prompting_report.pdf")
    else:
        return JSONResponse(status_code=400, content={"error": "Unknown report type"})

# Simple health check
@app.get("/api/health")
async def health():
    return JSONResponse(content={"status": "ok", "mistral_model": MISTRAL_MODEL, "qwen_model": QWEN_MODEL})
