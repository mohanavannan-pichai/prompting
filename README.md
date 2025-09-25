Art of Prompting

By - Mohanavannan Pichai

-----

# 🤖 Art Of Prompting: Ollama-Powered Prompt Builder

A simple, single-file FastAPI application designed to help you build powerful, structured prompts and compare the output of two different local Large Language Models (LLMs) served by **Ollama**.

This project features:

  * 📝 A **structured prompt builder** based on the "Art of Prompting" principles (Role, Context, Task, Style, etc.).
  * 🌐 A simple **FastAPI** backend serving a self-contained HTML/JavaScript frontend.
  * 💾 Integration with a local **MySQL** database to fetch role-specific context.
  * 🧠 Integration with **Ollama** to run models like Mistral and Qwen locally.
  * 📊 **Output comparison** between two chosen models.
  * 📄 **Report generation** (TXT, HTML, PDF).

## Prerequisites

To run this project, you'll need the following installed on your system:

1.  **Python 3.8+**
2.  **Docker (Recommended)** or a local installation of **MySQL** and **Ollama**.
3.  **wkhtmltopdf** (Optional, only for PDF report generation).

## 🚀 Setup & Installation

Follow these steps to get the application running on your desktop.

### 1\. Set up Ollama

The application uses **Ollama** to serve the LLMs locally.

1.  **Install Ollama:** Follow the official installation instructions for your OS.
2.  **Download Models:** The application is configured to use `mistral:latest` and `qwen3:4b`. Run the following commands in your terminal:
    ```bash
    ollama run mistral:latest
    ollama run qwen3:4b
    ```
    Ollama will download and start the models. Keep the Ollama service running.

### 2\. Set up MySQL Database

The application requires a MySQL database to store and fetch context for different roles.

1.  **Start MySQL:**

      * **Using Docker (Recommended):**
        ```bash
        docker run --name aop-mysql -e MYSQL_ROOT_PASSWORD=my-secret-pw -e MYSQL_DATABASE=promptdb -d -p 3306:3306 mysql:8.0
        ```
      * **Using Local Install:** Ensure your MySQL service is running on port `3306`.

2.  **Create User and Database:**
    The application is configured to use the following credentials (you can change them in `main.py` and `importtomysql.py` if needed):

      * **Database:** `promptdb`
      * **User:** `promptuser`
      * **Password:** `promptuser123`

    If using Docker or a new local install, you might need to connect to MySQL as root and create the user and grant permissions for `promptdb`.

### 3\. Install Python Dependencies

The project uses a dedicated Python script (`requirements.py`) to manage dependencies.

1.  **Create a Virtual Environment (Recommended):**

    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Linux/macOS
    # venv\Scripts\activate  # On Windows
    ```

2.  **Install Requirements:**

    ```bash
    pip install -r <(python requirements.py)
    # Alternatively:
    # python requirements.py > requirements.txt
    # pip install -r requirements.txt
    ```

### 4\. Prepare and Import Data

The application loads the list of roles from an Excel file (`Occupation_Data.xlsx`) and imports the corresponding context into MySQL.

1.  **Get `Occupation_Data.xlsx`:** Ensure you have the Excel file in the project directory. The file must have columns named "Title" (for roles) and "Description" (for context).
2.  **Run the Import Script:**
    This script will connect to the MySQL database and populate the `role_contexts` table.
    ```bash
    python importtomysql.py
    ```
    You should see the output: `✅ Imported [Number] rows into role_contexts`

### 5\. Run the FastAPI Application

With the database and Ollama running, you can now start the web application.

1.  **Run the Server:**

    ```bash
    # For local development (auto-reloads on file change)
    uvicorn main:app --reload

    # For production (using gunicorn as suggested in main.py)
    # gunicorn -k uvicorn.workers.UvicornWorker main:app -w 4
    ```

2.  **Access the App:** Open your web browser and navigate to:
    **`http://127.0.0.1:8000/`** (or `http://localhost:8000/`)

## 💡 How to Use the Application

The interface is divided into two main sections: **Prompt Components** and **Output/Results**.

### 1\. Build Your Prompt

On the left side, fill in the components of your prompt:

  * **Role:** Select a pre-loaded role (e.g., "Data Scientist"). This automatically fetches the **Context** from the database.
  * **Context:** The context fetched from the database, giving the model background information about the role.
  * **Example (Optional):** Provide a successful example of the desired output.
  * **Audience:** Define who the final output is for (e.g., "The CTO," "A high-school student").
  * **Format:** Select the desired output structure (e.g., "Research report," "Email").
  * **Style:** Select the tone/style (e.g., "Academic," "Humorous").
  * **Constraints (Optional):** Set limits (e.g., "Keep it under 200 words," "Avoid jargon").
  * **Task:** The core instruction for the LLM (e.g., "Summarize the quarterly earnings report...").

### 2\. Generate and Compare

1.  Click the **`Work on it`** button.
2.  The application will first construct the full **Final Prompt** in the text area.
3.  It then sends this prompt to the Ollama service to generate outputs from both the **Mistral** and **Qwen** models concurrently.
4.  The generated text from each model will appear in the dedicated output boxes.

### 3\. Generate a Report

1.  Once you have outputs, select a report type (`Text file (.txt)`, `Single-file web page (.html)`, or `PDF (.pdf)`) from the dropdown.
2.  Click **`Generate report`**.
3.  The report containing both model outputs will download to your machine.

-----

## Configuration

You can customize the models and database connection by modifying the global variables at the top of the `main.py` file:

| Variable | Description | Default Value |
| :--- | :--- | :--- |
| `MYSQL_URL` | SQLAlchemy connection string | `mysql+pymysql://promptuser:promptuser123@localhost:3306/promptdb` |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `MISTRAL_MODEL` | Name of the first Ollama model | `mistral:latest` |
| `QWEN_MODEL` | Name of the second Ollama model | `qwen3:4b` |