# requirements.py
requirements = [
    "fastapi",
    "uvicorn",
    "pandas",
    "sqlalchemy",
    "pymysql",          # or mysqlclient if you prefer
    "requests",
    "jinja2",
    "python-multipart",
    "openpyxl",         # for reading the Excel file
    "pdfkit",           # optional, only if you want PDF report generation
]

# If you just want to print them to pipe into pip:
if __name__ == "__main__":
    print("\n".join(requirements))

#pip install -r <(python requirements.py)