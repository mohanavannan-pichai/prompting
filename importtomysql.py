import pandas as pd
from sqlalchemy import create_engine

EXCEL_PATH = "Occupation_Data.xlsx"
MYSQL_URL  = "mysql+pymysql://promptuser:promptuser123@localhost:3306/promptdb"
TABLE_NAME = "role_contexts"

ROLE_COL    = "Title"
CONTEXT_COL = "Description"

df = pd.read_excel(EXCEL_PATH)
df = df[[ROLE_COL, CONTEXT_COL]].dropna(subset=[ROLE_COL])
df.columns = ["role", "context"]   # rename to match DB columns

engine = create_engine(MYSQL_URL)

# Replace table contents each time (drop & recreate):
df.to_sql(TABLE_NAME, engine, if_exists="replace", index=False)

print("✅ Imported", len(df), "rows into", TABLE_NAME)