# 🧪 Beverage Laboratory: Carbonated Glass Edition

A premium, high-end "Beverage Laboratory" experience designed for the modern home scientist. Originally built for SodaStream chemistry, the laboratory has now expanded to support a comprehensive suite of extraction and synthesis environments—all encased in the stunning **Carbonated Glass** design system.

---

## 🌑 The Aesthetic: Carbonated Glass
The Beverage Laboratory introduces a cutting-edge visual framework that prioritizes premium aesthetics and intuitive data visualization across both the consumer-facing frontend and the Django Admin suite:
- **Glassmorphism Shell**: Translucent surfaces with deep backdrop blurs and subtle reflections.
- **Neon-Glow HSL**: Vibrant, high-contrast color tokens (Lime, Orange, Cyan) optimized for a deep charcoal dark mode.
- **High-Luminosity Calibration**: Recalibrated text tokens (80-90% brightness) and enhanced placeholder contrast (65%) for perfect readability across all display types.
- **Modern Typography**: High-legibility "Outfit" font system for a clean, tech-first readout.
- **Unified Administration**: The native Django admin has been entirely overhauled to match the frontend, replacing legacy layouts with responsive Flexbox/Grid systems and dynamic glass elements.

## 🚀 Laboratory Environments

The application operates fundamentally split into three distinct laboratory environments:

### 💧 1. Soda Laboratory
- **Symphonic Formulation**: Precisely catalog syrups, flavor drops, and additives.
- **3-Tiered Recommendation Engine**: Programmatic analysis suggesting compatible secondary and tertiary compounds based on molecular category and potency.
- **Automated Lexicon**: Deterministic laboratory-grade naming for experimental mixes (e.g., *Atomic Citrus Blast*, *Neural Berry Pulse*).

### ☕ 2. Coffee Extraction Lab
- **Hyper-Specific Telemetry**: Records critical variables including:
  - **Extraction Method**: Espresso, Pour Over, French Press, AeroPress, Cold Brew.
  - **Grind Dialing**: Fine to Coarse granular control.
  - **Thermodynamics**: Real-time tracking of Water Temperature (Celsius/Fahrenheit).
  - **Time/Volume Yield**: Millisecond extraction logging.
- **Origin Analytics**: Logs coffee bean origin, roast level, and specific processing methods.

### ❄️ 3. Cryo-Slushie Lab
- **Liquid/Sugar Parity**: Real-time ratio monitors enforcing the strict 5:1 volumetric rule required to maintain frozen texture without freezing the auger.

---

## 🧠 AI Laboratory Assistant (Neural Mixology)

The Laboratory now features a dedicated **Neural Substrate** that assists in advanced flavor discovery and synthesis reporting.

### 📡 Multi-Substrate Support
The Assistant is compatible with a wide range of LLM providers, configurable via the **Laboratory Settings Hub**:
- **Cloud Providers**: OpenAI (GPT-4), Anthropic (Claude 3), Google (Gemini 1.5).
- **Local Inferencing**: Native Ollama support (Mistral, Llama 3, etc.) and AnythingLLM integrations.
- **VRAM Pre-Warming**: Automates a "Status Pulse" heartbeat that proactively loads local models into the GPU/VRAM on system load, ensuring zero-latency response times during active synthesis.

### 💡 Recommended Models (Quality & Speed)
When running **Ollama** locally, selecting the correct model is vital for maintaining responsive suggestion latency (ideally under 5 seconds) without sacrificing schema parsing reliability:
- **Small-Scale Models (Recommended)**: Use smaller, instruction-tuned models like `gemma4:e4b`, `gemma2:9b`, or `llama3:8b`. These have small footprints, load rapidly in consumer VRAM (such as an RTX 3080/4080 series), and generate tokens quickly.
- **Mixture of Experts (MoE)**: MoE models (like Mixtral) offer high intelligence with active parameter optimization, allowing complex mixology routing with fast token output.
- **Why Smaller is Better**: Because suggestion prompts rely on exact matching against the static Laboratory Registry, smaller models excel at structured tasks when kept at a low-to-medium temperature (`0.2` - `0.5`). Larger reasoning models can add unnecessary latency without improving keyword-matching success.

### 🧪 Synthesis Protocols
- **Molecular Affinity Matches**: The Assistant analyzes your current compound and proactively discovers matches based on chemical resonance and flavor science.
- **"Surprise Me" (Random Pairing)**: Initiates an autonomous pairing protocol that constructs a viable 3-component formula based on the current laboratory mode.
- **Synthesis Reports**: After every successful mix, the Assistant generates a 2-paragraph "Molecular Synergy Report," detailing the expected flavor body and chemical harmony of the result.

---

## 📊 System Architecture & Telemetry

### 📡 External Integrations (Target: Mealie)
The Beverage Laboratory does not exist in a silo. It connects seamlessly to your external Recipe endpoints.
- **API Persistence**: Secure, database-backed storage of your self-hosted Mealie Node URL and Private API Tokens.
- **1-Click Sync**: "Push to Mealie" rapid-action dispatching on all laboratory formulas.
- **Payload Translation**: Automatically maps specialized lab data (Intensities, Milliliters, Grams, Temperatures) into the standardized Mealie JSON Recipe Format without any data loss.

### 🧠 Central Command Dashboard
- **Dynamic Hall of Fame**: Real-time, theme-aware telemetry on aggregate laboratory performance:
    - **MVP Flavors**: Most utilized baseline compounds for the active lab.
    - **Leading Profiles**: Highest rated formulation categories.
    - **Signature Mixes**: Most historically reproduced formulas.

### 🛡️ Archival & Data Insurance
- **Vertical Navigation Hub**: Clean, component-based settings architectures.
- **Dossier Export**: Complete laboratory dump (Flavors, Recipes, History) into a single archival JSON format.
- **Target Merging**: Re-integration protocol prioritizing existing chemical identities to prevent database duplication.

---

## 🗺️ Architectural Topology

```mermaid
graph TD
    subgraph Frontend [UI: Carbonated Glass Environment]
        LabMod[Laboratory Mode Toggle] --> SODA[Soda Lab]
        LabMod --> COFF[Coffee Lab]
        LabMod --> CRYO[Cryo-Slushie Lab]
        Console[AI Assistant Terminal]
        UI_Admin[Unified Django Admin]
    end

    subgraph Core [Django Backend Core]
        Ing[Ingredient Registry]
        Form[Formula Templates]
        Rec[Recipe Objects]
        AI_Svc[AIAssistant Service]
        SysConf[SystemConfiguration Singleton]
        
        SODA --> Form
        COFF --> Form
        CRYO --> Form
        Form --> Rec
        Ing --> Rec
        Rec --> AI_Svc
    end

    subgraph Data [Containerized Persistence]
        DB[(PostgreSQL 16)]
        Rec --> DB
        Ing --> DB
        SysConf --> DB
    end
    
    subgraph Neural [AI Substrate Layer]
        Ollama[Local: Ollama VRAM]
        Cloud[Cloud: Gemini/OpenAI]
        AI_Svc --> Ollama
        AI_Svc --> Cloud
    end

    subgraph External [External Endpoints]
        Mealie[Mealie Self-Hosted Instance]
        Export[JSON Archival Payload]
        
        Settings[Settings Hub] --> Export
        Settings --> SysConf
        Rec -- "REST API Push" --> Mealie
    end
```

---

## 🛠️ Laboratory Stack

- **Framework**: Django 6.x (Python 3.12+)
- **AI Engine**: Multi-LLM Orchestration (Ollama, Gemini, OpenAI, Claude)
- **Database**: PostgreSQL 16 (Containerized)
- **UI Engine**: Custom Carbonated Glass CSS (Vanilla & HSL-mapped)
- **Networking**: `requests` for robust REST API dispatching
- **Deployment**: Docker Compose Orchestration
- **Performance**: Gunicorn production server with health-check monitoring

---

## 🧪 Installation Protocols

The laboratory terminal will be accessible at `http://localhost:8000`.

### ⚡ Quick Start (Recommended)
To start the application container stack immediately:
```bash
docker compose up -d --build
```

### 🔑 Default Credentials
- **Username**: `admin`
- **Password**: `adminpass123` (loaded via `.env`)

### 💾 Database Backup & Recovery
The system includes a cross-platform backup and restore utility that executes database operations against the running container.

#### 1. Database Backup
To generate a compressed database dump:
```bash
python backup.py --backup
```
Backups are compressed and saved in the `backups/` directory (e.g., `backups/backup_20260612_181534.sql.gz`).

#### 2. Database Restore
To restore database state from a compressed backup file:
```bash
python backup.py --restore backups/backup_YYYYMMDD_HHMMSS.sql.gz
```
*Note: This command will cleanly rebuild the schemas and load all data.*


### 🛡️ Ubuntu 24.04 (Noble Numbat) Production Note
If deploying on Ubuntu 24.04, **do not use the Snap version of Docker**. The Snap sandbox interferes with the `nftables` bridge routing required for inter-container communication (specifically between `web` and `db`).

**Recommended Setup:**
1. Uninstall Snap Docker: `sudo snap remove docker`
2. Install the [Official Docker Engine](https://docs.docker.com/engine/install/ubuntu/) via `apt`.
3. Ensure `net.ipv4.ip_forward=1` is enabled in your kernel settings.
4. If connectivity issues persist, a system reboot is required to synchronize the `DOCKER-ISOLATION` iptables chains.

**Note on Permissions:**
If you receive a `Permission denied` error for `entrypoint.sh` after a pull, it is because Docker volume mounts can sometimes override the container's internal execution bits. Run this on your host machine to fix it:
```bash
chmod +x entrypoint.sh
```

### 💻 Manual Configuration (Developer Mode)

1. **Environment Setup**:
   Copy the laboratory template to initiate your local config:
   ```bash
   cp .env.template .env
   ```
   *Note: Ensure the `DATABASE_HOST` is set to `localhost` if running outside of Docker.*

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Database Migration**:
   ```bash
   python manage.py migrate
   ```
   *Note: If starting fresh, the migrations have been squashed into an initial state for better performance.*

4. **Migration Cleanup Protocol**:
   To finalize a consolidated history:
   1. Confirm your current database is fully migrated.
   2. Remove the old migration files (0001-0008).
   3. Update the squashed migration file by removing the `replaces` field.

5. **Initialize Server**:
   ```bash
   python manage.py runserver
   ```

---

## ⚖️ License
MIT License - Developed for high-precision home experimentation.