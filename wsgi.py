"""
WSGI entry point for production deployment
"""
import os
from app import create_app

# Create app instance
app = create_app('production')

# Initialize database tables
with app.app_context():
    try:
        from app import db
        db.create_all()
        print("Database tables created successfully")
    except Exception as e:
        print(f"Error creating database tables: {e}")

if __name__ == "__main__":
    app.run()
