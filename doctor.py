#!/usr/bin/env python
"""Workspace Health Diagnostics script for BeverageLab."""

import os
import sys
import socket
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("doctor")


def load_env_file():
    """Manually parse .env file to load env vars for local run."""
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    try:
                        k, v = stripped.split('=', 1)
                        # Remove quotes if present
                        v = v.strip('"').strip("'")
                        os.environ.setdefault(k.strip(), v.strip())
                    except ValueError:
                        pass


def run_diagnostics() -> bool:
    print("------------------------------------------------")
    print("🔬 BEVERAGE LABORATORY DIAGNOSTIC SYSTEM (DOCTOR)")
    print("------------------------------------------------")
    
    # 1. Environment Variable Checks
    print("\n[1/4] Verifying Environment Variables...")
    required_vars = [
        'SECRET_KEY', 
        'POSTGRES_DB', 
        'POSTGRES_USER', 
        'POSTGRES_PASSWORD', 
        'DATABASE_HOST', 
        'DATABASE_PORT'
    ]
    missing = []
    for var in required_vars:
        val = os.environ.get(var)
        if not val:
            missing.append(var)
            print(f"❌ {var}: Missing!")
        else:
            # Mask sensitive values
            display_val = val if var not in ['SECRET_KEY', 'POSTGRES_PASSWORD'] else "********"
            print(f"✅ {var}: Configured ({display_val})")
            
    if missing:
        print(f"\n❌ Diagnostic failed: Missing required environment variables: {', '.join(missing)}")
        return False
        
    # 2. Database Connectivity and Migration Check
    print("\n[2/4] Verifying Database Reachability & Migration Status...")
    db_host = os.environ.get('DATABASE_HOST')
    db_port = int(os.environ.get('DATABASE_PORT', '5432'))
    
    # Try raw socket first
    try:
        s = socket.create_connection((db_host, db_port), timeout=3)
        s.close()
        print(f"✅ TCP Port {db_host}:{db_port} is reachable.")
    except Exception as e:
        print(f"❌ TCP Port {db_host}:{db_port} is unreachable: {e}")
        return False
        
    # Setup Django programmatically
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'soda_mixer.settings')
        import django
        django.setup()
    except Exception as e:
        print(f"❌ Failed to initialize Django environment: {e}")
        return False
        
    try:
        from django.db import connections
        from django.db.migrations.executor import MigrationExecutor
        
        connection = connections['default']
        connection.prepare_database()
        executor = MigrationExecutor(connection)
        
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            print(f"⚠️ Warning: There are {len(plan)} unapplied migrations!")
            for migration, backward in plan:
                print(f"  - Unapplied: {migration}")
        else:
            print("✅ All database migrations are fully applied.")
    except Exception as e:
        print(f"❌ Database connection or migration query failed: {e}")
        return False
        
    # 3. LLM Configuration & Status Pulse
    print("\n[3/4] Verifying AI Assistant Substrate...")
    try:
        from soda_mixer.flavors.ai_service import AIAssistant
        
        provider = AIAssistant.get_default_provider()
        if not provider:
            print("⚠️ Warning: No active LLM provider configured or enabled.")
        else:
            print(f"✅ Default Provider: {provider.name} ({provider.provider_type})")
            print(f"✅ Default Model: {provider.default_model or 'Not configured'}")
            print(f"✅ Thinking Enabled: {provider.enable_thinking} (Effort: {provider.thinking_effort})")
            
            # Check status
            status = AIAssistant.check_status()
            print(f"⚡ AI Assistant Connection Status: {status.upper()}")
    except Exception as e:
        print(f"❌ AI Assistant service check failed: {e}")
        
    # 4. External Integrations
    print("\n[4/4] Verifying External Integrations (Mealie)...")
    try:
        from soda_mixer.flavors.models import SystemConfiguration
        config = SystemConfiguration.get_config()
        if not config.mealie_url or not config.mealie_api_key:
            print("ℹ️ Mealie is not configured (optional).")
        else:
            print(f"✅ Mealie URL: {config.mealie_url}")
            # Try connecting
            import requests
            try:
                # Get request with timeout
                resp = requests.get(config.mealie_url.rstrip('/') + '/api/about', timeout=3)
                if resp.status_code == 200:
                    print("✅ Mealie instance is reachable and healthy.")
                else:
                    print(f"⚠️ Mealie responded with status code {resp.status_code}.")
            except Exception as conn_err:
                print(f"⚠️ Could not establish connection to Mealie: {conn_err}")
    except Exception as e:
         print(f"❌ External integration check failed: {e}")
         
    print("\n------------------------------------------------")
    print("✅ DIAGNOSTICS COMPLETE")
    print("------------------------------------------------")
    return True


if __name__ == '__main__':
    load_env_file()
    success = run_diagnostics()
    sys.exit(0 if success else 1)
