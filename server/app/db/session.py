"""
Database configuration and initialization for YOLO Generator
Creates MySQL database and tables if they don't exist
"""

import mysql.connector
from mysql.connector import Error

from app.core.config import settings
from app.core.logging import logger


def create_database():
    """Create database if it doesn't exist"""
    try:
        # Connect without database
        connection = mysql.connector.connect(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password
        )
        
        cursor = connection.cursor()
        
        # Create database
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {settings.db_name}")
        logger.info(f"✓ Database '{settings.db_name}' ready")
        
        cursor.close()
        connection.close()
        return True
        
    except Error as e:
        logger.error(f"✗ Error creating database: {e}")
        return False


def get_db_connection():
    """Get database connection"""
    try:
        connection = mysql.connector.connect(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            database=settings.db_name
        )
        return connection
    except Error as e:
        logger.error(f"✗ Error connecting to database: {e}")
        return None


def migrate_users_otp_columns(connection) -> None:
    """
    Older deployments may have `users` without OTP columns; CREATE TABLE IF NOT EXISTS
    does not add new columns. Login/verify UPDATE those columns and would fail with 500.
    """
    try:
        cur = connection.cursor()
        cur.execute("SHOW COLUMNS FROM users LIKE 'verification_code'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE users ADD COLUMN verification_code VARCHAR(32) NULL")
            logger.info("Migrated: added users.verification_code")
        cur.execute("SHOW COLUMNS FROM users LIKE 'verification_code_expires'")
        if not cur.fetchone():
            cur.execute(
                "ALTER TABLE users ADD COLUMN verification_code_expires TIMESTAMP NULL"
            )
            logger.info("Migrated: added users.verification_code_expires")
        connection.commit()
        cur.close()
    except Error as e:
        logger.error(f"migrate_users_otp_columns: {e}")
        raise


def create_tables():
    """Create all required tables"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role ENUM('admin', 'user', 'viewer') DEFAULT 'user',
                is_verified BOOLEAN DEFAULT FALSE,
                verification_code VARCHAR(6),
                verification_code_expires TIMESTAMP NULL,
                reset_token VARCHAR(255),
                reset_token_expires TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_username (username),
                INDEX idx_email (email),
                INDEX idx_role (role)
            )
        """)
        logger.info("✓ Table 'users' ready")
        migrate_users_otp_columns(connection)
        
        # Pending registrations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_registrations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                role ENUM('admin', 'user', 'viewer') DEFAULT 'user',
                verification_code VARCHAR(6),
                verification_code_expires TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_email (email)
            )
        """)
        logger.info("✓ Table 'pending_registrations' ready")
        
        # Datasets table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS datasets (
                id VARCHAR(255) PRIMARY KEY,
                user_id INT,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                classes JSON NOT NULL,
                total_images INT DEFAULT 0,
                annotated_images INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id),
                INDEX idx_created_at (created_at)
            )
        """)
        logger.info("✓ Table 'datasets' ready")
        
        # Dataset images table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dataset_images (
                id VARCHAR(255) PRIMARY KEY,
                dataset_id VARCHAR(255) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                original_name VARCHAR(255),
                path VARCHAR(500) NOT NULL,
                annotated BOOLEAN DEFAULT FALSE,
                split ENUM('train', 'val', 'test') NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                INDEX idx_dataset_id (dataset_id),
                INDEX idx_annotated (annotated),
                INDEX idx_split (split)
            )
        """)
        logger.info("✓ Table 'dataset_images' ready")
        
        # Annotations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS annotations (
                id VARCHAR(255) PRIMARY KEY,
                dataset_id VARCHAR(255) NOT NULL,
                image_id VARCHAR(255) NOT NULL,
                image_name VARCHAR(255) NOT NULL,
                width INT NOT NULL,
                height INT NOT NULL,
                boxes JSON NOT NULL,
                split ENUM('train', 'val', 'test') NULL,
                status ENUM('unlabeled', 'predicted', 'annotated', 'reviewed') DEFAULT 'annotated',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                FOREIGN KEY (image_id) REFERENCES dataset_images(id) ON DELETE CASCADE,
                INDEX idx_dataset_id (dataset_id),
                INDEX idx_image_id (image_id),
                INDEX idx_status (status)
            )
        """)
        logger.info("✓ Table 'annotations' ready")

        # Dataset Versions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dataset_versions (
                id VARCHAR(255) PRIMARY KEY,
                dataset_id VARCHAR(255) NOT NULL,
                version_number INT NOT NULL,
                name VARCHAR(255),
                preprocessing JSON,
                augmentations JSON,
                total_images INT DEFAULT 0,
                yaml_path VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                INDEX idx_dataset_id (dataset_id)
            )
        """)
        logger.info("✓ Table 'dataset_versions' ready")

        # Dataset Version Images table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dataset_version_images (
                id VARCHAR(255) PRIMARY KEY,
                version_id VARCHAR(255) NOT NULL,
                original_image_id VARCHAR(255),
                filename VARCHAR(255) NOT NULL,
                path VARCHAR(500) NOT NULL,
                split ENUM('train', 'val', 'test') DEFAULT 'train',
                width INT NOT NULL,
                height INT NOT NULL,
                boxes JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (version_id) REFERENCES dataset_versions(id) ON DELETE CASCADE,
                FOREIGN KEY (original_image_id) REFERENCES dataset_images(id) ON DELETE SET NULL,
                INDEX idx_version_id (version_id),
                INDEX idx_split (split)
            )
        """)
        logger.info("✓ Table 'dataset_version_images' ready")
        
        # Training jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_jobs (
                id VARCHAR(255) PRIMARY KEY,
                user_id INT,
                dataset_id VARCHAR(255),
                model_name VARCHAR(255) NOT NULL,
                status ENUM('pending', 'running', 'completed', 'failed') DEFAULT 'pending',
                progress INT DEFAULT 0,
                epochs INT NOT NULL,
                batch_size INT NOT NULL,
                config JSON,
                results JSON,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE SET NULL,
                INDEX idx_user_id (user_id),
                INDEX idx_status (status),
                INDEX idx_created_at (created_at)
            )
        """)
        logger.info("✓ Table 'training_jobs' ready")
        
        # Inference history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inference_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                model_name VARCHAR(255) NOT NULL,
                image_name VARCHAR(255),
                num_detections INT DEFAULT 0,
                confidence_threshold FLOAT,
                results JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id),
                INDEX idx_created_at (created_at)
            )
        """)
        logger.info("✓ Table 'inference_history' ready")
        
        # Models table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS models (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                name VARCHAR(255) NOT NULL,
                path VARCHAR(500) NOT NULL,
                type ENUM('pretrained', 'custom') DEFAULT 'custom',
                dataset_id VARCHAR(255),
                training_job_id VARCHAR(255),
                metrics JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id),
                INDEX idx_type (type)
            )
        """)
        logger.info("✓ Table 'models' ready")
        
        # System logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                level ENUM('INFO', 'WARNING', 'ERROR', 'CRITICAL') DEFAULT 'INFO',
                message TEXT NOT NULL,
                details JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_level (level),
                INDEX idx_created_at (created_at)
            )
        """)
        logger.info("✓ Table 'system_logs' ready")
        # Project members table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_members (
                id INT AUTO_INCREMENT PRIMARY KEY,
                dataset_id VARCHAR(255) NOT NULL,
                user_id INT NOT NULL,
                role ENUM('admin', 'annotator', 'viewer') DEFAULT 'annotator',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE KEY unique_membership (dataset_id, user_id)
            )
        """)
        logger.info("✓ Table 'project_members' ready")
        
        # Activity logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                dataset_id VARCHAR(255) NOT NULL,
                user_id INT,
                action VARCHAR(255) NOT NULL,
                details JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
                INDEX idx_dataset_id (dataset_id),
                INDEX idx_created_at (created_at)
            )
        """)
        logger.info("✓ Table 'activity_logs' ready")

        # Dataset quality snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dataset_quality_snapshots (
                id INT AUTO_INCREMENT PRIMARY KEY,
                dataset_id VARCHAR(255) NOT NULL,
                overall_quality_score FLOAT NOT NULL,
                class_balance_score FLOAT NOT NULL,
                label_accuracy_score FLOAT NOT NULL,
                iou_consistency_score FLOAT NOT NULL,
                total_images INT NOT NULL,
                annotated_images INT NOT NULL,
                duplicate_count INT DEFAULT 0,
                near_duplicate_count INT DEFAULT 0,
                corrupt_count INT DEFAULT 0,
                blurry_count INT DEFAULT 0,
                full_snapshot JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                INDEX idx_quality_dataset_id (dataset_id),
                INDEX idx_quality_created_at (created_at)
            )
        """)
        logger.info("✓ Table 'dataset_quality_snapshots' ready")

        connection.commit()
        cursor.close()
        connection.close()

        logger.info("✅ All tables created successfully!")
        return True
        
    except Error as e:
        logger.error(f"✗ Error creating tables: {e}")
        return False


def initialize_database():
    """Initialize database and tables"""
    logger.info("🔧 Initializing MySQL database...")
    logger.info(f"📍 Host: {settings.db_host}:{settings.db_port}")
    logger.info(f"📊 Database: {settings.db_name}")
    
    if create_database():
        if create_tables():
            logger.info("🎉 Database initialization complete!")
            return True
    
    logger.error("❌ Database initialization failed!")
    return False


def check_db_connection():
    """Check if database connection is working"""
    connection = get_db_connection()
    if connection:
        connection.close()
        return True
    return False


if __name__ == "__main__":
    initialize_database()

