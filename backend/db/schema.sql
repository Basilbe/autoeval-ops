-- HISTORICAL ARTIFACT (Phase 0). Do not run this directly.
-- As of Phase 3, all schema changes go through Alembic migrations:
--   alembic revision -m "description"   (write it by hand, or use --autogenerate
--   as a starting point and review carefully)
--   alembic upgrade head
-- This file records what Phase 0 originally created.

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    api_key VARCHAR(255) UNIQUE,
    api_key_hash VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Organizations table
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    plan VARCHAR(50) DEFAULT 'free',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Projects table
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    github_repo_url VARCHAR(255),
    github_token_encrypted TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Evaluations table
CREATE TABLE evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    commit_hash VARCHAR(40),
    prompt_version VARCHAR(255),
    model_name VARCHAR(100),
    test_cases_count INT DEFAULT 0,
    status VARCHAR(50) DEFAULT 'pending',
    results_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Evaluation Results table
CREATE TABLE eval_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_id UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    metric_name VARCHAR(100),
    metric_value FLOAT,
    status VARCHAR(50) DEFAULT 'pass',
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Traces table
CREATE TABLE traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_id UUID REFERENCES evaluations(id) ON DELETE CASCADE,
    trace_data JSONB,
    latency_ms INT,
    cost_usd FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_organizations_user_id ON organizations(user_id);
CREATE INDEX idx_projects_org_id ON projects(org_id);
CREATE INDEX idx_evaluations_project_id ON evaluations(project_id);
CREATE INDEX idx_evaluations_created_at ON evaluations(created_at);
CREATE INDEX idx_eval_results_eval_id ON eval_results(eval_id);
CREATE INDEX idx_traces_eval_id ON traces(eval_id);


