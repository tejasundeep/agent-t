import sqlite3
from registry import tool

@tool
def sqlite_query(db_path: str, query: str):
    """Execute a query (SELECT, INSERT, UPDATE, CREATE) on a local SQLite database and return results."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(query)
        
        # Check if query returns data
        if cursor.description:
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            conn.close()
            
            # Format results
            result = [f"Columns: {', '.join(columns)}"]
            for r in rows:
                result.append(str(r))
            return "\n".join(result)
        else:
            conn.commit()
            rows_affected = cursor.rowcount
            conn.close()
            return f"Query executed successfully. Rows affected: {rows_affected}."
    except Exception as e:
        return f"Database Error: {e}"
