CREATE DATABASE IF NOT EXISTS teleskillhub DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE teleskillhub;

CREATE TABLE IF NOT EXISTS departments (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
  id INT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(100) NOT NULL UNIQUE,
  department_id INT NOT NULL,
  is_admin TINYINT(1) DEFAULT 0,
  CONSTRAINT fk_users_dept FOREIGN KEY (department_id) REFERENCES departments(id)
);

CREATE TABLE IF NOT EXISTS skills (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(200) NOT NULL UNIQUE,
  description TEXT NULL,
  owner_id INT NOT NULL,
  visibility_type VARCHAR(20) NOT NULL DEFAULT 'public',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_skills_owner FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS skill_permissions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  skill_id INT NOT NULL,
  scope_type VARCHAR(20) NOT NULL,
  target_id INT NOT NULL,
  CONSTRAINT fk_permissions_skill FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS skill_versions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  skill_id INT NOT NULL,
  version_no INT NOT NULL,
  archive_name VARCHAR(255) NOT NULL,
  extracted_path VARCHAR(500) NOT NULL,
  changelog TEXT NULL,
  security_score INT DEFAULT 100,
  security_report JSON NULL,
  created_by INT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uk_skill_version UNIQUE (skill_id, version_no),
  CONSTRAINT fk_versions_skill FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE,
  CONSTRAINT fk_versions_user FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS skill_files (
  id INT PRIMARY KEY AUTO_INCREMENT,
  version_id INT NOT NULL,
  path VARCHAR(500) NOT NULL,
  is_dir TINYINT(1) DEFAULT 0,
  size INT DEFAULT 0,
  content_preview TEXT NULL,
  CONSTRAINT fk_files_version FOREIGN KEY (version_id) REFERENCES skill_versions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS skill_downloads (
  id INT PRIMARY KEY AUTO_INCREMENT,
  skill_id INT NOT NULL,
  version_id INT NOT NULL,
  downloaded_by INT NOT NULL,
  downloaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_download_skill FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE,
  CONSTRAINT fk_download_version FOREIGN KEY (version_id) REFERENCES skill_versions(id) ON DELETE CASCADE,
  CONSTRAINT fk_download_user FOREIGN KEY (downloaded_by) REFERENCES users(id)
);

INSERT INTO departments(name) VALUES ('Platform'), ('AI'), ('Security')
  ON DUPLICATE KEY UPDATE name = VALUES(name);

INSERT INTO users(id, username, department_id, is_admin) VALUES
  (1, 'admin', 1, 1),
  (2, 'alice', 2, 0),
  (3, 'bob', 3, 0)
  ON DUPLICATE KEY UPDATE username = VALUES(username), department_id = VALUES(department_id), is_admin = VALUES(is_admin);
