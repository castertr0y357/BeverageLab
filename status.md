# Project Status - BeverageLab

## 📋 Todo List
- [ ] Implement additional creative AI features as requested by user

## 🛠️ Completed Tasks
- [x] Implemented brand tracking for flavor ingredients: added a nullable `brand` CharField to `Ingredient` and replaced `name` unique constraint with a `unique_together = ['name', 'brand']` constraint. Updated AI profiling APIs to prefix name with brand for accurate results, added dynamic formatting logic to display the brand on the synthesis page only when duplicate flavor names exist in active inventory, and updated ingredient list, detail pages, and modals to support brand tracking.
- [x] Fixed ingredient analysis not adjusting base and accent suitability scores: explicitly defined suitability metrics in the single-ingredient analysis LLM prompt and updated the bulk analysis target selection query to capture ingredients with default suitability scores (3.0/3.0) even if other stats are customized.
- [x] Fixed base and accent scores visibility in the UI by displaying them textually on all ingredient cards (Step 1 grid, recommendations, recipe creation) and detail screens (ingredients, formulas/recipes). Implemented dynamic recommended and unorthodox base/accent partitioning on the Formula Synthesis creation page (`create_recipe.html`).
- [x] Implemented AI-synthesized base and accent suitability scoring for ingredients (`base_suitability` and `accent_suitability` in `Ingredient` model), including prompt structures, mock responses, database backfill migration, and dynamic frontend partitioning on the Home page grid for Standard vs. Experimental recommendation modes.
- [x] Added batch scale toggle (0.5L and 1.0L) and dual-unit (ml / oz) displays for ingredients in the recipes details view (`recipe_detail.html`) using client-side JavaScript formatting and scaling.
- [x] Documented user manual visual inspection protocol in workspace LLM rules files (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.windsurfrules`).
- [x] Synchronized workspace rules files (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, and `.windsurfrules`) with the latest global template `C:\Users\caste\.gemini\project.md`, customizing the project name (`BeverageLab`) and the verification command
- [x] Implemented a toggle in the database schema and UI configurations to enable or disable the model's internal thinking/reasoning process and configure the level of thinking effort (specifically passing the 'think' option to Ollama for local models like Gemma/DeepSeek-R1 and 'reasoning_effort' to OpenAI reasoning models like o1/o3-mini)
- [x] Fixed component list filtering when swapping between lab modes (Soda, Coffee, Cryo) on the home page. Added default coffee bean ingredients and adjusted compatible systems in the database, and restricted Step 1 library display to valid base components.
- [x] Sorted the compounds in the reagent registry alphabetically across all types and profiles (ordered by name instead of category and name)
- [x] Detected local environment (Django + PostgreSQL in Docker Compose)
- [x] Set project verification command `docker compose run --rm web python manage.py test`
- [x] Restructured views layer into a modular package (`soda_mixer/flavors/views/`)
- [x] Added comprehensive python type hinting across views, recommendations, middleware, and AI services
- [x] Configured Python standard logging with formatted operational messages across the views and AI services
- [x] Created `.env.example` to prevent configuration drift
- [x] Implemented a test suite with 27 unit and integration tests covering models, recommendations, settings, view endpoints, and mocked AI endpoints
- [x] Configured Django settings to parse `CSRF_TRUSTED_ORIGINS` from environment variables, preventing origin-checking CSRF failures in production, updated env configuration files, and mapped them in `docker-compose.yml` to propagate them to the web container
- [x] Removed host port mapping for the PostgreSQL database container, isolating it to the internal Docker network to prevent host port conflicts
- [x] Separated local development volume mount into `docker-compose.override.yml` to prevent Coolify production container code from being overwritten by stale/empty host volumes
- [x] Audited project and implemented startup configuration validation checks in `settings.py` for all required environment variables
- [x] Implemented `MOCK_MODE` offline mode support across the AI synthesis service and Mealie recipe export views
- [x] Created `doctor.py` diagnostic system to verify migrations, environment variables, LLM provider states, and integrations
- [x] Created `backup.py` utility to automate compressed SQL database backup and recovery operations
- [x] Updated `README.md` with Quick Start instructions, default admin credentials, and backup/restore documentation


## 🏗️ Architectural Notes
- Containerized Django 5.0 application.
- PostgreSQL database isolated within the internal Docker network, backing model data.
- Gunicorn web server configured with gevent async workers.
- Modular Views Package under `soda_mixer/flavors/views/` containing `main.py`, `ingredients.py`, `recipes.py`, `ai.py`, `auth.py`, and `settings.py`.
- Configurable `CSRF_TRUSTED_ORIGINS` via environment variables to allow flexible hosting configurations.
- Formatted log messages following standard laboratory pattern: `[Job/Operation] - [Category/Level] - [Detail Message]`.
- Mock-isolated test suite to ensure stable, reliable runs.
- Split Docker Compose configuration: production-safe `docker-compose.yml` without runtime volume mounts, and local-only `docker-compose.override.yml` for source code volume mounting and hot-reloading.
- Added AI-synthesized base and accent suitability scoring model properties (`base_suitability` and `accent_suitability` fields on `Ingredient`).
- Implemented dynamic frontend partitioning on the Home page grid to separate safe bases from unorthodox bases based on standard vs. experimental mode.


