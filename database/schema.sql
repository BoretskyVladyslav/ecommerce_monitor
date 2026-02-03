CREATE TABLE IF NOT EXISTS product_options (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    option_name VARCHAR(255) NOT NULL,
    status TINYINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_product_id (product_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    proxy TEXT,
    user_agent TEXT,
    cookies_path VARCHAR(255),
    status VARCHAR(50) DEFAULT 'Ready',
    last_active TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    session_id INT NOT NULL,
    status VARCHAR(50) NOT NULL,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS settings (
    setting_key VARCHAR(50) PRIMARY KEY,
    setting_value TEXT
);

-- Insert default values if they don't exist
INSERT IGNORE INTO settings (setting_key, setting_value) VALUES 
('threads', '1'),
('headless', '0'),
('delay_min', '2'),
('delay_max', '5'),
('session_pause', '60'),
('human_mode', '0');
