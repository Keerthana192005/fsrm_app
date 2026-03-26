"""
WSGI entry point for production deployment
"""
import os
from app import create_app

# Create app instance
app = create_app('production')

# Initialize database if needed (only for local development)
# In production, Render will handle database initialization
if os.environ.get('FLASK_ENV') != 'production':
    try:
        from app import create_tables_and_seed
        create_tables_and_seed(app)
    except Exception as e:
        print(f"Database initialization error: {e}")

if __name__ == "__main__":
    app.run()
